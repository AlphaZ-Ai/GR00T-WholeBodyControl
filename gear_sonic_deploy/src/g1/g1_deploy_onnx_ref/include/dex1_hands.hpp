#pragma once
#include <iostream>

// Protocol/ranges from xr_teleoperate robot_hand_unitree.py and robot_arm.py
// (817fb00c63cde15e5f24a0f8fa08e1e33ed89d3b). SONIC remains the only body writer.
#include <algorithm>
#include <array>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <unitree/idl/go2/MotorCmds_.hpp>
#include <unitree/idl/go2/MotorStates_.hpp>
#include <unitree/idl/hg/LowCmd_.hpp>
#include <unitree/idl/hg/LowState_.hpp>
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>

namespace dex1 {
constexpr std::array<int, 2> motor_indices{31, 33};
constexpr double open_q = 5.4;
constexpr double kp = 5.0;
constexpr double kd = 0.05;
constexpr double max_feedback_delta = 0.18;

// The deployment project uses -ffast-math, which can remove std::isfinite.
inline bool finite(double value) {
    return (std::bit_cast<std::uint64_t>(value) & 0x7ff0000000000000ULL)
        != 0x7ff0000000000000ULL;
}

// All nonzero SONIC index/middle/ring grip presets share index-distal = 1.5.
// Left Dex3 flexion is negative, right is positive; zero means open.
inline std::optional<double> closure(const std::array<double, 7>& pose, bool left) {
    for (double q : pose) if (!finite(q)) return std::nullopt;
    return std::clamp((left ? -pose[4] : pose[4]) / 1.5, 0.0, 1.0);
}

inline double target(double measured, std::optional<double> close, double max_close) {
    if (!close) return measured;  // No input: hold the measured position.
    const double desired = open_q * (1.0 - std::clamp(*close, 0.0, max_close));
    return std::clamp(desired, measured - max_feedback_delta, measured + max_feedback_delta);
}
}  // namespace dex1

class Dex1Hands {
    using Clock = std::chrono::steady_clock;
    using Cmd = unitree_go::msg::dds_::MotorCmds_;
    using State = unitree_go::msg::dds_::MotorStates_;
    struct Side {
        double q = 0, dq = 0, last_command = 0;
        bool valid = false;
        Clock::time_point stamp{}, command_stamp{};
        std::optional<double> close;
        std::shared_ptr<unitree::robot::ChannelPublisher<Cmd>> publisher;
        std::shared_ptr<unitree::robot::ChannelSubscriber<State>> subscriber;
    };
    std::mutex mutex_;
    std::array<Side, 2> sides_;
    bool internal_ = false, stopped_ = false;
    // Side swap: the Dex1 service names each gripper by MOTOR ID (id 0 -> "left", id 1 ->
    // "right"). On a robot whose id-0 motor sits on the RIGHT arm, the physical right
    // gripper answers on rt/dex1/left (and vice versa); --dex1-swap-sides fixes that here
    // so the policy's left/right stay physical.
    bool swap_sides_ = false;
    double max_close_ = 1.0;
    size_t wire(size_t side) const { return swap_sides_ ? 1 - side : side; }

    void update(size_t side, double q, double dq) {
        auto& s = sides_[side];
        s.valid = dex1::finite(q) && dex1::finite(dq) && q >= -0.18 && q <= 5.58;
        if (!s.valid) return;
        s.q = q; s.dq = dq; s.stamp = Clock::now();
    }

    template<class Motor> void command(Side& s, Motor& m) {
        const auto now = Clock::now();
        if (!s.valid || now - s.stamp > std::chrono::milliseconds(250)) {
            m.mode() = 0; m.kp() = 0; m.kd() = 0; m.tau() = 0; m.dq() = 0;
            return;
        }
        double q = dex1::target(s.q, s.close, max_close_);
        if (s.command_stamp.time_since_epoch().count() != 0 && s.close && !stopped_) {
            const double dt = std::min(0.02, std::chrono::duration<double>(now - s.command_stamp).count());
            q = std::clamp(q, s.last_command - 36.0 * dt, s.last_command + 36.0 * dt);
            q = std::clamp(q, s.q - dex1::max_feedback_delta, s.q + dex1::max_feedback_delta);
        }
        m.mode() = 1; m.q() = q; m.dq() = 0; m.tau() = 0;
        m.kp() = stopped_ ? 0 : dex1::kp;
        m.kd() = dex1::kd;
        s.last_command = q; s.command_stamp = now;
    }

public:
    void initialize(bool internal, bool swap_sides = false) {
        internal_ = internal;
        swap_sides_ = swap_sides;
        if (swap_sides_) std::cout << "[INFO] Dex1 sides swapped: physical left <-> service/motor 'right'" << std::endl;
        if (internal_) return;
        for (size_t i = 0; i < 2; ++i) {
            auto& s = sides_[i];
            const std::string ns = wire(i) == 0 ? "rt/dex1/left" : "rt/dex1/right";
            s.publisher = std::make_shared<unitree::robot::ChannelPublisher<Cmd>>(ns + "/cmd");
            s.publisher->InitChannel();
            s.subscriber = std::make_shared<unitree::robot::ChannelSubscriber<State>>(ns + "/state");
            s.subscriber->InitChannel([this, i](const void* message) {
                const auto& state = *static_cast<const State*>(message);
                std::lock_guard<std::mutex> lock(mutex_);
                if (state.states().size() != 1) { sides_[i].valid = false; return; }
                update(i, state.states()[0].q(), state.states()[0].dq());
            }, 1);
        }
    }

    void updateInternal(const unitree_hg::msg::dds_::LowState_& state) {
        if (!internal_) return;
        std::lock_guard<std::mutex> lock(mutex_);
        for (size_t i = 0; i < 2; ++i) {
            const auto& m = state.motor_state().at(dex1::motor_indices[wire(i)]);
            update(i, m.q(), m.dq());
        }
    }

    void setTargets(const std::array<double, 7>& left, bool left_valid,
                    const std::array<double, 7>& right, bool right_valid, double max_close) {
        std::lock_guard<std::mutex> lock(mutex_);
        max_close_ = dex1::finite(max_close) ? std::clamp(max_close, 0.2, 1.0) : 0.2;
        sides_[0].close = left_valid ? dex1::closure(left, true) : std::nullopt;
        sides_[1].close = right_valid ? dex1::closure(right, false) : std::nullopt;
    }

    void applyInternal(unitree_hg::msg::dds_::LowCmd_& cmd) {
        if (!internal_) return;
        std::lock_guard<std::mutex> lock(mutex_);
        for (size_t i = 0; i < 2; ++i) command(sides_[i], cmd.motor_cmd().at(dex1::motor_indices[wire(i)]));
    }

    void writeOnce() {
        if (internal_) return;
        std::lock_guard<std::mutex> lock(mutex_);
        for (auto& s : sides_) {
            if (!s.publisher) continue;
            Cmd cmd; cmd.cmds().resize(1); command(s, cmd.cmds()[0]);
            s.publisher->Write(cmd);
        }
    }

    std::array<double, 3> state(size_t side) {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto& s = sides_.at(side);
        return {s.q, s.dq, s.last_command};
    }

    void stop() {
        std::lock_guard<std::mutex> lock(mutex_);
        stopped_ = true;
        for (auto& s : sides_) s.close.reset();
    }
};

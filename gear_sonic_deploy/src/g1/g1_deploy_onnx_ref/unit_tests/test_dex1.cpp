#include <gtest/gtest.h>
#include <limits>
#include <thread>
#include <unitree/robot/channel/channel_factory.hpp>
#include "../include/dex1_hands.hpp"

TEST(Dex1, SonicGripMappingAndFeedbackLimits) {
    const std::array<double, 7> left{-.5, .7, .7, -1.5, -1.5, -.6, -1.5};
    auto right = left;
    for (auto& q : right) q = -q;
    EXPECT_DOUBLE_EQ(*dex1::closure(left, true), 1.0);
    EXPECT_DOUBLE_EQ(*dex1::closure(right, false), 1.0);
    EXPECT_DOUBLE_EQ(*dex1::closure({}, true), 0.0);
    EXPECT_NEAR(dex1::target(2.7, 1.0, 1.0), 2.52, 1e-9);
    EXPECT_NEAR(dex1::target(2.7, 0.0, 1.0), 2.88, 1e-9);
    EXPECT_DOUBLE_EQ(dex1::target(4.32, 1.0, .2), 4.32);
    EXPECT_DOUBLE_EQ(dex1::target(1.2, std::nullopt, 1.0), 1.2);
    right[0] = std::numeric_limits<double>::quiet_NaN();
    EXPECT_FALSE(dex1::closure(right, false));
}

TEST(Dex1, InternalSlotsHoldAndStop) {
    Dex1Hands hands;
    hands.initialize(true);
    unitree_hg::msg::dds_::LowState_ state;
    state.motor_state()[31].q() = 2.0;
    state.motor_state()[33].q() = 3.0;
    hands.updateInternal(state);
    unitree_hg::msg::dds_::LowCmd_ cmd;
    for (auto& m : cmd.motor_cmd()) m.q() = 12.0;
    hands.applyInternal(cmd);
    EXPECT_FLOAT_EQ(cmd.motor_cmd()[31].q(), 2.0);
    EXPECT_FLOAT_EQ(cmd.motor_cmd()[33].q(), 3.0);
    EXPECT_FLOAT_EQ(cmd.motor_cmd()[31].kp(), 5.0);
    for (int i = 0; i < 35; ++i)
        if (i != 31 && i != 33) EXPECT_FLOAT_EQ(cmd.motor_cmd()[i].q(), 12.0);
    hands.stop();
    hands.applyInternal(cmd);
    EXPECT_FLOAT_EQ(cmd.motor_cmd()[31].kp(), 0.0);
    EXPECT_FLOAT_EQ(cmd.motor_cmd()[33].kp(), 0.0);
}

TEST(Dex1, MissingInvalidAndStaleFeedbackDisablesMotors) {
    Dex1Hands hands;
    hands.initialize(true);
    unitree_hg::msg::dds_::LowCmd_ cmd;
    hands.applyInternal(cmd);
    EXPECT_EQ(cmd.motor_cmd()[31].mode(), 0);
    unitree_hg::msg::dds_::LowState_ state;
    state.motor_state()[31].q() = std::numeric_limits<float>::quiet_NaN();
    state.motor_state()[33].q() = 2.0;
    hands.updateInternal(state);
    hands.applyInternal(cmd);
    EXPECT_EQ(cmd.motor_cmd()[31].mode(), 0);
    EXPECT_EQ(cmd.motor_cmd()[33].mode(), 1);
    std::this_thread::sleep_for(std::chrono::milliseconds(270));
    hands.applyInternal(cmd);
    EXPECT_EQ(cmd.motor_cmd()[33].mode(), 0);
    EXPECT_FLOAT_EQ(cmd.motor_cmd()[33].kp(), 0);
}

TEST(Dex1, ExternalServiceProtocolOnLoopback) {
    using Cmd = unitree_go::msg::dds_::MotorCmds_;
    using State = unitree_go::msg::dds_::MotorStates_;
    // Separate DDS domain and loopback: never reaches the physical robot.
    unitree::robot::ChannelFactory::Instance()->Init(141, "lo");
    Dex1Hands hands;
    hands.initialize(false);
    unitree::robot::ChannelPublisher<State> publisher("rt/dex1/left/state");
    publisher.InitChannel();
    std::mutex mutex;
    std::optional<Cmd> received;
    unitree::robot::ChannelSubscriber<Cmd> subscriber("rt/dex1/left/cmd");
    subscriber.InitChannel([&](const void* message) {
        std::lock_guard<std::mutex> lock(mutex);
        received = *static_cast<const Cmd*>(message);
    }, 1);
    State state; state.states().resize(1); state.states()[0].q() = 2.7;
    bool ready = false;
    for (int i = 0; i < 100; ++i) {
        publisher.Write(state);
        hands.writeOnce();
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        std::lock_guard<std::mutex> lock(mutex);
        if (received && received->cmds().size() == 1 && received->cmds()[0].kp() == 5.0) {
            EXPECT_NEAR(received->cmds()[0].q(), 2.7, 1e-6);
            EXPECT_NEAR(received->cmds()[0].kd(), 0.05, 1e-6);
            ready = true;
            break;
        }
    }
    EXPECT_TRUE(ready) << "No Dex1 command received on the reference DDS topic/type";
}

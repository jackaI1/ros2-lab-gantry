#include "gantry_monitor/limits.hpp"
#include <memory>
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/joint_state.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/string.hpp>

class Monitor final : public rclcpp::Node {
 public:
  Monitor() : Node("trajectory_safety_monitor") {
    // Limits are versioned with the operator playbooks rather than mutable at runtime.
    warning_ = create_publisher<std_msgs::msg::String>("/gantry/safety_warning", 10);
    stop_ = create_publisher<std_msgs::msg::Bool>("/gantry/stop_requested", 10);
    subscription_ = create_subscription<sensor_msgs::msg::JointState>(
      "/joint_states", 10, [this](sensor_msgs::msg::JointState::ConstSharedPtr msg) {
        std_msgs::msg::String result;
        result.data = gantry_monitor::check(msg->name, msg->position, msg->velocity);
        std_msgs::msg::Bool stop;
        stop.data = result.data != "OK";
        warning_->publish(result);
        stop_->publish(stop);
      });
  }
 private:
  rclcpp::Publisher<std_msgs::msg::String>::SharedPtr warning_;
  rclcpp::Publisher<std_msgs::msg::Bool>::SharedPtr stop_;
  rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr subscription_;
};
int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<Monitor>());
  rclcpp::shutdown();
  return 0;
}

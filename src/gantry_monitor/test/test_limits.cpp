#include "gantry_monitor/limits.hpp"
#include <gtest/gtest.h>
#include <limits>
using gantry_monitor::check;
const std::vector<std::string> names{"x_joint", "y_joint", "z_joint"};
TEST(Monitor, HealthyAndReordered) {
  EXPECT_EQ(check(names, {.04,.04,.01}, {0,0,0}), "OK");
  EXPECT_EQ(check({"z_joint","x_joint","y_joint"}, {.01,.04,.04}, {0,0,0}), "OK");
}
TEST(Monitor, AllTravelBounds) {
  for (int i=0; i<3; ++i) {
    std::vector<double> p{.04,.04,.01};
    p[i]=0;
    EXPECT_EQ(check(names,p,{0,0,0}),names[i]+" limit switch");
    p[i]=gantry_monitor::Limits{}.upper[i];
    EXPECT_EQ(check(names,p,{0,0,0}),names[i]+" limit switch");
  }
}
TEST(Monitor, SignedVelocity) {
  EXPECT_EQ(check(names,{.04,.04,.01},{.061,0,0}),"x_joint overspeed");
  EXPECT_EQ(check(names,{.04,.04,.01},{0,-.061,0}),"y_joint overspeed");
  EXPECT_EQ(check(names,{.04,.04,.01},{0,0,.06}),"OK");
}
TEST(Monitor, InvalidFailsClosed) {
  EXPECT_EQ(check(names,{.04,.04},{0,0,0}),"invalid_feedback");
  EXPECT_EQ(check({"x_joint","x_joint","z_joint"},{.04,.04,.01},{0,0,0}),"invalid_feedback");
  EXPECT_EQ(check(names,{.04,.04,.01},{0,std::numeric_limits<double>::quiet_NaN(),0}),"invalid_feedback");
  EXPECT_EQ(check({"x_joint"},{.04},{0}),"invalid_feedback");
}

// Copyright 2011 Google Inc. All Rights Reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#ifndef NINJA_TEST_H_
#define NINJA_TEST_H_

#include <string.h>

#include <string>

// A tiny testing framework inspired by googletest, but much simpler and
// faster to compile. It supports most things commonly used from googltest. The
// most noticeable things missing: EXPECT_* and ASSERT_* don't support
// streaming notes to them with operator<<, and for failing tests the lhs and
// rhs are not printed.
namespace testing {
class Test {
  bool failed_;
  int assertion_failures_;
 public:
  Test() : failed_(false), assertion_failures_(0) {}
  virtual ~Test() {}
  virtual void SetUp() {}
  virtual void TearDown() {}
  virtual void Run() = 0;

  bool Failed() const { return failed_; }
  int AssertionFailures() const { return assertion_failures_; }
  void AddAssertionFailure() { assertion_failures_++; }
  bool Check(bool condition, const char* file, int line, const char* error);
};
}

void RegisterTest(testing::Test* (*)(), const char*);

extern testing::Test* g_current_test;
#define TEST_F_(x, y, name)                                           \
  struct y : public x {                                               \
    static testing::Test* Create() { return g_current_test = new y; } \
    virtual void Run();                                               \
  };                                                                  \
  struct Register##y {                                                \
    Register##y() { RegisterTest(y::Create, name); }                  \
  };                                                                  \
  Register##y g_register_##y;                                         \
  void y::Run()

#define TEST_F(x, y) TEST_F_(x, x##y, #x "." #y)
#define TEST(x, y) TEST_F_(testing::Test, x##y, #x "." #y)

#define FRIEND_TEST(x, y) friend class x##y

#define EXPECT_EQ(a, b) \
  g_current_test->Check(a == b, __FILE__, __LINE__, #a " == " #b)
#define EXPECT_NE(a, b) \
  g_current_test->Check(a != b, __FILE__, __LINE__, #a " != " #b)
#define EXPECT_GT(a, b) \
  g_current_test->Check(a > b, __FILE__, __LINE__, #a " > " #b)
#define EXPECT_LT(a, b) \
  g_current_test->Check(a < b, __FILE__, __LINE__, #a " < " #b)
#define EXPECT_GE(a, b) \
  g_current_test->Check(a >= b, __FILE__, __LINE__, #a " >= " #b)
#define EXPECT_LE(a, b) \
  g_current_test->Check(a <= b, __FILE__, __LINE__, #a " <= " #b)
#define EXPECT_TRUE(a) \
  g_current_test->Check(static_cast<bool>(a), __FILE__, __LINE__, #a)
#define EXPECT_FALSE(a) \
  g_current_test->Check(!static_cast<bool>(a), __FILE__, __LINE__, #a)
#define EXPECT_STREQ(a, b) \
  g_current_test->Check(strcmp(a, b) == 0, __FILE__, __LINE__, #a " streq " #b)

#define ASSERT_EQ(a, b) \
  if (!EXPECT_EQ(a, b)) { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_NE(a, b) \
  if (!EXPECT_NE(a, b)) { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_GT(a, b) \
  if (!EXPECT_GT(a, b)) { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_LT(a, b) \
  if (!EXPECT_LT(a, b)) { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_GE(a, b) \
  if (!EXPECT_GE(a, b)) { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_LE(a, b) \
  if (!EXPECT_LE(a, b)) { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_TRUE(a)  \
  if (!EXPECT_TRUE(a))  { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_FALSE(a) \
  if (!EXPECT_FALSE(a)) { g_current_test->AddAssertionFailure(); return; }
#define ASSERT_NO_FATAL_FAILURE(a)                           \
  {                                                          \
    int fail_count = g_current_test->AssertionFailures();    \
    a;                                                       \
    if (fail_count != g_current_test->AssertionFailures()) { \
      g_current_test->AddAssertionFailure();                 \
      return;                                                \
    }                                                        \
  }
struct ScopedTempDir {
  /// Create a temporary directory and chdir into it.
  void CreateAndEnter(const std::string& name);

  /// Clean up the temporary directory.
  void Cleanup();

  /// The temp directory containing our dir.
  std::string start_dir_;
  /// The subdirectory name for our dir, or empty if it hasn't been set up.
  std::string temp_dir_name_;
};

#endif // NINJA_TEST_H_

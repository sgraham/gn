// Copyright 2013 Google Inc. All Rights Reserved.
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

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "base/command_line.h"
#include "build_config.h"
#include "test.h"

#if defined(OS_WIN)
#include <windows.h>
#else
#include <unistd.h>
#endif

struct RegisteredTest {
  testing::Test* (*factory)();
  const char* name;
  bool should_run;
};
// This can't be a vector because tests call RegisterTest from static
// initializers and the order static initializers run it isn't specified. So
// the vector constructor isn't guaranteed to run before all of the
// RegisterTest() calls.
static RegisteredTest tests[10000];
testing::Test* g_current_test;
static int ntests;

void RegisterTest(testing::Test* (*factory)(), const char* name) {
  tests[ntests].factory = factory;
  tests[ntests++].name = name;
}

namespace {

bool PatternMatchesString(const char* pattern, const char* str) {
  switch (*pattern) {
    case '\0':
    case '-':
      return *str == '\0';
    case '*':
      return (*str != '\0' && PatternMatchesString(pattern, str + 1)) ||
             PatternMatchesString(pattern + 1, str);
    default:
      return *pattern == *str && PatternMatchesString(pattern + 1, str + 1);
  }
}

bool TestMatchesFilter(const char* test, const char* filter) {
  // Split --gtest_filter at '-' into positive and negative filters.
  const char* const dash = strchr(filter, '-');
  const char* pos =
      dash == filter ? "*" : filter;  // Treat '-test1' as '*-test1'
  const char* neg = dash ? dash + 1 : "";
  return PatternMatchesString(pos, test) && !PatternMatchesString(neg, test);
}

#if defined(OS_WIN)
struct ScopedEnableVTEscapeProcessing {
  ScopedEnableVTEscapeProcessing() {
    console_ = GetStdHandle(STD_OUTPUT_HANDLE);
    CONSOLE_SCREEN_BUFFER_INFO csbi;
    if (GetConsoleScreenBufferInfo(console_, &csbi) &&
        GetConsoleMode(console_, &original_mode_)) {
      SetConsoleMode(console_, original_mode_ |
                                   ENABLE_VIRTUAL_TERMINAL_PROCESSING |
                                   DISABLE_NEWLINE_AUTO_RETURN);
    } else {
      console_ = INVALID_HANDLE_VALUE;
    }
  }

  ~ScopedEnableVTEscapeProcessing() {
    if (is_valid())
      SetConsoleMode(console_, original_mode_);
  }

  bool is_valid() const { return console_ != INVALID_HANDLE_VALUE; }

  HANDLE console_;
  DWORD original_mode_;
};
#endif

}  // namespace

bool testing::Test::Check(bool condition,
                          const char* file,
                          int line,
                          const char* error) {
  if (!condition) {
    printf("\n*** Failure in %s:%d\n%s\n", file, line, error);
    failed_ = true;
  }
  return condition;
}

int main(int argc, char** argv) {
  base::CommandLine::Init(argc, argv);

#if defined(OS_WIN)
  ScopedEnableVTEscapeProcessing enable_vt_processing;
#endif
  setvbuf(stdout, NULL, _IOLBF, BUFSIZ);

  int tests_started = 0;

  const char* test_filter = "*";
  for (int i = 1; i < argc; ++i) {
    const char kTestFilterPrefix[] = "--gtest_filter=";
    if (strncmp(argv[i], kTestFilterPrefix, strlen(kTestFilterPrefix)) == 0) {
      test_filter = &argv[i][strlen(kTestFilterPrefix)];
    }
  }

  int nactivetests = 0;
  for (int i = 0; i < ntests; i++)
    if ((tests[i].should_run = TestMatchesFilter(tests[i].name, test_filter)))
      ++nactivetests;

  const char* prefix = "";
  const char* suffix = "\n";
#if defined(OS_WIN)
  if (enable_vt_processing.is_valid())
#else
  if (isatty(1))
#endif
  {
    prefix = "\r";
    suffix = "\x1B[K";
  }
  bool passed = true;
  for (int i = 0; i < ntests; i++) {
    if (!tests[i].should_run)
      continue;

    ++tests_started;
    testing::Test* test = tests[i].factory();
    printf("%s[%d/%d] %s%s", prefix, tests_started, nactivetests, tests[i].name,
           suffix);
    test->SetUp();
    test->Run();
    test->TearDown();
    if (test->Failed())
      passed = false;
    delete test;
  }

  printf("\n%s\n", passed ? "PASSED" : "FAILED");
  fflush(stdout);
  return passed ? EXIT_SUCCESS : EXIT_FAILURE;
}

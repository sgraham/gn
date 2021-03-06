// Copyright 2016 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "test/test.h"
#include "tools/gn/test_with_scope.h"

// Checks that variables used inside template definitions aren't reported
// unused if they were declared above the template.
TEST(FunctionTemplate, MarkUsed) {
  TestWithScope setup;
  TestParseInput input(
      "a = 1\n"  // Unused outside of template.
      "template(\"templ\") {\n"
      "  print(a)\n"
      "}\n");
  ASSERT_FALSE(input.has_error());

  Err err;
  input.parsed()->Execute(setup.scope(), &err);
  ASSERT_FALSE(err.has_error());

  // Normally the loader calls CheckForUnusedVars() when it loads a file
  // since normal blocks don't do this check. To avoid having to make this
  // test much more complicated, just explicitly do the check to make sure
  // things are marked properly.
  setup.scope()->CheckForUnusedVars(&err);
  EXPECT_FALSE(err.has_error());
}

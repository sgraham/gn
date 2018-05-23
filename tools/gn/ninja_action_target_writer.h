// Copyright (c) 2013 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#ifndef TOOLS_GN_NINJA_ACTION_TARGET_WRITER_H_
#define TOOLS_GN_NINJA_ACTION_TARGET_WRITER_H_

#include <vector>

#include "base/gtest_prod_util.h"
#include "base/macros.h"
#include "tools/gn/ninja_target_writer.h"

class OutputFile;

// Writes a .ninja file for a action target type.
class NinjaActionTargetWriter : public NinjaTargetWriter {
 public:
  NinjaActionTargetWriter(const Target* target, std::ostream& out);
  ~NinjaActionTargetWriter() override;

  void Run() override;

 private:
  FRIEND_TEST_ALL_PREFIXES(NinjaActionTargetWriter,
                           WriteOutputFilesForBuildLine);
  FRIEND_TEST_ALL_PREFIXES(NinjaActionTargetWriter,
                           WriteOutputFilesForBuildLineWithDepfile);
  FRIEND_TEST_ALL_PREFIXES(NinjaActionTargetWriter,
                           WriteArgsSubstitutions);

  // Writes the Ninja rule for invoking the script.
  //
  // Returns the name of the custom rule generated. This will be based on the
  // target name, and will include the string "$unique_name" if there are
  // multiple inputs.
  std::string WriteRuleDefinition();

  // Writes the rules for compiling each source, writing all output files
  // to the given vector.
  //
  // input_deps are the dependencies common to all build steps.
  void WriteSourceRules(const std::string& custom_rule_name,
                        const std::vector<OutputFile>& input_deps,
                        std::vector<OutputFile>* output_files);

  // Writes the output files generated by the output template for the given
  // source file. This will start with a space and will not include a newline.
  // Appends the output files to the given vector.
  void WriteOutputFilesForBuildLine(const SourceFile& source,
                                    std::vector<OutputFile>* output_files);

  void WriteDepfile(const SourceFile& source);

  // Path output writer that doesn't do any escaping or quoting. It does,
  // however, convert slashes.  Used for
  // computing intermediate strings.
  PathOutput path_output_no_escaping_;

  DISALLOW_COPY_AND_ASSIGN(NinjaActionTargetWriter);
};

#endif  // TOOLS_GN_NINJA_ACTION_TARGET_WRITER_H_

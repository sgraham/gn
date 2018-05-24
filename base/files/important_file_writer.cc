// Copyright (c) 2011 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "base/files/important_file_writer.h"

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string>
#include <utility>

#include "base/bind.h"
#include "base/callback_helpers.h"
#include "base/critical_closure.h"
#include "base/files/file.h"
#include "base/files/file_path.h"
#include "base/files/file_util.h"
#include "base/logging.h"
#include "base/macros.h"
#include "base/numerics/safe_conversions.h"
#include "base/strings/string_number_conversions.h"
#include "base/strings/string_util.h"
#include "base/task_runner.h"
#include "base/task_runner_util.h"
#include "base/threading/thread.h"
#include "base/time/time.h"
#include "build_config.h"

namespace base {

namespace {

constexpr auto kDefaultCommitInterval = TimeDelta::FromSeconds(10);

// This enum is used to define the buckets for an enumerated UMA histogram.
// Hence,
//   (a) existing enumerated constants should never be deleted or reordered, and
//   (b) new constants should only be appended at the end of the enumeration.
enum TempFileFailure {
  FAILED_CREATING,
  FAILED_OPENING,
  FAILED_CLOSING,  // Unused.
  FAILED_WRITING,
  FAILED_RENAMING,
  FAILED_FLUSHING,
  TEMP_FILE_FAILURE_MAX
};

// Helper function to call WriteFileAtomically() with a
// std::unique_ptr<std::string>.
void WriteScopedStringToFileAtomically(
    const FilePath& path,
    std::unique_ptr<std::string> data,
    Closure before_write_callback,
    Callback<void(bool success)> after_write_callback,
    const std::string& histogram_suffix) {
  if (!before_write_callback.is_null())
    before_write_callback.Run();

  TimeTicks start_time = TimeTicks::Now();
  bool result =
      ImportantFileWriter::WriteFileAtomically(path, *data, histogram_suffix);

  if (!after_write_callback.is_null())
    after_write_callback.Run(result);
}

void DeleteTmpFile(const FilePath& tmp_file_path,
                   StringPiece histogram_suffix) {
  DeleteFile(tmp_file_path, false);
}

}  // namespace

// static
bool ImportantFileWriter::WriteFileAtomically(const FilePath& path,
                                              StringPiece data,
                                              StringPiece histogram_suffix) {
#if defined(OS_CHROMEOS)
  // On Chrome OS, chrome gets killed when it cannot finish shutdown quickly,
  // and this function seems to be one of the slowest shutdown steps.
  // Include some info to the report for investigation. crbug.com/418627
  // TODO(hashimoto): Remove this.
  struct {
    size_t data_size;
    char path[128];
  } file_info;
  file_info.data_size = data.size();
  strlcpy(file_info.path, path.value().c_str(), arraysize(file_info.path));
  debug::Alias(&file_info);
#endif

  // Write the data to a temp file then rename to avoid data loss if we crash
  // while writing the file. Ensure that the temp file is on the same volume
  // as target file, so it can be moved in one step, and that the temp file
  // is securely created.
  FilePath tmp_file_path;
  if (!CreateTemporaryFileInDir(path.DirName(), &tmp_file_path)) {
    return false;
  }

  File tmp_file(tmp_file_path, File::FLAG_OPEN | File::FLAG_WRITE);
  if (!tmp_file.IsValid()) {
    DeleteFile(tmp_file_path, false);
    return false;
  }

  // If this fails in the wild, something really bad is going on.
  const int data_length = checked_cast<int32_t>(data.length());
  int bytes_written = tmp_file.Write(0, data.data(), data_length);
  bool flush_success = tmp_file.Flush();
  tmp_file.Close();

  if (bytes_written < data_length) {
    DeleteTmpFile(tmp_file_path, histogram_suffix);
    return false;
  }

  if (!flush_success) {
    DeleteTmpFile(tmp_file_path, histogram_suffix);
    return false;
  }

  base::File::Error replace_file_error = base::File::FILE_OK;
  if (!ReplaceFile(tmp_file_path, path, &replace_file_error)) {
    DeleteTmpFile(tmp_file_path, histogram_suffix);
    return false;
  }

  return true;
}

ImportantFileWriter::ImportantFileWriter(
    const FilePath& path,
    scoped_refptr<SequencedTaskRunner> task_runner,
    const char* histogram_suffix)
    : ImportantFileWriter(path,
                          std::move(task_runner),
                          kDefaultCommitInterval,
                          histogram_suffix) {}

ImportantFileWriter::ImportantFileWriter(
    const FilePath& path,
    scoped_refptr<SequencedTaskRunner> task_runner,
    TimeDelta interval,
    const char* histogram_suffix)
    : path_(path),
      task_runner_(std::move(task_runner)),
      serializer_(nullptr),
      commit_interval_(interval),
      histogram_suffix_(histogram_suffix ? histogram_suffix : ""),
      weak_factory_(this) {
  DCHECK(task_runner_);
}

ImportantFileWriter::~ImportantFileWriter() {
  DCHECK_CALLED_ON_VALID_SEQUENCE(sequence_checker_);
  // We're usually a member variable of some other object, which also tends
  // to be our serializer. It may not be safe to call back to the parent object
  // being destructed.
  DCHECK(!HasPendingWrite());
}

bool ImportantFileWriter::HasPendingWrite() const {
  DCHECK_CALLED_ON_VALID_SEQUENCE(sequence_checker_);
  return timer().IsRunning();
}

void ImportantFileWriter::WriteNow(std::unique_ptr<std::string> data) {
  DCHECK_CALLED_ON_VALID_SEQUENCE(sequence_checker_);
  if (!IsValueInRangeForNumericType<int32_t>(data->length())) {
    NOTREACHED();
    return;
  }

  Closure task = AdaptCallbackForRepeating(
      BindOnce(&WriteScopedStringToFileAtomically, path_, std::move(data),
               std::move(before_next_write_callback_),
               std::move(after_next_write_callback_), histogram_suffix_));

  if (!task_runner_->PostTask(FROM_HERE, MakeCriticalClosure(task))) {
    // Posting the task to background message loop is not expected
    // to fail, but if it does, avoid losing data and just hit the disk
    // on the current thread.
    NOTREACHED();

    task.Run();
  }
  ClearPendingWrite();
}

void ImportantFileWriter::ScheduleWrite(DataSerializer* serializer) {
  DCHECK_CALLED_ON_VALID_SEQUENCE(sequence_checker_);

  DCHECK(serializer);
  serializer_ = serializer;

  if (!timer().IsRunning()) {
    timer().Start(
        FROM_HERE, commit_interval_,
        Bind(&ImportantFileWriter::DoScheduledWrite, Unretained(this)));
  }
}

void ImportantFileWriter::DoScheduledWrite() {
  DCHECK(serializer_);
  std::unique_ptr<std::string> data(new std::string);
  if (serializer_->SerializeData(data.get())) {
    WriteNow(std::move(data));
  } else {
    DLOG(WARNING) << "failed to serialize data to be saved in "
                  << path_.value();
  }
  ClearPendingWrite();
}

void ImportantFileWriter::RegisterOnNextWriteCallbacks(
    const Closure& before_next_write_callback,
    const Callback<void(bool success)>& after_next_write_callback) {
  before_next_write_callback_ = before_next_write_callback;
  after_next_write_callback_ = after_next_write_callback;
}

void ImportantFileWriter::ClearPendingWrite() {
  timer().Stop();
  serializer_ = nullptr;
}

void ImportantFileWriter::SetTimerForTesting(Timer* timer_override) {
  timer_override_ = timer_override;
}

}  // namespace base

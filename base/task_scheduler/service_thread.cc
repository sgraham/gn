// Copyright 2018 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

#include "base/task_scheduler/service_thread.h"

#include "base/task_scheduler/post_task.h"
#include "base/task_scheduler/task_tracker.h"
#include "base/task_scheduler/task_traits.h"
#include "base/time/time.h"

namespace base {
namespace internal {

ServiceThread::ServiceThread(const TaskTracker* task_tracker)
    : Thread("TaskSchedulerServiceThread"), task_tracker_(task_tracker) {}

void ServiceThread::Init() {
}

NOINLINE void ServiceThread::Run(RunLoop* run_loop) {
  const int line_number = __LINE__;
  Thread::Run(run_loop);
}

}  // namespace internal
}  // namespace base

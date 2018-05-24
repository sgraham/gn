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

#ifdef _WIN32
#include <direct.h>  // Has to be before util.h is included.
#endif

#include "test.h"

#include <string.h>

#include <errno.h>
#include <stdlib.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

#include <algorithm>

namespace {

#ifdef _WIN32
#ifndef _mktemp_s
/// mingw has no mktemp.  Implement one with the same type as the one
/// found in the Windows API.
int _mktemp_s(char* templ) {
  char* ofs = strchr(templ, 'X');
  sprintf(ofs, "%d", rand() % 1000000);
  return 0;
}
#endif

#ifndef chdir
#define chdir _chdir
#endif

/// Windows has no mkdtemp.  Implement it in terms of _mktemp_s.
char* mkdtemp(char* name_template) {
  int err = _mktemp_s(name_template);
  if (err < 0) {
    perror("_mktemp_s");
    return NULL;
  }

  err = _mkdir(name_template);
  if (err < 0) {
    perror("mkdir");
    return NULL;
  }

  return name_template;
}
#endif  // _WIN32

std::string GetSystemTempDir() {
#ifdef _WIN32
  char buf[1024];
  if (!GetTempPathA(sizeof(buf), buf))
    return "";
  return buf;
#else
  const char* tempdir = getenv("TMPDIR");
  if (tempdir)
    return tempdir;
  return "/tmp";
#endif
}

#ifdef _MSC_VER
#define NORETURN __declspec(noreturn)
#else
#define NORETURN __attribute__((noreturn))
#endif
NORETURN void Fatal(const char* msg, ...) {
  va_list ap;
  fprintf(stderr, "gn test: fatal: ");
  va_start(ap, msg);
  vfprintf(stderr, msg, ap);
  va_end(ap);
  fprintf(stderr, "\n");
#ifdef _WIN32
  // On Windows, some tools may inject extra threads.
  // exit() may block on locks held by those threads, so forcibly exit.
  fflush(stderr);
  fflush(stdout);
  ExitProcess(1);
#else
  exit(1);
#endif
}

}  // anonymous namespace

void ScopedTempDir::CreateAndEnter(const std::string& name) {
  // First change into the system temp dir and save it for cleanup.
  start_dir_ = GetSystemTempDir();
  if (start_dir_.empty())
    Fatal("couldn't get system temp dir");
  if (chdir(start_dir_.c_str()) < 0)
    Fatal("chdir: %s", strerror(errno));

  // Create a temporary subdirectory of that.
  char name_template[1024];
  strcpy(name_template, name.c_str());
  strcat(name_template, "-XXXXXX");
  char* tempname = mkdtemp(name_template);
  if (!tempname)
    Fatal("mkdtemp: %s", strerror(errno));
  temp_dir_name_ = tempname;

  // chdir into the new temporary directory.
  if (chdir(temp_dir_name_.c_str()) < 0)
    Fatal("chdir: %s", strerror(errno));
}

void ScopedTempDir::Cleanup() {
  if (temp_dir_name_.empty())
    return;  // Something went wrong earlier.

  // Move out of the directory we're about to clobber.
  if (chdir(start_dir_.c_str()) < 0)
    Fatal("chdir: %s", strerror(errno));

#ifdef _WIN32
  std::string command = "rmdir /s /q " + temp_dir_name_;
#else
  std::string command = "rm -rf " + temp_dir_name_;
#endif
  if (system(command.c_str()) < 0)
    Fatal("system: %s", strerror(errno));

  temp_dir_name_.clear();
}

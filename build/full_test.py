#!/usr/bin/env python
# Copyright 2018 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import subprocess
import sys


def RemoveDir(d):
  if os.path.isdir(d):
    shutil.rmtree(d)

def main():
  if len(sys.argv) < 3 or len(sys.argv) > 4:
    print 'Usage: full_test.py /chrome/tree/at/556eead9ce1e rel_gn_path [clean]'
    return 1

  if len(sys.argv) == 4:
    RemoveDir('out')

  subprocess.check_call([sys.executable, os.path.join('build', 'build.py')])
  subprocess.check_call([os.path.join('out', 'gn_unittests')])
  orig_dir = getcwd()

  # Check in-tree vs. ours. Uses:
  # - Chromium tree at 556eead9ce1e in argv[1]
  # - relative path to argv[1] built gn binary in argv[2]
  os.chdir(sys.argv[1])
  comp_dir = os.path.join('out', 'COMP')
  a_dir = os.path.join('out', 'a')
  b_dir = os.path.join('out', 'b')
  RemoveDir(comp_dir)
  RemoveDir(a_dir)
  RemoveDir(b_dir)
  subprocess.check_call([sys.argv[2], 'gen', comp_dir, '--check'],
                        shell=IS_WIN)
  shutil.move(comp_dir, a_dir)

  RemoveDir(comp_dir)
  subprocess.check_call([os.path.join(orig_dir, 'out', 'gn'), 'gen', comp_dir,
                         '--check'],
                        shell=IS_WIN)
  shutil.move(comp_dir, b_dir)
  subprocess.check_call(['diff', '-r', a_dir, b_dir])
  return 0


if __name__ == '__main__':
    sys.exit(main())

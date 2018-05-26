#!/usr/bin/env python
# Copyright 2018 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Builds gn."""

import contextlib
import errno
import logging
import optparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile

SELF_DIR = os.path.dirname(os.path.abspath(__file__))
GN_ROOT = os.path.join(os.path.dirname(SELF_DIR), 'tools', 'gn')
SRC_ROOT = os.path.dirname(os.path.dirname(GN_ROOT))

is_win = sys.platform.startswith('win')
is_linux = sys.platform.startswith('linux')
is_mac = sys.platform.startswith('darwin')
is_aix = sys.platform.startswith('aix')
is_posix = is_linux or is_mac or is_aix

def check_call(cmd, **kwargs):
  logging.debug('Running: %s', ' '.join(cmd))

  subprocess.check_call(cmd, cwd=GN_ROOT, **kwargs)

def check_output(cmd, cwd=GN_ROOT, **kwargs):
  logging.debug('Running: %s', ' '.join(cmd))

  return subprocess.check_output(cmd, cwd=cwd, **kwargs)


def mkdir_p(path):
  try:
    os.makedirs(path)
  except OSError as e:
    if e.errno == errno.EEXIST and os.path.isdir(path):
      pass
    else: raise


def main(argv):
  parser = optparse.OptionParser(description=sys.modules[__name__].__doc__)
  parser.add_option('-d', '--debug', action='store_true',
                    help='Do a debug build. Defaults to release build.')
  parser.add_option('-v', '--verbose', action='store_true',
                    help='Log more details')
  options, args = parser.parse_args(argv)

  if args:
    parser.error('Unrecognized command line arguments: %s.' % ', '.join(args))

  logging.basicConfig(level=logging.DEBUG if options.verbose else logging.ERROR)

  try:
    build_dir = os.path.join(SRC_ROOT, 'out')
    if not os.path.exists(build_dir):
      os.makedirs(build_dir)
    return build_gn_with_ninja_manually(build_dir, options)
  except subprocess.CalledProcessError as e:
    print >> sys.stderr, str(e)
    return 1
  return 0

def build_gn_with_ninja_manually(tempdir, options):
  root_gen_dir = os.path.join(tempdir, 'gen')
  mkdir_p(root_gen_dir)

  write_gn_ninja(os.path.join(tempdir, 'build.ninja'),
                 root_gen_dir, options)
  cmd = ['ninja', '-C', tempdir, '-w', 'dupbuild=err']
  if options.verbose:
    cmd.append('-v')

  if is_win:
    cmd.append('gn.exe')
    cmd.append('gn_unittests.exe')
  else:
    cmd.append('gn')
    cmd.append('gn_unittests')

  check_call(cmd)

def write_generic_ninja(path, static_libraries, executables,
                        cc, cxx, ar, ld,
                        cflags=[], cflags_cc=[], ldflags=[],
                        libflags=[], include_dirs=[], solibs=[]):
  ninja_header_lines = [
    'cc = ' + cc,
    'cxx = ' + cxx,
    'ar = ' + ar,
    'ld = ' + ld,
    '',
  ]

  if is_win:
    template_filename = 'build_vs.ninja.template'
  elif is_mac:
    template_filename = 'build_mac.ninja.template'
  elif is_aix:
    template_filename = 'build_aix.ninja.template'
  else:
    template_filename = 'build.ninja.template'

  with open(os.path.join(SELF_DIR, template_filename)) as f:
    ninja_template = f.read()

  if is_win:
    executable_ext = '.exe'
    library_ext = '.lib'
    object_ext = '.obj'
  else:
    executable_ext = ''
    library_ext = '.a'
    object_ext = '.o'

  def escape_path_ninja(path):
      return path.replace('$ ', '$$ ').replace(' ', '$ ').replace(':', '$:')

  def src_to_obj(path):
    return escape_path_ninja('%s' % os.path.splitext(path)[0] + object_ext)

  def library_to_a(library):
    return '%s%s' % (library, library_ext)

  ninja_lines = []
  def build_source(src_file, settings):
    ninja_lines.extend([
        'build %s: %s %s' % (src_to_obj(src_file),
                             settings['tool'],
                             escape_path_ninja(
                                 os.path.join(SRC_ROOT, src_file))),
        '  includes = %s' % ' '.join(
            ['-I' + escape_path_ninja(dirname) for dirname in
             include_dirs + settings.get('include_dirs', [])]),
        '  cflags = %s' % ' '.join(cflags + settings.get('cflags', [])),
        '  cflags_cc = %s' %
            ' '.join(cflags_cc + settings.get('cflags_cc', [])),
    ])

  for library, settings in static_libraries.iteritems():
    for src_file in settings['sources']:
      build_source(src_file, settings)

    ninja_lines.extend(['build %s: alink_thin %s' % (
        library_to_a(library),
        ' '.join([src_to_obj(src_file) for src_file in settings['sources']])),
      '  libflags = %s' % ' '.join(libflags),
    ])

  for executable, settings in executables.iteritems():
    for src_file in settings['sources']:
      build_source(src_file, settings)

    ninja_lines.extend([
      'build %s%s: link %s | %s' % (
          executable, executable_ext,
          ' '.join([src_to_obj(src_file) for src_file in settings['sources']]),
          ' '.join([library_to_a(library) for library in settings['libs']])),
      '  ldflags = %s' % ' '.join(ldflags),
      '  solibs = %s' % ' '.join(solibs),
      '  libs = %s' % ' '.join(
          [library_to_a(library) for library in settings['libs']]),
    ])

  ninja_lines.append('')  # Make sure the file ends with a newline.

  with open(path, 'w') as f:
    f.write('\n'.join(ninja_header_lines))
    f.write(ninja_template)
    f.write('\n'.join(ninja_lines))

def write_gn_ninja(path, root_gen_dir, options):
  if is_win:
    cc = os.environ.get('CC', 'cl.exe')
    cxx = os.environ.get('CXX', 'cl.exe')
    ld = os.environ.get('LD', 'link.exe')
    ar = os.environ.get('AR', 'lib.exe')
  elif is_aix:
    cc = os.environ.get('CC', 'gcc')
    cxx = os.environ.get('CXX', 'c++')
    ld = os.environ.get('LD', cxx)
    ar = os.environ.get('AR', 'ar -X64')
  else:
    cc = os.environ.get('CC', 'cc')
    cxx = os.environ.get('CXX', 'c++')
    ld = cxx
    ar = os.environ.get('AR', 'ar')

  cflags = os.environ.get('CFLAGS', '').split()
  cflags_cc = os.environ.get('CXXFLAGS', '').split()
  ldflags = os.environ.get('LDFLAGS', '').split()
  libflags = os.environ.get('LIBFLAGS', '').split()
  include_dirs = [root_gen_dir, SRC_ROOT, os.path.join(SRC_ROOT, 'src')]
  libs = []

  cflags.extend(['-DNO_TCMALLOC'])
  if is_mac:
    cflags.append('-Wno-deprecated-declarations')

  if is_posix:
    if options.debug:
      cflags.extend(['-O0', '-g'])
    else:
      # The linux::ppc64 BE binary doesn't "work" when
      # optimization level is set to 2 (0 works fine).
      # Note that the current bootstrap script has no way to detect host_cpu.
      # This can be easily fixed once we start building using a GN binary,
      # as the optimization flag can then just be set using the
      # logic inside //build/toolchain.
      cflags.extend(['-O2', '-g0', '-DNDEBUG'])

    cflags.extend([
        '-D_FILE_OFFSET_BITS=64',
        '-D__STDC_CONSTANT_MACROS', '-D__STDC_FORMAT_MACROS',
        '-pthread',
        '-pipe',
        '-fno-exceptions',
        '-fno-rtti',
    ])
    cflags_cc.extend(['-std=c++14', '-Wno-c++11-narrowing'])
    if is_aix:
      cflags.extend(['-maix64'])
      ldflags.extend([ '-maix64 -Wl,-bbigtoc' ])
  elif is_win:
    if not options.debug:
      cflags.extend(['/Ox', '/DNDEBUG', '/GL'])
      ldflags.extend(['/LTCG', '/OPT:REF', '/OPT:ICF'])
      libflags.extend(['/LTCG'])

    cflags.extend([
        '/FS',
        '/Gy',
        '/W4',
        '/WX',
        '/wd4099',
        '/wd4100',
        '/wd4127',
        '/wd4244',
        '/wd4267',
        '/wd4505',
        '/wd4577',
        '/wd4706',
        '/wd4838',
        '/wd4996',
        '/Zi',
        '/DWIN32_LEAN_AND_MEAN', '/DNOMINMAX',
        '/D_CRT_SECURE_NO_DEPRECATE', '/D_SCL_SECURE_NO_DEPRECATE',
        '/D_NO_EXCEPTIONS',
        '/D_WIN32_WINNT=0x0A00', '/DWINVER=0x0A00',
        '/DUNICODE', '/D_UNICODE',
    ])
    cflags_cc.extend([
        '/GR-',
        '/D_HAS_EXCEPTIONS=0',
    ])

    ldflags.extend(['/DEBUG', '/MACHINE:x64'])
    libflags.extend(['/MACHINE:x64'])

  static_libraries = {
    'base': {'sources': [], 'tool': 'cxx', 'include_dirs': []},

    'gn_lib': {
    'sources': [
        'src/exe_path.cc',
        'src/msg_loop.cc',
        'src/sys_info.cc',
        'src/worker_pool.cc',
    ],
    'tool': 'cxx',
    'include_dirs': []
    },
  }

  executables = {
      'gn': {
        'sources': [
          'tools/gn/gn_main.cc',
        ],
        'tool': 'cxx',
        'include_dirs': [],
        'libs': []
      },
      'gn_unittests': {
        'sources': [
          'src/test/gn_test.cc',
          'src/test/test.cc',
          'tools/gn/test_with_scheduler.cc',
        ],
        'tool': 'cxx',
        'include_dirs': [],
        'libs': ['gn_lib']
      },
  }

  for name in os.listdir(GN_ROOT):
    if not name.endswith('.cc'):
      continue
    if name.endswith('_unittest.cc'):
      continue
    if name == 'run_all_unittests.cc':
      continue
    if name == 'test_with_scheduler.cc':
      continue
    if name == 'gn_main.cc':
      continue
    full_path = os.path.join(GN_ROOT, name)
    static_libraries['gn_lib']['sources'].append(
        os.path.relpath(full_path, SRC_ROOT))

  for name in os.listdir(os.path.join(GN_ROOT)):
    if name.endswith('_unittest.cc'):
      full_path = os.path.join(GN_ROOT, name)
      executables['gn_unittests']['sources'].append(
        os.path.relpath(full_path, SRC_ROOT))

  static_libraries['base']['sources'].extend([
      'base/callback_helpers.cc',
      'base/callback_internal.cc',
      'base/command_line.cc',
      'base/environment.cc',
      'base/files/file.cc',
      'base/files/file_enumerator.cc',
      'base/files/file_path.cc',
      'base/files/file_path_constants.cc',
      'base/files/file_util.cc',
      'base/files/scoped_file.cc',
      'base/files/scoped_temp_dir.cc',
      'base/json/json_parser.cc',
      'base/json/json_reader.cc',
      'base/json/json_string_value_serializer.cc',
      'base/json/json_writer.cc',
      'base/json/string_escape.cc',
      'base/logging.cc',
      'base/md5.cc',
      'base/memory/ref_counted.cc',
      'base/memory/weak_ptr.cc',
      'base/process/kill.cc',
      'base/process/memory.cc',
      'base/process/process_handle.cc',
      'base/process/process_iterator.cc',
      'base/rand_util.cc',
      'base/sha1.cc',
      'base/strings/pattern.cc',
      'base/strings/string_number_conversions.cc',
      'base/strings/string_piece.cc',
      'base/strings/string_split.cc',
      'base/strings/string_util.cc',
      'base/strings/string_util_constants.cc',
      'base/strings/stringprintf.cc',
      'base/strings/utf_string_conversion_utils.cc',
      'base/strings/utf_string_conversions.cc',
      'base/synchronization/atomic_flag.cc',
      'base/synchronization/lock.cc',
      'base/third_party/icu/icu_utf.cc',
      'base/third_party/nspr/prtime.cc',
      'base/time/clock.cc',
      'base/time/default_tick_clock.cc',
      'base/time/tick_clock.cc',
      'base/time/time.cc',
      'base/timer/elapsed_timer.cc',
      'base/value_iterators.cc',
      'base/values.cc',
  ])

  if is_posix:
    static_libraries['base']['sources'].extend([
        'base/files/file_enumerator_posix.cc',
        'base/files/file_posix.cc',
        'base/files/file_util_posix.cc',
        'base/posix/file_descriptor_shuffle.cc',
        'base/posix/safe_strerror.cc',
        'base/process/kill_posix.cc',
        'base/process/process_handle_posix.cc',
        'base/process/process_posix.cc',
        'base/rand_util_posix.cc',
        'base/strings/string16.cc',
        'base/synchronization/condition_variable_posix.cc',
        'base/synchronization/lock_impl_posix.cc',
        'base/threading/platform_thread_internal_posix.cc',
        'base/threading/platform_thread_posix.cc',
        'base/time/time_conversion_posix.cc',
    ])

  if is_linux or is_aix:
    static_libraries['base']['sources'].extend([
        'base/process/internal_linux.cc',
        'base/process/memory_linux.cc',
        'base/process/process_handle_linux.cc',
        'base/process/process_info_linux.cc',
        'base/process/process_iterator_linux.cc',
        'base/process/process_linux.cc',
        'base/strings/sys_string_conversions_posix.cc',
        'base/synchronization/waitable_event_posix.cc',
        'base/time/time_exploded_posix.cc',
        'base/time/time_now_posix.cc',
        'base/threading/platform_thread_linux.cc',
    ])
    if is_linux:
      libs.extend([
          '-lc',
          '-lgcc_s',
          '-lm',
          '-lpthread',
      ])
      libs.extend(['-lrt', '-latomic'])
    else:
      ldflags.extend(['-pthread'])
      libs.extend(['-lrt'])
      static_libraries['base']['sources'].extend([
          'base/process/internal_aix.cc'
      ])

  if is_mac:
    static_libraries['base']['sources'].extend([
        'base/files/file_util_mac.mm',
        'base/mac/bundle_locations.mm',
        'base/mac/call_with_eh_frame.cc',
        'base/mac/call_with_eh_frame_asm.S',
        'base/mac/dispatch_source_mach.cc',
        'base/mac/foundation_util.mm',
        'base/mac/mach_logging.cc',
        'base/mac/scoped_mach_port.cc',
        'base/mac/scoped_mach_vm.cc',
        'base/mac/scoped_nsautorelease_pool.mm',
        'base/process/process_handle_mac.cc',
        'base/process/process_info_mac.cc',
        'base/process/process_iterator_mac.cc',
        'base/strings/sys_string_conversions_mac.mm',
        'base/synchronization/waitable_event_mac.cc',
        'base/time/time_exploded_posix.cc',
        'base/time/time_mac.cc',
        'base/threading/platform_thread_mac.mm',
    ])

    libs.extend([
        '-framework', 'AppKit',
        '-framework', 'CoreFoundation',
        '-framework', 'Foundation',
        '-framework', 'Security',
    ])

  if is_win:
    static_libraries['base']['sources'].extend([
        'base/cpu.cc',
        'base/file_version_info_win.cc',
        'base/files/file_enumerator_win.cc',
        'base/files/file_util_win.cc',
        'base/files/file_win.cc',
        'base/process/kill_win.cc',
        'base/process/launch_win.cc',
        'base/process/memory_win.cc',
        'base/process/process_handle_win.cc',
        'base/process/process_info_win.cc',
        'base/process/process_iterator_win.cc',
        'base/process/process_win.cc',
        'base/rand_util_win.cc',
        'base/strings/sys_string_conversions_win.cc',
        'base/synchronization/condition_variable_win.cc',
        'base/synchronization/lock_impl_win.cc',
        'base/synchronization/waitable_event_win.cc',
        'base/threading/platform_thread_win.cc',
        'base/time/time_win.cc',
        'base/win/core_winrt_util.cc',
        'base/win/enum_variant.cc',
        'base/win/event_trace_controller.cc',
        'base/win/event_trace_provider.cc',
        'base/win/iat_patch_function.cc',
        'base/win/iunknown_impl.cc',
        'base/win/pe_image.cc',
        'base/win/process_startup_helper.cc',
        'base/win/registry.cc',
        'base/win/resource_util.cc',
        'base/win/scoped_bstr.cc',
        'base/win/scoped_handle.cc',
        'base/win/scoped_process_information.cc',
        'base/win/scoped_variant.cc',
        'base/win/shortcut.cc',
        'base/win/startup_information.cc',
        'base/win/wait_chain.cc',
        'base/win/win_util.cc',
        'base/win/windows_version.cc',
        'base/win/wrapped_window_proc.cc',
    ])

    libs.extend([
        'advapi32.lib',
        'dbghelp.lib',
        'kernel32.lib',
        'ole32.lib',
        'shell32.lib',
        'user32.lib',
        'userenv.lib',
        'version.lib',
        'winmm.lib',
        'ws2_32.lib',
        'Shlwapi.lib',
    ])

  # we just build static libraries that GN needs
  executables['gn']['libs'].extend(static_libraries.keys())
  executables['gn_unittests']['libs'].extend(static_libraries.keys())

  write_generic_ninja(path, static_libraries, executables, cc, cxx, ar, ld,
                      cflags, cflags_cc, ldflags, libflags, include_dirs, libs)


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))

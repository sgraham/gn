#!/usr/bin/env python
# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Bootstraps gn.
"""

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

BOOTSTRAP_DIR = os.path.dirname(os.path.abspath(__file__))
GN_ROOT = os.path.dirname(BOOTSTRAP_DIR)
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


def run_build(tempdir, options):
  build_root = os.path.join(SRC_ROOT, 'out')

  windows_x64_toolchain = None
  if is_win:
    windows_x64_toolchain = windows_prepare_toolchain(tempdir)
    os.environ["PATH"] = windows_x64_toolchain["paths"]

  build_gn_with_ninja_manually(tempdir, options, windows_x64_toolchain)
  temp_gn = os.path.join(tempdir, 'gn')
  out_gn = os.path.join(build_root, 'gn')

  if is_win:
    temp_gn += '.exe'
    out_gn += '.exe'

  mkdir_p(build_root)
  shutil.copy2(temp_gn, out_gn)

  if options.output:
    # Preserve the executable permission bit.
    shutil.copy2(out_gn, options.output)

def windows_target_build_arch():
    # Target build architecture set by vcvarsall.bat
    target_arch = os.environ.get('Platform')
    if target_arch in ['x64', 'x86']: return target_arch

    if platform.machine().lower() in ['x86_64', 'amd64']: return 'x64'
    return 'x86'

def windows_prepare_toolchain(tempdir):

  def CallPythonScopeScript(command, **kwargs):
    response = check_output(command, **kwargs)

    _globals = {"__builtins__":None}
    _locals = {}
    exec(response, _globals, _locals)

    return _locals

  toolchain_paths = CallPythonScopeScript(
      [sys.executable,
       os.path.join(SRC_ROOT, "build", "vs_toolchain.py"),
      "get_toolchain_dir"],
      cwd=tempdir)

  windows_x64_toolchain =  CallPythonScopeScript(
      [sys.executable,
       os.path.join(SRC_ROOT, "build", "toolchain",
                    "win", "setup_toolchain.py"),
       toolchain_paths["vs_path"],
       toolchain_paths["sdk_path"],
       toolchain_paths["runtime_dirs"],
       "win",
       "x64",
       "environment.x64",
       "true"
      ],
      cwd=tempdir)

  return windows_x64_toolchain

def main(argv):
  parser = optparse.OptionParser(description=sys.modules[__name__].__doc__)
  parser.add_option('-d', '--debug', action='store_true',
                    help='Do a debug build. Defaults to release build.')
  parser.add_option('-o', '--output',
                    help='place output in PATH', metavar='PATH')
  parser.add_option('--gn-gen-args', help='Args to pass to gn gen --args')
  parser.add_option('--build-path', help='The directory in which to build gn, '
                    'relative to the src directory. (eg. out/Release)'
                    'In the no-clean mode an absolute path will also force '
                    'the out_bootstrap to be located in the parent directory')
  parser.add_option('-v', '--verbose', action='store_true',
                    help='Log more details')
  options, args = parser.parse_args(argv)

  if args:
    parser.error('Unrecognized command line arguments: %s.' % ', '.join(args))

  logging.basicConfig(level=logging.DEBUG if options.verbose else logging.ERROR)

  try:
    out_bootstrap_dir = SRC_ROOT
    if options.build_path and os.path.isabs(options.build_path):
      out_bootstrap_dir = os.path.dirname(options.build_path)
    build_dir = os.path.join(out_bootstrap_dir, 'out_bootstrap')
    if not os.path.exists(build_dir):
      os.makedirs(build_dir)
    return run_build(build_dir, options)
  except subprocess.CalledProcessError as e:
    print >> sys.stderr, str(e)
    return 1
  return 0

def write_compiled_message(root_gen_dir, source):
  path = os.path.join(root_gen_dir, os.path.dirname(source))
  mkdir_p(path)
  check_call([
      'mc.exe',
      '-r', path, '-h', path,
      '-u', '-um',
      os.path.join(SRC_ROOT, source),
  ])

def write_buildflag_header_manually(root_gen_dir, header, flags):
  mkdir_p(os.path.join(root_gen_dir, os.path.dirname(header)))

  # Don't use tempfile.NamedTemporaryFile() here.
  # It doesn't work correctly on Windows.
  # see: http://bugs.python.org/issue14243
  temp_path = os.path.join(root_gen_dir, header + '.tmp')
  with open(temp_path, 'w') as f:
    f.write('--flags')
    for name,value in flags.items():
      f.write(' ' + name + '=' + value)

  check_call([
      sys.executable,
      os.path.join(SRC_ROOT, 'build', 'write_buildflag_header.py'),
      '--output', header,
      '--gen-dir', root_gen_dir,
      '--definitions', temp_path,
  ])

  os.remove(temp_path)

def write_build_date_header(root_gen_dir):
  check_call([
       sys.executable,
       os.path.join(SRC_ROOT, 'build', 'write_build_date_header.py'),
       os.path.join(root_gen_dir, 'base/generated_build_date.h'),
       'default',
  ])

def build_gn_with_ninja_manually(tempdir, options, windows_x64_toolchain):
  root_gen_dir = os.path.join(tempdir, 'gen')
  mkdir_p(root_gen_dir)

  write_buildflag_header_manually(root_gen_dir, 'base/allocator/buildflags.h',
      {'USE_ALLOCATOR_SHIM': 'true' if is_linux else 'false'})

  write_buildflag_header_manually(root_gen_dir,
                                  'base/debug/debugging_buildflags.h',
      {
          'ENABLE_PROFILING': 'false',
          'CAN_UNWIND_WITH_FRAME_POINTERS': 'false',
          'UNSAFE_DEVELOPER_BUILD': 'false',
          'CAN_UNWIND_WITH_CFI_TABLE': 'false',
      })

  write_buildflag_header_manually(root_gen_dir,
                                  'base/memory/protected_memory_buildflags.h',
                                  { 'USE_LLD': 'false' })

  write_buildflag_header_manually(root_gen_dir, 'base/cfi_buildflags.h',
      {
          'CFI_CAST_CHECK': 'false',
          'CFI_ICALL_CHECK': 'false',
          'CFI_ENFORCEMENT_TRAP': 'false',
          'CFI_ENFORCEMENT_DIAGNOSTIC': 'false'
      })

  write_build_date_header(root_gen_dir)

  if is_mac:
    # //base/build_time.cc needs base/generated_build_date.h,
    # and this file is only included for Mac builds.
    mkdir_p(os.path.join(root_gen_dir, 'base'))
    check_call([
        sys.executable,
        os.path.join(SRC_ROOT, 'build', 'write_build_date_header.py'),
        os.path.join(root_gen_dir, 'base', 'generated_build_date.h'),
        'default'
    ])

  if is_win:
    write_buildflag_header_manually(root_gen_dir,
                                    'base/win/base_win_buildflags.h',
        {'SINGLE_MODULE_MODE_HANDLE_VERIFIER': 'true'})

    write_compiled_message(root_gen_dir,
        'base/trace_event/etw_manifest/chrome_events_win.man')

  write_buildflag_header_manually(
      root_gen_dir, 'base/android/library_loader.h',
      {'USE_LLD': 'false', 'SUPPORTS_CODE_ORDERING': 'false'})

  write_gn_ninja(os.path.join(tempdir, 'build.ninja'),
                 root_gen_dir, options, windows_x64_toolchain)
  cmd = ['ninja', '-C', tempdir, '-w', 'dupbuild=err']
  if options.verbose:
    cmd.append('-v')

  if is_win:
    cmd.append('gn.exe')
  else:
    cmd.append('gn')

  check_call(cmd)

def write_generic_ninja(path, static_libraries, executables,
                        cc, cxx, ar, ld,
                        cflags=[], cflags_cc=[], ldflags=[],
                        include_dirs=[], solibs=[]):
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

  with open(os.path.join(GN_ROOT, 'bootstrap', template_filename)) as f:
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

    ninja_lines.append('build %s: alink_thin %s' % (
        library_to_a(library),
        ' '.join([src_to_obj(src_file) for src_file in settings['sources']])))

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

def write_gn_ninja(path, root_gen_dir, options, windows_x64_toolchain):
  if is_win:
    CCPATH = windows_x64_toolchain["vc_bin_dir"]

    cc = os.environ.get('CC', os.path.join(CCPATH, 'cl.exe'))
    cxx = os.environ.get('CXX', os.path.join(CCPATH, 'cl.exe'))
    ld = os.environ.get('LD', os.path.join(CCPATH, 'link.exe'))
    ar = os.environ.get('AR', os.path.join(CCPATH, 'lib.exe'))
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
  include_dirs = [root_gen_dir, SRC_ROOT]
  libs = []

  # //base/allocator/allocator_extension.cc needs this macro defined,
  # otherwise there would be link errors.
  cflags.extend(['-DNO_TCMALLOC', '-D__STDC_FORMAT_MACROS'])

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
      cflags.extend(['-O2', '-g0'])

    cflags.extend([
        '-D_FILE_OFFSET_BITS=64',
        '-D__STDC_CONSTANT_MACROS', '-D__STDC_FORMAT_MACROS',
        '-pthread',
        '-pipe',
        '-fno-exceptions'
    ])
    cflags_cc.extend(['-std=c++14', '-Wno-c++11-narrowing'])
    if is_aix:
     cflags.extend(['-maix64'])
     ldflags.extend([ '-maix64 -Wl,-bbigtoc' ])
  elif is_win:
    if not options.debug:
      cflags.extend(['/Ox', '/DNDEBUG', '/GL'])
      ldflags.extend(['/LTCG', '/OPT:REF', '/OPT:ICF'])

    cflags.extend([
        '/FS',
        '/Gy',
        '/W3', '/wd4244',
        '/Zi',
        '/DWIN32_LEAN_AND_MEAN', '/DNOMINMAX',
        '/D_CRT_SECURE_NO_DEPRECATE', '/D_SCL_SECURE_NO_DEPRECATE',
        '/D_WIN32_WINNT=0x0A00', '/DWINVER=0x0A00',
        '/DUNICODE', '/D_UNICODE',
    ])
    cflags_cc.extend([
        '/GR-',
        '/D_HAS_EXCEPTIONS=0',
    ])

    target_arch = windows_target_build_arch()
    if target_arch == 'x64':
        ldflags.extend(['/MACHINE:x64'])
    else:
        ldflags.extend(['/MACHINE:x86'])

  static_libraries = {
      'base': {'sources': [], 'tool': 'cxx', 'include_dirs': []},
      'dynamic_annotations': {'sources': [], 'tool': 'cc', 'include_dirs': []},
      'gn_lib': {'sources': [], 'tool': 'cxx', 'include_dirs': []},
  }

  executables = {
      'gn': {'sources': ['tools/gn/gn_main.cc'],
             'tool': 'cxx', 'include_dirs': [], 'libs': []},
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

  static_libraries['dynamic_annotations']['sources'].extend([
      'base/third_party/dynamic_annotations/dynamic_annotations.c',
      'base/third_party/superfasthash/superfasthash.c',
  ])
  static_libraries['base']['sources'].extend([
      'base/allocator/allocator_check.cc',
      'base/allocator/allocator_extension.cc',
      'base/at_exit.cc',
      'base/base_paths.cc',
      'base/base_switches.cc',
      'base/build_time.cc',
      'base/callback_helpers.cc',
      'base/callback_internal.cc',
      'base/command_line.cc',
      'base/debug/activity_tracker.cc',
      'base/debug/alias.cc',
      'base/debug/crash_logging.cc',
      'base/debug/dump_without_crashing.cc',
      'base/debug/stack_trace.cc',
      'base/debug/task_annotator.cc',
      'base/debug/thread_heap_usage_tracker.cc',
      'base/environment.cc',
      'base/feature_list.cc',
      'base/files/file.cc',
      'base/files/file_enumerator.cc',
      'base/files/file_path.cc',
      'base/files/file_path_constants.cc',
      'base/files/file_tracing.cc',
      'base/files/file_util.cc',
      'base/files/important_file_writer.cc',
      'base/files/memory_mapped_file.cc',
      'base/files/scoped_file.cc',
      'base/hash.cc',
      'base/json/json_parser.cc',
      'base/json/json_reader.cc',
      'base/json/json_string_value_serializer.cc',
      'base/json/json_writer.cc',
      'base/json/string_escape.cc',
      'base/lazy_instance_helpers.cc',
      'base/location.cc',
      'base/logging.cc',
      'base/md5.cc',
      'base/memory/platform_shared_memory_region.cc',
      'base/memory/read_only_shared_memory_region.cc',
      'base/memory/ref_counted.cc',
      'base/memory/ref_counted_memory.cc',
      'base/memory/shared_memory_mapping.cc',
      'base/memory/shared_memory_handle.cc',
      'base/memory/shared_memory_tracker.cc',
      'base/memory/weak_ptr.cc',
      'base/message_loop/incoming_task_queue.cc',
      'base/message_loop/message_loop.cc',
      'base/message_loop/message_loop_current.cc',
      'base/message_loop/message_loop_task_runner.cc',
      'base/message_loop/message_pump.cc',
      'base/message_loop/message_pump_default.cc',
      'base/message_loop/watchable_io_message_pump_posix.cc',
      'base/metrics/bucket_ranges.cc',
      'base/metrics/dummy_histogram.cc',
      'base/metrics/field_trial.cc',
      'base/metrics/field_trial_param_associator.cc',
      'base/metrics/field_trial_params.cc',
      'base/metrics/histogram.cc',
      'base/metrics/histogram_base.cc',
      'base/metrics/histogram_functions.cc',
      'base/metrics/histogram_samples.cc',
      'base/metrics/histogram_snapshot_manager.cc',
      'base/metrics/metrics_hashes.cc',
      'base/metrics/persistent_histogram_allocator.cc',
      'base/metrics/persistent_memory_allocator.cc',
      'base/metrics/persistent_sample_map.cc',
      'base/metrics/sample_map.cc',
      'base/metrics/sample_vector.cc',
      'base/metrics/sparse_histogram.cc',
      'base/metrics/statistics_recorder.cc',
      'base/observer_list_threadsafe.cc',
      'base/path_service.cc',
      'base/pending_task.cc',
      'base/pickle.cc',
      'base/process/kill.cc',
      'base/process/memory.cc',
      'base/process/process_handle.cc',
      'base/process/process_iterator.cc',
      'base/process/process_metrics.cc',
      'base/rand_util.cc',
      'base/run_loop.cc',
      'base/sequence_token.cc',
      'base/sequence_checker_impl.cc',
      'base/sequenced_task_runner.cc',
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
      'base/sys_info.cc',
      'base/task_runner.cc',
      'base/task_scheduler/delayed_task_manager.cc',
      'base/task_scheduler/environment_config.cc',
      'base/task_scheduler/post_task.cc',
      'base/task_scheduler/priority_queue.cc',
      'base/task_scheduler/scheduler_lock_impl.cc',
      'base/task_scheduler/scheduler_single_thread_task_runner_manager.cc',
      'base/task_scheduler/scheduler_worker.cc',
      'base/task_scheduler/scheduler_worker_pool.cc',
      'base/task_scheduler/scheduler_worker_pool_impl.cc',
      'base/task_scheduler/scheduler_worker_pool_params.cc',
      'base/task_scheduler/scheduler_worker_stack.cc',
      'base/task_scheduler/scoped_set_task_priority_for_current_thread.cc',
      'base/task_scheduler/sequence.cc',
      'base/task_scheduler/sequence_sort_key.cc',
      'base/task_scheduler/service_thread.cc',
      'base/task_scheduler/task.cc',
      'base/task_scheduler/task_scheduler.cc',
      'base/task_scheduler/task_scheduler_impl.cc',
      'base/task_scheduler/task_tracker.cc',
      'base/task_scheduler/task_traits.cc',
      'base/third_party/dmg_fp/dtoa_wrapper.cc',
      'base/third_party/dmg_fp/g_fmt.cc',
      'base/third_party/icu/icu_utf.cc',
      'base/third_party/nspr/prtime.cc',
      'base/threading/post_task_and_reply_impl.cc',
      'base/threading/scoped_blocking_call.cc',
      'base/threading/sequence_local_storage_map.cc',
      'base/threading/sequenced_task_runner_handle.cc',
      'base/threading/simple_thread.cc',
      'base/threading/thread.cc',
      'base/threading/thread_checker_impl.cc',
      'base/threading/thread_collision_warner.cc',
      'base/threading/thread_id_name_manager.cc',
      'base/threading/thread_local_storage.cc',
      'base/threading/thread_restrictions.cc',
      'base/threading/thread_task_runner_handle.cc',
      'base/time/clock.cc',
      'base/time/default_clock.cc',
      'base/time/default_tick_clock.cc',
      'base/time/tick_clock.cc',
      'base/time/time.cc',
      'base/timer/elapsed_timer.cc',
      'base/timer/timer.cc',
      'base/trace_event/category_registry.cc',
      'base/trace_event/event_name_filter.cc',
      'base/trace_event/heap_profiler_allocation_context.cc',
      'base/trace_event/heap_profiler_allocation_context_tracker.cc',
      'base/trace_event/heap_profiler_event_filter.cc',
      'base/trace_event/heap_profiler_heap_dump_writer.cc',
      'base/trace_event/heap_profiler_serialization_state.cc',
      'base/trace_event/heap_profiler_stack_frame_deduplicator.cc',
      'base/trace_event/heap_profiler_type_name_deduplicator.cc',
      'base/trace_event/malloc_dump_provider.cc',
      'base/trace_event/memory_allocator_dump.cc',
      'base/trace_event/memory_allocator_dump_guid.cc',
      'base/trace_event/memory_dump_manager.cc',
      'base/trace_event/memory_dump_provider_info.cc',
      'base/trace_event/memory_dump_request_args.cc',
      'base/trace_event/memory_dump_scheduler.cc',
      'base/trace_event/memory_infra_background_whitelist.cc',
      'base/trace_event/memory_peak_detector.cc',
      'base/trace_event/memory_usage_estimator.cc',
      'base/trace_event/process_memory_dump.cc',
      'base/trace_event/trace_buffer.cc',
      'base/trace_event/trace_config.cc',
      'base/trace_event/trace_config_category_filter.cc',
      'base/trace_event/trace_event_argument.cc',
      'base/trace_event/trace_event_filter.cc',
      'base/trace_event/trace_event_impl.cc',
      'base/trace_event/trace_event_memory_overhead.cc',
      'base/trace_event/trace_log.cc',
      'base/trace_event/trace_log_constants.cc',
      'base/trace_event/tracing_agent.cc',
      'base/unguessable_token.cc',
      'base/value_iterators.cc',
      'base/values.cc',
      'base/vlog.cc',
  ])

  if is_win:
    static_libraries['base']['sources'].extend([
        'base/memory/platform_shared_memory_region_win.cc'
    ])
  elif is_mac:
    static_libraries['base']['sources'].extend([
        'base/memory/platform_shared_memory_region_mac.cc'
    ])
  elif is_posix:
    static_libraries['base']['sources'].extend([
        'base/memory/platform_shared_memory_region_posix.cc'
    ])

  if is_posix:
    static_libraries['base']['sources'].extend([
        'base/base_paths_posix.cc',
        'base/debug/debugger_posix.cc',
        'base/debug/stack_trace_posix.cc',
        'base/files/file_enumerator_posix.cc',
        'base/files/file_descriptor_watcher_posix.cc',
        'base/files/file_posix.cc',
        'base/files/file_util_posix.cc',
        'base/files/memory_mapped_file_posix.cc',
        'base/memory/shared_memory_helper.cc',
        'base/message_loop/message_pump_libevent.cc',
        'base/posix/file_descriptor_shuffle.cc',
        'base/posix/global_descriptors.cc',
        'base/posix/safe_strerror.cc',
        'base/process/kill_posix.cc',
        'base/process/process_handle_posix.cc',
        'base/process/process_metrics_posix.cc',
        'base/process/process_posix.cc',
        'base/rand_util_posix.cc',
        'base/strings/string16.cc',
        'base/synchronization/condition_variable_posix.cc',
        'base/synchronization/lock_impl_posix.cc',
        'base/sys_info_posix.cc',
        'base/task_scheduler/task_tracker_posix.cc',
        'base/threading/platform_thread_internal_posix.cc',
        'base/threading/platform_thread_posix.cc',
        'base/threading/thread_local_storage_posix.cc',
        'base/time/time_conversion_posix.cc',
    ])
    static_libraries['libevent'] = {
        'sources': [
            'base/third_party/libevent/buffer.c',
            'base/third_party/libevent/evbuffer.c',
            'base/third_party/libevent/evdns.c',
            'base/third_party/libevent/event.c',
            'base/third_party/libevent/event_tagging.c',
            'base/third_party/libevent/evrpc.c',
            'base/third_party/libevent/evutil.c',
            'base/third_party/libevent/http.c',
            'base/third_party/libevent/log.c',
            'base/third_party/libevent/poll.c',
            'base/third_party/libevent/select.c',
            'base/third_party/libevent/signal.c',
            'base/third_party/libevent/strlcpy.c',
        ],
        'tool': 'cc',
        'include_dirs': [],
        'cflags': cflags + ['-DHAVE_CONFIG_H'],
    }

  if is_linux or is_aix:
    static_libraries['xdg_user_dirs'] = {
        'sources': [
            'base/third_party/xdg_user_dirs/xdg_user_dir_lookup.cc',
        ],
        'tool': 'cxx',
    }
    static_libraries['base']['sources'].extend([
        'base/memory/shared_memory_handle_posix.cc',
        'base/memory/shared_memory_posix.cc',
        'base/nix/xdg_util.cc',
        'base/process/internal_linux.cc',
        'base/process/memory_linux.cc',
        'base/process/process_handle_linux.cc',
        'base/process/process_info_linux.cc',
        'base/process/process_iterator_linux.cc',
        'base/process/process_linux.cc',
        'base/process/process_metrics_linux.cc',
        'base/strings/sys_string_conversions_posix.cc',
        'base/synchronization/waitable_event_posix.cc',
        'base/sys_info_linux.cc',
        'base/time/time_exploded_posix.cc',
        'base/time/time_now_posix.cc',
        'base/threading/platform_thread_linux.cc',
    ])
    if is_linux:
      libcxx_root = SRC_ROOT + '/buildtools/third_party/libc++/trunk'
      libcxxabi_root = SRC_ROOT + '/buildtools/third_party/libc++abi/trunk'
      cflags_cc.extend([
          '-nostdinc++',
          '-isystem' + libcxx_root + '/include',
          '-isystem' + libcxxabi_root + '/include',
      ])
      ldflags.extend(['-nodefaultlibs'])
      libs.extend([
          '-lc',
          '-lgcc_s',
          '-lm',
          '-lpthread',
      ])
      static_libraries['libc++'] = {
          'sources': [
              libcxx_root + '/src/algorithm.cpp',
              libcxx_root + '/src/any.cpp',
              libcxx_root + '/src/bind.cpp',
              libcxx_root + '/src/chrono.cpp',
              libcxx_root + '/src/condition_variable.cpp',
              libcxx_root + '/src/debug.cpp',
              libcxx_root + '/src/exception.cpp',
              libcxx_root + '/src/functional.cpp',
              libcxx_root + '/src/future.cpp',
              libcxx_root + '/src/hash.cpp',
              libcxx_root + '/src/ios.cpp',
              libcxx_root + '/src/iostream.cpp',
              libcxx_root + '/src/locale.cpp',
              libcxx_root + '/src/memory.cpp',
              libcxx_root + '/src/mutex.cpp',
              libcxx_root + '/src/new.cpp',
              libcxx_root + '/src/optional.cpp',
              libcxx_root + '/src/random.cpp',
              libcxx_root + '/src/regex.cpp',
              libcxx_root + '/src/shared_mutex.cpp',
              libcxx_root + '/src/stdexcept.cpp',
              libcxx_root + '/src/string.cpp',
              libcxx_root + '/src/strstream.cpp',
              libcxx_root + '/src/system_error.cpp',
              libcxx_root + '/src/thread.cpp',
              libcxx_root + '/src/typeinfo.cpp',
              libcxx_root + '/src/utility.cpp',
              libcxx_root + '/src/valarray.cpp',
              libcxx_root + '/src/variant.cpp',
              libcxx_root + '/src/vector.cpp',
          ],
          'tool': 'cxx',
          'cflags': cflags + [
              '-D_LIBCPP_NO_EXCEPTIONS',
              '-D_LIBCPP_BUILDING_LIBRARY',
              '-DLIBCXX_BUILDING_LIBCXXABI',
          ]
      }
      static_libraries['libc++abi'] = {
          'sources': [
              libcxxabi_root + '/src/abort_message.cpp',
              libcxxabi_root + '/src/cxa_aux_runtime.cpp',
              libcxxabi_root + '/src/cxa_default_handlers.cpp',
              libcxxabi_root + '/src/cxa_demangle.cpp',
              libcxxabi_root + '/src/cxa_exception_storage.cpp',
              libcxxabi_root + '/src/cxa_guard.cpp',
              libcxxabi_root + '/src/cxa_handlers.cpp',
              libcxxabi_root + '/src/cxa_noexception.cpp',
              libcxxabi_root + '/src/cxa_unexpected.cpp',
              libcxxabi_root + '/src/cxa_vector.cpp',
              libcxxabi_root + '/src/cxa_virtual.cpp',
              libcxxabi_root + '/src/fallback_malloc.cpp',
              libcxxabi_root + '/src/private_typeinfo.cpp',
              libcxxabi_root + '/src/stdlib_exception.cpp',
              libcxxabi_root + '/src/stdlib_stdexcept.cpp',
              libcxxabi_root + '/src/stdlib_typeinfo.cpp',
          ],
          'tool': 'cxx',
          'cflags': cflags + [
              '-DLIBCXXABI_SILENT_TERMINATE',
              '-D_LIBCXXABI_NO_EXCEPTIONS',
          ]
      }
      static_libraries['base']['sources'].extend([
        'base/allocator/allocator_shim.cc',
        'base/allocator/allocator_shim_default_dispatch_to_glibc.cc',
      ])
      libs.extend(['-lrt', '-latomic'])
      static_libraries['libevent']['include_dirs'].extend([
          os.path.join(SRC_ROOT, 'base', 'third_party', 'libevent', 'linux')
      ])
      static_libraries['libevent']['sources'].extend([
         'base/third_party/libevent/epoll.c',
      ])
    else:
      ldflags.extend(['-pthread'])
      libs.extend(['-lrt'])
      static_libraries['base']['sources'].extend([
          'base/process/internal_aix.cc'
      ])
      static_libraries['libevent']['include_dirs'].extend([
          os.path.join(SRC_ROOT, 'base', 'third_party', 'libevent', 'aix')
      ])
      static_libraries['libevent']['include_dirs'].extend([
          os.path.join(SRC_ROOT, 'base', 'third_party', 'libevent', 'compat')
      ])

  if is_mac:
    static_libraries['base']['sources'].extend([
        'base/base_paths_mac.mm',
        'base/files/file_util_mac.mm',
        'base/mac/bundle_locations.mm',
        'base/mac/call_with_eh_frame.cc',
        'base/mac/call_with_eh_frame_asm.S',
        'base/mac/foundation_util.mm',
        'base/mac/mach_logging.cc',
        'base/mac/scoped_mach_port.cc',
        'base/mac/scoped_mach_vm.cc',
        'base/mac/scoped_nsautorelease_pool.mm',
        'base/memory/shared_memory_handle_mac.cc',
        'base/memory/shared_memory_mac.cc',
        'base/message_loop/message_pump_mac.mm',
        'base/process/process_handle_mac.cc',
        'base/process/process_info_mac.cc',
        'base/process/process_iterator_mac.cc',
        'base/process/process_metrics_mac.cc',
        'base/strings/sys_string_conversions_mac.mm',
        'base/synchronization/waitable_event_mac.cc',
        'base/sys_info_mac.mm',
        'base/time/time_exploded_posix.cc',
        'base/time/time_mac.cc',
        'base/threading/platform_thread_mac.mm',
    ])
    static_libraries['libevent']['include_dirs'].extend([
        os.path.join(SRC_ROOT, 'base', 'third_party', 'libevent', 'mac')
    ])
    static_libraries['libevent']['sources'].extend([
        'base/third_party/libevent/kqueue.c',
    ])

    libs.extend([
        '-framework', 'AppKit',
        '-framework', 'CoreFoundation',
        '-framework', 'Foundation',
        '-framework', 'Security',
    ])

  if is_win:
    static_libraries['base']['sources'].extend([
        "base/allocator/partition_allocator/address_space_randomization.cc",
        'base/allocator/partition_allocator/page_allocator.cc',
        "base/allocator/partition_allocator/spin_lock.cc",
        'base/base_paths_win.cc',
        'base/cpu.cc',
        'base/debug/close_handle_hook_win.cc',
        'base/debug/debugger.cc',
        'base/debug/debugger_win.cc',
        'base/debug/profiler.cc',
        'base/debug/stack_trace_win.cc',
        'base/file_version_info_win.cc',
        'base/files/file_enumerator_win.cc',
        'base/files/file_path_watcher_win.cc',
        'base/files/file_util_win.cc',
        'base/files/file_win.cc',
        'base/files/memory_mapped_file_win.cc',
        'base/guid.cc',
        'base/logging_win.cc',
        'base/memory/memory_pressure_monitor_win.cc',
        'base/memory/shared_memory_handle_win.cc',
        'base/memory/shared_memory_win.cc',
        'base/message_loop/message_pump_win.cc',
        'base/native_library_win.cc',
        'base/power_monitor/power_monitor_device_source_win.cc',
        'base/process/kill_win.cc',
        'base/process/launch_win.cc',
        'base/process/memory_win.cc',
        'base/process/process_handle_win.cc',
        'base/process/process_info_win.cc',
        'base/process/process_iterator_win.cc',
        'base/process/process_metrics_win.cc',
        'base/process/process_win.cc',
        'base/profiler/native_stack_sampler_win.cc',
        'base/profiler/win32_stack_frame_unwinder.cc',
        'base/rand_util_win.cc',
        'base/strings/sys_string_conversions_win.cc',
        'base/sync_socket_win.cc',
        'base/synchronization/condition_variable_win.cc',
        'base/synchronization/lock_impl_win.cc',
        'base/synchronization/waitable_event_watcher_win.cc',
        'base/synchronization/waitable_event_win.cc',
        'base/sys_info_win.cc',
        'base/threading/platform_thread_win.cc',
        'base/threading/thread_local_storage_win.cc',
        'base/time/time_win.cc',
        'base/timer/hi_res_timer_manager_win.cc',
        'base/trace_event/trace_event_etw_export_win.cc',
        'base/win/core_winrt_util.cc',
        'base/win/enum_variant.cc',
        'base/win/event_trace_controller.cc',
        'base/win/event_trace_provider.cc',
        'base/win/i18n.cc',
        'base/win/iat_patch_function.cc',
        'base/win/iunknown_impl.cc',
        'base/win/message_window.cc',
        'base/win/object_watcher.cc',
        'base/win/pe_image.cc',
        'base/win/process_startup_helper.cc',
        'base/win/registry.cc',
        'base/win/resource_util.cc',
        'base/win/scoped_bstr.cc',
        'base/win/scoped_com_initializer.cc',
        'base/win/scoped_handle.cc',
        'base/win/scoped_handle_verifier.cc',
        'base/win/scoped_process_information.cc',
        'base/win/scoped_variant.cc',
        'base/win/scoped_winrt_initializer.cc',
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

  write_generic_ninja(path, static_libraries, executables, cc, cxx, ar, ld,
                      cflags, cflags_cc, ldflags, include_dirs, libs)


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))

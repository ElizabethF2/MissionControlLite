#!/usr/bin/env python3

import sys, os, subprocess, shutil, time, tomllib, json, tempfile
sys.dont_write_bytecode = True

DEFAULT_CONSECUTIVE_FAIL_TIMEOUT = 120
DEFAULT_CONSECUTIVE_FAIL_LIMIT_FOR_NET_RESET = 3
DEFAULT_CONSECUTIVE_FAIL_LIMIT_FOR_REBOOT = 10
DEFAULT_COMMAND_TIMEOUT = 600

def run(cmd, timeout):
  proc = subprocess.Popen(cmd,
                          stdout = subprocess.DEVNULL,
                          stderr = subprocess.DEVNULL,
                          stdin = subprocess.DEVNULL)
  try:
    proc.wait(timeout = timeout)
  except subprocess.TimeoutExpired:
    pass
  return proc

def main():
  try:
    try:
      import missioncontrollitelib
      config = missioncontrollitelib.get_config(config_name = 'repair.toml')
    except ModuleNotFoundError:
      with open('/etc/mclite/repair.toml', 'rb') as f:
        config = tomllib.load(f)
  except OSError:
    config = {}

  consecutive_fail_timeout = config.get('consecutive_fail_timeout',
                                         DEFAULT_CONSECUTIVE_FAIL_TIMEOUT)
  net_fail_limit = config.get('consecutive_fail_limit_for_net_reset',
                              DEFAULT_CONSECUTIVE_FAIL_LIMIT_FOR_NET_RESET)
  reboot_fail_limit = config.get('consecutive_fail_limit_for_reboot',
                                   DEFAULT_CONSECUTIVE_FAIL_LIMIT_FOR_REBOOT)
  command_timeout = config.get('command_timeout', DEFAULT_COMMAND_TIMEOUT)

  if not (state_path := config.get('state_path')):
    state_path = os.path.join(tempfile.gettempdir(), 'mclite_repair_state.json')

  try:
    with open(state_path, 'r') as f:
      state = json.load(f)
  except OSError:
    state = {}

  last_fail_time = state.get('last_fail_time', 0)
  fail_count = state.get('fail_count', 0)
  consecutive_fail_count = state.get('consecutive_fail_count', 0)

  fail_count += 1
  now = time.time()

  if (now - last_fail_time) < consecutive_fail_timeout:
    consecutive_fail_count += 1
  else:
    consecutive_fail_count = 0

  if consecutive_fail_count > net_fail_limit:
    systemctl = shutil.which('systemctl')
    if systemctl:
      run((systemctl, 'restart', 'NetworkManager'), command_timeout)

    if sys.platform in ('win32', 'cygwin'):
      run(('netsh', 'winsock', 'reset'), command_timeout)
      run(('netsh', 'int', 'ip'), command_timeout)
      run(('ipconfig', '/release'), command_timeout)
      run(('ipconfig', '/renew'), command_timeout)
      run(('ipconfig', '/flushdns'), command_timeout)

  state = {
    'last_fail_time': now,
    'fail_count': fail_count,
    'consecutive_fail_count': consecutive_fail_count,
  }
  with open(state_path, 'w') as f:
    json.dump(state, f)

  if consecutive_fail_count > reboot_fail_limit:
    if sys.platform in ('win32', 'cygwin'):
      run(('shutdown', '/r', '/t', '1'), command_timeout)
    else:
      run(('reboot',), command_timeout)

if __name__ == '__main__':
  main()

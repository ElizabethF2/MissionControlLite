#!/usr/bin/env python3

import sys, os, time, threading, subprocess, shlex, functools, pprint
import urllib.error
sys.dont_write_bytecode = True

import missioncontrollitelib
missioncontrollitelib.DEFAULT_CONFIG_ENV_VAR_NAME = 'MCLITE_SERVER_CONFIG'
from missioncontrollitelib import *

DEFAULT_COMMAND_OUTPUT_FLUSH_TIMEOUT = 25

def send(recipient, sections):
  bus = get_config()['mcbus_url']
  this_device = get_config()['this_device']
  key = get_config()['devices'][this_device]['server_key']
  missioncontrollitelib.send(bus, recipient, key, {'sections': sections},
                             verify = get_cert_path())

def get_inbox():
  this_device = get_config()['this_device']
  inbox = missioncontrollitelib.receive(
    get_config()['mcbus_url'],
    get_config()['devices'][this_device]['server_name'],
    verify = get_cert_path(),
  )
  key = get_config()['devices'][this_device]['client_key']
  return [missioncontrollitelib.decrypt(i, key) for i in inbox]

def run_cmd(sender, cmd, stdin):
  if type(cmd) is str:
    cmd = shlex.split(cmd)
  if type(stdin) is str:
    stdin = stdin.encode()
  proc = subprocess.Popen(cmd,
                          stdin = subprocess.PIPE,
                          stdout = subprocess.PIPE,
                          stderr = subprocess.STDOUT)
  if stdin:
    subprocess.stdin.write(stdin)
  os.set_blocking(proc.stdout.fileno(), False)
  timeout = get_config().get('command_output_flush_timeout',
                             DEFAULT_COMMAND_OUTPUT_FLUSH_TIMEOUT)
  sections = [
    {'title': 'CMD', 'body': shlex.join(cmd)},
    {'title': 'PID', 'body': str(proc.pid)},
  ]
  while True:
    try:
      rc = proc.wait(timeout = timeout)
    except subprocess.TimeoutExpired:
      rc = None
    if output := proc.stdout.read():
      if rc is None:
        send(sender, sections + [
          {'title': 'PARTIAL OUTPUT', 'body': output.decode()},
        ])
      else:
        sections.append({'title': 'OUTPUT', 'body': output.decode()})
    elif rc is not None:
      sections.append({'title': 'NO OUTPUT'})
    if rc is not None:
      sections.append({'title': 'RETURN CODE: ' + str(proc.returncode)})
      return send(sender, sections)

def handle_messages(messages):
  for message in messages:
    missioncontrollitelib.watchdog_tick()
    command_name = message['command_name']
    sender = message['sender']
    this_device = get_config()['this_device']
    cmd = get_config()['devices'][this_device]['commands'].get(command_name)
    if cmd:
      stdin = None
      if type(cmd) is dict:
        args = cmd.get('args', [])
        if cmd.get('accepts_stdin'):
          stdin = message.get('stdin', '')
        cmd = cmd['cmd']
        if type(cmd) is list:
          cmd = shlex.join(cmd)
        for arg in args:
          v = message.get('args', {}).get(arg, '')
          cmd = cmd.replace('{' + arg + '}', shlex.quote(v))
      threading.Thread(target = run_cmd,
                       args = (sender, cmd, stdin)).start()
    else:
      send(sender, [{'title': 'Error',
                     'body': 'Invalid Request: ' + pprint.pformat(message)}])

def do_test():
  print('Running basic sanity/smoke tests...')
  this_device = get_config()['this_device']
  name = get_config()['devices'][this_device]['server_name']
  try:
    send(name, 'testsections')
    actual_client_key = get_config()['devices'][this_device]['client_key']
    server_key = get_config()['devices'][this_device]['server_key']
    get_config()['devices'][this_device]['client_key'] = server_key
    inbox = get_inbox()
    get_config()['devices'][this_device]['client_key'] = actual_client_key
    if inbox != [{'sections': 'testsections'}]:
      raise ValueError(f'Unexpected inbox contents: {inbox}')
  except urllib.error.URLError:
    print('WARNING: device offline, bus tests skipped')
  now = missioncontrollitelib.watchdog_tick()
  last = missioncontrollitelib.get_last_watchdog_tick()
  if now != last:
    raise ValueError(f'tick mismatch {now} != {last}')
  handle_messages([])
  missioncontrollitelib.clear_watchdog_tick()
  cmd = get_config()['devices'][this_device]['commands'].get('')
  if not missioncontrollitelib.get_cert_path():
    raise ValueError('missing or empty cert path')
  print('Tests passed!')

def daemon_main():
  last = missioncontrollitelib.get_last_watchdog_tick()
  if (time.time() - last) <= get_config().get('watchdog_timeout',
                                              DEFAULT_WATCHDOG_TIMEOUT):
    return
  idle_timeout = get_config().get('idle_timeout', DEFAULT_IDLE_TIMEOUT)
  last_request = time.time()
  try:
    while (time.time() - last_request) <= idle_timeout or \
          len(threading.enumerate()) > 1:
      missioncontrollitelib.watchdog_tick()
      inbox = get_inbox()
      if len(inbox) > 0:
        last_request = time.time()
        handle_messages(inbox)
  finally:
    missioncontrollitelib.clear_watchdog_tick()

def main():
  if '--daemonized' in sys.argv[1:2]:
    return daemon_main()
  elif '--test' in sys.argv[1:2]:
    return do_test()
  elif len(sys.argv) > 1:
    print(f'WARNING: invalid arg(s): {sys.argv}')
    print('         launching background daemon')
  kwargs = {'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
  if detached_process := getattr(subprocess, 'DETACHED_PROCESS', 0):
    kwargs['creationflags'] = detached_process
  else:
    kwargs['start_new_session'] = True
  subprocess.Popen((sys.executable, __file__, '--daemonized'), **kwargs)

if __name__ == '__main__':
  main()

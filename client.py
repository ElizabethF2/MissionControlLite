#!/usr/bin/env python3

import sys, os, time, textwrap, uuid
sys.dont_write_bytecode = True

import missioncontrollitelib
missioncontrollitelib.DEFAULT_CONFIG_ENV_VAR_NAME = 'MCLITE_CLIENT_CONFIG'
from missioncontrollitelib import *

def send(device, payload, waker = False):
  bus = get_config()['mcbus_url']
  key = get_config()['devices'][device]['client_key']
  r = 'waker_name' if waker else 'server_name'
  recipient = get_config()['devices'][device][r]
  if waker and recipient is None:
    return
  missioncontrollitelib.send(bus, recipient, key, payload,
                             verify = get_cert_path())

def get_inbox(name, device):
  inbox = missioncontrollitelib.receive(
    get_config()['mcbus_url'],
    name,
    verify = get_cert_path(),
  )
  key = get_config()['devices'][device]['server_key']
  return [missioncontrollitelib.decrypt(i, key) for i in inbox]

def ask(choices):
  while True:
    valid = set()
    for idx, label in choices:
      print(f'{idx}) {label}')
      valid.add(str(idx))
    print('')
    inp = input('> ')
    print('')
    if inp in valid:
      return inp
    print('Invalid selection!')
    print('')

def wrap_and_indent(txt, width = 80, indent = '    '):
  return textwrap.indent(textwrap.fill(txt,
                                       replace_whitespace = False,
                                       drop_whitespace = False,
                                       width = 80), indent)

def wake(state):
  missing = object()
  dev = state['device']
  waker_name = get_config()['devices'][dev].get('waker_name', missing)
  if waker_name is not None:
    print('Waking server via bus...\n')
    send(dev, 'wake', waker = True)
  elif waker_url := get_config()['devices'][dev].get('waker_url', missing):
    print('Waking server via custom URL...\n')
    cert = get_config()['devices'][dev].get('waker_cert', missing)
    if cert is missing:
      cert = get_cert_path()
    missioncontrollitelib.request(waker_url, verify = cert)
  state['last_wake'] = time.time()

def wake_if_idle(state):
  idle_timeout = get_config().get('idle_timeout', DEFAULT_IDLE_TIMEOUT)
  last_wake = state.get('last_wake', 0)
  if (time.time() - last_wake) > idle_timeout:
    wake(state)

def check_inbox(state):
  print('Getting inbox...')
  print('')
  try:
    inbox = get_inbox(state['name'], state['device'])
  except KeyboardInterrupt:
    print('Interrupted!')
    inbox = []
  print(f'Got {len(inbox)} message(s)')
  print('')
  for idx, message in enumerate(inbox):
    print(f'Message #{idx+1}')
    for section in message.get('sections', []):
      title = section['title'][:78]
      print('  ' + title)
      body = section.get('body')
      if body:
        print(wrap_and_indent(body))
    print('')

def device_menu(state):
  while True:
    wake_if_idle(state)
    print(' -= Device Menu =- ')
    print('')
    print(f'Current Device: {state['device']}')
    print('')
    commands = get_config()['devices'][state['device']]['commands']
    choices = [(idx+1, i) for idx, i in enumerate(commands.keys())]
    i = ask(choices + [
      ('i', 'Check Inbox'),
      ('w', 'Wake Again'),
      ('q', 'Quit'),
    ])
    if i == 'q':
      return
    elif i == 'w':
      wake(state)
      continue
    elif i == 'i':
      wake(state)
    else:
      command_name = dict(choices)[int(i)]
      command = commands[command_name]
      args = {}
      stdin = None
      if type(command) is dict:
        for arg in command.get('args', []):
          print(f'Enter value for "{arg}":')
          inp = input('> ')
          args[arg] = inp
          print('')
        if command.get('accepts_stdin'):
          print('Enter EOF string for stdin:')
          eof = input('> ')
          print('Enter stdin:')
          stdin = []
          while True:
            try:
              line = input('> ')
              if line == eof:
                break
              stdin.append(line)
            except EOFError:
              break
          if len(stdin) > 0:
            stdin = '\n'.join(stdin) + '\n'
          else:
            stdin = ''
      wake_if_idle(state)
      print('Sending request...')
      print('')
      send(state['device'],{
          'command_name': command_name,
          'sender': state['name'],
          'args': args,
          'stdin': stdin,
      })
    check_inbox(state)

def main_menu():
  try:
    with open('/proc/self/comm', 'r+') as f:
      f.write('MCLite-Client')
  except (FileNotFoundError, PermissionError):
    pass

  while True:
    print(' -= Main Menu =-')
    print('')
    print('Please select a device to control:')
    print('')
    choices = [(idx+1, i) for idx,i in 
               enumerate(get_config().get('devices', {}).keys())]
    i = ask(choices + [('q', 'Quit')])
    if i == 'q':
      return
    state = {
      'name': f'mclite_client_{uuid.uuid4()}',
      'device': dict(choices)[int(i)],
    }
    device_menu(state)

if __name__ == '__main__':
  main_menu()

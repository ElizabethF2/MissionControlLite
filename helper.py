#!/usr/bin/env python3

HELP_TEXT = '''
TODO
'''.lstrip()

import sys, os, subprocess, shutil

DEFAULT_ID_LENGTH = 32
DEFAULT_KEY_LENGTH = 64
DBUS_SEARCH_PATHS = (
  '/run/user',
)
XDG_RUNTIME_SEARCH_PATHS = DBUS_SEARCH_PATHS
VALID_CONTAINERS_NAME_CHARS = 'abcdefghijklmnopqrstuvwxyz_' + \
                              'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
DEFAULT_CONTAINER_ENGINES = ('podman', 'docker')
DEFAULT_CONTAINER_PREFIX = 'mclite_'
DEFAULT_CONTAINER_SHELL = '/bin/sh'

def ps(named_args):
  matches = set()
  margs = named_args.get('match', [])
  if type(margs) is str:
    margs = [margs]
  for marg in margs:
    matches.update(map(str.strip, marg.split(',')))
  results = {}
  import shlex
  try:
    for pid in os.listdir('/proc'):
      if not pid.isdigit():
        continue
      try:
        with open(f'/proc/{pid}/cmdline', 'r') as f:
          cmdline = f.read()
        cmdline = shlex.join(cmdline.split('\0')[:-1])
        if any((m in cmdline for m in matches)):
          results[pid] = cmdline
      except FileNotFoundError:
        pass
  except FileNotFoundError:
    if not (powershell := shutil.which('powershell')):
      raise
    procs = __import__('json').loads(subprocess.check_output((
      powershell, '-c',
      'Get-CimInstance -ClassName Win32_Process | ConvertTo-Json'
    )))
    for proc in procs:
      cmdline = proc['CommandLine']
      if any((m in cmdline for m in matches)):
          pid = proc['ProcessId']
          results[pid] = cmdline
  for pid in sorted(results.keys()):
    print(f'PID: {pid}')
    print(f'CMDLINE: {results[pid]}')
    print('')

def try_find_dbus_sessions(named_args):
  results = []
  sockets_by_uid = {}
  if addr := os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
    sockets_by_uid[os.getuid()] = addr
  import stat
  for search_path in DBUS_SEARCH_PATHS:
    for d in os.listdir(search_path):
      if not d.isdigit():
        continue
      uid = int(d)
      try:
        socket = os.path.join(search_path, d, 'bus')
        st = os.stat(socket)
        if stat.S_ISSOCK(st.st_mode):
          sockets_by_uid.setdefault(uid, []).append('unix:path=' + socket)
      except FileNotFoundError:
        continue
  users = named_args.get('user', [])
  if type(users) is str:
    users = [users]
  dbus_users = named_args.get('dbus_user', [])
  users += dbus_users if type(dbus_users) is list else [dbus_users]
  if users:
    import pwd
    for user in users:
      uid = pwd.getpwnam(user).pw_uid
      try:
        results.extend(((uid, i) for i in sockets_by_uid.pop(uid)))
      except KeyError:
        pass
  try:
    root_sockets = [(0, i) for i in sockets_by_uid.pop(0)]
  except KeyError:
    root_sockets = []
  for uid in sorted(sockets_by_uid.keys()):
    results.extend(((uid, i) for i in sockets_by_uid.pop(uid)))
  results.extend(root_sockets)
  return results

def kde_logout(named_args):
  action = named_args.get('action', 'logout')
  qdbus = shutil.which('qdbus') or \
          shutil.which('qdbus6') or \
          'qdbus5'
  if os.getuid() != 0 and 'DBUS_SESSION_BUS_ADDRESS' in os.environ:
    subprocess.check_call((qdbus,
                           'org.kde.Shutdown',
                           '/Shutdown',
                           f'org.kde.Shutdown.{action}'))
    return
  dbus_sessions = try_find_dbus_sessions(named_args)
  if len(dbus_sessions) < 0:
    raise RuntimeError('No DBUS sessions found - try a regular reboot instead')
  uid, addr = dbus_sessions[0]
  subprocess.check_call(('sudo',
                         'DBUS_SESSION_BUS_ADDRESS='+addr,
                         '-u', f'#{uid}',
                         qdbus,
                         'org.kde.Shutdown', 
                         '/Shutdown', 
                         f'org.kde.Shutdown.{action}'))

def get_container_name(name, named_args):
  prefix = named_args.get('prefix', DEFAULT_CONTAINER_PREFIX)
  if any((c not in VALID_CONTAINERS_NAME_CHARS for c in prefix)):
    raise ValueError(f'Invalid prefix: {prefix}')
  if any((c not in VALID_CONTAINERS_NAME_CHARS for c in name)):
    raise ValueError(f'Invalid prefix: {name}')
  return prefix+name

def get_container_engine(named_args):
  for engine in ([named_args.get('engine')] + DEFAULT_CONTAINER_ENGINES):
    if engine and (engine := shutil.which(engine)):
      return engine
  raise ValueError(f'No container engine found: install Podman or Docker, ' +
                   'specify an engine with --engine and/or check args')

def run_container_cmd(cmd, named_args, stdin = None):
  cmd_args = [get_container_engine(named_args), *cmd]
  if user := named_args.get('user'):
    cmd_args = ['sudo', '-u', user, *cmd_args]
  return subprocess.check_call(cmd_args, stdin = stdin)

def create_container(name, image, cmd, named_args):
  name = get_container_name(name, named_args)
  run_container_cmd(['container', 'create', '-it', 
                     '--name', name, image] + cmd,
                    named_args)

def delete_container(name, named_args):
  name = get_container_name(name, named_args)
  run_container_cmd(['rm', name], named_args)

def start_container(name, named_args):
  name = get_container_name(name, named_args)
  run_container_cmd(['start', name], named_args)

def stop_container(name, named_args):
  name = get_container_name(name, named_args)
  run_container_cmd(['stop', name], named_args)

def exec_in_container(name, named_args):
  name = get_container_name(name, named_args)
  shell = named_args.get('shell', DEFAULT_CONTAINER_SHELL)
  stdin = sys.stdin.buffer.read()
  run_container_cmd(['exec', '-i', name, shell], named_args, stdin = stdin)

def run_script_in_container(name, script_path, named_args):
  name = get_container_name(name, named_args)
  shell = named_args.get('shell', DEFAULT_CONTAINER_SHELL)
  with open(script_path, 'rb') as f:
    contents = f.read()
  run_container_cmd(['exec', '-i', name, shell], named_args, stdin = contents)

def _try_runuser(user, env, cmd):
  if getattr(os, 'getuid', str)() != 0:
    return None
  runuser = shutil.which('runuser')
  if not runuser:
    return None
  env_bin = shutil.which('env')
  if not env_bin:
    return None
  if user.startswith('#'):
    found = False
    uid = int(user[1:])
    import pwd
    for entry in pwd.getpwall():
      if entry.pw_uid == uid:
        user = entry.pw_name
        found = True
    if not found:
      raise ValueError(f'Invalid UID: {uid}')
  p = subprocess.check_call([runuser, '-u'+user, '--', env_bin] +
                            [k+'='+v for k,v in env.items()] +
                            cmd)
  return p

def run_as_user(cmd, named_args):
  dbus_sessions = try_find_dbus_sessions(named_args)
  if len(dbus_sessions) < 0:
    raise RuntimeError('No DBUS sessions found')
  uid, addr = dbus_sessions[0]
  env = {'DBUS_SESSION_BUS_ADDRESS': addr}
  sudo_user = named_args.get('sudo_user')
  use_sudo = True
  if sudo_user:
    user = sudo_user if type(sudo_user) is str else sudo_user[0]
    import getpass
    use_sudo = (getpass.getuser() != user)
  else:
    user = f'#{uid}'
    use_sudo = (os.getuid() != uid)
  for rt_root in XDG_RUNTIME_SEARCH_PATHS:
    rt_dir = os.path.join(rt_root, str(uid))
    if os.path.isdir(rt_dir):
      env['XDG_RUNTIME_DIR'] = rt_dir
      xauths = list(filter(lambda i: i.startswith('xauth_'),
                           os.listdir(rt_dir)))
      xauths = [(i, os.path.getmtime(i)) for i in 
                (os.path.join(rt_dir, i) for i in xauths)]
      xauths = sorted(xauths, key = lambda i: i[1])
      if len(xauths) > 0:
        env['XAUTHORITY'] = xauths[0][0]
      break
  import tempfile
  try:
    for x in sorted(os.listdir(os.path.join(tempfile.gettempdir(),
                                            '.X11-unix'))):
      if x.startswith('X') and x[1:].isdigit():
        env['DISPLAY'] = f':{x[1:]}'
  except FileNotFoundError:
    pass
  try:
    for w in sorted(os.listdir(env['XDG_RUNTIME_DIR'])):
      if w.startswith('wayland-') and w[8:].isdigit():
        env['WAYLAND_DISPLAY'] = w
  except KeyError:
    pass
  if use_sudo:
    if not _try_runuser(user, env, cmd):
      subprocess.check_call(['sudo'] +
                            [k+'='+v for k,v in env.items()] +
                            ['-u', user, '--'] + cmd)
  else:
    subprocess.check_call(cmd, env = os.environ | env)

def get_sessions(user = None):
  import json
  js = json.loads(subprocess.check_output(
          ('loginctl', 'list-sessions', '-j')
  ))
  if not user:
    return js
  return list(filter(lambda i: i.get('user') == user, js))

def show_sessions(user = None):
  for idx, session in enumerate(get_sessions(user = user)):
    if idx > 0:
      print('')
    for k, v in session.items():
      print('# ' + repr(k) + ': ' + repr(v))
    print(subprocess.check_output(
          ('loginctl', 'show-session', str(session.get('session')))
    ).decode().strip())

def login_and_lock(user, session, conf):
  if len(get_sessions(user = user)) > 0:
    subprocess.check_call(('loginctl', 'lock-sessions'))
    return
  entries = (
    ('Relogin', 'true'),
    ('Session', session),
    ('User', user),
  )
  with open(conf, 'r') as f:
    txt = f.read()
  import re, tempfile, time, stat
  for k,v in entries:
    txt = re.sub('\n'+k+'=.*', '\n'+k+'='+v, txt)
  tf = tempfile.NamedTemporaryFile(mode = 'w', prefix = 'sddm_conf_')
  tf.write(txt)
  tf.flush()
  os.chmod(tf.fileno(), os.stat(conf).st_mode)
  subprocess.check_call(('mount', '--bind', tf.name, conf))
  subprocess.check_call(('systemctl', 'restart', 'display-manager.service'))
  while True:
    time.sleep(0.1)
    if len(get_sessions(user = user)) > 0:
      subprocess.check_call(('umount', conf))
      tf.close()
      break
  subprocess.check_call(('loginctl', 'lock-sessions'))

def generate_key(key_length = DEFAULT_KEY_LENGTH, b85 = True):
  key = b''
  while len(key) < key_length:
    key += getrandom(1, getattr(os, 'GRND_RANDOM', 0)) \
           if (getrandom := getattr(os, 'getrandom', None)) else \
           os.urandom(1)
  import base64
  return base64.b85encode(key).decode() if b85 else key

def generate_id(id_length = DEFAULT_ID_LENGTH):
  i = ''
  while len(i) < id_length:
    try:
      c = generate_key(key_length = 1, b85 = False).decode()
      if c in VALID_CONTAINERS_NAME_CHARS:
        i += c
    except UnicodeDecodeError:
      pass
  return i

def generate_config(key_length = DEFAULT_KEY_LENGTH,
                    id_length = DEFAULT_ID_LENGTH,
                    name = None):
  out = [
    f'[devices.{name}]',
    f"waker_name = '{name}-Waker-{generate_id(id_length = id_length)}'",
    f"server_name = '{name}-Server-{generate_id(id_length = id_length)}'",
    f"server_key = '{generate_key(key_length = key_length)}'",
    f"client_key = '{generate_key(key_length = key_length)}'",
  ]
  return ''.join((line + '\n' for line in out))

def main():
  positional_args = []
  named_args = {}
  current_name = None
  hit_end_of_named_args = False
  for arg in sys.argv[1:]:
    if arg == '--' and not hit_end_of_named_args:
      hit_end_of_named_args = True
      current_name = None
    elif arg[:2] == '--' and not hit_end_of_named_args:
      current_name = arg[2:]
    elif current_name is None:
      positional_args.append(arg)
    else:
      if type(named_args.get(current_name)) is str:
        named_args[current_name] = [named_args[current_name], arg]
      else:
        named_args[current_name] = arg
  if not positional_args:
    raise ValueError('No command given')
  command = positional_args[0]
  if command == 'ps':
    return ps(named_args)
  elif command == 'kde_logout':
    return kde_logout(named_args)
  elif command == 'create_container':
    name = positional_args[1]
    image = positional_args[2]
    cmd = positional_args[3:]
    return create_container(name, image, cmd, named_args)
  elif command == 'delete_container':
    name = positional_args[1]
    return delete_container(name, named_args)
  elif command == 'start_container':
    name = positional_args[1]
    return start_container(name, named_args)
  elif command == 'stop_container':
    name = positional_args[1]
    return stop_container(name, named_args)
  elif command == 'exec_in_container':
    name = positional_args[1]
    return exec_in_container(name, named_args)
  elif command == 'run_script_in_container':
    name = positional_args[1]
    script = positional_args[2]
    return run_script_in_container(name, script, named_args)
  elif command == 'run_as_user':
    cmd = positional_args[1:]
    return run_as_user(cmd, named_args)
  elif command == 'show_sessions':
    return show_sessions(user = named_args.get('user'))
  elif command == 'login_and_lock':
    user = positional_args[1]
    session = positional_args[2]
    conf = positional_args[3]
    return login_and_lock(user, session, conf)
  elif command == 'generate_key':
    kl = int(named_args.get('length', DEFAULT_KEY_LENGTH))
    return print(generate_key(key_length = kl))
  elif command == 'generate_id':
    il = int(named_args.get('length', DEFAULT_ID_LENGTH))
    return print(generate_id(id_length = il))
  elif command == 'generate_config':
    kl = int(named_args.get('key_length', DEFAULT_KEY_LENGTH))
    il = int(named_args.get('id_length', DEFAULT_ID_LENGTH))
    name = named_args.get('name')
    return print(generate_config(key_length = kl, id_length = il, name = name))
  elif command == 'help':
    return print(HELP_TEXT)
  else:
    raise ValueError(f'Invalid command: {command}\nRun `help` for help')

if __name__ == '__main__':
  main()

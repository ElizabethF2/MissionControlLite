#!/usr/bin/env python3

import os, collections, functools

_vdf_escape_chars = {
  'n': '\n',
  'r': '\r',
  't': '\t',
}

_locks = {}

INFINITE = 0xFFFFFFFF
WAIT_FAILED = 0xFFFFFFFF
WAIT_TIMEOUT = 0x00000102

def acquire_lock():
  try:
    import fcntl, errno, tempfile
    d = tempfile.gettempdir()
    f = f'steamrollr.{os.getuid()}.lock'
    while True:
      fh = open(os.path.join(d, f), 'wb')
      fcntl.lockf(fh, fcntl.LOCK_EX)
      try:
        if os.fstat(fh.fileno()) == os.stat(fh.name):
          break
      except FileNotFoundError:
        pass
      fh.close()
    _locks['fh'] = fh
  except ModuleNotFoundError:
    import ctypes
    n = 'steamrollr-mutex'
    handle = ctypes.windll.kernel32.CreateMutexW(0, False, n.encode())
    if not handle:
      raise ctypes.WinError()
    r = ctypes.windll.kernel32.WaitForSingleObject(handle, INFINITE)
    if r == WAIT_FAILED:
      raise ctypes.WinError()
    if r == WAIT_TIMEOUT:
      return False
    _locks['handle'] = handle

def release_lock():
  try:
    fh = _locks.pop('fh')
    os.remove(fh.name)
    fh.close()
  except KeyError:
    import ctypes
    handle = _locks.pop('handle')
    if not ctypes.windll.kernel32.ReleaseMutex(handle):
      raise ctypes.WinError()
    if not ctypes.windll.kernel32.CloseHandle(handle):
      raise ctypes.WinError()

def _vdf_error(error, line, column, fmt, *args):
  e = '[Line: {}, Column: {}] {}'.format(line, column, fmt.format(*args))
  raise error(e)

def _bvdf_error(error, offset, state, fmt, *args):
  raise error('[Offset: {}, State: {}] {}'.format(offset, state, fmt.format(*args)))

_VDF_BIN_START_DICT = b'\x00'
_VDF_BIN_END_DICT = b'\x08'
_VDF_BIN_START_STR = b'\x01'
_VDF_BIN_END_STR = b'\x00'
_VDF_BIN_START_UINT32 = b'\x02'

def load_binary_vdf(vdf, encoding = 'utf-8', read_to_eof = True):
  if type(vdf) is str:
    vdf = vdf.encode()
  if type(vdf) is bytes:
    import io
    vdf = io.BytesIO(vdf)
  stack = [{}]
  state = 'in_dict'
  buf = b''
  off = -1
  while True:
    b = vdf.read(1)
    off += 1
    if not b:
      break
    if state == 'in_dict':
      if b == _VDF_BIN_START_DICT:
        state = 'in_str_dict_key'
      elif b == _VDF_BIN_START_STR:
        state = 'in_str_str_key'
      elif b == _VDF_BIN_START_UINT32:
        state = 'in_str_uint32_key'
      elif b == _VDF_BIN_END_DICT:
        if len(stack) == 1:
          state = 'root_end'
        elif len(stack) >= 2:
          v = stack.pop()
          k = stack.pop()
          if type(k) not in (str, bytes):
            _bvdf_error(ValueError, off, state,
                        'End of dict with non-string key: {}', repr(k))
          if type(v) is not collections.OrderedDict:
            _bvdf_error(ValueError, off, state,
                        'End of dict with non-dict value: {}', repr(v))
          stack[-1][k] = v
        else:
          _bvdf_error(RuntimeError, off, state, 'Invalid stack: {}', stack)
        if not read_to_eof and len(stack) == 1:
          break
      else:
        _bvdf_error(ValueError, off, state, 'Unexpected byte in dict: {}', b)
    elif state.startswith('in_str_'):
      if b == _VDF_BIN_END_STR:
        try:
          buf = buf.decode(encoding = encoding)
        except UnicodeDecodeError:
          pass
        if state == 'in_str_dict_key':
          stack.append(buf)
          stack.append(collections.OrderedDict())
          state = 'in_dict'
        elif state == 'in_str_str_key':
          stack.append(buf)
          state = 'in_str_value'
        elif state == 'in_str_value':
          k = stack.pop()
          stack[-1][k] = buf
          state = 'in_dict'
        elif state == 'in_str_uint32_key':
          stack[-1][buf] = int.from_bytes(vdf.read(4),
                                          byteorder = 'little',
                                          signed = False)
          off += 4
          state = 'in_dict'
        else:
          _bvdf_error(ValueError, off, state, 'Invalid state at end of string')
        buf = b''
      else:
        buf += b
    elif state == 'root_end':
      _bvdf_error(ValueError, off, state,
                  'Unexpected byte after root dict: {}', b)
    else:
      _bvdf_error(RuntimeError, off, state, 'Unexpected state')
  k = list(stack[0].keys())
  if len(k) != 1:
    _bvdf_error(ValueError, off, state, 'Invalid root keys: {}', k)
  return k[0], stack[0][k[0]]

class _ByteBuff(object):
  def __init__(self, fh, encoding):
    self.fh = fh
    self.encoding = getattr(fh, 'encoding', encoding)
    import io
    self.buffer = io.BytesIO()

  def read(size = -1):
    ret = self.buffer.read(size = size)
    if len(ret) < size or size == -1:
      remaining = size - len(ret)
      b = self.fh.read(-1 if size == -1 else remaining)
      b = b.encode(encoding = self.encoding)
      if size == -1:
        ret += b
      else:
        ret += b[:remaining]
        self.buffer.write(b[remaining:])
    return ret

def load_vdf(vdf, encoding = 'utf-8', read_to_eof = True):
  if type(vdf) is bytes:
    raw_vdf = vdf
    try:
      vdf = vdf.decode(encoding = encoding)
    except UnicodeDecodeError:
      return load_binary_vdf(raw_vdf,
                             encoding = encoding,
                             read_to_eof = read_to_eof)
  else:
    raw_vdf = getattr(vdf, 'buffer', None)
  if type(vdf) is str:
    import io
    vdf = io.StringIO(vdf)
  stack = [{}]
  delim = None
  escaped = False
  is_value = False
  buf = ''
  ln = 1
  cl = 0
  tell = getattr(vdf, 'tell', None)
  initial_position = tell() if tell else None
  tell = getattr(raw_vdf, 'tell', None)
  initial_raw_position = tell() if tell else None
  while True:
    try:
      c = vdf.read(1)
    except UnicodeDecodeError:
      if ln != 1 or cl != 0:
        raise
      c = '\0'
    if ln == 1 and cl == 0:
      if type(c) is bytes:
        if raw_vdf is None:
          raw_vdf = vdf
          initial_raw_position = initial_position
        if c == b'\0':
          c = '\0'
        else:
          if initial_position is None:
            vdf.tell()
          vdf.seek(initial_position)
          import io
          vdf = io.TextIOWrapper(vdf, encoding = encoding)
          try:
            c = vdf.read(1)
          except UnicodeDecodeError:
            c = '\0'
      if c == '\0':
        if initial_raw_position is not None:
          vdf.seek(initial_raw_position)
        if raw_vdf is None:
          raw_vdf = _ByteBuff(fh)
        return load_binary_vdf(raw_vdf)
    if c == '\n':
      ln += 1
      cl = 0
    else:
      cl += 1
    if not c:
      break
    if delim:
      if escaped:
        buf += _vdf_escape_chars.get(c, c)
        escaped = False
      elif c == '\\':
        escaped = True
      elif c == delim:
        delim = None
        if is_value:
          k = stack.pop()
          stack[-1][k] = buf
        else:
          stack.append(buf)
        is_value = not is_value
        buf = ''
      else:
        buf += c
    else:
      if escaped:
        _vdf_error(RuntimeError, ln, cl, 'Escaped outside of string')
      if c in '"\'':
        delim = c
      elif c == '{':
        if not is_value:
          _vdf_error(ValueError, ln, cl, 'Key must be string')
        stack.append(collections.OrderedDict())
        is_value = False
      elif c == '}':
        if is_value:
          _vdf_error(ValueError, ln, cl,
                               'Unexpected end of dict before value')
        try:
          v = stack.pop()
        except IndexError:
          v = None
        if type(v) is not collections.OrderedDict:
          _vdf_error(ValueError, ln, cl, 'Unexpected end of dict outside of dict')
        try:
          k = stack.pop()
        except IndexError:
          k = None
        if type(k) is not str:
          _vdf_error(ValueError, ln, cl, 'Key must be string')
        stack[-1][k] = v
        if not read_to_eof and len(stack) == 1:
          break
      elif not c.isspace():
        _vdf_error(ValueError, ln, cl,
                             'Unexpected char {} outside of string', repr(c))
  k = list(stack[0].keys())
  if len(k) != 1:
    _vdf_error(ValueError, ln, cl, 'Invalid root keys: {}', k)
  return k[0], stack[0][k[0]]

@functools.cache
def get_config():
  path = os.environ.get('STEAMROLLR_CONFIG')
  if not path:
    xdg_config_home = os.environ.get('XDG_CONFIG_HOME')
    if xdg_config_home:
      path = os.path.join(xdg_config_home, 'steamrollr.vdf')
  if not path:
    appdata = os.environ.get('APPDATA')
    if appdata:
      path = os.path.join(appdata, 'steamrollr.vdf')
  if not path:
    path = os.path.expanduser(os.path.join('~', '.config', 'steamrollr.vdf'))
  with open(path, 'rb') as f:
    _, config = load_vdf(f)
  return config

def get_snapshot_path():
  path = get_config().get('snapshot_path')
  if path:
    return path
  filename = get_config().get('snapshot_filename', 'snapshots.gz')
  state_dir = get_config().get('state_dir')
  if state_dir:
    return os.path.join(state_dir, filename)
  state_dir = os.environ.get('XDG_STATE_HOME')
  if state_dir:
   return os.path.join(state_dir, 'steamrollr', filename)
  state_dir = os.environ.get('LOCALAPPDATA')
  if state_dir:
    return os.path.join(state_dir, 'steamrollr', filename)
  path = os.path.join('~', '.local', 'state', 'steamrollr', filename)
  return os.path.expanduser(path)

_SIZE_NONE = b'\x00'
_SIZE_ZERO = b'\x01'
_SIZE_UINT8 = b'\x02'
_SIZE_UINT16 = b'\x03'
_SIZE_UINT32 = b'\x04'
_SIZE_UINT64 = b'\x05'
_SIZE_INT_STR = b'\x06'

_COUNT_MAX = 255

def dump_string(s, fh):
  buf = s.encode()
  if b'\0' in buf:
    raise ValueError('Invalid string: {}'.format(buf))
  fh.write(buf)
  fh.write(b'\0')

def load_string(fh):
  buf = b''
  while True:
    b = fh.read(1)
    if not b or b == b'\0':
      break
    buf += b
  return buf.decode()

def dump_uint(value, length, fh):
  fh.write(value.to_bytes(length = length,
                          byteorder = 'little',
                          signed = False))

def load_uint(length, fh):
  buf = fh.read(length)
  if len(buf) < length:
    raise ValueError('Unexpected EOF')
  return int.from_bytes(buf,
                        byteorder = 'little',
                        signed = False)

def dump_size(size, fh):
  if size is None:
    return fh.write(_SIZE_NONE)
  if size == 0:
    return fh.write(_SIZE_ZERO)
  if size < 256:
    fh.write(_SIZE_UINT8)
    return dump_uint(size, 1, fh)
  if size < 65536:
    fh.write(_SIZE_UINT16)
    return dump_uint(size, 2, fh)
  if size < 4294967296:
    fh.write(_SIZE_UINT32)
    return dump_uint(size, 4, fh)
  if size < 18446744073709551616:
    fh.write(_SIZE_UINT64)
    return dump_uint(size, 8, fh)
  fh.write(_SIZE_INT_STR)
  dump_string(str(size))

def load_size(fh):
  tag = fh.read(1)
  if tag == _SIZE_NONE:
    return None
  if tag == _SIZE_ZERO:
    return 0
  if tag == _SIZE_UINT8:
    return load_uint(1, fh)
  elif tag == _SIZE_UINT16:
    return load_uint(2, fh)
  elif tag == _SIZE_UINT32:
    return load_uint(4, fh)
  elif tag == _SIZE_UINT64:
    return load_uint(8, fh)
  elif tag == _SIZE_INT_STR:
    return int(load_string(fh))
  else:
    raise ValueError('Invalid size tag: {}'.format(tag))  

def dump_node(name, node, fh):
  dump_string(name, fh)
  size = node.get('size')
  dump_size(size, fh)
  dump_uint(round(node['mtime']), 4, fh)
  if size:
    fh.write(node['sha256'])
  elif size is None:
    dump_nodes(node.get('children', {}), fh)

def dump_nodes(nodes, fh):
  remaining = 0
  for idx, node in enumerate(nodes.items()):
    if idx % _COUNT_MAX == 0:
      remaining = len(nodes) - idx
      if remaining > _COUNT_MAX:
        dump_uint(_COUNT_MAX, 1, fh)
      else:
        dump_uint(remaining, 1, fh)
    name, node = node
    dump_node(name, node, fh)
  if remaining in (0, _COUNT_MAX):
    dump_uint(0, 1, fh)

def load_node(fh):
  node = {}
  name = load_string(fh)
  size = load_size(fh)
  if size is not None:
    node['size'] = size
  node['mtime'] = load_uint(4, fh)
  if size:
    h = fh.read(32)
    if len(h) < 32:
      raise ValueError('Unexpected EOF')
    node['sha256'] = h
  elif size is None:
    children = load_nodes(fh)
    if len(children) > 0:
      node['children'] = children
  return name, node

def load_nodes(fh):
  nodes = {}
  while True:
    count = load_uint(1, fh)
    for _ in range(count):
      node_name, node = load_node(fh)
      nodes[node_name] = node
    if count < _COUNT_MAX:
      break
  return nodes

def dump_snapshots(snapshots, fh):
  for slug, snapshot in snapshots.items():
    dump_string(slug, fh)
    dump_nodes(snapshot, fh)
  dump_string('', fh)

def load_snapshots(fh):
  snapshots = {}
  while True:
    slug = load_string(fh)
    if not slug:
      break
    snapshot = load_nodes(fh)
    snapshots[slug] = snapshot
  return snapshots

def read_snapshots():
  import gzip
  try:
    with gzip.open(get_snapshot_path(), 'rb') as gf:
      return load_snapshots(gf)
  except FileNotFoundError:
    return {}

def write_snapshots(snapshots):
  path = get_snapshot_path()
  import gzip
  os.makedirs(os.path.dirname(path), exist_ok = True)
  with gzip.open(get_snapshot_path(), 'wb') as gf:
    dump_snapshots(snapshots, gf)

def parse_bool(b):
  if b in (True, False):
    return b
  s = str(b).strip().lower()
  if s in ('y', 'yes', 'true', '1'):
    return True
  if s in ('n', 'no', 'false', '0'):
    return False
  raise ValueError('Invalid bool: {}'.format(repr(b)))

_SLUG_VALID_CHARS = 'abcdefghijklmnopqrstuvwxyz0123456789'

def make_slug(game):
  if (appid := game.get('appid')) is None:
    appid = os.path.basename(game['install_dir'])
  slug = get_config().get('slugs', {}).get(appid)
  if not slug:
    slug = os.path.basename(game['install_dir']).lower()
  slug = ''.join((c if c in _SLUG_VALID_CHARS else '' for c in slug))
  if not slug:
    e = ('Unable to generate slug for {}. '.format(repr(game.get('name'))) +
         'Please manually set one in the config.')
    raise ValueError(e)
  return slug

def get_library_path(library, mount = True):
  path = os.path.expandvars(os.path.expanduser(library['path']))
  root = library.get('root')
  if root:
    path = os.path.join(os.path.expandvars(os.path.expanduser(root)), path)
  mount_cmd = library.get('mount_cmd')
  if mount_cmd:
    if not root:
      print('WARNING mount_cmd was specified but root was not')
    eroot = root if root else path
    if mount and not os.path.ismount(eroot):
      import subprocess, shlex
      subprocess.check_call(shlex.split(mount_cmd))
  return path

def make_steam_game(appsdir, fname):
  if not fname.startswith('appmanifest_'):
    return None
  path = os.path.join(appsdir, fname)
  with open(path, 'rb') as f:
    root_key, vdf = load_vdf(f)
  appid = vdf.get('appid')
  install_dir = vdf.get('installdir')
  if not appid or not install_dir:
    return None
  install_dir = os.path.join(appsdir, 'common', install_dir)
  game = {'appid': str(appid), 'install_dir': install_dir}
  name = vdf.get('name')
  if name:
    game['name'] = name
  return game

def make_basic_game(appsdir, fname):
  return {
    'name': fname,
    'install_dir': os.path.join(appsdir, fname),
  }

def list_library(library):
  games = {}
  no_snapshot = parse_bool(library.get('no_snapshot', False))
  kind = library.get('kind', 'steam')
  if kind not in ('steam', 'basic'):
    raise ValueError('Invalid kind {}'.format(repr(kind)))
  appsdir = get_library_path(library, mount = True)
  try:
    with open(os.path.join(appsdir, 'libraryfolder.vdf'), 'r') as f:
      root_key, vdf = load_vdf(f)
    if root_key == 'libraryfolder':
      appsdir = os.path.join(appsdir, 'steamapps')
  except FileNotFoundError:
    pass  
  for f in os.listdir(appsdir):
    if kind == 'steam':
      game = make_steam_game(appsdir, f)
    elif kind == 'basic':
      game = make_basic_game(appsdir, f)
    if game is None:
      continue
    if no_snapshot:
      game['no_snapshot'] = True
    games[make_slug(game)] = game
  return games

def list_libraries():
  games = {}
  for library in get_config()['libraries'].values():
    library_games = list_library(library)
    for slug, game in library_games.items():
      if slug not in games:
        games[slug] = game
  return games

def copy_with_snapshots(src_dir,
                        dest_dir = None,
                        reference_snapshot = None,
                        delete_src = False):
  if delete_src:
    paths_to_delete = []
  snapshot = {}
  queue = [[]]
  if dest_dir:
    dest_st = os.stat(dest_dir)
    dest_dir = os.path.join(dest_dir, os.path.basename(src_dir))
    try:
      os.mkdir(dest_dir)
      os.chown(dest_dir, dest_st.st_uid, dest_st.st_gid)
    except FileExistsError:
      pass
  while len(queue) > 0:
    subpaths = queue.pop()
    snaproot = snapshot
    refroot = None if reference_snapshot is None else reference_snapshot
    for p in subpaths:
      snaproot = snaproot['children'][p]
      refroot = None if refroot is None else refroot.get(p).get('children', {})
    with os.scandir(os.path.join(src_dir, *subpaths)) as it:
      for entry in it:
        st = entry.stat()
        mtime = round(st.st_mtime)
        node = {'mtime': mtime}
        name = entry.name
        entry_subpaths = subpaths + [name]
        entry_subpath_str = os.path.join(*entry_subpaths)
        if entry.is_dir():
          if (reference_snapshot is None or 
              (name in refroot and 
               'size' not in refroot[name])):
            queue.append(entry_subpaths)
            if dest_dir:
              dest_path = os.path.join(dest_dir, entry_subpath_str)
              try:
                os.mkdir(dest_path)
                os.chown(dest_path, dest_st.st_uid, dest_st.st_gid)
                ref_mtime = (snaproot or {}).get(name, {}).get('mtime', mtime)
                os.utime(dest_path, times = (ref_mtime, ref_mtime))
              except FileExistsError:
                pass
          if delete_src:
            paths_to_delete.append((os.rmdir,
                                    os.path.join(src_dir, entry_subpath_str)))
        else:
          size = st.st_size
          node['size'] = size
          if (reference_snapshot is None or 
              (name in refroot and
               refroot[name]['size'] == size)):
            dest_fh = None
            digest = None
            with open(os.path.join(src_dir,
                                   entry_subpath_str), 'rb') as src_fh:
              try:
                if dest_dir:
                  dest_fh = open(os.path.join(dest_dir,
                                              entry_subpath_str), 'wb')
                if size > 0:
                  h = __import__('hashlib').sha256()
                  while True:
                    b = src_fh.read(512*1024)
                    if not b:
                      break
                    h.update(b)
                    if dest_fh:
                      dest_fh.write(b)
                  digest = h.digest()
                  node['sha256'] = digest
              finally:
                if dest_fh is not None:
                  dest_fh.close()
                  os.chown(dest_fh.name, dest_st.st_uid, dest_st.st_gid)
                  ref_mtime = (snaproot or {}).get(name, {}).get('mtime',
                                                                 mtime)
                  os.utime(dest_fh.name, times = (ref_mtime, ref_mtime))
              if (size > 0 and
                  dest_fh is not None and
                  reference_snapshot is not None and
                  (refroot or {}).get(name, {}).get('sha256') != digest):
                os.remove(dest_fh.name)
          if delete_src:
            paths_to_delete.append((os.remove,
                                    os.path.join(src_dir, entry_subpath_str)))
        snaproot.setdefault('children', {})[name] = node
  if delete_src:
    for remove, path in paths_to_delete:
      remove(path)
  snapshot = snapshot.get('children', {})
  return snapshot

def try_find_reference_snapshot(slug):
  acquire_lock()
  try:
    snapshots = read_snapshots()
  finally:
    release_lock()
  return snapshots.get(slug)

def try_find_game_source(slug, need_snapshot):
  games = list_libraries()
  game = games.get(slug, {})
  if need_snapshot and game.get('no_snapshot', False):
    game = {}
  return game.get('install_dir')

def move_or_copy_or_snapshot_internal(slug,
                                      dest_library = None,
                                      delete_src = False):
  reference_snapshot = try_find_reference_snapshot(slug)
  need_snapshot = not reference_snapshot
  src_dir = try_find_game_source(slug, need_snapshot)
  if not src_dir:
    raise FileNotFoundError('No suitable source for {}'.format(repr(slug)))
  if dest_library:
    dest_library = get_config()['libraries'][dest_library]
    dest_dir = get_library_path(dest_library)
    if dest_library.get('kind', 'steam') == 'steam':
      dest_dir = os.path.join(dest_dir, 'common')
  else:
    if reference_snapshot:
      return
    dest_dir = None
  new_snapshot = copy_with_snapshots(src_dir,
                                     reference_snapshot = reference_snapshot,
                                     dest_dir = dest_dir,
                                     delete_src = delete_src)
  if need_snapshot:
    acquire_lock()
    try:
      snapshots = read_snapshots()
      snapshots[slug] = new_snapshot
      write_snapshots(snapshots)
    finally:
      release_lock()

def purge(slugs = None, uninstalled = False, all = False):
  if all:
    try:
      snapshot_path = get_snapshot_path()
      os.remove(snapshot_path)
      os.rmdir(os.path.dirname(snapshot_path))
    except OSError:
      pass
    return
  if slugs is None:
    slugs = []
  if uninstalled:
    games = list_libraries()
  acquire_lock()
  try:
    snapshots = read_snapshots()
    modified = False
    for slug in slugs:
      snapshots.pop(slug)
      modified = True
    for slug in list(snapshots.keys()):
      if uninstalled and slug not in games:
        snapshots.pop(slug)
        modified = True
    if modified:
      write_snapshots(snapshots)
  finally:
    release_lock()

def print_games():
  games = list_libraries()
  for slug in sorted(games.keys()):
    print('Slug: {}'.format(slug))
    game = games[slug]
    print('Name: {}'.format(game.get('name')))
    print('AppID: {}'.format(game.get('appid')))
    print('Source: {}'.format(game.get('install_dir')))
    can_snapshot = not parse_bool(game.get('no_snapshot', False))
    print('Can Snapshot: {}'.format(can_snapshot))
    print('')

def print_snaps(slugs):
  acquire_lock()
  try:
    snapshots = read_snapshots()
  finally:
    release_lock()
  import pprint
  for slug in sorted(slugs):
    print(slug)
    pprint.pp(snapshots.get(slug),
              sort_dicts = True)
    print('')

_command_aliases = {
  'ls': 'list',
  'mv': 'move',
  'cp': 'copy',
  'snap': 'snapshot',
  'ds': 'dump_snaps',
}

def main():
  import sys
  args = list(reversed(sys.argv[1:]))
  command = None
  purge_uninstalled = False
  purge_all = False
  slugs = []
  while len(args) > 0:
    arg = args.pop()
    if command is None:
      command = _command_aliases.get(arg, arg)
    elif command == 'purge' and arg == '--uninstalled':
      purge_uninstalled = True
    elif command == 'purge' and arg == '--all':
      purge_all = True
    elif command in ('copy', 'move', 'purge', 'snapshot', 'dump_snaps'):
      slugs.append(arg)
    else:
      raise ValueError('Unexpected arguement: {}'.format(repr(arg)))  
  if command == 'list':
    print_games()
  elif command == 'snapshot':
    for slug in slugs:
      move_or_copy_or_snapshot_internal(slug,
                                        dest_library = None,
                                        delete_src = False)
  elif command == 'copy':
    library = slugs.pop()
    for slug in slugs:
      move_or_copy_or_snapshot_internal(slug,
                                        dest_library = library,
                                        delete_src = False)
  elif command == 'move':
    library = slugs.pop()
    for slug in slugs:
      move_or_copy_or_snapshot_internal(slug,
                                        dest_library = library,
                                        delete_src = True)
  elif command == 'purge':
    purge(slugs, uninstalled = purge_uninstalled, all = purge_all)
  elif command == 'dump_snaps':
    print_snaps(slugs)
  else:
    print('Steamrollr is a tool for securely moving Steam games between ' +
          'trusted and\nuntrusted sandboxes. See its manual for usage ' + 
          'instructions.')

if __name__ == '__main__':
  main()

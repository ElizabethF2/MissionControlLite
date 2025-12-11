import os, base64, hashlib, tempfile, getpass, time, functools
import ssl, urllib.request, urllib.parse, json

try:
  import cryptography.hazmat.primitives.ciphers
  import cryptography.hazmat.primitives.hashes
  import cryptography.hazmat.primitives.hmac
  import cryptography.hazmat.primitives.padding
except ModuleNotFoundError:
  pass

DEFAULT_IDLE_TIMEOUT = 300
DEFAULT_WATCHDOG_TIMEOUT = 300
DEFAULT_CONFIG_NAME = 'config.toml'
DEFAULT_CONFIG_ENV_VAR_NAME = 'MISSIONCONTROLLITELIBCONFIG'
DEFAULT_CERT_NAME = 'cert.pem'
DEFAULT_NAMESPACES = ('mclite', 'missioncontrollite', 'mission-control-lite')
DEFAULT_CONFIG_DIRS = (
  os.path.join('/etc', 'v_NAMESPACE'),
  os.path.join('/srv', 'v_NAMESPACE'),
  os.path.join('/opt', 'v_NAMESPACE'),
  os.path.dirname(__file__),
  os.curdir,
)

@functools.cache
def get_config_and_config_path(**kwargs):
  import tomllib
  var = kwargs.get('config_env_var_name', DEFAULT_CONFIG_ENV_VAR_NAME)
  if var:
    path = os.environ.get(var)
    if path:
      with open(path, 'rb') as f:
        return tomllib.load(f)
  xdg_config_home = os.environ.get('XDG_CONFIG_HOME')
  namespace = kwargs.get('namespace')
  namespaces = (namespace,) if namespace else DEFAULT_NAMESPACES
  config_name = kwargs.get('config_name', DEFAULT_CONFIG_NAME)
  for namespace in namespaces:
    if not xdg_config_home:
      xdg_config_home = os.path.join(os.path.expanduser('~'), '.config')
    try:
      with open(os.path.join(xdg_config_home, namespace, config_name), 'rb') as f:
        return tomllib.load(f), f.name
    except FileNotFoundError:
      pass
  config_paths = kwargs.get('config_paths', DEFAULT_CONFIG_DIRS)
  for config_path in config_paths:
    for namespace in namespaces:
      if config_paths is DEFAULT_CONFIG_DIRS:
        config_dir = config_path.replace('v_NAMESPACE', namespace)
        paths = [os.path.join(config_dir, config_name)]
      else:
        paths = [config_path, os.path.join(config_path, config_name)]
      for path in paths:
        try:
          with open(path, 'rb') as f:
            return tomllib.load(f), f.name
        except IsADirectoryError:
          continue
        except FileNotFoundError:
          break
      if config_paths is not DEFAULT_CONFIG_DIRS:
        break
  raise FileNotFoundError('Config file missing')

def get_config(**kwargs):
  return get_config_and_config_path(**kwargs)[0]

def get_config_path(**kwargs):
  return get_config_and_config_path(**kwargs)[1]

def get_cert_path(**kwargs):
  cert = get_config(**kwargs).get('mcbus_cert')
  if cert:
    return cert
  return os.path.join(os.path.dirname(get_config_path()), DEFAULT_CERT_NAME)

def get_watchdog_file(name = None):
  name = name if name else DEFAULT_NAMESPACES[0]
  fname = f'{name}-{getpass.getuser()}.watchdog'
  return os.path.join(tempfile.gettempdir(), fname)

def watchdog_tick(name = None, mode = 0o600):
  flags = os.O_WRONLY | os.O_CREAT | \
          getattr(os, 'O_SHORT_LIVED', 0) | getattr(os, 'O_TEMPORARY', 0)
  fh = None
  try:
    fh = os.open(get_watchdog_file(name = name), flags, mode = mode)
    now = time.time()
    os.write(fh, json.dumps(now).encode())
  finally:
    if fh is not None:
      os.close(fh)
  return now

def get_last_watchdog_tick(name = None):
  try:
    with open(get_watchdog_file(name = name), 'r') as f:
      return json.load(f)
  except (FileNotFoundError, ValueError):
    return 0

def clear_watchdog_tick(name = None):
  os.remove(get_watchdog_file(name = name))

def random_bytes(size):
  buf = b''
  while len(buf) < size:
    buf += getrandom(1, getattr(os, 'GRND_RANDOM', 0)) \
           if (getrandom := getattr(os, 'getrandom', None)) else \
           os.urandom(1)
  return buf

def aes_encrypt(payload, key):
  bsize = cryptography.hazmat.primitives.ciphers.algorithms.AES.block_size
  padder = cryptography.hazmat.primitives.padding.PKCS7(bsize).padder()
  payload = padder.update(payload) + padder.finalize()
  iv = random_bytes(bsize//8)
  encryptor = cryptography.hazmat.primitives.ciphers.Cipher(
      cryptography.hazmat.primitives.ciphers.algorithms.AES(key[:32]),
      cryptography.hazmat.primitives.ciphers.modes.CBC(iv),
  ).encryptor()
  enc = iv + encryptor.update(payload) + encryptor.finalize()
  hmac = cryptography.hazmat.primitives.hmac.HMAC(
    key[32:],
    cryptography.hazmat.primitives.hashes.SHA256()
  )
  hmac.update(enc)
  return enc + hmac.finalize()

def aes_decrypt(payload, key):
  bsize = cryptography.hazmat.primitives.ciphers.algorithms.AES.block_size
  unpadder = cryptography.hazmat.primitives.padding.PKCS7(bsize).unpadder()
  iv = payload[:bsize//8]
  hmac_len = cryptography.hazmat.primitives.hashes.SHA256.digest_size
  hmac = payload[-hmac_len:]
  chmac = cryptography.hazmat.primitives.hmac.HMAC(
    key[32:],
    cryptography.hazmat.primitives.hashes.SHA256()
  )
  chmac.update(payload[:-hmac_len])
  chmac.verify(hmac)
  pl = payload[len(iv):-hmac_len]
  decryptor = cryptography.hazmat.primitives.ciphers.Cipher(
      cryptography.hazmat.primitives.ciphers.algorithms.AES(key[:32]),
      cryptography.hazmat.primitives.ciphers.modes.CBC(iv),
  ).decryptor()
  pl = decryptor.update(pl) + decryptor.finalize()
  pl = unpadder.update(pl) + unpadder.finalize()
  return pl

def encrypt(payload, key):
  pload = json.dumps(payload).encode()
  epayload = {
    'sha3_512': hashlib.sha3_512(pload).hexdigest(),
    'payload': base64.b85encode(pload).decode(),
  }
  epayload = json.dumps(epayload).encode()
  return aes_encrypt(epayload, key)

def request(url, verify = True, data = None):
  if verify:
    cafile = None if verify is True else verify
    ctx = ssl.create_default_context(cafile = cafile)
  else:
    ctx = None
  req = urllib.request.Request(url)
  if data is not None:
    data = json.dumps(data).encode()
    req.add_header('Content-Length', len(data))
  return urllib.request.urlopen(req, context = ctx, data = data)

def send(mcbus_url, recipient, key, payload, verify = True):
  if type(key) is str:
    key = base64.b85decode(key)
  pl = {
    'recipient': recipient,
    'payload': base64.b85encode(encrypt(payload, key)).decode(),
  }
  request(mcbus_url, data = pl, verify = verify)

def decrypt(payload, key):
  if type(payload) is str:
    payload = base64.b85decode(payload)
  if type(key) is str:
    key = base64.b85decode(key)
  dpayload = aes_decrypt(payload, key)
  dpayload = json.loads(dpayload)
  pload = base64.b85decode(dpayload['payload'])
  if hashlib.sha3_512(pload).hexdigest() != dpayload['sha3_512']:
    raise ValueError()
  return json.loads(pload)

def receive(mcbus_url, name, verify = True):
  url = mcbus_url
  if not url.endswith('/'):
    url += '/'
  resp = request(url + '?name=' + urllib.parse.quote(name),
                 verify = verify)
  inbox = []
  for message in json.loads(resp.read()):
    pl = message.get('payload')
    if not pl:
      continue
    inbox.append(pl)
  return inbox

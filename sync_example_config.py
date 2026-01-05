#!/usr/bin/env python3

import sys, os, subprocess, tomllib
sys.dont_write_bytecode = True
import missioncontrollitelib

def main():
  server_cfg_path = missioncontrollitelib.get_config_path()
  user = os.environ['SUDO_USER']
  py = 'import sys; sys.dont_write_bytecode = True;' + \
       'import missioncontrollitelib as mc;' + \
       'mc.DEFAULT_CONFIG_ENV_VAR_NAME = "MCLITE_CLIENT_CONFIG";' + \
       'print(mc.get_config_path());'
  out = subprocess.check_output(('sudo', '-u', user, sys.executable, '-c', py))
  client_cfg_path = out.decode().strip()
  with open(server_cfg_path, 'r') as f:
    server_cfg_txt = f.read()
  server_cfg = tomllib.loads(server_cfg_txt)
  with open(client_cfg_path, 'r') as f:
    client_cfg_txt = f.read()
  client_cfg = tomllib.loads(client_cfg_txt)
  with open(os.path.join(os.path.dirname(__file__),
                         'config.example.toml'), 'r') as f:
    example_cfg_txt = f.read()
  example_cfg = tomllib.loads(example_cfg_txt)
  new_cfg_txt = example_cfg_txt
  new_cfg_txt = new_cfg_txt.replace(
    f"this_device = '{example_cfg['this_device']}'",
    f"this_device = '{server_cfg['this_device']}'"
  )
  new_cfg_txt = new_cfg_txt.replace(example_cfg['mcbus_url'],
                                    server_cfg['mcbus_url'])
  for device_name, device in server_cfg['devices'].items():
    for k, v in device.items():
      if k == 'commands':
        continue
      path = f'devices.{device_name}.{k}'
      if type(v) is not str:
        raise Exception(f'Unexpected type for {path}: {repr(v)}')
      example_v = example_cfg['devices'][device_name][k]
      if example_v == v:
        raise Exception(f'Non-unique: {path}')
      new_cfg_txt = new_cfg_txt.replace(example_v, v)
  with open(client_cfg_path, 'w') as f:
    f.write(new_cfg_txt)
  with open(server_cfg_path, 'w') as f:
    f.write(new_cfg_txt)

if __name__ == '__main__':
  main()

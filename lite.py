#!/usr/bin/env python3

def main():
  import sys, os, time, ssl, urllib.request
  while True:
    time.sleep(float(sys.argv[1]))
    try:
      if len(urllib.request.urlopen(urllib.request.Request(sys.argv[4]),
                                    context = ssl.create_default_context(
                                      cafile = sys.argv[3]
                                    ),
                                    timeout = float(sys.argv[2]))
                                      .read()
                                      .replace(b' ', b'')
                                      .replace(b'\t', b'')
                                      .replace(b'\r', b'')
                                      .replace(b'\n', b'')) > 2:
        os.system(sys.argv[5])
    except:
      os.system(sys.argv[6])

if __name__ == '__main__':
  main()

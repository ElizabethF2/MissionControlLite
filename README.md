# Mission Control Lite

Mission Control Lite is a streamlined, lightweight version of [Mission Control](https://github.com/ElizabethF2/MissionControl) designed for secure and efficient remote command execution. Built with ultra-low resource usage in mind (under 800 KB when idle), it offers a cross-platform, highly modular architecture that makes customization simple. By leveraging the Mission Control bus as a relay, it works seamlessly behind firewalls and without port forwarding, even if the server changes networks. Mission Control Lite can automatically detect and attempt to fix network outages (e.g. by resetting network adapters or rebooting devices), while also keeping these recovery actions fully customizable. Security is a core focus: by default, commands are restricted to a user-defined list, traffic is encrypted end-to-end with SSL and AES, and the system can run with limited permissions or inside a container or sandbox for added protection.

## Overview

In order to maximize customizability, Mission Control Lite (MClite) is split into several modules. This repo provides a complete and working set of modules but the expectation is that many users will add, modify, extend or replace modules based on their needs. See the Addition Notes section for more information on how to make and modify modules and on how to select which of the included modules to use. The core modules are as follows:

 - **Bus**: a small, RESTful server which enables clients to send and receive JSON objects in real time to and from named inboxes. The Bus can be found in the [main Mission Control repo](https://github.com/ElizabethF2/MissionControl). The Bus is can be self-hosted or deployed to a number of free hosts. The Bus is used by the Client to communicate with the Waker and Server (more details below). A simplified version of the Bus, `waker.js`, is included in this repo which is designed to be deployed as an [Apps Script Web App](https://developers.google.com/apps-script/guides/web). It can be used as an alternative to the regular bus for Client to Waker communication. This can be useful to reduce the number of requests and amount of uptime needed by the main Bus when using hosts which limit the number of hours of uptime.
 - **Waker**: A small daemon which listens to its own inbox on the Bus for wake requests sent by Clients. The Waker is the only process which runs when the Server is idle and it's responsible for starting the main Server process when wake requests are received and for starting the Repair script whenever errors occur. Three versions of the Waker are included in this repo: `lite.c` which uses libcurl and supports all platforms that libcurl does, `winlite.c` which supports WinHTTP on Windows and `lite.py` which uses the standard Python library and should run wherever Python does. The Waker is the only module in MClite which is always running.
- **Server**: The main Server is implemented in `server.py`. The Server listens for requests from the Client via the Bus using its own inbox. After a timeout has elapsed without any requests from the client, the Server will shutdown to release resources it was using. The Server included in this repo is limited to running commands defined in a user-provided toml file.
- **Repair**: The Repair script is run whenever the Waker encounters any errors. It's job is to automatically recover from any issues which prevent communication with the Client when remotely, manually resolving these issues would not be possible. This could include anything from DNS outages, network interruptions, resource exhaustion, etc. The default Repair script included in this repo counts the number of failures and consecutive failures and, when the consecutive failures exceed user-defined thresholds, it will attempt to reset the network stack and, if that fails enough times, it will reboot the device.
- **Client**: The Client is a CLI application used to communicate with the Waker and Server in order to control a device.
- **missioncontrollitelib**: missioncontrollitelib is a Python library used by the Server, Client and Repair script. It contains common functions needed when creating MClite modules such as communicating with the Bus, encryption and decryption, crash handling, web requests, token generation, text formatting and more. missioncontrollitelib is designed to avoid duplicating code across MClite modules and to make it easier to make your own MClite modules. Use `python -m pydoc missioncontrollitelib` to view its documentation.
- **Helper**: The Helper is a small command line utility which bundles multiple common tasks into a single script. It is designed to be called from the Server. It exists as a separate script from the Server in order to improve modularity/customizability, improve parallelization by moving each task to its own process and to improve reliability by containing errors and crashes to the process for the affected task rather than the Server's process. Use `python helper help` for detailed usage information.

## Installation

**Note:** The installation instructions primarily cover setting up MClite using libcurl and systemd on Linux using the default/example modules included in this repo but the process should be similar for other platforms. See the Additional Notes section for information on how to create, modify and select modules. It is possible to run MClite with fewer dependencies than those mention in these installation steps depending on how you customize MClite's modules.

If you haven't already, install Python, python-cryptography, libcurl, clang and binutils on your Server device(s) and Python and python-cryptography on your Client device(s).

Run the commands below to compile the Waker on the Server device:

```
clang -Oz -g0 -flto=full -DDEBUG=0 -DUSE_SMALL_CURL_BUFFER=1 lite.c -lcurl -o missioncontrollited
strip -s --remove-section=.comment missioncontrollited
```

If desired, you may now uninstall clang and binutils as they will not be needed unless you need to rebuild the Waker.

Setup the Bus as described in the [main Mission Control repo](https://github.com/ElizabethF2/MissionControl). After doing so, you should have a private key for the Bus, `key.pem`, and a public certificate, `cert.pem`.

You can run MClite as root, your regular user account or its own dedicated account. Using a dedicated account with limited permissions has the best security. Decide which method you want to use. Note that MClite can still run non-root commands commands from an account with limited permissions by using a setuid utility like sudo to configure exceptions for certatin commands. See the Additional Notes section for details. On the Server device, you can create a dedicated user for MClite using `useradd -m missioncontrollited`.

On the Server device, install the Waker daemon using the commands below. If only one user needs to be able to run the daemon or if you do not have root permissions, you can install the daemon to a user-specific path by replacing `/bin/missioncontrollited` with that path e.g. `~/.local/bin/missioncontrollited` and by replacing `root` with the desired username.
```
cp missioncontrollited /bin/missioncontrollited
chmod 0755 /bin/missioncontrollited
chown root: /bin/missioncontrollited
```

On the server device, create a folder to contain the scripts for the Server, Repair script and Helper, copy the scripts and make them executable. This can be any location such as `/srv/mclite` or `~/.local/share/mclite`. Substitute your desired location for `/srv/mclite` in the commands below. As before, substitute your desired username for `root`. If you wish to hide the contents of the scripts from other users, substitute `0750` for `0755`.
```
mkdir -p /srv/mclite
cp server.py /srv/mclite/server
cp repair.py /srv/mclite/repair
cp helper.py /srv/mclite/helper
chmod -R 0755 /srv/mclite
chown -R root: /srv/mclite
```

On the Server device, create a folder to contain the config files for MClite. By default, missioncontrollitelib will search for config files in folders called `mclite`, `missioncontrollite` or `mission-control-lite` in `/etc`, `/srv`, `/opt` and [XDG_CONFIG_HOME](https://specifications.freedesktop.org/basedir/latest). It will also look for config files in the same directory missioncontrollitelib was installed and in the current working directory. You can also place your config files anywhere and use environment variables to tell MClite where to look. Within the folder you created, copy the example config and the Bus' public certificate, `cert.pem`, to the config folder. As before, substitute your desired folder for `/etc/mclite`, your desired username for `root` and substitute `0640` for `0644` if you want to keep your config files unreadable by other users.
```
mkdir -p /etc/mclite
cp config.example.toml /etc/mclite/config.toml
cp cert.pem /etc/mclite/cert.pem
chmod -R 0644 /etc/mclite
chown -R root: /etc/mclite
```

Pick a name which will be used to identify your Server device. If you are setting up MClite on multiple Server devices, each will need a unique name. Run the commands below substituting the path you installed the helper to for `/srv/mclite/helper` and your desired device name for `My_Laptop_92`. Device names can contain letters, numbers, underscores and hyphens.
```
cd /srv/mclite
python ./helper generate_config --name My_Laptop_92
```

Open the config file, `config.toml`, in your editor of choice. Copy the `[devices]` entry generated by the previous command and paste it into file, replacing/removing the examples devices entries. Replace `mcbus_url` with the actual URL of your Bus. Replace `this_device` with the name of the current device. The config file can contain multiple devices such that all of your Server devices and all of your Clients will use the same config file with the only difference between the config on each Server device being what `this_device` is set to. The Client ignores this setting. Replace the example commands with the commands you actually want to run. For the best security, limit commands to minimum of what you need and avoid allowing commands to accept arguments or stdin which would enable an attacker to run arbitrary commands if they were to gain access. Change any other settings in the config file then save and quit once you are done.

On the Server deivce, install the service for the Waker. The service can be installed as a system service or a user service. System services will run whenever the device is booted but require root permissions to install while user services can be installed without root permissions but will only run when the user they're installed for is logged in.

To install as a system service run `cp MissionControlLite.service /etc/systemd/system/MissionControlLite.service`. To install as a user service, run `cp MissionControlLite.service ~/.config/systemd/user/MissionControlLite.service`. For either, run `chmod 0640` to prevent unauthorized access to the service file. Open the file in your editor of choice. Settings for the Waker daemon are passed as command line args and these settings are stored in the service file. The service file is preconfigured with default settings which should be replaced with your desired settings:

 - Replace the `20` on the `ExecStart` line with the desired time in whole seconds between requests to the Bus. Smaller values make the Waker wake up sooner but larger values make it use less resources. In most cases, this should be left at its default value.
 - Replace the `180` on the `ExecStart` line with the desired timeout time in whole seconds for the Waker to timeout. This controls how long the Waker will wait for a response from the Bus before it determines it can't communicate with the Bus and it triggers the Repair script. This can be any value but must be higher than the Bus' own timeout time; otherwise the Waker will always timeout and trigger the Repair script whenever it is idle. In most cases, this should be left at its default value.
 - Replace `/etc/mclite/cert.pem` with the full path to the public certificate for the Bus.
 - Replace `https://example.org:1234/?name=GAMELAPTOP-Linux-Waker-TqKgT1hkUMdC` with the URL for the Waker's inbox i.e. replace `https://example.org:1234` with the Bus' URL and replace `GAMELAPTOP-Linux-Waker-TqKgT1hkUMdC` with the `waker_name` from the config file.
 - Replace `/etc/mclite/server` with the path to the Server script.
 - Replace `/etc/mclite/repair` with the path to the Repair script.
 - Replace `/bin/missioncontrollited` with the path to the Waker daemon if it is different.

If you're deploying the service file as a system service but you've configured running the Waker, Server and other components to run as a non-root user, uncomment the `User=` and `Group=` lines and replace `missioncontrollited` with the user and group you want to run everything as. The settings for `StartLimitIntervalSec`, `StartLimitBurst`, `Restart` and `RestartSec` can be left at their default values, however, feel free to change them or add any other settings if desired. Save and close the service file when done editing.

On the client device, copy the config directory and its contents from the Server device then install the Client script using one of the sets of commands below:
```
# For all users
cp client.py /usr/bin/missioncontrollite-client
chmod 0755 /usr/bin/missioncontrollite-client
chown root: /usr/bin/missioncontrollite-client

# For only the current user
cp client.py ~/.local/bin/missioncontrollite-client
chmod 0750 ~/.local/bin/missioncontrollite-client
```

On both the Server and Client devices, install missioncontrollitelib. You can install it in any directory in your [PYTHONPATH](https://docs.python.org/3/using/cmdline.html#envvar-PYTHONPATH). In most cases, you'll want to install it to your site packages path which will make it available for all users. If you don't have permission to modify the site packages path or don't want the library available globally, it can also be installed to the same directory as the Server and Repair scripts on the Server device and the same directory as the Client script on the Client device. You can view the site package paths using `python -c 'import site;print(site.getsitepackages())'`. Copy the library using `cp missioncontrollitelib.py /usr/lib/python3.13/site-packages/missioncontrollitelib.py`, substituting your desired install path for `/usr/lib/python3.13/site-packages`. Use `chmod 0755 /usr/lib/python3.13/site-packages/missioncontrollitelib.py` for paths available to all users or `chmod 0750 /usr/lib/python3.13/site-packages/missioncontrollitelib.py` for paths available to only the current user. Use `chmod root: /usr/lib/python3.13/site-packages/missioncontrollitelib.py` to change the ownership, substituting the desired user for `root`.

Finally, on the Server device, enable and start the service using `systemctl enable --now MissionControlLite.service` if installed as a system service or `systemctl enable --user --now MissionControlLite.service` if installed as a user service. Use `systemctl status MissionControlLite.service` or `systemctl status --user MissionControlLite.service` respectively to check the service's status. You should now be able to control your device remotely using the command `missioncontrollite-client` and following the on-screen prompts on your Client device.

## Additional Notes

### Setuid Utilities

When running MClite as a non-root user, you can still run commands which require root permissions by using a setuid utility like sudo. For example, if you're running MClite as a user called `missioncontrollited`, you can create a drop-in file called `/etc/sudoers.d/mclite` with the below contents:
```
missioncontrollited ALL=(root) NOPASSWD: /usr/bin/systemctl restart --signal=SIGINT MissionControlLite
```
Then, you can add the command to your config file and use it from MClite despite the service not being run with root permissions:
```
[devices.YOUR-DEVICE-NAME-HERE.commands]
restart_mclite = 'sudo systemctl restart --signal=SIGINT MissionControlLite'
```
See the [sudoers manual](https://www.sudo.ws/docs/man/sudoers.man) for more information.

### Wakers

Note that `lite.py` is mainly included as a reference implementation you can use as a guide if you are making your own Waker and it is not recommended to use it except as a last resort if you are unable to get another Waker running. `lite.c` and `winlite.c` will always use significantly less resources and their memory footprint can be further drastically reduced if other applications or services running on your device are already using libcurl or WinHTTP. You can use a utility such as `lsof` or `listdlls` to check which libraries are in use. If your device is not already using libcurl or WinHTTP but is already using a different library for web requests, consider creating a custom waker using `lite.c` or `winlite.c` as templates and/or open an issue in this repo to get a waker for the library in question added.

### Customization

When adding new functionality to the server, when possible, consider creating your own Helper script or extend the existing Helper script rather than adding the functions directly to the Server script. Keeping this functionality in a separate process helps to contain crashes and other errors and it can aid in diagnosing and debugging errors by ensuring the Client is able to view error messages and stack traces.

When customizing the Server and/or Repair script, note that the Wakers included in this repo ignore the return code and output of the scripts. If you want the return code to be handled or logged, you will need to create a wrapper script which does the handling and add it between the Waker and Server and Repair script.

By design, the Waker will wait for the Server and Repair scripts to complete, blocking execution until they do. Under normal operation, this can be useful. For example, if the Repair script is resolving an issue, the Waker won't try to make any new connections to the Bus until the Repair script is done with its repairs. The issue with this is that any scripts that hang without crashing or exiting will cause all of MClite to hang and become unresponsive. A couple of strategies are used to avoid this. The Server immediately daemonizes itself and returns control to the Waker. The daemon uses the watchdog functions in missioncontrollitelib to create and check a "watchdog file". As the Server runs, it "ticks" the watchdog file, updating its timestamp at regular intervals and the file is deleted when the Server shuts down. New Server daemons will only continue to run if there is not already a watchdog file or if the timestamp on the file indicates that the existing Server has hung. This ensures that the Client and Waker are able to start new, responsive Server instances even if one hangs or crashes. The Repair scripts avoids hangs but explicitly avoiding loops which could cause a hang and by running all of its subprocesses with a timeout which ensures that the Repair script will eventually exit. Consider using both of these as references and consider using missioncontrollitelib's watchdogs functions if you are designing your own scripts to be used with the Waker.

The Wakers and missioncontrollitelib are designed around the Mission Control Bus and its RESTful API, however, this implementation detail is abstracted from the other components. If desired, the Waker and missioncontrollitelib can be customized to exchange messages between the Client device(s) and Server device(s) using a different method such as email, SMS, a messaging app, a cloud storage provider, etc. These could be used as a fallback in cases where the Bus is down or inaccessible. For the relevant implementations, see `write_callback()` in `lite.c` and `receive()` and `send()` in missioncontrollitelib.

The default, included Repair script is somewhat limited as it only attempts to reset the OS' network stack and to reboot the device. The Repair script can be extended with more advanced functionality, for example:
 - Cycling through different networks until a working network is found
 - Using a web automation framework like Selenium or a remote access utility like SSH or a UPS utility to restart a router and/or modem
 - Using a web automation framework like Selenium to detect and navigate through a network's captive portal
 - Starting an alternative Server or launching the Server with an alternative config which uses a different Bus or different method to communicate with the client as a fallback for when the Bus is offline
 - Attempting to send a message notifying the user that an outage has occurred

### Windows

The Server and Repair scripts cannot be directly executed on Windows. When setting up MClite on Windows, copy `server.bat` and `repair.bat` to the same directory as the Server and Repair script and have your Waker daemon call the .bat files instead of calling the scripts directly.


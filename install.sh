#!/bin/sh

# Defaults
[ -z "$ONLY_BUILD" ] && ONLY_BUILD="no"
[ -z "$BUILD_IN_CONTAINER" ] && BUILD_IN_CONTAINER="yes"
[ -z "$REMOVE_CONTAINER" ] && REMOVE_CONTAINER="yes"
[ -z "$CONTAINER_NAME" ] && CONTAINER_NAME="missioncontrollite_build_container"
[ -z "$CONTAINER_IMAGE" ] && CONTAINER_IMAGE="archlinux"
[ -z "$REBUILD" ] && REBUILD="yes"

[ -z "$DAEMON_INSTALL_PATH" ] && DAEMON_INSTALL_PATH="/usr/bin/missioncontrollited"

[ -z "$SERVER_INSTALL_PATH" ] && $SERVER_INSTALL_PATH="/srv/mclite/server"
[ -z "$DO_INSTALL_SERVER" ] && DO_INSTALL_SERVER="yes"

[ -z "$CLIENT_INSTALL_PATH" ] && $CLIENT_INSTALL_PATH="/usr/bin/missioncontrollite-client"
[ -z "$DO_INSTALL_CLIENT" ] && DO_INSTALL_CLIENT="no"

[ -z "$REPAIR_INSTALL_PATH" ] && $REPAIR_INSTALL_PATH="/srv/mclite/repair"
[ -z "$DO_INSTALL_REPAIR" ] && DO_INSTALL_REPAIR="yes"

[ -z "$HELPER_INSTALL_PATH" ] && $HELPER_INSTALL_PATH="/srv/mclite/helper"
[ -z "$DO_INSTALL_HELPER" ] && DO_INSTALL_HELPER="yes"

[ -z "$LIBRARY_INSTALL_PATH" ] && $LIBRARY_INSTALL_PATH="/srv/mclite/missioncontrollitelib.py"
# _PYSITEPKGDIR="$(python3 -c "print(__import__('site').getsitepackages()[0])")"
# [ -z "$LIBRARY_INSTALL_PATH" ] && \
#  $LIBRARY_INSTALL_PATH="$_PYSITEPKGDIR/missioncontrollitelib.py"
[ -z "$DO_INSTALL_LIBRARY" ] && DO_INSTALL_LIBRARY="yes"

[ -z "$SERVICE_NAME" ] && SERVICE_NAME="missioncontrollited"
[ -z "$SERVICE_TYPE" ] && \
  [ "$(who -m | cut -f1 -d' ')" = "root" ] && \
  SERVICE_TYPE=root
[ -z "$SERVICE_TYPE" ] && SERVICE_TYPE=user
[ -z "$DO_INSTALL_SERVICE" ] && DO_INSTALL_SERVICE="yes"

[ -z "$DAEMON_POLL_DELAY_SEC" ] && DAEMON_POLL_DELAY_SEC="25"
[ -z "$DAEMON_TIMEOUT_SEC" ] && DAEMON_TIMEOUT_SEC="60"
[ -z "$CERTIFICATE_PATH" ] && CERTIFICATE_PATH="/etc/mclite/cert.pem"
[ -z "$INBOX_URL" ] && INBOX_URL="https://example.com:1234/?name=EXAMPLE-WAKER-123"



[ -z "$CONTAINER_ENGINE" ] && CONTAINER_ENGINE="$(type -p podman)" 
[ -z "$CONTAINER_ENGINE" ] && CONTAINER_ENGINE="$(type -p docker)" 

echo Looking for a past install of the daemon at $DAEMON_INSTALL_PATH
should_build="no"
[ ! -e "$DAEMON_INSTALL_PATH" ] && should_build="yes"
[ "$REBUILD" = "yes" ] && should_build="yes"
if [ "$should_build" = "yes" ]; then
  BUILDCMD="clang -Oz -g0 -flto=full -lcurl lite.c -o /tmp/missioncontrollited;"
  BUILDCMD="$BUILDCMD strip -s --remove-section=.comment /tmp/missioncontrollited"

  if [ "$BUILD_IN_CONTAINER" = "yes" ]; then
    [ -z "$CONTAINER_ENGINE" ] && echo "No container engine found" && exit 1

    # Ensure container exists
    $CONTAINER_ENGINE ps -a --format "Container Already Created: {{.Status}}" -f "name=$CONTAINER_NAME" | grep .
    if [ "$?" != "0" ]; then 
      $CONTAINER_ENGINE container create -it -v "$(pwd):/ws:ro" \
        --name $CONTAINER_NAME $CONTAINER_IMAGE /bin/sh
      echo "Created a container named $CONTAINER_NAME via $CONTAINER_ENGINE"
    fi

    # Start the container
    $CONTAINER_ENGINE start $CONTAINER_NAME

    echo "Building the daemon in the container"
    $CONTAINER_ENGINE exec -it $CONTAINER_NAME /bin/sh -c \
      "echo pacman -Syu --needed --noconfirm clang lld; \
       cd /ws;\
       $BUILDCMD"

    echo "Copying the daemon to $DAEMON_INSTALL_PATH"
    $CONTAINER_ENGINE cp "$CONTAINER_NAME:/tmp/missioncontrollited" "$DAEMON_INSTALL_PATH"
    chmod +x "$DAEMON_INSTALL_PATH"

    if [ "$REMOVE_CONTAINER" = "yes" ]; then
      echo "Removing container: $CONTAINER_NAME"
      $CONTAINER_ENGINE rm -f $CONTAINER_NAME
    fi
  else
    echo "Buidling the daemon"
    ${SHELL:-sh} -c "$BUILDCMD"
  fi
else
  echo "Found the daemon, skipping compilation"
fi

if [ "$ONLY_BUILD" = "yes" ]; then
  echo "ONLY_BUILD flag was set, skipping remaining steps"
  exit 0
fi

if [ "$DO_INSTALL_SERVER" = "yes" ]; then
  mkdir -p "$(dirname $SERVER_INSTALL_PATH)"
  cp "$(dirname "$0")/server.py" "$SERVER_INSTALL_PATH"
  chmod +x "$SERVER_INSTALL_PATH"
fi

if [ "$DO_INSTALL_LIBRARY" = "yes" ]; then
  mkdir -p "$(dirname $LIBRARY_INSTALL_PATH)"
  cp "$(dirname "$0")/missioncontrollitelib.py" "$LIBRARY_INSTALL_PATH"
fi

if [ "$DO_INSTALL_REPAIR" = "yes" ]; then
  mkdir -p "$(dirname $REPAIR_INSTALL_PATH)"
  cp "$(dirname "$0")/repair.py" "$REPAIR_INSTALL_PATH"
  chmod +x "$REPAIR_INSTALL_PATH"
fi

if [ "$DO_INSTALL_HELPER" = "yes" ]; then
  mkdir -p "$(dirname $HELPER_INSTALL_PATH)"
  cp "$(dirname "$0")/helper.py" "$HELPER_INSTALL_PATH"
  chmod +x "$HELPER_INSTALL_PATH"
fi

if [ "$DO_INSTALL_CLIENT" = "yes" ]; then
  mkdir -p "$(dirname $CLIENT_INSTALL_PATH)"
  cp "$(dirname "$0")/client.py" "$CLIENT_INSTALL_PATH"
  chmod +x "$CLIENT_INSTALL_PATH"
fi

if [ "$SERVICE_TYPE" = "root" ]; then
  SERVICE_ROOT="/etc/systemd/system"
else
  SERVICE_ROOT="$HOME/.config/systemd/user"
fi

SERVICE_PATH="$SERVICE_ROOT/$SERVICE_NAME.service"
echo Attempting to install the service as a $SERVICE_TYPE service at $SERVICE_PATH
if [ ! -e "$SERVICE_ROOT" ]; then
  echo systemd unit path missing
  echo systemd must be installed and running for this script to setup the service
  exit 1
fi

cat <<EOF > "$SERVICE_PATH"
[Unit]
Description=Mission Control Lite Daemon
After=multi-user.target
Wants=multi-user.target 
StartLimitIntervalSec=$DAEMON_POLL_DELAY_SEC
StartLimitBurst=5

[Service]
Type=simple
ExecStart=$DAEMON_INSTALL_PATH $DAEMON_POLL_DELAY_SEC $DAEMON_TIMEOUT_SEC "$CERTIFICATE_PATH" "$INBOX_URL" "$SERVER_INSTALL_PATH" "$REPAIR_INSTALL_PATH"
Restart=always
RestartSec=$DAEMON_TIMEOUT_SEC

[Install]
WantedBy=default.target
EOF

if [ "$SERVICE_TYPE" = "root" ]; then
  systemctl restart "$SERVICE_NAME"
  systemctl enable "$SERVICE_NAME"
else
  systemctl --user restart "$SERVICE_NAME"
  systemctl --user enable "$SERVICE_NAME"
fi

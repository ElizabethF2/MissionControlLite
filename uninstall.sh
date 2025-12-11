#!/bin/sh

# Defaults
[ -z "$CONTAINER_NAME" ] && CONTAINER_NAME="missioncontrollite_build_container"
[ -z "$REMOVE_CONTAINER" ] && REMOVE_CONTAINER="yes"

[ -z "$DAEMON_INSTALL_PATH" ] && DAEMON_INSTALL_PATH="/usr/bin/missioncontrollited"
[ -z "$DO_REMOVE_DAEMON" ] && DO_REMOVE_DAEMON="yes"

[ -z "$SERVER_INSTALL_PATH" ] && $SERVER_INSTALL_PATH="/srv/mclite/server"
[ -z "$DO_REMOVE_SERVER" ] && DO_REMOVE_SERVER="yes"
[ -z "$DO_REMOVE_SERVER_DIR" ] && DO_REMOVE_SERVER_DIR="yes"

[ -z "$CLIENT_INSTALL_PATH" ] && $CLIENT_INSTALL_PATH="/usr/bin/missioncontrollite-client"
[ -z "$DO_REMOVE_CLIENT" ] && DO_REMOVE_CLIENT="no"
[ -z "$DO_REMOVE_CLIENT_DIR" ] && DO_REMOVE_CLIENT_DIR="no"

[ -z "$REPAIR_INSTALL_PATH" ] && $REPAIR_INSTALL_PATH="/srv/mclite/repair"
[ -z "$DO_REMOVE_REPAIR" ] && DO_REMOVE_REPAIR="yes"
[ -z "$DO_REMOVE_REPAIR_DIR" ] && DO_REMOVE_REPAIR_DIR="yes"

[ -z "$HELPER_INSTALL_PATH" ] && $HELPER_INSTALL_PATH="/usr/bin/missioncontrollite-helper"
[ -z "$DO_REMOVE_HELPER" ] && DO_REMOVE_HELPER="yes"
[ -z "$DO_REMOVE_HELPER_DIR" ] && DO_REMOVE_HELPER_DIR="yes"

[ -z "$LIBRARY_INSTALL_PATH" ] && $LIBRARY_INSTALL_PATH="/srv/mclite/"
# _PYSITEPKGDIR="$(python3 -c "print(__import__('site').getsitepackages()[0])")"
# [ -z "$LIBRARY_INSTALL_PATH" ] && \
#  $LIBRARY_INSTALL_PATH="$_PYSITEPKGDIR/missioncontrollitelib.py"
[ -z "$DO_REMOVE_LIBRARY" ] && DO_REMOVE_LIBRARY="yes"
[ -z "$DO_REMOVE_LIBRARY_DIR" ] && DO_REMOVE_LIBRARY_DIR="yes"

[ -z "$SERVICE_NAME" ] && SERVICE_NAME="missioncontrollited"
[ -z "$SERVICE_TYPE" ] && \
  [ "$(who -m | cut -f1 -d' ')" = "root" ] && \
  SERVICE_TYPE=root
[ -z "$SERVICE_TYPE" ] && SERVICE_TYPE=user
[ -z "$DO_REMOVE_SERVICE" ] && DO_REMOVE_SERVICE="yes"
[ -z "$DO_REMOVE_SERVICE_DIR" ] && DO_REMOVE_SERVICE_DIR="yes"

[ -z "$CONFIG_PATH" ] && CONFIG_PATH="/etc/mclite/config.toml"
[ -z "$DO_REMOVE_CONFIG" ] && DO_REMOVE_CONFIG="no"
[ -z "$DO_REMOVE_CONFIG_DIR" ] && DO_REMOVE_CONFIG_DIR="no"

[ -z "$CERTIFICATE_PATH" ] && CERTIFICATE_PATH="/etc/mclite/cert.pem"
[ -z "$DO_REMOVE_CERTIFICATE" ] && DO_REMOVE_CERTIFICATE="no"
[ -z "$DO_REMOVE_CERTIFICATE_DIR" ] && DO_REMOVE_CERTIFICATE_DIR="no"

[ -z "$CONTAINER_ENGINE" ] && CONTAINER_ENGINE="$(type -p podman)" 
[ -z "$CONTAINER_ENGINE" ] && CONTAINER_ENGINE="$(type -p docker)" 

echo "Uninstalling Mission Control Lite"
[ "$DO_REMOVE_DAEMON" = "yes" ] && rm "$DAEMON_INSTALL_PATH"
[ "$DO_REMOVE_DAEMON_DIR" = "yes" ] && rmdir "$(dirname "$DAEMON_INSTALL_PATH")"

[ "$DO_REMOVE_SERVER" = "yes" ] && rm "$SERVER_INSTALL_PATH"
[ "$DO_REMOVE_SERVER_DIR" = "yes" ] && rmdir "$(dirname "$SERVER_INSTALL_PATH")"

[ "$DO_REMOVE_CLIENT" = "yes" ] && rm "$CLIENT_INSTALL_PATH"
[ "$DO_REMOVE_CLIENT_DIR" = "yes" ] && rmdir "$(dirname "$CLIENT_INSTALL_PATH")"

[ "$DO_REMOVE_REPAIR" = "yes" ] && rm "$REPAIR_INSTALL_PATH"
[ "$DO_REMOVE_REPAIR_DIR" = "yes" ] && rmdir "$(dirname "$REPAIR_INSTALL_PATH")"

[ "$DO_REMOVE_HELPER" = "yes" ] && rm "$HELPER_INSTALL_PATH"
[ "$DO_REMOVE_HELPER_DIR" = "yes" ] && rmdir "$(dirname "$HELPER_INSTALL_PATH")"

[ "$DO_REMOVE_LIBRARY" = "yes" ] && rm "$LIBRARY_INSTALL_PATH"
[ "$DO_REMOVE_LIBRARY_DIR" = "yes" ] && rmdir "$(dirname "$LIBRARY_INSTALL_PATH")"

[ "$DO_REMOVE_CONFIG" = "yes" ] && rm "$CONFIG_INSTALL_PATH"
[ "$DO_REMOVE_CONFIG_DIR" = "yes" ] && rmdir "$(dirname "$CONFIG_INSTALL_PATH")"

[ "$DO_REMOVE_CERTIFICATE" = "yes" ] && rm "$CERTIFICATE_INSTALL_PATH"
[ "$DO_REMOVE_CERTIFICATE_DIR" = "yes" ] && rmdir "$(dirname "$CERTIFICATE_INSTALL_PATH")"

if [ "$SERVICE_TYPE" = "root" ]; then
  SERVICE_ROOT="/etc/systemd/system"
else
  SERVICE_ROOT="$HOME/.config/systemd/user"
fi

if [ "$DO_REMOVE_SERVICE" = "yes" ]; then
  rm "$SERVICE_ROOT/$SERVICE_NAME.service"
fi

if [ "$DO_REMOVE_SERVICE_DIR" = "yes" ] && [ "$SERVICE_TYPE" != "root" ]; then
  rmdir "$SERVICE_ROOT"
fi

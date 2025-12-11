#!/bin/sh

VMNAME=windows

virtuator call $VMNAME put "$(dirname "$0")/install.bat" "/install.bat"
virtuator call $VMNAME put "$(dirname "$0")/winlite.c" "/winlite.c"
echo "
set RUNNING_IN_A_VM=1
/install.bat
" | virtuator call $VMNAME ssh
echo ''

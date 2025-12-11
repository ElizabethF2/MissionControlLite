@echo off

if not defined ONLY_BUILD (
  set ONLY_BUILD=0
)
if not defined DO_BUILD_DAEMON (
  set DO_BUILD_DAEMON=1
)
if not defined CLEANUP_BUILD (
  set CLEANUP_BUILD=0
)
if not defined DEBUG (
  set DEBUG=0
)
if not defined VSROOT (
  set "VSROOT=%ProgramFiles(x86)%\Microsoft Visual Studio"
)
if not defined VSYEAR (
  set VSYEAR=2022
)
if not defined BUILDROOT (
  set "BUILDROOT=%TEMP%\winlite"
)
if not defined INSTALL_PATH (
  set "INSTALL_PATH=%ProgramData%\mclite"
)
if not defined DO_INSTALL_BUILD_TOOLS (
  set DO_INSTALL_BUILD_TOOLS=1
)
if not defined DO_INSTALL_SCRIPTS (
  set DO_INSTALL_SCRIPTS=1
)
if not defined DO_INSTALL_DAEMON (
  set DO_INSTALL_DAEMON=1
)
if not defined DO_CREATE_TASK (
  set DO_CREATE_TASK=1
)
if not defined TASK_USER_ID (
  set "TASK_USER_ID=NT AUTHORITY\SYSTEM"
)
if not defined TASK_LOGON_TYPE (
  set TASK_LOGON_TYPE=ServiceAccount
)
if not defined DAEMON_POLL_DELAY_MS (
  set DAEMON_POLL_DELAY_MS=25000
)
if not defined DAEMON_TIMEOUT_MS (
  set DAEMON_TIMEOUT_MS=60000
)
if not defined DAEMON_CERTIFICATE (
  set DAEMON_CERTIFICATE=cert.cer
)
if not defined DAEMON_BUS_HOST (
  set DAEMON_BUS_HOST=example.com
)
if not defined DAEMON_BUS_PORT (
  set DAEMON_BUS_PORT=443
)
if not defined DAEMON_BUS_PATH (
  set DAEMON_BUS_PATH=/?name=EXAMPLE-INBOX-NAME
)
if not defined DAEMON_SERVER_SCRIPT (
  set DAEMON_SERVER_SCRIPT=server.bat
)
if not defined DAEMON_REPAIR_SCRIPT (
  set DAEMON_REPAIR_SCRIPT=repair.bat
)
if not defined DAEMON_EXE_NAME (
  set DAEMON_EXE_NAME=missioncontrollited
)
if not defined DAEMON_WORKING_DIR (
  set DAEMON_WORKING_DIR=%INSTALL_PATH%
)

if "%DO_INSTALL_BUILD_TOOLS%" EQU "1" (
  if not exist "%VSROOT%" (
    set c1=Microsoft.VisualStudio.Workload.VCTools
    set c2=Microsoft.VisualStudio.Component.VC.Tools.x86.x64
    set c3=Microsoft.VisualStudio.Component.Windows11SDK.26100
    winget install Microsoft.VisualStudio.2022.BuildTools ^
      --force ^
      --override ^
      "--wait --passive --add %c1% --add %c2% --add %c3%"
  )
)

if "%DO_BUILD_DAEMON%" EQU "1" (
  pushd "%VSROOT%\%VSYEAR%"
  call "BuildTools\VC\Auxiliary\Build\vcvars64.bat"
  popd

  mkdir "%BUILDROOT%"
  mkdir "%BUILDROOT%\bin"
  mkdir "%BUILDROOT%\obj"

  if "%RUNNING_IN_A_VM%" EQU "1" (
    cd /d "%BUILDROOT%"
    del "%BUILDROOT%\winlite.c"
    move "%~dp0\winlite.c" "%BUILDROOT%\winlite.c"
    del "%BUILDROOT%\%~n0%~x0"
  )

  cl /O2 /DDEBUG=%DEBUG% winlite.c ^
    /Fo:"%BUILDROOT%\obj\missioncontrollited.obj" ^
    /Fe:"%BUILDROOT%\bin\missioncontrollited.exe"

  pushd "%VSROOT%\%VSYEAR%"
  call "BuildTools\VC\Auxiliary\Build\vcvars32.bat"
  popd

  cl /O2 /DDEBUG=%DEBUG% winlite.c ^
    /Fo:"%BUILDROOT%\obj\missioncontrollited32.obj" ^
    /Fe:"%BUILDROOT%\bin\missioncontrollited32.exe"
)

if "%ONLY_BUILD%" EQU "1" (
  goto DO_EXIT
)

if "%DO_INSTALL_SCRIPTS%" EQU "1" (
  mkdir "%INSTALL_PATH%"
  copy server.py "%INSTALL_PATH%\server.py"
  copy server.bat "%INSTALL_PATH%\server.bat"
  copy repair.py "%INSTALL_PATH%\repair.py"
  copy repair.bat "%INSTALL_PATH%\repair.bat"
  copy missioncontrollitelib.py "%INSTALL_PATH%\missioncontrollitelib.py"
  copy helper.py "%INSTALL_PATH%\helper.py"
)

if "%DO_INSTALL_DAEMON%" EQU "1" (
  mkdir "%INSTALL_PATH%"
  set cpu0=HKLM\Hardware\Description\System\CentralProcessor\0
  reg Query "%cpu0%" | find /i "x86" > NUL
  if "%errorlevel%" equ "0" (
    set fname=missioncontrollited32
  ) else (
    set fname=missioncontrollited
  )
  copy "%BUILDROOT%\bin\%fname%.exe" "%INSTALL_PATH%\%DAEMON_EXE_NAME%.exe"
)

if "%CLEANUP_BUILD%" EQU "1" (
  if "%DO_BUILD_DAEMON%" EQU "1" (
    del /S "%BUILDROOT%"
  )
)

if "%DO_CREATE_TASK%" EQU "1" (
  echo $args = $Env:DAEMON_CERTIFICATE, ^
               $Env:DAEMON_BUS_HOST, ^
               $Env:DAEMON_BUS_PORT, ^
               $Env:DAEMON_BUS_PATH, ^
               $Env:DAEMON_SERVER_SCRIPT, ^
               $Env:DAEMON_REPAIR_SCRIPT; ^
       $args = $args -join ' '; ^
       Register-ScheduledTask ^
        -Action ^( ^
          New-ScheduledTaskAction ^
            -Execute $Env:DAEMON_EXE_NAME ^
            -Argument $args ^
            -WorkingDirectory $Env:DAEMON_WORKING_DIR ^
        ^) ^
        -Trigger ^( ^
          New-ScheduledTaskTrigger -AtStartup ^
        ^) ^
        -Principal ^( ^
          New-ScheduledTaskPrincipal ^
            -UserId $Env:TASK_USER_ID ^
            -LogonType $Env:TASK_LOGON_TYPE ^
            -RunLevel Highest ^
        ^) ^
        -Settings ^( ^
          New-ScheduledTaskSettingsSet ^
            -AllowStartIfOnBatteries ^
            -DontStopIfGoingOnBatteries ^
        ^) ^
        -TaskName 'MissionControlLite' ^
        -Description 'MissionControlLite Daemon' ^
  | powershell
)

:DO_EXIT
if "%DO_BUILD_DAEMON%" EQU "1" (
  if "%RUNNING_IN_A_VM%" EQU "1" (
    move "%0" "%BUILDROOT%\%~n0%~x0" & exit
  )
)

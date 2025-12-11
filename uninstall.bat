@echo off

if not defined CLEANUP_BUILD (
  set CLEANUP_BUILD=0
)
if not defined BUILDROOT (
  set BUILDROOT=%TEMP%\winlite
)
if not defined INSTALL_PATH (
  set INSTALL_PATH=%ProgramData%\mclite
)
if not defined DO_REMOVE_INSTALL_PATH (
  set DO_REMOVE_INSTALL_PATH=1
)
if not defined DO_REMOVE_TASK (
  set DO_REMOVE_TASK=1
)

if "%CLEANUP_BUILD%" EQU "1" (
  del /S "%BUILDROOT%"
)

if "%DO_REMOVE_INSTALL_PATH%" EQU "1" (
  del /s/f "%INSTALL_PATH%"
)

if "%DO_REMOVE_TASK%" EQU "1" (
  schtasks /delete /tn "MissionControlLite"
)

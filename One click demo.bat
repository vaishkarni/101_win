@echo off
setlocal EnableExtensions
title SO-101 One click demo
REM ------------------------------------------------------------------
REM  SO-101 leader/follower teleop - ONE CLICK DEMO (Windows 10/11)
REM  Double-click this file. It will:
REM    1. set the computer up if needed (Python 3 + the pyserial library)
REM    2. check both arms (nothing moves)
REM    3. start teleop: move the LEADER by hand, the FOLLOWER copies it
REM  Nothing here changes the arms' calibration - it lives inside the servos.
REM ------------------------------------------------------------------
set "KIT=%~dp0so101_kit"
set "COMMON=%KIT%\common"
set "PY="

echo ======================================================
echo   SO-101 ONE CLICK DEMO
echo   1 setup (first time only)  2 check arms  3 teleop
echo ======================================================
echo.
if not exist "%COMMON%\so101\__main__.py" (
  echo !! The so101_kit folder is missing next to this file.
  echo    Copy the whole berlin folder, not just this .bat
  pause
  exit /b 1
)

REM ---------------- 1. Python 3 ----------------
py -3 -c "import sys" >nul 2>&1 && set PY=py -3
if defined PY goto havepython
python -c "import sys" >nul 2>&1 && set PY=python
if defined PY goto havepython
call :findpython
if defined PY goto havepython

echo -- Python 3 is not installed on this computer.
choice /C YN /N /M "   Install it automatically now (needs internet)? [Y/N] "
if errorlevel 2 goto manualpython
echo -- installing Python 3.12 with winget, this takes a few minutes ...
winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements --override "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0"
call :findpython
if defined PY goto havepython
py -3 -c "import sys" >nul 2>&1 && set PY=py -3
if defined PY goto havepython

:manualpython
echo.
echo !! Python 3 is still not available.
echo    Install it from https://www.python.org/downloads/  and in the installer
echo    tick "Add python.exe to PATH".  Then double-click this file again.
start "" https://www.python.org/downloads/
pause
exit /b 1

:havepython
echo -- Python found: %PY%

REM ---------------- 2. pyserial library ----------------
%PY% -c "import serial" >nul 2>&1
if not errorlevel 1 goto haveserial
echo -- first run on this computer: installing the pyserial library ...
%PY% -m pip install --quiet --disable-pip-version-check --no-index --find-links "%KIT%\wheels" pyserial >nul 2>&1
%PY% -c "import serial" >nul 2>&1
if not errorlevel 1 goto haveserial
echo    offline copy failed, trying the internet ...
%PY% -m pip install --quiet --disable-pip-version-check pyserial
%PY% -c "import serial" >nul 2>&1
if not errorlevel 1 goto haveserial
echo !! Could not install pyserial. Is the internet connected?
pause
exit /b 1

:haveserial
echo -- setup OK.

REM ---------------- 3. check both arms ----------------
:check
echo.
echo -- checking both arms, nothing moves ...
echo.
cd /d "%COMMON%"
%PY% -m so101 check
if errorlevel 1 goto checkfail
goto teleop

:checkfail
echo.
echo !! The arm check failed. Usual causes:
echo    - an arm is not plugged in by USB, or its power supply is off
echo    - Windows has no driver for the USB adapter yet. Wait a minute after
echo      plugging in; if it still fails install the CH343 driver from
echo      https://www.wch-ic.com/downloads/CH343SER_EXE.html  then unplug/replug
echo    - USB adapters seen right now:
%PY% -m so101 ports
echo.
choice /C RQ /N /M "   Press R to check again, Q to quit: "
if errorlevel 2 exit /b 1
goto check

REM ---------------- 4. teleop ----------------
:teleop
echo.
echo ======================================================
echo   STARTING TELEOP
echo   Keep hands clear of the FOLLOWER: it moves to copy the leader.
echo   Move the LEADER by hand. The follower follows.
echo   STOP: press Ctrl-C in this window, then hold the follower
echo   during the 3 second countdown - after that it goes limp.
echo   If Windows then asks "Terminate batch job (Y/N)?":
echo   N = back to this menu, Y = close the window.
echo ======================================================
echo.
%PY% -m so101 teleop
echo.
echo -- teleop ended.
choice /C SQ /N /M "   Press S to start again (check + teleop), Q to quit: "
if errorlevel 2 exit /b 0
goto check

REM ---------------- helper: look for a python.exe that is not on PATH yet ----------------
:findpython
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%~D\python.exe" set PY="%%~D\python.exe"
if defined PY goto :eof
for /d %%D in ("%ProgramFiles%\Python3*") do if exist "%%~D\python.exe" set PY="%%~D\python.exe"
goto :eof

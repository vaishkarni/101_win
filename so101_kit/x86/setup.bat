@echo off
REM One-time setup for the SO-101 teleop kit on Windows 10/11 (x86-64).
REM Needs Python 3 from https://www.python.org/downloads/  (tick "Add python.exe to PATH" when installing).
echo == SO-101 teleop kit setup (Windows) ==
python --version >nul 2>&1 || ( echo !! Python not found. Install it from python.org and tick "Add python.exe to PATH", then run this again. & pause & exit /b 1 )
python -m pip install --quiet pyserial || ( echo !! could not install pyserial - is the internet connected? & pause & exit /b 1 )
echo.
echo Setup done. Plug in both arms, switch them on, then double-click check_arms.bat
echo If Windows does not recognise the arm USB adapters (no COM port), install the WCH CH343 driver:
echo   https://www.wch-ic.com/downloads/CH343SER_EXE.html
pause

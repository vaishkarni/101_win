@echo off
cd /d "%~dp0..\common"
echo ======================================================
echo   SO-101 TELEOP
echo   1. Both arms plugged in by USB and powered ON?
echo   2. Keep hands clear of the FOLLOWER: it will move
echo      slowly to copy the leader when it starts.
echo   3. Stop with Ctrl-C. Hold the follower while it
echo      counts down, then it goes limp.
echo ======================================================
python -m so101 check >nul 2>&1 || ( python -m so101 check & echo. & echo !! Fix the problem above, then start again. & pause & exit /b 1 )
python -m so101 teleop %*
pause

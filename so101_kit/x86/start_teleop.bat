@echo off
cd /d "%~dp0..\common"
echo ======================================================
echo   SO-101 TELEOP
echo   1. Both arms plugged in by USB and powered ON?
echo   2. Keep hands clear of the FOLLOWER: it will move
echo      slowly to copy the leader when it starts.
echo   3. Stop with Ctrl-C. Hold the follower while it
echo      counts down, then it goes limp. Do NOT close
echo      the window or cut the power while it runs.
echo ======================================================
python -m so101 check >nul 2>&1
if not errorlevel 1 goto teleop
python -m so101 check
echo.
echo !! The check failed. If a previous teleop was cut short, the servo settings
echo    can be repaired from the owner's snapshot (nothing moves).
choice /C YN /N /M "   Try the repair and check again? [Y/N] "
if errorlevel 2 ( echo !! Fix the problem above, then start again. & pause & exit /b 1 )
python -m so101 restore-snapshot
python -m so101 check || ( echo. & echo !! Still failing - fix the problem above, then start again. & pause & exit /b 1 )
:teleop
python -u -m so101 teleop %*
set RC=%errorlevel%
echo.
if "%RC%"=="4" echo !! The follower's wrist-roll servo lost its turn counter. Switch the FOLLOWER power OFF, wait 5 s, ON again, then start again.
if "%RC%"=="3" echo !! The follower is posed too far from the leader. Move the FOLLOWER by hand close to the leader's pose (it is limp), then start again.
if "%RC%"=="2" echo !! The follower servos did not answer or their settings are wrong. Check its power switch and USB cable, then start again.
pause

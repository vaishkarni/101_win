@echo off
cd /d "%~dp0..\common"
python -m so101 check -v
pause

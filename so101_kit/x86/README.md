# SO-101 teleop on a PC or laptop (x86)

## Linux (Ubuntu / Debian)
1. Copy the whole kit folder onto the computer.
2. Open a terminal in this `x86` folder and run `bash setup.sh` - it asks for your password once. Log out and back in once.
3. Plug both arms in by USB, connect their power supplies and switch them on.
4. `bash check_arms.sh` - must end with `BOTH ARMS OK`.
5. `bash start_teleop.sh`, or double-click the **SO-101 Teleop** desktop icon. Stop with Ctrl-C.

## Windows 10 / 11
1. Install Python 3 from https://www.python.org/downloads/ and tick **"Add python.exe to PATH"** in the installer.
2. Double-click `setup.bat`.
3. Plug both arms in by USB, connect their power supplies and switch them on. Windows installs the USB-serial
   driver by itself; if no COM port appears after a minute, install the CH343 driver from
   https://www.wch-ic.com/downloads/CH343SER_EXE.html
4. Double-click `check_arms.bat` - must end with `BOTH ARMS OK`.
5. Double-click `start_teleop.bat`. Stop with Ctrl-C in its window.

## macOS
Works with the same Python program: `pip3 install pyserial`, then in `../common` run `python3 -m so101 check` and `python3 -m so101 teleop`.

Notes
- setup.sh removes the `brltty` package if present (it hijacks USB-serial adapters on some Ubuntu versions).
- Any USB port works, USB 2 or 3. The arms are found by their adapter serial numbers, so the port order does not matter.

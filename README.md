# SO-101 leader/follower teleop - Windows one-click kit

For the demo PC the two SO-101 arms are plugged into (Windows 10/11). No technical knowledge needed.

## Setup

1. Click the green **Code** button above, **Download ZIP**, and unzip it anywhere (Desktop is fine).
2. Plug both arms in by USB, connect both power supplies, switch them on.
3. Double-click **`One click demo.bat`**.

That's it. The script:

- installs Python 3 and the pyserial library if the PC does not have them yet (asks before installing Python;
  pyserial is bundled, no internet needed),
- checks both arms (nothing moves). If the check fails it shows the cause and offers **R** to retry.
  Usual causes: an arm is not plugged in or not powered, or Windows has no driver for the USB adapter yet -
  wait a minute, if still failing install the CH343 driver from https://www.wch-ic.com/downloads/CH343SER_EXE.html
  and unplug/replug the arms,
- starts teleop: move the **LEADER** by hand, the **FOLLOWER** copies it. Keep hands clear of the follower.

## Stopping

Press **Ctrl-C** in the window, hold the follower during the 3 second countdown, then it goes limp.
If Windows asks `Terminate batch job (Y/N)?`: **N** = back to the menu (S = start again), **Y** = close the window.

## Do not recalibrate

The arms were calibrated by the owner. The calibration is stored inside the servos and ships with the arms;
nothing on the PC needs calibrating. The owner tools in `so101_kit/common` are not needed for the demo.

## Files

- `One click demo.bat` - the only file to run
- `so101_kit/` - the teleop program (`common/`, calibrated `arm_config.json`, bundled `wheels/`), plus
  `x86/` and `jetson/` scripts for one-step-at-a-time use or Linux PCs

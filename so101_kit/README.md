# SO-101 Leader / Follower Teleop Kit

Two SO-101 robot arms: you move the **leader** arm by hand and the **follower** arm copies it.
The arms are already calibrated. Nothing has to be measured or tuned on your side.

## Which folder do I open?

| Your computer | Folder |
|---|---|
| NVIDIA Jetson (Orin Nano, Orin NX, AGX Orin, ...) | `jetson/` |
| Any normal PC or laptop (Ubuntu / Debian Linux, or Windows 10/11) | `x86/` |

Not sure? Jetson boards are the small green NVIDIA boxes. Everything else is `x86/`.
Both folders use the same program in `common/`, so copy the **whole kit folder**, not just one sub-folder.

## Three steps

1. **Setup, once**: open a terminal in the folder for your computer and run `bash setup.sh`
   (Windows: double-click `setup.bat`). It installs one small Python library and gives you access to the arms' USB ports.
   On Linux, log out and back in once after setup.
2. **Check**: plug in both arms (USB + power, switches ON) and run `bash check_arms.sh` (Windows: `check_arms.bat`).
   It must end with `BOTH ARMS OK`.
3. **Teleop**: run `bash start_teleop.sh` (Windows: `start_teleop.bat`), or double-click the *SO-101 Teleop* icon that setup put on the desktop.
   Keep clear of the follower: it first moves slowly to the leader's pose, then follows live. Stop with **Ctrl-C**; hold the follower during the 3-second countdown, it goes limp afterwards.
   **Always stop with Ctrl-C.** Do not close the window or switch the arms off while teleop runs: Ctrl-C lets the program put the
   wrist-roll servo back in order. If that ever happens anyway, the next check fails and offers a one-key repair.

## Something is wrong?

Run `check_arms.sh` and read the lines marked `FAIL`. The usual causes, in order:

- **No arms found**: a USB cable is out, or (Linux) setup was not run / you did not log out and in again.
- **Only one arm found / motors do not answer**: that arm's power supply is unplugged or its switch is off.
  The follower needs its 12 V supply; the leader runs on its own small supply.
- **Follower is very far from the leader**: move the follower by hand roughly into the leader's pose and start again.
- **A joint "is pushing against something"**: the follower hit an obstacle or its own limit. Move the leader back a bit; it resumes by itself.
- **Calibration differs from the owner's snapshot**: do not use the arms; contact the owner.

Nothing in this kit changes the arms' calibration. Only the owner tools (`python3 -m so101 rangecal`, `shift`, `restore`...) do, and they are not used by the scripts above.

## What is inside

- `common/so101/` - the program (Python 3, needs only `pyserial`): servo driver, health check, teleop, owner calibration tools
- `common/arm_config.json` - which USB adapter is which arm, gripper mapping, teleop speeds, the owner's calibration snapshot
- `jetson/`, `x86/` - setup / check / start / stop scripts for each platform (x86 also has Windows `.bat` files)
- `OWNER_CHECKLIST.md` - for the owner: how to calibrate and prepare the arms before handing them over

Advanced: everything is also reachable as `cd common && python3 -m so101 --help`.

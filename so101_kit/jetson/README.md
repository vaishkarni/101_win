# SO-101 teleop on an NVIDIA Jetson

Tested on a Jetson Orin Nano (JetPack 6, Ubuntu 22.04). Works the same on Orin NX / AGX Orin / Xavier with JetPack 5 or 6.

1. Copy the whole kit folder onto the Jetson (USB stick, or `scp`).
2. Open a terminal in this `jetson` folder and run `bash setup.sh` - it asks for your password once.
   Then log out and back in (or reboot) once.
3. Plug both arms into the Jetson's USB ports (a powered hub is fine), connect their power supplies and switch them on.
4. `bash check_arms.sh` - must end with `BOTH ARMS OK`.
5. `bash start_teleop.sh`, or double-click the **SO-101 Teleop** icon on the desktop.
   Keep clear of the follower while it moves to the leader's pose. Stop with Ctrl-C.

Notes
- Only the arms' USB cables go to the Jetson. The arms are powered by their own supplies, not by USB.
- No Docker, no conda, no ROS: plain `python3` + `pyserial` (installed by setup.sh with apt).
- If an icon says "untrusted", right-click it and choose *Allow Launching*.
- The Jetson's own USB console (NVIDIA, /dev/ttyACM*) is ignored automatically; the arms are found by their adapter serial numbers.

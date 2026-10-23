#!/bin/bash
# One-time setup for the SO-101 teleop kit on a normal PC or laptop (Ubuntu 20.04 / 22.04 / 24.04 or Debian, x86_64).
# Run once:   bash setup.sh      (it will ask for your password for sudo)
set -e
KIT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== SO-101 teleop kit setup (x86 Linux) =="
if [ "$(uname -m)" = "aarch64" ]; then echo "!! This looks like a Jetson/ARM machine. Use the jetson folder instead."; exit 1; fi
echo "-- installing Python serial support (apt)"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-serial python3-pip >/dev/null
python3 -c "import serial" 2>/dev/null || python3 -m pip install --user pyserial
echo "-- giving your user access to the USB arm adapters"
sudo usermod -aG dialout "$USER"
sudo tee /etc/udev/rules.d/99-so101-arms.rules >/dev/null <<'RULES'
# SO-101 arm USB bus adapters (WCH CH343/CH340 serial): make them usable without root
SUBSYSTEM=="tty", ATTRS{idVendor}=="1a86", MODE="0666", GROUP="dialout"
RULES
sudo udevadm control --reload-rules && sudo udevadm trigger
if dpkg -l brltty 2>/dev/null | grep -q '^ii'; then
  echo "-- removing brltty (braille display service that steals USB serial adapters)"
  sudo apt-get remove -y -qq brltty >/dev/null
fi
echo "-- desktop shortcuts"
bash "$KIT/x86/make_shortcuts.sh" || true
echo
echo "== Setup done. =="
echo "If the arms were plugged in during setup, unplug and re-plug their USB cables once."
echo "Then run:  bash $KIT/x86/check_arms.sh"
echo "(If check_arms says 'permission denied', log out and back in once - the dialout group needs a new login.)"

#!/bin/bash
# Creates "SO-101 Teleop" and "SO-101 Check Arms" icons on the Desktop (GNOME / Ubuntu desktop).
KIT="$(cd "$(dirname "$0")/.." && pwd)"; HERE="$KIT/x86"
DESK="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"; mkdir -p "$DESK"
mk() {  # name, script
  f="$DESK/$1.desktop"
  cat > "$f" <<D
[Desktop Entry]
Type=Application
Name=$1
Comment=SO-101 arms
Exec=bash -c '"$HERE/$2"; echo; read -p "Press Enter to close this window"'
Terminal=true
Icon=utilities-terminal
Categories=Utility;
D
  chmod +x "$f"; gio set "$f" metadata::trusted true 2>/dev/null || true
}
mk "SO-101 Teleop" start_teleop.sh
mk "SO-101 Check Arms" check_arms.sh
echo "shortcuts created in $DESK (if an icon asks 'Allow Launching', right-click it and choose that)"

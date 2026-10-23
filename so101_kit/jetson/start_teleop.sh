#!/bin/bash
# Start leader -> follower teleop. Stop it with Ctrl-C (or by closing the window after it says 'torque OFF').
KIT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$KIT/common"
echo "======================================================"
echo "  SO-101 TELEOP"
echo "  1. Both arms plugged in by USB and powered ON?"
echo "  2. Keep hands clear of the FOLLOWER: it will move"
echo "     slowly to copy the leader when it starts."
echo "  3. Stop with Ctrl-C. Hold the follower while it"
echo "     counts down, then it goes limp."
echo "======================================================"
python3 -m so101 check >/dev/null 2>&1 || { python3 -m so101 check; echo; echo "!! Fix the problem above, then start again."; exit 1; }
exec python3 -m so101 teleop "$@"

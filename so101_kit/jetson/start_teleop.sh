#!/bin/bash
# Start leader -> follower teleop. Stop it with Ctrl-C (hold the follower during the countdown, then it goes limp).
# Do NOT close the window or cut the power while it runs: Ctrl-C lets the program put the servos back in order.
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
if ! python3 -m so101 check >/dev/null 2>&1; then
  python3 -m so101 check
  echo
  if [ -t 0 ]; then
    printf '!! The check failed. If a previous teleop was cut short, the servo settings can be repaired\n   from the owner\x27s snapshot (nothing moves). Try the repair and check again? [y/N] '
    read -r ans
    if [ "$ans" = y ] || [ "$ans" = Y ]; then
      python3 -m so101 restore-snapshot && python3 -m so101 check && exec python3 -u -m so101 teleop "$@"
    fi
  fi
  echo "!! Fix the problem above, then start again."; exit 1
fi
python3 -u -m so101 teleop "$@"; rc=$?
case $rc in
  0|130) ;;
  4) echo; echo "!! The follower's wrist-roll servo lost its turn counter. Switch the FOLLOWER power OFF, wait 5 s, ON again, then start again." ;;
  3) echo; echo "!! The follower is posed too far from the leader. Move the FOLLOWER by hand close to the leader's pose (it is limp), then start again." ;;
  2) echo; echo "!! The follower servos did not answer or their settings are wrong. Check its power switch and USB cable, then start again (the check offers a repair)." ;;
  *) echo; echo "!! teleop exited with code $rc - see the lines above." ;;
esac
exit $rc

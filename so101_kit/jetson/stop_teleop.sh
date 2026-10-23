#!/bin/bash
# Stop a running teleop politely (same as Ctrl-C in its window: hold, count down, release).
pkill -INT -f "so101 teleop" && echo "stop requested - the follower goes limp after the countdown" || echo "teleop is not running"

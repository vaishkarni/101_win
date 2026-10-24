# Owner checklist - before handing the arms to a client

Everything the arms need to work 1:1 lives in the servos themselves (EEPROM offsets and limits) plus
`common/arm_config.json` (adapter serials, gripper map, calibration snapshot). The client never calibrates.

## A. Calibrate (only when needed - full calibration 2026-09-11, wrist-roll offsets re-homed 2026-10-24)

Run from `common/` on any machine with the arms connected (`python3 -m so101 ...`, pyserial installed, port access):

1. `backup backup_before.json` - safety copy of every servo's offset + limits.
2. `rangecal leader` then `rangecal follower` - torque off, sweep every joint to BOTH mechanical stops
   (gripper fully open and closed). Each joint's travel is centred on 2048; follower limits = stops minus 40 counts.
3. `compare` - leader/follower spans should match within ~60 counts. **wrist_roll has no stop** and the demo needs more
   than one turn of it, so teleop drives the follower roll in servo multi-turn mode (see D). Both rolls were `shift`-ed
   on 2026-10-24 so the owner's home pose reads ~3686 counts (the 0/4095 wrap sits ~36 deg above home); keep leader and
   follower roll offsets shifted by the same amount.
4. Hold both arms in the same pose, `matchcheck` - differences should be small and all `same dir`.
   Fix residual offsets with `shift ARM JOINT DELTA` (reading becomes reading-DELTA) at pressed stops.
5. `gripper` - measures the follower jaw stops at low torque and stores the gripper map
   (the leader side of the map comes from its rangecal).
6. Trim any follower limit by editing `follower.limits_counts` in arm_config.json and running `setlimits`
   (the wrist_flex max is kept at 2850 to avoid the stall seen at ~2817 under load).

## B. Snapshot and test (ALWAYS, right before shipping)

1. `python3 -m so101 snapshot` - stores the servos' offsets + limits in arm_config.json. The client's
   `check_arms` compares the servos against this and refuses teleop if they differ.
2. `python3 -m so101 check -v` must say `BOTH ARMS OK`.
3. `python3 -m so101 teleop` - run a few minutes of live teleop, including the gripper and the wrist roll THROUGH the wrap
   (turn it more than one full turn each way: the follower must keep following, no long swing, and must stop at the
   travel guard 1.5 turns from where it started). Stop with Ctrl-C and run `check` again: it must be green (roll limits
   back to 1-4094).
4. Simulated tests (no arms needed, pyserial installed): `python3 tests/test_kit.py` from `common/`, and
   `python3 tests/fake_multiturn_test.py .` and `python3 tests/fake_teleop_test.py .` from `common/`. All three print a pass line.
5. If the USB adapters were ever swapped: `python3 -m so101 adopt-serials` (leader = lower bus voltage).

## C. Package

- `bash make_release.sh` builds `so101_kit_jetson.zip` and `so101_kit_x86.zip` (each contains `common/` + its platform folder + README).
  Or just copy the whole `client_kit` folder to a USB stick.
- Ship with the arms: both USB cables, the follower's 12 V supply, the leader's supply, this folder.
- Label the arms LEADER / FOLLOWER. The adapter serials are in arm_config.json
  (leader 58FD016978, follower 58FD017395 as of 2026-10-12).

## D. Known gotchas to mention to the client

- **Wrist roll runs in servo multi-turn mode while teleop runs** (both angle limits 0). Teleop probes the servo's hidden
  turn counter at start with low torque, never sends the roll more than 1.5 turns from its start angle (the gripper
  cable runs through the wrist), and writes the single-turn limits 1-4094 back on exit. Always stop with Ctrl-C.
  If a run is cut short (window closed, power lost) the next `check` fails on the roll limits: `restore-snapshot`
  repairs it (the one-click launchers offer this). If teleop exits with "could not find the servo turn counter",
  power-cycle the FOLLOWER (that resets the counter) and start again.
- Never send a multi-turn goal to the roll by hand without a fresh probe, and never remove the travel guard: an unbounded
  multi-turn goal once spun the roll over a full turn and pulled the gripper servo cable out (2026-10-24).

- Leader bus is ~5 V by design; its servos cannot drive and `check` accepts that (`VOLTAGE` flag on the leader is normal).
- If the leader's shoulder_lift stops following (frozen encoder seen once), unplug/replug the leader's USB.
- Fast-blinking follower LED = servo alarm under load, clears when torque is released (stop/start teleop).
- Flaky packets on the follower bus are expected; the driver retries and the goal is resent every tick.

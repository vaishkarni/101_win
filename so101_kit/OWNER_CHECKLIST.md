# Owner checklist - before handing the arms to a client

Everything the arms need to work 1:1 lives in the servos themselves (EEPROM offsets and limits) plus
`common/arm_config.json` (adapter serials, gripper map, calibration snapshot). The client never calibrates.

## A. Calibrate (only when needed - the arms were last calibrated 2026-09-11)

Run from `common/` on any machine with the arms connected (`python3 -m so101 ...`, pyserial installed, port access):

1. `backup backup_before.json` - safety copy of every servo's offset + limits.
2. `rangecal leader` then `rangecal follower` - torque off, sweep every joint to BOTH mechanical stops
   (gripper fully open and closed). Each joint's travel is centred on 2048; follower limits = stops minus 40 counts.
3. `compare` - leader/follower spans should match within ~60 counts (wrist_roll has no stop: both arms were set to
   2048 in the same natural pose instead; use `shift` if needed).
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
3. `python3 -m so101 teleop` - run a few minutes of live teleop, including the gripper and wrist roll.
4. If the USB adapters were ever swapped: `python3 -m so101 adopt-serials` (leader = lower bus voltage).

## C. Package

- `bash make_release.sh` builds `so101_kit_jetson.zip` and `so101_kit_x86.zip` (each contains `common/` + its platform folder + README).
  Or just copy the whole `client_kit` folder to a USB stick.
- Ship with the arms: both USB cables, the follower's 12 V supply, the leader's supply, this folder.
- Label the arms LEADER / FOLLOWER. The adapter serials are in arm_config.json
  (leader 58FD016978, follower 58FD017395 as of 2026-10-12).

## D. Known gotchas to mention to the client

- Leader bus is ~5 V by design; its servos cannot drive and `check` accepts that (`VOLTAGE` flag on the leader is normal).
- If the leader's shoulder_lift stops following (frozen encoder seen once), unplug/replug the leader's USB.
- Fast-blinking follower LED = servo alarm under load, clears when torque is released (stop/start teleop).
- Flaky packets on the follower bus are expected; the driver retries and the goal is resent every tick.

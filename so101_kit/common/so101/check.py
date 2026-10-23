"""Plain-language health check for both arms (read only, nothing moves)."""
import sys
import time
from .arms import NAMES, IDS, feetech_ports, resolve_ports, Arm
from .feetech import STATUS_FLAGS, STS3215_MODEL, BusError


def check_arm(role, port, cfg, verbose):
    print('\n%s arm on %s' % (role.upper(), port))
    try:
        arm = Arm(role, port, cfg)
    except Exception as e:
        print('  FAIL: cannot open the port (%s)' % e)
        return False
    ok = True
    try:
        rows = arm.health()
    except BusError as e:
        print('  FAIL: servos do not answer (%s). Is the %s power switch on? Is the power supply plugged in?' % (e, role))
        arm.close(); return False
    missing = [r['joint'] for r in rows if not r['ok']]
    if len(missing) == 6:
        print('  FAIL: none of the 6 motors answer. Switch the %s arm power ON and check its power supply.' % role)
        arm.close(); return False
    if missing:
        print('  FAIL: motors not answering: %s (check the cable between the motors)' % ', '.join(missing)); ok = False
    live = [r for r in rows if r['ok']]
    v = sum(r['v'] for r in live) / len(live)
    nominal = cfg[role]['bus_voltage_nominal']
    print('  %d of 6 motors answer, bus voltage %.1f V (expected about %.0f V)' % (len(live), v, nominal))
    if role == 'follower' and v < 9.0:
        print('  FAIL: follower voltage too low - plug in the 12 V power supply and switch it on.'); ok = False
    if role == 'leader' and v < 4.5:
        print('  FAIL: leader voltage too low - check its power.'); ok = False
    for r in live:
        flags = [f for b, f in STATUS_FLAGS.items() if r['status'] & (1 << b)]
        if r['model'] != STS3215_MODEL:
            print('  WARN: %s reports model %d (expected STS3215 = %d)' % (r['joint'], r['model'], STS3215_MODEL))
        if r['temp'] > 60:
            print('  WARN: %s is hot (%d C) - let it cool' % (r['joint'], r['temp']))
        if flags and not (role == 'leader' and flags == ['VOLTAGE']):
            print('  WARN: %s reports %s' % (r['joint'], ','.join(flags)))
    # calibration check against the owner's snapshot
    snap = (cfg.get('eeprom_snapshot') or {}).get(role)
    if snap:
        diffs = []
        for r in live:
            s = snap.get(r['joint'])
            if not s:
                continue
            if r['offset'] != s['offset'] or r['min'] != s['min'] or r['max'] != s['max']:
                diffs.append('%s (offset %d/%d, limits %d-%d / %d-%d)' % (r['joint'], r['offset'], s['offset'], r['min'], r['max'], s['min'], s['max']))
        if diffs:
            print('  FAIL: the servo calibration differs from the owner\'s snapshot on: ' + '; '.join(diffs))
            print('        Do NOT run teleop. Contact the owner (or restore with: python3 -m so101 restore-snapshot).'); ok = False
        else:
            print('  calibration matches the owner\'s snapshot')
    else:
        print('  (no calibration snapshot in arm_config.json - owner has not run "snapshot")')
    if verbose:
        print('  %-14s %3s %5s %5s %4s %6s %5s %5s %6s' % ('joint', 'id', 'pos', 'V', 'C', 'status', 'min', 'max', 'offset'))
        for r in live:
            print('  %-14s %3d %5d %5.1f %4d   0x%02x %5d %5d %6d' % (r['joint'], r['id'], r['pos'], r['v'], r['temp'], r['status'], r['min'], r['max'], r['offset']))
    arm.close()
    print('  RESULT: %s' % ('OK' if ok else 'PROBLEM'))
    return ok


def run(cfg, args):
    found = feetech_ports()
    print('USB arm adapters found: ' + (', '.join('%s (serial %s)' % (d, s or '?') for d, s in found) or 'NONE'))
    lp, fp = resolve_ports(cfg, args.leader, args.follower)
    okl = check_arm('leader', lp, cfg, args.verbose)
    okf = check_arm('follower', fp, cfg, args.verbose)
    print('\n==== %s ====' % ('BOTH ARMS OK - you can start teleop' if okl and okf else 'SOMETHING IS WRONG - see the lines marked FAIL above'))
    sys.exit(0 if okl and okf else 1)

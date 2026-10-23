"""Owner-side calibration tools (port of arm_calib.py to the standalone driver).

  snapshot             read Offset + limits of both arms into arm_config.json (ship this with the arms)
  restore-snapshot     write Offset + limits from arm_config.json back into the servos
  backup FILE          dump Offset + limits + positions of both arms to FILE (json)
  restore FILE         write Offset + limits back from a backup json
  rangecal ARM [SECS]  hard-stop calibration: torque off, sweep EVERY joint to both mechanical stops; the mid-point of
                       each joint's travel is made to read 2048 (EEPROM offset); follower limits = stops - 40 counts
  compare              leader vs follower travel per joint from the last rangecal, and the gripper map
  check                leader vs follower readings (median of 9) + per-joint difference, for a hand-matched pose
  gripper              drive the follower gripper to its stops at low torque and store the endpoint map
  shift ARM JOINT D    make JOINT on ARM read (reading - D) at the same physical pose (EEPROM offset)
  setlimits            rewrite the follower limits from arm_config.json follower.limits_counts
  adopt-serials        store the adapter serial numbers of the currently connected arms in arm_config.json
"""
import json
import statistics
import sys
import time
from .arms import NAMES, IDS, open_arms, resolve_ports, save_config, feetech_ports, bus_voltage, bus_alive, Arm
from .feetech import dec_offset, enc_offset, BusError, FeetechBus


def _median_pos(arm, n=9):
    S = []
    for _ in range(n):
        try:
            S.append(arm.positions())
        except BusError:
            pass
        time.sleep(0.03)
    return [int(statistics.median(s[i] for s in S)) for i in range(6)]


def _set_offset_delta(bus, sid, delta):
    """Shift one servo's reading by -delta (reading' = reading - delta). Returns (before, after, new_offset)."""
    before = bus.read(sid, 'Present_Position'); off = dec_offset(bus.read(sid, 'Offset'))
    want = (before - delta) % 4096
    for cand in (off + delta, off - delta):
        while cand > 2047: cand -= 4096
        while cand < -2048: cand += 4096
        bus.write_eeprom(sid, 'Offset', enc_offset(cand)); time.sleep(0.05)
        after = bus.read(sid, 'Present_Position')
        if min((after - want) % 4096, (want - after) % 4096) <= 3:
            return before, after, cand
    raise BusError('id %d: offset write did not produce the expected reading (%d, wanted %d)' % (sid, after, want))


def _write_limits(bus, sid, lo, hi):
    for _ in range(6):
        try:
            bus.write_eeprom(sid, 'Min_Angle_Limit', lo); time.sleep(0.03)
            bus.write_eeprom(sid, 'Max_Angle_Limit', hi); time.sleep(0.03)
            return
        except BusError:
            time.sleep(0.05)
    raise BusError('id %d: could not write limits %d-%d' % (sid, lo, hi))


def cmd_snapshot(cfg, args):
    L, F = open_arms(cfg, args.leader, args.follower)
    snap = {'leader': L.eeprom_snapshot(), 'follower': F.eeprom_snapshot(), 'taken': time.strftime('%Y-%m-%d %H:%M:%S')}
    for role, a in (('leader', L), ('follower', F)):
        print(role, {n: (d['offset'], d['min'], d['max']) for n, d in snap[role].items()})
    cfg['eeprom_snapshot'] = snap
    cfg['follower']['limits_counts'] = {n: [d['min'], d['max']] for n, d in snap['follower'].items()}
    save_config(cfg); L.close(); F.close()


def cmd_restore_snapshot(cfg, args):
    snap = cfg.get('eeprom_snapshot')
    if not snap:
        sys.exit('no eeprom_snapshot in arm_config.json')
    _restore(cfg, args, snap)


def cmd_backup(cfg, args):
    L, F = open_arms(cfg, args.leader, args.follower)
    out = {}
    for role, a in (('leader', L), ('follower', F)):
        out[role] = a.eeprom_snapshot()
        pos = a.positions()
        for n, p in zip(NAMES, pos): out[role][n]['pos'] = p
        print(role, {n: (d['offset'], d['min'], d['max']) for n, d in out[role].items()})
    json.dump(out, open(args.file, 'w'), indent=1); print('backup written:', args.file)
    L.close(); F.close()


def cmd_restore(cfg, args):
    _restore(cfg, args, json.load(open(args.file)))


def _restore(cfg, args, bk):
    L, F = open_arms(cfg, args.leader, args.follower)
    for role, a in (('leader', L), ('follower', F)):
        a.torque(False)
        for n, i in zip(NAMES, IDS):
            d = bk[role][n]
            a.bus.write_eeprom(i, 'Offset', enc_offset(d['offset'])); time.sleep(0.03)
            _write_limits(a.bus, i, d['min'], d['max'])
            print('%s.%s: offset=%d lim=%d-%d' % (role, n, dec_offset(a.bus.read(i, 'Offset')), a.bus.read(i, 'Min_Angle_Limit'), a.bus.read(i, 'Max_Angle_Limit')))
    print('restored'); L.close(); F.close()


def cmd_rangecal(cfg, args):
    role = args.arm; secs = args.seconds; MARGIN = 40 if role == 'follower' else 0
    L, F = open_arms(cfg, args.leader, args.follower)
    a = L if role == 'leader' else F
    a.torque(False)
    for i in IDS: _write_limits(a.bus, i, 0, 4095)
    p0 = a.positions()
    print('[%s] torque OFF, limits opened. Move EVERY joint to BOTH mechanical stops (gripper fully open and closed).' % role, flush=True)
    print('[%s] waiting for the first motion... (then up to %.0f s of recording; ends early after 8 s without motion once every joint has >100 counts)' % (role, secs), flush=True)
    lo = list(p0); hi = list(p0); t0 = None; last_move = None; prev = list(p0)
    while True:
        p = a.positions()
        moved = max(abs(x - y) for x, y in zip(p, prev)) > 6; prev = p
        if t0 is None:
            if max(abs(x - y) for x, y in zip(p, p0)) > 30:
                t0 = time.time(); last_move = t0; print('[%s] motion detected, recording' % role, flush=True)
            time.sleep(0.02); continue
        if moved: last_move = time.time()
        lo = [min(x, y) for x, y in zip(lo, p)]; hi = [max(x, y) for x, y in zip(hi, p)]
        el = time.time() - t0
        if int(el * 50) % 250 == 0:
            print('  t=%3.0fs span=' % el + ' '.join('%s:%d' % (nm[:5], h - l) for nm, l, h in zip(NAMES, lo, hi)), flush=True)
        if el > secs or (el > 20 and time.time() - last_move > 8 and min(h - l for l, h in zip(lo, hi)) > 100): break
        time.sleep(0.02)
    print('[%s] travel: ' % role + ', '.join('%s=%d..%d (%d)' % (nm, l, h, h - l) for nm, l, h in zip(NAMES, lo, hi)), flush=True)
    wrap = [nm for nm, l, h in zip(NAMES, lo, hi) if l < 5 or h > 4090]
    if wrap: print('!! joints touching the 0/4095 wrap (travel may cross it): %s - results for them may be off; re-run with the joint started mid-travel' % wrap)
    print('[%s] centring each joint on 2048 (EEPROM offset)...' % role, flush=True)
    rng = {}
    for k, (n, i) in enumerate(zip(NAMES, IDS)):
        if hi[k] - lo[k] < 100:
            print('  %-14s travel %d too small - skipped' % (n, hi[k] - lo[k])); continue
        mid = (lo[k] + hi[k]) // 2; delta = mid - 2048
        before, after, newoff = _set_offset_delta(a.bus, i, delta)
        l, h = lo[k] - delta, hi[k] - delta; rng[n] = [l, h]
        print('  %-14s mid %5d -> 2048  offset now %5d  pos %d->%d   travel now %d..%d' % (n, mid, newoff, before, after, l, h), flush=True)
        if role == 'follower':
            _write_limits(a.bus, i, max(0, l + MARGIN), min(4095, h - MARGIN))
            print('  %-14s follower limits %d-%d' % ('', max(0, l + MARGIN), min(4095, h - MARGIN)), flush=True)
    cal = cfg.setdefault('rangecal', {}); cal[role] = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'range': rng, 'span': {n: h - l for n, (l, h) in rng.items()}}
    if 'gripper' in rng:
        g = cfg.setdefault('gripper_map', {})
        g[role + '_closed'] = rng['gripper'][0] + MARGIN; g[role + '_open'] = rng['gripper'][1] - MARGIN
    if role == 'follower':
        cfg['follower']['limits_counts'] = {n: [max(0, l + MARGIN), min(4095, h - MARGIN)] for n, (l, h) in rng.items()}
    cfg['eeprom_snapshot'] = None   # stale now: run snapshot again
    save_config(cfg); L.close(); F.close()
    print('[%s] done. Every joint reads 2048 at the middle of its travel. Run "snapshot" when both arms are calibrated.' % role)


def cmd_compare(cfg, args):
    rc = cfg.get('rangecal', {}); Lr = rc.get('leader', {}).get('range', {}); Fr = rc.get('follower', {}).get('range', {})
    print('%-14s%16s%18s%8s%8s%6s' % ('joint', 'leader travel', 'follower travel', 'span L', 'span F', 'diff'))
    for n in NAMES:
        if n in Lr and n in Fr:
            sl = Lr[n][1] - Lr[n][0]; sf = Fr[n][1] - Fr[n][0]
            flag = '' if abs(sf - sl) < 60 or n == 'gripper' else '!! stops differ: same pose may read up to %d counts apart at the ends' % (abs(sf - sl) // 2)
            print('%-14s%7d..%-7d%9d..%-7d%8d%8d%6d  %s' % (n, Lr[n][0], Lr[n][1], Fr[n][0], Fr[n][1], sl, sf, sf - sl, flag))
    print('gripper map:', cfg.get('gripper_map'))


def cmd_check(cfg, args):
    L, F = open_arms(cfg, args.leader, args.follower)
    L.torque(False); F.torque(False)
    lp = _median_pos(L); fp = _median_pos(F)
    print('%-14s%8s%9s%6s%8s%8s' % ('joint', 'leader', 'follower', 'diff', 'L-2048', 'F-2048'))
    for nm, l, f in zip(NAMES, lp, fp):
        s = '' if (abs(l - 2048) < 60 or abs(f - 2048) < 60) else ('same dir' if (l - 2048) * (f - 2048) > 0 else '!! MIRRORED')
        print('%-14s%8d%9d%6d%8d%8d  %s' % (nm, l, f, f - l, l - 2048, f - 2048, s))
    L.close(); F.close()


def cmd_gripper(cfg, args):
    L, F = open_arms(cfg, args.leader, args.follower)
    i = 6; b = F.bus
    lo, hi = b.read(i, 'Min_Angle_Limit'), b.read(i, 'Max_Angle_Limit'); old_tl = b.read(i, 'Torque_Limit')

    def seek(t):
        b.write(i, 'Goal_Position', t); last = None; still = 0; t0 = time.time()
        while time.time() - t0 < 8:
            p = b.read(i, 'Present_Position')
            still = still + 1 if (last is not None and abs(p - last) <= 2) else 0; last = p
            if still >= 8 or abs(p - t) <= 5: break
            time.sleep(0.05)
        return p
    try:
        b.write(i, 'Torque_Limit', 300); b.write(i, 'Acceleration', 20); b.write(i, 'Goal_Speed', 200); b.write(i, 'Torque_Enable', 1)
        c = seek(lo); time.sleep(0.3); o = seek(hi); time.sleep(0.3); seek(c)
    finally:
        b.write(i, 'Torque_Enable', 0); b.write(i, 'Torque_Limit', old_tl)
    g = cfg.setdefault('gripper_map', {}); g['follower_closed'] = c; g['follower_open'] = o
    print('follower gripper closed/open stops:', c, o, '| leader closed/open:', g.get('leader_closed'), g.get('leader_open'))
    save_config(cfg); L.close(); F.close()


def cmd_shift(cfg, args):
    L, F = open_arms(cfg, args.leader, args.follower)
    a = L if args.arm == 'leader' else F; i = IDS[NAMES.index(args.joint)]
    before, after, newoff = _set_offset_delta(a.bus, i, args.delta)
    print('%s.%s: offset now %d, reading %d -> %d' % (args.arm, args.joint, newoff, before, after))
    cfg.setdefault('shifts', []).append([args.arm, args.joint, args.delta, time.strftime('%Y-%m-%d %H:%M:%S')])
    cfg['eeprom_snapshot'] = None
    save_config(cfg); L.close(); F.close()


def cmd_setlimits(cfg, args):
    L, F = open_arms(cfg, args.leader, args.follower)
    for n, i in zip(NAMES, IDS):
        lo, hi = cfg['follower']['limits_counts'][n]
        _write_limits(F.bus, i, lo, hi)
        print('  %-14s limits %d-%d readback %d-%d' % (n, lo, hi, F.bus.read(i, 'Min_Angle_Limit'), F.bus.read(i, 'Max_Angle_Limit')))
    cfg['eeprom_snapshot'] = None; save_config(cfg); L.close(); F.close()


def cmd_adopt_serials(cfg, args):
    found = feetech_ports()
    if len(found) != 2:
        sys.exit('need exactly two adapters connected, found %d' % len(found))
    info = []
    for dev, sn in found:
        b = FeetechBus(dev); n = bus_alive(b); v = bus_voltage(b) if n else None; b.close(); info.append((dev, sn, n, v))
        print('%s serial=%s motors=%d voltage=%s' % (dev, sn, n, v))
    live = sorted([x for x in info if x[3] is not None], key=lambda x: x[3])
    if len(live) != 2 or live[1][3] - live[0][3] < 1.5:
        sys.exit('cannot tell leader from follower by voltage; edit arm_config.json by hand')
    cfg['leader']['adapter_serial'] = live[0][1]; cfg['follower']['adapter_serial'] = live[1][1]
    print('leader = %s (%s), follower = %s (%s)' % (live[0][0], live[0][1], live[1][0], live[1][1]))
    save_config(cfg)

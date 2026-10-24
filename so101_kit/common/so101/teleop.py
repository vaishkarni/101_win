"""1:1 leader -> follower teleop for the servo-matched SO-101 arms.

Both arms were calibrated by the owner so that the same physical pose reads the same count on every joint
(offsets stored in the servos' EEPROM).  Each tick: follower goal = leader reading (clamped to the follower's
EEPROM limits, gripper through the endpoint map), slewed by at most --max-step counts, sent as one sync write.
Start-up: the follower ramps slowly to the leader's pose.  An overloaded joint stops pushing and holds until the
leader comes back close to it.  Ctrl-C: hold, count down, then release torque.

Wrist roll (teleop.multiturn_joints): both rolls turn freely all the way round, through the encoder's 0/4095
wrap, and the owner needs more than one turn of travel.  While teleop runs, the follower roll servo is put in
Feetech multi-turn mode (both angle limits 0): goals are then absolute multi-turn positions, k*4096 + reading,
and the servo always takes the short way.  The servo's turn counter k is invisible and persists while powered, so
teleop finds it at start with a PROBE: torque limited to mt_probe_torque, speed 100, goal = the current reading
assuming k = 0, then +1, -1, +2, -2 turns; the first goal that holds with no motion and no load is the right turn.
A wrong guess only creeps a few counts before torque is cut.  From then on every roll goal is clamped to
mt_travel_guard counts from the start angle (the gripper cable runs through the wrist) and the follower never
chases a leader more than mt_far_stop counts away.  On exit the single-turn limits are written back.
Other joints with real limits: the leader reading is unwrapped and clamped; past a stop the follower waits at the
stop and follows again when the leader comes back (or re-syncs after it settles on the far side).
"""
import os
import sys
import time
from .arms import NAMES, IDS, open_arms, CONFIG_PATH
from .feetech import BusError, enc_pos, dec_pos, s10


def open_log(args):
    """Per-tick CSV log (leader raw, leader unwrapped, follower goal, follower position, load, flags)."""
    path = getattr(args, 'log', None)
    if path == '-':
        return None, None
    if not path:
        d = os.path.join(os.path.dirname(CONFIG_PATH), 'logs')
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, time.strftime('teleop_%Y%m%d_%H%M%S.csv'))
    f = open(path, 'w')
    f.write('t,' + ','.join('%s_%s' % (k, n) for k in ('L', 'U', 'goal', 'F', 'load') for n in NAMES) + ',held,paused\n')
    return f, path


def short(d):
    return (d + 2048) % 4096 - 2048


def run(cfg, args):
    T = cfg['teleop']
    speed = T['speed'] if args.speed is None else args.speed
    accel = T['accel'] if args.accel is None else args.accel
    max_step = T['max_step'] if args.max_step is None else args.max_step
    resync_dwell = float(T.get('resync_dwell', 1.0)); resync_speed = int(T.get('resync_speed', 600))
    MT = [n for n in T.get('multiturn_joints', []) if n in NAMES]
    multi = [n in MT for n in NAMES]
    guard = int(T.get('mt_travel_guard', 6144)); far_stop = int(T.get('mt_far_stop', 4000))
    probe_torque = int(T.get('mt_probe_torque', 300)); probe_time = float(T.get('mt_probe_time', 0.5))
    signs = [int(s) for s in cfg.get('signs', [1] * 6)]
    active = [n for n in (args.joints.split(',') if args.joints else NAMES) if n in NAMES]
    act_idx = [NAMES.index(n) for n in active]
    act_ids = [IDS[i] for i in act_idx]
    G = cfg.get('gripper_map') or {}
    gain = None
    if G.get('leader_open') and G.get('follower_open'):
        gain = (G['follower_open'] - G['follower_closed']) / float(G['leader_open'] - G['leader_closed'])
        print('gripper map: leader %d..%d -> follower %d..%d (gain %.3f)' % (G['leader_closed'], G['leader_open'], G['follower_closed'], G['follower_open'], gain))

    L, F = open_arms(cfg, args.leader, args.follower)
    print('leader on %s, follower on %s' % (L.port, F.port))
    try:
        lim = F.limits()
    except BusError as e:
        print('!! cannot read the follower servos (%s). Is the follower power switch on?' % e, file=sys.stderr)
        sys.exit(2)
    print('follower limits:', dict(zip(NAMES, lim)), '| multi-turn: %s | active: %s' % (MT or 'none', active))
    nolim = [NAMES[i] for i in act_idx if lim[i][0] == 0 and lim[i][1] == 0 and not multi[i]]
    if nolim:
        print('!! follower %s has both angle limits set to 0 (multi-turn mode) but is not listed in teleop.multiturn_joints. Teleop will not'
              ' drive a joint like that: a goal could spin it round. Restore the limits first (python -m so101 restore-snapshot).' % nolim, file=sys.stderr)
        sys.exit(2)

    def to_follower(i, v):
        """Leader count -> follower count for joint i (sign flip, gripper endpoint map), not clamped."""
        if i == 5 and gain:
            return G['follower_closed'] + (v - G['leader_closed']) * gain
        return v if signs[i] == 1 else 4096 - v

    def target(u):
        """Follower goals (clamped to the limits; a multi-turn joint is not clamped here), plus the unclamped values."""
        g = []; raw = []
        for i in range(6):
            v = to_follower(i, u[i])
            raw.append(int(v))
            g.append(int(v) if multi[i] else int(min(max(v, lim[i][0]), lim[i][1])))
        return g, raw

    unwrapped = [None] * 6

    def unwrap(l):
        """Leader readings as a continuous angle: the first reading is taken as is (for a limited joint, a reading in
        the gap between the follower's stops is placed just past the nearer stop), after that each tick adds the
        shortest signed change, so turning on through the 0/4095 wrap keeps counting instead of jumping by 4096."""
        for i in range(6):
            if unwrapped[i] is None:
                v = to_follower(i, l[i]); lo, hi = lim[i]
                if i != 5 and not multi[i] and (v < lo or v > hi):
                    below, above = (lo - v) % 4096, (v - hi) % 4096
                    v = lo - below if below < above else hi + above
                    unwrapped[i] = v if signs[i] == 1 else 4096 - v
                else:
                    unwrapped[i] = l[i]
            else:
                unwrapped[i] += short(l[i] - unwrapped[i])
        return list(unwrapped)

    f_unw = [None] * 6

    def track(f):
        """Follower readings; a multi-turn joint's single-turn reading is unwrapped the same way."""
        for i in range(6):
            if f_unw[i] is None or not multi[i]:
                f_unw[i] = f[i]
            else:
                f_unw[i] += short(f[i] - f_unw[i])
        return list(f_unw)

    def rd(arm, what='pos'):
        err = None
        for _ in range(3):
            try:
                return arm.positions() if what == 'pos' else arm.loads()
            except BusError as e:
                err = e
                time.sleep(0.01)
        raise BusError('%s arm: %s' % (arm.role, err))

    kturn = [0] * 6          # servo turn counter per multi-turn joint: servo goal = kturn*4096 + software goal
    orig_tl = {}
    mt_on = False

    def send_goals(vals):
        F.bus.sync_write(act_ids, 'Goal_Position', [enc_pos(vals[i] + kturn[i] * 4096) if multi[i] else int(vals[i]) for i in act_idx])

    def multiturn_restore():
        for i in act_idx:
            if not multi[i]:
                continue
            sid = IDS[i]; bus = F.bus
            lo, hi = cfg['follower']['limits_counts'].get(NAMES[i], [1, 4094])
            if (lo, hi) == (0, 0):
                lo, hi = 1, 4094
            for _ in range(3):
                try:
                    bus.write(sid, 'Torque_Enable', 0)
                    bus.write_eeprom(sid, 'Min_Angle_Limit', lo); bus.write_eeprom(sid, 'Max_Angle_Limit', hi)
                    if i in orig_tl:
                        bus.write(sid, 'Torque_Limit', orig_tl[i])
                    print('[%s] back to single-turn limits %d-%d' % (NAMES[i], lo, hi), flush=True)
                    break
                except BusError:
                    time.sleep(0.2)
            else:
                print('!! %s: could NOT restore its angle limits (left at 0/0 = multi-turn mode). Run: python -m so101 restore-snapshot' % NAMES[i], file=sys.stderr)

    def multiturn_enable():
        """Put each multi-turn joint in multi-turn mode and find its turn counter with a gentle probe."""
        nonlocal mt_on
        for i in act_idx:
            if not multi[i]:
                continue
            sid = IDS[i]; bus = F.bus
            bus.write(sid, 'Torque_Enable', 0)
            if bus.read(sid, 'Mode') != 0:
                bus.write_eeprom(sid, 'Mode', 0)
            if lim[i] != (0, 0):
                bus.write_eeprom(sid, 'Min_Angle_Limit', 0); bus.write_eeprom(sid, 'Max_Angle_Limit', 0)
            mt_on = True
            orig_tl[i] = bus.read(sid, 'Torque_Limit')
            bus.write(sid, 'Torque_Limit', probe_torque); bus.write(sid, 'Acceleration', 10); bus.write(sid, 'Goal_Speed', 100)
            found = None
            for k in (0, 1, -1, 2, -2):
                p = dec_pos(bus.read(sid, 'Present_Position'))
                bus.write(sid, 'Goal_Position', enc_pos(k * 4096 + p))
                bus.write(sid, 'Torque_Enable', 1)
                t0 = time.time(); moved = 0; load = 0; pushed = False
                while time.time() - t0 < probe_time:
                    time.sleep(0.02)
                    q = dec_pos(bus.read(sid, 'Present_Position')); load = s10(bus.read(sid, 'Present_Load'))
                    moved = short(q - p)
                    if abs(moved) > 10 or abs(load) > 150:
                        pushed = True
                        break
                if not pushed:
                    found = k
                    break
                bus.write(sid, 'Torque_Enable', 0)
                print('[%s] probe %+d turn: servo pushed (moved %+d, load %d) -> not this turn' % (NAMES[i], k, moved, load), flush=True)
                time.sleep(0.3)
            if found is None:
                bus.write(sid, 'Torque_Enable', 0)
                multiturn_restore()
                print('!! %s: could not find the servo turn counter within 2 turns. Switch the FOLLOWER power OFF and ON (that resets it)'
                      ' and start teleop again.' % NAMES[i], file=sys.stderr)
                sys.exit(4)
            kturn[i] = found
            bus.write(sid, 'Torque_Limit', orig_tl[i])
            print('[%s] multi-turn mode on, servo turn counter %+d, holding at %d' % (NAMES[i], found, dec_pos(bus.read(sid, 'Present_Position'))), flush=True)

    t_end = time.time() + (args.duration if args.duration and args.duration > 0 else 1e12)
    logf = None
    try:
        L.torque(False)
        l = rd(L); f = rd(F); fu = track(f); u = unwrap(l); g, _ = target(u)
        for i in act_idx:
            if multi[i]:   # start in the follower's own turn: the shortest way round to the leader's angle
                g[i] = fu[i] + short(g[i] - fu[i])
                unwrapped[i] = g[i] if signs[i] == 1 else 4096 - g[i]
        start_pos = list(fu)
        print('leader  :', l); print('follower:', f); print('target  :', g)
        print('initial follower error:', [g[i] - fu[i] for i in range(6)])
        if args.dry:
            print('DRY RUN: reading only, nothing moves. Ctrl-C to stop.')
            while time.time() < t_end:
                l = rd(L); f = rd(F); fu = track(f); u = unwrap(l); g, _ = target(u)
                print('L', l, 'unwrapped', u, 'F', fu, 'err', [g[i] - fu[i] for i in range(6)], flush=True)
                time.sleep(0.5)
            return
        big = [n for n, i in zip(active, act_idx) if abs(g[i] - fu[i]) > T['far_abort']]
        if big:
            print('!! the follower is very far from the leader on %s. Move the FOLLOWER by hand closer to the leader pose and try again.' % big)
            sys.exit(3)
        multiturn_enable()
        F.bus.sync_write(act_ids, 'Acceleration', [15] * len(act_ids))
        F.bus.sync_write(act_ids, 'Goal_Speed', [200] * len(act_ids))
        for _ in range(3):
            send_goals(g); time.sleep(0.05)
            F.torque(True, act_ids); time.sleep(0.05)
        print('ramping slowly to the leader pose - keep clear of the follower...', flush=True)
        for _ in range(int(T['ramp_time'] / 0.15)):
            time.sleep(0.15)
            send_goals(g)
            f = rd(F); fu = track(f)
            if max(abs(g[i] - fu[i]) for i in act_idx) < 30:
                break
        f = rd(F); fu = track(f)
        print('after ramp, follower error:', [g[i] - fu[i] for i in range(6)], flush=True)
        F.bus.sync_write(act_ids, 'Acceleration', [accel] * len(act_ids))
        F.bus.sync_write(act_ids, 'Goal_Speed', [speed] * len(act_ids))
        logf, logpath = open_log(args)
        if logf:
            print('tick log:', logpath)
        print('TELEOP LIVE - move the leader arm. Press Ctrl-C to stop.', flush=True)
        t0 = time.time(); k = 0; bad = [0] * 6; paused = [False] * 6; held = [False] * 6; last = list(g); load = [0] * 6
        settle = [None] * 6; slow = [False] * 6; guarded = [False] * 6
        while time.time() < t_end:
            l = rd(L); u = unwrap(l); g, raw = target(u)
            f = rd(F); fu = track(f)
            for i in act_idx:
                lo, hi = lim[i]
                if multi[i]:
                    lo_g, hi_g = start_pos[i] - guard, start_pos[i] + guard
                    if g[i] > hi_g or g[i] < lo_g:
                        g[i] = min(max(g[i], lo_g), hi_g)
                        if not guarded[i]:
                            guarded[i] = True
                            print('!! %s: travel guard - the follower will not go more than %d counts (%.1f turns) from where it started. Turn the leader back.'
                                  % (NAMES[i], guard, guard / 4096.0), flush=True)
                    elif guarded[i]:
                        guarded[i] = False
                        print('[%s] back inside the travel guard -> following again' % NAMES[i], flush=True)
                    if abs(g[i] - fu[i]) > far_stop:
                        g[i] = last[i]
                        if not held[i]:
                            held[i] = True
                            print('!! %s: leader is %d counts away (more than %d). Holding; bring the leader back toward the follower.' % (NAMES[i], raw[i] - fu[i], far_stop), flush=True)
                    elif held[i]:
                        held[i] = False
                        print('[%s] leader is back within reach -> following again' % NAMES[i], flush=True)
                elif raw[i] < lo - 100 or raw[i] > hi + 100:
                    # leader is past a stop of the follower; g[i] is that stop and the follower waits there
                    if not held[i]:
                        held[i] = True; settle[i] = None
                        print('!! %s: leader is past the follower stop (by %d counts). The follower waits at %d until the leader comes back.'
                              % (NAMES[i], (raw[i] - hi) if raw[i] > hi else (lo - raw[i]), g[i]), flush=True)
                    # re-sync: the leader went right through the wedge and is parked at an angle the follower can reach
                    # from its own side.  Once it has been still there for resync_dwell s, re-base one turn and go there.
                    w = raw[i] % 4096
                    if i != 5 and lo <= w <= hi:
                        if settle[i] is None or abs(w - settle[i][1]) > 30:
                            settle[i] = (time.time(), w)
                        elif time.time() - settle[i][0] >= resync_dwell:
                            turns = int(round((w - raw[i]) / 4096.0))
                            unwrapped[i] += turns * 4096 if signs[i] == 1 else -turns * 4096
                            g[i] = w; raw[i] = w; held[i] = False; settle[i] = None; slow[i] = True
                            F.bus.sync_write([IDS[i]], 'Goal_Speed', [resync_speed])
                            print('[%s] leader has settled on the far side (%d) -> re-syncing: follower moves %+d counts at reduced speed'
                                  % (NAMES[i], w, w - last[i]), flush=True)
                    else:
                        settle[i] = None
                elif held[i] and lo <= raw[i] <= hi:
                    held[i] = False; settle[i] = None
                    print('[%s] leader is back in range (%d) -> following again' % (NAMES[i], raw[i]), flush=True)
                if slow[i] and abs(g[i] - fu[i]) < 60:
                    slow[i] = False
                    F.bus.sync_write([IDS[i]], 'Goal_Speed', [speed])
                    print('[%s] re-synced, normal speed again' % NAMES[i], flush=True)
                if paused[i]:
                    last[i] = fu[i]
                    if abs(g[i] - fu[i]) < T.get('resume_within', 150):
                        paused[i] = False
                        print('[%s] leader is back close -> following again' % NAMES[i], flush=True)
                else:
                    last[i] = min(max(g[i], last[i] - max_step), last[i] + max_step)
            send_goals(last)
            k += 1
            if logf:
                logf.write('%.3f,' % (time.time() - t0) + ','.join(str(int(x)) for row in (l, u, last, fu, load) for x in row)
                           + ',%s,%s\n' % ('|'.join(NAMES[i] for i in range(6) if held[i] or guarded[i]), '|'.join(NAMES[i] for i in range(6) if paused[i])))
            if k % 5 == 0:
                load = rd(F, 'load')
                for i in act_idx:
                    if NAMES[i] == 'gripper' or paused[i]:
                        continue
                    if abs(load[i]) > T['load_hold']:
                        bad[i] += 1
                        if bad[i] >= 10:
                            paused[i] = True; bad[i] = 0
                            print('!! %s is pushing against something (load %d). Holding it; move the leader %s back toward it to resume.' % (NAMES[i], load[i], NAMES[i]), flush=True)
                    else:
                        bad[i] = 0
            if args.verbose and k % 50 == 0:
                print('t=%4.0fs L=%s U=%s err=%s%s' % (time.time() - t0, l, [int(x) for x in u], [last[i] - fu[i] for i in range(6)],
                      ' paused=' + ','.join(NAMES[i] for i in range(6) if paused[i]) if any(paused) else ''), flush=True)
            time.sleep(0.015)
    except KeyboardInterrupt:
        print('\nstopping')
    finally:
        try:
            if logf:
                logf.close()
        except Exception:
            pass
        try:
            n = int(T.get('release_countdown', 3))
            if not args.dry and n > 0:
                print('HOLD THE FOLLOWER ARM - releasing its motors in %d s' % n, flush=True)
                for s in range(n, 0, -1):
                    print('  %d' % s, flush=True); time.sleep(1)
            F.torque(False)
            print('follower torque OFF - the arm is limp now')
        except Exception as e:
            print('could not release torque cleanly:', e)
        if mt_on:
            try:
                multiturn_restore()
            except Exception as e:
                print('!! could not restore the roll limits (%s). Run: python -m so101 restore-snapshot' % e, file=sys.stderr)
        L.close(); F.close()

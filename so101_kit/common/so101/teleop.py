"""1:1 leader -> follower teleop for the servo-matched SO-101 arms.

Both arms were calibrated by the owner so that the same physical pose reads the same count on every joint
(offsets stored in the servos' EEPROM).  Each tick: follower goal = leader reading (clamped to the follower's
EEPROM limits, gripper through the endpoint map), slewed by at most --max-step counts, sent as one sync write.
Start-up: the follower ramps slowly to the leader's pose.  An overloaded joint stops pushing and holds until the
leader comes back close to it.  Ctrl-C: hold, count down, then release torque.
"""
import sys
import time
from .arms import NAMES, IDS, open_arms
from .feetech import BusError


def run(cfg, args):
    T = cfg['teleop']
    speed = T['speed'] if args.speed is None else args.speed
    accel = T['accel'] if args.accel is None else args.accel
    max_step = T['max_step'] if args.max_step is None else args.max_step
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
    print('follower limits:', dict(zip(NAMES, lim)), '| active:', active)

    def target(l):
        g = []
        for i in range(6):
            v = l[i] if signs[i] == 1 else 4096 - l[i]
            if i == 5 and gain:
                v = G['follower_closed'] + (l[i] - G['leader_closed']) * gain
            g.append(int(min(max(v, lim[i][0]), lim[i][1])))
        return g

    def rd(arm, what='pos'):
        for _ in range(3):
            try:
                return arm.positions() if what == 'pos' else arm.loads()
            except BusError:
                time.sleep(0.01)
        raise

    t_end = time.time() + (args.duration if args.duration and args.duration > 0 else 1e12)
    try:
        L.torque(False)
        l = rd(L); f = rd(F); g = target(l)
        print('leader  :', l); print('follower:', f); print('target  :', g)
        print('initial follower error:', [gi - fi for gi, fi in zip(g, f)])
        if args.dry:
            print('DRY RUN: reading only, nothing moves. Ctrl-C to stop.')
            while time.time() < t_end:
                l = rd(L); f = rd(F); g = target(l)
                print('L', l, 'F', f, 'err', [gi - fi for gi, fi in zip(g, f)], flush=True)
                time.sleep(0.5)
            return
        big = [n for n, i in zip(active, act_idx) if abs(g[i] - f[i]) > T['far_abort']]
        if big:
            print('!! the follower is very far from the leader on %s. Move the FOLLOWER by hand closer to the leader pose and try again.' % big)
            sys.exit(3)
        F.bus.sync_write(act_ids, 'Acceleration', [15] * len(act_ids))
        F.bus.sync_write(act_ids, 'Goal_Speed', [200] * len(act_ids))
        for _ in range(3):
            F.bus.sync_write(act_ids, 'Goal_Position', [g[i] for i in act_idx]); time.sleep(0.05)
            F.torque(True, act_ids); time.sleep(0.05)
        print('ramping slowly to the leader pose - keep clear of the follower...', flush=True)
        for _ in range(int(T['ramp_time'] / 0.15)):
            time.sleep(0.15)
            F.bus.sync_write(act_ids, 'Goal_Position', [g[i] for i in act_idx])
            f = rd(F)
            if max(abs(g[i] - f[i]) for i in act_idx) < 30:
                break
        f = rd(F)
        print('after ramp, follower error:', [g[i] - f[i] for i in range(6)], flush=True)
        F.bus.sync_write(act_ids, 'Acceleration', [accel] * len(act_ids))
        F.bus.sync_write(act_ids, 'Goal_Speed', [speed] * len(act_ids))
        print('TELEOP LIVE - move the leader arm. Press Ctrl-C to stop.', flush=True)
        t0 = time.time(); k = 0; bad = [0] * 6; paused = [False] * 6; last = list(g)
        while time.time() < t_end:
            l = rd(L); g = target(l)
            for i in act_idx:
                if paused[i]:
                    last[i] = f[i]
                    if abs(g[i] - f[i]) < T.get('resume_within', 150):
                        paused[i] = False
                        print('[%s] leader is back close -> following again' % NAMES[i], flush=True)
                else:
                    last[i] = min(max(g[i], last[i] - max_step), last[i] + max_step)
            F.bus.sync_write(act_ids, 'Goal_Position', [last[i] for i in act_idx])
            k += 1
            if k % 5 == 0:
                load = rd(F, 'load'); f = rd(F)
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
                print('t=%4.0fs L=%s err=%s%s' % (time.time() - t0, l, [last[i] - f[i] for i in range(6)],
                      ' paused=' + ','.join(NAMES[i] for i in range(6) if paused[i]) if any(paused) else ''), flush=True)
            time.sleep(0.015)
    except KeyboardInterrupt:
        print('\nstopping')
    finally:
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
        L.close(); F.close()

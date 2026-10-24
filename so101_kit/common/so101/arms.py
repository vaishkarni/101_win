"""Find the two SO-101 bus adapters and open them as leader / follower.

Identification order:
  1. --leader / --follower command-line ports (or SO101_LEADER / SO101_FOLLOWER env vars)
  2. USB adapter serial numbers stored in arm_config.json (the normal case)
  3. if exactly two Feetech adapters are found and the serials are unknown: the bus with the
     higher servo voltage is the follower (leader 5-7.4 V, follower 12 V) - a warning is printed
"""
import json
import os
import sys
import time
from serial.tools import list_ports
from .feetech import FeetechBus, BusError, STS3215_MODEL, dec_offset, dec_pos

NAMES = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']
IDS = [1, 2, 3, 4, 5, 6]
ADAPTER_VID_PID = {(0x1A86, 0x55D3), (0x1A86, 0x7523), (0x1A86, 0x55D4)}   # WCH CH343 / CH340 USB-serial (Waveshare bus servo adapter)

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get('SO101_CONFIG', os.path.join(os.path.dirname(HERE), 'arm_config.json'))


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg):
    tmp = CONFIG_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(cfg, f, indent=1)
    os.replace(tmp, CONFIG_PATH)
    print('saved', CONFIG_PATH)


def feetech_ports():
    """All serial ports that look like a Feetech/Waveshare bus adapter: list of (device, serial_number)."""
    out = []
    for p in sorted(list_ports.comports(), key=lambda p: p.device):
        if (p.vid, p.pid) in ADAPTER_VID_PID or (p.vid == 0x1A86):
            out.append((p.device, (p.serial_number or '').strip()))
    return out


def open_bus(port):
    b = FeetechBus(port)
    return b


def bus_alive(bus):
    """How many of the six servos answer on this bus."""
    return sum(1 for i in IDS if bus.ping(i) is not None)


def bus_voltage(bus):
    for i in IDS:
        try:
            return bus.read(i, 'Present_Voltage') / 10.0
        except BusError:
            continue
    return None


def resolve_ports(cfg, leader=None, follower=None, quiet=False):
    """Return (leader_port, follower_port) or raise SystemExit with a plain-language message."""
    leader = leader or os.environ.get('SO101_LEADER')
    follower = follower or os.environ.get('SO101_FOLLOWER')
    if leader and follower:
        return leader, follower
    found = feetech_ports()
    want_l, want_f = cfg['leader']['adapter_serial'], cfg['follower']['adapter_serial']
    by_sn = {sn: dev for dev, sn in found if sn}
    lp = leader or by_sn.get(want_l)
    fp = follower or by_sn.get(want_f)
    if lp and fp:
        return lp, fp
    if not found:
        fail('No arm USB adapters were found.',
             'Check that BOTH arm USB cables are plugged into this computer,',
             'then run this again.  (On Linux, run setup.sh once if you have not yet.)')
    if len(found) == 1:
        dev, sn = found[0]
        which = 'leader' if sn == want_l else ('follower' if sn == want_f else 'unknown')
        fail('Only ONE arm USB adapter was found (%s, serial %s = %s arm).' % (dev, sn or '?', which),
             'Plug in the other arm as well and run this again.')
    # two or more adapters but serials do not match the config: decide by voltage
    if not quiet:
        print('! adapter serial numbers do not match arm_config.json (found %s). Identifying by bus voltage...'
              % ', '.join('%s=%s' % (d, s or '?') for d, s in found))
    volts = []
    for dev, sn in found:
        try:
            b = FeetechBus(dev)
            n = bus_alive(b)
            v = bus_voltage(b) if n else None
            b.close()
            volts.append((dev, sn, n, v))
        except Exception as e:
            volts.append((dev, sn, 0, None))
    live = [x for x in volts if x[2] and x[3] is not None]
    if len(live) != 2:
        fail('Found %d adapters but could not talk to the servos on two of them: %s' % (len(found), volts),
             'Check the arm power switches / power supplies, then run this again.')
    live.sort(key=lambda x: x[3])
    (ldev, lsn, _, lv), (fdev, fsn, _, fv) = live
    if abs(fv - lv) < 1.5:
        fail('Both arms report nearly the same voltage (%.1f V and %.1f V) so I cannot tell leader from follower.' % (lv, fv),
             'Tell the owner, or start with explicit ports: --leader PORT --follower PORT')
    print('! leader = %s (%.1f V, serial %s), follower = %s (%.1f V, serial %s).' % (ldev, lv, lsn or '?', fdev, fv, fsn or '?'))
    print('  If this is right, tell the owner to update arm_config.json, or run: python3 -m so101 adopt-serials')
    return (leader or ldev), (follower or fdev)


def fail(*lines):
    print('\n' + '\n'.join('!! ' + l for l in lines) + '\n', file=sys.stderr)
    sys.exit(2)


class Arm:
    """One arm: a bus plus the six joints, with convenience reads."""

    def __init__(self, role, port, cfg):
        self.role, self.port, self.cfg = role, port, cfg
        self.bus = FeetechBus(port)

    def close(self):
        self.bus.close()

    def positions(self):
        return [dec_pos(v) for v in self.bus.sync_read(IDS, 'Present_Position')]

    def loads(self):
        from .feetech import s10
        return [s10(v) for v in self.bus.sync_read(IDS, 'Present_Load')]

    def limits(self):
        lo = self.bus.sync_read(IDS, 'Min_Angle_Limit')
        hi = self.bus.sync_read(IDS, 'Max_Angle_Limit')
        return list(zip([int(v) for v in lo], [int(v) for v in hi]))

    def torque(self, on, ids=IDS):
        self.bus.sync_write(ids, 'Torque_Enable', [1 if on else 0] * len(ids))

    def eeprom_snapshot(self):
        snap = {}
        for n, i in zip(NAMES, IDS):
            snap[n] = {'offset': dec_offset(self.bus.read(i, 'Offset')),
                       'min': self.bus.read(i, 'Min_Angle_Limit'),
                       'max': self.bus.read(i, 'Max_Angle_Limit')}
            time.sleep(0.01)
        return snap

    def health(self):
        rows = []
        for n, i in zip(NAMES, IDS):
            if self.bus.ping(i) is None:
                rows.append({'joint': n, 'id': i, 'ok': False})
                continue
            r = lambda k: self.bus.read(i, k)
            rows.append({'joint': n, 'id': i, 'ok': True, 'model': r('Model_Number'), 'pos': r('Present_Position'),
                         'v': r('Present_Voltage') / 10.0, 'temp': r('Present_Temperature'), 'status': r('Status'),
                         'torque': r('Torque_Enable'), 'min': r('Min_Angle_Limit'), 'max': r('Max_Angle_Limit'), 'mode': r('Mode'),
                         'offset': dec_offset(r('Offset')), 'vmin': r('Min_Voltage_Limit') / 10.0, 'vmax': r('Max_Voltage_Limit') / 10.0})
        return rows


def open_arms(cfg, leader=None, follower=None, need_follower=True):
    lp, fp = resolve_ports(cfg, leader, follower)
    L = Arm('leader', lp, cfg)
    F = Arm('follower', fp, cfg) if need_follower else None
    return L, F

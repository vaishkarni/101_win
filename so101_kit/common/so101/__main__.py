"""python3 -m so101 <command> [options]   - SO-101 leader/follower teleop kit."""
import argparse
import sys
from . import __version__
from .arms import load_config, CONFIG_PATH, NAMES as NAMES_ALL


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m so101', description='SO-101 leader/follower teleop kit v%s (config: %s)' % (__version__, CONFIG_PATH))
    ap.add_argument('--leader', help='serial port of the leader arm (normally found automatically)')
    ap.add_argument('--follower', help='serial port of the follower arm (normally found automatically)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check', help='health check of both arms, nothing moves'); p.add_argument('-v', '--verbose', action='store_true')
    p = sub.add_parser('teleop', help='leader drives the follower until Ctrl-C')
    p.add_argument('--duration', type=float, default=0, help='seconds, 0 = until Ctrl-C')
    p.add_argument('--joints', default='', help='comma list to drive a subset, e.g. gripper,wrist_flex')
    p.add_argument('--dry', action='store_true', help='read only, print leader/follower/error, nothing moves')
    p.add_argument('--speed', type=int); p.add_argument('--accel', type=int); p.add_argument('--max-step', type=int)
    p.add_argument('-v', '--verbose', action='store_true')
    p.add_argument('--log', help='per-tick CSV log file (default: common/logs/teleop_<date>.csv, "-" = none)')
    p = sub.add_parser('ports', help='list the USB arm adapters that are plugged in')
    # owner tools
    sub.add_parser('snapshot', help='OWNER: store the servos\' calibration (offsets+limits) in arm_config.json')
    sub.add_parser('restore-snapshot', help='write the stored calibration back into the servos')
    p = sub.add_parser('backup', help='OWNER: dump servo calibration to a json file'); p.add_argument('file')
    p = sub.add_parser('restore', help='OWNER: restore servo calibration from a backup json'); p.add_argument('file')
    p = sub.add_parser('rangecal', help='OWNER: hard-stop calibration of one arm'); p.add_argument('arm', choices=['leader', 'follower']); p.add_argument('seconds', nargs='?', type=float, default=75)
    sub.add_parser('compare', help='OWNER: compare leader/follower travel from the last rangecal')
    sub.add_parser('matchcheck', help='OWNER: leader vs follower readings at a hand-matched pose')
    sub.add_parser('gripper', help='OWNER: measure follower gripper stops at low torque')
    p = sub.add_parser('shift', help='OWNER: shift one joint reading by -DELTA'); p.add_argument('arm', choices=['leader', 'follower']); p.add_argument('joint'); p.add_argument('delta', type=int)
    sub.add_parser('setlimits', help='OWNER: write follower limits from arm_config.json')
    p = sub.add_parser('setmode', help='OWNER: set a follower servo mode (0 position, 1 wheel); teleop restores 0 itself on exit'); p.add_argument('joint', choices=NAMES_ALL); p.add_argument('mode', type=int, choices=[0, 1])
    sub.add_parser('adopt-serials', help='store the connected adapters\' serial numbers in arm_config.json')
    a = ap.parse_args(argv)
    cfg = load_config()
    if a.cmd == 'check':
        from . import check; check.run(cfg, a)
    elif a.cmd == 'teleop':
        from . import teleop; teleop.run(cfg, a)
    elif a.cmd == 'ports':
        from .arms import feetech_ports
        found = feetech_ports()
        print('\n'.join('%s  serial=%s' % (d, s or '?') for d, s in found) or 'no Feetech USB adapters found')
    else:
        from . import calibrate as c
        {'snapshot': c.cmd_snapshot, 'restore-snapshot': c.cmd_restore_snapshot, 'backup': c.cmd_backup, 'restore': c.cmd_restore,
         'rangecal': c.cmd_rangecal, 'compare': c.cmd_compare, 'matchcheck': c.cmd_check, 'gripper': c.cmd_gripper,
         'shift': c.cmd_shift, 'setlimits': c.cmd_setlimits, 'adopt-serials': c.cmd_adopt_serials, 'setmode': c.cmd_setmode}[a.cmd](cfg, a)


if __name__ == '__main__':
    main()

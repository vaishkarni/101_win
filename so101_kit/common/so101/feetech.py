"""Minimal Feetech STS3215 bus driver (pyserial only, no LeRobot).

Wire protocol (SCServo): FF FF ID LEN INSTR PARAMS CHECKSUM, LEN = len(PARAMS)+2,
CHECKSUM = ~(ID+LEN+INSTR+sum(PARAMS)) & 0xFF.  2-byte values are little-endian on the STS series.
Registers that matter for the SO-101 kit are listed in REG (address, size).
"""
import time
import serial

BROADCAST = 0xFE
PING, READ, WRITE, SYNC_READ, SYNC_WRITE = 0x01, 0x02, 0x03, 0x82, 0x83
STS3215_MODEL = 777

REG = {   # name: (address, bytes)
    'Model_Number': (3, 2), 'ID': (5, 1), 'Baud_Rate': (6, 1),
    'Min_Angle_Limit': (9, 2), 'Max_Angle_Limit': (11, 2),
    'Max_Temperature_Limit': (13, 1), 'Max_Voltage_Limit': (14, 1), 'Min_Voltage_Limit': (15, 1),
    'Max_Torque_Limit': (16, 2), 'Offset': (31, 2), 'Mode': (33, 1),
    'Torque_Enable': (40, 1), 'Acceleration': (41, 1), 'Goal_Position': (42, 2), 'Goal_Time': (44, 2),
    'Goal_Speed': (46, 2), 'Torque_Limit': (48, 2), 'Lock': (55, 1),
    'Present_Position': (56, 2), 'Present_Speed': (58, 2), 'Present_Load': (60, 2),
    'Present_Voltage': (62, 1), 'Present_Temperature': (63, 1), 'Status': (65, 1), 'Moving': (66, 1),
    'Present_Current': (69, 2),
}
STATUS_FLAGS = {0: 'VOLTAGE', 1: 'SENSOR', 2: 'TEMPERATURE', 3: 'CURRENT', 5: 'OVERLOAD'}


class BusError(Exception):
    pass


def s10(v):
    """Present_Load / Present_Speed: 10-bit magnitude, direction in bit 10."""
    v = int(v)
    return -(v & 0x3FF) if v & 0x400 else (v & 0x3FF)


def dec_offset(v):
    """Offset register: 11-bit magnitude, sign in bit 11."""
    v = int(v)
    return -(v & 0x7FF) if v & 0x800 else v


def enc_offset(v):
    v = int(v)
    return (0x800 | (-v)) if v < 0 else v


def dec_pos(v):
    """Present_Position / Goal_Position: 15-bit magnitude, sign in bit 15 (only seen outside 0..4095 when a servo
    has both angle limits set to 0, i.e. a free-turning joint)."""
    v = int(v)
    return -(v & 0x7FFF) if v & 0x8000 else v


def enc_pos(v):
    v = int(v)
    return (0x8000 | min(-v, 0x7FFF)) if v < 0 else min(v, 0x7FFF)


def _checksum(body):
    return (~sum(body)) & 0xFF


class FeetechBus:
    """One USB bus adapter with STS3215 servos on it."""

    def __init__(self, port, baud=1_000_000, timeout=0.03, retries=4):
        self.port_name = port
        self.retries = retries
        self.ser = serial.Serial(port, baudrate=baud, timeout=timeout, write_timeout=0.2)
        self.ser.reset_input_buffer()

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    # ---- raw packets -------------------------------------------------------------------------
    def _send(self, sid, instr, params=()):
        params = bytes(params)
        body = bytes([sid, len(params) + 2, instr]) + params
        pkt = b'\xff\xff' + body + bytes([_checksum(body)])
        self.ser.reset_input_buffer()
        self.ser.write(pkt)
        self.ser.flush()

    def _recv(self, expect_params):
        """Read one status packet: FF FF ID LEN ERR PARAMS CHK.  Returns (id, err, params)."""
        n = 6 + expect_params
        buf = self.ser.read(n)
        # resync on the FF FF header if there is garbage in front of it
        start = buf.find(b'\xff\xff')
        if start < 0:
            raise BusError('no response')
        if start > 0:
            buf = buf[start:] + self.ser.read(start)
        if len(buf) < 6:
            raise BusError('short response')
        sid, ln, err = buf[2], buf[3], buf[4]
        need = 4 + ln
        if len(buf) < need:
            buf += self.ser.read(need - len(buf))
            if len(buf) < need:
                raise BusError('truncated response')
        body = buf[2:need - 1]
        if _checksum(body) != buf[need - 1]:
            raise BusError('bad checksum')
        return sid, err, bytes(buf[5:need - 1])

    def _txrx(self, sid, instr, params, expect_params):
        last = None
        for _ in range(self.retries):
            try:
                self._send(sid, instr, params)
                rid, err, data = self._recv(expect_params)
                if rid != sid:
                    raise BusError('reply from id %d, expected %d' % (rid, sid))
                if len(data) != expect_params:
                    raise BusError('expected %d data bytes, got %d' % (expect_params, len(data)))
                return err, data
            except BusError as e:
                last = e
                time.sleep(0.005)
        raise BusError('id %d: %s (after %d tries)' % (sid, last, self.retries))

    # ---- basic ops -------------------------------------------------------------------------
    def ping(self, sid):
        """Returns the error byte (0 = fine) or None when the servo does not answer."""
        try:
            err, _ = self._txrx(sid, PING, (), 0)
            return err
        except BusError:
            return None

    def read(self, sid, name):
        addr, size = REG[name]
        _, data = self._txrx(sid, READ, (addr, size), size)
        return int.from_bytes(data, 'little')

    def write(self, sid, name, value):
        addr, size = REG[name]
        data = int(value).to_bytes(size, 'little', signed=False)
        self._txrx(sid, WRITE, bytes([addr]) + data, 0)

    def write_eeprom(self, sid, name, value):
        """Unlock, write, re-lock, read back.  Raises if the read-back differs."""
        self.write(sid, 'Lock', 0)
        time.sleep(0.01)
        try:
            self.write(sid, name, value)
            time.sleep(0.02)
        finally:
            self.write(sid, 'Lock', 1)
            time.sleep(0.01)
        back = self.read(sid, name)
        if back != int(value):
            raise BusError('id %d %s: wrote %d, read back %d' % (sid, name, value, back))
        return back

    # ---- group ops ---------------------------------------------------------------------------
    def sync_write(self, ids, name, values):
        addr, size = REG[name]
        params = bytes([addr, size])
        for sid, v in zip(ids, values):
            params += bytes([sid]) + int(v).to_bytes(size, 'little', signed=False)
        for _ in range(2):
            try:
                self._send(BROADCAST, SYNC_WRITE, params)
                return
            except serial.SerialException:
                time.sleep(0.005)

    def sync_read(self, ids, name):
        """Read one register from several servos; falls back to single reads for missing answers."""
        addr, size = REG[name]
        out = {}
        try:
            self._send(BROADCAST, SYNC_READ, bytes([addr, size]) + bytes(ids))
            for _ in ids:
                rid, err, data = self._recv(size)
                if len(data) == size:
                    out[rid] = int.from_bytes(data, 'little')
        except BusError:
            pass
        for sid in ids:
            if sid not in out:
                out[sid] = self.read(sid, name)
        return [out[sid] for sid in ids]

    def read_all(self, ids, name):
        return self.sync_read(ids, name)

    def torque(self, ids, on):
        self.sync_write(ids, 'Torque_Enable', [1 if on else 0] * len(ids))

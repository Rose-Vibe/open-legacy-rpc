"""Minimal pcap/pcapng reader using only the standard library."""
import struct
import subprocess
import tempfile
import os


def read_pcap(path):
    """Yield (timestamp_sec, src_port, dst_port, udp_payload) for each UDP packet.

    Supports both pcap and pcapng formats. For pcapng, uses tshark to extract
    fields if available, otherwise converts to pcap.
    """
    with open(path, 'rb') as f:
        magic = f.read(4)

    if magic in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4'):
        yield from _read_pcap_legacy(path, magic)
    elif magic == b'\x0a\x0d\x0d\x0a':
        yield from _read_pcapng_via_tshark(path)
    else:
        raise ValueError(f"Not a pcap/pcapng file: {path} (magic: {magic.hex()})")


def _read_pcapng_via_tshark(path):
    """Use tshark to extract UDP payload hex from pcapng files."""
    cmd = [
        'tshark', '-r', path,
        '-Y', 'udp',
        '-T', 'fields',
        '-e', 'frame.time_epoch',
        '-e', 'udp.srcport',
        '-e', 'udp.dstport',
        '-e', 'udp.payload',
        '-E', 'separator=|',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # Fallback: convert to pcap
        with tempfile.NamedTemporaryFile(suffix='.pcap', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            subprocess.run(['editcap', '-F', 'pcap', path, tmp_path], check=True,
                          capture_output=True)
            yield from _read_pcap_legacy(tmp_path)
        finally:
            os.unlink(tmp_path)
        return

    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        parts = line.split('|')
        if len(parts) < 4:
            continue
        try:
            ts = float(parts[0])
            src_port = int(parts[1])
            dst_port = int(parts[2])
            hex_data = parts[3].replace(':', '')
            if not hex_data:
                continue
            payload = bytes.fromhex(hex_data)
            yield ts, src_port, dst_port, payload
        except (ValueError, IndexError):
            continue


def _read_pcap_legacy(path, magic=None):
    """Read legacy pcap format."""
    with open(path, 'rb') as f:
        if magic is None:
            magic = f.read(4)
        else:
            f.read(4)  # skip past magic already read by caller
        if magic == b'\xd4\xc3\xb2\xa1':
            endian = '<'
        elif magic == b'\xa1\xb2\xc3\xd4':
            endian = '>'
        else:
            raise ValueError(f"Not a pcap file: {path}")

        ver_major, ver_minor, tz, sigfigs, snaplen, linktype = struct.unpack(
            endian + 'HHiIII', f.read(20))

        while True:
            hdr = f.read(16)
            if len(hdr) < 16:
                break
            ts_sec, ts_usec, incl_len, orig_len = struct.unpack(endian + 'IIII', hdr)
            data = f.read(incl_len)
            if len(data) < incl_len:
                break

            ts = ts_sec + ts_usec / 1_000_000
            payload = _extract_udp_payload(data, linktype)
            if payload is not None:
                yield ts, payload[0], payload[1], payload[2]


def _extract_udp_payload(data, linktype):
    """Extract (src_port, dst_port, udp_payload) from a link-layer frame."""
    if linktype == 0:  # LINKTYPE_NULL (loopback)
        if len(data) < 4:
            return None
        af = struct.unpack('<I', data[:4])[0]
        if af != 2:  # AF_INET
            return None
        ip_data = data[4:]
    elif linktype == 1:  # LINKTYPE_ETHERNET
        if len(data) < 14:
            return None
        ethertype = struct.unpack('!H', data[12:14])[0]
        if ethertype != 0x0800:
            return None
        ip_data = data[14:]
    elif linktype == 113:  # LINKTYPE_LINUX_SLL
        if len(data) < 16:
            return None
        proto = struct.unpack('!H', data[14:16])[0]
        if proto != 0x0800:
            return None
        ip_data = data[16:]
    elif linktype == 276:  # LINKTYPE_LINUX_SLL2
        if len(data) < 20:
            return None
        proto = struct.unpack('!H', data[:2])[0]
        if proto != 0x0800:
            return None
        ip_data = data[20:]
    else:
        return None

    if len(ip_data) < 20:
        return None
    ihl = (ip_data[0] & 0x0F) * 4
    proto = ip_data[9]
    if proto != 17:  # UDP
        return None

    udp_data = ip_data[ihl:]
    if len(udp_data) < 8:
        return None
    src_port, dst_port, udp_len = struct.unpack('!HHH', udp_data[:6])
    payload = udp_data[8:8 + udp_len - 8]

    return src_port, dst_port, payload

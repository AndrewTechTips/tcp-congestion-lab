"""Packet format and checksum.

Header (13 bytes, network byte order):
  type (1) | seq (4) | ack (4) | length (2) | checksum (2)
"""

import struct

DATA, ACK, SYN, SYNACK, FIN, FINACK = range(6)
TYPE_NAMES = {DATA: "DATA", ACK: "ACK", SYN: "SYN", SYNACK: "SYN-ACK",
              FIN: "FIN", FINACK: "FIN-ACK"}

HEADER = struct.Struct("!BIIHH")
HEADER_SIZE = HEADER.size
MAX_PAYLOAD = 1000  # small enough that IP never has to fragment


def checksum(data: bytes) -> int:
    # the Internet checksum (RFC 1071): one's complement sum of 16-bit words
    if len(data) % 2:
        data += b"\x00"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF


def build(ptype, seq=0, ack=0, payload=b""):
    hdr = HEADER.pack(ptype, seq, ack, len(payload), 0)
    cs = checksum(hdr + payload)
    return HEADER.pack(ptype, seq, ack, len(payload), cs) + payload


def parse(raw: bytes):
    """Returns (type, seq, ack, payload), or None if the packet is damaged."""
    if len(raw) < HEADER_SIZE:
        return None
    ptype, seq, ack, length, cs = HEADER.unpack_from(raw)
    payload = raw[HEADER_SIZE:]
    if length != len(payload):
        return None
    # recompute with the checksum field zeroed
    zeroed = HEADER.pack(ptype, seq, ack, length, 0) + payload
    if checksum(zeroed) != cs:
        return None
    return ptype, seq, ack, payload

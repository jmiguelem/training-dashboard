"""Generate the PWA icons (no dependencies). Run: python3 scripts/make_icons.py"""
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "frontend" / "public"
BG, RING, DOT = (18, 18, 17), (57, 135, 229), (235, 104, 52)


def png(size: int) -> bytes:
    cx = cy = (size - 1) / 2
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / size
            if 0.27 <= d <= 0.36:
                px = RING
            elif d <= 0.10:
                px = DOT
            else:
                px = BG
            row += bytes(px)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(
        b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
    (OUT / name).write_bytes(png(size))
    print("wrote", name)

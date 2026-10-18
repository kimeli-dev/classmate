"""Export the app icon to assets/ as PNGs and a multi-size .ico (for PyInstaller / shortcuts).

Usage: python tools/export_icon.py
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QGuiApplication

from sessionly.ui.icon import icon_pixmap

SIZES = [16, 20, 24, 32, 48, 64, 128, 256]


def png_bytes(size: int) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    icon_pixmap(size).save(buf, "PNG")
    return bytes(data)


def write_ico(path: Path) -> None:
    images = [(s, png_bytes(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        blobs += blob
    path.write_bytes(header + entries + blobs)


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841 - needed for QPixmap
    out = Path(__file__).resolve().parent.parent / "assets"
    out.mkdir(exist_ok=True)
    write_ico(out / "sessionly.ico")
    icon_pixmap(512).save(str(out / "sessionly.png"))
    print(f"Wrote {out / 'sessionly.ico'} and sessionly.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

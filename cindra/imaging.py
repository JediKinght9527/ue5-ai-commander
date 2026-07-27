"""imaging —— 纯 stdlib 的 PNG 读写工具。

Cindra 坚持零第三方依赖 (requirements 只有 anthropic SDK), 所以自己写一个
最小 PNG 编码器: 每行 filter=0, zlib 压缩, 足够 mock 视口渲染用。
真 UE 截图是引擎产的标准 PNG, 这里只需要读尺寸和 base64。

自检: python3 -m cindra.imaging
"""
from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

# Anthropic API 单图上限 5MB; 留余量
MAX_IMAGE_BYTES = 4_500_000

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(path: str | Path, width: int, height: int,
              rgb_rows: list[bytes]) -> None:
    """写 8-bit RGB PNG。rgb_rows: 每行 width*3 字节。"""
    if len(rgb_rows) != height:
        raise ValueError(f"expected {height} rows, got {len(rgb_rows)}")
    raw = b"".join(b"\x00" + row for row in rgb_rows)  # 每行 filter=0
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    payload = (_PNG_SIG + _chunk(b"IHDR", ihdr)
               + _chunk(b"IDAT", zlib.compress(raw, 6))
               + _chunk(b"IEND", b""))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(payload)


def read_png_size(path: str | Path) -> tuple[int, int]:
    """读 PNG 宽高 (IHDR)。"""
    data = Path(path).read_bytes()
    if data[:8] != _PNG_SIG or data[12:16] != b"IHDR":
        raise ValueError(f"not a PNG: {path}")
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def b64_file(path: str | Path, max_bytes: int = MAX_IMAGE_BYTES) -> str:
    """文件 -> base64 字符串, 超过 API 上限直接报错 (别把请求打爆)。"""
    data = Path(path).read_bytes()
    if len(data) > max_bytes:
        raise ValueError(
            f"image too large: {len(data)} bytes > {max_bytes} ({path}); "
            "降低截图分辨率 (默认 1280x720 不该超)")
    return base64.standard_b64encode(data).decode("ascii")


def _selfcheck() -> None:
    import tempfile

    ok = 0
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.png"
        rows = [bytes([255, 0, 0] * 4), bytes([0, 255, 0] * 4),
                bytes([0, 0, 255] * 4), bytes([9, 9, 9] * 4)]
        write_png(p, 4, 4, rows)
        first = p.read_bytes()
        write_png(p, 4, 4, rows)
        assert p.read_bytes() == first, "写入不确定性!"
        ok += 1
        print("[1/3] write_png 确定性 ✓")

        assert read_png_size(p) == (4, 4)
        ok += 1
        print("[2/3] read_png_size ✓")

        b = b64_file(p)
        assert base64.standard_b64decode(b) == first
        try:
            b64_file(p, max_bytes=10)
            raise AssertionError("应该抛体积超限")
        except ValueError:
            pass
        ok += 1
        print("[3/3] b64_file + 体积守卫 ✓")
    print(f"imaging 自检 {ok}/3 全部通过")


if __name__ == "__main__":
    _selfcheck()

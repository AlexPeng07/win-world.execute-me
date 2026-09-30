"""Grab pixels off the screen with GDI, for measuring what a terminal really drew.

Used by win/calibrate.py: Windows Terminal does not answer cursor-position reports
(ESC [ 6 n), so the only way to learn how wide a glyph is, is to look at the screen.
"""
from __future__ import annotations
import ctypes, struct
from ctypes import wintypes

gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
user32 = ctypes.WinDLL('user32', use_last_error=True)


def _make_dpi_aware():
    """Without this, GetSystemMetrics and BitBlt work in a scaled coordinate space and a
    grab of the 'whole' screen is really a crop of its top-left, so anything painted in
    the lower rows silently vanishes from the measurement."""
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):  # per-monitor v2
            return 'per-monitor-v2'
    except (AttributeError, OSError):
        pass
    try:
        if user32.SetProcessDPIAware():
            return 'system-dpi-aware'
    except (AttributeError, OSError):
        pass
    return 'unaware'


DPI_MODE = _make_dpi_aware()

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
DIB_RGB_COLORS = 0
BI_RGB = 0


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [('biSize', wintypes.DWORD), ('biWidth', ctypes.c_long), ('biHeight', ctypes.c_long),
                ('biPlanes', wintypes.WORD), ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD), ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', ctypes.c_long), ('biYPelsPerMeter', ctypes.c_long),
                ('biClrUsed', wintypes.DWORD), ('biClrImportant', wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wintypes.DWORD * 3)]


def primary_screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def grab(x=0, y=0, width=None, height=None):
    """Copy a screen rectangle into memory; returns (width, height, bytes) as BGRA top-down."""
    if width is None or height is None:
        screen_width, screen_height = primary_screen_size()
        width = width or screen_width
        height = height or screen_height
    desktop = user32.GetDesktopWindow()
    source = user32.GetWindowDC(wintypes.HWND(desktop))
    if not source:
        raise ctypes.WinError(ctypes.get_last_error())
    memory = None
    bitmap = None
    old_bitmap = None
    bits = ctypes.c_void_p()
    try:
        memory = gdi32.CreateCompatibleDC(wintypes.HDC(source))
        info = BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height  # negative means top-down rows
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = BI_RGB
        bitmap = gdi32.CreateDIBSection(wintypes.HDC(memory), ctypes.byref(info), DIB_RGB_COLORS,
                                       ctypes.byref(bits), None, 0)
        if not bitmap:
            raise ctypes.WinError(ctypes.get_last_error())
        old_bitmap = gdi32.SelectObject(wintypes.HDC(memory), ctypes.c_void_p(bitmap))
        raster = gdi32.BitBlt(wintypes.HDC(memory), 0, 0, width, height,
                              wintypes.HDC(source), x, y, SRCCOPY | CAPTUREBLT)
        if not raster:
            raise ctypes.WinError(ctypes.get_last_error())
        data = ctypes.string_at(bits, width * height * 4)
        return width, height, data
    finally:
        if old_bitmap and memory:
            gdi32.SelectObject(wintypes.HDC(memory), ctypes.c_void_p(old_bitmap))
        if bitmap:
            gdi32.DeleteObject(ctypes.c_void_p(bitmap))
        if memory:
            gdi32.DeleteDC(wintypes.HDC(memory))
        user32.ReleaseDC(wintypes.HWND(desktop), wintypes.HDC(source))


def write_bmp(path, width, height, data):
    """Save the grab as an uncompressed 24-bit BMP so any viewer can open the evidence."""
    row_bytes = (width * 3 + 3) // 4 * 4
    pixels = bytearray()
    for y in range(height - 1, -1, -1):  # BMP stores bottom-up
        start = y * width * 4
        for x in range(width):
            offset = start + x * 4
            pixels += data[offset:offset + 3]
        pixels += b'\x00' * (row_bytes - width * 3)
    size = 54 + len(pixels)
    header = struct.pack('<2sIHHI', b'BM', size, 0, 0, 54)
    info = struct.pack('<IiiHHIIiiII', 40, width, height, 1, 24, BI_RGB, len(pixels), 1, 1, 0, 0)
    path = str(path)
    with open(path, 'wb') as handle:
        handle.write(header + info + bytes(pixels))
    return size


def write_png(path, width, height, data):
    """Save the grab as an 8-bit RGB PNG using stdlib zlib, for evidence any viewer opens.

    Byte constants are written as integer lists on purpose: this file has no escape
    sequences, because a backslash in a generated patch is how NULs get into source.
    """
    import array
    import zlib
    raw = bytearray()
    for y in range(height):
        base = y * width * 4
        row = array.array('B', data[base:base + width * 4])
        blue, green, red = row[0::4], row[1::4], row[2::4]
        rgb = bytearray(width * 3)
        rgb[0::3] = red
        rgb[1::3] = green
        rgb[2::3] = blue
        raw.append(0)  # PNG filter type 0 (none) for this scanline
        raw += rgb

    def chunk(kind, payload):
        return (struct.pack('>I', len(payload)) + kind + payload
                + struct.pack('>I', zlib.crc32(kind + payload) & 0xFFFFFFFF))

    signature = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    header = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    body = zlib.compress(bytes(raw), 6)
    png = signature + chunk(b'IHDR', header) + chunk(b'IDAT', body) + chunk(b'IEND', bytes())
    with open(str(path), 'wb') as handle:
        handle.write(png)
    return len(png)

"""Windows console plumbing for the terminal MV.

The POSIX build did three things through termios/tty/select that have to be done with
the console API here: put the terminal in VT mode, ask it how big it is, and hand keys
to the frame loop without the loop ever blocking on a read.
"""
from __future__ import annotations
import ctypes, os, queue, shutil, sys, threading
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
winmm = ctypes.WinDLL('winmm')

STD_INPUT_HANDLE, STD_OUTPUT_HANDLE, STD_ERROR_HANDLE = -10, -11, -12
ENABLE_PROCESSED_OUTPUT = 0x0001
ENABLE_WRAP_AT_EOL_OUTPUT = 0x0002
ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
ENABLE_LINE_INPUT = 0x0002
ENABLE_ECHO_INPUT = 0x0004
ENABLE_INSERT_MODE = 0x0020
ENABLE_QUICK_EDIT_MODE = 0x0040
ENABLE_EXTENDED_FLAGS = 0x0080

kernel32.GetStdHandle.restype = wintypes.HANDLE
kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
kernel32.GetConsoleMode.restype = wintypes.BOOL
kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel32.SetConsoleMode.restype = wintypes.BOOL
kernel32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]


class COORD(ctypes.Structure):
    _fields_ = [('X', ctypes.c_short), ('Y', ctypes.c_short)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [('Left', ctypes.c_short), ('Top', ctypes.c_short),
                ('Right', ctypes.c_short), ('Bottom', ctypes.c_short)]


class SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [('dwSize', COORD), ('dwCursorPosition', COORD), ('wAttributes', wintypes.WORD),
                ('srWindow', SMALL_RECT), ('dwMaximumWindowSize', COORD)]


def std_handle(which):
    handle = kernel32.GetStdHandle(wintypes.DWORD(which))
    if not handle or handle == wintypes.HANDLE(-1).value:
        raise OSError('no console handle for std ' + str(which))
    return handle


def get_mode(which):
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(std_handle(which), ctypes.byref(mode)):
        raise ctypes.WinError(ctypes.get_last_error())
    return mode.value


def set_mode(which, value):
    if not kernel32.SetConsoleMode(std_handle(which), wintypes.DWORD(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return value


class Console:
    """Owns the console modes for one playback session, and puts them back."""

    def __init__(self):
        self.saved = {}
        self.notes = []

    def enter(self):
        output = get_mode(STD_OUTPUT_HANDLE)
        self.saved['output'] = output
        # VT processing is what makes the existing escape-sequence painter work; wrap at
        # end of line must stay on because the painter writes full rows, and PROCESSED
        # output would let a stray '\n' scroll the alternate screen.
        wanted = (output | ENABLE_VIRTUAL_TERMINAL_PROCESSING | ENABLE_PROCESSED_OUTPUT |
                  ENABLE_WRAP_AT_EOL_OUTPUT)
        if wanted != output:
            set_mode(STD_OUTPUT_HANDLE, wanted)
            self.notes.append('output mode 0x%x -> 0x%x' % (output, wanted))
        input_mode = get_mode(STD_INPUT_HANDLE)
        self.saved['input'] = input_mode
        # QuickEdit is a selection freeze waiting to happen: one drag inside the picture
        # stops every write and the audio clock keeps running, so the watchdog fires.
        wanted = (input_mode | ENABLE_EXTENDED_FLAGS) & ~ENABLE_QUICK_EDIT_MODE & ~ENABLE_INSERT_MODE
        wanted &= ~ENABLE_LINE_INPUT & ~ENABLE_ECHO_INPUT
        if wanted != input_mode:
            set_mode(STD_INPUT_HANDLE, wanted)
            self.notes.append('input mode 0x%x -> 0x%x' % (input_mode, wanted))
        return self

    def leave(self):
        for which, key in ((STD_OUTPUT_HANDLE, 'output'), (STD_INPUT_HANDLE, 'input')):
            if key in self.saved:
                try:
                    set_mode(which, self.saved[key])
                except OSError:
                    pass
        self.saved = {}

    def visible_size(self):
        """Viewport columns/rows straight from the buffer record, or None."""
        info = SCREEN_BUFFER_INFO()
        handle = std_handle(STD_OUTPUT_HANDLE)
        if not kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
            return None
        columns = info.srWindow.Right - info.srWindow.Left + 1
        rows = info.srWindow.Bottom - info.srWindow.Top + 1
        if columns < 2 or rows < 2:
            return None
        return columns, rows


def size():
    """Columns, rows and which mechanism answered, because '100x36' can be a silent lie.

    The viewport record comes first on purpose: os.get_terminal_size() reports
    CONSOLE_SCREEN_BUFFER_INFO.dwSize, and under conhost that is the *buffer*, whose row
    count includes scrollback - a 9999-row buffer would otherwise be painted in full and
    only the min(h, 85) cap would notice. Windows Terminal keeps dwSize equal to the
    viewport, so the two agree there and the ordering only matters for other hosts.
    """
    try:
        viewport = Console().visible_size()
    except OSError:
        viewport = None
    if viewport:
        return viewport[0], viewport[1], 'GetConsoleScreenBufferInfo(srWindow)'
    for fd, label in ((1, 'os.get_terminal_size(stdout)'), (0, 'os.get_terminal_size(stdin)')):
        try:
            if not os.isatty(fd):
                continue
        except (OSError, ValueError):
            continue
        try:
            measured = os.get_terminal_size(fd)
        except OSError:
            continue
        if measured.columns > 1 and measured.lines > 1:
            return measured.columns, measured.lines, label
    measured = shutil.get_terminal_size()
    return measured.columns, measured.lines, 'shutil.get_terminal_size(env)'


class KeyQueue:
    """Keys on a worker thread, so the frame loop can time out instead of blocking.

    Arrows arrive as a 0xe0/0x00 prefix plus a scan letter; they are re-written into the
    escape sequences the existing dispatch already understands, so nothing downstream
    needs to know a Windows console was involved.
    """
    EXTENDED = {chr(72): '\x1b[A', chr(80): '\x1b[B', chr(77): '\x1b[C', chr(75): '\x1b[D',
                chr(73): '\x1b[H', chr(71): '\x1b[F', chr(83): '\x1b[3~', chr(79): '\x1b[1~'}

    def __init__(self):
        self.events = queue.Queue()
        self._stop = threading.Event()
        self._import_error = ''
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self):
        try:
            import msvcrt
        except ImportError as error:  # pragma: no cover - non-Windows import guard
            self._import_error = str(error)
            return
        while not self._stop.is_set():
            try:
                char = msvcrt.getwch()
            except (EOFError, KeyboardInterrupt, OSError):
                self.events.put('\x03')
                return
            if char in ('\x00', '\xe0'):
                try:
                    follow = msvcrt.getwch()
                except (EOFError, KeyboardInterrupt, OSError):
                    return
                mapped = self.EXTENDED.get(follow)
                if mapped:
                    self.events.put(mapped)
                continue
            self.events.put(char)

    def read(self, timeout=None):
        """Wait up to timeout for a key, then return everything pending as one string.

        Mirrors the blocking read the POSIX loop did, so a burst of keys lands in a
        single frame instead of one key per frame.
        """
        try:
            chunk = self.events.get(timeout=timeout)
        except queue.Empty:
            return ''
        while True:
            try:
                chunk += self.events.get(block=False)
            except queue.Empty:
                return chunk

    def close(self):
        self._stop.set()


class HighResolutionTimer:
    """Hold the system timer at 1 ms while the frame loop runs, then release it.

    Measured on this machine: a 41.7 ms frame wait jittered up to 23.9 ms without this
    and stayed inside 18.0 ms with it.
    """

    def __init__(self):
        self.held = False

    def acquire(self):
        try:
            self.held = winmm.timeBeginPeriod(1) == 0
        except (OSError, AttributeError):
            self.held = False
        return self.held

    def release(self):
        if self.held:
            try:
                winmm.timeEndPeriod(1)
            except OSError:
                pass
            self.held = False


def host_report():
    """Where this is being drawn, for the report file and for the pre-flight warning."""
    if os.environ.get('WT_SESSION'):
        return 'windows-terminal'
    if os.environ.get('TERM_PROGRAM') == 'vscode':
        return 'vscode-terminal'
    if os.environ.get('ConEmuANSI') or os.environ.get('ConEmuPID'):
        return 'conemu'
    try:
        import msvcrt  # noqa: F401
        return 'console'
    except ImportError:
        return 'no-console'

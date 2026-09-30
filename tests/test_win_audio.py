"""Contract tests for the Windows audio clock (win/audioclock.ps1).

These run against the child on its own, before player.py is ported, so a failure says
which side is wrong. The clock is wrapped in the same shape as player.Audio's reader
(state / command / error / last / proc / close) so the assertions below can later be
replayed through the real player without re-tuning any tolerance.
"""
from __future__ import annotations
import ctypes, json, os, re, subprocess, sys, threading, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'win'/'audioclock.ps1'
SONG = ROOT/'media'/'song.mp3'
CONFIG = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
Powershell = Path(os.environ['SystemRoot'])/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'


class Clock:
    """Reader mirroring player.Audio: keep the newest message, remember the gap."""

    def __init__(self, audio_path=SONG, mute=True, extra=(), expect_fail=False):
        argv = [str(Powershell), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', str(SCRIPT), '-AudioPath', str(audio_path)]
        if mute:
            argv.append('-Mute')
        argv += list(extra)
        self.messages = []
        self.state = {'time': 0.0, 'duration': 0.0, 'playing': False}
        self.error = ''
        self.last = time.monotonic()
        self.max_gap = 0.0
        # Startup (PowerShell + media open, ~2.5 s measured) is not a stall: the parent
        # tolerates it through its 20 s readiness deadline, so gaps only start counting
        # once a duration has been seen.
        self.counting = False
        self.proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, bufsize=1,
                                      encoding='utf-8', errors='replace')
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        self.stderr_lines = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        if expect_fail:
            return
        deadline = time.monotonic() + 10
        while not self.state['duration']:
            if self.proc.poll() is not None:
                time.sleep(0.1)  # let the stderr drain finish collecting the reason
                raise RuntimeError('child exited early: ' + '; '.join(self.stderr_lines))
            if time.monotonic() > deadline:
                raise RuntimeError('no duration within 10s')
            time.sleep(0.01)
        self.last = time.monotonic()
        self.counting = True

    def _drain_stderr(self):
        for line in self.proc.stderr:
            stripped = line.strip()
            if stripped:
                self.stderr_lines.append(stripped)

    def _read(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            now = time.monotonic()
            if self.counting:
                self.max_gap = max(self.max_gap, now - self.last)
            self.last = now
            self.messages.append(message)
            if 'error' in message:
                self.error = message['error']
            else:
                self.state = message

    def command(self, line):
        self.proc.stdin.write(line + '\n')
        self.proc.stdin.flush()

    def wait_for(self, predicate, timeout=4.0):
        """Poll the newest state until predicate(state) holds; returns the state or None."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate(self.state):
                return dict(self.state)
            time.sleep(0.005)
        return None

    def close(self):
        if self.proc.poll() is None:
            try:
                self.command('quit')
                self.proc.wait(timeout=3)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                self.proc.kill()
                self.proc.wait(timeout=3)
        else:
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass
        return self.proc.returncode


def pid_alive(pid):
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    alive = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) and code.value == 259
    ctypes.windll.kernel32.CloseHandle(handle)
    return bool(alive)


class SongRequired(unittest.TestCase):
    """These suites must go red without the audio, never quietly skip past it.

    An earlier version put skipIf on 14 of the 19 cases, so a fresh clone reported OK
    while testing almost nothing.
    """

    def test_media_song_mp3_is_present(self):
        if not SONG.is_file():
            self.fail(f'缺少 {SONG}。先跑 C:\\Python314\\python.exe win\\get_song.py 再跑本套件；'
                      '这些用例不允许静默跳过。')


class ClockContract(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.addCleanup(self.clock.close)

    # --- the seam: what player.py's loop depends on -------------------------------
    def test_reports_the_duration_the_timeline_was_built_for(self):
        self.assertLess(abs(self.clock.state['duration'] - CONFIG['duration']), 0.5,
                        'audio clock disagrees with config.json duration')

    def test_seek_while_paused_lands_exactly(self):
        self.clock.command('seek 158.7')
        state = self.clock.wait_for(lambda s: abs(s['time'] - 158.7) < 0.05)
        self.assertIsNotNone(state, 'position never reached 158.7: ' + repr(self.clock.state))
        self.assertLess(abs(state['time'] - 158.7), 0.3)
        self.assertFalse(state['playing'], 'seek must not start playback by itself')

    def test_position_tracks_wall_clock_while_playing(self):
        self.clock.command('seek 20')
        self.assertIsNotNone(self.clock.wait_for(lambda s: abs(s['time'] - 20) < 0.2))
        self.clock.command('play')
        self.assertIsNotNone(self.clock.wait_for(lambda s: s['playing']), 'never reported playing')
        first, at_first = self.clock.state['time'], time.monotonic()
        time.sleep(2.0)
        second, at_second = self.clock.state['time'], time.monotonic()
        # This proves the reported position tracks a real clock. It cannot prove the
        # number comes from the media engine rather than a monotonic timer - that needs
        # the end-of-track and pause-freeze cases below to fail in characteristically
        # media-shaped ways, which is why they are separate tests.
        self.assertLess(abs((second - first) - (at_second - at_first)), 0.2,
                        f'position moved {second - first:.3f}s over {at_second - at_first:.3f}s wall')

    def test_pause_freezes_position(self):
        self.clock.command('play')
        self.assertIsNotNone(self.clock.wait_for(lambda s: s['playing']))
        self.clock.command('pause')
        self.assertIsNotNone(self.clock.wait_for(lambda s: not s['playing']))
        first = self.clock.state['time']
        time.sleep(0.7)
        self.assertEqual(first, self.clock.state['time'], 'paused clock kept moving')

    def test_seek_while_playing(self):
        self.clock.command('play')
        self.assertIsNotNone(self.clock.wait_for(lambda s: s['playing']))
        self.clock.command('seek 100.0')
        state = self.clock.wait_for(lambda s: abs(s['time'] - 100.0) < 0.3, timeout=3)
        self.assertIsNotNone(state, 'seek during playback did not take: ' + repr(self.clock.state))

    def test_seek_beyond_the_end_is_clamped(self):
        self.clock.command('seek ' + str(self.clock.state['duration'] + 30))
        state = self.clock.wait_for(lambda s: s['time'] > 0, timeout=2)
        self.assertIsNotNone(state)
        self.assertLessEqual(state['time'], self.clock.state['duration'])
        self.assertGreater(state['time'], self.clock.state['duration'] - 0.5)

    def test_track_end_is_visible_to_the_parent_end_logic(self):
        duration = self.clock.state['duration']
        self.clock.command(f'seek {duration - 1.2}')
        self.assertIsNotNone(self.clock.wait_for(lambda s: s['time'] > duration - 2))
        self.clock.command('play')
        self.assertIsNotNone(self.clock.wait_for(lambda s: s['playing']))
        stopped = self.clock.wait_for(lambda s: not s['playing'], timeout=4)
        self.assertIsNotNone(stopped, 'playback never reported stopping at the end')
        # player.py:254 treats "at duration and not playing" as the finished state.
        self.assertGreater(stopped['time'], duration - 0.5,
                           'position at end must stay near duration so the parent can see it finished')

    # --- the child's own behaviour -------------------------------------------------
    def test_backend_and_pid_prove_which_process_answered(self):
        # setUp returns the moment duration is known, so let a few ticks land first.
        self.assertIsNotNone(self.wait_for_messages(8))
        for message in self.clock.messages[:8]:
            self.assertEqual(message.get('backend'), 'winrt-mediafoundation')
            self.assertEqual(message.get('pid'), self.clock.proc.pid,
                             'the clock that answered is not the process we spawned')

    def wait_for_messages(self, count, timeout=4.0):
        deadline = time.monotonic() + timeout
        while len(self.clock.messages) < count and time.monotonic() < deadline:
            time.sleep(0.02)
        return len(self.clock.messages) >= count

    def test_no_gap_would_trip_the_parent_watchdog(self):
        before = len(self.clock.messages)
        time.sleep(6.0)
        self.assertLess(self.clock.max_gap, 2.0,
                        'a gap this wide makes player.py raise 音频时钟停止更新')
        rate = (len(self.clock.messages) - before) / 6.0
        # Measured ceiling is 64 Hz (one 15.6 ms tick); the parent draws 24 fps, so
        # anything much below a tick-per-frame rate would repeat frames.
        self.assertGreater(rate, 40.0, f'clock emitted {rate:.1f} Hz, expected ~64 Hz')

    def test_quit_exits_promptly_and_leaves_no_orphan(self):
        pid = self.clock.proc.pid
        self.clock.command('play')
        started = time.monotonic()
        code = self.clock.close()
        self.assertEqual(code, 0, 'child exited with ' + str(code))
        self.assertLess(time.monotonic() - started, 3.0)
        self.assertFalse(pid_alive(pid), f'powershell pid {pid} still alive')
        self.clock = None

    def test_stderr_stays_empty_on_the_happy_path(self):
        # A line here means the child fought a localized error we never surfaced.
        for command in ('seek 44.0', 'play', 'pause', 'volume 0.4', 'seek 90.5'):
            self.clock.command(command)
            time.sleep(0.25)
        time.sleep(0.5)
        self.assertEqual(self.clock.stderr_lines, [],
                         'child wrote to stderr: ' + ' | '.join(self.clock.stderr_lines))
        self.assertEqual(self.clock.error, '')


class ClockFailureModes(unittest.TestCase):
    def test_missing_file_reports_on_both_channels(self):
        missing = SONG.parent/'definitely-not-here.mp3'
        self.assertFalse(missing.is_file())
        clock = Clock(missing, expect_fail=True)
        self.addCleanup(clock.close)
        try:
            code = clock.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            clock.proc.kill()
            self.fail('child hung on a missing file instead of failing')
        time.sleep(0.1)
        self.assertEqual(clock.error, 'audio file not found')
        self.assertTrue(clock.stderr_lines, 'no stderr explanation for the exit')
        self.assertNotEqual(code, 0)

    def test_closed_stdin_is_treated_as_quit(self):
        clock = Clock()
        self.addCleanup(clock.close)
        clock.proc.stdin.close()
        try:
            code = clock.proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            clock.proc.kill()
            self.fail('child ignored stdin EOF and had to be killed')
        self.assertEqual(code, 0)

    def test_volume_and_mute_are_accepted(self):
        clock = Clock(extra=['-Volume', '0.2'])
        self.addCleanup(clock.close)
        clock.command('volume 0.5')
        clock.command('volume 2.0')
        clock.command('volume -1')
        time.sleep(0.2)
        self.assertEqual(clock.error, '')
        self.assertGreater(clock.state['duration'], 0)


class SilentBackendContract(unittest.TestCase):
    """--backend none must still behave like a clock, or the frame loop lies to itself."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        import player
        cls.player = player

    def setUp(self):
        self.clock = self.player.Silent(CONFIG['duration'])
        self.addCleanup(self.clock.close)

    def test_same_surface_as_the_real_clock(self):
        for name in ('state', 'error', 'last', 'proc', 'command', 'close', 'ready_seconds'):
            self.assertTrue(hasattr(self.clock, name), 'missing ' + name)
        self.assertIsNone(self.clock.proc.poll(), 'run() treats a dead poll() as a crash')

    def test_duration_comes_from_config(self):
        self.assertAlmostEqual(self.clock.state['duration'], CONFIG['duration'], places=3)

    def test_seek_play_pause(self):
        self.clock.command('seek 12.5')
        self.assertAlmostEqual(self.clock.state['time'], 12.5, places=2)
        self.assertFalse(self.clock.state['playing'])
        self.clock.command('play')
        first, at_first = self.clock.state['time'], time.monotonic()
        time.sleep(0.6)
        moved = self.clock.state['time'] - first
        self.assertLess(abs(moved - (time.monotonic() - at_first)), 0.15)
        self.clock.command('pause')
        frozen = self.clock.state['time']
        time.sleep(0.4)
        self.assertEqual(frozen, self.clock.state['time'])

    def test_it_stops_claiming_to_play_at_the_end(self):
        self.clock.command(f'seek {CONFIG["duration"] - 0.2}')
        self.clock.command('play')
        deadline = time.monotonic() + 3
        while self.clock.state['playing'] and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(self.clock.state['playing'], 'never reported the end')
        self.assertLessEqual(self.clock.state['time'], self.clock.state['duration'])

    def test_watchdog_stays_satisfied_while_running(self):
        deadline = time.monotonic() + 3.0
        worst = 0.0
        while time.monotonic() < deadline:
            worst = max(worst, time.monotonic() - self.clock.last)
            time.sleep(0.01)
        self.assertLess(worst, 2.0, 'run() would have raised 音频时钟停止更新')


class AudioFailureReapsItsChild(unittest.TestCase):
    """If the clock cannot come up, whoever spawned it must still clean up.

    run()'s finally only sees the Audio object if the constructor returned, so a raise
    there used to leave powershell.exe running with the console modes still changed.
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        import player
        cls.player = player

    def test_unreadable_media_leaves_no_process_behind(self):
        bogus = ROOT/'.build'/'not-really-mp3.bin'
        bogus.parent.mkdir(parents=True, exist_ok=True)
        bogus.write_bytes(b'this is not audio' * 64)
        self.addCleanup(lambda: bogus.unlink(missing_ok=True))
        started = time.monotonic()
        with self.assertRaises(RuntimeError) as caught:
            self.player.Audio(bogus)
        message = str(caught.exception)
        pid = None
        match = re.search(r'pid=(\d+)', message)
        if match:
            pid = int(match.group(1))
        if pid is None:
            # The constructor must say which process it gave up on; otherwise this test
            # cannot prove the child died rather than the message merely being short.
            self.fail(f'Audio() raised without reporting the child pid: {message[:200]}')
        self.assertFalse(pid_alive(pid), f'powershell pid {pid} survived a failed start')
        self.assertLess(time.monotonic() - started, 25.0)


if __name__ == '__main__':
    unittest.main(verbosity=2)

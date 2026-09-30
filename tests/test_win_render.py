"""Prove the Windows port did not change a single painted cell.

The upstream file cannot run on this machine at all (it imports termios, and its
read_text() calls die on a cp936 console codec), so the oracle here is the upstream
source with exactly those two things repaired and nothing else. The repair is counted,
not assumed, and any other difference fails the build.

Then the whole film is rendered twice - once by the oracle's painter, once by the
ported one - and every frame must agree exactly.
"""
from __future__ import annotations
import difflib, json, pathlib, subprocess, sys, time, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

IMPORT_OLD = 'import sys, termios, threading, time, tty, unicodedata'
IMPORT_NEW = 'import sys, threading, time, unicodedata'
READ_OLD = '.read_text())'
READ_NEW = ".read_text(encoding='utf-8'))"
PRISTINE = ROOT/'.build'/'pristine'/'player_upstream.py'
# Pinned to the commit cloned from GitHub, so committing the port cannot turn this
# oracle into a copy of the file under test.
UPSTREAM_COMMIT = '9d8e815281a104ccb648ec2f2df88cd9f0cb8c12'
UPSTREAM_SHA256 = 'aac5c7b48f66301325ee393d36434b394d054505b573d8f5ec0cd508861d8263'
# The author's own bundle test asserted these lines at these times; keep them as the
# spot checks a reader can eyeball, on top of the full sweep.
EXPECTED = [(67.3, 'If I can make you happy'), (124.2, 'Then maybe'),
            (159.85, 'TROIS'), (183.2, 'Question me')]
CONFIG = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))


def pristine_bytes():
    import hashlib, subprocess
    if not PRISTINE.is_file():
        PRISTINE.parent.mkdir(parents=True, exist_ok=True)
        fetched = subprocess.run(['git', 'show', UPSTREAM_COMMIT + ':player.py'],
                                 cwd=str(ROOT), capture_output=True)
        if fetched.returncode != 0:
            raise RuntimeError('no pristine copy and git show failed: '
                               + fetched.stderr.decode('utf-8', 'replace'))
        PRISTINE.write_bytes(fetched.stdout)
    data = PRISTINE.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != UPSTREAM_SHA256:
        raise RuntimeError(f'pristine player.py is {digest}, expected {UPSTREAM_SHA256}; '
                           'the oracle would not be upstream code any more')
    return data


def build_oracle():
    source = pristine_bytes().decode('utf-8')
    imports = source.count(IMPORT_OLD)
    reads = source.count(READ_OLD)
    patched = source.replace(IMPORT_OLD, IMPORT_NEW).replace(READ_OLD, READ_NEW)
    namespace = {'__file__': str(ROOT/'player.py'), '__name__': 'upstream_oracle'}
    exec(compile(patched, 'upstream_oracle.py', 'exec'), namespace)
    return namespace, source, patched, imports, reads


class OracleIsOnlyRepaired(unittest.TestCase):
    """The oracle must differ from upstream in the two ways said out loud, and no others."""

    def setUp(self):
        self.oracle, self.source, self.patched, self.imports, self.reads = build_oracle()

    def test_repairs_are_exactly_the_two_named(self):
        self.assertEqual(self.imports, 1, 'expected one termios import line')
        self.assertEqual(self.reads, 3, 'expected three read_text() calls')
        changed = [line for line in difflib.unified_diff(self.source.splitlines(),
                   self.patched.splitlines(), lineterm='', n=0)
                   if (line.startswith('-') or line.startswith('+')) and not line.startswith(('---', '+++'))]
        self.assertEqual(len(changed), 8, 'unexpected edit volume:\n' + '\n'.join(changed))

    def test_painter_objects_exist_in_both(self):
        import player
        for name in ('Canvas', 'Film', 'FONT', 'cw', 'crop', 'wrap', 'width'):
            self.assertIn(name, self.oracle, 'upstream oracle lost ' + name)
            self.assertTrue(hasattr(player, name), 'ported player lost ' + name)


class WholeFilmMatches(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oracle, _, _, _, _ = build_oracle()
        import player
        cls.player = player
        cls.started = time.monotonic()
        cls.oracle_film = cls.oracle['Film']()
        cls.player_film = player.Film()
        cls.budget = 0.5
        # Sweep past config.json's duration: the media engine reports 211.98365 and the
        # clock contract allows +-0.5 s, so the tail must be compared too.
        top = CONFIG['duration'] + 0.6
        cls.times = [round(t * cls.budget, 2) for t in range(int(top / cls.budget) + 1)]

    def render_both(self, t, w, h, **flags):
        oracle = self.oracle_film.render(t, w, h, **flags)
        ours = self.player_film.render(t, w, h, **flags)
        return oracle, ours

    def test_glyph_widths_agree_for_every_glyph_either_can_draw(self):
        glyphs = set()
        for t in self.times[::8]:
            oracle, ours = self.render_both(t, 125, 45, paused=True)
            glyphs.update(ch for line in oracle.plain().splitlines() for ch in line)
            glyphs.update(ch for line in ours.plain().splitlines() for ch in line)
        wide = [ch for ch in sorted(glyphs) if self.oracle['cw'](ch) != self.player.cw(ch)]
        self.assertEqual(wide, [], f'cw() now measures these differently: {wide}')

    def test_every_frame_of_the_film_matches(self):
        mismatches = []
        for t in self.times:
            oracle, ours = self.render_both(t, 125, 45, paused=True)
            if oracle.plain() != ours.plain() or oracle.ansi() != ours.ansi():
                mismatches.append(t)
        self.assertEqual(mismatches, [], f'{len(mismatches)} of {len(self.times)} frames differ, first: {mismatches[:6]}')

    def test_corner_screen_sizes_and_overlays_match(self):
        flags = [{'paused': True}, {'paused': False}, {'paused': True, 'ready': True},
                 {'paused': False, 'help_on': True}, {'paused': True, 'ready': True, 'help_on': True}]
        sizes = [(63, 23), (64, 24), (80, 30), (125, 45), (240, 85), (300, 120)]
        checked = 0
        for width, height in sizes:
            for t in (0.0, 20.0, 67.3, 124.2, 159.85, 209.0):
                for flag in flags:
                    oracle, ours = self.render_both(t, width, height, **flag)
                    self.assertEqual(oracle.plain(), ours.plain(),
                                     f'{width}x{height} t={t} {flag}')
                    self.assertEqual(oracle.ansi(), ours.ansi(), f'ansi {width}x{height} t={t} {flag}')
                    checked += 1
        self.assertGreaterEqual(checked, 150, 'the matrix silently shrank')

    def test_sweep_took_the_time_it_reports(self):
        elapsed = time.monotonic() - self.started
        print(f'\n  rendered {len(self.times) * 2} frames plus overlays in {elapsed:.1f}s '
              f'({self.budget}s steps over {CONFIG["duration"]:.0f}s)')
        self.assertLess(elapsed, 240, 'a sweep this slow will not finish in CI')


class NothingInThePristineCopyChanges(unittest.TestCase):
    def test_ambiguous_knob_changes_the_picture_and_defaults_to_narrow(self):
        """The knob must reach the painter, and the shipped default must stay narrow.

        Note for whoever reads a red here: a glyph counted as two cells overwrites its
        neighbour rather than shifting the row, so plain() can be identical on frames whose
        Ambiguous glyphs sit mid-line. That is why this asserts cw() directly and only
        requires *some* frame in the film to differ.
        """
        import player
        glyphs = player.ambiguous_used()
        self.assertTrue(glyphs, 'ambiguous_used() found nothing, so the knob cannot work')
        probe = sorted(glyphs)[0]
        player.AMBIGUOUS_WIDE.clear()
        self.assertEqual(player.cw(probe), 1, 'default must count Ambiguous as one cell')
        player.AMBIGUOUS_WIDE.add(probe)
        self.assertEqual(player.cw(probe), 2, 'the set is not wired into cw()')
        player.AMBIGUOUS_WIDE.clear()

        def render(time_point, *extra):
            argv = [sys.executable, str(ROOT/'player.py'), '--snapshot', time_point, '--plain',
                    '--width', '125', '--height', '45'] + list(extra)
            done = subprocess.run(argv, cwd=str(ROOT), capture_output=True, encoding='utf-8',
                                  errors='replace')
            self.assertEqual(done.returncode, 0, done.stderr[-300:])
            return done.stdout
        differed = [t for t in ('124.2', '190.0', '205.0')
                    if render(t, '--ambiguous-width', '1') != render(t, '--ambiguous-width', '2')]
        self.assertTrue(differed, 'no frame of the film responds to --ambiguous-width 2')
        self.assertEqual(render('190.0'), render('190.0', '--ambiguous-width', '1'),
                         'the shipped default is no longer the narrow reading')
        self.assertIn('TROIS', render('159.85'))

    def test_reading_a_frame_never_touches_the_working_tree(self):
        import player
        before = {p.name for p in ROOT.iterdir()}
        player.Film().render(100.0, 100, 40, True).ansi()
        after = {p.name for p in ROOT.iterdir()}
        self.assertEqual(before, after, 'rendering created or removed a top-level entry')


class UpstreamExpectationsStillHold(unittest.TestCase):
    def test_the_four_cues_the_author_tested(self):
        import player
        film = player.Film()
        for t, expected in EXPECTED:
            painted = film.render(t, 125, 45, True).plain()
            self.assertIn(expected, painted, f'{expected!r} missing at t={t}')


if __name__ == '__main__':
    unittest.main(verbosity=2)

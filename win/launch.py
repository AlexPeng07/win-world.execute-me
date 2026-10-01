"""Decide how to start the MV. Kept in Python so the launcher has no batch quoting traps.

cmd.exe expands %ERRORLEVEL% at parse time inside a parenthesised block, cannot see a
child's exit code without delayed expansion, and labels/goto in a line-feed-only .cmd are
their own hazard. All of that lives here instead; win/launch.cmd only finds Python.
"""
from __future__ import annotations
import argparse, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS = {'full': ['--fullscreen'], 'max': ['--maximized'], 'win': []}


def child_env():
    env = dict(os.environ)
    # Keep __pycache__ out of the repository while it plays.
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def ensure_song(python):
    song = ROOT/'media'/'song.mp3'
    if song.is_file():
        return 0
    print('First run: fetching the original song out of the official release package...')
    return subprocess.run([python, str(ROOT/'win'/'get_song.py')], cwd=str(ROOT),
                          env=child_env()).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', nargs='?', default='max', choices=sorted(FLAGS),
                        help='full = cover the taskbar, max = maximised window, win = plain window')
    args = parser.parse_args()

    if ensure_song(sys.executable) != 0:
        print('Could not obtain media/song.mp3. Check the network and run again.', file=sys.stderr)
        return 1

    terminal = shutil.which('wt.exe')
    if not terminal:
        print('Windows Terminal was not found; running in this console instead.', file=sys.stderr)
        return subprocess.run([sys.executable, 'player.py'],
                              cwd=str(ROOT), env=child_env()).returncode

    # -d . keeps the repository path out of the command line entirely: this directory name
    # holds a semicolon, parentheses and a space, and wt uses ';' to split its own
    # arguments. Passing argv as a list means nothing has to be quoted by hand.
    command = [terminal] + FLAGS[args.mode] + ['-d', '.', sys.executable, 'player.py']
    print('launching: ' + ' '.join(command))
    return subprocess.run(command, cwd=str(ROOT), env=child_env()).returncode


if __name__ == '__main__':
    sys.exit(main())

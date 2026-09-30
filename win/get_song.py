"""Fetch the original song out of the official release package and verify it.

The repository does not carry audio (media/ is gitignored), but spectrum.json and
lyrics.json were measured against one specific recording, so only the audio embedded in
the v1.0.0 player package keeps animation, captions and spectrum in sync.

Three independent stages, all of which must actually run before anything is written to
media/: the downloaded package must match the author's published SHA256SUMS.txt, the
extracted MP3 must match the per-file hash in the package's own manifest, and the media
engine must report a duration that agrees with config.json.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, subprocess, sys, threading, time, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'.build'/'cache'
PACKAGE = 'world-execute-mv.pyz'
MEMBER = 'media/song.mp3'
TARGET = ROOT/'media'/'song.mp3'
CONFIG = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
BASE = 'https://github.com/yym8224961/world.execute-me-ascii/releases/download/v1.0.0/'
UA = {'User-Agent': 'world-execute-mv-windows/1.0'}
POWERSHELL = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'),
                          'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe')
CLOCK = ROOT/'win'/'audioclock.ps1'


def fetch(url, timeout=600):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as response:
        return response.read()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def published_digest():
    """The author's own checksum for the package, so transport damage is detectable."""
    for line in fetch(BASE + 'SHA256SUMS.txt', 60).decode('utf-8', 'replace').splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].lstrip('*') == PACKAGE:
            return parts[0].lower()
    return ''


def load_package(force=False):
    """Return package bytes only if they match the published checksum; no silent fallback."""
    CACHE.mkdir(parents=True, exist_ok=True)
    expected = published_digest()
    if not expected:
        raise SystemExit(f'官方 {PACKAGE} 的 SHA256SUMS.txt 里没有对应条目，无法验证下载完整性；'
                         '请检查网络或稍后重试。')
    cached = CACHE/PACKAGE
    marker = CACHE/(PACKAGE + '.verified')
    if cached.is_file() and not force:
        digest = sha256(cached.read_bytes())
        if digest == expected and marker.is_file() and marker.read_text().strip() == digest:
            return cached.read_bytes(), 'cache', expected, digest
    data = fetch(BASE + PACKAGE)
    digest = sha256(data)
    if digest != expected:
        raise SystemExit(f'下载包与官方 SHA256SUMS.txt 不符（要 {expected}，得 {digest}），拒绝使用。')
    cached.write_bytes(data)
    marker.write_text(digest + '\n', encoding='utf-8')
    return data, 'download', expected, digest


def extract(bundle_bytes):
    """Pull the MP3 out and check it against the manifest that shipped inside the package."""
    with zipfile.ZipFile(io.BytesIO(bundle_bytes)) as archive:
        manifest = json.loads(archive.read('bundle-manifest.json'))
        files = manifest.get('files', {})
        if MEMBER not in files:
            raise SystemExit('发布包里没有 ' + MEMBER + '；清单字段：' + ', '.join(sorted(files)))
        data = archive.read(MEMBER)
    want = files[MEMBER].lower()
    got = sha256(data)
    if got != want:
        raise SystemExit(f'音频校验失败：清单要 {want}，实得 {got}')
    return data, want, got, manifest


def engine_duration(path, timeout=25.0):
    """Ask the same media stack the player uses. MCI cannot decode MP3 on this machine."""
    argv = [POWERSHELL, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(CLOCK),
            '-AudioPath', str(path), '-Mute']
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, bufsize=1,
                            encoding='utf-8', errors='replace')
    found = {'duration': 0.0}

    def read():
        for line in proc.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('duration'):
                found['duration'] = float(message['duration'])
                return
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not found['duration']:
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    if proc.poll() is None:
        try:
            proc.stdin.write('quit\n')
            proc.stdin.flush()
            proc.wait(timeout=3)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            proc.kill()
    stderr = proc.stderr.read()
    return found['duration'], (proc.returncode, stderr.strip()[-300:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='re-download even if the cache verifies')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    report = {'target': str(TARGET)}
    bundle_bytes, origin, expected, digest = load_package(args.force)
    report.update({'package_bytes': len(bundle_bytes), 'package_sha256': digest,
                   'published_sha256': expected, 'package_origin': origin,
                   'package_matches_published': digest == expected})
    data, want, got, manifest = extract(bundle_bytes)
    report.update({'audio_bytes': len(data), 'audio_sha256': got, 'audio_manifest_sha256': want,
                   'audio_matches_manifest': got == want, 'embedded_platform': manifest.get('platform'),
                   'config_duration_s': CONFIG['duration']})

    # Stage three runs against a scratch copy, so a rejected file never reaches media/.
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    scratch = CACHE/'duration-probe.mp3'
    scratch.write_bytes(data)
    duration, probe = engine_duration(scratch)
    scratch.unlink(missing_ok=True)
    report['engine_duration_s'] = duration
    report['engine_probe'] = probe
    report['length_delta_s'] = round(duration - CONFIG['duration'], 3) if duration else None
    if not duration:
        report['verdict'] = 'ENGINE_CANNOT_MEASURE'
        reject(report, '媒体引擎报不出时长，拒绝落盘：无法确认这份音频与频谱时间轴对得上。')
    if abs(duration - CONFIG['duration']) > 0.5:
        report['verdict'] = 'LENGTH_MISMATCH_CHECK_AUDIO_SOURCE'
        reject(report, f'时长对不上（引擎 {duration} vs 配置 {CONFIG["duration"]}），拒绝落盘。')
    TARGET.write_bytes(data)
    if TARGET.stat().st_size != len(data):
        reject(report, '音频落盘大小不一致。')
    report['verdict'] = 'OK'
    output(report, args)


def reject(report, message):
    output(report, None)
    raise SystemExit(message)


def output(report, args):
    if args and args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for key, value in report.items():
            print(f'{key}: {value}')


if __name__ == '__main__':
    sys.exit(main())

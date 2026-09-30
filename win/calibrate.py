"""Measure how many cells this console really gives each East-Asian-Ambiguous glyph.

The painter counts those glyphs as one cell, because that is what the author's macOS
terminal drew. A Windows console sizes a cell from the font, so a CJK fallback could draw
one glyph across two cells and shift everything after it on that row.

Windows Terminal was measured here as not answering cursor-position reports (ESC [ 6 n
returns nothing), so this reads pixels: it paints rows, grabs the screen through GDI, and
compares where each row ends. Every row is "#" + glyph x 40 + "#". The trailing "#" is the
same character in every row, so side bearings cancel and any difference in its right edge
is exactly 40 x (cells-per-glyph - 1) cells of drift.

Rows are spaced far apart on purpose: full-block glyphs paint the whole cell height and
would otherwise fuse with a neighbour into one band.

  wt.exe --fullscreen -d . C:\\Python314\\python.exe win\\calibrate.py
"""
from __future__ import annotations
import argparse, json, sys, time, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from win import screenctl, winconsole

REPEATS = 40
EDGE_CHAR = '#'
FILLER = 'X'
CONTROL_GLYPH = '中'          # Han: must read two cells or the instrument is lying
ROW_STRIDE = 7                # blank rows between measurements, so bands cannot fuse
FIRST_ROW = 2
SETTLE_S = 0.45
THRESHOLD = 128


def ambiguous_glyphs():
    """Ask the painter itself, so the measured set and the drawn set cannot disagree."""
    import player
    return sorted(player.ambiguous_used())


def row_text(glyph, repeats=REPEATS):
    return EDGE_CHAR + glyph * repeats + EDGE_CHAR


def paint_plan(glyphs, first_row=FIRST_ROW, stride=ROW_STRIDE):
    """[(console row, glyph)] with the ruler first; every measurement is isolated."""
    plan = [(first_row, FILLER)]
    row = first_row + stride
    for glyph in glyphs:
        plan.append((row, glyph))
        row += stride
    return plan


def fits(plan, columns, rows):
    return columns >= REPEATS + 2 and rows >= (plan[-1][0] if plan else 0)


def paint(plan):
    sys.stdout.write('\x1b[?1049h\x1b[?25l\x1b[0m\x1b[?7l\x1b[2J')
    for row, glyph in plan:
        sys.stdout.write(f'\x1b[{row};1H\x1b[0;97;40m{row_text(glyph)}\x1b[0m')
    sys.stdout.flush()


def ink_rows(data, width, height, scan_width):
    counts = []
    for y in range(height):
        base = y * width * 4
        ink = 0
        for x in range(scan_width):
            offset = base + x * 4
            if data[offset] >= THRESHOLD or data[offset + 1] >= THRESHOLD or data[offset + 2] >= THRESHOLD:
                ink += 1
        counts.append(ink)
    return counts


def bands_of(counts, minimum=3):
    found, start = [], None
    for y, ink in enumerate(counts):
        if ink >= minimum and start is None:
            start = y
        elif ink < minimum and start is not None:
            found.append((start, y - 1))
            start = None
    if start is not None:
        found.append((start, len(counts) - 1))
    return found


def right_edge(data, width, top, bottom, scan_width):
    for x in range(scan_width - 1, -1, -1):
        for y in range(top, bottom + 1):
            offset = y * width * 4 + x * 4
            if data[offset] >= THRESHOLD or data[offset + 1] >= THRESHOLD or data[offset + 2] >= THRESHOLD:
                return x
    return None


def left_edge(data, width, top, bottom, scan_width):
    for x in range(scan_width):
        for y in range(top, bottom + 1):
            offset = y * width * 4 + x * 4
            if data[offset] >= THRESHOLD or data[offset + 1] >= THRESHOLD or data[offset + 2] >= THRESHOLD:
                return x
    return None


def grab_and_segment(report):
    width, height, data = screenctl.grab()
    # Wide enough for a worst case row: 81 cells of drift at the measured cell width.
    scan = min(width, 1500)
    lines = bands_of(ink_rows(data, width, height, scan))
    return width, height, data, scan, lines


def measure_batch(plan, report, evidence=False):
    """Paint one batch, grab once, return {glyph: cells} for that batch."""
    paint(plan)
    time.sleep(SETTLE_S)
    width, height, data, scan, lines = grab_and_segment(report)
    if evidence:
        # Keep the frame the numbers were actually measured from, not the summary screen.
        bmp = ROOT/'.build'/'calibrate-screen.bmp'
        png = ROOT/'.build'/'calibrate-screen.png'
        bmp.parent.mkdir(parents=True, exist_ok=True)
        screenctl.write_bmp(bmp, width, height, data)
        screenctl.write_png(png, width, height, data)
        report['grab'] = {'width': width, 'height': height, 'dpi_mode': screenctl.DPI_MODE,
                          'bmp': str(bmp), 'png': str(png)}
    if len(lines) != len(plan):
        report.setdefault('band_problems', []).append(
            {'expected': len(plan), 'found': len(lines), 'rows': [p[0] for p in plan]})
        return {}
    ruler_top, ruler_bottom = lines[0]
    ruler_right = right_edge(data, width, ruler_top, ruler_bottom, scan)
    ruler_left = left_edge(data, width, ruler_top, ruler_bottom, scan)
    if ruler_right is None or ruler_left is None:
        return {}
    cell_px = (ruler_right - ruler_left + 1) / (REPEATS + 1)
    report.setdefault('cell_px', []).append(round(cell_px, 4))
    out = {}
    for (row, glyph), (top, bottom) in zip(plan[1:], lines[1:]):
        right = right_edge(data, width, top, bottom, scan)
        if right is None:
            out[glyph] = {'cells': None, 'note': 'no ink'}
            continue
        shift = right - ruler_right
        out[glyph] = {'cells': round(1 + shift / (REPEATS * cell_px), 3), 'shift_px': shift,
                      'console_row': row}
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default=str(ROOT / 'docs' / 'win-glyph-metrics.json'))
    parser.add_argument('--apply', action='store_true', help='write the wide set into config.json')
    parser.add_argument('--batch', type=int, default=6, help='glyphs measured per screen')
    args = parser.parse_args()

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SystemExit('需要真实终端：用 wt.exe --fullscreen -d . python win\\calibrate.py 运行。')

    columns, rows_available, size_source = winconsole.size()
    glyphs = ambiguous_glyphs()
    queue = [CONTROL_GLYPH] + glyphs
    report = {'host': winconsole.host_report(), 'dpi_mode': screenctl.DPI_MODE,
              'repeats': REPEATS, 'row_stride': ROW_STRIDE,
              'console': {'columns': columns, 'rows': rows_available, 'source': size_source},
              'ambiguous_count': len(glyphs)}
    probe_plan = paint_plan(queue[:args.batch])
    if not fits(probe_plan, columns, rows_available):
        report['verdict'] = 'WINDOW_TOO_SMALL'
        report['needs'] = {'rows': probe_plan[-1][0], 'columns': REPEATS + 2}
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'窗口太小：需要 {probe_plan[-1][0]} 行 x {REPEATS + 2} 列，实际 {rows_available} x {columns}。'
              '按 Ctrl+Shift+减号 缩小字号，或减小 --batch。')
        return 2

    console = winconsole.Console()
    console.enter()
    results = {}
    code = 0
    try:
        for start in range(0, len(queue), args.batch):
            batch = queue[start:start + args.batch]
            measured = measure_batch(paint_plan(batch), report, evidence=(start == 0))
            results.update(measured)
        control = results.get(CONTROL_GLYPH, {}).get('cells')
        filler_ok = True
        wide = [ch for ch, data in results.items()
                if ch != CONTROL_GLYPH and data.get('cells') and data['cells'] > 1.5]
        unresolved = [ch for ch, data in results.items() if data.get('cells') is None]
        instrument_ok = control is not None and abs(control - 2) < 0.15 and not report.get('band_problems')
        report['results'] = results
        report['control_cjk_cells'] = control
        report['instrument_self_check'] = 'ok' if instrument_ok else 'BROKEN'
        report['ambiguous_measured'] = len(results) - (1 if CONTROL_GLYPH in results else 0)
        report['ambiguous_wide'] = sorted(wide)
        report['unresolved'] = sorted(unresolved)
        if not instrument_ok:
            report['verdict'] = 'BROKEN_INSTRUMENT'
            code = 1
        elif wide:
            report['verdict'] = 'SOME_WIDE'
        else:
            report['verdict'] = 'ALL_NARROW'
        summary = (f'{report["verdict"]}: measured={report["ambiguous_measured"]} '
                   f'wide={len(wide)} unresolved={len(unresolved)} '
                   f'CJK控制组={control} cell_px={report.get("cell_px")}')
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        sys.stdout.write('\x1b[2J\x1b[H\x1b[0;97;40m' + summary + '\x1b[0m')
        for glyph, data_row in sorted(results.items()):
            if abs((data_row.get('cells') or 1) - 1) > 0.15:
                sys.stdout.write(f'\x1b[0;97;40m  {glyph} -> {data_row}\x1b[0m\r\n')
        sys.stdout.flush()
        if args.apply:
            config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
            config['ambiguous_wide'] = sorted(wide)
            (ROOT / 'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n',
                                              encoding='utf-8')
            print(f'applied {len(wide)} wide glyphs to config.json')
        print('\n(按任意键收尾)')
        time.sleep(1.5)
        print(summary + f'\n报告：{args.out}')
        return code
    finally:
        sys.stdout.write('\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l')
        sys.stdout.flush()
        console.leave()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        import traceback
        crash = ROOT / '.build' / 'calibrate-crash.txt'
        crash.parent.mkdir(parents=True, exist_ok=True)
        crash.write_text(traceback.format_exc(), encoding='utf-8')
        raise

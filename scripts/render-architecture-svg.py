#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'assets' / 'architecture.json'
OUT = ROOT / 'docs' / 'assets' / 'architecture.svg'

ACCENTS = {
    'green': {'stroke': '#34d399', 'fill': '#0f3d2e', 'soft': '#123528'},
    'purple': {'stroke': '#c084fc', 'fill': '#4c1384', 'soft': '#34135f'},
    'orange': {'stroke': '#fb923c', 'fill': '#6a3415', 'soft': '#4c2410'},
    'blue': {'stroke': '#60a5fa', 'fill': '#22356f', 'soft': '#1b2c59'},
    'cyan': {'stroke': '#38bdf8', 'fill': '#155e86', 'soft': '#124868'},
    'gray': {'stroke': '#a1a1aa', 'fill': '#52525b', 'soft': '#3f3f46'},
    'slate': {'stroke': '#94a3b8', 'fill': '#334155', 'soft': '#263445'},
}

CARD_W = 504
CARD_H = 232
TOP = 320
LEFT = 88
GAP_X = 34
GAP_Y = 34
HEADER_H = 56
INNER_PAD = 26
CHIP_H = 36
CHIP_GAP_X = 14
CHIP_GAP_Y = 14
CANVAS_W = 1760
CANVAS_H = 1176
COL3_W = 138
COL2_W = 196
SINGLE_W = 198
EXTRA_W = 146
EXTRA_W_WIDE = 168


def esc(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def fit_label(label: str, max_chars: int) -> str:
    if len(label) <= max_chars:
        return label
    return label[: max_chars - 1].rstrip() + '…'


def render_chip(x, y, w, label, fill, stroke, text_cls='chip', h=CHIP_H, rx=12):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>'
        f'<text x="{x + 16}" y="{y + 23}" class="{text_cls}">{esc(label)}</text>'
    )


def layout_positions(group):
    layout = group['layout']
    items = group['items']
    extras = group.get('extras', [])
    positions = []

    y1 = 104
    y2 = y1 + CHIP_H + CHIP_GAP_Y
    y3 = y2 + CHIP_H + CHIP_GAP_Y

    if layout == 'single':
        positions.append(('primary', fit_label(items[0], 18), INNER_PAD, y1, SINGLE_W))
        return positions

    if layout == '2col-wide':
        x_positions = [INNER_PAD, INNER_PAD + COL2_W + CHIP_GAP_X]
        for idx, label in enumerate(items[:2]):
            positions.append(('primary', fit_label(label, 24), x_positions[idx], y1, COL2_W))
        return positions

    x_positions = [INNER_PAD, INNER_PAD + COL3_W + CHIP_GAP_X, INNER_PAD + (COL3_W + CHIP_GAP_X) * 2]
    for idx, label in enumerate(items[:6]):
        row = 0 if idx < 3 else 1
        col = idx % 3
        y = y1 if row == 0 else y2
        positions.append(('primary', fit_label(label, 16), x_positions[col], y, COL3_W))

    extra_x = INNER_PAD
    for idx, label in enumerate(extras[:4]):
        positions.append(('extra', fit_label(label, 18), extra_x, y3, EXTRA_W_WIDE if len(label) > 14 else EXTRA_W))
        extra_x += (EXTRA_W_WIDE if len(label) > 14 else EXTRA_W) + CHIP_GAP_X
    return positions


def card(group, x, y):
    accent = ACCENTS[group['accent']]
    parts = [
        '<g>',
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="28" fill="url(#panel)" stroke="{accent["stroke"]}" stroke-width="2.4" filter="url(#shadow)"/>',
        f'<path d="M {x+28} {y} H {x+CARD_W-28} Q {x+CARD_W} {y} {x+CARD_W} {y+28} V {y+HEADER_H} H {x} V {y+28} Q {x} {y} {x+28} {y} Z" fill="{accent["fill"]}"/>',
        f'<text x="{x + 26}" y="{y + 34}" class="title2">{esc(group["title"])}</text>',
        f'<text x="{x + CARD_W - 26}" y="{y + 34}" class="ip" text-anchor="end">{esc(group["ip"])}</text>',
        f'<text x="{x + 26}" y="{y + 86}" class="meta">{esc(group["subtitle"])}</text>'
    ]

    for kind, label, dx, dy, w in layout_positions(group):
        if kind == 'primary':
            fill = accent['soft']
            stroke = accent['stroke']
        else:
            fill = '#1b2437'
            stroke = '#42536b'
        parts.append(render_chip(x + dx, y + dy, w, label, fill, stroke))

    note = group.get('note')
    if note:
        parts.append(f'<text x="{x + 26}" y="{y + CARD_H - 18}" class="note">{esc(note)}</text>')

    parts.append('</g>')
    return '\n'.join(parts)


def header(title, subtitle, networks, legend):
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" role="img" aria-labelledby="title desc">
  <title id="title">{esc(title)}</title>
  <desc id="desc">{esc(subtitle)}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b1220"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#182236"/>
      <stop offset="100%" stop-color="#121a2b"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#020617" flood-opacity="0.36"/>
    </filter>
    <style>
      .title1 {{ font: 700 40px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .subtitle1 {{ font: 400 18px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .title2 {{ font: 700 18px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .meta {{ font: 400 14px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .ip {{ font: 700 14px Inter,Segoe UI,Arial,sans-serif; fill: #dbe4ee; }}
      .chip {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .legendTitle {{ font: 700 16px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .legendText {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .note {{ font: 500 12px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
    </style>
  </defs>
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="url(#bg)"/>
  <text x="56" y="64" class="title1">{esc(title)}</text>
  <text x="56" y="96" class="subtitle1">{esc(subtitle)}</text>
  <rect x="36" y="126" width="1688" height="1008" rx="32" fill="rgba(15,23,42,0.58)" stroke="#334155" stroke-width="2.2" filter="url(#shadow)"/>
''']

    x = 56
    y = 144
    widths = [250, 280, 300]
    for i, net in enumerate(networks):
        accent = ACCENTS[net['accent']]
        w = widths[i]
        parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="42" rx="14" fill="#111827" stroke="{accent["stroke"]}" stroke-width="1.8"/>')
        parts.append(f'<text x="{x + 16}" y="{y + 26}" class="meta">{esc(net["label"])}</text>')
        x += w + 18

    lx, ly, lw, lh = 1180, 144, 512, 124
    parts.append(f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="20" fill="#0f172a" stroke="#334155" stroke-width="1.8"/>')
    parts.append(f'<text x="{lx + 18}" y="{ly + 28}" class="legendTitle">Legend</text>')
    for idx, item in enumerate(legend):
        accent = ACCENTS[item['accent']]
        col = idx % 2
        row = idx // 2
        px = lx + 18 + col * 242
        py = ly + 50 + row * 28
        parts.append(f'<rect x="{px}" y="{py}" width="14" height="14" rx="4" fill="{accent["fill"]}" stroke="{accent["stroke"]}"/>')
        parts.append(f'<text x="{px + 24}" y="{py + 12}" class="legendText">{esc(item["label"])}</text>')
    return '\n'.join(parts)


def main():
    data = json.loads(DATA.read_text())
    parts = [header(data['title'], data['subtitle'], data['networks'], data['legend'])]

    for idx, group in enumerate(data['groups']):
        row = idx // 3
        col = idx % 3
        x = LEFT + col * (CARD_W + GAP_X)
        y = TOP + row * (CARD_H + GAP_Y)
        parts.append(card(group, x, y))

    parts.append('</svg>\n')
    OUT.write_text('\n'.join(parts))
    print(f'Wrote {OUT}')


if __name__ == '__main__':
    main()

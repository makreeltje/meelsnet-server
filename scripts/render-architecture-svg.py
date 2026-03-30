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
CARD_H = 228
TOP = 320
LEFT = 88
GAP_X = 34
GAP_Y = 34
HEADER_H = 56
COLS = 3
INNER_PAD = 26
CHIP_H = 36
CHIP_GAP = 12
EXTRA_H = 34
NOTE_H = 18
CANVAS_W = 1760
CANVAS_H = 1170


def esc(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def chip_w(label: str, wide=False):
    base = 16 + len(label) * 7.4
    if wide:
        return min(320, max(150, int(base)))
    return min(190, max(132, int(base)))


def layout_positions(layout, items, extras):
    positions = []
    x0 = INNER_PAD
    y = 104

    if layout == 'single':
        positions.append(('primary', items[0], x0, y, 180))
        return positions

    if layout == '2col-wide':
        x = x0
        for i, label in enumerate(items):
            w = chip_w(label, wide=True)
            positions.append(('primary', label, x, y, w))
            x += w + CHIP_GAP
        return positions

    x_positions = [x0, x0 + 150, x0 + 300]
    for idx, label in enumerate(items):
        row = idx // COLS
        col = idx % COLS
        positions.append(('primary', label, x_positions[col], y + row * (CHIP_H + 14), 118 if len(label) < 10 else 132))

    extra_y = y + ((len(items) + COLS - 1) // COLS) * (CHIP_H + 14) + 6
    x = x0
    for label in extras:
        w = chip_w(label)
        if x + w > CARD_W - INNER_PAD:
            extra_y += EXTRA_H
            x = x0
        positions.append(('extra', label, x, extra_y, w))
        x += w + CHIP_GAP
    return positions


def render_chip(x, y, w, label, fill, stroke, text_cls='chip', h=CHIP_H, rx=12):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>'
        f'<text x="{x + 16}" y="{y + 23}" class="{text_cls}">{esc(label)}</text>'
    )


def card(group, x, y):
    accent = ACCENTS[group['accent']]
    parts = [
        f'<g>',
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="28" fill="url(#panel)" stroke="{accent["stroke"]}" stroke-width="2.4" filter="url(#shadow)"/>',
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{HEADER_H}" rx="28" fill="{accent["fill"]}"/>',
        f'<rect x="{x}" y="{y + HEADER_H - 18}" width="{CARD_W}" height="18" fill="{accent["fill"]}"/>',
        f'<text x="{x + 26}" y="{y + 34}" class="title2">{esc(group["title"])}</text>',
        f'<text x="{x + CARD_W - 26}" y="{y + 34}" class="ip" text-anchor="end">{esc(group["ip"])}</text>',
        f'<text x="{x + 26}" y="{y + 86}" class="meta">{esc(group["subtitle"])}</text>'
    ]

    for kind, label, dx, dy, w in layout_positions(group['layout'], group['items'], group['extras']):
        if kind == 'primary':
            fill = accent['soft']
            stroke = accent['stroke']
        else:
            fill = '#1b2437'
            stroke = '#42536b'
        parts.append(render_chip(x + dx, y + dy, w, label, fill, stroke))

    if group.get('note'):
        parts.append(f'<text x="{x + 26}" y="{y + CARD_H - 20}" class="note">{esc(group["note"])}</text>')

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
  <rect x="36" y="126" width="1688" height="1000" rx="32" fill="rgba(15,23,42,0.58)" stroke="#334155" stroke-width="2.2" filter="url(#shadow)"/>
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

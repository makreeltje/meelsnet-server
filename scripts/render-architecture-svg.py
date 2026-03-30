#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'assets' / 'architecture.json'
OUT = ROOT / 'docs' / 'assets' / 'architecture.svg'

ACCENTS = {
    'green': {'stroke': '#34d399', 'fill': '#0f3d2e'},
    'purple': {'stroke': '#c084fc', 'fill': '#4c1384'},
    'orange': {'stroke': '#fb923c', 'fill': '#6a3415'},
    'blue': {'stroke': '#60a5fa', 'fill': '#22356f'},
    'cyan': {'stroke': '#38bdf8', 'fill': '#155e86'},
    'gray': {'stroke': '#a1a1aa', 'fill': '#52525b'},
    'slate': {'stroke': '#94a3b8', 'fill': '#334155'},
}

CARD_W = 504
CARD_H = 244
LEFT = 88
TOP = 320
GAP_X = 34
GAP_Y = 34
CANVAS_W = 1760
CANVAS_H = 1210


def esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def split_cols(items):
    left = items[::2]
    right = items[1::2]
    return left, right


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
      <feDropShadow dx="0" dy="12" stdDeviation="16" flood-color="#020617" flood-opacity="0.34"/>
    </filter>
    <style>
      .title1 {{ font: 700 40px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .subtitle1 {{ font: 400 18px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .title2 {{ font: 700 18px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .meta {{ font: 400 14px Inter,Segoe UI,Arial,sans-serif; fill: #a8b3c7; }}
      .ip {{ font: 700 14px Inter,Segoe UI,Arial,sans-serif; fill: #dbe4ee; }}
      .svc {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .bullet {{ font: 700 13px Inter,Segoe UI,Arial,sans-serif; fill: #cbd5e1; }}
      .legendTitle {{ font: 700 16px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .legendText {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .footer {{ font: 500 12px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
    </style>
  </defs>
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="url(#bg)"/>
  <text x="56" y="64" class="title1">{esc(title)}</text>
  <text x="56" y="96" class="subtitle1">{esc(subtitle)}</text>
  <rect x="36" y="126" width="1688" height="1040" rx="32" fill="rgba(15,23,42,0.58)" stroke="#334155" stroke-width="2.2" filter="url(#shadow)"/>
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


def card(group, x, y):
    accent = ACCENTS[group['accent']]
    left, right = split_cols(group['services'])

    parts = [
        '<g>',
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="28" fill="url(#panel)" stroke="{accent["stroke"]}" stroke-width="2.4" filter="url(#shadow)"/>',
        f'<path d="M {x+28} {y} H {x+CARD_W-28} Q {x+CARD_W} {y} {x+CARD_W} {y+28} V {y+58} H {x} V {y+28} Q {x} {y} {x+28} {y} Z" fill="{accent["fill"]}"/>',
        f'<text x="{x + 26}" y="{y + 34}" class="title2">{esc(group["title"])}</text>',
        f'<text x="{x + CARD_W - 26}" y="{y + 34}" class="ip" text-anchor="end">{esc(group["ip"])}</text>',
        f'<text x="{x + 26}" y="{y + 86}" class="meta">{esc(group["subtitle"])}</text>',
        f'<line x1="{x + 246}" y1="{y + 106}" x2="{x + 246}" y2="{y + CARD_H - 26}" stroke="#334155" stroke-width="1" opacity="0.9"/>'
    ]

    start_y = y + 126
    step = 26
    for idx, label in enumerate(left[:4]):
        yy = start_y + idx * step
        parts.append(f'<text x="{x + 28}" y="{yy}" class="bullet">•</text>')
        parts.append(f'<text x="{x + 44}" y="{yy}" class="svc">{esc(label)}</text>')
    for idx, label in enumerate(right[:4]):
        yy = start_y + idx * step
        parts.append(f'<text x="{x + 266}" y="{yy}" class="bullet">•</text>')
        parts.append(f'<text x="{x + 282}" y="{yy}" class="svc">{esc(label)}</text>')

    footer = group.get('footer')
    if footer:
        parts.append(f'<text x="{x + 26}" y="{y + CARD_H - 18}" class="footer">{esc(footer)}</text>')

    parts.append('</g>')
    return '\n'.join(parts)


def main():
    data = json.loads(DATA.read_text())
    parts = [header(data['title'], data['subtitle'], data['networks'], data['legend'])]
    for idx, group in enumerate(data['groups']):
        row = idx // 3
        col = idx % 3
        x = LEFT + col * (CARD_W + GAP_X)
        y = TOP + row * (CARD_H + 34)
        parts.append(card(group, x, y))
    parts.append('</svg>\n')
    OUT.write_text('\n'.join(parts))
    print(f'Wrote {OUT}')


if __name__ == '__main__':
    main()

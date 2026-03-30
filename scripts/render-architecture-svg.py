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
CARD_H = 212
LEFT = 88
TOP = 430
GAP_X = 34
GAP_Y = 30
CANVAS_W = 1760
CANVAS_H = 1208
PANEL_Y = 126
HEADER_H = 54


def esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + '…'


def render_top(title, subtitle, networks, legend, host_specs):
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
      <feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#020617" flood-opacity="0.28"/>
    </filter>
    <style>
      .title1 {{ font: 700 40px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .subtitle1 {{ font: 400 18px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .title2 {{ font: 700 18px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .meta {{ font: 400 14px Inter,Segoe UI,Arial,sans-serif; fill: #a8b3c7; }}
      .specs {{ font: 600 12px Inter,Segoe UI,Arial,sans-serif; fill: #cbd5e1; }}
      .ip {{ font: 700 14px Inter,Segoe UI,Arial,sans-serif; fill: #dbe4ee; }}
      .service {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .serviceMuted {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #cbd5e1; }}
      .legendTitle {{ font: 700 16px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .legendText {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .hostTitle {{ font: 700 18px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .hostMeta {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #dbe4ee; }}
      .footer {{ font: 500 12px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
    </style>
  </defs>
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="url(#bg)"/>
  <text x="56" y="64" class="title1">{esc(title)}</text>
  <text x="56" y="96" class="subtitle1">{esc(subtitle)}</text>
  <rect x="36" y="{PANEL_Y}" width="1688" height="1046" rx="32" fill="rgba(15,23,42,0.58)" stroke="#334155" stroke-width="2.2" filter="url(#shadow)"/>
''']

    nx = 56
    ny = 144
    widths = [250, 280, 300]
    for i, net in enumerate(networks):
        accent = ACCENTS[net['accent']]
        w = widths[i]
        parts.append(f'<rect x="{nx}" y="{ny}" width="{w}" height="42" rx="14" fill="#111827" stroke="{accent["stroke"]}" stroke-width="1.8"/>')
        parts.append(f'<text x="{nx + 16}" y="{ny + 26}" class="meta">{esc(net["label"])}</text>')
        nx += w + 18

    hx, hy, hw, hh = 56, 206, 1080, 126
    parts.append(f'<rect x="{hx}" y="{hy}" width="{hw}" height="{hh}" rx="24" fill="#0f172a" stroke="#334155" stroke-width="1.8"/>')
    parts.append(f'<text x="{hx + 22}" y="{hy + 32}" class="hostTitle">Host summary · {esc(host_specs["host"])}</text>')
    parts.append(f'<text x="{hx + 22}" y="{hy + 58}" class="meta">{esc(host_specs["platform"])}</text>')
    host_items = [host_specs['cpu'], host_specs['memory'], host_specs['boot'], host_specs['storage']]
    item_x = [hx + 22, hx + 246, hx + 470, hx + 694]
    widths = [190, 190, 190, 360]
    for px, item, w in zip(item_x, host_items, widths):
        parts.append(f'<rect x="{px}" y="{hy + 76}" width="{w}" height="32" rx="11" fill="#172033" stroke="#475569"/>')
        parts.append(f'<text x="{px + 14}" y="{hy + 97}" class="hostMeta">{esc(item)}</text>')

    lx, ly, lw, lh = 1164, 206, 528, 126
    parts.append(f'<rect x="{lx}" y="{ly}" width="{lw}" height="{lh}" rx="24" fill="#0f172a" stroke="#334155" stroke-width="1.8"/>')
    parts.append(f'<text x="{lx + 18}" y="{ly + 32}" class="legendTitle">Legend</text>')
    for idx, item in enumerate(legend):
        accent = ACCENTS[item['accent']]
        col = idx % 2
        row = idx // 2
        px = lx + 18 + col * 248
        py = ly + 50 + row * 24
        parts.append(f'<rect x="{px}" y="{py}" width="14" height="14" rx="4" fill="{accent["fill"]}" stroke="{accent["stroke"]}"/>')
        parts.append(f'<text x="{px + 24}" y="{py + 12}" class="legendText">{esc(item["label"])}</text>')
    return '\n'.join(parts)


def render_card(group, x, y):
    accent = ACCENTS[group['accent']]
    services = group['services'][:8]
    left = services[:4]
    right = services[4:8]
    parts = [
        '<g>',
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="22" fill="url(#panel)" stroke="{accent["stroke"]}" stroke-width="2.0" filter="url(#shadow)"/>',
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{HEADER_H}" rx="22" fill="{accent["fill"]}"/>',
        f'<rect x="{x}" y="{y + HEADER_H - 16}" width="{CARD_W}" height="16" fill="{accent["fill"]}"/>',
        f'<text x="{x + 22}" y="{y + 33}" class="title2">{esc(group["title"])}</text>',
        f'<text x="{x + CARD_W - 22}" y="{y + 33}" class="ip" text-anchor="end">{esc(group["ip"])}</text>',
        f'<text x="{x + 22}" y="{y + 78}" class="specs">{esc(group.get("specs", ""))}</text>',
        f'<text x="{x + 22}" y="{y + 98}" class="meta">{esc(group["subtitle"])}</text>'
    ]

    start_y = y + 126
    step = 18
    for idx, label in enumerate(left):
        yy = start_y + idx * step
        cls = 'service' if idx < 2 else 'serviceMuted'
        parts.append(f'<text x="{x + 22}" y="{yy}" class="{cls}">{esc(truncate(label, 24))}</text>')
    for idx, label in enumerate(right):
        yy = start_y + idx * step
        cls = 'service' if idx < 2 else 'serviceMuted'
        parts.append(f'<text x="{x + 274}" y="{yy}" class="{cls}">{esc(truncate(label, 24))}</text>')

    footer = group.get('footer', '')
    if footer:
        parts.append(f'<text x="{x + 22}" y="{y + CARD_H - 18}" class="footer">{esc(footer)}</text>')
    parts.append('</g>')
    return '\n'.join(parts)


def main():
    data = json.loads(DATA.read_text())
    parts = [render_top(data['title'], data['subtitle'], data['networks'], data['legend'], data['hostSpecs'])]
    for idx, group in enumerate(data['groups']):
        row = idx // 3
        col = idx % 3
        x = LEFT + col * (CARD_W + GAP_X)
        y = TOP + row * (CARD_H + GAP_Y)
        parts.append(render_card(group, x, y))
    parts.append('</svg>\n')
    OUT.write_text('\n'.join(parts))
    print(f'Wrote {OUT}')


if __name__ == '__main__':
    main()

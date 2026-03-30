#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'assets' / 'architecture.json'
OUT_DARK = ROOT / 'docs' / 'assets' / 'architecture-dark.svg'
OUT_LIGHT = ROOT / 'docs' / 'assets' / 'architecture-light.svg'

ACCENTS = {
    'green': {'stroke': '#34d399', 'fill': '#0f3d2e', 'light_fill': '#dcfce7', 'light_stroke': '#22c55e'},
    'purple': {'stroke': '#c084fc', 'fill': '#4c1384', 'light_fill': '#f3e8ff', 'light_stroke': '#a855f7'},
    'orange': {'stroke': '#fb923c', 'fill': '#6a3415', 'light_fill': '#ffedd5', 'light_stroke': '#f97316'},
    'blue': {'stroke': '#60a5fa', 'fill': '#22356f', 'light_fill': '#dbeafe', 'light_stroke': '#3b82f6'},
    'cyan': {'stroke': '#38bdf8', 'fill': '#155e86', 'light_fill': '#cffafe', 'light_stroke': '#06b6d4'},
    'gray': {'stroke': '#a1a1aa', 'fill': '#52525b', 'light_fill': '#f4f4f5', 'light_stroke': '#71717a'},
    'slate': {'stroke': '#94a3b8', 'fill': '#334155', 'light_fill': '#e2e8f0', 'light_stroke': '#64748b'},
}

CARD_W = 504
CARD_H = 212
LEFT = 88
TOP = 396
GAP_X = 34
GAP_Y = 30
CANVAS_W = 1760
CANVAS_H = 1170
PANEL_Y = 126
HEADER_H = 54
GRID_W = CARD_W * 3 + GAP_X * 2

THEMES = {
    'dark': {
        'bg1': '#0b1220',
        'bg2': '#111827',
        'panel1': '#182236',
        'panel2': '#121a2b',
        'outer_fill': 'rgba(15,23,42,0.58)',
        'outer_stroke': '#334155',
        'card_stroke': None,
        'text_main': '#f8fafc',
        'text_sub': '#94a3b8',
        'text_meta': '#a8b3c7',
        'text_specs': '#cbd5e1',
        'text_service': '#e2e8f0',
        'text_service_muted': '#cbd5e1',
        'text_ip': '#dbe4ee',
        'panel_fill': '#0f172a',
        'subpanel_fill': '#172033',
        'subpanel_stroke': '#475569',
        'shadow': '0.28'
    },
    'light': {
        'bg1': '#f8fafc',
        'bg2': '#e2e8f0',
        'panel1': '#ffffff',
        'panel2': '#f8fafc',
        'outer_fill': 'rgba(255,255,255,0.92)',
        'outer_stroke': '#cbd5e1',
        'card_stroke': '#cbd5e1',
        'text_main': '#0f172a',
        'text_sub': '#475569',
        'text_meta': '#64748b',
        'text_specs': '#475569',
        'text_service': '#0f172a',
        'text_service_muted': '#334155',
        'text_ip': '#1e293b',
        'panel_fill': '#ffffff',
        'subpanel_fill': '#f8fafc',
        'subpanel_stroke': '#cbd5e1',
        'shadow': '0.12'
    }
}


def esc(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + '…'


def render_top(title, subtitle, networks, legend, host_specs, theme_name):
    theme = THEMES[theme_name]
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" role="img" aria-labelledby="title desc">
  <title id="title">{esc(title)} ({theme_name})</title>
  <desc id="desc">{esc(subtitle)}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{theme['bg1']}"/>
      <stop offset="100%" stop-color="{theme['bg2']}"/>
    </linearGradient>
    <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{theme['panel1']}"/>
      <stop offset="100%" stop-color="{theme['panel2']}"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#020617" flood-opacity="{theme['shadow']}"/>
    </filter>
    <style>
      .title1 {{ font: 700 40px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_main']}; }}
      .subtitle1 {{ font: 400 18px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_sub']}; }}
      .title2 {{ font: 700 18px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_main']}; }}
      .meta {{ font: 400 14px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_meta']}; }}
      .specs {{ font: 600 12px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_specs']}; }}
      .ip {{ font: 700 14px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_ip']}; }}
      .service {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_service']}; }}
      .serviceMuted {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_service_muted']}; }}
      .legendTitle {{ font: 700 16px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_main']}; }}
      .legendText {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_service']}; }}
      .hostTitle {{ font: 700 18px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_main']}; }}
      .hostMeta {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_service']}; }}
      .footer {{ font: 500 12px Inter,Segoe UI,Arial,sans-serif; fill: {theme['text_meta']}; }}
    </style>
  </defs>
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="url(#bg)"/>
  <text x="56" y="64" class="title1">{esc(title)}</text>
  <text x="56" y="96" class="subtitle1">{esc(subtitle)}</text>
  <rect x="36" y="{PANEL_Y}" width="1688" height="1008" rx="32" fill="{theme['outer_fill']}" stroke="{theme['outer_stroke']}" stroke-width="2.2" filter="url(#shadow)"/>
''']

    nx = 56
    ny = 144
    widths = [250, 280, 300]
    for i, net in enumerate(networks):
        accent = ACCENTS[net['accent']]
        stroke = accent['stroke'] if theme_name == 'dark' else accent['light_stroke']
        fill = '#111827' if theme_name == 'dark' else '#ffffff'
        w = widths[i]
        parts.append(f'<rect x="{nx}" y="{ny}" width="{w}" height="42" rx="14" fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>')
        parts.append(f'<text x="{nx + 16}" y="{ny + 26}" class="meta">{esc(net["label"])}</text>')
        nx += w + 18

    total_w = GRID_W
    host_w = 1084
    legend_w = total_w - host_w - GAP_X
    hx, hy, hh = LEFT, 206, 126
    lx, ly, lh = LEFT + host_w + GAP_X, 206, 126

    parts.append(f'<rect x="{hx}" y="{hy}" width="{host_w}" height="{hh}" rx="24" fill="{theme["panel_fill"]}" stroke="{theme["outer_stroke"]}" stroke-width="1.8"/>')
    parts.append(f'<text x="{hx + 22}" y="{hy + 32}" class="hostTitle">Host summary · {esc(host_specs["host"])}</text>')
    parts.append(f'<text x="{hx + 22}" y="{hy + 58}" class="meta">{esc(host_specs["platform"])}</text>')
    host_items = [host_specs['cpu'], host_specs['memory'], host_specs['boot'], host_specs['storage']]
    item_x = [hx + 22, hx + 246, hx + 470, hx + 694]
    item_w = [190, 190, 190, 368]
    for px, item, w in zip(item_x, host_items, item_w):
        parts.append(f'<rect x="{px}" y="{hy + 76}" width="{w}" height="32" rx="11" fill="{theme["subpanel_fill"]}" stroke="{theme["subpanel_stroke"]}"/>')
        parts.append(f'<text x="{px + 14}" y="{hy + 97}" class="hostMeta">{esc(item)}</text>')

    parts.append(f'<rect x="{lx}" y="{ly}" width="{legend_w}" height="{lh}" rx="24" fill="{theme["panel_fill"]}" stroke="{theme["outer_stroke"]}" stroke-width="1.8"/>')
    parts.append(f'<text x="{lx + 18}" y="{ly + 32}" class="legendTitle">Legend</text>')
    col_gap = 210
    for idx, item in enumerate(legend):
        accent = ACCENTS[item['accent']]
        fill = accent['fill'] if theme_name == 'dark' else accent['light_fill']
        stroke = accent['stroke'] if theme_name == 'dark' else accent['light_stroke']
        col = idx % 2
        row = idx // 2
        px = lx + 18 + col * col_gap
        py = ly + 50 + row * 24
        parts.append(f'<rect x="{px}" y="{py}" width="14" height="14" rx="4" fill="{fill}" stroke="{stroke}"/>')
        parts.append(f'<text x="{px + 24}" y="{py + 12}" class="legendText">{esc(item["label"])}</text>')
    return '\n'.join(parts)


def render_card(group, x, y, theme_name):
    theme = THEMES[theme_name]
    accent = ACCENTS[group['accent']]
    header_fill = accent['fill'] if theme_name == 'dark' else accent['light_fill']
    header_stroke = accent['stroke'] if theme_name == 'dark' else accent['light_stroke']
    card_stroke = header_stroke if theme_name == 'dark' else theme['card_stroke']
    services = group['services'][:8]
    left = services[:4]
    right = services[4:8]
    parts = [
        '<g>',
        f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="22" fill="url(#panel)" stroke="{card_stroke}" stroke-width="2.0" filter="url(#shadow)"/>',
        f'<path d="M {x+22} {y} H {x+CARD_W-22} Q {x+CARD_W} {y} {x+CARD_W} {y+22} V {y+HEADER_H} H {x} V {y+22} Q {x} {y} {x+22} {y} Z" fill="{header_fill}" stroke="{header_stroke}" stroke-width="0"/>',
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


def render(theme_name):
    data = json.loads(DATA.read_text())
    parts = [render_top(data['title'], data['subtitle'], data['networks'], data['legend'], data['hostSpecs'], theme_name)]
    for idx, group in enumerate(data['groups']):
        row = idx // 3
        col = idx % 3
        x = LEFT + col * (CARD_W + GAP_X)
        y = TOP + row * (CARD_H + GAP_Y)
        parts.append(render_card(group, x, y, theme_name))
    parts.append('</svg>\n')
    return ''.join(parts)


def main():
    OUT_DARK.write_text(render('dark'))
    OUT_LIGHT.write_text(render('light'))
    print(f'Wrote {OUT_DARK}')
    print(f'Wrote {OUT_LIGHT}')


if __name__ == '__main__':
    main()

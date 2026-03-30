#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'assets' / 'architecture.json'
OUT = ROOT / 'docs' / 'assets' / 'architecture.svg'

ACCENTS = {
    'green': {'stroke': '#34d399', 'fill': '#0b3b2e'},
    'purple': {'stroke': '#c084fc', 'fill': '#3b0764'},
    'orange': {'stroke': '#fb923c', 'fill': '#3f1d0d'},
    'blue': {'stroke': '#60a5fa', 'fill': '#132033'},
    'cyan': {'stroke': '#38bdf8', 'fill': '#082f49'},
    'gray': {'stroke': '#a1a1aa', 'fill': '#1f2937'},
}

HEADER = '''<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1320" viewBox="0 0 1800 1320" role="img" aria-labelledby="title desc">
  <title id="title">{title}</title>
  <desc id="desc">{subtitle}</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#0b1220"/>
      <stop offset="100%" stop-color="#111827"/>
    </linearGradient>
    <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#172033"/>
      <stop offset="100%" stop-color="#101826"/>
    </linearGradient>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#020617" flood-opacity="0.45"/>
    </filter>
    <style>
      .title {{ font: 700 40px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .subtitle {{ font: 400 18px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .section {{ font: 700 20px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .label {{ font: 700 17px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .meta {{ font: 400 13px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .small {{ font: 500 13px Inter,Segoe UI,Arial,sans-serif; fill: #cbd5e1; }}
      .chip {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
    </style>
  </defs>
  <rect width="1800" height="1320" fill="url(#bg)"/>
  <text x="70" y="78" class="title">{title}</text>
  <text x="70" y="110" class="subtitle">{subtitle}</text>
  <rect x="50" y="145" width="1700" height="1125" rx="34" fill="rgba(15,23,42,0.55)" stroke="#334155" stroke-width="2.5" filter="url(#shadow)"/>
  <text x="78" y="190" class="section">Proxmox host · srv-mn</text>
  <text x="78" y="214" class="meta">vmbr0 = LAN 192.168.2.0/24 · vmbr1 = service network 10.10.0.0/24</text>
'''


def esc(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def chip(x, y, w, label, fill, stroke, cls='chip', h=42, rx=12):
    text_y = y + (27 if h == 42 else 17)
    text_cls = cls if h == 42 else 'small'
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/><text x="{x + 20}" y="{text_y}" class="{text_cls}">{esc(label)}</text>'


def render_networks(networks):
    x = 78
    out = []
    widths = [180, 210, 220, 248]
    for idx, net in enumerate(networks):
        accent = ACCENTS.get(net['accent'], ACCENTS['blue'])['stroke']
        w = widths[idx] if idx < len(widths) else 220
        out.append(f'<g><rect x="{x}" y="242" width="{w}" height="56" rx="16" fill="#0f172a" stroke="{accent}" stroke-width="2"/>'
                   f'<text x="{x + 24}" y="276" class="label">{esc(net["label"])}</text></g>')
        x += w + 22
    return '\n'.join(out)


def render_group(g):
    accent = ACCENTS[g['accent']]
    parts = [
        f'<g><rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="28" fill="url(#panel)" stroke="{accent["stroke"]}" stroke-width="2.3" filter="url(#shadow)"/>',
        f'<text x="{g["x"] + 26}" y="{g["y"] + 38}" class="label">{esc(g["title"])}</text>',
        f'<text x="{g["x"] + 26}" y="{g["y"] + 62}" class="meta">{esc(g["subtitle"])}</text>'
    ]
    for item in g['items']:
        if item['variant'] == 'accent':
            parts.append(chip(item['x'], item['y'], item['w'], item['label'], accent['fill'], accent['stroke']))
        elif item['variant'] in ('default', 'defaultLong'):
            parts.append(chip(item['x'], item['y'], item['w'], item['label'], '#132033', '#60a5fa'))
        elif item['variant'] in ('small', 'smallLong'):
            parts.append(chip(item['x'], item['y'], item['w'], item['label'], '#111827', '#475569', h=24, rx=10))
    parts.append('</g>')
    return '\n'.join(parts)


def legend():
    return '''
  <g>
    <rect x="920" y="902" width="752" height="162" rx="24" fill="#0f172a" stroke="#334155" stroke-width="2"/>
    <text x="948" y="938" class="label">Legend</text>
    <rect x="948" y="960" width="18" height="18" rx="5" fill="#0b3b2e" stroke="#34d399"/><text x="980" y="974" class="small">core infra / ingress / auth</text>
    <rect x="948" y="992" width="18" height="18" rx="5" fill="#3b0764" stroke="#c084fc"/><text x="980" y="1006" class="small">media stack</text>
    <rect x="948" y="1024" width="18" height="18" rx="5" fill="#3f1d0d" stroke="#fb923c"/><text x="980" y="1038" class="small">home automation / MQTT</text>
    <rect x="1250" y="960" width="18" height="18" rx="5" fill="#082f49" stroke="#38bdf8"/><text x="1282" y="974" class="small">monitoring / exporters</text>
    <text x="1250" y="1007" class="small">Diagram intentionally simplified: only key paths are shown.</text>
  </g>
'''


def main():
    data = json.loads(DATA.read_text())
    pieces = [HEADER.format(title=esc(data['title']), subtitle=esc(data['subtitle']))]
    pieces.append(render_networks(data['networks']))
    for group in data['groups']:
        pieces.append(render_group(group))
    pieces.append(legend())
    pieces.append('</svg>\n')
    OUT.write_text('\n'.join(pieces))
    print(f'Wrote {OUT}')


if __name__ == '__main__':
    main()

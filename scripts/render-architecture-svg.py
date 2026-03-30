#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'docs' / 'assets' / 'architecture.json'
OUT = ROOT / 'docs' / 'assets' / 'architecture.svg'

ACCENTS = {
    'green': {'stroke': '#34d399', 'fill': '#0b3b2e', 'soft': '#123528'},
    'purple': {'stroke': '#c084fc', 'fill': '#3b0764', 'soft': '#2e1065'},
    'orange': {'stroke': '#fb923c', 'fill': '#3f1d0d', 'soft': '#4a2410'},
    'blue': {'stroke': '#60a5fa', 'fill': '#132033', 'soft': '#172554'},
    'cyan': {'stroke': '#38bdf8', 'fill': '#082f49', 'soft': '#0c4a6e'},
    'gray': {'stroke': '#a1a1aa', 'fill': '#27272a', 'soft': '#3f3f46'},
    'slate': {'stroke': '#94a3b8', 'fill': '#1e293b', 'soft': '#334155'},
}

CANVAS_W = 1760
CANVAS_H = 1140


def esc(text: str) -> str:
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def chip_width(label: str) -> int:
    return max(120, min(218, 34 + len(label) * 8))


def render_chip(x, y, label, fill, stroke, text_cls='chip', h=36, rx=12):
    w = chip_width(label)
    ty = y + 23
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"/>'
        f'<text x="{x + 16}" y="{ty}" class="{text_cls}">{esc(label)}</text>'
    ), w


def layout_rows(items, x0, y0, max_width, accent):
    rows = []
    current = []
    x = x0
    y = y0
    row_h = 0
    for item in items:
        if item['variant'] == 'footnote':
            if current:
                rows.extend(current)
                current = []
                y += row_h + 14
                x = x0
                row_h = 0
            rows.append(('footnote', item, x0, y))
            y += 30
            continue

        if item['variant'] == 'primary':
            fill = accent['fill']
            stroke = accent['stroke']
        elif item['variant'] == 'secondary':
            fill = accent['soft']
            stroke = accent['stroke']
        else:
            fill = '#111827'
            stroke = '#475569'

        w = chip_width(item['label'])
        if x + w > x0 + max_width:
            rows.extend(current)
            current = []
            y += row_h + 14
            x = x0
            row_h = 0
        current.append(('chip', item, x, y, fill, stroke, w))
        x += w + 12
        row_h = max(row_h, 36)
    rows.extend(current)
    return rows


def render_group(g):
    accent = ACCENTS[g['accent']]
    out = [
        f'<g>',
        f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="{g["h"]}" rx="28" fill="url(#panel)" stroke="{accent["stroke"]}" stroke-width="2.3" filter="url(#shadow)"/>',
        f'<rect x="{g["x"]}" y="{g["y"]}" width="{g["w"]}" height="56" rx="28" fill="{accent["soft"]}" opacity="0.95"/>',
        f'<text x="{g["x"] + 24}" y="{g["y"] + 34}" class="label">{esc(g["title"])}</text>',
        f'<text x="{g["x"] + g["w"] - 24}" y="{g["y"] + 34}" class="ip" text-anchor="end">{esc(g["ip"])}</text>',
        f'<text x="{g["x"] + 24}" y="{g["y"] + 78}" class="meta">{esc(g["subtitle"])}</text>',
    ]

    rows = layout_rows(g['items'], g['x'] + 24, g['y'] + 104, g['w'] - 48, accent)
    for entry in rows:
        if entry[0] == 'footnote':
            _, item, x, y = entry
            out.append(f'<text x="{x}" y="{y}" class="footnote">{esc(item["label"])}</text>')
        else:
            _, item, x, y, fill, stroke, _ = entry
            snippet, _ = render_chip(x, y, item['label'], fill, stroke)
            out.append(snippet)
    out.append('</g>')
    return '\n'.join(out)


def render_header(title, subtitle, networks):
    parts = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" role="img" aria-labelledby="title desc">
  <title id="title">{esc(title)}</title>
  <desc id="desc">{esc(subtitle)}</desc>
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
      <feDropShadow dx="0" dy="12" stdDeviation="18" flood-color="#020617" flood-opacity="0.42"/>
    </filter>
    <style>
      .title {{ font: 700 38px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .subtitle {{ font: 400 18px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .label {{ font: 700 18px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
      .meta {{ font: 400 14px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .ip {{ font: 700 14px Inter,Segoe UI,Arial,sans-serif; fill: #cbd5e1; }}
      .chip {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .footnote {{ font: 500 12px Inter,Segoe UI,Arial,sans-serif; fill: #94a3b8; }}
      .legend {{ font: 600 13px Inter,Segoe UI,Arial,sans-serif; fill: #e2e8f0; }}
      .legendTitle {{ font: 700 16px Inter,Segoe UI,Arial,sans-serif; fill: #f8fafc; }}
    </style>
  </defs>
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="url(#bg)"/>
  <text x="56" y="64" class="title">{esc(title)}</text>
  <text x="56" y="96" class="subtitle">{esc(subtitle)}</text>
  <rect x="36" y="126" width="1688" height="978" rx="32" fill="rgba(15,23,42,0.58)" stroke="#334155" stroke-width="2.2" filter="url(#shadow)"/>
''']

    x = 56
    y = 144
    widths = [246, 270, 288]
    for i, n in enumerate(networks):
        accent = ACCENTS[n['accent']]
        w = widths[i] if i < len(widths) else 240
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="42" rx="14" fill="#0f172a" stroke="{accent["stroke"]}" stroke-width="1.8"/>'
            f'<text x="{x + 16}" y="{y + 26}" class="meta" fill="#e2e8f0">{esc(n["label"])}</text>'
        )
        x += w + 16
    return '\n'.join(parts)


def render_legend(items):
    x = 1180
    y = 144
    out = [
        f'<rect x="{x}" y="{y}" width="512" height="124" rx="20" fill="#0f172a" stroke="#334155" stroke-width="1.8"/>',
        f'<text x="{x + 18}" y="{y + 28}" class="legendTitle">Legend</text>'
    ]
    lx = x + 18
    ly = y + 50
    for idx, item in enumerate(items):
        accent = ACCENTS[item['accent']]
        col = idx % 2
        row = idx // 2
        px = lx + col * 240
        py = ly + row * 28
        out.append(f'<rect x="{px}" y="{py}" width="14" height="14" rx="4" fill="{accent["fill"]}" stroke="{accent["stroke"]}"/>')
        out.append(f'<text x="{px + 24}" y="{py + 12}" class="legend">{esc(item["label"])}</text>')
    return '\n'.join(out)


def main():
    data = json.loads(DATA.read_text())
    parts = [render_header(data['title'], data['subtitle'], data['networks'])]
    parts.append(render_legend(data['legend']))
    for group in data['groups']:
        parts.append(render_group(group))
    parts.append('</svg>\n')
    OUT.write_text('\n'.join(parts))
    print(f'Wrote {OUT}')


if __name__ == '__main__':
    main()

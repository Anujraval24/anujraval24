#!/usr/bin/env python3
"""Render the profile README cards as animated SVGs.

    python scripts/render_cards.py            # animated cards -> cards/
    STATIC=1 python scripts/render_cards.py   # final frame, no animation -> cards-static/

The cards are displayed through <img> tags, so everything is self-contained:
an inline <style> with CSS keyframes, and fonts subset with pyftsubset and
embedded as base64 WOFF data URIs. Every animation is switched off under
prefers-reduced-motion. (SMIL <animate> is deliberately not used: it cannot be
turned off from CSS, so it would ignore that setting.)

Inputs : data/profile.json, data/contributions.json (refreshed daily by the Action)
Outputs: hero.svg, tile-<key>.svg, chart.svg, repo-<name>.svg, graph.svg
"""
import base64
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
STATIC = os.environ.get("STATIC") == "1"
OUT = ROOT / ("cards-static" if STATIC else "cards")
W = 830  # card width; README shows cards at width="100%"

PROFILE = json.loads((ROOT / "data" / "profile.json").read_text())
DATA = json.loads((ROOT / "data" / "contributions.json").read_text())
B = PROFILE["brand"]
GROUND, DEEP, RIM = B["ground"], B["ground_deep"], B["rim"]
TEXT, MUTED, BRAND, RAMP = B["text"], B["muted"], B["turmeric"], B["ramp"]

FONT_FILES = {
    400: ROOT / "fonts" / "bricolage-grotesque-latin-400-normal.woff",
    600: ROOT / "fonts" / "bricolage-grotesque-latin-600-normal.woff",
    800: ROOT / "fonts" / "bricolage-grotesque-latin-800-normal.woff",
}
FACES = {w: TTFont(str(p)) for w, p in FONT_FILES.items()}
CMAPS = {w: f.getBestCmap() for w, f in FACES.items()}
HMTX = {w: f["hmtx"] for w, f in FACES.items()}
UPEM = FACES[400]["head"].unitsPerEm

LANG_COLORS = {
    "JavaScript": "#f1e05a", "TypeScript": "#3178c6", "Java": "#b07219",
    "HTML": "#e34c26", "Python": "#3572A5", "CSS": "#563d7c", "Shell": "#89e051",
}

# Where each card starts on the page timeline (seconds), so the page plays top to bottom.
STAGE = {"hero": 0.0, "tiles": 0.55, "chart": 1.15, "repos": 1.85, "graph": 2.6}


# ----------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=True)


def measure(text, weight, size):
    cmap, hmtx = CMAPS[weight], HMTX[weight]
    total = 0
    for ch in text:
        g = cmap.get(ord(ch))
        total += hmtx[g][0] if g else UPEM * 0.5
    return total * size / UPEM


def wrap(text, weight, size, max_w, max_lines):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if measure(trial, weight, size) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and measure(last + "…", weight, size) > max_w:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return lines


def n(x):
    return f"{x:,}"


_subset_cache = {}


def subset_face(weight, chars):
    chars = "".join(sorted(set(chars) | {" "}))
    key = (weight, chars)
    if key in _subset_cache:
        return _subset_cache[key]
    missing = [c for c in chars if ord(c) not in CMAPS[weight]]
    if missing:
        print(f"warning: glyphs missing from font {weight}: {''.join(missing)!r}", file=sys.stderr)
    exe = shutil.which("pyftsubset") or None
    with tempfile.TemporaryDirectory() as td:
        outp = Path(td) / "s.woff"
        cmd = [exe] if exe else [sys.executable, "-m", "fontTools.subset"]
        cmd += [
            str(FONT_FILES[weight]), f"--text={chars}", "--flavor=woff",
            "--layout-features=kern", "--no-hinting", f"--output-file={outp}",
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        b64 = base64.b64encode(outp.read_bytes()).decode()
    _subset_cache[key] = b64
    return b64


class Card:
    """Collects SVG parts and the exact characters each font weight needs."""

    def __init__(self, name, height, label, stage, width=W):
        self.name, self.h, self.label, self.stage, self.w = name, height, label, stage, width
        self.parts, self.chars = [], {400: set(), 600: set(), 800: set()}

    def add(self, s):
        self.parts.append(s)

    def anim(self, cls, delay=0.0, extra=""):
        if STATIC:
            return f' class="{extra}"' if extra else ""
        d = self.stage + delay
        cls_all = f"a {cls} {extra}".strip()
        return f' class="{cls_all}" style="animation-delay:{d:.2f}s"'

    def text(self, x, y, s, weight=400, size=16, fill=TEXT, anchor="start", cls="up", delay=0.0):
        self.chars[weight].update(s)
        self.add(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
            f'fill="{fill}" text-anchor="{anchor}"{self.anim(cls, delay)}>{esc(s)}</text>'
        )

    def rich(self, x, y, runs, cls="up", delay=0.0):
        """runs: [(text, weight, size, fill, dx)] inside one <text>."""
        spans = []
        for s, wt, size, fill, dx in runs:
            self.chars[wt].update(s)
            dxa = f' dx="{dx}"' if dx else ""
            spans.append(f'<tspan font-weight="{wt}" font-size="{size}" fill="{fill}"{dxa}>{esc(s)}</tspan>')
        self.add(f'<text x="{x}" y="{y}"{self.anim(cls, delay)}>{"".join(spans)}</text>')

    def style(self):
        faces = "".join(
            f"@font-face{{font-family:'Bric';font-weight:{w};font-style:normal;"
            f"src:url(data:font/woff;base64,{subset_face(w, c)}) format('woff')}}"
            for w, c in self.chars.items() if c
        )
        css = faces + "text{font-family:'Bric',system-ui,sans-serif}"
        if not STATIC:
            css += (
                ".a{animation-duration:.75s;animation-timing-function:cubic-bezier(.2,.7,.2,1);"
                "animation-fill-mode:both}"
                ".up{animation-name:up}"
                "@keyframes up{from{opacity:0;transform:translateY(12px)}}"
                ".fade{animation-name:fade}"
                "@keyframes fade{from{opacity:0}}"
                ".grow{animation-name:grow;transform-box:fill-box;transform-origin:50% 100%}"
                "@keyframes grow{from{transform:scaleY(0)}}"
                ".pop{animation-name:pop;animation-duration:.5s;transform-box:fill-box;transform-origin:50% 50%}"
                "@keyframes pop{from{opacity:0;transform:scale(.3)}}"
                "@media (prefers-reduced-motion:reduce){.a{animation:none!important}}"
            )
        return css

    def render(self):
        body = "".join(self.parts)  # build first so every glyph is registered
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{esc(self.label)}">'
            f"<title>{esc(self.label)}</title><style>{self.style()}</style>"
            f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="18" fill="{GROUND}" stroke="{RIM}"/>'
            f"{body}</svg>\n"
        )

    def save(self):
        OUT.mkdir(parents=True, exist_ok=True)
        path = OUT / f"{self.name}.svg"
        path.write_text(self.render(), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.1f} KB")


def diamond(cx, cy, r):
    return f"M{cx:.1f} {cy - r:.1f}L{cx + r:.1f} {cy:.1f}L{cx:.1f} {cy + r:.1f}L{cx - r:.1f} {cy:.1f}Z"


# ------------------------------------------------------------ data derivations
DAYS = [(date.fromisoformat(d["date"]), d["count"]) for d in DATA["days"]]
TODAY = DAYS[-1][0]
TOTAL = DATA.get("total") or sum(c for _, c in DAYS)


def years_working():
    y, m = map(int, PROFILE["career_start"].split("-"))
    return max(1, int((TODAY - date(y, m, 1)).days // 365.25))


def streaks():
    longest = run = 0
    for _, c in DAYS:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    i = len(DAYS) - 1
    if DAYS[i][1] == 0:  # today may not have a contribution yet
        i -= 1
    cur = 0
    while i >= 0 and DAYS[i][1] > 0:
        cur += 1
        i -= 1
    return cur, longest


def monthly():
    months, y, m = [], TODAY.year, TODAY.month
    for _ in range(12):
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    sums = {k: 0 for k in months}
    for d, c in DAYS:
        if (d.year, d.month) in sums:
            sums[(d.year, d.month)] += c
    return [(date(y, m, 1).strftime("%b"), sums[(y, m)]) for y, m in months]


def fmt_day(d):
    return f"{d.strftime('%b')} {d.day}"


# ------------------------------------------------------------------- cards
def hero():
    c = Card("hero", 300, f"{PROFILE['name']}, {PROFILE['role']}", STAGE["hero"])
    # Block-print lattice, printed in a diagonal sweep: the one big moment on the page.
    cx, cy, pitch = 668, 150, 28
    cols, rows = 11, 11
    x0, y0 = 520, 20
    for r in range(rows):
        for col in range(cols):
            x = x0 + col * pitch + (pitch / 2 if r % 2 else 0)
            y = y0 + r * (pitch * 0.92)
            if math.hypot(x - cx, y - cy) < 96 or x > W - 22:
                continue
            strength = (x - x0) / (cols * pitch)
            op = 0.10 + 0.62 * strength
            delay = 0.35 + 0.045 * (col + r)
            c.add(f'<path d="{diamond(x, y, 7.5)}" fill="{BRAND}" opacity="{op:.2f}"{c.anim("pop", delay)}/>')
            if (col + r) % 3 == 0:
                c.add(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="{GROUND}"{c.anim("pop", delay + 0.05)}/>')

    # Portrait if configured, otherwise a monogram.
    portrait = PROFILE.get("portrait")
    ppath = ROOT / portrait if portrait else None
    c.add(f'<circle cx="{cx}" cy="{cy}" r="74" fill="{DEEP}" stroke="{BRAND}" stroke-width="3"{c.anim("pop", 0.2)}/>')
    if ppath and ppath.exists():
        raw = ppath.read_bytes()
        mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
        c.add(
            f'<clipPath id="pc"><circle cx="{cx}" cy="{cy}" r="68"/></clipPath>'
            f'<image href="data:{mime};base64,{base64.b64encode(raw).decode()}" x="{cx - 68}" y="{cy - 68}" '
            f'width="136" height="136" preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"{c.anim("fade", 0.35)}/>'
        )
    else:
        initials = "".join(p[0] for p in PROFILE["name"].split()[:2]).upper()
        c.text(cx, cy + 20, initials, 800, 56, BRAND, "middle", "fade", 0.3)

    c.text(48, 128, PROFILE["name"], 800, 78, TEXT, "start", "up", 0.1)
    tagline = PROFILE["tagline"].replace("{years}", str(years_working()))
    for i, line in enumerate(wrap(tagline, 400, 23, 440, 3)):
        c.text(48, 176 + i * 31, line, 400, 23, TEXT, "start", "up", 0.3 + i * 0.08)
    c.text(48, 262, PROFILE["role"], 600, 16, BRAND, "start", "up", 0.55)
    c.save()


def tile(spec):
    key = spec["key"]
    order = [t["key"] for t in PROFILE["tiles"]].index(key)
    c = Card(f"tile-{key}", 190, f"{spec['title']}: {spec['sub']}", STAGE["tiles"] + 0.1 * order, width=400)
    # Corner stamp: a 3x3 block of diamonds.
    for i in range(3):
        for j in range(3):
            if (i + j) % 2 == 0:
                c.add(f'<path d="{diamond(330 + i * 16, 36 + j * 16, 6)}" fill="{BRAND}"{c.anim("pop", 0.1 + 0.05 * (i + j))}/>')
    c.text(28, 112, spec["title"], 800, 44, TEXT, "start", "up", 0.15)
    c.text(28, 148, spec["sub"], 400, 20, MUTED, "start", "up", 0.25)
    # Arrow drawn as a path (the font has no arrow glyph).
    c.add(
        f'<path d="M318 150 L350 150 M338 138 L350 150 L338 162" fill="none" stroke="{BRAND}" stroke-width="3.5" '
        f'stroke-linecap="round" stroke-linejoin="round"{c.anim("fade", 0.4)}/>'
    )
    c.save()


def chart():
    data = monthly()
    cur, longest = streaks()
    active = sum(1 for _, c in DAYS if c > 0)
    busiest = max(DAYS, key=lambda dc: (dc[1], dc[0]))
    c = Card("chart", 340, f"Contributions per month, {n(TOTAL)} in the last year", STAGE["chart"])
    c.text(48, 62, "Contributions per month", 800, 26, TEXT, "start", "up", 0)
    c.text(48, 88, f"{n(TOTAL)} in the last 12 months", 400, 16, MUTED, "start", "up", 0.08)

    base_y, top_y, left, slot = 288, 124, 48, 43.5
    peak = max(v for _, v in data) or 1
    for i, (lab, v) in enumerate(data):
        x = left + i * slot
        h = max(3, (base_y - top_y) * v / peak)
        delay = 0.2 + i * 0.06
        is_peak = v == peak
        c.add(
            f'<rect x="{x:.1f}" y="{base_y - h:.1f}" width="30" height="{h:.1f}" rx="4" '
            f'fill="{BRAND if is_peak else RAMP[3]}"{c.anim("grow", delay)}/>'
        )
        c.text(x + 15, base_y - h - 8, n(v), 800 if is_peak else 600, 14, TEXT if is_peak else MUTED, "middle", "fade", delay + 0.3)
        c.text(x + 15, base_y + 24, lab, 400, 14, MUTED, "middle", "fade", delay)
    c.add(f'<line x1="{left - 6}" y1="{base_y + 0.5}" x2="{left + 12 * slot - 8}" y2="{base_y + 0.5}" stroke="{RIM}" stroke-width="1.5"/>')

    # Stats column
    sx = 618
    c.add(f'<line x1="{sx - 28}" y1="40" x2="{sx - 28}" y2="{c.h - 40}" stroke="{RIM}"/>')
    def plural(k, word):
        return word if k == 1 else word + "s"

    stats = [
        (str(cur), plural(cur, "day"), "Current streak"),
        (str(longest), plural(longest, "day"), "Longest streak"),
        (n(active), plural(active, "day"), "Active days"),
        (n(busiest[1]), plural(busiest[1], "contribution"), f"Busiest day, {fmt_day(busiest[0])}"),
    ]
    for i, (num, unit, label) in enumerate(stats):
        y = 84 + i * 62
        c.rich(sx, y, [(num, 800, 34, BRAND if i == 0 else TEXT, 0), (unit, 600, 15, MUTED, 7)], "up", 0.35 + i * 0.12)
        c.text(sx, y + 22, label, 400, 15, MUTED, "start", "up", 0.4 + i * 0.12)
    c.save()


def lang_color(lang):
    return LANG_COLORS.get(lang, MUTED)


def star_path(cx, cy, r):
    pts = []
    for k in range(10):
        ang = -math.pi / 2 + k * math.pi / 5
        rad = r if k % 2 == 0 else r * 0.42
        pts.append(f"{cx + rad * math.cos(ang):.1f},{cy + rad * math.sin(ang):.1f}")
    return " ".join(pts)


def repo_card(repo, idx):
    c = Card(f"repo-{repo['name']}", 168, f"{repo['name']}: {repo['description']}", STAGE["repos"] + idx * 0.15)
    c.text(36, 52, repo["name"], 800, 28, TEXT, "start", "up", 0)
    for i, line in enumerate(wrap(repo["description"] or "No description yet.", 400, 16.5, 640, 2)):
        c.text(36, 82 + i * 22, line, 400, 16.5, MUTED, "start", "up", 0.1 + i * 0.06)
    y, x = 140, 36
    if repo["language"]:
        c.add(f'<circle cx="{x + 5}" cy="{y - 5}" r="5.5" fill="{lang_color(repo["language"])}"{c.anim("pop", 0.25)}/>')
        c.text(x + 18, y, repo["language"], 600, 15, TEXT, "start", "fade", 0.25)
        x += 18 + measure(repo["language"], 600, 15) + 28
    c.add(f'<polygon points="{star_path(x + 7, y - 6, 8)}" fill="{BRAND}"{c.anim("pop", 0.3)}/>')
    c.text(x + 22, y, n(repo["stars"]), 600, 15, TEXT, "start", "fade", 0.3)
    x += 22 + measure(n(repo["stars"]), 600, 15) + 28
    c.add(
        f'<g fill="none" stroke="{MUTED}" stroke-width="1.8" stroke-linecap="round"{c.anim("pop", 0.35)}>'
        f'<circle cx="{x + 2}" cy="{y - 13}" r="2.6"/><circle cx="{x + 12}" cy="{y - 13}" r="2.6"/>'
        f'<circle cx="{x + 7}" cy="{y - 1}" r="2.6"/>'
        f'<path d="M{x + 2} {y - 10}V{y - 8}Q{x + 2} {y - 6} {x + 7} {y - 6}Q{x + 12} {y - 6} {x + 12} {y - 8}V{y - 10}M{x + 7} {y - 6}V{y - 4}"/></g>'
    )
    c.text(x + 22, y, n(repo["forks"]), 600, 15, TEXT, "start", "fade", 0.35)
    # Open-link arrow, top right
    c.add(
        f'<path d="M772 40 L796 40 M796 40 L796 64 M796 40 L772 64" fill="none" stroke="{BRAND}" stroke-width="3.2" '
        f'stroke-linecap="round" stroke-linejoin="round"{c.anim("fade", 0.4)}/>'
    )
    c.save()


def graph():
    pitch, cell, gx, gy = 13, 10, 92, 92
    first = DAYS[0][0]
    offset = (first.weekday() + 1) % 7  # Sunday-first rows
    nonzero = sorted(v for _, v in DAYS if v > 0) or [1]
    q = [nonzero[int(len(nonzero) * f)] for f in (0.25, 0.5, 0.75)]

    def level(v):
        if v == 0:
            return 0
        return 1 + sum(v > t for t in q)

    weeks = (len(DAYS) + offset + 6) // 7
    c = Card("graph", 238, f"Contribution graph, {n(TOTAL)} contributions in the last year", STAGE["graph"])
    c.text(48, 52, "Contribution graph", 800, 26, TEXT, "start", "up", 0)
    c.text(782, 52, f"{n(TOTAL)} in the last year", 400, 16, MUTED, "end", "up", 0.08)

    for r, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        c.text(48, gy + r * pitch + 9, lab, 400, 12, MUTED, "start", "fade", 0.1)

    last_month = None
    cols = {}
    for i, (d, v) in enumerate(DAYS):
        col, row = divmod(i + offset, 7)
        cols.setdefault(col, []).append((row, v))
        if (row == 0 or i == 0) and d.month != last_month:
            c.text(gx + col * pitch, gy - 12, d.strftime("%b"), 400, 12, MUTED, "start", "fade", 0.05 + col * 0.016)
            last_month = d.month
    for col in range(weeks):
        cells = "".join(
            f'<rect x="{gx + col * pitch}" y="{gy + row * pitch}" width="{cell}" height="{cell}" rx="2.5" fill="{RAMP[level(v)]}"/>'
            for row, v in cols.get(col, [])
        )
        c.add(f'<g{c.anim("fade", 0.1 + col * 0.016)}>{cells}</g>')

    # Legend, right-aligned under the grid
    ly, right = gy + 7 * pitch + 22, 782
    c.text(right, ly + 9, "More", 400, 12, MUTED, "end", "fade", 1.2)
    cx0 = right - measure("More", 400, 12) - 8 - 5 * pitch + (pitch - cell)
    for k in range(5):
        c.add(f'<rect x="{cx0 + k * pitch:.1f}" y="{ly}" width="{cell}" height="{cell}" rx="2.5" fill="{RAMP[k]}"{c.anim("fade", 1.2)}/>')
    c.text(cx0 - 8, ly + 9, "Less", 400, 12, MUTED, "end", "fade", 1.2)
    c.save()


def main():
    if DATA.get("sample"):
        print("note: data/contributions.json is SAMPLE data; the Action replaces it with real numbers", file=sys.stderr)
    print(f"mode: {'STATIC (final frame)' if STATIC else 'animated'} -> {OUT.relative_to(ROOT)}/")
    hero()
    for spec in PROFILE["tiles"]:
        tile(spec)
    chart()
    by_name = {r["name"]: r for r in DATA["repos"]}
    for i, name in enumerate(PROFILE["featured_repos"]):
        if name not in by_name:
            sys.exit(f"repo {name!r} is in profile.json but missing from contributions.json")
        repo_card(by_name[name], i)
    graph()


if __name__ == "__main__":
    main()

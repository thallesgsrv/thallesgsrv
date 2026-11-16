#!/usr/bin/env python3
"""Gera profile-card.svg com contribuições reais do GitHub (estilo terminal)."""
import json, os, random, sys, urllib.request
from datetime import date, timedelta
from html import escape

USER = os.environ.get("GH_USER", "thallesgsrv")
TOKEN = os.environ.get("GH_TOKEN", "")
NAME, SUB = "Thalles Gabriel", "Saraiva de Lira Silva"
ABOUT = [("curso:", "Ciência da Computação"), ("onde:", "UFCG · Campina Grande, PB"), ("raízes:", "Cajazeiras, Paraíba")]
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def fetch_days():
    if "--demo" in sys.argv:
        random.seed(7)
        d0 = date.today() - timedelta(days=364)
        return [(d0 + timedelta(days=i), random.choice([0, 0, 1, 2, 3, 5, 8, 13])) for i in range(365)]
    q = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{
      weeks{contributionDays{date contributionCount}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": q, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    data = json.load(urllib.request.urlopen(req))
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [(date.fromisoformat(d["date"]), d["contributionCount"]) for w in weeks for d in w["contributionDays"]]


def stats(days):
    total = sum(c for _, c in days)
    active = sum(1 for _, c in days if c)
    best = max(days, key=lambda x: x[1])
    longest = run = 0
    for _, c in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    cur, i = 0, len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1  # hoje ainda pode estar zerado
    while i >= 0 and days[i][1] > 0:
        cur += 1
        i -= 1
    avg = total / active if active else 0
    return dict(total=total, active=active, best=best[1], longest=longest, cur=cur, avg=avg)


def level(c, mx):
    if c == 0:
        return 0
    r = c / mx
    return 1 if r <= .25 else 2 if r <= .5 else 3 if r <= .75 else 4


def build(days):
    s = stats(days)
    mx = max(c for _, c in days) or 1
    W, M = 940, 46
    out = []

    def t(x, y, txt, fill="#c9d1d9", size=14, weight=400, anchor="start"):
        out.append(f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(txt))}</text>')

    def prompt(x, y, cmd):
        out.append(f'<text x="{x}" y="{y}" font-size="14"><tspan fill="#7ee787">{USER}@github</tspan><tspan fill="#8b949e"> ~ </tspan><tspan fill="#c9d1d9">$ {escape(cmd)}</tspan></text>')

    # --- heatmap ---
    prompt(M, 76, "./contributions.sh")
    first = days[0][0]
    offset = (first.weekday() + 1) % 7  # domingo = 0
    cell, gap = 13, 3
    gx, gy = M + 34, 112
    last_m = -1
    for i, (d, c) in enumerate(days):
        col, row = (i + offset) // 7, (i + offset) % 7
        if row == 0 and d.month != last_m:
            if d.day <= 7 or i == 0:
                t(gx + col * (cell + gap), gy - 8, MONTHS[d.month - 1], "#8b949e", 11)
            last_m = d.month
        out.append(f'<rect x="{gx + col * (cell + gap)}" y="{gy + row * (cell + gap)}" width="{cell}" height="{cell}" rx="2" fill="{LEVELS[level(c, mx)]}"/>')
    for r, lab in ((1, "seg"), (3, "qua"), (5, "sex")):
        t(M, gy + r * (cell + gap) + 11, lab, "#8b949e", 11)
    hy = gy + 7 * (cell + gap) + 18
    t(M, hy, f"{s['total']:,} contribuições no último ano".replace(",", "."), "#8b949e", 12)
    out.append(f'<line x1="{M}" y1="{hy + 20}" x2="{W - M}" y2="{hy + 20}" stroke="#30363d"/>')

    # --- whoami ---
    wy = hy + 52
    prompt(M, wy, "whoami")
    lines = open(os.path.join(os.path.dirname(__file__), "ascii.txt")).read().split("\n")
    while lines and not lines[0].strip(): lines.pop(0)
    while lines and not lines[-1].strip(): lines.pop()
    ay = wy + 24
    asc = "".join(f'<tspan x="{M}" y="{ay + i * 9:.1f}">{escape(l)}</tspan>' for i, l in enumerate(lines))
    out.append(f'<text xml:space="preserve" fill="#7ee787" style="font-size:8px;white-space:pre">{asc}</text>')

    rx = 500
    t(rx, wy + 30, NAME, "#ffffff", 26, 700)
    t(rx, wy + 52, SUB, "#8b949e", 14)
    for i, (k, v) in enumerate(ABOUT):
        out.append(f'<text x="{rx}" y="{wy + 80 + i * 20}" font-size="14"><tspan fill="#79c0ff">{k}</tspan><tspan fill="#c9d1d9"> {escape(v)}</tspan></text>')

    boxes = [("streak atual", s["cur"], "dias"), ("maior streak", s["longest"], "dias"),
             ("contribuições", s["total"], "no ano"), ("dias ativos", s["active"], f"de {len(days)}"),
             ("melhor dia", s["best"], "contribuições"), ("média/dia ativo", f"{s['avg']:.1f}", "contribuições")]
    bw, bh, bx0, by0 = 192, 62, rx, wy + 150
    for i, (lab, val, sub) in enumerate(boxes):
        x, y = bx0 + (i % 2) * (bw + 12), by0 + (i // 2) * (bh + 10)
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="6" fill="#0d1117" stroke="#30363d"/>')
        t(x + 12, y + 18, lab, "#8b949e", 11)
        t(x + 12, y + 44, val, "#39d353", 24, 700)
        t(x + 12 + 14 * len(str(val)) + 8, y + 44, sub, "#8b949e", 11)

    # --- barras por mês ---
    by = by0 + 3 * (bh + 10) + 24
    t(rx, by, "contribuições / mês", "#8b949e", 11)
    per = {}
    for d, c in days:
        per[(d.year, d.month)] = per.get((d.year, d.month), 0) + c
    keys = sorted(per)[-12:]
    mm = max(per[k] for k in keys) or 1
    base, hmax, bwid = by + 84, 60, 24
    for i, k in enumerate(keys):
        h = max(2, per[k] / mm * hmax)
        x = rx + i * 33
        out.append(f'<rect x="{x}" y="{base - h:.1f}" width="{bwid}" height="{h:.1f}" rx="2" fill="#39d353"/>')
        t(x + bwid / 2, base + 14, MONTHS[k[1] - 1][0], "#8b949e", 10, 400, "middle")

    H = int(max(ay + len(lines) * 9, base + 14) + 36)
    head = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Perfil de {USER} no estilo terminal" font-family="{FONT}">
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="#0d1117" stroke="#30363d"/>
<rect x="0.5" y="0.5" width="{W - 1}" height="40" rx="12" fill="#161b22"/><rect x="0.5" y="28" width="{W - 1}" height="13" fill="#161b22"/>
<circle cx="24" cy="21" r="6" fill="#ff5f56"/><circle cx="44" cy="21" r="6" fill="#ffbd2e"/><circle cx="64" cy="21" r="6" fill="#27c93f"/>
<text x="{W / 2}" y="26" text-anchor="middle" fill="#8b949e" font-size="13">{USER} — zsh</text>
'''
    return head + "\n".join(out) + "\n</svg>\n"


if __name__ == "__main__":
    svg = build(fetch_days())
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile-card.svg")
    open(path, "w", encoding="utf-8").write(svg)
    print("ok ->", path)

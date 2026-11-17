#!/usr/bin/env python3
"""Gera os SVGs do perfil do GitHub (cartão estilo terminal + cards de projetos)
e atualiza a seção de projetos do README.md.

  GH_TOKEN=<token> python generate.py      # dados reais (usado pelo GitHub Actions)
  python generate.py --demo --out /tmp/x   # dados fictícios, sem token, para testar o visual
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
import textwrap
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEMO = "--demo" in sys.argv
OUT = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else ROOT

USER = os.environ.get("GH_USER", "thallesgsrv")
TOKEN = os.environ.get("GH_TOKEN", "")

# ── Personalização ───────────────────────────────────────────────────────────
NAME, SUB = "Thalles Gabriel", "Saraiva de Lira Silva"
ABOUT = [
    ("curso:", "Ciência da Computação"),
    ("onde:", "UFCG · Campina Grande, PB"),
    ("raízes:", "Cajazeiras, Paraíba"),
]
# Usados só se você não tiver repositórios fixados (pinned) no perfil.
FALLBACK_REPOS = ["Big-O-Library", "Chatbot", "nasa-space-apps", "eda"]

# ── Visual ───────────────────────────────────────────────────────────────────
FONT = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"
C = dict(bg="#0d1117", bar="#161b22", line="#30363d", fg="#c9d1d9", dim="#8b949e",
         green="#7ee787", accent="#39d353", blue="#79c0ff", white="#ffffff")
LEVELS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
BRT = timezone(timedelta(hours=-3))

ICON_REPO = "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z"
ICON_STAR = "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.751.751 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z"
ICON_FORK = "M5 5.372v.878c0 .414.336.75.75.75h4.5a.75.75 0 0 0 .75-.75v-.878a2.25 2.25 0 1 1 1.5 0v.878a2.25 2.25 0 0 1-2.25 2.25h-1.5v2.128a2.251 2.251 0 1 1-1.5 0V8.5h-1.5A2.25 2.25 0 0 1 3.5 6.25v-.878a2.25 2.25 0 1 1 1.5 0ZM5 3.25a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Zm6.75.75a.75.75 0 1 0 0-1.5.75.75 0 0 0 0 1.5Zm-3 8.75a.75.75 0 1 0-1.5 0 .75.75 0 0 0 1.5 0Z"


# ── Dados ────────────────────────────────────────────────────────────────────
REPO_FIELDS = "name description url stargazerCount forkCount pushedAt primaryLanguage{name color}"
QUERY = """
query($login:String!){ user(login:$login){
  createdAt
  followers{totalCount}
  repositories(ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC){totalCount}
  pinnedItems(first:6,types:REPOSITORY){nodes{... on Repository{%s}}}
  langs:repositories(first:100,ownerAffiliations:OWNER,isFork:false,privacy:PUBLIC){nodes{
    languages(first:8,orderBy:{field:SIZE,direction:DESC}){edges{size node{name color}}}}}
  contributionsCollection{contributionCalendar{weeks{contributionDays{date contributionCount}}}}
}}""" % REPO_FIELDS


def gql(query: str, variables: dict | None = None) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    res = json.load(urllib.request.urlopen(req, timeout=30))
    if res.get("errors"):
        raise RuntimeError(res["errors"])
    return res["data"]


def fetch_data() -> dict:
    if not TOKEN:
        sys.exit("Defina GH_TOKEN (ou rode com --demo para testar sem token).")
    u = gql(QUERY, {"login": USER})["user"]
    weeks = u["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [(date.fromisoformat(x["date"]), x["contributionCount"]) for w in weeks for x in w["contributionDays"]]

    repos = [r for r in u["pinnedItems"]["nodes"] if r]
    if not repos:
        parts = " ".join(f'r{i}:repository(owner:"{USER}",name:"{n}"){{{REPO_FIELDS}}}' for i, n in enumerate(FALLBACK_REPOS))
        repos = [r for r in gql("query{%s}" % parts).values() if r]

    langs: dict[str, list] = {}
    for repo in u["langs"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]
            langs.setdefault(n["name"], [n["color"] or "#8b949e", 0])[1] += e["size"]
    return dict(
        days=days, repos=repos, followers=u["followers"]["totalCount"],
        nrepos=u["repositories"]["totalCount"], since=u["createdAt"][:4],
        langs=sorted(((k, v[0], v[1]) for k, v in langs.items()), key=lambda x: -x[2]),
    )


def demo_data() -> dict:
    random.seed(11)
    d0 = date.today() - timedelta(days=366)
    days = []
    for i in range(367):
        p = 0.12 + 0.5 * (i / 366) ** 1.6
        days.append((d0 + timedelta(days=i), random.choice([1, 2, 3, 5, 8, 14]) if random.random() < p else 0))
    iso = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    mk = lambda n, desc, lang, col, st, fk: dict(name=n, description=desc, url=f"https://github.com/{USER}/{n}",
                                                 stargazerCount=st, forkCount=fk, pushedAt=iso,
                                                 primaryLanguage=dict(name=lang, color=col))
    return dict(
        days=days, followers=7, nrepos=14, since="2024",
        repos=[mk("Big-O-Library", "Biblioteca para estudar e visualizar a complexidade de algoritmos.", "Python", "#3572A5", 2, 0),
               mk("Chatbot", "Chatbot conversacional com integração a modelos de linguagem.", "Python", "#3572A5", 1, 0),
               mk("nasa-space-apps", "Projeto desenvolvido para o hackathon NASA Space Apps Challenge.", "JavaScript", "#f1e05a", 0, 0),
               mk("eda", None, "Jupyter Notebook", "#DA5B0B", 0, 0)],
        langs=[("Python", "#3572A5", 61), ("Jupyter Notebook", "#DA5B0B", 18), ("JavaScript", "#f1e05a", 9),
               ("HTML", "#e34c26", 6), ("CSS", "#563d7c", 4), ("Shell", "#89e051", 2)],
    )


# ── Utilidades ───────────────────────────────────────────────────────────────
def br(n) -> str:
    return f"{n:,}".replace(",", ".")


def ago(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    s = (datetime.now(timezone.utc) - dt).total_seconds()
    for lim, div, un, un_pl in ((3600, 60, "min", "min"), (86400, 3600, "hora", "horas"), (86400 * 30, 86400, "dia", "dias"),
                                (86400 * 365, 86400 * 30, "mês", "meses"), (1e12, 86400 * 365, "ano", "anos")):
        if s < lim:
            n = max(1, int(s // div))
            return f"há {n} {un if n == 1 else un_pl}"
    return ""


def stats(days):
    total = sum(c for _, c in days)
    active = sum(1 for _, c in days if c)
    best = max((c for _, c in days), default=0)
    longest = run = 0
    for _, c in days:
        run = run + 1 if c else 0
        longest = max(longest, run)
    cur, i = 0, len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1  # o dia de hoje ainda pode estar zerado
    while i >= 0 and days[i][1] > 0:
        cur += 1
        i -= 1
    return dict(total=total, active=active, best=best, longest=longest, cur=cur,
                avg=total / active if active else 0)


def make_level(days):
    nz = sorted(c for _, c in days if c > 0)
    if not nz:
        return lambda c: 0
    q1, q2, q3 = nz[len(nz) // 4], nz[len(nz) // 2], nz[3 * len(nz) // 4]
    return lambda c: 0 if c == 0 else 1 if c <= q1 else 2 if c <= q2 else 3 if c <= q3 else 4


def load_ascii():
    lines = (ROOT / "ascii.txt").read_text(encoding="utf-8").expandtabs(4).split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    lines = [l.rstrip() for l in lines]
    ind = min(len(l) - len(l.lstrip()) for l in lines if l.strip())
    lines = [l[ind:] for l in lines]
    return lines, max(len(l) for l in lines)


# ── Cartão principal ─────────────────────────────────────────────────────────
def build_card(d: dict) -> str:
    days = d["days"]
    s, lvl = stats(days), make_level(days)
    W, M = 940, 46
    out: list[str] = []

    def t(x, y, txt, fill=C["fg"], size=14, weight=400, anchor="start"):
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(txt))}</text>')

    def prompt(y, cmd, cursor=False):
        cur = '<tspan class="cur"> _</tspan>' if cursor else ""
        out.append(f'<text x="{M}" y="{y}" font-size="14"><tspan fill="{C["green"]}" font-weight="600">{USER}@github</tspan>'
                   f'<tspan fill="{C["dim"]}"> ~ </tspan><tspan fill="{C["fg"]}">$ {escape(cmd)}</tspan>{cur}</text>')

    def divider(y):
        out.append(f'<line x1="{M}" y1="{y}" x2="{W - M}" y2="{y}" stroke="{C["line"]}"/>')

    # 1) contribuições ---------------------------------------------------------
    prompt(76, "./contributions.sh")
    offset = (days[0][0].weekday() + 1) % 7  # domingo = 0
    ncols = (len(days) + offset + 6) // 7
    gx, gap, gy = M + 30, 3, 112
    step = (W - M - gx + gap) / ncols
    cell = step - gap

    labels, last = [], -1
    for col in range(ncols):
        dt = days[max(0, col * 7 - offset)][0]
        if dt.month != last:
            labels.append((col, dt.month))
            last = dt.month
    if len(labels) > 1 and labels[1][0] - labels[0][0] < 3:
        labels.pop(0)
    for col, m in labels:
        t(gx + col * step, gy - 9, MONTHS[m - 1], C["dim"], 11)
    for r, lab in ((1, "seg"), (3, "qua"), (5, "sex")):
        t(M, gy + r * step + cell - 2, lab, C["dim"], 11)
    for i, (_, c) in enumerate(days):
        col, row = (i + offset) // 7, (i + offset) % 7
        out.append(f'<rect x="{gx + col * step:.1f}" y="{gy + row * step:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{LEVELS[lvl(c)]}"/>')

    hy = gy + 7 * step + 18
    t(M, hy, f"{br(s['total'])} contribuições no último ano", C["dim"], 12)
    lx = W - M - 142
    t(lx, hy, "menos", C["dim"], 11)
    for k in range(5):
        out.append(f'<rect x="{lx + 40 + k * 15}" y="{hy - 10}" width="11" height="11" rx="2.5" fill="{LEVELS[k]}"/>')
    t(lx + 40 + 5 * 15 + 3, hy, "mais", C["dim"], 11)
    divider(hy + 20)

    # 2) whoami ------------------------------------------------------------------
    wy = hy + 54
    prompt(wy, "whoami")
    rx = 500
    t(rx, wy + 36, NAME, C["white"], 26, 700)
    t(rx, wy + 58, SUB, C["dim"], 14)
    about = ABOUT + [("github:", f"desde {d['since']} · {d['nrepos']} repos · {d['followers']} seguidores")]
    for i, (k, v) in enumerate(about):
        out.append(f'<text x="{rx}" y="{wy + 88 + i * 20}" font-size="14"><tspan fill="{C["blue"]}">{k}</tspan><tspan fill="{C["fg"]}"> {escape(v)}</tspan></text>')

    boxes = [("streak atual", s["cur"], "dias"), ("maior streak", s["longest"], "dias"),
             ("contribuições", br(s["total"]), "no ano"), ("dias ativos", s["active"], f"de {len(days)}"),
             ("melhor dia", s["best"], "contribuições"), ("média/dia ativo", f"{s['avg']:.1f}".replace(".", ","), "contribuições")]
    bw, bh, by0 = 191, 62, wy + 172
    for i, (lab, val, sub) in enumerate(boxes):
        x, y = rx + (i % 2) * (bw + 12), by0 + (i // 2) * (bh + 10)
        out.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="7" fill="{C["bg"]}" stroke="{C["line"]}"/>')
        t(x + 14, y + 19, lab, C["dim"], 11)
        t(x + 14, y + 47, val, C["accent"], 24, 700)
        t(x + 14 + 14.4 * len(str(val)) + 8, y + 47, sub, C["dim"], 11)

    cy = by0 + 3 * (bh + 10) + 14
    t(rx, cy, "contribuições / mês", C["dim"], 11)
    per: dict = {}
    for dt, c in days:
        per[(dt.year, dt.month)] = per.get((dt.year, dt.month), 0) + c
    keys = sorted(per)[-12:]
    mm = max(per[k] for k in keys) or 1
    base, hmax = cy + 14 + 62, 62
    pitch = (W - M - rx) / len(keys)
    bwid = pitch - 9
    for i, k in enumerate(keys):
        h = max(2, per[k] / mm * hmax)
        x = rx + i * pitch
        out.append(f'<rect x="{x:.1f}" y="{base - h:.1f}" width="{bwid:.1f}" height="{h:.1f}" rx="2.5" fill="{C["accent"]}" opacity="{0.55 + 0.45 * per[k] / mm:.2f}"/>')
        t(x + bwid / 2, base + 15, MONTHS[k[1] - 1], C["dim"], 9.5, 400, "middle")
    right_end = base + 20

    # retrato ASCII: grade fixa (textLength) para ficar igual em qualquer fonte
    lines, maxlen = load_ascii()
    cw = 410 / maxlen
    lh = cw * 1.85
    ah = len(lines) * lh
    ay = wy + 16 + max(0, (right_end - wy - 16 - ah) / 2)
    asc = []
    for i, l in enumerate(lines):
        if not l.strip():
            continue
        lead = len(l) - len(l.lstrip())
        txt = l.strip()
        asc.append(f'<text x="{M + lead * cw:.1f}" y="{ay + (i + 1) * lh:.1f}" textLength="{len(txt) * cw:.1f}" lengthAdjust="spacing">{escape(txt)}</text>')
    out.append(f'<g xml:space="preserve" fill="url(#asc)" style="font-size:{cw / 0.6:.2f}px;white-space:pre">{"".join(asc)}</g>')
    y1 = max(right_end, ay + ah) + 22
    divider(y1)

    # 3) linguagens ------------------------------------------------------------
    ly = y1 + 34
    prompt(ly, "./languages.sh")
    langs = d["langs"]
    total = sum(x[2] for x in langs) or 1
    top, rest = langs[:6], langs[6:]
    items = [(n, col, sz) for n, col, sz in top]
    if rest:
        items.append(("Outras", "#6e7681", sum(x[2] for x in rest)))
    bx, bwid_all, by, bhh = M, W - 2 * M, ly + 20, 12
    out.append(f'<clipPath id="lb"><rect x="{bx}" y="{by}" width="{bwid_all}" height="{bhh}" rx="6"/></clipPath><g clip-path="url(#lb)">')
    x = bx
    for n, col, sz in items:
        w = max(4, sz / total * bwid_all)
        out.append(f'<rect x="{x:.1f}" y="{by}" width="{w - 2:.1f}" height="{bhh}" fill="{col}"/>')
        x += w
    out.append("</g>")
    lx, lyy = M, by + bhh + 26
    for n, col, sz in items:
        pct = f"{sz / total * 100:.1f}%".replace(".", ",")
        wlab = 18 + len(f"{n} {pct}") * 7.3 + 24
        if lx + wlab > W - M:
            lx, lyy = M, lyy + 22
        out.append(f'<circle cx="{lx + 5}" cy="{lyy - 4}" r="5" fill="{col}"/>')
        out.append(f'<text x="{lx + 16}" y="{lyy}" font-size="12" fill="{C["fg"]}">{escape(n)} <tspan fill="{C["dim"]}">{pct}</tspan></text>')
        lx += wlab
    divider(lyy + 22)

    # 4) rodapé ----------------------------------------------------------------
    fy = lyy + 54
    prompt(fy, "", cursor=True)
    now = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")
    t(W - M, fy, f"atualizado em {now} (BRT)", C["dim"], 11, 400, "end")

    H = int(fy + 34)
    head = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" font-family="{FONT}">
<title>Perfil de {USER} no GitHub</title>
<desc>Cartão em estilo terminal com contribuições, estatísticas e linguagens de {NAME}.</desc>
<defs>
<linearGradient id="asc" gradientUnits="userSpaceOnUse" x1="0" y1="{ay:.0f}" x2="0" y2="{ay + ah:.0f}"><stop offset="0" stop-color="#b6f5c0"/><stop offset="1" stop-color="#2ea043"/></linearGradient>
<style>.cur{{fill:{C["fg"]};animation:blink 1.1s steps(1) infinite}}@keyframes blink{{50%{{fill:transparent}}}}@media (prefers-reduced-motion:reduce){{.cur{{animation:none}}}}</style>
</defs>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="12" fill="{C["bg"]}" stroke="{C["line"]}"/>
<path d="M0.5 40.5V12.5a12 12 0 0 1 12-12h915a12 12 0 0 1 12 12v28z" fill="{C["bar"]}"/>
<line x1="0.5" y1="40.5" x2="{W - 0.5}" y2="40.5" stroke="{C["line"]}"/>
<circle cx="24" cy="21" r="6" fill="#ff5f56"/><circle cx="44" cy="21" r="6" fill="#ffbd2e"/><circle cx="64" cy="21" r="6" fill="#27c93f"/>
<text x="{W / 2}" y="26" text-anchor="middle" fill="{C["dim"]}" font-size="13">{USER} — zsh — 120×40</text>
'''
    return head + "\n".join(out) + "\n</svg>\n"


# ── Cards de projetos ────────────────────────────────────────────────────────
def build_repo_card(r: dict) -> str:
    W, H, P = 460, 132, 22
    desc = r.get("description") or "Sem descrição."
    lines = textwrap.wrap(desc, 56)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1].rstrip(".,; ")[:53] + "…"
    name = r["name"] if len(r["name"]) <= 32 else r["name"][:31] + "…"
    out = [f'<g transform="translate({P},{P - 3}) scale(1.1)" fill="{C["dim"]}"><path d="{ICON_REPO}"/></g>',
           f'<text x="{P + 26}" y="{P + 12}" font-size="16" font-weight="700" fill="{C["green"]}">{escape(name)}</text>']
    for i, l in enumerate(lines):
        out.append(f'<text x="{P}" y="{P + 42 + i * 19}" font-size="12.5" fill="{C["dim"] if r.get("description") else "#6e7681"}">{escape(l)}</text>')
    y, x = H - 24, P
    lang = r.get("primaryLanguage")
    if lang:
        out.append(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{lang["color"] or C["dim"]}"/>'
                   f'<text x="{x + 16}" y="{y}" font-size="12" fill="{C["fg"]}">{escape(lang["name"])}</text>')
        x += 16 + len(lang["name"]) * 7.3 + 18
    for icon, n in ((ICON_STAR, r["stargazerCount"]), (ICON_FORK, r["forkCount"])):
        out.append(f'<g transform="translate({x},{y - 12}) scale(0.9)" fill="{C["dim"]}"><path d="{icon}"/></g>'
                   f'<text x="{x + 19}" y="{y}" font-size="12" fill="{C["fg"]}">{n}</text>')
        x += 19 + len(str(n)) * 7.3 + 16
    if r.get("pushedAt"):
        out.append(f'<text x="{W - P}" y="{y}" font-size="11" fill="#6e7681" text-anchor="end">{ago(r["pushedAt"])}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" font-family="{FONT}">
<title>{escape(r["name"])}</title>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{C["bg"]}" stroke="{C["line"]}"/>
{chr(10).join(out)}
</svg>
'''


def slug(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", n)


def update_readme(repos: list[dict]) -> None:
    src = ROOT / "README.md"
    if not src.exists():
        return
    md = src.read_text(encoding="utf-8")
    cards = "\n".join(f'<a href="{r["url"]}"><img src="./assets/repo-{slug(r["name"])}.svg" alt="{escape(r["name"])}" width="48%"/></a>'
                      for r in repos)
    block = f'<!-- PROJECTS:START -->\n<div align="center">\n\n{cards}\n\n</div>\n<!-- PROJECTS:END -->'
    new, n = re.subn(r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->", lambda _: block, md, flags=re.S)
    if n:
        (OUT / "README.md").write_text(new, encoding="utf-8")


def main() -> None:
    d = demo_data() if DEMO else fetch_data()
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    (OUT / "profile-card.svg").write_text(build_card(d), encoding="utf-8")
    keep = set()
    for r in d["repos"]:
        f = OUT / "assets" / f"repo-{slug(r['name'])}.svg"
        f.write_text(build_repo_card(r), encoding="utf-8")
        keep.add(f.name)
    for old in (OUT / "assets").glob("repo-*.svg"):
        if old.name not in keep:
            old.unlink()
    update_readme(d["repos"])
    print("ok ->", OUT)


if __name__ == "__main__":
    main()

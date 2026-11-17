#!/usr/bin/env python3
"""Gera os cards SVG do perfil do GitHub (pasta cards/)
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
# Cada linha aparece no cartão como "rótulo: valor". Adicione/remova à vontade (ideal: 2 a 4 linhas).
# Sugestões úteis: ("foco:", "..."), ("estudando:", "..."), ("aberto a:", "estágio · projetos open source")
ABOUT = [
    ("curso:", "Ciência da Computação"),
    ("onde:", "UFCG · Campina Grande, PB"),
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


# ── Base dos cards ───────────────────────────────────────────────────────────
W, M, OP = 880, 36, 6          # largura, margem interna, respiro vertical embutido (empilha sem espaços)
CSS = """<style>
@keyframes pop{from{opacity:0;transform:translateY(7px)}}
@keyframes fade{from{opacity:0}}
@keyframes growy{from{transform:scaleY(0)}}
@keyframes growx{from{transform:scaleX(0)}}
@keyframes blink{50%{fill:transparent}}
.cur{fill:#c9d1d9}
@media (prefers-reduced-motion:no-preference){
.pop{animation:pop .55s ease-out backwards}
.fade{animation:fade .35s ease-out backwards}
.gy{transform-box:fill-box;transform-origin:50% 100%;animation:growy .8s cubic-bezier(.2,.8,.2,1) backwards}
.gx{transform-box:fill-box;transform-origin:0 50%;animation:growx .8s cubic-bezier(.2,.8,.2,1) backwards}
.cur{animation:blink 1.1s steps(1) infinite}
}
</style>"""


class Card:
    """Janela de terminal de 880px; coordenadas relativas ao topo da janela."""

    def __init__(self, cmd: str, title: str):
        self.cmd, self.title, self.out, self.defs = cmd, title, [], []

    def t(self, x, y, txt, fill=C["fg"], size=14, weight=400, anchor="start", cls="", delay=None):
        a = f' class="{cls}"' if cls else ""
        a += f' style="animation-delay:{delay:.2f}s"' if delay is not None else ""
        self.out.append(f'<text{a} x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{escape(str(txt))}</text>')

    def raw(self, s):
        self.out.append(s)

    def prompt(self, y, cmd, cursor=False, x=M):
        cur = '<tspan class="cur"> _</tspan>' if cursor else ""
        self.out.append(f'<text x="{x}" y="{y}" font-size="14"><tspan fill="{C["green"]}" font-weight="600">{USER}@github</tspan>'
                        f'<tspan fill="{C["dim"]}"> ~ </tspan><tspan fill="{C["fg"]}">$ {escape(cmd)}</tspan>{cur}</text>')

    def render(self, h: int) -> str:
        H = h + 2 * OP
        bar = f"M0.5 34.5V12.5a12 12 0 0 1 12-12H{W - 12.5}a12 12 0 0 1 12 12v22z"
        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(self.title)}" font-family="{FONT}">
<title>{escape(self.title)}</title>
{CSS}
<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#111722"/><stop offset="1" stop-color="{C["bg"]}"/></linearGradient>{"".join(self.defs)}</defs>
<g transform="translate(0,{OP})">
<rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="12" fill="url(#bg)" stroke="{C["line"]}"/>
<path d="{bar}" fill="{C["bar"]}"/><line x1="0" y1="34.5" x2="{W}" y2="34.5" stroke="{C["line"]}"/>
<circle cx="22" cy="17.5" r="5.5" fill="#ff5f56"/><circle cx="40" cy="17.5" r="5.5" fill="#ffbd2e"/><circle cx="58" cy="17.5" r="5.5" fill="#27c93f"/>
<text x="{W / 2}" y="22" text-anchor="middle" fill="{C["dim"]}" font-size="12">{USER}@github: ~$ {escape(self.cmd)}</text>
{chr(10).join(self.out)}
</g>
</svg>
'''


def updated_stamp() -> str:
    return "atualizado em " + datetime.now(BRT).strftime("%d/%m/%Y %H:%M") + " (BRT)"


# ── Card 1: contribuições ────────────────────────────────────────────────────
def card_heatmap(d: dict) -> str:
    days = d["days"]
    s, lvl = stats(days), make_level(days)
    c = Card("./contributions.sh", f"Contribuições de {NAME} no último ano")
    offset = (days[0][0].weekday() + 1) % 7
    ncols = (len(days) + offset + 6) // 7
    gx, gap, gy = M + 30, 3, 74
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
        c.t(gx + col * step, gy - 10, MONTHS[m - 1], C["dim"], 11)
    for r, lab in ((1, "seg"), (3, "qua"), (5, "sex")):
        c.t(M, gy + r * step + cell - 2, lab, C["dim"], 11)

    cols: dict = {}
    for i, (_, v) in enumerate(days):
        col, row = (i + offset) // 7, (i + offset) % 7
        cols.setdefault(col, []).append(f'<rect x="{gx + col * step:.1f}" y="{gy + row * step:.1f}" width="{cell:.1f}" height="{cell:.1f}" rx="2.5" fill="{LEVELS[lvl(v)]}"/>')
    for col, rects in cols.items():
        c.raw(f'<g class="pop" style="animation-delay:{0.15 + col * 0.016:.3f}s">{"".join(rects)}</g>')

    hy = gy + 7 * step + 26
    c.t(M, hy, f"{br(s['total'])} contribuições no último ano", C["fg"], 13, 600)
    lx = W - M - 142
    c.t(lx, hy, "menos", C["dim"], 11)
    for k in range(5):
        c.raw(f'<rect x="{lx + 40 + k * 15}" y="{hy - 10}" width="11" height="11" rx="2.5" fill="{LEVELS[k]}"/>')
    c.t(lx + 40 + 5 * 15 + 3, hy, "mais", C["dim"], 11)
    return c.render(int(hy + 24))


# ── Card 2: whoami (retrato + perfil + linguagens) ───────────────────────────
def card_profile(d: dict) -> str:
    c = Card("./whoami", f"{NAME}: retrato em ASCII, perfil e linguagens")
    lines, maxlen = load_ascii()
    cw = 380 / maxlen
    lh = cw * 1.85
    ah = len(lines) * lh
    top = 58
    rx, rw = 470, W - M - 470

    asc = []
    for i, l in enumerate(lines):
        if not l.strip():
            continue
        lead, txt = len(l) - len(l.lstrip()), l.strip()
        asc.append(f'<text class="fade" style="animation-delay:{0.1 + i * 0.025:.3f}s" x="{M + lead * cw:.1f}" y="{top + (i + 1) * lh:.1f}" textLength="{len(txt) * cw:.1f}" lengthAdjust="spacing">{escape(txt)}</text>')
    c.defs.append(f'<linearGradient id="asc" gradientUnits="userSpaceOnUse" x1="0" y1="{top:.0f}" x2="0" y2="{top + ah:.0f}"><stop offset="0" stop-color="#b6f5c0"/><stop offset="1" stop-color="#2ea043"/></linearGradient>')
    c.raw(f'<g xml:space="preserve" fill="url(#asc)" style="font-size:{cw / 0.6:.2f}px;white-space:pre">{"".join(asc)}</g>')

    langs = d["langs"]
    total = sum(x[2] for x in langs) or 1
    items = list(langs[:6])
    if langs[6:]:
        items.append(("Outras", "#6e7681", sum(x[2] for x in langs[6:])))
    row_h = 32
    block_h = 60 + 20 + len(ABOUT) * 22 + 36 + 24 + len(items) * row_h
    y = top + max(0, (ah - block_h) / 2)

    c.t(rx, y + 30, NAME, C["white"], 30, 700, cls="pop", delay=0.1)
    c.t(rx, y + 54, SUB, C["dim"], 14, cls="pop", delay=0.2)
    y += 60 + 20
    for i, (k, v) in enumerate(ABOUT):
        c.raw(f'<text class="pop" style="animation-delay:{0.3 + i * 0.08:.2f}s" x="{rx}" y="{y + 16 + i * 22:.1f}" font-size="14"><tspan fill="{C["blue"]}">{k}</tspan><tspan fill="{C["fg"]}"> {escape(v)}</tspan></text>')
    y += len(ABOUT) * 22 + 36
    c.t(rx, y, "linguagens", C["dim"], 11, cls="pop", delay=0.5)
    y += 24
    for i, (n, col, sz) in enumerate(items):
        yy = y + i * row_h
        dl = 0.55 + i * 0.07
        pct = sz / total
        c.raw(f'<g class="pop" style="animation-delay:{dl:.2f}s"><circle cx="{rx + 5}" cy="{yy - 4}" r="5" fill="{col}"/>'
              f'<text x="{rx + 18}" y="{yy}" font-size="13" fill="{C["fg"]}">{escape(n)}</text>'
              f'<text x="{rx + rw}" y="{yy}" font-size="13" fill="{C["dim"]}" text-anchor="end">{f"{pct * 100:.1f}".replace(".", ",")}%</text></g>')
        c.raw(f'<rect x="{rx}" y="{yy + 8}" width="{rw}" height="4" rx="2" fill="{C["bar"]}"/>'
              f'<rect class="gx" style="animation-delay:{dl + 0.1:.2f}s" x="{rx}" y="{yy + 8}" width="{max(4, pct * rw):.1f}" height="4" rx="2" fill="{col}"/>')
    return c.render(int(top + ah + 26))


# ── Card 3: atividade ────────────────────────────────────────────────────────
def card_activity(d: dict) -> str:
    days = d["days"]
    s = stats(days)
    c = Card("./stats.sh", "Estatísticas de contribuição: streaks, dias ativos e contribuições por mês")
    boxes = [("streak atual", s["cur"], "dias"), ("maior streak", s["longest"], "dias"),
             ("contribuições", br(s["total"]), "no ano"), ("dias ativos", s["active"], f"de {len(days)}"),
             ("melhor dia", s["best"], "contribuições"), ("média por dia ativo", f"{s['avg']:.1f}".replace(".", ","), "contribuições")]
    gap = 12
    bw, bh, by0 = (W - 2 * M - 2 * gap) / 3, 84, 58
    for i, (lab, val, sub) in enumerate(boxes):
        x, y = M + (i % 3) * (bw + gap), by0 + (i // 3) * (bh + gap)
        c.raw(f'<g class="pop" style="animation-delay:{0.1 + i * 0.07:.2f}s"><rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="{bh}" rx="9" fill="{C["bg"]}" stroke="{C["line"]}"/>')
        c.t(x + 18, y + 26, lab, C["dim"], 12)
        c.t(x + 18, y + 64, val, C["accent"], 34, 700)
        c.t(x + 18 + 20.4 * len(str(val)) + 10, y + 64, sub, C["dim"], 12)
        c.raw("</g>")

    cy = by0 + 2 * (bh + gap) + 24
    c.t(M, cy, "contribuições por mês", C["dim"], 12)
    per: dict = {}
    for dt, v in days:
        per[(dt.year, dt.month)] = per.get((dt.year, dt.month), 0) + v
    keys = sorted(per)[-12:]
    mx = max(per[k] for k in keys) or 1
    hmax, base = 80, cy + 22 + 14 + 80
    pitch = (W - 2 * M) / len(keys)
    bwid = pitch - 16
    for i, k in enumerate(keys):
        v = per[k]
        h = max(3, v / mx * hmax)
        x = M + i * pitch + 8
        c.raw(f'<rect class="gy" style="animation-delay:{0.3 + i * 0.05:.2f}s" x="{x:.1f}" y="{base - h:.1f}" width="{bwid:.1f}" height="{h:.1f}" rx="3" fill="{C["accent"]}" opacity="{0.5 + 0.5 * v / mx:.2f}"/>')
        c.t(x + bwid / 2, base - h - 6, br(v), C["fg"] if v == mx else C["dim"], 11, 700 if v == mx else 400, "middle", cls="fade", delay=0.9 + i * 0.05)
        c.t(x + bwid / 2, base + 17, MONTHS[k[1] - 1], C["dim"], 11, 400, "middle")
    fy = base + 52
    c.raw(f'<line x1="{M}" y1="{fy - 24}" x2="{W - M}" y2="{fy - 24}" stroke="{C["line"]}"/>')
    c.prompt(fy, "", cursor=True)
    c.t(W - M, fy, updated_stamp(), C["dim"], 11, 400, "end")
    return c.render(int(fy + 24))


# ── Faixas de título (como o "What I'm coding" do repositório de referência) ─
def card_strip(cmd: str) -> str:
    h = 46
    H = h + 2 * OP
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{escape(cmd)}" font-family="{FONT}">
<title>{escape(cmd)}</title>
<g transform="translate(0,{OP})"><rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="10" fill="{C["bg"]}" stroke="{C["line"]}"/>
<text x="{M}" y="28" font-size="14"><tspan fill="{C["green"]}" font-weight="600">{USER}@github</tspan><tspan fill="{C["dim"]}"> ~ </tspan><tspan fill="{C["fg"]}">$ {escape(cmd)}</tspan></text></g>
</svg>
'''


# ── Cards de projetos ────────────────────────────────────────────────────────
def build_repo_card(r: dict) -> str:
    RW, RH, P = 440, 132, 22
    W2, H2 = RW + 12, RH + 2 * OP        # 6px de respiro de cada lado: cards lado a lado não colam
    desc = r.get("description") or "Sem descrição."
    lines = textwrap.wrap(desc, 52)
    if len(lines) > 2:
        lines = lines[:2]
        lines[1] = lines[1].rstrip(".,; ")[:49] + "…"
    name = r["name"] if len(r["name"]) <= 30 else r["name"][:29] + "…"
    out = [f'<g transform="translate({P},{P - 3}) scale(1.1)" fill="{C["dim"]}"><path d="{ICON_REPO}"/></g>',
           f'<text x="{P + 26}" y="{P + 12}" font-size="16" font-weight="700" fill="{C["green"]}">{escape(name)}</text>']
    for i, l in enumerate(lines):
        out.append(f'<text x="{P}" y="{P + 42 + i * 19}" font-size="12.5" fill="{C["dim"] if r.get("description") else "#6e7681"}">{escape(l)}</text>')
    y, x = RH - 24, P
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
        out.append(f'<text x="{RW - P}" y="{y}" font-size="11" fill="#6e7681" text-anchor="end">{ago(r["pushedAt"])}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W2}" height="{H2}" viewBox="0 0 {W2} {H2}" role="img" aria-label="{escape(r["name"])}" font-family="{FONT}">
<title>{escape(r["name"])}</title>
<g transform="translate(6,{OP})"><rect x="0.5" y="0.5" width="{RW - 1}" height="{RH - 1}" rx="10" fill="{C["bg"]}" stroke="{C["line"]}"/>
{chr(10).join(out)}</g>
</svg>
'''


def slug(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", n)


def update_readme(repos: list) -> None:
    src = ROOT / "README.md"
    if not src.exists():
        return
    md = src.read_text(encoding="utf-8")
    per_row = 3 if len(repos) % 3 == 0 else 2
    pct = f"{100 / per_row:.3f}".rstrip("0").rstrip(".")
    imgs = [f'<a href="{r["url"]}"><img src="./cards/repo-{slug(r["name"])}.svg" width="{pct}%" alt="{escape(r["name"])}" /></a>' for r in repos]
    rows = "<br>\n".join("".join(imgs[i:i + per_row]) for i in range(0, len(imgs), per_row))
    block = f"<!-- PROJECTS:START -->\n{rows}\n<!-- PROJECTS:END -->"
    new, n = re.subn(r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->", lambda _: block, md, flags=re.S)
    if n:
        (OUT / "README.md").write_text(new, encoding="utf-8")


def main() -> None:
    d = demo_data() if DEMO else fetch_data()
    cards = OUT / "cards"
    cards.mkdir(parents=True, exist_ok=True)
    files = {"heatmap.svg": card_heatmap(d), "profile.svg": card_profile(d), "activity.svg": card_activity(d),
             "title-projetos.svg": card_strip("ls projetos/"), "title-links.svg": card_strip("./links.sh")}
    keep = set(files)
    for name, svg in files.items():
        (cards / name).write_text(svg, encoding="utf-8")
    for r in d["repos"]:
        f = f"repo-{slug(r['name'])}.svg"
        (cards / f).write_text(build_repo_card(r), encoding="utf-8")
        keep.add(f)
    for old in cards.glob("*.svg"):
        if old.name not in keep:
            old.unlink()
    for legacy in [OUT / "profile-card.svg", *(OUT / "assets").glob("repo-*.svg")]:   # versão anterior
        legacy.unlink(missing_ok=True)
    update_readme(d["repos"])
    print("ok ->", cards)


if __name__ == "__main__":
    main()
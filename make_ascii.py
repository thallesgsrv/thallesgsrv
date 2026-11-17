#!/usr/bin/env python3
"""Converte uma foto em retrato ASCII e grava em ascii.txt (usado pelo generate.py).

O fundo da foto é removido automaticamente (preenchimento a partir das bordas), então só
o rosto/ombros viram caracteres e o resto fica vazio, ideal para o cartão escuro.

  pip install pillow
  python make_ascii.py perfil.png
  python make_ascii.py perfil.png --tol 55        # fundo não saiu inteiro? aumente (30–80)
  python make_ascii.py perfil.png --tol 20        # comeu parte do rosto/cabelo? diminua
  python make_ascii.py perfil.png --cols 80       # mais detalhe
  python make_ascii.py perfil.png --gamma 1.5     # mais contraste nos meios-tons
  python make_ascii.py perfil.png --keep-bg       # não remover o fundo
  python make_ascii.py perfil.png --invert        # troca claro/escuro
"""
import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

RAMP = " .'`^:;-~=+*xoO#%@"   # do vazio ao denso
CELL_ASPECT = 0.54            # largura/altura de uma célula do SVG


def subject_mask(rgb: Image.Image, tol: int) -> Image.Image:
    """Máscara 255 = sujeito, 0 = fundo (flood fill a partir das bordas)."""
    w, h = rgb.size
    work = rgb.copy()
    mark = (255, 0, 255)
    # cor de referência do fundo: média dos cantos superiores (corpo/ombros ficam embaixo)
    k = max(3, w // 40)
    ref = [sum(c) // len(c) for c in zip(*(rgb.crop(box).resize((1, 1), Image.BOX).getpixel((0, 0))
                                          for box in ((0, 0, k, k), (w - k, 0, w, k))))]
    step = lambda n: max(1, n // 16)
    border = [(x, 0) for x in range(0, w, step(w))] + [(x, h - 1) for x in range(0, w, step(w))] \
           + [(0, y) for y in range(0, h, step(h))] + [(w - 1, y) for y in range(0, h, step(h))]
    for p in border:                                            # só semeia onde a cor parece fundo
        px = work.getpixel(p)
        if px != mark and max(abs(px[i] - ref[i]) for i in range(3)) <= tol + 25:
            ImageDraw.floodfill(work, p, mark, thresh=tol)
    r, g, b = work.split()
    bg = ImageChops.multiply(ImageChops.multiply(r.point(lambda v: 255 if v == 255 else 0),
                                                 g.point(lambda v: 255 if v == 0 else 0)),
                             b.point(lambda v: 255 if v == 255 else 0))
    m = ImageOps.invert(bg)
    m = m.filter(ImageFilter.MedianFilter(7))                   # tira ruído
    m = m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))   # fecha buracos pequenos
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--cols", type=int, default=66)
    ap.add_argument("--gamma", type=float, default=1.2)
    ap.add_argument("--tol", type=int, default=40)
    ap.add_argument("--keep-bg", action="store_true")
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).with_name("ascii.txt")))
    a = ap.parse_args()

    im = ImageOps.exif_transpose(Image.open(a.image))
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bgc = Image.new("RGBA", im.size, (255, 255, 255, 255))
        im = Image.alpha_composite(bgc, im)
    rgb = im.convert("RGB")
    rgb.thumbnail((700, 700), Image.LANCZOS)                    # trabalho em resolução menor

    mask = Image.new("L", rgb.size, 255) if a.keep_bg else subject_mask(rgb, a.tol)
    box = mask.getbbox()
    if box and not a.keep_bg:                                   # recorta no sujeito, com folga
        pad = int(0.04 * max(rgb.size))
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(rgb.width, box[2] + pad), min(rgb.height, box[3] + pad))
        rgb, mask = rgb.crop(box), mask.crop(box)

    gray = rgb.convert("L")
    try:
        gray = ImageOps.autocontrast(gray, cutoff=2, mask=mask)  # contraste só no sujeito
    except TypeError:
        gray = ImageOps.autocontrast(gray, cutoff=2)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=3, percent=160, threshold=2))

    cols = a.cols
    rows = max(1, round(cols * gray.height / gray.width * CELL_ASPECT))
    g = gray.resize((cols, rows), Image.LANCZOS)
    m = mask.resize((cols, rows), Image.BOX)
    if a.invert:
        g = ImageOps.invert(g)

    gp, mp, n = g.load(), m.load(), len(RAMP) - 1
    lines = []
    for y in range(rows):
        row = "".join(" " if mp[x, y] < 128 else
                      RAMP[max(1, min(n, int((gp[x, y] / 255) ** a.gamma * n + 0.5)))] for x in range(cols))
        lines.append(row.rstrip())
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ok -> {a.out}  ({cols}x{rows})")


if __name__ == "__main__":
    main()
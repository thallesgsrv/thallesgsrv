#!/usr/bin/env python3
"""Converte uma foto em retrato ASCII e grava em ascii.txt (usado pelo generate.py).

  pip install pillow
  python make_ascii.py perfil.png                 # padrão: 70 colunas
  python make_ascii.py perfil.png --cols 80       # mais detalhe
  python make_ascii.py perfil.png --invert        # se o fundo da foto for claro e o rosto sair "apagado"
  python make_ascii.py perfil.png --gamma 1.4     # >1 escurece os meios-tons, <1 clareia
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

RAMP = " .'`^:;-~=+*xoO#%@"   # do vazio (escuro) ao denso (claro)
CELL_ASPECT = 0.54            # largura/altura de uma célula do SVG (5,8 x 10,7 px)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--cols", type=int, default=70)
    ap.add_argument("--gamma", type=float, default=1.15)
    ap.add_argument("--invert", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).with_name("ascii.txt")))
    a = ap.parse_args()

    im = Image.open(a.image)
    if im.mode in ("RGBA", "LA"):                      # transparência -> fundo preto
        bg = Image.new("RGBA", im.size, (0, 0, 0, 255))
        im = Image.alpha_composite(bg, im.convert("RGBA"))
    g = ImageOps.exif_transpose(im).convert("L")

    rows = max(1, round(a.cols * g.height / g.width * CELL_ASPECT))
    g = g.resize((a.cols * 4, rows * 4), Image.LANCZOS)          # reduz em 2 etapas: mais nítido
    g = ImageOps.autocontrast(g, cutoff=2)
    g = g.filter(ImageFilter.UnsharpMask(radius=2, percent=140, threshold=2))
    g = g.resize((a.cols, rows), Image.LANCZOS)
    if a.invert:
        g = ImageOps.invert(g)

    px, n = g.load(), len(RAMP) - 1
    lines = []
    for y in range(rows):
        row = "".join(RAMP[min(n, int((px[x, y] / 255) ** a.gamma * n + 0.5))] for x in range(a.cols))
        lines.append(row.rstrip())
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"ok -> {a.out}  ({a.cols}x{rows})")


if __name__ == "__main__":
    sys.exit(main())

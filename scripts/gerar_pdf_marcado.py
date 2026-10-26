"""
gerar_pdf_marcado.py
---------------------
Renderiza o DXF da prancha num PDF fiel ao que sai impresso (fundo branco, desenho em
preto, igual plotagem real em P&B) e marca em cima, com marca-texto nativo de PDF (igual
a ferramenta "Destacar" do Foxit/Acrobat), cada achado da revisao. Cada marcacao carrega
um comentario clicavel explicando o problema, cor por categoria:

  amarelo  = legibilidade (texto abaixo da altura minima)
  vermelho = sobreposicao/colisao entre elementos
  laranja  = invasao da area do carimbo
  azul     = fechamento de cota (divergencia entre total e soma das parciais)

Recebe os achados num JSON (lista de objetos com categoria, bbox [x0,y0,x1,y1] nas
MESMAS coordenadas brutas do DXF, e descricao). Esse JSON e montado pela skill a partir
dos dados de analisar_dxf.py, nao por este script.

Requer ezdxf, matplotlib e pymupdf (pip install ezdxf matplotlib pymupdf).
"""

import sys
import json
import argparse

try:
    import ezdxf
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as ex:
    print(f"Erro: falta pacote ({ex}). Rode: pip install ezdxf matplotlib")
    sys.exit(1)

try:
    import pymupdf as fitz
except ImportError:
    print("Erro: pacote 'pymupdf' nao instalado. Rode: pip install pymupdf")
    sys.exit(1)

CORES = {
    "legibilidade": (1, 0.9, 0),       # amarelo
    "sobreposicao": (1, 0.2, 0.2),     # vermelho
    "invasao_carimbo": (1, 0.55, 0),   # laranja
    "fechamento_cota": (0.2, 0.5, 1),  # azul
}


def renderizar_base(doc, largura_pol=16.8, altura_pol=11.9):
    msp = doc.modelspace()
    fig = plt.figure(figsize=(largura_pol, altura_pol))
    ax = fig.add_axes([0, 0, 1, 1])
    ctx = RenderContext(doc)
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.MONOCHROME_LIGHT_BG)
    backend = MatplotlibBackend(ax)
    Frontend(ctx, backend, config=cfg).draw_layout(msp, finalize=True)
    return fig, ax


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", help="caminho do arquivo DXF")
    ap.add_argument("achados", help="JSON com a lista de achados (categoria, bbox, descricao)")
    ap.add_argument("--out", required=True, help="PDF de saida, marcado")
    args = ap.parse_args()

    doc = ezdxf.readfile(args.dxf)
    achados = json.load(open(args.achados, encoding="utf-8"))

    fig, ax = renderizar_base(doc)
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    w_in, h_in = fig.get_size_inches()

    pdf_tmp = args.out + ".base.pdf"
    fig.savefig(pdf_tmp)
    plt.close(fig)

    docpdf = fitz.open(pdf_tmp)
    page = docpdf[0]

    def dxf_para_pdf(bbox):
        x0, y0, x1, y1 = bbox
        px0 = (x0 - xlim[0]) / (xlim[1] - xlim[0]) * w_in * 72
        px1 = (x1 - xlim[0]) / (xlim[1] - xlim[0]) * w_in * 72
        py0_frombaixo = (y0 - ylim[0]) / (ylim[1] - ylim[0]) * h_in * 72
        py1_frombaixo = (y1 - ylim[0]) / (ylim[1] - ylim[0]) * h_in * 72
        py0 = page.rect.height - py1_frombaixo
        py1 = page.rect.height - py0_frombaixo
        return fitz.Rect(min(px0, px1), min(py0, py1), max(px0, px1), max(py0, py1))

    contagem = {}
    for a in achados:
        categoria = a["categoria"]
        cor = CORES.get(categoria, (0.6, 0.6, 0.6))
        rect = dxf_para_pdf(a["bbox"])
        if rect.width < 1:
            rect.x1 += 1
        if rect.height < 1:
            rect.y1 += 1
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=cor)
        annot.set_info(content=a.get("descricao", ""), title=categoria)
        annot.update()
        contagem[categoria] = contagem.get(categoria, 0) + 1

    docpdf.save(args.out)
    docpdf.close()

    import os
    os.remove(pdf_tmp)

    print(f"PDF marcado salvo em {args.out}")
    for cat, qtd in contagem.items():
        print(f"  {cat}: {qtd} marcacao(oes)")


if __name__ == "__main__":
    main()

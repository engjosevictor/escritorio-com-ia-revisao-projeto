"""
analisar_dxf.py
----------------
Le um DXF de prancha de projeto (estrutural, arquitetonico, qualquer disciplina) e
extrai os dados brutos que a skill revisao-projeto usa pra apontar problemas:

- Toda entidade do modelspace (texto, cota, linha, hachura, arco, circulo etc.): camada,
  bounding box REAL (via ezdxf.bbox.extents, que renderiza a fonte de verdade pro texto,
  nao estima por numero de caractere) e o conteudo, quando for texto/cota
- Lista de camadas existentes no arquivo (pra perguntar ao usuario qual e qual, nunca
  adivinhar nome de camada)
- Calibracao de unidade: compara o tamanho bruto da camada informada como moldura/limite
  da folha contra os formatos de papel ABNT (A0 a A4), pra descobrir o fator real sem
  depender do $INSUNITS do cabecalho (que vem errado com frequencia em DXF convertido de
  DWG)
- Escalas encontradas no proprio desenho (texto "Escala N:N"), pra contexto do relatorio

Nao decide nada por conta propria (altura minima aceitavel, qual camada e o carimbo): so
devolve os dados em JSON pra quem esta usando a skill decidir junto com o usuario.

Requer o pacote ezdxf (pip install ezdxf).
"""

import re
import sys
import json
import argparse

try:
    import ezdxf
    from ezdxf import bbox as ezbbox
except ImportError:
    print("Erro: pacote 'ezdxf' nao instalado. Rode: pip install ezdxf")
    sys.exit(1)

PADRAO_ESCALA = re.compile(r"\b(?:escala|esc)\.?\s*1\s*:\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE)

# formatos ABNT em cm (largura, altura)
FORMATOS_PAPEL_CM = {
    "A0": (118.9, 84.1),
    "A1": (84.1, 59.4),
    "A2": (59.4, 42.0),
    "A3": (42.0, 29.7),
    "A4": (29.7, 21.0),
}
FATORES_CANDIDATOS = [0.001, 0.01, 0.1, 1, 10, 100, 1000]


def calibrar_unidade_por_folha(largura_bruta, altura_bruta):
    """Compara o tamanho bruto da moldura com os formatos ABNT em varios fatores de
    escala pra descobrir quanto multiplicar as coordenadas do DXF pra virar centimetro
    real de papel. Nunca confia no $INSUNITS do cabecalho, que costuma vir errado em
    arquivo convertido de DWG."""
    melhor = None
    for fator in FATORES_CANDIDATOS:
        l, a = largura_bruta * fator, altura_bruta * fator
        for formato, (w, h) in FORMATOS_PAPEL_CM.items():
            for ww, hh in ((w, h), (h, w)):
                erro = abs(l - ww) / ww + abs(a - hh) / hh
                if erro < 0.1 and (melhor is None or erro < melhor["erro"]):
                    melhor = {"fator_para_cm": fator, "formato_detectado": formato, "erro": erro}
    return melhor


def texto_da_entidade(e):
    tipo = e.dxftype()
    if tipo == "MTEXT":
        return e.plain_text()
    if tipo == "TEXT":
        return e.dxf.text
    return None


def altura_da_entidade(e):
    tipo = e.dxftype()
    if tipo == "MTEXT":
        return e.dxf.char_height
    if tipo == "TEXT":
        return e.dxf.height
    return None


def extrair_entidades(msp):
    entidades = []
    falhas = 0
    for e in msp:
        caixa = ezbbox.extents([e], fast=False)
        if caixa.extmin is None:
            falhas += 1
            continue
        item = {
            "tipo": e.dxftype(),
            "camada": e.dxf.layer,
            "bbox": [caixa.extmin.x, caixa.extmin.y, caixa.extmax.x, caixa.extmax.y],
        }
        texto = texto_da_entidade(e)
        if texto is not None:
            item["texto"] = texto
            item["altura"] = altura_da_entidade(e)
        if e.dxftype() == "DIMENSION":
            try:
                item["medida_real"] = e.get_measurement()
            except Exception:
                pass
        entidades.append(item)
    return entidades, falhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dxf", help="caminho do arquivo DXF")
    ap.add_argument("--out", default=None, help="arquivo de saida JSON (senao imprime no terminal)")
    ap.add_argument("--camada-moldura", default=None,
                     help="nome(s) da camada do limite externo da folha, separados por virgula, pra calibrar a unidade real contra os formatos ABNT")
    args = ap.parse_args()

    doc = ezdxf.readfile(args.dxf)
    msp = doc.modelspace()
    camadas = sorted({layer.dxf.name for layer in doc.layers})

    entidades, falhas = extrair_entidades(msp)
    if falhas:
        print(f"aviso: {falhas} entidade(s) sem bounding box calculavel, ignoradas", file=sys.stderr)

    textos = [e for e in entidades if "texto" in e]

    calibracao = None
    if args.camada_moldura:
        camadas_moldura = {c.strip() for c in args.camada_moldura.split(",")}
        caixa_moldura = [e["bbox"] for e in entidades if e["camada"] in camadas_moldura]
        if caixa_moldura:
            x0 = min(b[0] for b in caixa_moldura)
            y0 = min(b[1] for b in caixa_moldura)
            x1 = max(b[2] for b in caixa_moldura)
            y1 = max(b[3] for b in caixa_moldura)
            largura_bruta, altura_bruta = x1 - x0, y1 - y0
            calibracao = calibrar_unidade_por_folha(largura_bruta, altura_bruta) or {
                "aviso": "nao bateu com nenhum formato ABNT nos fatores testados, confirmar manualmente",
            }
            calibracao["largura_bruta"] = largura_bruta
            calibracao["altura_bruta"] = altura_bruta

    escalas_encontradas = []
    for t in textos:
        m = PADRAO_ESCALA.search(t["texto"])
        if m:
            escalas_encontradas.append({
                "texto": t["texto"].strip(),
                "valor_escala": float(m.group(1).replace(",", ".")),
                "x": (t["bbox"][0] + t["bbox"][2]) / 2,
                "y": (t["bbox"][1] + t["bbox"][3]) / 2,
            })

    resultado = {
        "arquivo": args.dxf,
        "unidades_insunits_header": doc.header.get("$INSUNITS", None),
        "camadas": camadas,
        "total_entidades": len(entidades),
        "total_textos": len(textos),
        "calibracao_unidade": calibracao,
        "escalas_encontradas": escalas_encontradas,
        "entidades": entidades,
    }

    saida = json.dumps(resultado, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(saida)
        print(f"Dados extraidos em {args.out} ({len(entidades)} entidades, {len(textos)} textos, {len(camadas)} camadas)")
    else:
        print(saida)


if __name__ == "__main__":
    main()

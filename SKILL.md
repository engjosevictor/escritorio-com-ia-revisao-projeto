---
name: revisao-projeto
description: Revisa visualmente uma prancha de projeto (arquitetônico, estrutural, qualquer disciplina) em DXF, procurando problemas gráficos antes de mandar pra impressão ou pra obra, como texto ilegível na escala, sobreposição de texto/cota, desenho invadindo o carimbo ou a margem, cota que não fecha, e carimbo com campo vazio. Entrega um PDF da própria prancha com cada achado marcado em cima do desenho (marca-texto colorido por categoria, com comentário clicável), além do relatório em texto. Use quando o usuário mandar um arquivo DXF de prancha pedindo pra revisar, conferir, checar antes de plotar/imprimir, ou mencionar "revisão de projeto", "confere essa prancha", "ta pronta pra imprimir".
---

# Revisão de Projeto

Revisa uma prancha de projeto em DXF por problemas gráficos (não é revisão técnica de
cálculo ou de norma, é revisão visual: o que vai ficar ilegível ou errado quando a
prancha for plotada ou impressa).

Sempre recebe DXF (nunca PDF/imagem) — é o que dá precisão pra medir altura real de
texto e posição exata dos elementos.

## Fase 0 — Entender a prancha antes de checar qualquer coisa

Rodar `scripts/analisar_dxf.py <arquivo.dxf>` primeiro:

```
python scripts/analisar_dxf.py "prancha.dxf" --out dados.json
```

Requer `ezdxf` (`pip install ezdxf`) — perguntar antes de instalar se não tiver.

Depois, resolver (sem perguntar à toa, só quando o arquivo não responder):

1. **Nome da camada (layer) do limite externo da folha (moldura/margem).** Mostrar a
   lista de camadas encontradas (`camadas`) e pedir pro usuário confirmar qual é — nunca
   adivinhar pelo nome parecido ("MARGEM", "MOLDURA", "FORMATO" etc.), mesmo quando
   parecer óbvio. Rodar de novo com `--camada-moldura "<nome(s)>"` (aceita mais de uma
   camada separada por vírgula, ex. moldura fina + moldura grossa)
2. **Calibrar a unidade real pelo tamanho da folha, não pelo cabeçalho do arquivo.** O
   script compara o tamanho bruto da moldura com os formatos ABNT (A0 a A4) em vários
   fatores de escala e devolve em `calibracao_unidade` qual fator converte a coordenada
   bruta do DXF pra centímetro real de papel. **Nunca usar o `$INSUNITS` do cabeçalho**
   (`unidades_insunits_header`) pra isso — ele costuma vir errado em arquivo convertido de
   DWG pra DXF, mesmo quando a geometria em si está correta. Se a calibração não bater com
   nenhum formato ABNT (campo `aviso` em vez de `fator_para_cm`), avisar o usuário e
   perguntar a unidade real antes de continuar
3. **Nome da camada (layer) do carimbo**, se for diferente da moldura. Mesma regra, nunca
   adivinhar. Sem essa confirmação, a checagem de invasão do carimbo não roda
4. **Escala(s) da prancha**, só como contexto do relatório (não entra na conta de altura,
   ver Fase 1). O script já procura texto no padrão "Escala N:N" no próprio DXF
   (`escalas_encontradas`). Uma prancha pode ter mais de uma escala (detalhes diferentes
   na mesma folha) — nesse caso, associar cada achado à escala mais próxima dele (mesma
   lógica de proximidade usada na skill de vigas pra separar valores por vão) só pra dizer
   no relatório "esse detalhe está em 1:25", não pra calcular altura
5. **Altura mínima de texto aceitável no papel**: usar 2mm como padrão, sem perguntar.
   Só perguntar se o usuário mencionar que o escritório usa outro valor, ou se pedir pra
   mudar depois de ver o resultado

## Fase 1 — Rodar as checagens

Com os dados extraídos (`dados.json`) e as respostas da Fase 0, verificar cada bloco.
Todas as checagens são geométricas, a partir dos números reais do arquivo — nunca
afirmar um problema que não foi medido.

**Legibilidade**
1. Altura real de texto/cota no papel (mm) = altura bruta no DXF × `fator_para_cm` × 10.
   Marcar qualquer texto abaixo do mínimo combinado na Fase 0
2. (Não avaliar espessura/peso de linha nem hachura por enquanto — o DXF puro não traz
   isso de forma confiável sem saber o estilo de plotagem de cada escritório; avisar essa
   limitação se o usuário perguntar)

**Sobreposição e colisão**
3. Comparar a bounding box real de cada entidade (`entidades[].bbox`, já vem da
   geometria renderizada de verdade via `ezdxf.bbox.extents`, não é estimativa) com as
   demais, apontando pares que se cruzam
4. Se a camada do carimbo foi informada: apontar qualquer entidade de outra camada que
   invade essa área. Elemento da própria moldura/letra de referência encostando na borda
   do carimbo é esperado, não é erro — usar bom senso ao reportar isso como achado real
   ou como adjacência normal
5. Se a camada da moldura/limite da folha foi informada: apontar elemento que ultrapassa
   esse limite

**Fechamento de cota**
6. Cada entidade `DIMENSION` já traz `medida_real` (distância geométrica medida de
   verdade, não o texto digitado na cota, que normalmente vem vazio por ser automático).
   Agrupar cotas próximas e alinhadas no mesmo eixo (mesma lógica de proximidade usada
   nos outros blocos) pra achar cadeias onde uma cota "total" deveria bater com a soma de
   cotas "parciais" menores dentro do mesmo trecho. Só reportar divergência quando a
   cadeia for inequívoca (uma cota maior cobrindo claramente o mesmo intervalo de um
   grupo de cotas menores); se o agrupamento ficar ambíguo, não forçar uma comparação,
   avisar que não foi possível confirmar essa cadeia com segurança

**Carimbo**
7. Dentro da área do carimbo (se informada), listar os textos encontrados e perguntar ao
   usuário se os campos obrigatórios (título, escala, data, revisão, responsável técnico,
   registro profissional) estão todos preenchidos — a skill mostra o que tem, o usuário
   confirma se falta algo, porque ela não sabe de cor o padrão de carimbo de cada
   escritório

## Fase 2 — Relatório em texto

Organizar os achados nos mesmos quatro blocos da Fase 1, cada um com a coordenada (x, y)
e a camada do elemento, pra facilitar achar no CAD. Nada de problema encontrado num
bloco, dizer isso explicitamente ("sem problema de legibilidade encontrado") em vez de
omitir o bloco.

## Fase 3 — PDF marcado (entrega principal)

Além do relatório em texto, gerar um PDF da prancha com cada achado marcado em cima do
desenho real, igual marca-texto (ferramenta "Destacar" do Foxit/Acrobat): o usuário abre
o PDF, vê a marcação colorida em cima do elemento exato, e clica pra ler o comentário com
o problema.

1. Montar uma lista de achados em JSON, um item por achado:
   `{"categoria": "legibilidade|sobreposicao|invasao_carimbo|fechamento_cota", "bbox": [x0,y0,x1,y1], "descricao": "texto explicando o problema"}`.
   O `bbox` usa as **mesmas coordenadas brutas do DXF** (não precisa converter nada, o
   script cuida do mapeamento pro PDF)
2. Rodar, passando o `fator_para_cm` que a Fase 0 já calibrou (`calibracao_unidade` no JSON
   do `analisar_dxf.py`) — sem isso a página do PDF nasce num tamanho arbitrário e todo
   texto fino (tabela, cota, nota) fica pequeno demais pra aparecer:
   ```
   python scripts/gerar_pdf_marcado.py "prancha.dxf" achados.json --fator-cm 1 --out "prancha_revisada.pdf"
   ```
3. O script renderiza a prancha em preto sobre fundo branco, no tamanho real da folha
   (igual sai impresso — não é o tema escuro do CAD, nem um tamanho reduzido), e sobrepõe
   o marca-texto de cada achado em opacidade baixa (pra não empilhar virando um borrão
   sólido quando vários achados ficam próximos), com cor por categoria (amarelo =
   legibilidade, vermelho = sobreposição, laranja = invasão de carimbo, azul = fechamento
   de cota) e o comentário anexado como nota clicável no PDF
4. Requer `matplotlib` e `pymupdf`, além do `ezdxf` já usado na Fase 0 — perguntar antes
   de instalar o que faltar
5. Entregar o caminho completo do PDF gerado, e avisar que cada marcação tem um
   comentário (a maioria dos leitores de PDF mostra isso ao clicar ou passar o mouse em
   cima, ou num painel de comentários lateral)

## Regras

1. Nunca afirmar um problema sem ter extraído o dado real do DXF que o comprova
2. Nunca adivinhar o nome da camada do carimbo, da moldura ou do limite da folha —
   perguntar, usando a lista de camadas do arquivo como referência
3. Nunca confiar no `$INSUNITS` do cabeçalho do DXF pra converter unidade — sempre
   calibrar pelo tamanho real da moldura contra os formatos ABNT. Se não bater com nenhum
   formato, perguntar ao usuário em vez de supor um fator
4. Não fazer revisão técnica (cálculo, norma, dimensionamento) — isso é outra skill. Essa
   é só revisão gráfica
5. Nunca instalar pacote (`ezdxf`, `matplotlib`, `pymupdf`) sem perguntar antes
6. O PDF marcado sempre renderiza em preto sobre fundo branco, nunca no tema escuro do
   CAD — é isso que corresponde ao que realmente sai impresso, e é o que faz o marca-texto
   aparecer (ele fica invisível sobre fundo preto)

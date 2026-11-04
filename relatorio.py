"""Relatório estático da operação Olist, num arquivo HTML só.

Execução:
    uv run python relatorio.py

A spec do painel (docstring de painel.py) continua valendo aqui: nenhum
cálculo, só leitura, formatação e as mesmas funções de gráfico.

R1. FONTE
    Lê os marts com painel.ler(), formata com painel.reais/pct/numero e
    monta os gráficos com as funções de painel.py. Não importa streamlit.
    Não desenha nenhum gráfico que não esteja em painel.py.
    Por quê: página e relatório mostram o mesmo número do mesmo jeito.

R2. SAÍDA
    Escreve relatorio.html na raiz: um arquivo só, com as mesmas quatro
    faixas do app.py, na mesma ordem. Cartões em HTML simples, numa grade.
    Gráficos com figura.to_html(full_html=False); a biblioteca do plotly
    vem do CDN uma vez só, no primeiro gráfico (include_plotlyjs="cdn"), e
    nos outros include_plotlyjs=False. Cada gráfico com div_id fixo ("g01",
    "g02"...).
    Por quê: sem o id fixo o plotly sorteia um novo a cada execução, e o
    arquivo muda sem o dado mudar.

R3. SEM FILTRO
    O faturamento mostra o período padrão do app.py (jan/2017 a ago/2018),
    e o título do gráfico diz o período.

R4. RODAPÉ
    Data e hora em que o arquivo foi gerado: "Dados de 25/10/2026 14:03".
    Por quê: o arquivo não fala com o banco; quem lê precisa saber de
    quando é o número.

R5. SAÍDA NA TELA
    Imprime o caminho do arquivo e o tamanho em KB. stdout em utf-8.

Critérios de aceite:
- Abrir relatorio.html com dois cliques mostra os sete cartões com os
  mesmos valores do app.py.
- O arquivo tem menos de 200 KB.
- Rodar duas vezes muda só a data do rodapé.
"""

import sys
from datetime import datetime
from html import escape
from pathlib import Path

import painel

ARQUIVO = Path(__file__).resolve().parent / "relatorio.html"

CSS = """
:root { --fundo: #fcfcfb; --cartao: #ffffff; --borda: #e4e3df;
        --texto: #0b0b0b; --texto-2: #52514e; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 16px; background: var(--fundo);
       color: var(--texto); font-family: system-ui, sans-serif; }
main { max-width: 1400px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 4px; }
.nota { color: var(--texto-2); font-size: .85rem; margin: 0 0 20px; }
.cartoes { display: grid; gap: 12px; margin-bottom: 16px;
           grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
.cartao { background: var(--cartao); border: 1px solid var(--borda);
          border-radius: 8px; padding: 12px 14px; }
.rotulo { color: var(--texto-2); font-size: .8rem; }
.valor { font-size: 1.6rem; font-weight: 600; margin-top: 4px;
         font-variant-numeric: tabular-nums; }
.faixa { display: grid; gap: 12px; margin-bottom: 12px;
         grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.grafico { background: var(--cartao); border: 1px solid var(--borda);
           border-radius: 8px; padding: 4px; min-width: 0; }
footer { color: var(--texto-2); font-size: .85rem; margin-top: 20px; }
"""


def _cartoes(dados) -> str:
    itens = "".join(
        f'<div class="cartao"><div class="rotulo">{escape(r)}</div>'
        f'<div class="valor">{escape(v)}</div></div>'
        for r, v in painel.cartoes(dados)
    )
    return f'<section class="cartoes">{itens}</section>'


def _graficos(figuras) -> list[str]:
    blocos = []
    for i, fig in enumerate(figuras, start=1):
        trecho = fig.to_html(
            full_html=False,
            include_plotlyjs="cdn" if i == 1 else False,
            div_id=f"g{i:02d}",
            config={"displaylogo": False, "responsive": True},
        )
        blocos.append(f'<div class="grafico">{trecho}</div>')
    return blocos


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    try:
        dados = painel.ler(painel.MARTS)
    except painel.DadosFaltando as e:
        print("Faltando: " + ", ".join(e.faltando), file=sys.stderr)
        print(f'Rode antes: "{painel.COMANDO_MARTS}"', file=sys.stderr)
        sys.exit(1)

    inicio, fim = painel.PERIODO_PADRAO
    faturamento = painel.faturamento_mensal(
        painel.recortar_periodo(dados["vendas_mensais"], inicio, fim)
    )
    # Só o texto do título muda; o gráfico continua o de painel.py.
    faturamento.update_layout(
        title=f"01 · Faturamento mensal · {painel.mes_ano(inicio)} a {painel.mes_ano(fim)}"
    )

    # Mesma ordem do app.py: faixa 2, depois faixas 3 e 4.
    g = _graficos([
        faturamento,
        painel.receita_por_categoria(dados["top_categorias"]),
        painel.mix_pagamento(dados["mix_pagamento"]),
        painel.ticket_por_uf(dados["ticket_medio_por_estado"]),
        painel.clientes_por_uf(dados["clientes_por_uf"]),
        painel.nota_por_categoria(dados["nota_por_categoria"]),
        painel.concentracao_vendedores(dados["vendedores_pareto"]),
    ])

    gerado = datetime.now().strftime("%d/%m/%Y %H:%M")
    html = f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist · visão da operação</title>
<style>{CSS}</style>
</head>
<body>
<main>
<h1>Olist · visão da operação</h1>
<p class="nota">Os cartões valem para o período inteiro.</p>
{_cartoes(dados)}
<section>{g[0]}</section>
<section class="faixa">{"".join(g[1:4])}</section>
<section class="faixa">{"".join(g[4:7])}</section>
<footer>Dados de {gerado}</footer>
</main>
</body>
</html>
"""
    # newline="\n": no Windows o padrão gravaria \r\n, e o arquivo mudaria
    # conforme a máquina que gerou.
    ARQUIVO.write_text(html, encoding="utf-8", newline="\n")
    print(f"{ARQUIVO}  {painel.numero(ARQUIVO.stat().st_size / 1024, 1)} KB")


if __name__ == "__main__":
    main()

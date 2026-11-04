"""Painel da operação Olist: leitura dos marts, formatação e gráficos.

Este módulo não importa streamlit. Quem desenha a página é app.py; o
relatório HTML reaproveita as mesmas funções daqui.

1. LEITURA
   ler(marts) -> dict nome -> DataFrame. Para cada nome, só
   SELECT * FROM marts.<nome>. Nenhuma outra SQL.
   Conexão com duckdb.connect("olist.duckdb", read_only=True), aberta e
   fechada dentro de ler().
   Por quê: conexão aberta segura o arquivo, e o pipeline.marts não
   consegue gravar com o painel de pé.

2. NENHUM CÁLCULO
   Proibido aqui e em app.py: agrupar, somar, tirar média, contar, juntar
   tabelas, pivotar, e qualquer conta entre colunas. Permitido: ordenar,
   filtrar linhas, pegar as n primeiras, renomear coluna e formatar texto.
   Por quê: número novo na tela exige um .sql novo em marts. Se faltar
   algum número, o certo é parar e dizer qual mart está faltando.
   Única exceção: Recompra = 100 - recompra.pct_clientes da linha
   pedidos_por_cliente = 1, porque o mart 05 guarda o complemento.

3. LAYOUT (app.py), de cima para baixo, layout="wide"
   Cabeçalho: título "Olist · visão da operação" à esquerda; à direita, o
     filtro de período (item 5).
   Faixa 1: sete cartões (st.metric), nesta ordem, cada rótulo com a
     definição curta: Ticket médio (kpis.ticket_medio, reais) · Cancelados
     (kpis.pct_cancelados, 2 casas) · Peso do frete (kpis.pct_frete, 1 casa)
     · Recompra (item 2, 2 casas) · No prazo (entrega_no_prazo.pct_no_prazo,
     1 casa) · Dias até entregar (kpis.dias_entrega, 1 casa) · Nota média
     (kpis.nota_media, 2 casas).
   Faixa 2, largura inteira: faturamento mensal, linha com marcadores.
   Faixa 3, três colunas: receita por categoria (top 10, barras
     horizontais, maior em cima); mix de pagamento (barras por pct_valor);
     ticket médio por UF (barras horizontais, maior em cima).
   Faixa 4, três colunas: clientes por UF (barras horizontais, maior em
     cima); nota por categoria (10 primeiras por posicao_pior, pontos, pior
     em cima); concentração de vendedores (pct_acumulado por posicao, com
     linha horizontal tracejada em 80).
   Cada gráfico: título com o número do mart ("01 · Faturamento mensal"),
   uma cor só, eixo com unidade, width="stretch".

4. FORMATO
   reais(valor, casas=2)  -> "R$ 1.003.862,14"
   pct(valor, casas=1)    -> "93,2%"
   numero(valor, casas=0) -> "96.470"
   Milhar com ponto, decimal com vírgula, sempre. Sem locale do sistema.
   Por quê: o resultado não pode depender da máquina de quem roda.
   Uma função por gráfico, recebendo o DataFrame e devolvendo a figura
   plotly.
   Por quê: o relatório HTML reaproveita as mesmas funções.

5. FILTRO DE PERÍODO (app.py)
   st.select_slider com os meses de vendas_mensais, padrão de jan/2017 a
   ago/2018. Recorta só as linhas do gráfico de faturamento; os cartões e
   os outros gráficos não mudam, e a página diz isso embaixo do filtro.
   Por quê: recortar linha é SELECT; recalcular cartão por período seria
   regra de negócio fora do SQL.

6. CACHE E ERRO (app.py)
   Leitura com st.cache_data; o botão "Recarregar dados" limpa o cache.
   Sem olist.duckdb, ou faltando qualquer mart usado no item 3: st.error
   dizendo quais, com o comando "uv run python -m pipeline.marts", e
   st.stop().
   Por quê: um painel vazio ou pela metade parece operação parada.

Critérios de aceite:
- Os sete cartões mostram: R$ 137,42 · 0,63% · 14,2% · 3,04% · 93,2% ·
  12,5 · 4,09.
- O faturamento abre com 20 meses (jan/2017 a ago/2018) e, com o filtro
  aberto até as pontas, mostra os 24.
- Top 10 de categorias com health_beauty em cima; nota com office_furniture
  em cima; ticket por UF com PB em cima e SP embaixo.
- Nenhuma função de agregação ou junção de pandas aparece neste arquivo
  nem em app.py.
- Com o painel de pé, uv run python -m pipeline.marts roda sem erro de lock.
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Mesmo critério do pipeline/db.py: caminho relativo a este arquivo, para
# "streamlit run" de outra pasta não falhar procurando o banco no cwd.
BANCO = Path(__file__).resolve().parent / "olist.duckdb"

# Só os marts que a página usa (item 3); a checagem do item 6 vale para eles.
MARTS = [
    "kpis",
    "recompra",
    "entrega_no_prazo",
    "vendas_mensais",
    "top_categorias",
    "mix_pagamento",
    "ticket_medio_por_estado",
    "clientes_por_uf",
    "nota_por_categoria",
    "vendedores_pareto",
]

COMANDO_MARTS = "uv run python -m pipeline.marts"

# Período que o faturamento mostra ao abrir (item 5); o relatório usa o mesmo.
PERIODO_PADRAO = (pd.Timestamp("2017-01-01"), pd.Timestamp("2018-08-01"))

COR = "#2a78d6"
COR_REFERENCIA = "#8a8984"  # cinza neutro, legível em tema claro e escuro

_MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
          "jul", "ago", "set", "out", "nov", "dez"]


class DadosFaltando(Exception):
    """O banco ou algum mart não existe. faltando lista o que falta."""

    def __init__(self, faltando: list[str]):
        self.faltando = faltando
        super().__init__(", ".join(faltando))


# ---------------------------------------------------------------- leitura

def ler(marts: list[str]) -> dict[str, pd.DataFrame]:
    # Checado antes do connect: com read_only o DuckDB não cria o arquivo,
    # mas o erro dele não diz qual arquivo faltou.
    if not BANCO.is_file():
        raise DadosFaltando([BANCO.name])

    dados: dict[str, pd.DataFrame] = {}
    faltando: list[str] = []
    con = duckdb.connect(str(BANCO), read_only=True)
    try:
        for nome in marts:
            try:
                dados[nome] = con.execute(f'SELECT * FROM marts."{nome}"').df()
            except duckdb.CatalogException:
                # Segue lendo os outros para a mensagem listar todos de uma vez.
                faltando.append(f"marts.{nome}")
    finally:
        con.close()

    if faltando:
        raise DadosFaltando(faltando)
    return dados


# ---------------------------------------------------------------- formato

def _br(valor, casas: int) -> str:
    # Formata no padrão americano e troca os separadores; o "_" é só ponte.
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def reais(valor, casas: int = 2) -> str:
    return f"R$ {_br(valor, casas)}"


def pct(valor, casas: int = 1) -> str:
    return f"{_br(valor, casas)}%"


def numero(valor, casas: int = 0) -> str:
    return _br(valor, casas)


def mes_ano(data) -> str:
    """2017-01-01 -> "jan/2017"."""
    return f"{_MESES[data.month - 1]}/{data.year}"


def pct_recompra(recompra: pd.DataFrame) -> float:
    """A única conta permitida (item 2): o mart 05 guarda o complemento."""
    linha = recompra[recompra["pedidos_por_cliente"] == 1]
    return 100 - linha["pct_clientes"].iloc[0]


def cartoes(dados: dict[str, pd.DataFrame]) -> list[tuple[str, str]]:
    """Os sete cartões do item 3, em ordem: (rótulo, valor formatado).

    Aqui e não em app.py para o relatório mostrar exatamente os mesmos.
    """
    kpis = dados["kpis"].iloc[0]
    return [
        ("Ticket médio · R$ por pedido válido", reais(kpis["ticket_medio"])),
        ("Cancelados · % de todos os pedidos", pct(kpis["pct_cancelados"], 2)),
        ("Peso do frete · % do frete no valor pago", pct(kpis["pct_frete"], 1)),
        ("Recompra · % de clientes com 2+ pedidos",
         pct(pct_recompra(dados["recompra"]), 2)),
        ("No prazo · % entregue até a data prevista",
         pct(dados["entrega_no_prazo"]["pct_no_prazo"].iloc[0], 1)),
        ("Dias até entregar · média da compra à entrega",
         numero(kpis["dias_entrega"], 1)),
        ("Nota média · avaliações de 1 a 5", numero(kpis["nota_media"], 2)),
    ]


def recortar_periodo(vendas_mensais: pd.DataFrame, inicio, fim) -> pd.DataFrame:
    """Só filtra linhas (item 5): os meses de inicio a fim, inclusive."""
    mes = vendas_mensais["mes"]
    return vendas_mensais[(mes >= inicio) & (mes <= fim)]


# ---------------------------------------------------------------- gráficos

def _estilo(fig: go.Figure, titulo: str, altura: int = 380) -> go.Figure:
    fig.update_layout(
        title=titulo,
        height=altura,
        # Separadores do plotly no padrão brasileiro: decimal "," e milhar ".".
        separators=",.",
        margin=dict(l=10, r=10, t=50, b=10),
        showlegend=False,
    )
    return fig


def _barras_horizontais(df, x, y, titulo, eixo_x, eixo_y, formato_x, altura):
    # Espera df já ordenado do maior para o menor; o eixo invertido põe a
    # primeira linha em cima.
    fig = px.bar(df, x=x, y=y, orientation="h",
                 labels={x: eixo_x, y: eixo_y})
    fig.update_traces(marker_color=COR, hovertemplate=f"%{{y}}: %{{x:{formato_x}}}<extra></extra>")
    fig.update_yaxes(autorange="reversed", type="category")
    fig.update_xaxes(tickformat=formato_x)
    return _estilo(fig, titulo, altura)


def faturamento_mensal(vendas_mensais: pd.DataFrame) -> go.Figure:
    df = vendas_mensais.sort_values("mes")
    fig = px.line(df, x="mes", y="receita", markers=True,
                  labels={"mes": "Mês", "receita": "Receita (R$)"})
    fig.update_traces(
        line_color=COR, line_width=2, marker_size=8,
        hovertemplate="%{x|%m/%Y}: R$ %{y:,.2f}<extra></extra>",
    )
    # Rótulos dos meses montados aqui: o plotly escreveria "Jan 2017".
    fig.update_xaxes(tickvals=df["mes"], ticktext=[mes_ano(m) for m in df["mes"]])
    fig.update_yaxes(tickformat=",.0f", rangemode="tozero")
    return _estilo(fig, "01 · Faturamento mensal")


def receita_por_categoria(top_categorias: pd.DataFrame) -> go.Figure:
    df = top_categorias.sort_values("receita", ascending=False).head(10)
    return _barras_horizontais(
        df, "receita", "categoria", "02 · Receita por categoria (top 10)",
        "Receita (R$)", "Categoria", ",.0f", 420,
    )


def mix_pagamento(mix: pd.DataFrame) -> go.Figure:
    df = mix.sort_values("pct_valor", ascending=False)
    fig = px.bar(df, x="tipo", y="pct_valor",
                 labels={"tipo": "Tipo de pagamento", "pct_valor": "% do valor pago"})
    fig.update_traces(marker_color=COR, hovertemplate="%{x}: %{y:.1f}%<extra></extra>")
    fig.update_yaxes(ticksuffix="%")
    return _estilo(fig, "07 · Mix de pagamento", 420)


def ticket_por_uf(ticket: pd.DataFrame) -> go.Figure:
    df = ticket.sort_values("ticket_medio", ascending=False)
    return _barras_horizontais(
        df, "ticket_medio", "uf", "06 · Ticket médio por UF",
        "Ticket médio (R$)", "UF", ",.2f", 620,
    )


def clientes_por_uf(clientes: pd.DataFrame) -> go.Figure:
    df = clientes.sort_values("clientes", ascending=False)
    return _barras_horizontais(
        df, "clientes", "uf", "12 · Clientes por UF",
        "Clientes (pessoas)", "UF", ",.0f", 620,
    )


def nota_por_categoria(notas: pd.DataFrame) -> go.Figure:
    df = notas.sort_values("posicao_pior").head(10)
    fig = px.scatter(df, x="nota_media", y="categoria",
                     labels={"nota_media": "Nota média (1 a 5)", "categoria": "Categoria"})
    fig.update_traces(marker_color=COR, marker_size=10,
                      hovertemplate="%{y}: %{x:.2f}<extra></extra>")
    fig.update_yaxes(autorange="reversed", type="category")
    fig.update_xaxes(tickformat=".2f")
    return _estilo(fig, "04 · Nota por categoria (10 piores)", 620)


def concentracao_vendedores(pareto: pd.DataFrame) -> go.Figure:
    df = pareto.sort_values("posicao")
    fig = px.line(df, x="posicao", y="pct_acumulado",
                  labels={"posicao": "Vendedores (posição por receita)",
                          "pct_acumulado": "% acumulado da receita"})
    fig.update_traces(line_color=COR, line_width=2,
                      hovertemplate="%{x:,}º vendedor: %{y:.2f}%<extra></extra>")
    fig.add_hline(y=80, line_dash="dash", line_color=COR_REFERENCIA, line_width=1,
                  annotation_text="80%", annotation_position="bottom right")
    fig.update_xaxes(tickformat=",")
    fig.update_yaxes(ticksuffix="%", range=[0, 100])
    return _estilo(fig, "09 · Concentração de vendedores", 620)

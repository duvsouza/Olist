"""Página do painel da operação Olist. A spec está em painel.py.

Execução:
    uv run streamlit run app.py
"""

import pandas as pd
import streamlit as st

import painel

st.set_page_config(page_title="Olist · visão da operação", layout="wide")


@st.cache_data
def carregar() -> dict[str, pd.DataFrame]:
    # ler() abre e fecha a conexão; o cache guarda só os DataFrames, então
    # nenhum lock fica preso no olist.duckdb enquanto a página está de pé.
    # Exceção não entra no cache: depois de rodar o pipeline, o próximo
    # carregamento tenta de novo sozinho.
    return painel.ler(painel.MARTS)


try:
    dados = carregar()
except painel.DadosFaltando as e:
    st.error(
        "Faltando: " + ", ".join(e.faltando) + "\n\n"
        f"Rode antes: `{painel.COMANDO_MARTS}`"
    )
    if st.button("Recarregar dados"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

vendas = dados["vendas_mensais"].sort_values("mes")
meses = list(vendas["mes"])

# ---------------------------------------------------------------- cabeçalho
esquerda, direita = st.columns([3, 2], vertical_alignment="bottom")
esquerda.title("Olist · visão da operação")
with direita:
    inicio, fim = st.select_slider(
        "Período do faturamento",
        options=meses,
        value=painel.PERIODO_PADRAO,
        format_func=painel.mes_ano,
    )
    st.caption("os cartões valem para o período inteiro")
    if st.button("Recarregar dados"):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------------- faixa 1
for coluna, (rotulo, valor) in zip(st.columns(7), painel.cartoes(dados)):
    coluna.metric(rotulo, valor)

# ---------------------------------------------------------------- faixa 2
recorte = painel.recortar_periodo(vendas, inicio, fim)
st.plotly_chart(painel.faturamento_mensal(recorte), width="stretch")

# ---------------------------------------------------------------- faixa 3
c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.receita_por_categoria(dados["top_categorias"]), width="stretch")
c2.plotly_chart(painel.mix_pagamento(dados["mix_pagamento"]), width="stretch")
c3.plotly_chart(painel.ticket_por_uf(dados["ticket_medio_por_estado"]), width="stretch")

# ---------------------------------------------------------------- faixa 4
c1, c2, c3 = st.columns(3)
c1.plotly_chart(painel.clientes_por_uf(dados["clientes_por_uf"]), width="stretch")
c2.plotly_chart(painel.nota_por_categoria(dados["nota_por_categoria"]), width="stretch")
c3.plotly_chart(painel.concentracao_vendedores(dados["vendedores_pareto"]), width="stretch")

import duckdb
import pandas as pd
import pytest

import painel

# Marts inventados, com as colunas que painel.py lê. Cada valor foi escolhido
# para a conta do teste sair exata.
MARTS_INVENTADOS = {
    "kpis": "SELECT 150.25 AS ticket_medio, 1.5 AS pct_cancelados, "
            "12.3 AS pct_frete, 11.5 AS dias_entrega, 4.25 AS nota_media",
    # 90% compraram uma vez só: a recompra é o complemento, 10%.
    "recompra": "SELECT * FROM (VALUES (1, 90, 90.0), (2, 10, 10.0)) "
                "t(pedidos_por_cliente, clientes, pct_clientes)",
    "entrega_no_prazo": "SELECT 80.5 AS pct_no_prazo",
    # Um mês antes e um depois do período padrão: o recorte tira os dois.
    "vendas_mensais": "SELECT * FROM (VALUES "
                      "(DATE '2016-12-01', 1, 10.00), (DATE '2017-01-01', 2, 200.00), "
                      "(DATE '2018-08-01', 3, 300.00), (DATE '2018-09-01', 1, 5.00)) "
                      "t(mes, pedidos, receita)",
    "top_categorias": "SELECT * FROM (VALUES ('cama', 50.00), ('beleza', 90.00)) "
                      "t(categoria, receita)",
    "mix_pagamento": "SELECT * FROM (VALUES ('boleto', 25.0), ('cartao', 75.0)) "
                     "t(tipo, pct_valor)",
    "ticket_medio_por_estado": "SELECT * FROM (VALUES ('SP', 100.0), ('PB', 200.0), "
                               "('RJ', 150.0)) t(uf, ticket_medio)",
    "clientes_por_uf": "SELECT * FROM (VALUES ('SP', 30), ('AC', 1)) t(uf, clientes)",
    "nota_por_categoria": "SELECT * FROM (VALUES ('moveis', 3.5, 1), ('livros', 4.5, 2)) "
                          "t(categoria, nota_media, posicao_pior)",
    "vendedores_pareto": "SELECT * FROM (VALUES (1, 60.0), (2, 85.0), (3, 100.0)) "
                         "t(posicao, pct_acumulado)",
}


def criar_marts(caminho, sem=()):
    """DuckDB novo com os marts inventados; usado também por test_relatorio."""
    con = duckdb.connect(str(caminho))
    con.execute("CREATE SCHEMA marts")
    for nome, sql in MARTS_INVENTADOS.items():
        if nome not in sem:
            con.execute(f"CREATE TABLE marts.{nome} AS {sql}")
    con.close()


# ---------------------------------------------------------------- formato

def test_reais_usa_ponto_no_milhar_e_virgula_no_decimal():
    assert painel.reais(1234567.891) == "R$ 1.234.567,89"


def test_reais_aceita_outra_quantidade_de_casas():
    assert painel.reais(1500, casas=0) == "R$ 1.500"


def test_pct_tem_uma_casa_por_padrao():
    assert painel.pct(12.34) == "12,3%"


def test_pct_com_duas_casas():
    assert painel.pct(0.5, 2) == "0,50%"


def test_numero_sem_casas_por_padrao():
    assert painel.numero(1234567) == "1.234.567"


def test_numero_com_uma_casa():
    assert painel.numero(1000.25, 1) == "1.000,2"


def test_mes_ano_escreve_o_mes_em_portugues():
    assert painel.mes_ano(pd.Timestamp("2018-02-01")) == "fev/2018"


def test_recompra_e_o_complemento_de_quem_comprou_uma_vez():
    recompra = pd.DataFrame({"pedidos_por_cliente": [1, 2], "pct_clientes": [90.0, 10.0]})
    assert painel.pct_recompra(recompra) == 10.0


def test_recortar_periodo_inclui_as_duas_pontas():
    vendas = pd.DataFrame({"mes": pd.to_datetime(
        ["2016-12-01", "2017-01-01", "2018-08-01", "2018-09-01"])})
    recorte = painel.recortar_periodo(vendas, *painel.PERIODO_PADRAO)
    assert list(recorte["mes"]) == list(pd.to_datetime(["2017-01-01", "2018-08-01"]))


# ---------------------------------------------------------------- leitura

def test_ler_devolve_um_dataframe_por_mart(tmp_path, monkeypatch):
    banco = tmp_path / "t.duckdb"
    criar_marts(banco)
    monkeypatch.setattr(painel, "BANCO", banco)
    dados = painel.ler(["kpis", "clientes_por_uf"])
    assert list(dados) == ["kpis", "clientes_por_uf"]
    assert list(dados["clientes_por_uf"]["uf"]) == ["SP", "AC"]


def test_ler_fecha_a_conexao_e_libera_o_arquivo(tmp_path, monkeypatch):
    banco = tmp_path / "t.duckdb"
    criar_marts(banco)
    monkeypatch.setattr(painel, "BANCO", banco)
    painel.ler(painel.MARTS)
    # Conexão de escrita no mesmo arquivo: falharia com a read_only aberta.
    con = duckdb.connect(str(banco))
    con.execute("CREATE TABLE marts.nova AS SELECT 1 AS x")
    con.close()
    assert banco.is_file()


def test_ler_sem_banco_diz_qual_arquivo_falta(tmp_path, monkeypatch):
    monkeypatch.setattr(painel, "BANCO", tmp_path / "nao_existe.duckdb")
    with pytest.raises(painel.DadosFaltando) as erro:
        painel.ler(painel.MARTS)
    assert erro.value.faltando == ["nao_existe.duckdb"]
    assert not (tmp_path / "nao_existe.duckdb").exists()  # não cria banco vazio


def test_ler_lista_todos_os_marts_que_faltam(tmp_path, monkeypatch):
    banco = tmp_path / "t.duckdb"
    criar_marts(banco, sem=("kpis", "recompra"))
    monkeypatch.setattr(painel, "BANCO", banco)
    with pytest.raises(painel.DadosFaltando) as erro:
        painel.ler(painel.MARTS)
    assert erro.value.faltando == ["marts.kpis", "marts.recompra"]


def test_cartoes_formatam_os_sete_valores_na_ordem(tmp_path, monkeypatch):
    banco = tmp_path / "t.duckdb"
    criar_marts(banco)
    monkeypatch.setattr(painel, "BANCO", banco)
    valores = [v for _, v in painel.cartoes(painel.ler(painel.MARTS))]
    assert valores == ["R$ 150,25", "1,50%", "12,3%", "10,00%", "80,5%", "11,5", "4,25"]


# ---------------------------------------------------------------- gráficos

def _pontos(fig):
    return len(fig.data[0].x)


def test_faturamento_tem_um_ponto_por_mes():
    df = pd.DataFrame({"mes": pd.to_datetime(["2017-01-01", "2017-02-01", "2017-03-01"]),
                       "receita": [10.0, 20.0, 30.0]})
    fig = painel.faturamento_mensal(df)
    assert _pontos(fig) == 3
    assert list(fig.layout.xaxis.ticktext) == ["jan/2017", "fev/2017", "mar/2017"]


def test_receita_por_categoria_tem_uma_barra_por_linha_maior_em_cima():
    df = pd.DataFrame({"categoria": ["a", "b", "c"], "receita": [5.0, 30.0, 10.0]})
    fig = painel.receita_por_categoria(df)
    assert list(fig.data[0].y) == ["b", "c", "a"]  # eixo invertido: b em cima
    assert fig.layout.yaxis.autorange == "reversed"


def test_receita_por_categoria_corta_no_top_10():
    # Doze categorias: as duas de menor receita ficam fora.
    df = pd.DataFrame({"categoria": [f"c{i:02d}" for i in range(12)],
                       "receita": [float(i) for i in range(12)]})
    fig = painel.receita_por_categoria(df)
    assert _pontos(fig) == 10
    assert "c00" not in list(fig.data[0].y) and "c01" not in list(fig.data[0].y)


def test_mix_pagamento_tem_uma_barra_por_tipo():
    df = pd.DataFrame({"tipo": ["boleto", "cartao", "voucher"], "pct_valor": [20.0, 75.0, 5.0]})
    fig = painel.mix_pagamento(df)
    assert list(fig.data[0].x) == ["cartao", "boleto", "voucher"]


def test_ticket_por_uf_tem_uma_barra_por_uf_maior_em_cima():
    df = pd.DataFrame({"uf": ["SP", "PB", "RJ"], "ticket_medio": [100.0, 200.0, 150.0]})
    fig = painel.ticket_por_uf(df)
    assert list(fig.data[0].y) == ["PB", "RJ", "SP"]


def test_clientes_por_uf_tem_uma_barra_por_uf():
    df = pd.DataFrame({"uf": ["AC", "SP"], "clientes": [1, 30]})
    fig = painel.clientes_por_uf(df)
    assert list(fig.data[0].y) == ["SP", "AC"]


def test_nota_por_categoria_tem_um_ponto_por_categoria_pior_em_cima():
    df = pd.DataFrame({"categoria": ["livros", "moveis"], "nota_media": [4.5, 3.5],
                       "posicao_pior": [2, 1]})
    fig = painel.nota_por_categoria(df)
    assert list(fig.data[0].y) == ["moveis", "livros"]


def test_concentracao_tem_um_ponto_por_vendedor_e_linha_em_80():
    df = pd.DataFrame({"posicao": [1, 2, 3], "pct_acumulado": [60.0, 85.0, 100.0]})
    fig = painel.concentracao_vendedores(df)
    assert _pontos(fig) == 3
    assert [(s.y0, s.line.dash) for s in fig.layout.shapes] == [(80, "dash")]

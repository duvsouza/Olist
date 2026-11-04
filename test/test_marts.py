import io
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from pipeline import db, marts
from pipeline.transformacao import TABELAS as TABELAS_REFINED

# Os .sql de verdade do projeto: lê o texto, nunca o banco.
SQL_PROJETO = Path(__file__).resolve().parent.parent / "sql" / "marts"


def _preparar(tmp_path, monkeypatch, sem_refined=()):
    """Banco novo com as oito tabelas de refined (vazias) e pasta de SQL."""
    banco = tmp_path / "t.duckdb"
    con = duckdb.connect(str(banco))
    con.execute("CREATE SCHEMA refined")
    for tabela in TABELAS_REFINED:
        if tabela not in sem_refined:
            con.execute(f"CREATE TABLE refined.{tabela} (x INTEGER)")
    con.close()
    pasta = tmp_path / "sql" / "marts"
    pasta.mkdir(parents=True)
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", banco)
    monkeypatch.setattr(marts, "_RAIZ", tmp_path)
    monkeypatch.setattr(marts, "PASTA_SQL", pasta)
    return banco, pasta


def _capturar(monkeypatch, nome="stdout"):
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")
    monkeypatch.setattr(sys, nome, saida)
    return saida


def _texto(saida):
    saida.flush()
    return saida.buffer.getvalue().decode("utf-8")


def _marts_existentes(banco):
    con = duckdb.connect(str(banco))
    try:
        return [t for (t,) in con.execute(
            "SELECT table_name FROM duckdb_tables() "
            "WHERE schema_name = 'marts' ORDER BY 1"
        ).fetchall()]
    finally:
        con.close()


def test_arquivo_com_select_1_cria_mart_com_uma_linha(tmp_path, monkeypatch):
    banco, pasta = _preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x;\n", encoding="utf-8")
    saida = _capturar(monkeypatch)
    marts.main()
    con = duckdb.connect(str(banco))
    linhas = con.execute("SELECT * FROM marts.teste").fetchall()
    con.close()
    assert linhas == [(1,)]
    assert _texto(saida).splitlines()[-1] == "1 mart, 1 linha"


def test_arquivo_apagado_faz_o_mart_sumir(tmp_path, monkeypatch):
    banco, pasta = _preparar(tmp_path, monkeypatch)
    (pasta / "00_teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    (pasta / "01_fica.sql").write_text("SELECT 2 AS y", encoding="utf-8")
    _capturar(monkeypatch)
    marts.main()
    (pasta / "00_teste.sql").unlink()
    marts.main()
    assert _marts_existentes(banco) == ["fica"]


def test_arquivo_sem_prefixo_para_antes_de_executar_qualquer_sql(tmp_path, monkeypatch):
    banco, pasta = _preparar(tmp_path, monkeypatch)
    # 01_valido.sql rodaria sem erro; não pode ser executado.
    (pasta / "01_valido.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    (pasta / "teste.sql").write_text("SELECT 1 AS x", encoding="utf-8")  # sem NN_
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        marts.main()
    assert _marts_existentes(banco) == []
    assert "sql/marts/teste.sql" in _texto(erro)


def test_dois_arquivos_com_o_mesmo_nome_de_tabela_param(tmp_path, monkeypatch):
    banco, pasta = _preparar(tmp_path, monkeypatch)
    # Maiúscula e minúscula dão a mesma tabela no DuckDB.
    (pasta / "01_Vendas.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    (pasta / "02_vendas.sql").write_text("SELECT 2 AS x", encoding="utf-8")
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        marts.main()
    assert _marts_existentes(banco) == []
    assert "mesma tabela marts.vendas" in _texto(erro)


def test_mart_vazio_encerra_e_deixa_marts_como_estava(tmp_path, monkeypatch):
    banco, pasta = _preparar(tmp_path, monkeypatch)
    (pasta / "01_antigo.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    _capturar(monkeypatch)
    marts.main()
    # Segunda execução: um mart novo que volta sem linhas.
    (pasta / "02_vazio.sql").write_text("SELECT 1 AS x WHERE false", encoding="utf-8")
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        marts.main()
    assert _marts_existentes(banco) == ["antigo"]
    assert "Mart vazio: marts.vazio" in _texto(erro)


def test_sql_com_erro_para_tudo_e_deixa_marts_como_estava(tmp_path, monkeypatch):
    banco, pasta = _preparar(tmp_path, monkeypatch)
    (pasta / "01_antigo.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    _capturar(monkeypatch)
    marts.main()
    (pasta / "02_quebrado.sql").write_text("SELEC 1", encoding="utf-8")  # sintaxe errada
    (pasta / "03_depois.sql").write_text("SELECT 3 AS z", encoding="utf-8")
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        marts.main()
    assert _marts_existentes(banco) == ["antigo"]
    assert "Falhou: sql/marts/02_quebrado.sql" in _texto(erro)


def test_pasta_sem_sql_encerra(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        marts.main()
    assert "Nenhum arquivo .sql" in _texto(erro)


def test_refined_incompleto_encerra(tmp_path, monkeypatch):
    _, pasta = _preparar(tmp_path, monkeypatch, sem_refined=("pagamentos",))
    (pasta / "01_a.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        marts.main()
    assert "refined.pagamentos" in _texto(erro)


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch):
    _, pasta = _preparar(tmp_path, monkeypatch)
    (pasta / "01_a.sql").write_text("SELECT * FROM range(1500)", encoding="utf-8")
    (pasta / "02_b.sql").write_text("SELECT 1 AS x", encoding="utf-8")
    primeira = _capturar(monkeypatch)
    marts.main()
    segunda = _capturar(monkeypatch)
    marts.main()
    assert _texto(primeira) == _texto(segunda)
    assert _texto(primeira).splitlines() == [
        "✓ marts.a  1.500 linhas",
        "✓ marts.b      1 linha",
        "2 marts, 1.501 linhas",
    ]


# ------------------------------------------------ sql/marts/01 e 03 de verdade

def _refined_pedidos(tmp_path, pedidos, itens=()):
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    con.execute("CREATE SCHEMA refined")
    con.execute(
        "CREATE TABLE refined.pedidos (pedido_id VARCHAR, status VARCHAR, "
        "data_compra TIMESTAMP, data_entrega TIMESTAMP, data_entrega_prevista DATE)"
    )
    con.execute("CREATE TABLE refined.itens_pedido (pedido_id VARCHAR, preco DECIMAL(10,2))")
    con.executemany("INSERT INTO refined.pedidos VALUES (?, ?, ?, ?, ?)", pedidos)
    if itens:
        con.executemany("INSERT INTO refined.itens_pedido VALUES (?, ?)", itens)
    return con


def _rodar_sql(con, arquivo):
    return con.execute((SQL_PROJETO / arquivo).read_text(encoding="utf-8")).fetchall()


def test_pedido_com_dois_itens_conta_uma_vez(tmp_path):
    con = _refined_pedidos(
        tmp_path,
        [("p1", "delivered", "2017-01-10 09:00:00", None, None)],
        [("p1", Decimal("10.00")),   # primeiro item do pedido p1
         ("p1", Decimal("20.50"))],  # segundo item do mesmo pedido
    )
    linhas = _rodar_sql(con, "01_vendas_mensais.sql")
    con.close()
    assert linhas == [(date(2017, 1, 1), 1, Decimal("30.50"))]


def test_cancelado_fica_fora_da_receita(tmp_path):
    con = _refined_pedidos(
        tmp_path,
        [("p1", "delivered", "2017-01-10 09:00:00", None, None),    # entra
         ("p2", "canceled", "2017-01-12 09:00:00", None, None),     # sai
         ("p3", "unavailable", "2017-01-13 09:00:00", None, None),  # sai
         ("p4", "shipped", "2017-02-01 00:00:00", None, None)],     # entra, outro mês
        [("p1", Decimal("10.00")), ("p2", Decimal("100.00")),
         ("p3", Decimal("200.00")), ("p4", Decimal("5.25"))],
    )
    linhas = _rodar_sql(con, "01_vendas_mensais.sql")
    con.close()
    assert linhas == [
        (date(2017, 1, 1), 1, Decimal("10.00")),
        (date(2017, 2, 1), 1, Decimal("5.25")),
    ]


def test_entrega_no_dia_previsto_a_tarde_esta_no_prazo(tmp_path):
    con = _refined_pedidos(tmp_path, [
        # entregue às 15h do dia previsto: no prazo
        ("a", "delivered", "2018-03-01 10:00:00", "2018-03-10 15:00:00", "2018-03-10"),
        # entregue no dia seguinte ao previsto: atrasado
        ("b", "delivered", "2018-03-01 10:00:00", "2018-03-11 09:00:00", "2018-03-10"),
        # entregue antes do previsto: no prazo
        ("c", "delivered", "2018-03-01 10:00:00", "2018-03-05 12:00:00", "2018-03-10"),
        # delivered sem data de entrega: fora do denominador
        ("d", "delivered", "2018-03-01 10:00:00", None, "2018-03-10"),
        # não é delivered, mesmo com data: fora do denominador
        ("e", "canceled", "2018-03-01 10:00:00", "2018-03-20 10:00:00", "2018-03-10"),
    ])
    linhas = _rodar_sql(con, "03_entrega_no_prazo.sql")
    con.close()
    entregues, no_prazo, atrasados, pct_no_prazo = linhas[0]
    assert (entregues, no_prazo, atrasados) == (3, 2, 1)
    assert pct_no_prazo == 66.7  # round(100 * 2 / 3, 1); não é dinheiro

import gzip
import io
import sys

import duckdb
import pytest

from pipeline import db, ingestao

# Cabeçalho mínimo de cada arquivo; só pedidos e clientes recebem linhas.
CABECALHOS = {
    "olist_orders_dataset.csv.gz": "order_id,customer_id,order_status,order_purchase_timestamp",
    "olist_order_items_dataset.csv.gz": "order_id,order_item_id,price",
    "olist_order_payments_dataset.csv.gz": "order_id,payment_value",
    "olist_order_reviews_dataset.csv.gz": "review_id,order_id",
    "olist_customers_dataset.csv.gz": "customer_id,customer_zip_code_prefix,customer_city",
    "olist_sellers_dataset.csv.gz": "seller_id",
    "olist_products_dataset.csv.gz": "product_id",
    "product_category_name_translation.csv.gz": "product_category_name",
    "olist_geolocation_dataset.csv.gz": "geolocation_zip_code_prefix",
}

PEDIDOS = [
    "p1,c1,delivered,2017-10-02 10:56:33",  # pedido comum
    "p2,c2,canceled,",                      # data vazia: tem que virar NULL
    "p2,c2,canceled,",                      # linha duplicada: raw não deduplica
]

CLIENTES = [
    "c1,01151,sao paulo",  # CEP com zero à esquerda: não pode perder o zero
    "c2,22790,NA",         # cidade literalmente "NA": continua texto, não nulo
]


def _escrever_raw(pasta, sem=None):
    pasta.mkdir(exist_ok=True)
    corpo = {
        "olist_orders_dataset.csv.gz": PEDIDOS,
        "olist_customers_dataset.csv.gz": CLIENTES,
    }
    for nome, cabecalho in CABECALHOS.items():
        if nome == sem:
            continue
        texto = "\n".join([cabecalho, *corpo.get(nome, [])]) + "\n"
        with gzip.open(pasta / nome, "wt", encoding="utf-8", newline="") as f:
            f.write(texto)


def _preparar(tmp_path, monkeypatch, sem=None):
    _escrever_raw(tmp_path / "raw", sem=sem)
    banco = tmp_path / "t.duckdb"
    monkeypatch.setattr(ingestao, "PASTA_RAW", tmp_path / "raw")
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", banco)
    return banco


def _capturar(monkeypatch, nome="stdout"):
    # TextIOWrapper, não StringIO: main() chama reconfigure(encoding=...).
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")
    monkeypatch.setattr(sys, nome, saida)
    return saida


def _texto(saida):
    saida.flush()
    return saida.buffer.getvalue().decode("utf-8")


def test_csv_vira_tabela_com_as_mesmas_linhas(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch)
    ingestao.main()
    con = duckdb.connect(str(banco))
    pedidos = con.execute("SELECT count(*) FROM raw.pedidos").fetchall()[0][0]
    clientes = con.execute("SELECT count(*) FROM raw.clientes").fetchall()[0][0]
    tabelas = con.execute(
        "SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'raw'"
    ).fetchall()[0][0]
    con.close()
    # 3 linhas de pedidos, inclusive a duplicada; nove arquivos, nove tabelas.
    assert (pedidos, clientes, tabelas) == (3, 2, 9)


def test_todas_as_colunas_entram_como_varchar(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch)
    ingestao.main()
    con = duckdb.connect(str(banco))
    tipos = {
        t for (t,) in con.execute(
            "SELECT DISTINCT data_type FROM duckdb_columns() WHERE schema_name = 'raw'"
        ).fetchall()
    }
    con.close()
    assert tipos == {"VARCHAR"}


def test_cep_mantem_o_zero_a_esquerda(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch)
    ingestao.main()
    con = duckdb.connect(str(banco))
    cep = con.execute(
        "SELECT customer_zip_code_prefix FROM raw.clientes WHERE customer_id = 'c1'"
    ).fetchall()[0][0]
    con.close()
    assert cep == "01151"


def test_campo_vazio_vira_nulo_e_texto_na_continua_texto(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch)
    ingestao.main()
    con = duckdb.connect(str(banco))
    datas_nulas = con.execute(
        "SELECT count(*) FROM raw.pedidos WHERE order_purchase_timestamp IS NULL"
    ).fetchall()[0][0]
    cidade = con.execute(
        "SELECT customer_city FROM raw.clientes WHERE customer_id = 'c2'"
    ).fetchall()[0][0]
    con.close()
    assert (datas_nulas, cidade) == (2, "NA")


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch)
    primeira = _capturar(monkeypatch)
    ingestao.main()
    segunda = _capturar(monkeypatch)
    ingestao.main()
    assert _texto(primeira) == _texto(segunda)
    assert _texto(primeira).splitlines()[-1].split() == ["Total", "5"]


def test_arquivo_faltando_encerra_sem_criar_banco(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, sem="olist_sellers_dataset.csv.gz")
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit) as saida:
        ingestao.main()
    assert saida.value.code == 1
    assert not banco.exists()  # parou antes de abrir o banco
    assert "olist_sellers_dataset.csv.gz" in _texto(erro)

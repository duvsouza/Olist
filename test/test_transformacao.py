import io
import sys
from decimal import Decimal

import duckdb
import pytest

from pipeline import db, transformacao

# Pedido válido, nas colunas de raw.olist_orders (8 colunas, tudo texto).
P1 = ("p1", "c1", "delivered", "2017-10-02 10:56:33", "2017-10-02 11:07:15",
      "2017-10-04 19:55:00", "2017-10-10 21:25:13", "2017-10-18 00:00:00")


def _criar_raw(caminho, linhas, sem=()):
    """raw com as oito tabelas de entrada, só com as linhas pedidas."""
    con = duckdb.connect(str(caminho))
    con.execute("CREATE SCHEMA raw")
    for tabela, colunas in transformacao.TABELAS.items():
        if tabela in sem:
            continue
        nomes = [o for o, _, _ in colunas]
        definicao = ", ".join(f'"{n}" VARCHAR' for n in nomes)
        con.execute(f"CREATE TABLE raw.{tabela} ({definicao})")
        if linhas.get(tabela):
            marcas = ", ".join("?" * len(nomes))
            con.executemany(f"INSERT INTO raw.{tabela} VALUES ({marcas})",
                            [list(l) for l in linhas[tabela]])
    con.close()


def _preparar(tmp_path, monkeypatch, linhas, sem=()):
    banco = tmp_path / "t.duckdb"
    _criar_raw(banco, linhas, sem)
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", banco)
    return banco


def _capturar(monkeypatch, nome="stdout"):
    saida = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", newline="\n")
    monkeypatch.setattr(sys, nome, saida)
    return saida


def _texto(saida):
    saida.flush()
    return saida.buffer.getvalue().decode("utf-8")


def _consulta(banco, sql):
    con = duckdb.connect(str(banco))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def _existe_refined(banco):
    return _consulta(
        banco, "SELECT count(*) FROM duckdb_schemas() WHERE schema_name = 'refined'"
    )[0][0] == 1


def test_duplicata_exata_sai_e_e_contada(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, {
        "pedidos": [
            P1,
            P1,  # linha inteira repetida: fica uma
        ],
    })
    saida = _capturar(monkeypatch)
    transformacao.main()
    assert _consulta(banco, "SELECT count(*) FROM refined.pedidos")[0][0] == 1
    assert "2 ->       1 linhas  (1 duplicatas)" in _texto(saida)


def test_datas_viram_timestamp_e_data_prevista_vira_date(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, {"pedidos": [P1]})
    _capturar(monkeypatch)
    transformacao.main()
    tipos = dict(_consulta(banco, "SELECT column_name, column_type FROM "
                                  "(DESCRIBE refined.pedidos)"))
    assert tipos["data_compra"] == "TIMESTAMP"
    assert tipos["data_entrega"] == "TIMESTAMP"
    assert tipos["data_entrega_prevista"] == "DATE"


def test_dinheiro_vira_decimal_e_soma_fecha_no_centavo(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, {
        "itens_pedido": [
            # 0.1 + 0.2: em DOUBLE daria 0.30000000000000004
            ("p1", "1", "pr1", "v1", "2017-10-06 11:07:15", "0.10", "1.00"),
            ("p1", "2", "pr2", "v1", "2017-10-06 11:07:15", "0.20", "2.50"),
        ],
    })
    _capturar(monkeypatch)
    transformacao.main()
    tipo = dict(_consulta(banco, "SELECT column_name, column_type FROM "
                                 "(DESCRIBE refined.itens_pedido)"))["preco"]
    soma = _consulta(banco, "SELECT sum(preco) FROM refined.itens_pedido")[0][0]
    assert tipo == "DECIMAL(10,2)"
    assert soma == Decimal("0.30")


def test_cep_continua_texto_com_zero_a_esquerda(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, {
        "clientes": [("c1", "u1", "01151", "sao paulo", "SP")],  # CEP com zero
    })
    _capturar(monkeypatch)
    transformacao.main()
    assert _consulta(banco, "SELECT cep_prefixo FROM refined.clientes")[0][0] == "01151"


def test_nulo_nao_e_apagado_nem_preenchido(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, {
        "pedidos": [
            P1,
            # cancelado sem aprovação, envio e entrega: nulos são informação
            ("p2", "c2", "canceled", "2017-10-03 08:00:00", None, None, None,
             "2017-10-20 00:00:00"),
        ],
    })
    saida = _capturar(monkeypatch)
    transformacao.main()
    nulos = _consulta(banco, "SELECT count(*) FROM refined.pedidos "
                             "WHERE data_entrega IS NULL")[0][0]
    assert nulos == 1
    assert "nulos mantidos: data_aprovacao 1, data_envio 1, data_entrega 1" in _texto(saida)


def test_valor_que_nao_converte_encerra_sem_virar_nulo(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, {
        "pedidos": [
            P1,
            # mês 13: strptime estoura em vez de devolver nulo
            ("p2", "c2", "delivered", "2017-13-02 10:00:00", None, None, None,
             "2017-10-20 00:00:00"),
        ],
    })
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit) as saida:
        transformacao.main()
    mensagem = _texto(erro)
    assert saida.value.code == 1
    assert "raw.pedidos.order_purchase_timestamp" in mensagem
    assert "2017-13-02 10:00:00" in mensagem
    assert not _existe_refined(banco)  # nada gravado: a transação foi desfeita


def test_dinheiro_que_nao_converte_encerra(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {
        "itens_pedido": [
            # vírgula decimal: CAST para DECIMAL estoura
            ("p1", "1", "pr1", "v1", "2017-10-06 11:07:15", "10,50", "1.00"),
        ],
    })
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        transformacao.main()
    assert "raw.itens_pedido.price" in _texto(erro)


def test_chave_repetida_com_conteudo_diferente_encerra(tmp_path, monkeypatch):
    banco = _preparar(tmp_path, monkeypatch, {
        "pedidos": [
            P1,
            # mesmo pedido_id com status diferente: o script não escolhe
            ("p1",) + P1[1:2] + ("canceled",) + P1[3:],
        ],
    })
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        transformacao.main()
    assert "Chave repetida com conteúdo diferente em refined.pedidos" in _texto(erro)
    assert not _existe_refined(banco)


def test_tabela_faltando_em_raw_encerra(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {}, sem=("avaliacoes",))
    erro = _capturar(monkeypatch, "stderr")
    with pytest.raises(SystemExit):
        transformacao.main()
    assert "raw.avaliacoes" in _texto(erro)


def test_rodar_duas_vezes_imprime_a_mesma_coisa(tmp_path, monkeypatch):
    _preparar(tmp_path, monkeypatch, {"pedidos": [P1]})
    primeira = _capturar(monkeypatch)
    transformacao.main()
    segunda = _capturar(monkeypatch)
    transformacao.main()
    assert _texto(primeira) == _texto(segunda)
    assert len(_texto(primeira).splitlines()) == 9  # oito tabelas e o total

import importlib
from pathlib import Path

import pandas as pd

from pipeline import db


def test_importar_db_nao_cria_arquivo_nenhum(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    importlib.reload(db)
    assert list(tmp_path.iterdir()) == []


def test_banco_fica_na_raiz_do_projeto_e_nao_no_cwd():
    # Só compara caminhos: nenhum teste abre o olist.duckdb de verdade.
    raiz = Path(db.__file__).resolve().parent.parent
    assert db._ARQUIVO_BANCO == raiz / "olist.duckdb"
    assert db.PASTA_RAW == raiz / "raw"


def test_conectar_de_outra_pasta_cria_o_banco_no_caminho_fixo(tmp_path, monkeypatch):
    banco = tmp_path / "projeto" / "olist.duckdb"
    banco.parent.mkdir()
    outra_pasta = tmp_path / "outra"
    outra_pasta.mkdir()
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", banco)
    monkeypatch.chdir(outra_pasta)

    db.conectar().close()

    assert banco.is_file()
    assert list(outra_pasta.iterdir()) == []


def test_criar_schema_pode_rodar_duas_vezes(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", tmp_path / "t.duckdb")
    con = db.conectar()
    db.criar_schema(con, "raw")
    db.criar_schema(con, "raw")
    schemas = con.execute(
        "SELECT schema_name FROM duckdb_schemas() WHERE schema_name = 'raw'"
    ).fetchall()
    con.close()
    assert schemas == [("raw",)]


def test_gravar_tres_linhas_devolve_tres_tambem_na_segunda_vez(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", tmp_path / "t.duckdb")
    con = db.conectar()
    db.criar_schema(con, "raw")
    df = pd.DataFrame({"a": ["1", "2", "3"]})

    primeira = db.gravar(con, df, "raw", "t")
    segunda = db.gravar(con, df, "raw", "t")  # recria, não acrescenta

    con.close()
    assert (primeira, segunda) == (3, 3)


def test_gravar_nao_deixa_view_temporaria(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", tmp_path / "t.duckdb")
    con = db.conectar()
    db.criar_schema(con, "raw")
    db.gravar(con, pd.DataFrame({"a": ["x"]}), "raw", "t")
    views = con.execute(
        "SELECT view_name FROM duckdb_views() WHERE NOT internal"
    ).fetchall()
    con.close()
    assert views == []


def test_gravar_mantem_nulo_como_null(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_ARQUIVO_BANCO", tmp_path / "t.duckdb")
    con = db.conectar()
    db.criar_schema(con, "raw")
    # Segunda linha com valor ausente: tem que chegar ao banco como NULL.
    db.gravar(con, pd.DataFrame({"a": ["x", None]}, dtype=str), "raw", "t")
    nulos = con.execute("SELECT count(*) FROM raw.t WHERE a IS NULL").fetchall()[0][0]
    con.close()
    assert nulos == 1

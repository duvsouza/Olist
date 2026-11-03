"""Módulo de conexão com o olist.duckdb, compartilhado pelas quatro etapas.

Expõe exatamente:
    PASTA_RAW                        Path da pasta raw/ com os nove .csv.gz
    conectar()                       abre o olist.duckdb, criando se faltar
    criar_schema(con, nome)          CREATE SCHEMA IF NOT EXISTS
    gravar(con, df, schema, tabela)  grava e devolve a contagem lida do banco

D1. CAMINHOS
    PASTA_RAW e o olist.duckdb são resolvidos a partir da localização deste
    arquivo (a pasta acima de pipeline/), nunca do diretório corrente.
    Por quê: rodar o script de outra pasta não pode criar um olist.duckdb
    vazio no lugar errado, que parece ingestão quebrada.

D2. TRÊS FUNÇÕES E UMA CONSTANTE, NADA MAIS
    Este módulo não lê CSV, não conhece nome de tabela, não imprime nada e
    não converte tipo. Quem decide tudo isso é cada etapa.
    Por quê: as aulas 2, 3 e 4 importam este arquivo. Regra de negócio
    escondida aqui valeria para todas as etapas sem aparecer em nenhuma spec.

D3. gravar
    Recria a tabela (CREATE OR REPLACE TABLE schema.tabela) com as colunas e
    os tipos do DataFrame, sem alterar nada: coluna str vira VARCHAR, nulo
    continua NULL. Não deixa view ou tabela temporária para trás. Devolve
    SELECT count(*) da tabela recém-gravada, lido do banco.
    Por quê: a contagem que aparece na tela tem que ser a do que foi
    gravado, não a do que estava na memória.

D4. CONEXÃO
    conectar() devolve a conexão aberta; quem chama é quem fecha. Este
    módulo não guarda conexão global.
    Por quê: o .duckdb aceita um único processo escrevendo; conexão escondida
    num módulo importado é lock que ninguém sabe que está segurando.

Critérios de aceite:
- Importar pipeline.db não abre banco nem cria arquivo nenhum.
- conectar() chamado de dentro de outra pasta cria o olist.duckdb na raiz
  do projeto, e não na pasta corrente.
- gravar() com um DataFrame de 3 linhas devolve 3, e rodar duas vezes
  continua devolvendo 3.
"""

from pathlib import Path

import duckdb
import pandas as pd

_RAIZ = Path(__file__).resolve().parent.parent
PASTA_RAW = _RAIZ / "raw"
_ARQUIVO_BANCO = _RAIZ / "olist.duckdb"


def conectar() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(_ARQUIVO_BANCO))


def criar_schema(con: duckdb.DuckDBPyConnection, nome: str) -> None:
    con.execute(f'CREATE SCHEMA IF NOT EXISTS "{nome}"')


def gravar(
    con: duckdb.DuckDBPyConnection, df: pd.DataFrame, schema: str, tabela: str
) -> int:
    destino = f'"{schema}"."{tabela}"'
    # register cria uma view sobre o DataFrame; o finally garante que ela some
    # mesmo se o CREATE falhar (D3: nada temporário fica para trás).
    view = "_gravar_df"
    con.register(view, df)
    try:
        con.execute(f"CREATE OR REPLACE TABLE {destino} AS SELECT * FROM {view}")
    finally:
        con.unregister(view)
    # fetchall, não fetchone: o DuckDB 2 recusa o próximo comando na conexão
    # enquanto houver resultado não consumido.
    return con.execute(f"SELECT count(*) FROM {destino}").fetchall()[0][0]

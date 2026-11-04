"""Etapa 2: transformação do schema raw no schema refined do olist.duckdb.

Execução:
    uv run python -m pipeline.transformacao

1. ESCOPO
   Lê de raw, escreve em refined. Nunca escreve em raw.
   Entram oito tabelas: pedidos, itens_pedido, pagamentos, clientes,
   vendedores, produtos, traducao_categorias, avaliacoes.
   Fica de fora geolocalizacao.
   Por quê: nenhum mart do curso usa geolocalizacao, e não se limpa o que
   ninguém vai ler. raw fica intocado porque é a fronteira entre "o dado
   que chegou" e "o dado que eu decidi"; se refined escrevesse em raw,
   não haveria mais com o que comparar.

2. NOMES
   Colunas renomeadas para português, snake_case, pelo mapa TABELAS abaixo,
   completo e literal. Nenhuma coluna fora do mapa; nenhuma descartada.
   Por quê: é o vocabulário que vou digitar de memória nos JOINs da aula 3.
   Coluna descartada aqui é pergunta que o mart não consegue mais fazer.

3. TIPOS
   - Datas com hora (data_compra, data_aprovacao, data_envio, data_entrega,
     data_limite_envio, data_resposta): TIMESTAMP, formato declarado
     '%Y-%m-%d %H:%M:%S'.
     Por quê: formato declarado não adivinha; formato inferido pode ler
     dia por mês sem avisar.
   - data_entrega_prevista: DATE.
     Por quê: a hora é 00:00:00 nas 99.441 linhas; guardar a hora seria
     inventar precisão.
   - data_criacao: DATE.
     Por quê: a hora é 00:00:00 em 99.139 das 99.224 avaliações; nas outras
     85 é 01:00:00, efeito de horário de verão, e não um horário de verdade.
   - Dinheiro (preco, frete, valor): DECIMAL(10,2).
     Por quê: DOUBLE não representa centavos com exatidão, e soma de
     dinheiro tem que fechar.
   - Contagens e medidas (item_seq, pagamento_seq, parcelas, tamanho_nome,
     tamanho_descricao, qtd_fotos, peso_g, comprimento_cm, altura_cm,
     largura_cm, nota): INTEGER.
   - Todo o resto continua VARCHAR, inclusive cep_prefixo.
     Por quê: 23.995 clientes têm CEP começando com zero; CEP é
     identificador, nunca é somado, e como número perderia o zero.
   A conversão é feita em SQL pelo DuckDB (strptime, CAST), disparada pelo
   Python.
   Por quê: o dado já está no banco; não há por que trazê-lo para a memória
   só para converter tipo.

4. CONVERSÃO QUE FALHA
   Para tudo. Só strptime e CAST, que estouram; nunca try_strptime,
   TRY_CAST ou errors="coerce", que transformam falha em nulo. Ao falhar:
   diz tabela, coluna e um exemplo do valor que não converteu, e encerra
   com sys.exit(1).
   Por quê: um nulo fabricado pela conversão fica indistinguível de um nulo
   verdadeiro do dado, para sempre.

5. DUPLICATAS
   Chave de cada tabela (CHAVES abaixo). Em avaliacoes a chave é
   (avaliacao_id, pedido_id): avaliacao_id sozinho não é chave, o mesmo id
   aparece em mais de um pedido.
   Linha inteira repetida: mantém uma, e conta quantas saíram.
   Chave repetida com conteúdo diferente: para, mostra a chave e as linhas
   conflitantes, sys.exit(1). Não escolhe uma por conta própria.
   Por quê: escolher em silêncio é decidir sem dizer que decidiu.

6. NULOS
   Nenhuma linha é apagada por ter nulo. Nenhum nulo é preenchido.
   Anomalias de negócio também ficam (pedido delivered sem data_entrega,
   data_envio antes da data_compra, pedido com mais de uma avaliação).
   Por quê: nas datas de pedidos o nulo é informação (pedido cancelado não
   tem data de entrega porque não foi entregue). Rotular os 610 produtos
   sem categoria é decisão de mart (aula 3), não de refined. Avaliação sem
   texto é a regra, não a exceção. refined não corrige fato; quem decide o
   que fazer com ele é a pergunta que o mart responde.

7. SAÍDA NA TELA
   Uma linha por tabela:
     refined.pedidos            99.441 -> 99.441 linhas  (0 duplicatas)
   Abaixo dela, indentadas, as colunas com nulo e a contagem:
       nulos mantidos: data_aprovacao 160, data_envio 1.783, data_entrega 2.965
   Contagens vindas do banco, milhar separado por ponto. Linha final com o
   total. stdout reconfigurado para utf-8.
   Por quê: essa saída é o instrumento de conferência da etapa: entrada =
   saída e nulos visíveis provam que nada foi apagado nem inventado. No
   Prompt de Comando do Windows, acento sai embaralhado sem o utf-8.

REEXECUÇÃO
   CREATE OR REPLACE TABLE, nunca acrescenta. Rodar dez vezes = rodar uma.
   Por quê: é o que permite errar sem medo.

ERRO
   Antes de transformar, verifica se as oito tabelas de entrada existem em
   raw. Faltando qualquer uma: lista quais, diz para rodar
   "uv run python -m pipeline.ingestao" e encerra com sys.exit(1).
   Por quê: transformar sete de oito tabelas produz um refined incompleto
   que parece completo.

Critérios de aceite:
- Oito tabelas em refined; em cada uma, linhas que saem = linhas que entram
  (com este dado, 0 duplicatas em todas). Total: 550.759.
- DESCRIBE refined.pedidos mostra TIMESTAMP nas cinco datas com hora e DATE
  em data_entrega_prevista.
- Nulos depois = nulos antes, coluna por coluna (pedidos: 160 / 1.783 /
  2.965; produtos: 610 em categoria; avaliacoes: 87.656 em titulo,
  58.247 em comentario).
- sum(preco) em refined.itens_pedido bate com sum(CAST(price AS DECIMAL))
  em raw, centavo por centavo.
- cep_prefixo continua com o zero à esquerda: '01151' e não 1151.
- Rodar duas vezes seguidas imprime exatamente a mesma coisa.
"""

import re
import sys

import duckdb

from pipeline.db import conectar, criar_schema

ORIGEM = "raw"
DESTINO = "refined"

FORMATO_DATA_HORA = "%Y-%m-%d %H:%M:%S"

# Expressões de conversão. {c} é a coluna de raw já entre aspas.
TEXTO = "{c}"
TIMESTAMP = f"strptime({{c}}, '{FORMATO_DATA_HORA}')"
# A hora é lida com o formato completo e só então descartada: assim uma
# data num formato inesperado estoura em vez de ser truncada.
DATA = f"CAST(strptime({{c}}, '{FORMATO_DATA_HORA}') AS DATE)"
DINHEIRO = "CAST({c} AS DECIMAL(10,2))"
INTEIRO = "CAST({c} AS INTEGER)"

# tabela -> [(coluna em raw, coluna em refined, conversão)], na ordem de raw.
TABELAS = {
    "pedidos": [
        ("order_id", "pedido_id", TEXTO),
        ("customer_id", "cliente_id", TEXTO),
        ("order_status", "status", TEXTO),
        ("order_purchase_timestamp", "data_compra", TIMESTAMP),
        ("order_approved_at", "data_aprovacao", TIMESTAMP),
        ("order_delivered_carrier_date", "data_envio", TIMESTAMP),
        ("order_delivered_customer_date", "data_entrega", TIMESTAMP),
        ("order_estimated_delivery_date", "data_entrega_prevista", DATA),
    ],
    "itens_pedido": [
        ("order_id", "pedido_id", TEXTO),
        ("order_item_id", "item_seq", INTEIRO),
        ("product_id", "produto_id", TEXTO),
        ("seller_id", "vendedor_id", TEXTO),
        ("shipping_limit_date", "data_limite_envio", TIMESTAMP),
        ("price", "preco", DINHEIRO),
        ("freight_value", "frete", DINHEIRO),
    ],
    "pagamentos": [
        ("order_id", "pedido_id", TEXTO),
        ("payment_sequential", "pagamento_seq", INTEIRO),
        ("payment_type", "tipo", TEXTO),
        ("payment_installments", "parcelas", INTEIRO),
        ("payment_value", "valor", DINHEIRO),
    ],
    "clientes": [
        ("customer_id", "cliente_id", TEXTO),
        ("customer_unique_id", "cliente_unico_id", TEXTO),
        ("customer_zip_code_prefix", "cep_prefixo", TEXTO),
        ("customer_city", "cidade", TEXTO),
        ("customer_state", "uf", TEXTO),
    ],
    "vendedores": [
        ("seller_id", "vendedor_id", TEXTO),
        ("seller_zip_code_prefix", "cep_prefixo", TEXTO),
        ("seller_city", "cidade", TEXTO),
        ("seller_state", "uf", TEXTO),
    ],
    "produtos": [
        ("product_id", "produto_id", TEXTO),
        ("product_category_name", "categoria", TEXTO),
        ("product_name_lenght", "tamanho_nome", INTEIRO),
        ("product_description_lenght", "tamanho_descricao", INTEIRO),
        ("product_photos_qty", "qtd_fotos", INTEIRO),
        ("product_weight_g", "peso_g", INTEIRO),
        ("product_length_cm", "comprimento_cm", INTEIRO),
        ("product_height_cm", "altura_cm", INTEIRO),
        ("product_width_cm", "largura_cm", INTEIRO),
    ],
    "traducao_categorias": [
        ("product_category_name", "categoria", TEXTO),
        ("product_category_name_english", "categoria_en", TEXTO),
    ],
    "avaliacoes": [
        ("review_id", "avaliacao_id", TEXTO),
        ("order_id", "pedido_id", TEXTO),
        ("review_score", "nota", INTEIRO),
        ("review_comment_title", "titulo", TEXTO),
        ("review_comment_message", "comentario", TEXTO),
        ("review_creation_date", "data_criacao", DATA),
        ("review_answer_timestamp", "data_resposta", TIMESTAMP),
    ],
}

# Chaves com os nomes de refined.
CHAVES = {
    "pedidos": ["pedido_id"],
    "itens_pedido": ["pedido_id", "item_seq"],
    "pagamentos": ["pedido_id", "pagamento_seq"],
    "clientes": ["cliente_id"],
    "vendedores": ["vendedor_id"],
    "produtos": ["produto_id"],
    "traducao_categorias": ["categoria"],
    "avaliacoes": ["avaliacao_id", "pedido_id"],
}

# Quantas chaves conflitantes mostrar antes de resumir o resto.
MAX_CONFLITOS_MOSTRADOS = 5


class FalhaEtapa(Exception):
    """Erro já explicado em texto; main imprime, desfaz e sai com 1."""


def _milhar(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _q(nome: str) -> str:
    return f'"{nome}"'


def _um(con: duckdb.DuckDBPyConnection, sql: str):
    # fetchall, não fetchone: o DuckDB 2 recusa o próximo comando na conexão
    # enquanto houver resultado não consumido.
    return con.execute(sql).fetchall()[0][0]


def _tabelas_faltando(con: duckdb.DuckDBPyConnection) -> list[str]:
    existentes = {
        linha[0]
        for linha in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = ?",
            [ORIGEM],
        ).fetchall()
    }
    return [t for t in TABELAS if t not in existentes]


def _valor_da_mensagem(mensagem: str) -> str:
    # O DuckDB cita o valor que não converteu na própria mensagem de erro.
    # Ler dali evita usar try_cast/try_strptime até para diagnosticar.
    achado = re.search(r"""string (["'])(.*?)\1 (?:to|according)""", mensagem)
    return achado.group(2) if achado else mensagem.splitlines()[0]


def _localizar_falha(
    con: duckdb.DuckDBPyConnection, tabela: str, erro: duckdb.Error
) -> str:
    """Converte coluna por coluna, com as mesmas expressões estritas, até
    achar a que estoura. Devolve a mensagem para o usuário."""
    for origem, destino, conversao in TABELAS[tabela]:
        if conversao is TEXTO:
            continue
        expr = conversao.format(c=_q(origem))
        try:
            # count(expr) obriga a avaliar a expressão em todas as linhas.
            _um(con, f"SELECT count({expr}) FROM {ORIGEM}.{_q(tabela)}")
        except duckdb.Error as e:
            return (
                f"Conversão falhou em {ORIGEM}.{tabela}.{origem} "
                f"(-> {DESTINO}.{tabela}.{destino}): "
                f"valor {_valor_da_mensagem(str(e))!r} não converteu.\n"
                f"  {str(e).splitlines()[0]}"
            )
    # Não deveria acontecer: o CREATE falhou mas nenhuma coluna isolada falha.
    return f"Conversão falhou em {ORIGEM}.{tabela}: {erro}"


def _conflitos_de_chave(con: duckdb.DuckDBPyConnection, tabela: str) -> str | None:
    destino = f"{DESTINO}.{_q(tabela)}"
    chave = ", ".join(_q(c) for c in CHAVES[tabela])
    # A tabela já está sem linhas inteiras repetidas, então chave repetida
    # aqui é necessariamente conteúdo diferente.
    repetidas = con.execute(
        f"SELECT {chave} FROM {destino} GROUP BY ALL HAVING count(*) > 1 ORDER BY ALL"
    ).fetchall()
    if not repetidas:
        return None

    colunas = [d for _, d, _ in TABELAS[tabela]]
    cabecalho = (
        f"Chave repetida com conteúdo diferente em {DESTINO}.{tabela} "
        f"({_milhar(len(repetidas))} chaves). Chave: ({', '.join(CHAVES[tabela])})"
    )
    linhas = [cabecalho]
    for valores in repetidas[:MAX_CONFLITOS_MOSTRADOS]:
        filtro = " AND ".join(f"{_q(c)} IS NOT DISTINCT FROM ?" for c in CHAVES[tabela])
        conflitantes = con.execute(
            f"SELECT * FROM {destino} WHERE {filtro} ORDER BY ALL", list(valores)
        ).fetchall()
        linhas.append(f"  chave {valores}:")
        for registro in conflitantes:
            linhas.append(
                "    " + ", ".join(f"{c}={v!r}" for c, v in zip(colunas, registro))
            )
    if len(repetidas) > MAX_CONFLITOS_MOSTRADOS:
        resto = len(repetidas) - MAX_CONFLITOS_MOSTRADOS
        linhas.append(f"  ... e mais {_milhar(resto)} chaves.")
    return "\n".join(linhas)


def _transformar(con: duckdb.DuckDBPyConnection, tabela: str) -> tuple[int, int, int]:
    """Cria refined.<tabela>. Devolve (linhas em raw, linhas em refined,
    duplicatas removidas)."""
    origem = f"{ORIGEM}.{_q(tabela)}"
    destino = f"{DESTINO}.{_q(tabela)}"
    selecao = ", ".join(
        f"{conversao.format(c=_q(o))} AS {_q(d)}" for o, d, conversao in TABELAS[tabela]
    )
    # O DISTINCT é feito sobre o texto de raw, antes de converter: duas linhas
    # que só ficariam iguais depois da conversão (ex.: 01:00:00 e 00:00:00 em
    # data_criacao) não são "linha inteira repetida" e caem na checagem de
    # chave, onde o script para em vez de escolher.
    try:
        con.execute(
            f"CREATE OR REPLACE TABLE {destino} AS "
            f"SELECT {selecao} FROM (SELECT DISTINCT * FROM {origem})"
        )
    except (duckdb.ConversionException, duckdb.InvalidInputException) as e:
        # A transação fica abortada após o erro; o diagnóstico precisa de
        # uma transação nova, e a de main já não vale mais nada.
        con.execute("ROLLBACK")
        raise FalhaEtapa(_localizar_falha(con, tabela, e)) from e

    conflito = _conflitos_de_chave(con, tabela)
    if conflito:
        raise FalhaEtapa(conflito)

    entrada = _um(con, f"SELECT count(*) FROM {origem}")
    saida = _um(con, f"SELECT count(*) FROM {destino}")
    return entrada, saida, entrada - saida


def _nulos(con: duckdb.DuckDBPyConnection, tabela: str) -> list[tuple[str, int]]:
    colunas = [d for _, d, _ in TABELAS[tabela]]
    contagens = con.execute(
        "SELECT "
        + ", ".join(f"count(*) - count({_q(c)})" for c in colunas)
        + f" FROM {DESTINO}.{_q(tabela)}"
    ).fetchall()[0]
    return [(c, n) for c, n in zip(colunas, contagens) if n]


def _linha(nome: str, entrada: int, saida: int, duplicatas: int) -> str:
    return (
        f"{nome:<28}{_milhar(entrada):>7} -> {_milhar(saida):>7} linhas  "
        f"({_milhar(duplicatas)} duplicatas)"
    )


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    con = conectar()
    try:
        faltando = _tabelas_faltando(con)
        if faltando:
            print(f"Tabelas faltando no schema {ORIGEM}:", file=sys.stderr)
            for tabela in faltando:
                print(f"  {ORIGEM}.{tabela}", file=sys.stderr)
            print('Rode antes: "uv run python -m pipeline.ingestao"', file=sys.stderr)
            sys.exit(1)

        # Uma transação para as oito tabelas: se a sexta falha, as cinco
        # primeiras não ficam recriadas ao lado de três versões antigas.
        con.execute("BEGIN TRANSACTION")
        try:
            criar_schema(con, DESTINO)
            relatorio = []
            for tabela in TABELAS:
                entrada, saida, duplicatas = _transformar(con, tabela)
                relatorio.append(
                    (tabela, entrada, saida, duplicatas, _nulos(con, tabela))
                )
            con.execute("COMMIT")
        except FalhaEtapa as e:
            # _transformar pode já ter desfeito a transação (erro de conversão).
            try:
                con.execute("ROLLBACK")
            except duckdb.Error:
                pass
            print(str(e), file=sys.stderr)
            sys.exit(1)

        total_entrada = total_saida = total_duplicatas = 0
        for tabela, entrada, saida, duplicatas, nulos in relatorio:
            print(_linha(f"{DESTINO}.{tabela}", entrada, saida, duplicatas))
            if nulos:
                print(
                    "    nulos mantidos: "
                    + ", ".join(f"{c} {_milhar(n)}" for c, n in nulos)
                )
            total_entrada += entrada
            total_saida += saida
            total_duplicatas += duplicatas
        print(_linha("Total", total_entrada, total_saida, total_duplicatas))
    finally:
        con.close()


if __name__ == "__main__":
    main()

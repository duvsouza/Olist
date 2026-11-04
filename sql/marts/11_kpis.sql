-- Os cartões do dashboard que não saem dos marts 03 e 05.
-- Grão: a operação inteira, uma linha. Cada CTE também tem uma linha só,
-- e é isso que torna seguro juntá-las sem ON.
WITH receita_pedido AS (
    -- Grão: um pedido válido com item.
    SELECT p.pedido_id, sum(i.preco) AS receita, sum(i.frete) AS frete
    FROM refined.pedidos      AS p
    JOIN refined.itens_pedido AS i ON i.pedido_id = p.pedido_id
    WHERE p.status NOT IN ('canceled', 'unavailable')
    GROUP BY p.pedido_id
),
venda AS (
    SELECT
        round(avg(receita), 2)                                     AS ticket_medio,
        round(median(receita), 2)                                  AS ticket_mediana,
        round(100.0 * sum(frete) / (sum(receita) + sum(frete)), 1) AS pct_frete
    FROM receita_pedido
),
cancelamento AS (
    SELECT round(100.0 * count(*) FILTER (WHERE status = 'canceled') / count(*), 2) AS pct_cancelados
    FROM refined.pedidos
),
entrega AS (
    SELECT
        round(avg(date_diff('day', data_compra, data_entrega)), 1) AS dias_entrega,
        median(date_diff('day', data_compra, data_entrega))        AS dias_entrega_mediana
    FROM refined.pedidos
    WHERE status = 'delivered'
      AND data_entrega IS NOT NULL
),
satisfacao AS (
    SELECT round(avg(nota), 2) AS nota_media
    FROM refined.avaliacoes
)
SELECT *
FROM venda, cancelamento, entrega, satisfacao
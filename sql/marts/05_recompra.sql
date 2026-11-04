-- Quantos clientes voltaram a comprar?
-- Grão: um número de pedidos por cliente (1 pedido, 2 pedidos...).
-- Cliente é a pessoa (cliente_unico_id). Só pedidos válidos.
WITH pedidos_por_pessoa AS (
    -- Grão: uma pessoa.
    SELECT
        c.cliente_unico_id,
        count(*) AS pedidos
    FROM refined.pedidos  AS p
    JOIN refined.clientes AS c ON c.cliente_id = p.cliente_id
    WHERE p.status NOT IN ('canceled', 'unavailable')
    GROUP BY c.cliente_unico_id
)
SELECT
    pedidos                                            AS pedidos_por_cliente,
    count(*)                                           AS clientes,
    round(100.0 * count(*) / sum(count(*)) OVER (), 2) AS pct_clientes
FROM pedidos_por_pessoa
GROUP BY pedidos
ORDER BY pedidos_por_cliente
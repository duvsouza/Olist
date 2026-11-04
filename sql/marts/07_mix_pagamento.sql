-- Mix de pagamento nos pedidos válidos.
-- Grão: um tipo de pagamento.
-- valor soma R$ 15.739.137,01, mais que a receita do mart 01: o cliente paga
-- também o frete (R$ 2.241.126,29) e juros. A coluna pedidos não soma entre
-- tipos: pedido pago com cartão e voucher conta nos dois (soma 100.417).
SELECT
    g.tipo,
    count(*)                                                     AS pagamentos,
    count(DISTINCT g.pedido_id)                                  AS pedidos,
    sum(g.valor)                                                 AS valor,
    round(100.0 * sum(g.valor) / sum(sum(g.valor)) OVER (), 1)   AS pct_valor
FROM refined.pagamentos AS g
JOIN refined.pedidos    AS p ON p.pedido_id = g.pedido_id
WHERE p.status NOT IN ('canceled', 'unavailable')
GROUP BY g.tipo
ORDER BY valor DESC
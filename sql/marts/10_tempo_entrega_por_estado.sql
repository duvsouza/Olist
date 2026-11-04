-- Tempo de entrega por estado.
-- Grão: uma UF do cliente. Mesmo denominador do mart 03.
-- Parte de data_compra: o tempo que o cliente espera, não só o da transportadora.
SELECT
    c.uf,
    count(*)                                                       AS entregues,
    round(avg(date_diff('day', p.data_compra, p.data_entrega)), 1) AS dias_medio,
    median(date_diff('day', p.data_compra, p.data_entrega))        AS dias_mediana
FROM refined.pedidos  AS p
JOIN refined.clientes AS c ON c.cliente_id = p.cliente_id
WHERE p.status = 'delivered'
  AND p.data_entrega IS NOT NULL
GROUP BY c.uf
ORDER BY dias_medio
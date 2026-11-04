-- Quanto chegou no prazo?
-- Grão: a operação inteira, uma linha.
-- Denominador: delivered com data de entrega. Chegar no dia previsto é no prazo.
SELECT
    count(*) AS entregues,
    sum(CASE WHEN data_entrega::DATE <= data_entrega_prevista THEN 1 ELSE 0 END) AS no_prazo,
    sum(CASE WHEN data_entrega::DATE >  data_entrega_prevista THEN 1 ELSE 0 END) AS atrasados,
    round(100.0 * sum(CASE WHEN data_entrega::DATE <= data_entrega_prevista THEN 1 ELSE 0 END)
          / count(*), 1) AS pct_no_prazo
FROM refined.pedidos
WHERE status = 'delivered'
  AND data_entrega IS NOT NULL
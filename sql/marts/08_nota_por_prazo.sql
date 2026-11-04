-- A nota de quem recebeu no prazo e atrasado.
-- Grão: uma situação de entrega. Mesmo denominador do mart 03.
WITH nota_pedido AS (
    -- Grão: um pedido avaliado, com a média das suas avaliações.
    SELECT pedido_id, avg(nota) AS nota
    FROM refined.avaliacoes
    GROUP BY pedido_id
),
entregue AS (
    -- Grão: um pedido delivered com data de entrega.
    SELECT pedido_id,
           CASE WHEN data_entrega::DATE <= data_entrega_prevista
                THEN 'no_prazo' ELSE 'atrasado' END AS situacao
    FROM refined.pedidos
    WHERE status = 'delivered'
      AND data_entrega IS NOT NULL
)
SELECT
    e.situacao,
    count(*)                                                     AS pedidos_avaliados,
    round(avg(n.nota), 2)                                        AS nota_media,
    round(100.0 * count(*) FILTER (WHERE n.nota <= 2) / count(*), 1) AS pct_nota_baixa
FROM entregue    AS e
JOIN nota_pedido AS n ON n.pedido_id = e.pedido_id
GROUP BY e.situacao
ORDER BY e.situacao DESC
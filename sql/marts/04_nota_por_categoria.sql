-- Que nota cada categoria recebe, e qual a posição dela?
-- Grão: uma categoria com 100 pedidos avaliados ou mais.
-- Cada pedido conta uma vez por categoria, com a média das suas avaliações.
WITH nota_pedido AS (
    SELECT pedido_id, avg(nota) AS nota
    FROM refined.avaliacoes
    GROUP BY pedido_id
),
categoria_pedido AS (
    SELECT DISTINCT
        i.pedido_id,
        coalesce(t.categoria_en, pr.categoria, 'sem_categoria') AS categoria
    FROM refined.itens_pedido             AS i
    JOIN refined.produtos                 AS pr ON pr.produto_id = i.produto_id
    LEFT JOIN refined.traducao_categorias AS t  ON t.categoria  = pr.categoria
),
por_categoria AS (
    SELECT
        c.categoria,
        count(*)              AS pedidos_avaliados,
        round(avg(n.nota), 2) AS nota_media
    FROM categoria_pedido AS c
    JOIN nota_pedido      AS n ON n.pedido_id = c.pedido_id
    GROUP BY c.categoria
    HAVING count(*) >= 100
)
SELECT
    categoria,
    pedidos_avaliados,
    nota_media,
    rank() OVER (ORDER BY nota_media) AS posicao_pior
FROM por_categoria
ORDER BY posicao_pior
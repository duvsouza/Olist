-- Quais categorias mais vendem?
-- Grão: uma categoria. A coluna pedidos não soma entre categorias.
SELECT
    coalesce(t.categoria_en, pr.categoria, 'sem_categoria') AS categoria,
    count(DISTINCT p.pedido_id)                             AS pedidos,
    count(*)                                                AS itens,
    sum(i.preco)                                            AS receita
FROM refined.itens_pedido             AS i
JOIN refined.pedidos                  AS p  ON p.pedido_id  = i.pedido_id
JOIN refined.produtos                 AS pr ON pr.produto_id = i.produto_id
LEFT JOIN refined.traducao_categorias AS t  ON t.categoria  = pr.categoria
WHERE p.status NOT IN ('canceled', 'unavailable')
GROUP BY 1
ORDER BY receita DESC
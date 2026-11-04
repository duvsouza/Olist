-- Ticket médio por estado.
-- Grão: uma UF do cliente.
WITH receita_pedido AS (
    -- Grão: um pedido válido com item.
    SELECT p.pedido_id, c.uf, sum(i.preco) AS receita
    FROM refined.itens_pedido AS i
    JOIN refined.pedidos      AS p ON p.pedido_id  = i.pedido_id
    JOIN refined.clientes     AS c ON c.cliente_id = p.cliente_id
    WHERE p.status NOT IN ('canceled', 'unavailable')
    GROUP BY p.pedido_id, c.uf
)
SELECT uf, count(*) AS pedidos, round(avg(receita), 2) AS ticket_medio
FROM receita_pedido
GROUP BY uf
ORDER BY ticket_medio DESC
-- Quantas pessoas compram de cada UF?
-- Grão: uma UF. A coluna clientes não soma: 39 pessoas aparecem em mais de uma UF.
SELECT
    uf,
    count(DISTINCT cliente_unico_id) AS clientes
FROM refined.clientes
GROUP BY uf
ORDER BY clientes DESC
-- ============================================================
-- Migration V2: acrescenta o 9º tipo de imperfeição do §5.1
-- ============================================================
-- O §5.1 do documento lista 9 tipos de imperfeição a injetar, mas o
-- enum criado em V1 tem só 8 — faltava "datas fora de ordem lógica"
-- (aposentadoria antes do ingresso, óbito antes do nascimento),
-- dimensão de qualidade: consistência.
--
-- Esta migration contém APENAS o ADD VALUE, de propósito: o Flyway
-- envolve cada migration numa transação, e o Postgres proíbe usar um
-- valor de enum recém-adicionado dentro da mesma transação em que ele
-- foi criado ("unsafe use of new value of enum type"). Qualquer INSERT
-- ou CHECK citando 'datas_fora_ordem' aqui faria a migration falhar.

ALTER TYPE tipo_erro_injetado_enum ADD VALUE 'datas_fora_ordem';

-- ============================================================
-- Migration V3: camada de staging, cpf_sintetico e constraints
-- ============================================================
-- Motivação: o §5.1 exige injetar nulos em campos obrigatórios
-- (ex.: data_nascimento) e unidades/formatos trocados (valor em
-- centavos, data em DD/MM/AAAA). Contra as tabelas tipadas e NOT NULL
-- de V1 isso é fisicamente impossível.
--
-- Solução: o gerador passa a escrever SUJO no schema `staging`, onde
-- todo campo de negócio é TEXT NULL. O pipeline de qualidade valida,
-- pontua e PROMOVE as linhas aprovadas para as tabelas tipadas de V1.
-- As tabelas de V1 continuam sendo o dataset de análise; o staging é
-- a área de entrada + o log de rejeição.

-- ---------- 1. cpf_sintetico ----------
-- O §5.1 define duplicidade como "mesmo CPF sintético, IDs diferentes",
-- mas V1 não tinha o campo. Nullable: a tabela pode já estar populada
-- e o erro de completude precisa que a coluna aceite ausência.

ALTER TABLE participante ADD COLUMN cpf_sintetico VARCHAR(11);

CREATE INDEX idx_participante_cpf ON participante (cpf_sintetico);

-- ---------- 2. schema staging ----------

CREATE SCHEMA IF NOT EXISTS staging;

COMMENT ON SCHEMA staging IS
    'Área de entrada do gerador. Todo campo de negócio é TEXT NULL para '
    'aceitar as imperfeições do §5.1. Linha rejeitada fica com '
    'promovido = FALSE e motivos_rejeicao preenchido.';

-- As 5 colunas de controle abaixo são idênticas nas 4 tabelas:
--   staging_id       PK física da linha de entrada. Só é usada quando o
--                    id de negócio foi corrompido (erro 'nulo' ou
--                    'duplicidade') — nos demais casos o elo com a
--                    tabela final é o próprio id de negócio, que o
--                    gerador emite antes de escrever e a promoção reusa.
--   lote_id          uma execução do gerador.
--   ingerido_em      quando a linha entrou no staging.
--   promovido        TRUE depois que o pipeline copiou para a tabela final.
--   motivos_rejeicao códigos das regras que barraram a linha (R01..R99).

CREATE TABLE staging.participante (
    staging_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lote_id                  UUID NOT NULL,
    ingerido_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    promovido                BOOLEAN NOT NULL DEFAULT FALSE,
    motivos_rejeicao         TEXT[],
    participante_id          TEXT,
    cpf_sintetico            TEXT,
    plano_tipo               TEXT,
    submassa                 TEXT,
    sexo                     TEXT,
    data_nascimento          TEXT,
    data_ingresso            TEXT,
    data_desligamento        TEXT,
    status_atual             TEXT,
    data_evento_conhecimento TEXT,
    data_vigencia_inicio     TEXT,
    data_vigencia_fim        TEXT,
    versao_registro          TEXT
);

CREATE TABLE staging.evento (
    staging_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lote_id            UUID NOT NULL,
    ingerido_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    promovido          BOOLEAN NOT NULL DEFAULT FALSE,
    motivos_rejeicao   TEXT[],
    evento_id          TEXT,
    participante_id    TEXT,
    tipo_evento        TEXT,
    data_evento        TEXT,
    data_conhecimento  TEXT,
    fonte              TEXT
);

CREATE TABLE staging.exposicao (
    staging_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lote_id           UUID NOT NULL,
    ingerido_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    promovido         BOOLEAN NOT NULL DEFAULT FALSE,
    motivos_rejeicao  TEXT[],
    exposicao_id      TEXT,
    participante_id   TEXT,
    submassa          TEXT,
    idade_exata       TEXT,
    ano_calendario    TEXT,
    tempo_exposto     TEXT,
    tipo_saida        TEXT,
    data_base         TEXT
);

CREATE TABLE staging.contribuicao_beneficio (
    staging_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lote_id             UUID NOT NULL,
    ingerido_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    promovido           BOOLEAN NOT NULL DEFAULT FALSE,
    motivos_rejeicao    TEXT[],
    id                  TEXT,
    participante_id     TEXT,
    competencia         TEXT,
    valor_contribuicao  TEXT,
    valor_beneficio     TEXT,
    status_pagamento    TEXT
);

CREATE INDEX idx_stg_participante_lote ON staging.participante (lote_id);
CREATE INDEX idx_stg_evento_lote ON staging.evento (lote_id);
CREATE INDEX idx_stg_exposicao_lote ON staging.exposicao (lote_id);
CREATE INDEX idx_stg_contrib_lote ON staging.contribuicao_beneficio (lote_id);

-- ---------- 3. view de rejeitados ----------
-- Não existe tabela de quarentena: o próprio staging é o log de
-- rejeição. Esta view unifica as 4 tabelas para o relatório.

CREATE VIEW staging.v_rejeitados AS
    SELECT 'participante' AS tabela_origem, staging_id, lote_id,
           participante_id AS registro_id, motivos_rejeicao
      FROM staging.participante WHERE NOT promovido
    UNION ALL
    SELECT 'evento', staging_id, lote_id, evento_id, motivos_rejeicao
      FROM staging.evento WHERE NOT promovido
    UNION ALL
    SELECT 'exposicao', staging_id, lote_id, exposicao_id, motivos_rejeicao
      FROM staging.exposicao WHERE NOT promovido
    UNION ALL
    SELECT 'contribuicao_beneficio', staging_id, lote_id, id, motivos_rejeicao
      FROM staging.contribuicao_beneficio WHERE NOT promovido;

-- ---------- 4. unicidade do data_quality_score ----------
-- Sem isso, reexecutar o pipeline duplica os scores. Com o índice, o
-- pipeline usa ON CONFLICT DO UPDATE e a reexecução é idempotente.

CREATE UNIQUE INDEX uq_dqs_avaliacao ON data_quality_score
    (granularidade, referencia_id, dimensao_qualidade, data_avaliacao, regra_aplicada);

-- ---------- 5. referencia_externa: esqueleto pré-benchmark ----------
-- R__referencia_externa.sql insere as 4 fontes do §1 com o escopo de
-- comparação já definido pelo documento, mas versao_tabua e
-- data_consulta só existem depois que alguém de fato consultar a fonte.
-- Relaxar o NOT NULL evita que o seed precise inventar esses valores.

ALTER TABLE referencia_externa ALTER COLUMN versao_tabua DROP NOT NULL;
ALTER TABLE referencia_externa ALTER COLUMN data_consulta DROP NOT NULL;

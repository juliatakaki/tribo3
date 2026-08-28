-- ============================================================
-- Tribo 3 — Massa Sintética Previdenciária
-- Migration V1: schema inicial
-- Convenção: migrations/V{n}__descricao.sql, nunca editar uma
-- migration já aplicada — mudança de schema = V2, V3, etc.
-- ============================================================

-- ---------- ENUMS ----------
-- Valores fechados aqui; qualquer novo valor exige nova migration.

CREATE TYPE plano_tipo_enum AS ENUM ('BD', 'CD', 'CV');

CREATE TYPE sexo_enum AS ENUM ('M', 'F');

CREATE TYPE status_participante_enum AS ENUM (
    'ativo', 'aposentado', 'desligado', 'obito', 'pensionista'
);

CREATE TYPE tipo_evento_enum AS ENUM (
    'obito', 'invalidez', 'aposentadoria', 'desligamento',
    'correcao_cadastral', 'atraso_contribuicao', 'mudanca_regra'
);

CREATE TYPE tipo_saida_enum AS ENUM ('obito', 'censura', 'saida_estudo');

CREATE TYPE status_pagamento_enum AS ENUM ('em_dia', 'atraso', 'quitado');

CREATE TYPE fonte_externa_enum AS ENUM ('IBGE', 'HMD', 'BR_EMS', 'SOA');

CREATE TYPE granularidade_dq_enum AS ENUM (
    'variavel', 'participante', 'submassa_plano', 'data_base'
);

CREATE TYPE dimensao_qualidade_enum AS ENUM (
    'completude', 'validade', 'consistencia', 'unicidade',
    'acuracia', 'temporalidade', 'materialidade'
);

CREATE TYPE tipo_erro_injetado_enum AS ENUM (
    'idade_invalida', 'duplicidade', 'grafia_divergente', 'nulo',
    'outlier', 'orfao', 'atraso_anomalo', 'unidade_trocada'
);

-- ---------- 3.1 participante ----------
-- Bitemporal: nunca UPDATE em campo de negócio, sempre INSERT de novo
-- snapshot. participante_id é o identificador lógico (repete entre
-- snapshots); participante_registro_id é a PK física de cada snapshot.

CREATE TABLE participante (
    participante_registro_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    participante_id          UUID NOT NULL,
    plano_tipo               plano_tipo_enum NOT NULL,
    submassa                 VARCHAR(50) NOT NULL,
    sexo                     sexo_enum NOT NULL,
    data_nascimento          DATE NOT NULL,
    data_ingresso            DATE NOT NULL,
    data_desligamento        DATE,
    status_atual             status_participante_enum NOT NULL,
    data_evento_conhecimento TIMESTAMPTZ NOT NULL,
    data_vigencia_inicio     DATE NOT NULL,
    data_vigencia_fim        DATE,
    versao_registro          INT NOT NULL,
    UNIQUE (participante_id, versao_registro)
);

CREATE INDEX idx_participante_id ON participante (participante_id);
CREATE INDEX idx_participante_submassa ON participante (submassa);
CREATE INDEX idx_participante_vigencia_atual
    ON participante (participante_id) WHERE data_vigencia_fim IS NULL;

-- ---------- 3.2 evento ----------

CREATE TABLE evento (
    evento_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    participante_id    UUID NOT NULL,
    tipo_evento         tipo_evento_enum NOT NULL,
    data_evento         DATE NOT NULL,
    data_conhecimento   TIMESTAMPTZ NOT NULL,
    fonte               VARCHAR(100) NOT NULL
);

CREATE INDEX idx_evento_participante ON evento (participante_id);
CREATE INDEX idx_evento_tipo ON evento (tipo_evento);

-- Nota: sem FK física para participante_id aqui de propósito — ver
-- seção 5 (registro_erro_injetado tipo 'orfao' testa exatamente a
-- ausência dessa integridade referencial). Se decidirem que órfão deve
-- ser sempre impossível no dado "limpo", trocar por:
-- REFERENCES participante(participante_id) e mover a injeção de erro
-- órfão para uma etapa que desliga a constraint temporariamente.

-- ---------- 3.3 exposicao ----------

CREATE TABLE exposicao (
    exposicao_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    participante_id   UUID NOT NULL,
    submassa          VARCHAR(50) NOT NULL,
    idade_exata       DECIMAL(6,3) NOT NULL,
    ano_calendario    INT NOT NULL,
    tempo_exposto     DECIMAL(6,5) NOT NULL,
    tipo_saida        tipo_saida_enum NOT NULL,
    data_base         DATE NOT NULL
);

CREATE INDEX idx_exposicao_participante ON exposicao (participante_id);
CREATE INDEX idx_exposicao_submassa_database ON exposicao (submassa, data_base);
CREATE INDEX idx_exposicao_ano ON exposicao (ano_calendario);

-- ---------- 3.4 contribuicao_beneficio ----------

CREATE TABLE contribuicao_beneficio (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    participante_id     UUID NOT NULL,
    competencia         DATE NOT NULL,  -- primeiro dia do mês de referência
    valor_contribuicao  DECIMAL(14,2) NOT NULL,
    valor_beneficio     DECIMAL(14,2),
    status_pagamento    status_pagamento_enum NOT NULL
);

CREATE INDEX idx_contrib_participante ON contribuicao_beneficio (participante_id);
CREATE INDEX idx_contrib_competencia ON contribuicao_beneficio (competencia);

-- ---------- 3.5 referencia_externa ----------
-- Tabela independente, sem FK para participante — só registra benchmark.

CREATE TABLE referencia_externa (
    referencia_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fonte                fonte_externa_enum NOT NULL,
    versao_tabua         VARCHAR(50) NOT NULL,
    escopo_comparacao    VARCHAR(200) NOT NULL,
    data_consulta        DATE NOT NULL,
    resultado_benchmark  TEXT
);

-- ---------- 3.6 dicionario_dados ----------

CREATE TABLE dicionario_dados (
    nome_campo      VARCHAR(100) NOT NULL,
    tabela          VARCHAR(100) NOT NULL,
    tipo            VARCHAR(50) NOT NULL,
    unidade         VARCHAR(50),
    dominio_valido  TEXT,
    obrigatorio     BOOLEAN NOT NULL,
    origem          VARCHAR(100) NOT NULL,
    responsavel     VARCHAR(100) NOT NULL,
    versao          VARCHAR(20) NOT NULL,
    PRIMARY KEY (tabela, nome_campo, versao)
);

-- ---------- 3.7 data_quality_score ----------

CREATE TABLE data_quality_score (
    score_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    granularidade       granularidade_dq_enum NOT NULL,
    referencia_id       VARCHAR(200) NOT NULL,
    dimensao_qualidade  dimensao_qualidade_enum NOT NULL,
    score               DECIMAL(4,3) NOT NULL CHECK (score BETWEEN 0 AND 1),
    data_avaliacao      DATE NOT NULL,
    regra_aplicada      VARCHAR(100) NOT NULL
);

CREATE INDEX idx_dqs_granularidade ON data_quality_score (granularidade, referencia_id);
CREATE INDEX idx_dqs_data_avaliacao ON data_quality_score (data_avaliacao);

-- ---------- 5.2 registro_erro_injetado (gabarito) ----------
-- Schema separado de propósito: não é dado de análise, é gabarito
-- interno pra medir precisão/recall do pipeline de qualidade.

CREATE SCHEMA IF NOT EXISTS gabarito;

CREATE TABLE gabarito.registro_erro_injetado (
    erro_id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tabela_alvo              VARCHAR(100) NOT NULL,
    registro_id              VARCHAR(200) NOT NULL,
    campo_afetado            VARCHAR(100) NOT NULL,
    tipo_erro                tipo_erro_injetado_enum NOT NULL,
    valor_correto_original   TEXT,
    valor_injetado           TEXT NOT NULL,
    detectado_pela_limpeza   BOOLEAN
);

CREATE INDEX idx_gabarito_tabela_registro
    ON gabarito.registro_erro_injetado (tabela_alvo, registro_id);

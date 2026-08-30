-- ============================================================
-- Repeatable: dicionário de dados (§3.6)
-- ============================================================
-- Migration REPEATABLE (prefixo R__) de propósito: o Flyway reexecuta
-- toda vez que o checksum do arquivo muda. O dicionário evolui junto
-- com o schema, e congelá-lo numa migration versionada obrigaria a
-- criar V8__, V9__ só para corrigir uma descrição.
--
-- O §3.6 exige no mínimo 15 campos documentados; o modelo tem ~50.
--
-- PENDENTE: a coluna `responsavel` está preenchida com 'Tribo 3' —
-- trocar pela dupla responsável por cada tabela quando o time definir.

DELETE FROM dicionario_dados;

INSERT INTO dicionario_dados
    (tabela, nome_campo, tipo, unidade, dominio_valido, obrigatorio, origem, responsavel, versao)
VALUES
-- ---------- 3.1 participante ----------
('participante', 'participante_registro_id', 'uuid', NULL, 'UUID v4', TRUE, 'banco', 'Tribo 3', 'V3'),
('participante', 'participante_id', 'uuid', NULL, 'UUID v4; identificador lógico, repete entre snapshots', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'cpf_sintetico', 'string', NULL, '11 dígitos; sintético, nunca CPF real', FALSE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'plano_tipo', 'enum', NULL, 'BD, CD, CV', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'submassa', 'string', NULL, 'Plano A, Plano B, Plano C', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'sexo', 'enum', NULL, 'M, F', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'data_nascimento', 'date', 'data', 'ISO 8601; idade resultante entre 0 e 130 anos', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'data_ingresso', 'date', 'data', 'ISO 8601; >= data_nascimento + 18 anos', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'data_desligamento', 'date', 'data', 'ISO 8601; >= data_ingresso; nula se não houve desligamento', FALSE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'status_atual', 'enum', NULL, 'ativo, aposentado, desligado, obito, pensionista', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'data_evento_conhecimento', 'timestamp', 'timestamp', 'ISO 8601 com timezone; >= data_vigencia_inicio', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'data_vigencia_inicio', 'date', 'data', 'ISO 8601; início de validade do snapshot', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'data_vigencia_fim', 'date', 'data', 'ISO 8601; nula enquanto o snapshot é o vigente', FALSE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('participante', 'versao_registro', 'int', 'contagem', 'inteiro >= 1; único por participante_id', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),

-- ---------- 3.2 evento ----------
('evento', 'evento_id', 'uuid', NULL, 'UUID v4', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('evento', 'participante_id', 'uuid', NULL, 'UUID v4; sem FK física de propósito — permite o erro órfão do §5.1', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('evento', 'tipo_evento', 'enum', NULL, 'obito, invalidez, aposentadoria, desligamento, correcao_cadastral, atraso_contribuicao, mudanca_regra', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('evento', 'data_evento', 'date', 'data', 'ISO 8601; data real de ocorrência', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('evento', 'data_conhecimento', 'timestamp', 'timestamp', 'ISO 8601 com timezone; >= data_evento', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('evento', 'fonte', 'string', NULL, 'texto livre; origem do dado para lineage', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),

-- ---------- 3.3 exposicao ----------
('exposicao', 'exposicao_id', 'uuid', NULL, 'UUID v4', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('exposicao', 'participante_id', 'uuid', NULL, 'UUID v4', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('exposicao', 'submassa', 'string', NULL, 'Plano A, Plano B, Plano C', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('exposicao', 'idade_exata', 'decimal', 'anos', 'DECIMAL(6,3); entre 0 e 130', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('exposicao', 'ano_calendario', 'int', 'ano', 'inteiro; ano civil da observação', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('exposicao', 'tempo_exposto', 'decimal', 'fração de ano', 'DECIMAL(6,5); entre 0 e 1', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('exposicao', 'tipo_saida', 'enum', NULL, 'obito, censura, saida_estudo', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('exposicao', 'data_base', 'date', 'data', 'ISO 8601; data de corte da avaliação', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),

-- ---------- 3.4 contribuicao_beneficio ----------
('contribuicao_beneficio', 'id', 'uuid', NULL, 'UUID v4', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('contribuicao_beneficio', 'participante_id', 'uuid', NULL, 'UUID v4', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('contribuicao_beneficio', 'competencia', 'date', 'ano-mês', 'ISO 8601; sempre o primeiro dia do mês de referência', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('contribuicao_beneficio', 'valor_contribuicao', 'decimal', 'BRL', 'DECIMAL(14,2); >= 0', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('contribuicao_beneficio', 'valor_beneficio', 'decimal', 'BRL', 'DECIMAL(14,2); >= 0; nulo fora da fase de benefício', FALSE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('contribuicao_beneficio', 'status_pagamento', 'enum', NULL, 'em_dia, atraso, quitado', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),

-- ---------- 3.5 referencia_externa ----------
('referencia_externa', 'referencia_id', 'uuid', NULL, 'UUID v4', TRUE, 'banco', 'Tribo 3', 'V3'),
('referencia_externa', 'fonte', 'enum', NULL, 'IBGE, HMD, BR_EMS, SOA', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('referencia_externa', 'versao_tabua', 'string', NULL, 'texto livre; nula até a fonte ser efetivamente consultada', FALSE, 'curadoria_manual', 'Tribo 3', 'V3'),
('referencia_externa', 'escopo_comparacao', 'string', NULL, 'texto livre; ex.: qx, tendência, improvement, faixa etária', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('referencia_externa', 'data_consulta', 'date', 'data', 'ISO 8601; nula até a fonte ser efetivamente consultada', FALSE, 'curadoria_manual', 'Tribo 3', 'V3'),
('referencia_externa', 'resultado_benchmark', 'text', NULL, 'texto livre; não é dado de entrada do modelo', FALSE, 'curadoria_manual', 'Tribo 3', 'V3'),

-- ---------- 3.6 dicionario_dados ----------
('dicionario_dados', 'nome_campo', 'string', NULL, 'nome técnico do campo', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'tabela', 'string', NULL, 'tabela de origem do campo', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'tipo', 'string', NULL, 'string, date, decimal, enum, uuid, int, bool, text, timestamp', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'unidade', 'string', NULL, 'unidade de medida, quando aplicável', FALSE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'dominio_valido', 'text', NULL, 'valores/regras permitidos para o campo', FALSE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'obrigatorio', 'bool', NULL, 'true, false', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'origem', 'string', NULL, 'sistema/gerador responsável pela criação do campo', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'responsavel', 'string', NULL, 'dupla/pessoa responsável pelo campo', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),
('dicionario_dados', 'versao', 'string', NULL, 'versão do schema em que o campo foi definido', TRUE, 'curadoria_manual', 'Tribo 3', 'V3'),

-- ---------- 3.7 data_quality_score ----------
('data_quality_score', 'score_id', 'uuid', NULL, 'UUID v4', TRUE, 'banco', 'Tribo 3', 'V3'),
('data_quality_score', 'granularidade', 'enum', NULL, 'variavel, participante, submassa_plano, data_base', TRUE, 'pipeline_qualidade', 'Tribo 3', 'V3'),
-- Convenção de preenchimento do referencia_id, fixada aqui para que a
-- tabela continue interpretável no futuro:
--   variavel        -> 'tabela.campo'   ex.: 'participante.data_nascimento'
--   participante    -> participante_id (UUID)
--   submassa_plano  -> nome da submassa ex.: 'Plano A'
--   data_base       -> data ISO         ex.: '2024-12-31'
('data_quality_score', 'referencia_id', 'string', NULL, 'variavel -> tabela.campo; participante -> UUID; submassa_plano -> nome da submassa; data_base -> data ISO', TRUE, 'pipeline_qualidade', 'Tribo 3', 'V3'),
('data_quality_score', 'dimensao_qualidade', 'enum', NULL, 'completude, validade, consistencia, unicidade, acuracia, temporalidade, materialidade', TRUE, 'pipeline_qualidade', 'Tribo 3', 'V3'),
('data_quality_score', 'score', 'decimal', 'proporção', 'DECIMAL(4,3); entre 0 e 1', TRUE, 'pipeline_qualidade', 'Tribo 3', 'V3'),
('data_quality_score', 'data_avaliacao', 'date', 'data', 'ISO 8601; quando a verificação foi executada', TRUE, 'pipeline_qualidade', 'Tribo 3', 'V3'),
('data_quality_score', 'regra_aplicada', 'string', NULL, 'código da regra: R01..R09', TRUE, 'pipeline_qualidade', 'Tribo 3', 'V3'),

-- ---------- 5.2 gabarito.registro_erro_injetado ----------
('gabarito.registro_erro_injetado', 'erro_id', 'uuid', NULL, 'UUID v4', TRUE, 'banco', 'Tribo 3', 'V3'),
('gabarito.registro_erro_injetado', 'tabela_alvo', 'string', NULL, 'participante, evento, exposicao, contribuicao_beneficio', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('gabarito.registro_erro_injetado', 'registro_id', 'string', NULL, 'id de negócio do registro afetado (nunca o staging_id)', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('gabarito.registro_erro_injetado', 'campo_afetado', 'string', NULL, 'nome do campo onde a imperfeição foi introduzida', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('gabarito.registro_erro_injetado', 'tipo_erro', 'enum', NULL, 'idade_invalida, datas_fora_ordem, grafia_divergente, duplicidade, nulo, outlier, orfao, atraso_anomalo, unidade_trocada', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('gabarito.registro_erro_injetado', 'valor_correto_original', 'text', NULL, 'valor antes da injeção; nulo quando o erro não substitui um valor', FALSE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('gabarito.registro_erro_injetado', 'valor_injetado', 'text', NULL, 'valor efetivamente gravado no staging; o token <NULL> significa que a imperfeição injetada foi a ausência do valor', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('gabarito.registro_erro_injetado', 'detectado_pela_limpeza', 'bool', NULL, 'true/false preenchido pelo pipeline; nulo = ainda não avaliado', FALSE, 'pipeline_qualidade', 'Tribo 3', 'V3'),

-- ---------- staging (colunas de controle, comuns às 4 tabelas) ----------
('staging', 'staging_id', 'uuid', NULL, 'UUID v4; PK da linha de entrada', TRUE, 'banco', 'Tribo 3', 'V3'),
('staging', 'lote_id', 'uuid', NULL, 'UUID v4; identifica uma execução do gerador', TRUE, 'gerador_sintetico_v1', 'Tribo 3', 'V3'),
('staging', 'ingerido_em', 'timestamp', 'timestamp', 'ISO 8601 com timezone', TRUE, 'banco', 'Tribo 3', 'V3'),
('staging', 'promovido', 'bool', NULL, 'true depois que o pipeline copiou a linha para a tabela final', TRUE, 'pipeline_qualidade', 'Tribo 3', 'V3'),
('staging', 'motivos_rejeicao', 'text', NULL, 'array de códigos de regra que barraram a linha (R01..R99)', FALSE, 'pipeline_qualidade', 'Tribo 3', 'V3');

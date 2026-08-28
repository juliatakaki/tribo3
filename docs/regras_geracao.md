# Regras de geração — massa sintética v1

## Parâmetros desta rodada

- Script: `gerar_dataset.py`
- Volume: 300 participantes (`--n-participantes 300`)
- Seed: 42 (`--seed 42`) — mesma seed reproduz o mesmo dataset
- Biblioteca: Faker (locale pt_BR) + `random.Random` para amostragem ponderada

## Distribuições usadas

- **plano_tipo**: uniforme entre BD, CD, CV
- **submassa**: uniforme entre "Plano A", "Plano B", "Plano C"
- **sexo**: uniforme M/F
- **status_atual**: ativo 55%, aposentado 20%, desligado 15%, óbito 5%, pensionista 5%
- **data_nascimento**: idade entre 20 e 70 anos na data de geração
- **data_ingresso**: entre os 18 anos do participante e 30 dias atrás
- **status_pagamento** (contribuições): em dia 80%, atraso 15%, quitado 5%

## Regras derivadas (não amostradas diretamente)

- `evento` só é gerado para participantes com status diferente de "ativo", mapeando status → tipo_evento (aposentado→aposentadoria, desligado→desligamento, óbito→óbito, pensionista→invalidez como simplificação).
- `exposicao` gera uma linha por ano civil entre o ingresso e o desligamento (ou hoje, se ainda ativo).
- `contribuicao_beneficio` gera até 6 meses de competência antes do fim do vínculo (ou hoje).

## Injeção de imperfeições (seção 5.1 do documento)

- Taxa: 5% dos participantes recebem alguma imperfeição.
- Tipos implementados nesta rodada: `idade_invalida`, `grafia_divergente`, `nulo`, `outlier`.
- Tipos pendentes de implementação (afetam mais de uma tabela, exigem lógica própria): `duplicidade`, `orfao`, `atraso_anomalo`, `unidade_trocada`.
- Cada imperfeição injetada é registrada em `gabarito.registro_erro_injetado` com valor original e valor injetado, antes da inserção no dado de trabalho.

## Limitações conhecidas desta primeira rodada

- `exposicao` e `contribuicao_beneficio` usam lógica simplificada (não cobrem todos os casos de transição de status no meio do ano).
- Apenas um snapshot por participante (`versao_registro = 1`) — retificações bitemporais ainda não são simuladas.
- 4 dos 8 tipos de imperfeição da seção 5.1 ainda não estão implementados.

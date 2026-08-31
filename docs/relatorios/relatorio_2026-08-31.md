# Relatório de qualidade — 2026-08-31

## 1. Detecção de imperfeições (recall por tipo)

Compara o que foi injetado de propósito (`gabarito.registro_erro_injetado`)
com o que as 9 regras automatizadas detectaram.

| tipo de erro | injetados | detectados | recall |
|---|---|---|---|
| idade_invalida | 2 | 2 | 100% |
| duplicidade | 4 | 4 | 100% |
| grafia_divergente | 1 | 1 | 100% |
| nulo | 3 | 3 | 100% |
| outlier | 2 | 2 | 100% |
| orfao | 1 | 1 | 100% |
| atraso_anomalo | 1 | 1 | 100% |
| unidade_trocada | 1 | 1 | 100% |
| datas_fora_ordem | 4 | 4 | 100% |

## 2. Data Quality Score médio por dimensão e granularidade

| granularidade | dimensão | score médio | nº avaliações |
|---|---|---|---|
| variavel | completude | 1.000 | 29 |
| variavel | validade | 0.997 | 2 |
| variavel | consistencia | 0.994 | 9 |
| variavel | unicidade | 0.987 | 1 |
| variavel | acuracia | 1.000 | 2 |
| variavel | temporalidade | 0.997 | 2 |
| variavel | materialidade | 1.000 | 2 |
| participante | completude | 1.000 | 303 |
| participante | validade | 0.998 | 302 |
| participante | consistencia | 0.997 | 904 |
| participante | unicidade | 0.987 | 302 |
| participante | acuracia | 0.999 | 300 |
| participante | temporalidade | 0.998 | 303 |
| participante | materialidade | 1.000 | 302 |
| submassa_plano | completude | 1.000 | 5 |
| submassa_plano | validade | 1.000 | 4 |
| submassa_plano | consistencia | 0.883 | 13 |
| submassa_plano | unicidade | 0.990 | 4 |
| submassa_plano | acuracia | 1.000 | 4 |
| submassa_plano | temporalidade | 0.998 | 5 |
| submassa_plano | materialidade | 1.000 | 4 |
| data_base | completude | 1.000 | 51 |
| data_base | validade | 1.000 | 51 |
| data_base | consistencia | 0.999 | 149 |
| data_base | unicidade | 0.995 | 47 |
| data_base | acuracia | 1.000 | 24 |
| data_base | temporalidade | 0.997 | 47 |
| data_base | materialidade | 1.000 | 47 |

## 3. Tratamento de exceções

Total de linhas rejeitadas nesta rodada (não promovidas para as 
tabelas finais): **75**.

Rejeitadas por tabela e motivo:

| tabela | motivo (código da regra) | ocorrências |
|---|---|---|
| contribuicao_beneficio | R99_pai_rejeitado | 27 |
| evento | R07_orfao | 1 |
| evento | R99_pai_rejeitado | 2 |
| exposicao | R99_pai_rejeitado | 38 |
| participante | R01_idade_invalida | 2 |
| participante | R04_duplicidade | 2 |
| participante | R05_nulo | 3 |

## Notas

- Este relatório cobre recall (detecção) e tratamento de exceções,
  lidos do estado persistido no banco. Não recalcula falsos
  positivos/precisão — isso é impresso no console ao rodar
  `pipeline_qualidade.py` diretamente.
- Rodar de novo após qualquer nova execução do gerador ou do
  pipeline para atualizar os números.
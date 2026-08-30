# Regras de geração e de qualidade — massa sintética v1

Declaração explícita do que o gerador reproduz, exigida pelo §6 do
documento de referência ("o gerador deve declarar explicitamente quais
distribuições, dependências, eventos raros e inconsistências
intencionais reproduz").

## Parâmetros da rodada padrão

| Parâmetro | Valor | Onde muda |
| --- | --- | --- |
| Volume | 300 participantes | `N_PARTICIPANTES` no `.env` |
| Seed | 42 | `SEED` no `.env` |
| Data de referência | data de hoje | `DATA_REFERENCIA` no `.env` (AAAA-MM-DD) |
| Biblioteca | Faker (pt_BR) + `random.Random` | — |

**Reprodutibilidade (§6):** mesma `SEED` + mesma `DATA_REFERENCIA` = dataset
idêntico, ids inclusive. Os UUIDs saem de `dominio.novo_uuid(rng)`, e não de
`uuid.uuid4()`, justamente porque `uuid4` ignora a seed. Se `DATA_REFERENCIA`
ficar vazia o gerador usa a data de hoje — reproduzir um lote antigo exige
fixá-la.

## Distribuições amostradas

- **plano_tipo**: uniforme entre BD, CD, CV
- **submassa**: uniforme entre "Plano A", "Plano B", "Plano C"
- **sexo**: uniforme M/F
- **status_atual**: ativo 55%, aposentado 20%, desligado 15%, óbito 5%, pensionista 5%
- **data_nascimento**: idade entre 20 e 70 anos na data de referência
- **data_ingresso**: entre os 18 anos do participante e 30 dias antes da data de referência
- **cpf_sintetico**: `Faker.cpf()` — sintético, nunca CPF real
- **valor_contribuicao**: uniforme entre R$ 200 e R$ 2.500
- **valor_beneficio**: uniforme entre R$ 1.000 e R$ 5.000, só para aposentado/pensionista
- **status_pagamento**: em dia 80%, atraso 15%, quitado 5%

## Dependências entre entidades (não amostradas)

- `evento` só existe para quem não é "ativo". Mapa status → tipo_evento:
  aposentado→aposentadoria, desligado→desligamento, óbito→óbito,
  pensionista→invalidez (simplificação).
- **`data_desligamento` só é preenchida para `desligado` e `obito`.** Aposentar
  não é desligar: o §3.1 define o campo como "preenchida se houver
  desligamento", e preenchê-lo para aposentados truncaria a exposição ao risco
  e enviesaria o qx para baixo.
- `exposicao`: uma linha por ano civil entre o ingresso e o fim da exposição.
  O fim é o desligamento/óbito para quem sai, e a data de referência para quem
  permanece no plano — inclusive aposentados e pensionistas, que continuam
  expostos ao risco de morte.
- `idade_exata` é calculada de fato — `(data_base - data_nascimento) / 365.25`.
- `contribuicao_beneficio`: até 6 competências mensais antes do fim do vínculo.
- Um snapshot por participante (`versao_registro = 1`). Retificação bitemporal
  não é simulada nesta rodada — o schema suporta, o gerador não exercita.

## Imperfeições injetadas (§5.1)

5% dos participantes recebem uma imperfeição, com uma garantia adicional: a
primeira rodada percorre os 9 tipos uma vez cada. Com sorteio puro e poucos
alvos, algum tipo sairia com zero injeções e o precision/recall dele viraria
NaN no relatório.

| # | Tipo | O que é injetado | Tabela | Dimensão (§3.7) | Regra |
| --- | --- | --- | --- | --- | --- |
| 1 | `idade_invalida` | data_nascimento 140 anos atrás (idade > 130) | participante | validade | R01 |
| 2 | `datas_fora_ordem` | desligamento 400 dias antes do ingresso, e o evento junto | participante + evento | consistência | R02 |
| 3 | `grafia_divergente` | "Plano A" → "PLANO_A" / "plano a" / "P. A" | participante | consistência | R03 |
| 4 | `duplicidade` | mesmo CPF sintético em dois participante_id | participante | unicidade | R04 |
| 5 | `nulo` | data_nascimento ausente (SQL NULL) | participante | completude | R05 |
| 6 | `outlier` | contribuição negativa ou benefício absurdo | contribuicao_beneficio | acurácia | R06 |
| 7 | `orfao` | evento apontando para participante_id inexistente | evento | consistência | R07 |
| 8 | `atraso_anomalo` | data_conhecimento > 1 ano após data_evento | evento | temporalidade | R08 |
| 9 | `unidade_trocada` | valor em centavos, ou data em DD/MM/AAAA | contribuicao / participante | materialidade | R09 |

Notas de fidelidade ao documento:

- O §5.1 chama a dimensão do tipo 7 de "integridade referencial", mas o enum
  `dimensao_qualidade_enum` do §3.7 não tem esse valor. Mapeado para
  `consistencia`, o mais próximo dentro do conjunto fechado do documento.
- Duplicidade é modelada por CPF, não por `participante_id`: V1 tem
  `UNIQUE (participante_id, versao_registro)`, e duplicar o id derrubaria a
  promoção inteira em vez de exercitar a regra.
- `valor_injetado` é NOT NULL no gabarito, então a injeção de ausência é
  registrada com o token `<NULL>`. No dado de trabalho o campo fica NULL de
  verdade.

## As 9 regras de qualidade

O escopo exige no mínimo 5; há uma por tipo injetado, porque um tipo sem
detector apareceria como falso negativo permanente e tornaria o recall
ininterpretável.

**Rejeitam a linha** (violação dura): R01 idade fora de faixa, R04 duplicidade,
R05 campo obrigatório ausente, R07 órfão — mais falha de cast, valor fora do
domínio de um enum e valor que estouraria o DECIMAL da coluna.

**Só reduzem o score** (a linha é promovida assim mesmo): R02, R03, R06, R08,
R09. Rejeitar tudo deixaria as tabelas finais limpas demais e o dataset
perderia a função descrita no §5.

**Tratamento aplicado na promoção:** R03 normaliza a grafia da submassa para a
forma canônica; R09 converte a data não-ISO para ISO. Valor em centavos é
sinalizado mas **não** corrigido automaticamente — não há como distinguir com
segurança um valor em centavos de um valor legitimamente alto.

**Cascata:** se um participante é rejeitado, seus eventos/exposições/
contribuições também são, com o motivo `R99_pai_rejeitado`. Sem isso eles
virariam órfãos que ninguém injetou, poluindo a precisão da R07.

## Convenção do `data_quality_score.referencia_id`

O campo é livre (`VARCHAR(200)`). Sem convenção fixa a tabela fica ilegível em
poucas semanas:

| Granularidade | Formato | Exemplo |
| --- | --- | --- |
| `variavel` | `tabela.campo` | `participante.data_nascimento` |
| `participante` | UUID do participante | `9f3c…` |
| `submassa_plano` | nome da submassa | `Plano A` |
| `data_base` | data ISO (fim do ano civil) | `2024-12-31` |

O score é sempre `1 - violações/avaliadas` dentro do grupo. As regras devolvem
células (registro × campo), o que permite derivar as 4 granularidades do §3.7
com um agregador só.

## Limitações conhecidas

- Retificação bitemporal não é simulada (um snapshot por participante).
- `referencia_externa` tem só o esqueleto das 4 fontes do §1; `versao_tabua`,
  `data_consulta` e `resultado_benchmark` ficam nulos até alguém de fato baixar
  a tábua e rodar o benchmark.
- Tábua biométrica (qx/lx/dx com intervalos de confiança, §2) está fora desta
  rodada.
- O precision/recall dá 1.00 em todos os tipos porque a base sintética é limpa
  fora do que se injeta e as regras foram desenhadas para não se sobrepor. Isso
  mede que o pipeline pega exatamente o que foi plantado — **não** prevê o
  desempenho dele numa base real.
- `dicionario_dados.responsavel` está preenchido com "Tribo 3" em todos os
  campos; trocar pela dupla responsável quando o time definir.

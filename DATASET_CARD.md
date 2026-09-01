# Data Card — Massa Sintética Tribo 3

## Propósito

Massa de dados previdenciária inteiramente sintética, criada para testar
um pipeline de qualidade de dados (curadoria, detecção de imperfeições,
scoring) antes de aplicá-lo a dados reais. Não representa nenhuma
população ou fundo de previdência real — todos os participantes, CPFs,
eventos e valores são gerados por algoritmo.

## Escopo

- **Cobre**: participantes, eventos de carreira/saída, exposição ao
  risco (base para cálculo atuarial de mortalidade) e contribuições/
  benefícios, de um plano de previdência complementar fictício com 3
  submassas (Plano A, Plano B, Plano C) e 3 tipos de plano (BD, CD, CV).
- **Não cobre**: dados de nenhuma entidade real, nenhum CPF real (o
  campo `cpf_sintetico` nunca corresponde a documento real), nenhum
  valor monetário com relação a moeda real além da unidade (BRL nominal).
- **Uso pretendido**: exercitar e validar as regras de qualidade e o
  cálculo do Data Quality Score, não para análise atuarial de verdade.

## Processo de geração

1. `gerar_dataset.py` gera participantes, eventos, exposição e
   contribuições em memória, com seed fixa, e escreve tudo no schema
   `staging` (colunas `TEXT`, sem validação de tipo ainda).
2. Nesse mesmo passo, injeta imperfeições propositais em uma fração dos
   registros (9 tipos, um por dimensão de qualidade — ver
   `docs/regras_geracao.md`), registrando cada uma em
   `gabarito.registro_erro_injetado` com valor original e valor
   injetado.
3. `pipeline_qualidade.py` lê o staging, aplica as 9 regras automatizadas
   (`scripts/regras.py`), grava o Data Quality Score por variável,
   participante, submassa/plano e data-base, promove as linhas aprovadas
   para as tabelas tipadas (`participante`, `evento`, `exposicao`,
   `contribuicao_beneficio`) e marca no gabarito quais imperfeições foram
   detectadas.
4. Todo o processo é reprodutível: mesma seed produz o mesmo dataset,
   IDs incluídos (UUIDs derivados do gerador seedado, não aleatórios de
   sistema).

Parâmetros e distribuições usados: ver `docs/regras_geracao.md`.

## Volume e período

- Volume desta rodada: 300 participantes sintéticos (parâmetro
  `N_PARTICIPANTES`, ajustável).
- Período coberto: datas de nascimento, ingresso e eventos são gerados
  em torno da data de referência da execução (`DATA_REFERENCIA`, padrão
  hoje) — não representa um recorte histórico fixo, mas uma massa
  "atual" a cada nova geração.

## Limitações conhecidas

- `exposicao` e `contribuicao_beneficio` usam lógica simplificada (uma
  linha por ano civil / até 6 meses de competência), não cobrem todas as
  transições possíveis de status no meio do ano.
- Campo `responsavel` no dicionário de dados está com valor genérico
  ("Tribo 3") — pendente de atribuição por pessoa/dupla.
- O relatório de qualidade com precision/recall completo é impresso no
  console pelo `pipeline_qualidade.py`; a versão persistida em arquivo
  (`docs/relatorios/`) cobre recall e tratamento de exceções, mas não
  recalcula falsos positivos sem rodar o pipeline de novo.
- Apenas um snapshot por participante nesta rodada (`versao_registro =
  1`) — retificação bitemporal (corrigir um snapshot antigo mantendo
  histórico) ainda não é exercitada pelo gerador.
- O benchmark contra a IBGE (`referencia_externa`, fonte IBGE) acusa
  desvio de ordem de grandeza na faixa 0-19 anos — não é erro de
  geração: o gerador só cria participantes a partir da maioridade
  (`data_ingresso` calculado a partir dos 18 anos), então não existe
  exposição nem óbito sintético nessa faixa para comparar com a
  mortalidade infantil/juvenil real da IBGE. A faixa 70+ não tem dado
  suficiente pelo mesmo motivo de escala (poucos idosos avançados numa
  amostra de 300).
- O benchmark contra o HMD (fonte HMD, referência Austrália 2021,
  período não coberto pelo país Brasil na base) mostra desvio maior
  ainda na faixa 20-29 (até ~49x em mulheres) que na comparação com a
  IBGE. Duas causas prováveis, não isoladas uma da outra: (1)
  mortalidade real na Austrália é bem mais baixa que no Brasil nessa
  faixa, diferença esperada entre os países; (2) com ~300 participantes
  divididos por sexo e faixa etária, a célula "mulheres 20-29" tem
  exposição pequena, então poucos óbitos já mudam bastante a proporção.
  Não dá para separar as duas causas sem examinar o n exato de cada
  célula.

## Changelog de versões do schema

- **V1** — schema inicial: 8 entidades (participante, evento, exposicao,
  contribuicao_beneficio, referencia_externa, dicionario_dados,
  data_quality_score, gabarito.registro_erro_injetado).
- **V2** — adiciona o 9º tipo de imperfeição (`datas_fora_ordem`) ao
  enum de tipos de erro.
- **V3** — adiciona `cpf_sintetico` a `participante`; cria o schema
  `staging` (área de entrada + log de rejeição); torna
  `data_quality_score` idempotente (`ON CONFLICT`); relaxa
  `referencia_externa` para aceitar fontes ainda não consultadas.
- **R\_\_dicionario_dados** / **R\_\_referencia_externa** — migrations
  repetíveis, reaplicadas sempre que o conteúdo muda.

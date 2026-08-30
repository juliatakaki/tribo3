# Tribo 3 — Ambiente de dados (Postgres + migrations + massa sintética)

Implementa o documento *"Desenho do Banco de Dados de Referência (Massa
Sintética)"*: schema bitemporal, gerador de massa sintética com imperfeições
controladas, pipeline de qualidade e gabarito para medir precision/recall da
limpeza.

## Estrutura

```text
tribo3/
  docker-compose.yml
  .env.example
  migrations/
    V1__schema_inicial.sql           7 tabelas do §3 + gabarito do §5.2
    V2__enum_datas_fora_ordem.sql    9º tipo de imperfeição do §5.1
    V3__staging_cpf_e_constraints.sql camada staging + cpf_sintetico
    R__dicionario_dados.sql          catálogo do §3.6 (repeatable)
    R__referencia_externa.sql        as 4 fontes do §1 (repeatable)
  scripts/
    gerar_dataset.py       gera a massa e escreve no staging
    injetores.py           os 9 tipos de imperfeição do §5.1
    regras.py              as 9 regras de qualidade
    pipeline_qualidade.py  valida, pontua, promove e mede precision/recall
    seed.py                orquestrador idempotente do compose
    dominio.py             domínios e limiares compartilhados
    db.py                  conexão
  docs/
    regras_geracao.md      data card: distribuições, imperfeições, regras
```

## Primeira vez

```bash
git clone <repo>
cd tribo3
cp .env.example .env
docker compose up -d
```

Isso sobe quatro serviços:

- **db** — Postgres 16, dados em volume Docker (não some ao reiniciar).
- **migrate** — Flyway, aplica `migrations/` em ordem. Roda uma vez e sai.
- **seed** — gera a massa sintética, roda o pipeline de qualidade e promove os
  dados. Roda uma vez e sai. **Idempotente**: se já houver dados, não faz nada.
- **pgadmin** — interface web em `http://localhost:5050`, credenciais do `.env`.

Ao terminar, o banco já está populado: staging preenchido, imperfeições
injetadas, scores calculados e as tabelas finais promovidas.

```bash
docker compose logs seed   # relatório de precision/recall por tipo de erro
```

## O que fica no banco

| Tabela | Conteúdo |
| --- | --- |
| `participante`, `evento`, `exposicao`, `contribuicao_beneficio` | dataset de análise, já curado |
| `staging.*` | entrada crua, com as imperfeições e o motivo de cada rejeição |
| `staging.v_rejeitados` | tudo que não foi promovido, com os códigos de regra |
| `data_quality_score` | scores nas 4 granularidades do §3.7 |
| `dicionario_dados` | catálogo do §3.6 |
| `gabarito.registro_erro_injetado` | erros plantados + se a limpeza pegou |
| `referencia_externa` | esqueleto das 4 fontes do §1, aguardando benchmark |

`referencia_externa` sai com `versao_tabua`, `data_consulta` e
`resultado_benchmark` nulos de propósito: eles só existem depois que alguém
baixar a tábua do IBGE/BR-EMS e rodar a comparação. Ela nunca é fonte de linhas
do dataset de entrada (§4).

## Conferir

```bash
# migrations aplicadas
docker compose logs migrate

# todo erro injetado foi avaliado (nao_avaliado deve ser 0)
docker compose exec db psql -U tribo3 -d tribo3 -c "
  SELECT tipo_erro, count(*) total,
         count(*) FILTER (WHERE detectado_pela_limpeza) detectados,
         count(*) FILTER (WHERE detectado_pela_limpeza IS NULL) nao_avaliado
  FROM gabarito.registro_erro_injetado GROUP BY 1 ORDER BY 1;"

# por que cada linha foi rejeitada
docker compose exec db psql -U tribo3 -d tribo3 -c "
  SELECT tabela_origem, unnest(motivos_rejeicao) motivo, count(*)
  FROM staging.v_rejeitados GROUP BY 1,2 ORDER BY 3 DESC;"
```

## Repopular do zero

```bash
docker compose down -v && docker compose up -d
```

`down -v` apaga o volume; sem o `-v` os dados ficam e o `seed` continua pulando.

## Rodar os scripts fora do container

```bash
pip install -r scripts/requirements.txt
cd scripts
python gerar_dataset.py --n-participantes 300 --seed 42
python pipeline_qualidade.py
```

Os defaults de conexão apontam para `localhost:5433` (a porta que o compose
publica no host). Ajuste via `PGHOST`/`PGPORT` se mudar o `.env`.

## Volume, seed e reprodutibilidade

`N_PARTICIPANTES`, `SEED` e `DATA_REFERENCIA` vêm do `.env`. Mesma `SEED` +
mesma `DATA_REFERENCIA` produz um dataset idêntico, ids inclusive (§6). Com
`DATA_REFERENCIA` vazia o gerador usa a data de hoje — para reproduzir um lote
antigo, fixe a data.

## Mudar o schema

1. Nunca editar uma migration `V*` já aplicada — o Flyway valida checksum e
   falha.
2. Criar `migrations/V4__descricao_curta.sql`.
3. As `R__*.sql` (dicionário, referência externa) são *repeatable*: pode editar
   à vontade, o Flyway reaplica quando o conteúdo muda.
4. `docker compose up -d migrate`.

## Derrubar

```bash
docker compose down          # para os containers, mantém os dados
docker compose down -v       # para e APAGA os dados
```

## Próximo passo

Tábua biométrica própria (exposição, qx, lx, dx e intervalos de confiança,
§2) sobre a tabela `exposicao` já promovida.

# Tribo 3 — Ambiente de dados (Postgres + migrations)

## Estrutura de pastas esperada

```
tribo3/
  docker-compose.yml
  .env.example
  migrations/
    V1__schema_inicial.sql
  scripts/
    (scripts de geração de dados, virão na Fase 2)
```

Baixe `V1__schema_inicial.sql` (mandado antes) e coloque dentro de uma
pasta `migrations/` na raiz do projeto. Os arquivos `docker-compose.yml`
e `.env.example` ficam na raiz.

## Primeira vez (qualquer pessoa do time)

```bash
git clone <repo>
cd tribo3
cp .env.example .env
docker compose up -d
```

Isso sobe três serviços:

- **db** — Postgres 16, dados persistidos em volume Docker (não some ao
  reiniciar o container).
- **migrate** — roda o Flyway, aplica as migrations de `migrations/` em
  ordem (`V1__`, `V2__`, ...). Roda uma vez e sai; conferir o log com
  `docker compose logs migrate`.
- **pgadmin** — interface web em `http://localhost:5050` pra quem quiser
  inspecionar as tabelas sem instalar client nenhum. Login com as
  credenciais do `.env` (`PGADMIN_EMAIL` / `PGADMIN_PASSWORD`).

## Conferir se aplicou certo

```bash
docker compose logs migrate
```

Deve aparecer `Successfully applied 1 migration`. Se rodar de novo com
o banco já migrado, o Flyway não reaplica — só confirma que está em dia.

## Conectar direto via psql (opcional)

```bash
docker compose exec db psql -U tribo3 -d tribo3 -c "\dt"
```

Lista as tabelas criadas.

## Quando alguém do time mudar o schema

1. Nunca editar `V1__schema_inicial.sql` depois que já foi aplicado por
   alguém.
2. Criar `migrations/V2__descricao_curta.sql` com o `ALTER TABLE` ou
   `CREATE TABLE` novo.
3. Commitar o arquivo novo e avisar o time pra rodar:
   ```bash
   docker compose up -d migrate
   ```
   Isso reaplica só a migration nova em todo mundo que der pull.

## Derrubar o ambiente

```bash
docker compose down          # para os containers, mantém os dados
docker compose down -v       # para e APAGA os dados (cuidado)
```

## Próximo passo

Script de geração da massa sintética (Fase 2 do guia de dados e
qualidade) vai rodar como um serviço adicional neste mesmo compose,
lendo as tabelas já criadas pelas migrations.

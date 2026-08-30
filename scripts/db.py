"""Conexão com o banco, compartilhada por gerar_dataset, pipeline_qualidade e seed."""

import os
import time

import psycopg2


def conectar():
    """Abre conexão usando as variáveis de ambiente do .env.

    O default de porta é 5433 porque é isso que o docker-compose publica
    no host (5432 costuma estar ocupada por outro Postgres local). Dentro
    do compose o serviço `seed` sobrescreve com PGHOST=db / PGPORT=5432.
    """
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5433"),
        dbname=os.environ.get("POSTGRES_DB", "tribo3"),
        user=os.environ.get("POSTGRES_USER", "tribo3"),
        password=os.environ.get("POSTGRES_PASSWORD", "tribo3_dev"),
    )


def conectar_esperando_migrations(tentativas=30, intervalo=2):
    """Conecta e espera as migrations terminarem antes de devolver a conexão.

    O compose já declara `condition: service_completed_successfully` no
    migrate, mas isso só vale no Docker Compose v2 — na v1 o depends_on
    não espera o Flyway sair. A espera aqui torna o seed correto nas duas
    versões, sem depender de qual binário a pessoa tem instalado.
    """
    ultimo_erro = None
    for _ in range(tentativas):
        try:
            conn = conectar()
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('staging.participante')")
                if cur.fetchone()[0] is not None:
                    return conn
            conn.close()
            ultimo_erro = "migrations ainda não aplicadas"
        except psycopg2.OperationalError as erro:
            ultimo_erro = erro
        time.sleep(intervalo)
    raise RuntimeError(f"banco não ficou pronto a tempo: {ultimo_erro}")


def tem_linhas(cur, tabela):
    """True se a tabela tiver pelo menos uma linha. Base dos guards de idempotência."""
    cur.execute(f"SELECT 1 FROM {tabela} LIMIT 1")
    return cur.fetchone() is not None

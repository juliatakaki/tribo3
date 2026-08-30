"""
Orquestrador do `docker compose up`: gera a massa e roda o pipeline.

Idempotente por design — o compose executa este serviço em todo `up`, e
subir o ambiente duas vezes não pode duplicar o dataset.

Os dois guards são independentes de propósito: se a geração tiver rodado
e o pipeline tiver quebrado, o `up` seguinte roda só o que faltou.

Para repopular do zero: docker compose down -v && docker compose up -d
"""

import os
import sys

import gerar_dataset
import pipeline_qualidade
from db import conectar_esperando_migrations, tem_linhas


def main():
    n_participantes = os.environ.get("N_PARTICIPANTES", "300")
    seed = os.environ.get("SEED", "42")
    # Sem DATA_REFERENCIA o gerador usa a data de hoje, e o mesmo SEED
    # produziria datasets diferentes em dias diferentes. Fixe a variável
    # para reproduzir um lote antigo exatamente (§6).
    data_referencia = os.environ.get("DATA_REFERENCIA", "")

    conn = conectar_esperando_migrations()
    cur = conn.cursor()
    ja_gerado = tem_linhas(cur, "staging.participante")
    ja_avaliado = tem_linhas(cur, "data_quality_score")
    cur.close()
    conn.close()

    if ja_gerado:
        print("staging.participante já tem dados — geração pulada.")
    else:
        sys.argv = ["gerar_dataset.py",
                    "--n-participantes", n_participantes,
                    "--seed", seed]
        if data_referencia:
            sys.argv += ["--data-referencia", data_referencia]
        gerar_dataset.main()

    if ja_avaliado:
        print("data_quality_score já tem dados — pipeline de qualidade pulado.")
    else:
        pipeline_qualidade.main()


if __name__ == "__main__":
    main()

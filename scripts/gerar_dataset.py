"""
Gerador de massa sintética — Tribo 3
Fase 2: gera participantes, eventos, exposição e contribuições/benefícios,
injeta imperfeições controladas (seção 5.1 do documento) e registra o
gabarito em gabarito.registro_erro_injetado.

Uso:
    python gerar_dataset.py --n-participantes 300 --seed 42

Requisitos: pip install -r requirements.txt
Espera o banco já migrado (V1__schema_inicial.sql aplicado).
"""

import argparse
import os
import random
import uuid
from datetime import date, timedelta

import psycopg2
import psycopg2.extras
from faker import Faker

# ---------- domínios fixos (batem com os enums do V1) ----------

PLANO_TIPOS = ["BD", "CD", "CV"]
SUBMASSAS = ["Plano A", "Plano B", "Plano C"]
STATUS_PESOS = [
    ("ativo", 0.55),
    ("aposentado", 0.20),
    ("desligado", 0.15),
    ("obito", 0.05),
    ("pensionista", 0.05),
]
STATUS_PARA_EVENTO = {
    "obito": "obito",
    "aposentado": "aposentacao" if False else "aposentadoria",
    "desligado": "desligamento",
    "pensionista": "invalidez",  # simplificação: pensionista via invalidez
}
TAXA_INJECAO = 0.05  # % de participantes que recebem alguma imperfeição
TIPOS_ERRO = [
    "idade_invalida", "duplicidade", "grafia_divergente", "nulo",
    "outlier", "orfao", "atraso_anomalo", "unidade_trocada",
]


def escolher_status(rng):
    valores = [v for v, _ in STATUS_PESOS]
    pesos = [p for _, p in STATUS_PESOS]
    return rng.choices(valores, weights=pesos, k=1)[0]


def gerar_participante(fake, rng):
    nascimento = fake.date_of_birth(minimum_age=20, maximum_age=70)
    ingresso = fake.date_between(start_date=nascimento + timedelta(days=18 * 365), end_date="-30d")
    status = escolher_status(rng)
    desligamento = None
    if status in ("desligado", "aposentado", "obito", "pensionista"):
        desligamento = fake.date_between(start_date=ingresso, end_date="today")

    return {
        "participante_id": str(uuid.uuid4()),
        "plano_tipo": rng.choice(PLANO_TIPOS),
        "submassa": rng.choice(SUBMASSAS),
        "sexo": rng.choice(["M", "F"]),
        "data_nascimento": nascimento,
        "data_ingresso": ingresso,
        "data_desligamento": desligamento,
        "status_atual": status,
        "data_evento_conhecimento": ingresso + timedelta(days=rng.randint(1, 5)),
        "data_vigencia_inicio": ingresso,
        "data_vigencia_fim": None,
        "versao_registro": 1,
    }


def gerar_evento(participante, fake, rng):
    tipo = STATUS_PARA_EVENTO.get(participante["status_atual"])
    if tipo is None or participante["data_desligamento"] is None:
        return None
    data_evento = participante["data_desligamento"]
    return {
        "evento_id": str(uuid.uuid4()),
        "participante_id": participante["participante_id"],
        "tipo_evento": tipo,
        "data_evento": data_evento,
        "data_conhecimento": data_evento + timedelta(days=rng.randint(1, 10)),
        "fonte": "gerador_sintetico_v1",
    }


def gerar_exposicao(participante, rng):
    linhas = []
    fim = participante["data_desligamento"] or date.today()
    ano_inicio = participante["data_ingresso"].year
    ano_fim = fim.year
    for ano in range(ano_inicio, ano_fim + 1):
        idade = ano - participante["data_nascimento"].year
        ultimo_ano = ano == ano_fim
        tipo_saida = "censura"
        if ultimo_ano and participante["status_atual"] == "obito":
            tipo_saida = "obito"
        elif ultimo_ano and participante["status_atual"] in ("desligado",):
            tipo_saida = "saida_estudo"
        linhas.append({
            "exposicao_id": str(uuid.uuid4()),
            "participante_id": participante["participante_id"],
            "submassa": participante["submassa"],
            "idade_exata": round(idade + rng.random(), 3),
            "ano_calendario": ano,
            "tempo_exposto": round(rng.uniform(0.5, 1.0), 5) if ultimo_ano else 1.0,
            "tipo_saida": tipo_saida,
            "data_base": date(ano, 12, 31) if not ultimo_ano else fim,
        })
    return linhas


def gerar_contribuicoes(participante, rng):
    linhas = []
    fim = participante["data_desligamento"] or date.today()
    meses = min(6, max(1, (fim.year - participante["data_ingresso"].year) * 12 + 1))
    competencia = date(fim.year, fim.month, 1)
    for i in range(meses):
        mes = competencia.month - i
        ano = competencia.year
        while mes <= 0:
            mes += 12
            ano -= 1
        linhas.append({
            "id": str(uuid.uuid4()),
            "participante_id": participante["participante_id"],
            "competencia": date(ano, mes, 1),
            "valor_contribuicao": round(rng.uniform(200, 2500), 2),
            "valor_beneficio": round(rng.uniform(1000, 5000), 2) if participante["status_atual"] in ("aposentado", "pensionista") else None,
            "status_pagamento": rng.choices(["em_dia", "atraso", "quitado"], weights=[0.8, 0.15, 0.05], k=1)[0],
        })
    return linhas


def injetar_imperfeicao(participante, rng):
    """Corrompe UM campo do participante e devolve o registro de gabarito.
    Não mexe no dict original passado — devolve um dict novo."""
    tipo = rng.choice(TIPOS_ERRO)
    corrompido = dict(participante)
    campo = None
    original = None
    injetado = None

    if tipo == "idade_invalida":
        campo = "data_nascimento"
        original = str(participante["data_nascimento"])
        corrompido["data_nascimento"] = date(1880, 1, 1)  # idade > 130
        injetado = str(corrompido["data_nascimento"])
    elif tipo == "grafia_divergente":
        campo = "submassa"
        original = participante["submassa"]
        corrompido["submassa"] = original.replace("Plano ", "PLANO_").lower()
        injetado = corrompido["submassa"]
    elif tipo == "nulo":
        campo = "data_ingresso"
        original = str(participante["data_ingresso"])
        # data_ingresso é NOT NULL no schema — simular como valor sentinela
        # até decidirem se esse campo pode aceitar nulo de fato.
        corrompido["data_ingresso"] = participante["data_nascimento"]
        injetado = "valor_sentinela_nao_null"
    elif tipo == "outlier":
        campo = "data_desligamento"
        original = str(participante["data_desligamento"])
        corrompido["data_desligamento"] = participante["data_ingresso"] - timedelta(days=365)
        injetado = str(corrompido["data_desligamento"])
    else:
        # duplicidade, orfao, atraso_anomalo, unidade_trocada tratados fora
        # (afetam mais de uma tabela) — deixados como TODO explícito.
        return participante, None

    gabarito = {
        "tabela_alvo": "participante",
        "registro_id": participante["participante_id"],
        "campo_afetado": campo,
        "tipo_erro": tipo,
        "valor_correto_original": original,
        "valor_injetado": injetado,
    }
    return corrompido, gabarito


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-participantes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    Faker.seed(args.seed)
    rng = random.Random(args.seed)
    fake = Faker("pt_BR")

    participantes, eventos, exposicoes, contribuicoes, gabarito = [], [], [], [], []

    for _ in range(args.n_participantes):
        p = gerar_participante(fake, rng)
        if rng.random() < TAXA_INJECAO:
            p, g = injetar_imperfeicao(p, rng)
            if g:
                gabarito.append(g)
        participantes.append(p)

        ev = gerar_evento(p, fake, rng)
        if ev:
            eventos.append(ev)
        exposicoes.extend(gerar_exposicao(p, rng))
        contribuicoes.extend(gerar_contribuicoes(p, rng))

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "tribo3"),
        user=os.environ.get("POSTGRES_USER", "tribo3"),
        password=os.environ.get("POSTGRES_PASSWORD", "tribo3_dev"),
    )
    cur = conn.cursor()

    psycopg2.extras.execute_values(cur, """
        INSERT INTO participante (participante_id, plano_tipo, submassa, sexo,
            data_nascimento, data_ingresso, data_desligamento, status_atual,
            data_evento_conhecimento, data_vigencia_inicio, data_vigencia_fim,
            versao_registro)
        VALUES %s
    """, [(p["participante_id"], p["plano_tipo"], p["submassa"], p["sexo"],
           p["data_nascimento"], p["data_ingresso"], p["data_desligamento"],
           p["status_atual"], p["data_evento_conhecimento"],
           p["data_vigencia_inicio"], p["data_vigencia_fim"], p["versao_registro"])
          for p in participantes])

    if eventos:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO evento (evento_id, participante_id, tipo_evento,
                data_evento, data_conhecimento, fonte)
            VALUES %s
        """, [(e["evento_id"], e["participante_id"], e["tipo_evento"],
               e["data_evento"], e["data_conhecimento"], e["fonte"])
              for e in eventos])

    if exposicoes:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO exposicao (exposicao_id, participante_id, submassa,
                idade_exata, ano_calendario, tempo_exposto, tipo_saida, data_base)
            VALUES %s
        """, [(x["exposicao_id"], x["participante_id"], x["submassa"],
               x["idade_exata"], x["ano_calendario"], x["tempo_exposto"],
               x["tipo_saida"], x["data_base"]) for x in exposicoes])

    if contribuicoes:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO contribuicao_beneficio (id, participante_id, competencia,
                valor_contribuicao, valor_beneficio, status_pagamento)
            VALUES %s
        """, [(c["id"], c["participante_id"], c["competencia"],
               c["valor_contribuicao"], c["valor_beneficio"], c["status_pagamento"])
              for c in contribuicoes])

    if gabarito:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO gabarito.registro_erro_injetado (erro_id, tabela_alvo,
                registro_id, campo_afetado, tipo_erro, valor_correto_original,
                valor_injetado)
            VALUES %s
        """, [(str(uuid.uuid4()), g["tabela_alvo"], g["registro_id"],
               g["campo_afetado"], g["tipo_erro"], g["valor_correto_original"],
               g["valor_injetado"]) for g in gabarito])

    conn.commit()
    cur.close()
    conn.close()

    print(f"Gerado: {len(participantes)} participantes, {len(eventos)} eventos, "
          f"{len(exposicoes)} linhas de exposição, {len(contribuicoes)} contribuições, "
          f"{len(gabarito)} erros injetados (seed={args.seed}).")


if __name__ == "__main__":
    main()

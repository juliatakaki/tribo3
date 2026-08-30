"""
Gerador de massa sintética — Tribo 3

Gera participantes, eventos, exposição e contribuições/benefícios, injeta
as imperfeições controladas do §5.1 e registra o gabarito em
gabarito.registro_erro_injetado.

O destino é o schema `staging` (todo campo TEXT NULL), não as tabelas
tipadas: é o que permite gravar nulo em campo obrigatório e data em
formato trocado, como o §5.1 exige. Quem promove staging -> tabelas
finais é o pipeline_qualidade.py.

Uso:
    python gerar_dataset.py --n-participantes 300 --seed 42

Mesma seed = mesmo dataset (§6, reprodutibilidade).
"""

import argparse
import random
import uuid
from datetime import date, timedelta

import psycopg2.extras
from faker import Faker

from db import conectar
from dominio import (PLANO_TIPOS, SEXOS, SUBMASSAS, TIPOS_ERRO, novo_uuid,
                     to_text)
from injetores import INJETORES

# ---------- parâmetros de geração (declarados no data card, §6) ----------

STATUS_PESOS = [
    ("ativo", 0.55),
    ("aposentado", 0.20),
    ("desligado", 0.15),
    ("obito", 0.05),
    ("pensionista", 0.05),
]

# Só desligado e óbito encerram o vínculo. Aposentado e pensionista
# continuam no plano — o §3.1 define data_desligamento como "preenchida
# se houver desligamento", e preenchê-la para aposentados truncaria a
# exposição ao risco e enviesaria o qx.
STATUS_QUE_DESLIGAM = ("desligado", "obito")

STATUS_PARA_EVENTO = {
    "obito": "obito",
    "aposentado": "aposentadoria",
    "desligado": "desligamento",
    "pensionista": "invalidez",  # simplificação: pensionista via invalidez
}

TAXA_INJECAO = 0.05  # fração dos participantes que recebe alguma imperfeição
MESES_CONTRIBUICAO = 6

# Data-base do lote. Fica num global porque atravessa quase toda função
# de geração. O §6 exige "mesma seed = mesmo resultado": com date.today()
# implícito, rodar amanhã produziria um dataset diferente com a mesma
# seed, então a data entra como parâmetro explícito (--data-referencia).
DATA_REFERENCIA = date.today()


def escolher_status(rng):
    valores = [v for v, _ in STATUS_PESOS]
    pesos = [p for _, p in STATUS_PESOS]
    return rng.choices(valores, weights=pesos, k=1)[0]


def gerar_participante(fake, rng):
    nascimento = DATA_REFERENCIA - timedelta(days=rng.randint(20, 70) * 365)
    ingresso = fake.date_between_dates(
        date_start=nascimento + timedelta(days=18 * 365),
        date_end=DATA_REFERENCIA - timedelta(days=30),
    )
    status = escolher_status(rng)

    # Data em que o status mudou (para quem não é mais ativo). Vira
    # data_evento e, só para quem de fato desliga, data_desligamento.
    data_mudanca = None
    if status != "ativo":
        data_mudanca = fake.date_between_dates(
            date_start=ingresso, date_end=DATA_REFERENCIA
        )

    return {
        "participante_id": novo_uuid(rng),
        "cpf_sintetico": fake.cpf().replace(".", "").replace("-", ""),
        "plano_tipo": rng.choice(PLANO_TIPOS),
        "submassa": rng.choice(SUBMASSAS),
        "sexo": rng.choice(SEXOS),
        "data_nascimento": nascimento,
        "data_ingresso": ingresso,
        "data_desligamento": data_mudanca if status in STATUS_QUE_DESLIGAM else None,
        "status_atual": status,
        "data_evento_conhecimento": ingresso + timedelta(days=rng.randint(1, 5)),
        "data_vigencia_inicio": ingresso,
        "data_vigencia_fim": None,
        "versao_registro": 1,
        # Campo interno, não persistido: só orienta evento e exposição.
        "_data_mudanca": data_mudanca,
    }


def gerar_evento(participante, rng):
    tipo = STATUS_PARA_EVENTO.get(participante["status_atual"])
    if tipo is None:
        return None
    data_evento = participante["_data_mudanca"]
    return {
        "evento_id": novo_uuid(rng),
        "participante_id": participante["participante_id"],
        "tipo_evento": tipo,
        "data_evento": data_evento,
        "data_conhecimento": data_evento + timedelta(days=rng.randint(1, 10)),
        "fonte": "gerador_sintetico_v1",
    }


def _fim_da_exposicao(participante):
    """Até quando o participante está exposto ao risco.

    Desligamento e óbito encerram; aposentadoria e invalidez não — quem
    se aposenta continua exposto ao risco de morte dentro do plano.
    """
    if participante["status_atual"] in STATUS_QUE_DESLIGAM:
        return participante["data_desligamento"]
    return DATA_REFERENCIA


def gerar_exposicao(participante, rng):
    """Uma linha por ano civil entre o ingresso e o fim da exposição."""
    linhas = []
    inicio = participante["data_ingresso"]
    fim = _fim_da_exposicao(participante)
    nascimento = participante["data_nascimento"]

    for ano in range(inicio.year, fim.year + 1):
        janela_inicio = max(inicio, date(ano, 1, 1))
        janela_fim = min(fim, date(ano, 12, 31))
        if janela_fim < janela_inicio:
            continue
        ultimo_ano = ano == fim.year

        tipo_saida = "censura"
        if ultimo_ano and participante["status_atual"] == "obito":
            tipo_saida = "obito"
        elif ultimo_ano and participante["status_atual"] == "desligado":
            tipo_saida = "saida_estudo"

        # Idade exata na data-base, calculada de fato (não ano - ano).
        idade = (janela_fim - nascimento).days / 365.25
        # +1 porque a janela é inclusiva nas duas pontas.
        tempo = ((janela_fim - janela_inicio).days + 1) / 365.25

        linhas.append({
            "exposicao_id": novo_uuid(rng),
            "participante_id": participante["participante_id"],
            "submassa": participante["submassa"],
            "idade_exata": round(idade, 3),
            "ano_calendario": ano,
            "tempo_exposto": round(min(tempo, 1.0), 5),
            "tipo_saida": tipo_saida,
            "data_base": janela_fim,
        })
    return linhas


def gerar_contribuicoes(participante, rng):
    """Até 6 competências mensais antes do fim do vínculo."""
    linhas = []
    fim = _fim_da_exposicao(participante)
    em_beneficio = participante["status_atual"] in ("aposentado", "pensionista")
    ano, mes = fim.year, fim.month

    for _ in range(MESES_CONTRIBUICAO):
        if date(ano, mes, 1) < participante["data_ingresso"].replace(day=1):
            break
        linhas.append({
            "id": novo_uuid(rng),
            "participante_id": participante["participante_id"],
            "competencia": date(ano, mes, 1),
            "valor_contribuicao": round(rng.uniform(200, 2500), 2),
            "valor_beneficio": round(rng.uniform(1000, 5000), 2) if em_beneficio else None,
            "status_pagamento": rng.choices(
                ["em_dia", "atraso", "quitado"], weights=[0.8, 0.15, 0.05], k=1
            )[0],
        })
        mes -= 1
        if mes == 0:
            mes, ano = 12, ano - 1
    return linhas


def injetar_imperfeicoes(rng, dados, n_alvos):
    """Aplica n_alvos imperfeições entre os 9 tipos do §5.1.

    A primeira rodada percorre os 9 tipos uma vez cada, em ordem
    embaralhada: com sorteio puro e poucos alvos, algum tipo sairia com
    zero injeções e a regra correspondente ficaria sem nada para
    detectar — o precision/recall dele viraria NaN no relatório do §5.2.
    Os alvos restantes são sorteados livremente.

    Quando o tipo escolhido não tem alvo disponível no lote, tenta os
    demais, para que a taxa de injeção declarada valha de fato.
    """
    gabarito = []
    usados = set()

    ordem = rng.sample(TIPOS_ERRO, k=len(TIPOS_ERRO))
    for i in range(max(n_alvos, len(TIPOS_ERRO))):
        if i < len(ordem):
            preferidos = [ordem[i]]
        else:
            preferidos = rng.sample(TIPOS_ERRO, k=len(TIPOS_ERRO))
        for tipo in preferidos + TIPOS_ERRO:
            linhas = INJETORES[tipo](rng, dados, usados)
            if linhas:
                gabarito.extend(linhas)
                break
    return gabarito


# ---------- escrita no staging ----------

COLUNAS_STAGING = {
    "staging.participante": [
        "participante_id", "cpf_sintetico", "plano_tipo", "submassa", "sexo",
        "data_nascimento", "data_ingresso", "data_desligamento", "status_atual",
        "data_evento_conhecimento", "data_vigencia_inicio", "data_vigencia_fim",
        "versao_registro",
    ],
    "staging.evento": [
        "evento_id", "participante_id", "tipo_evento", "data_evento",
        "data_conhecimento", "fonte",
    ],
    "staging.exposicao": [
        "exposicao_id", "participante_id", "submassa", "idade_exata",
        "ano_calendario", "tempo_exposto", "tipo_saida", "data_base",
    ],
    "staging.contribuicao_beneficio": [
        "id", "participante_id", "competencia", "valor_contribuicao",
        "valor_beneficio", "status_pagamento",
    ],
}


def inserir_staging(cur, tabela, registros, lote_id):
    if not registros:
        return
    colunas = COLUNAS_STAGING[tabela]
    lista = ", ".join(["lote_id"] + colunas)
    valores = [
        tuple([lote_id] + [to_text(r[c]) for c in colunas]) for r in registros
    ]
    psycopg2.extras.execute_values(
        cur, f"INSERT INTO {tabela} ({lista}) VALUES %s", valores
    )


def main():
    global DATA_REFERENCIA

    parser = argparse.ArgumentParser()
    parser.add_argument("--n-participantes", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-referencia", type=date.fromisoformat,
                        default=DATA_REFERENCIA,
                        help="data-base do lote (ISO). Fixe para reproduzir "
                             "um dataset antigo byte a byte.")
    args = parser.parse_args()
    DATA_REFERENCIA = args.data_referencia

    Faker.seed(args.seed)
    rng = random.Random(args.seed)
    fake = Faker("pt_BR")

    dados = {"participantes": [], "eventos": [], "exposicoes": [], "contribuicoes": []}

    for _ in range(args.n_participantes):
        p = gerar_participante(fake, rng)
        dados["participantes"].append(p)

        ev = gerar_evento(p, rng)
        if ev:
            dados["eventos"].append(ev)
        dados["exposicoes"].extend(gerar_exposicao(p, rng))
        dados["contribuicoes"].extend(gerar_contribuicoes(p, rng))

    # Injeção depois da geração completa: os injetores de duplicidade e
    # órfão precisam do lote inteiro montado para escolher alvos.
    n_alvos = round(args.n_participantes * TAXA_INJECAO)
    gabarito = injetar_imperfeicoes(rng, dados, n_alvos)

    lote_id = str(uuid.uuid4())
    conn = conectar()
    cur = conn.cursor()

    inserir_staging(cur, "staging.participante", dados["participantes"], lote_id)
    inserir_staging(cur, "staging.evento", dados["eventos"], lote_id)
    inserir_staging(cur, "staging.exposicao", dados["exposicoes"], lote_id)
    inserir_staging(cur, "staging.contribuicao_beneficio", dados["contribuicoes"], lote_id)

    if gabarito:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO gabarito.registro_erro_injetado (tabela_alvo, registro_id,
                campo_afetado, tipo_erro, valor_correto_original, valor_injetado)
            VALUES %s
        """, [(g["tabela_alvo"], g["registro_id"], g["campo_afetado"], g["tipo_erro"],
               g["valor_correto_original"], g["valor_injetado"]) for g in gabarito])

    conn.commit()
    cur.close()
    conn.close()

    por_tipo = {}
    for g in gabarito:
        por_tipo[g["tipo_erro"]] = por_tipo.get(g["tipo_erro"], 0) + 1

    print(f"Lote {lote_id} gravado em staging "
          f"(seed={args.seed}, data_referencia={DATA_REFERENCIA}):")
    print(f"  {len(dados['participantes'])} participantes, {len(dados['eventos'])} eventos, "
          f"{len(dados['exposicoes'])} exposições, {len(dados['contribuicoes'])} contribuições")
    print(f"  {len(gabarito)} imperfeições injetadas: "
          + ", ".join(f"{t}={n}" for t, n in sorted(por_tipo.items())))


if __name__ == "__main__":
    main()

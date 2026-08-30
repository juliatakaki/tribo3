"""As 9 regras automatizadas de qualidade — uma por tipo de imperfeição do §5.1.

O escopo exige no mínimo 5 regras; aqui há uma para cada tipo injetado,
porque um tipo sem detector apareceria como falso negativo permanente no
recall do §5.2 e tornaria o indicador ininterpretável.

Toda regra tem a mesma assinatura:

    regra(ctx) -> (violacoes, universo)

`universo` é a lista de CÉLULAS avaliadas (uma por par registro × campo)
e `violacoes` é o subconjunto reprovado. Trabalhar com células, e não com
registros, é o que permite ao pipeline derivar as 4 granularidades do
§3.7 com um agregador só:

    variavel       -> agrupa por tabela.campo
    participante   -> agrupa por participante_id
    submassa_plano -> agrupa por submassa
    data_base      -> agrupa por data_base

Regras marcadas `hard=True` rejeitam a linha (ela não é promovida para a
tabela tipada); as `hard=False` apenas reduzem o score e a linha é
promovida assim mesmo. Rejeitar tudo deixaria as tabelas finais limpas
demais e o dataset perderia a função descrita no §5.
"""

from datetime import date

from dominio import (
    DIAS_ATRASO_ANOMALO,
    IDADE_MAXIMA,
    IDADE_MINIMA,
    LIMIAR_BENEFICIO,
    LIMIAR_CONTRIBUICAO,
    PLANO_TIPOS,
    SUBMASSAS,
)

SUBMASSA_DESCONHECIDA = "DESCONHECIDA"

# Campos obrigatórios por tabela — espelham os NOT NULL de V1 e são a
# base da regra de completude (R05).
OBRIGATORIOS = {
    "participante": [
        "participante_id", "plano_tipo", "submassa", "sexo", "data_nascimento",
        "data_ingresso", "status_atual", "data_evento_conhecimento",
        "data_vigencia_inicio", "versao_registro",
    ],
    "evento": [
        "evento_id", "participante_id", "tipo_evento", "data_evento",
        "data_conhecimento", "fonte",
    ],
    "exposicao": [
        "exposicao_id", "participante_id", "submassa", "idade_exata",
        "ano_calendario", "tempo_exposto", "tipo_saida", "data_base",
    ],
    "contribuicao_beneficio": [
        "id", "participante_id", "competencia", "valor_contribuicao",
        "status_pagamento",
    ],
}

CHAVE_PRIMARIA = {
    "participante": "participante_id",
    "evento": "evento_id",
    "exposicao": "exposicao_id",
    "contribuicao_beneficio": "id",
}

# De qual campo sai a data-base de cada tabela. Todas são normalizadas
# para o fim do ano civil, que é a data de corte usada em avaliação
# atuarial — sem isso a granularidade 'data_base' viraria uma linha por
# dia distinto e deixaria de agregar qualquer coisa.
CAMPO_DATA_BASE = {
    "participante": "data_vigencia_inicio",
    "evento": "data_evento",
    "exposicao": "data_base",
    "contribuicao_beneficio": "competencia",
}


# ---------- helpers ----------

def ausente(texto):
    """§5.1 completude: NULL, string vazia e 'None' contam todos como ausência."""
    return texto is None or texto.strip() in ("", "None")


def _contexto(tabela, rec, ctx):
    """(participante_id, submassa, data_base) de um registro, para agregar."""
    pid = rec.get("participante_id")
    submassa = rec.get("submassa") or ctx["submassa_por_participante"].get(
        pid, SUBMASSA_DESCONHECIDA
    )
    d = rec.get(CAMPO_DATA_BASE[tabela]) or ctx["data_avaliacao"]
    return pid, submassa, date(d.year, 12, 31)


def _celulas(tabela, registros, campos, ctx, filtro=None):
    """Uma célula por registro × campo, já com as chaves de agregação."""
    saida = []
    for rec in registros:
        if filtro is not None and not filtro(rec):
            continue
        pid, submassa, data_base = _contexto(tabela, rec, ctx)
        for campo in campos:
            saida.append({
                "tabela": tabela,
                "campo": campo,
                "registro_id": rec.get(CHAVE_PRIMARIA[tabela]) or rec["_staging_id"],
                "staging_id": rec["_staging_id"],
                "participante_id": pid,
                "submassa": submassa,
                "data_base": data_base,
            })
    return saida


def _idade_em(nascimento, referencia):
    return (referencia - nascimento).days / 365.25


# ---------- R01 — idade/data inválida (validade) ----------

def r01_idade_invalida(ctx):
    universo, violacoes = [], []

    for rec in ctx["participantes"]:
        if rec["data_nascimento"] is None:
            continue  # ausência é problema da R05, não desta
        cel = _celulas("participante", [rec], ["data_nascimento"], ctx)[0]
        universo.append(cel)
        idade = _idade_em(rec["data_nascimento"], ctx["data_avaliacao"])
        if not (IDADE_MINIMA <= idade <= IDADE_MAXIMA):
            violacoes.append(cel)

    # A mesma checagem em exposicao também protege o DECIMAL(6,3) de
    # idade_exata: um valor absurdo aqui estouraria o INSERT.
    for rec in ctx["exposicoes"]:
        if rec["idade_exata"] is None:
            continue
        cel = _celulas("exposicao", [rec], ["idade_exata"], ctx)[0]
        universo.append(cel)
        if not (IDADE_MINIMA <= float(rec["idade_exata"]) <= IDADE_MAXIMA):
            violacoes.append(cel)

    return violacoes, universo


# ---------- R02 — datas fora de ordem lógica (consistência) ----------

def r02_datas_fora_ordem(ctx):
    universo, violacoes = [], []

    for rec in ctx["participantes"]:
        nasc, ing, desl = (rec["data_nascimento"], rec["data_ingresso"],
                           rec["data_desligamento"])
        if ing is not None and nasc is not None:
            cel = _celulas("participante", [rec], ["data_ingresso"], ctx)[0]
            universo.append(cel)
            if ing < nasc:
                violacoes.append(cel)
        if desl is not None and ing is not None:
            cel = _celulas("participante", [rec], ["data_desligamento"], ctx)[0]
            universo.append(cel)
            if desl < ing:
                violacoes.append(cel)

    # Evento antes do ingresso do participante (§5.1: "aposentadoria
    # antes do ingresso").
    ingresso_por_participante = {
        p["participante_id"]: p["data_ingresso"]
        for p in ctx["participantes"] if p["data_ingresso"] is not None
    }
    for rec in ctx["eventos"]:
        ingresso = ingresso_por_participante.get(rec["participante_id"])
        if rec["data_evento"] is None or ingresso is None:
            continue
        cel = _celulas("evento", [rec], ["data_evento"], ctx)[0]
        universo.append(cel)
        if rec["data_evento"] < ingresso:
            violacoes.append(cel)

    return violacoes, universo


# ---------- R03 — grafia divergente (consistência/padronização) ----------

def r03_grafia_divergente(ctx):
    """Valor fora do domínio canônico por diferença de grafia, não de conteúdo."""
    universo, violacoes = [], []

    for tabela, registros in (("participante", ctx["participantes"]),
                              ("exposicao", ctx["exposicoes"])):
        for rec in registros:
            if rec["submassa"] is None:
                continue
            cel = _celulas(tabela, [rec], ["submassa"], ctx)[0]
            universo.append(cel)
            if rec["submassa"] not in SUBMASSAS:
                violacoes.append(cel)

    for rec in ctx["participantes"]:
        if rec["plano_tipo"] is None:
            continue
        cel = _celulas("participante", [rec], ["plano_tipo"], ctx)[0]
        universo.append(cel)
        if rec["plano_tipo"] not in PLANO_TIPOS:
            violacoes.append(cel)

    return violacoes, universo


def normalizar_submassa(valor):
    """Devolve a grafia canônica, ou None se não der para reconhecer."""
    if valor is None:
        return None
    chave = valor.upper().replace("_", " ").replace(".", "").replace(" ", "")
    for canonico in SUBMASSAS:
        if canonico.upper().replace(" ", "") == chave:
            return canonico
    # "P. A" -> "PA" não bate com "PLANOA"; tenta pela inicial + letra final.
    for canonico in SUBMASSAS:
        if chave and canonico.upper().endswith(chave[-1]) and chave[0] == canonico[0].upper():
            return canonico
    return None


# ---------- R04 — duplicidade (unicidade) ----------

def r04_duplicidade(ctx):
    """Mesmo CPF sintético em participante_id diferentes (§5.1).

    Flagra TODOS os membros do grupo duplicado: olhando só para a base
    não há como distinguir o original da cópia. Quem escolhe qual linha
    sobreviver é a promoção, de forma determinística.
    """
    universo, violacoes = [], []
    por_cpf = {}
    for rec in ctx["participantes"]:
        if rec["cpf_sintetico"] is None:
            continue
        por_cpf.setdefault(rec["cpf_sintetico"], []).append(rec)

    for cpf, grupo in por_cpf.items():
        celulas = _celulas("participante", grupo, ["cpf_sintetico"], ctx)
        universo.extend(celulas)
        if len(grupo) > 1:
            violacoes.extend(celulas)

    return violacoes, universo


# ---------- R05 — valores nulos/faltantes (completude) ----------

def r05_nulo(ctx):
    universo, violacoes = [], []
    tabelas = (("participante", ctx["participantes"]),
               ("evento", ctx["eventos"]),
               ("exposicao", ctx["exposicoes"]),
               ("contribuicao_beneficio", ctx["contribuicoes"]))

    for tabela, registros in tabelas:
        campos = OBRIGATORIOS[tabela]
        for rec in registros:
            for cel in _celulas(tabela, [rec], campos, ctx):
                universo.append(cel)
                if ausente(rec["_bruto"].get(cel["campo"])):
                    violacoes.append(cel)

    return violacoes, universo


# ---------- R06 — outliers/valores absurdos (acurácia) ----------

def r06_outlier(ctx):
    """Contribuição negativa e benefício muito acima da faixa plausível."""
    universo, violacoes = [], []

    for rec in ctx["contribuicoes"]:
        if rec["valor_contribuicao"] is not None:
            cel = _celulas("contribuicao_beneficio", [rec], ["valor_contribuicao"], ctx)[0]
            universo.append(cel)
            if float(rec["valor_contribuicao"]) < 0:
                violacoes.append(cel)
        if rec["valor_beneficio"] is not None:
            cel = _celulas("contribuicao_beneficio", [rec], ["valor_beneficio"], ctx)[0]
            universo.append(cel)
            valor = float(rec["valor_beneficio"])
            if valor < 0 or valor > LIMIAR_BENEFICIO:
                violacoes.append(cel)

    return violacoes, universo


# ---------- R07 — registros órfãos (integridade referencial) ----------

def r07_orfao(ctx):
    """Filho apontando para um participante_id que não existe no lote.

    A comparação é contra TODOS os participantes do staging, não contra
    os já promovidos: se fosse contra os promovidos, todo filho de um
    participante rejeitado por outra regra viraria um órfão que ninguém
    injetou — falsos positivos que estragariam a precisão do §5.2.
    """
    universo, violacoes = [], []
    existentes = ctx["ids_participantes"]

    for tabela, registros in (("evento", ctx["eventos"]),
                              ("exposicao", ctx["exposicoes"]),
                              ("contribuicao_beneficio", ctx["contribuicoes"])):
        for rec in registros:
            if rec["participante_id"] is None:
                continue  # ausência é problema da R05
            cel = _celulas(tabela, [rec], ["participante_id"], ctx)[0]
            universo.append(cel)
            if rec["participante_id"] not in existentes:
                violacoes.append(cel)

    return violacoes, universo


# ---------- R08 — atraso de conhecimento anômalo (temporalidade) ----------

def r08_atraso_anomalo(ctx):
    """data_conhecimento distante demais de data_evento.

    As duas pontas são reduzidas a `date` antes da subtração: comparar
    TIMESTAMPTZ com DATE direto daria off-by-one conforme o fuso da
    máquina que roda o pipeline.
    """
    universo, violacoes = [], []

    for rec in ctx["eventos"]:
        if rec["data_evento"] is None or rec["data_conhecimento"] is None:
            continue
        cel = _celulas("evento", [rec], ["data_conhecimento"], ctx)[0]
        universo.append(cel)
        if (rec["data_conhecimento"] - rec["data_evento"]).days > DIAS_ATRASO_ANOMALO:
            violacoes.append(cel)

    for rec in ctx["participantes"]:
        if rec["data_evento_conhecimento"] is None or rec["data_vigencia_inicio"] is None:
            continue
        cel = _celulas("participante", [rec], ["data_evento_conhecimento"], ctx)[0]
        universo.append(cel)
        atraso = (rec["data_evento_conhecimento"] - rec["data_vigencia_inicio"]).days
        if atraso > DIAS_ATRASO_ANOMALO:
            violacoes.append(cel)

    return violacoes, universo


# ---------- R09 — unidades/formatos trocados (materialidade) ----------

def r09_unidade_trocada(ctx):
    """Data em formato não-ISO e valor gravado em centavos em vez de reais."""
    universo, violacoes = [], []

    for rec in ctx["participantes"]:
        cel = _celulas("participante", [rec], ["data_ingresso"], ctx)[0]
        universo.append(cel)
        if "data_ingresso" in rec["_formato_nao_iso"]:
            violacoes.append(cel)

    for rec in ctx["contribuicoes"]:
        if rec["valor_contribuicao"] is None:
            continue
        cel = _celulas("contribuicao_beneficio", [rec], ["valor_contribuicao"], ctx)[0]
        universo.append(cel)
        if float(rec["valor_contribuicao"]) > LIMIAR_CONTRIBUICAO:
            violacoes.append(cel)

    return violacoes, universo


# ---------- catálogo ----------
# tipo_erro do §5.1 -> (função, rejeita a linha?)
# O código (R01..R09) e a dimensão de qualidade saem de dominio.py, para
# que injetor e detector nunca divirjam.

REGRAS = {
    "idade_invalida":    (r01_idade_invalida, True),
    "datas_fora_ordem":  (r02_datas_fora_ordem, False),
    "grafia_divergente": (r03_grafia_divergente, False),
    "duplicidade":       (r04_duplicidade, True),
    "nulo":              (r05_nulo, True),
    "outlier":           (r06_outlier, False),
    "orfao":             (r07_orfao, True),
    "atraso_anomalo":    (r08_atraso_anomalo, False),
    "unidade_trocada":   (r09_unidade_trocada, False),
}

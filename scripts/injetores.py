"""Injeção controlada de imperfeições — §5.1 do documento de referência.

Uma função por tipo de imperfeição, todas com a mesma assinatura:

    injetor(rng, dados, usados) -> list[gabarito] | None

`dados` é o dict com as 4 listas de registros ainda tipados (antes da
serialização para o staging); o injetor mutila os registros no lugar.
`usados` guarda os (tabela, registro_id) já corrompidos, para não
empilhar duas imperfeições no mesmo registro — o que tornaria o
precision/recall do §5.2 ambíguo.

Devolve None quando não há alvo adequado no lote (o chamador tenta outro
tipo). Caso contrário devolve as linhas de gabarito, cujo
`valor_injetado` é EXATAMENTE o texto que será gravado no staging.
"""

from datetime import timedelta

from dominio import (
    DIAS_ATRASO_ANOMALO,
    LIMIAR_BENEFICIO,
    LIMIAR_CONTRIBUICAO,
    TOKEN_AUSENTE,
    novo_uuid,
    to_text,
)


def _gabarito(tabela, registro_id, campo, tipo_erro, original, injetado):
    return {
        "tabela_alvo": tabela,
        "registro_id": str(registro_id),
        "campo_afetado": campo,
        "tipo_erro": tipo_erro,
        "valor_correto_original": to_text(original),
        # A coluna é NOT NULL: injeção de ausência vira o token explícito.
        "valor_injetado": to_text(injetado) if injetado is not None else TOKEN_AUSENTE,
    }


def _sortear(rng, registros, usados, tabela, chave, filtro=None):
    """Sorteia um registro ainda não corrompido, opcionalmente filtrado."""
    candidatos = [
        r for r in registros
        if (tabela, str(r[chave])) not in usados and (filtro is None or filtro(r))
    ]
    if not candidatos:
        return None
    return rng.choice(candidatos)


def _marcar(usados, tabela, registro_id):
    usados.add((tabela, str(registro_id)))


# ---------- 1. idade/data inválida — dimensão: validade ----------

def injetar_idade_invalida(rng, dados, usados):
    """Data de nascimento que produz idade > 130 anos."""
    p = _sortear(rng, dados["participantes"], usados, "participante", "participante_id")
    if p is None:
        return None
    original = p["data_nascimento"]
    # timedelta em vez de replace(year=...) para não quebrar em 29/02.
    p["data_nascimento"] = original - timedelta(days=140 * 365)
    _marcar(usados, "participante", p["participante_id"])
    return [_gabarito("participante", p["participante_id"], "data_nascimento",
                      "idade_invalida", original, p["data_nascimento"])]


# ---------- 2. datas fora de ordem lógica — dimensão: consistência ----------

def injetar_datas_fora_ordem(rng, dados, usados):
    """Desligamento antes do ingresso (§5.1: 'aposentadoria antes do ingresso')."""
    p = _sortear(rng, dados["participantes"], usados, "participante", "participante_id",
                 filtro=lambda r: r["data_desligamento"] is not None)
    if p is None:
        return None
    original = p["data_desligamento"]
    p["data_desligamento"] = p["data_ingresso"] - timedelta(days=400)
    _marcar(usados, "participante", p["participante_id"])

    linhas = [_gabarito("participante", p["participante_id"], "data_desligamento",
                        "datas_fora_ordem", original, p["data_desligamento"])]

    # O evento correspondente acompanha a data, senão a inconsistência
    # ficaria só numa das duas tabelas. Ele entra no gabarito como uma
    # segunda linha: a regra R02 vai flagrar os dois registros, e sem a
    # linha aqui o flag do evento contaria como falso positivo.
    for ev in dados["eventos"]:
        if ev["participante_id"] == p["participante_id"]:
            original_ev = ev["data_evento"]
            # data_conhecimento anda junto: mover só data_evento criaria
            # um atraso de conhecimento de ~400 dias que ninguém injetou,
            # e a R08 o contaria como falso positivo.
            atraso = ev["data_conhecimento"] - original_ev
            ev["data_evento"] = p["data_desligamento"]
            ev["data_conhecimento"] = ev["data_evento"] + atraso
            _marcar(usados, "evento", ev["evento_id"])
            linhas.append(_gabarito("evento", ev["evento_id"], "data_evento",
                                    "datas_fora_ordem", original_ev, ev["data_evento"]))

    return linhas


# ---------- 3. grafia divergente — dimensão: consistência ----------

def injetar_grafia_divergente(rng, dados, usados):
    """Mesma submassa escrita de formas diferentes ('Plano A' / 'PLANO_a' / 'plano a')."""
    p = _sortear(rng, dados["participantes"], usados, "participante", "participante_id")
    if p is None:
        return None
    original = p["submassa"]
    variantes = [
        original.upper().replace(" ", "_"),
        original.lower(),
        original.replace("Plano ", "P. "),
    ]
    p["submassa"] = rng.choice(variantes)
    _marcar(usados, "participante", p["participante_id"])

    # A divergência fica só em participante. Propagá-la para exposicao
    # exigiria uma linha de gabarito por linha de exposição do
    # participante, inflando o gabarito sem testar nada a mais — a regra
    # R03 já varre as duas tabelas contra o domínio canônico.

    return [_gabarito("participante", p["participante_id"], "submassa",
                      "grafia_divergente", original, p["submassa"])]


# ---------- 4. duplicidade — dimensão: unicidade ----------

def injetar_duplicidade(rng, dados, usados):
    """Mesmo CPF sintético em dois participante_id diferentes (§5.1).

    Duplicar o participante_id em vez do CPF esbarraria no
    UNIQUE (participante_id, versao_registro) de V1 e derrubaria a
    promoção inteira — por isso a duplicidade é modelada pelo CPF.
    """
    p = _sortear(rng, dados["participantes"], usados, "participante", "participante_id",
                 filtro=lambda r: r["cpf_sintetico"] is not None)
    if p is None:
        return None
    clone = dict(p)
    clone["participante_id"] = novo_uuid(rng)
    dados["participantes"].append(clone)
    _marcar(usados, "participante", p["participante_id"])
    _marcar(usados, "participante", clone["participante_id"])

    # As DUAS linhas entram no gabarito: olhando só para a base, não há
    # como saber qual das duas é a cópia — a regra de unicidade flagra o
    # par inteiro, e registrar só o clone transformaria o flag do
    # original num falso positivo.
    return [
        _gabarito("participante", p["participante_id"], "cpf_sintetico",
                  "duplicidade", p["cpf_sintetico"], p["cpf_sintetico"]),
        _gabarito("participante", clone["participante_id"], "cpf_sintetico",
                  "duplicidade", None, clone["cpf_sintetico"]),
    ]


# ---------- 5. valor nulo/faltante — dimensão: completude ----------

def injetar_nulo(rng, dados, usados):
    """Campo obrigatório vazio — o §5.1 cita data_nascimento nominalmente."""
    p = _sortear(rng, dados["participantes"], usados, "participante", "participante_id")
    if p is None:
        return None
    original = p["data_nascimento"]
    p["data_nascimento"] = None
    _marcar(usados, "participante", p["participante_id"])
    return [_gabarito("participante", p["participante_id"], "data_nascimento",
                      "nulo", original, None)]


# ---------- 6. outlier/valor absurdo — dimensão: acurácia ----------

def injetar_outlier(rng, dados, usados):
    """Contribuição negativa ou benefício muito acima da faixa plausível."""
    c = _sortear(rng, dados["contribuicoes"], usados, "contribuicao_beneficio", "id")
    if c is None:
        return None
    if c["valor_beneficio"] is not None and rng.random() < 0.5:
        campo, original = "valor_beneficio", c["valor_beneficio"]
        c["valor_beneficio"] = round(LIMIAR_BENEFICIO * rng.uniform(10, 40), 2)
        injetado = c["valor_beneficio"]
    else:
        campo, original = "valor_contribuicao", c["valor_contribuicao"]
        c["valor_contribuicao"] = -original
        injetado = c["valor_contribuicao"]
    _marcar(usados, "contribuicao_beneficio", c["id"])
    return [_gabarito("contribuicao_beneficio", c["id"], campo,
                      "outlier", original, injetado)]


# ---------- 7. registro órfão — dimensão: consistência (int. referencial) ----------

def injetar_orfao(rng, dados, usados):
    """Evento apontando para um participante_id que não existe."""
    ev = _sortear(rng, dados["eventos"], usados, "evento", "evento_id")
    if ev is None:
        return None
    original = ev["participante_id"]
    ev["participante_id"] = novo_uuid(rng)
    _marcar(usados, "evento", ev["evento_id"])
    return [_gabarito("evento", ev["evento_id"], "participante_id",
                      "orfao", original, ev["participante_id"])]


# ---------- 8. atraso de conhecimento anômalo — dimensão: temporalidade ----------

def injetar_atraso_anomalo(rng, dados, usados):
    """data_conhecimento muito distante de data_evento (o normal é 1 a 10 dias)."""
    ev = _sortear(rng, dados["eventos"], usados, "evento", "evento_id")
    if ev is None:
        return None
    original = ev["data_conhecimento"]
    ev["data_conhecimento"] = ev["data_evento"] + timedelta(
        days=DIAS_ATRASO_ANOMALO + rng.randint(30, 700)
    )
    _marcar(usados, "evento", ev["evento_id"])
    return [_gabarito("evento", ev["evento_id"], "data_conhecimento",
                      "atraso_anomalo", original, ev["data_conhecimento"])]


# ---------- 9. unidade/formato trocado — dimensão: materialidade ----------

def injetar_unidade_trocada(rng, dados, usados):
    """Valor em centavos em vez de reais, ou data em DD/MM/AAAA em vez de ISO."""
    if rng.random() < 0.5:
        c = _sortear(rng, dados["contribuicoes"], usados, "contribuicao_beneficio", "id")
        if c is not None:
            original = c["valor_contribuicao"]
            c["valor_contribuicao"] = round(original * 100, 2)  # reais -> centavos
            assert c["valor_contribuicao"] > LIMIAR_CONTRIBUICAO
            _marcar(usados, "contribuicao_beneficio", c["id"])
            return [_gabarito("contribuicao_beneficio", c["id"], "valor_contribuicao",
                              "unidade_trocada", original, c["valor_contribuicao"])]

    p = _sortear(rng, dados["participantes"], usados, "participante", "participante_id")
    if p is None:
        return None
    original = p["data_ingresso"]
    # String crua: o staging é TEXT, então o formato não-ISO sobrevive
    # até o parse do pipeline.
    p["data_ingresso"] = original.strftime("%d/%m/%Y")
    _marcar(usados, "participante", p["participante_id"])
    return [_gabarito("participante", p["participante_id"], "data_ingresso",
                      "unidade_trocada", original, p["data_ingresso"])]


INJETORES = {
    "idade_invalida":    injetar_idade_invalida,
    "datas_fora_ordem":  injetar_datas_fora_ordem,
    "grafia_divergente": injetar_grafia_divergente,
    "duplicidade":       injetar_duplicidade,
    "nulo":              injetar_nulo,
    "outlier":           injetar_outlier,
    "orfao":             injetar_orfao,
    "atraso_anomalo":    injetar_atraso_anomalo,
    "unidade_trocada":   injetar_unidade_trocada,
}

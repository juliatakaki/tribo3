"""Domínios e limiares compartilhados entre o gerador (injeção) e o pipeline (detecção).

Ficam num módulo só de propósito: se o injetor e a regra usassem limiares
diferentes, o precision/recall do §5.2 mediria o desalinhamento entre os
dois em vez de medir a qualidade do pipeline.
"""

import uuid

# ---------- domínios canônicos (espelham os enums de V1) ----------

PLANO_TIPOS = ["BD", "CD", "CV"]
SUBMASSAS = ["Plano A", "Plano B", "Plano C"]
SEXOS = ["M", "F"]
STATUS_PARTICIPANTE = ["ativo", "aposentado", "desligado", "obito", "pensionista"]
TIPOS_EVENTO = [
    "obito", "invalidez", "aposentadoria", "desligamento",
    "correcao_cadastral", "atraso_contribuicao", "mudanca_regra",
]
TIPOS_SAIDA = ["obito", "censura", "saida_estudo"]
STATUS_PAGAMENTO = ["em_dia", "atraso", "quitado"]

# ---------- limiares de plausibilidade ----------

IDADE_MAXIMA = 130          # §5.1: "idade > 130" é o exemplo de idade inválida
IDADE_MINIMA = 0

# Faixas normais geradas: contribuição uniform(200, 2500), benefício
# uniform(1000, 5000). Os limiares abaixo ficam acima do teto normal e
# abaixo do valor injetado, para que injeção e detecção não se cruzem.
LIMIAR_CONTRIBUICAO = 10_000.0   # acima disso: provável valor em centavos (R09)
LIMIAR_BENEFICIO = 50_000.0      # acima disso: outlier de benefício (R06)

# §5.1 "atraso de conhecimento anômalo": data_conhecimento muito distante
# de data_evento. O gerador normal usa 1 a 10 dias.
DIAS_ATRASO_ANOMALO = 365

# Estouro dos DECIMAL de V1 — o pipeline precisa checar ANTES do INSERT,
# senão um único valor absurdo aborta o execute_values inteiro.
MAX_IDADE_EXATA = 999.999        # exposicao.idade_exata  DECIMAL(6,3)
MAX_TEMPO_EXPOSTO = 9.99999      # exposicao.tempo_exposto DECIMAL(6,5)
MAX_VALOR = 999_999_999_999.99   # contribuicao_beneficio  DECIMAL(14,2)

# ---------- mapa tipo de erro -> dimensão de qualidade (§5.1) ----------
# Nota: o §5.1 nomeia a dimensão do erro 'orfao' como "integridade
# referencial", mas o enum dimensao_qualidade_enum do §3.7 não tem esse
# valor. Mapeado para 'consistencia', que é o mais próximo do conjunto
# fechado definido pelo documento.

DIMENSAO_POR_TIPO_ERRO = {
    "idade_invalida":    "validade",
    "datas_fora_ordem":  "consistencia",
    "grafia_divergente": "consistencia",
    "duplicidade":       "unicidade",
    "nulo":              "completude",
    "outlier":           "acuracia",
    "orfao":             "consistencia",
    "atraso_anomalo":    "temporalidade",
    "unidade_trocada":   "materialidade",
}

# Código da regra que detecta cada tipo — uma regra por tipo (§5.1).
REGRA_POR_TIPO_ERRO = {
    "idade_invalida":    "R01",
    "datas_fora_ordem":  "R02",
    "grafia_divergente": "R03",
    "duplicidade":       "R04",
    "nulo":              "R05",
    "outlier":           "R06",
    "orfao":             "R07",
    "atraso_anomalo":    "R08",
    "unidade_trocada":   "R09",
}

TIPOS_ERRO = list(REGRA_POR_TIPO_ERRO)

# gabarito.registro_erro_injetado.valor_injetado é NOT NULL em V1, mas a
# imperfeição do tipo 'nulo' injeta justamente uma ausência. O token
# abaixo registra isso de forma explícita: no dado de trabalho o campo
# fica SQL NULL de verdade; no gabarito fica escrito que foi ausência que
# se injetou ali.
TOKEN_AUSENTE = "<NULL>"

# Código usado quando a linha filha cai junto com o participante rejeitado.
# Não é uma regra do §5.1 — é bookkeeping da promoção.
MOTIVO_PAI_REJEITADO = "R99_pai_rejeitado"


# ---------- identificadores ----------

def novo_uuid(rng):
    """UUID v4 derivado do rng semeado.

    uuid.uuid4() usa entropia do sistema e ignora a seed, o que faria
    cada execução produzir ids diferentes — o §6 exige "mesma seed =
    mesmo resultado", e os ids são parte do resultado.
    """
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


# ---------- serialização para o staging ----------

def to_text(valor):
    """Converte um valor tipado no TEXT que vai para o staging.

    Strings passam intactas — é assim que as imperfeições de formato
    (data em DD/MM/AAAA) chegam cruas ao banco. None vira SQL NULL de
    verdade, nunca a string 'None': o §5.1 pede ausência real do valor
    para exercitar a regra de completude.
    """
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor
    if isinstance(valor, bool):
        return "true" if valor else "false"
    return str(valor)

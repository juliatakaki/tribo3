"""
Pipeline de qualidade — Tribo 3

Lê o schema `staging`, aplica as 9 regras automatizadas do §5.1, grava o
Data Quality Score nas 4 granularidades do §3.7, promove as linhas
aprovadas para as tabelas tipadas e mede precision/recall contra o
gabarito do §5.2.

Uso:
    python pipeline_qualidade.py

É idempotente: só processa linhas ainda não promovidas, e os scores são
gravados com ON CONFLICT DO UPDATE.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import psycopg2.extras

import regras as mod_regras
from db import conectar
from dominio import (
    DIMENSAO_POR_TIPO_ERRO,
    MAX_IDADE_EXATA,
    MAX_TEMPO_EXPOSTO,
    MAX_VALOR,
    MOTIVO_PAI_REJEITADO,
    PLANO_TIPOS,
    REGRA_POR_TIPO_ERRO,
    SEXOS,
    STATUS_PAGAMENTO,
    STATUS_PARTICIPANTE,
    TIPOS_EVENTO,
    TIPOS_SAIDA,
)
from regras import CHAVE_PRIMARIA, ausente, normalizar_submassa

# ---------- esquema de parsing por tabela ----------
# campo -> tipo lógico. Guia tanto o cast quanto a validação de domínio.

CAMPOS = {
    "participante": {
        "participante_id": "uuid", "cpf_sintetico": "texto", "plano_tipo": PLANO_TIPOS,
        "submassa": "texto", "sexo": SEXOS, "data_nascimento": "data",
        "data_ingresso": "data", "data_desligamento": "data",
        "status_atual": STATUS_PARTICIPANTE, "data_evento_conhecimento": "data",
        "data_vigencia_inicio": "data", "data_vigencia_fim": "data",
        "versao_registro": "inteiro",
    },
    "evento": {
        "evento_id": "uuid", "participante_id": "uuid", "tipo_evento": TIPOS_EVENTO,
        "data_evento": "data", "data_conhecimento": "data", "fonte": "texto",
    },
    "exposicao": {
        "exposicao_id": "uuid", "participante_id": "uuid", "submassa": "texto",
        "idade_exata": "decimal", "ano_calendario": "inteiro",
        "tempo_exposto": "decimal", "tipo_saida": TIPOS_SAIDA, "data_base": "data",
    },
    "contribuicao_beneficio": {
        "id": "uuid", "participante_id": "uuid", "competencia": "data",
        "valor_contribuicao": "decimal", "valor_beneficio": "decimal",
        "status_pagamento": STATUS_PAGAMENTO,
    },
}

TABELAS = list(CAMPOS)

# Tetos dos DECIMAL de V1. Um valor acima disso não é só implausível: ele
# aborta o execute_values inteiro com numeric field overflow, então a
# checagem tem que acontecer ANTES do INSERT, não no servidor.
TETO_DECIMAL = {
    ("exposicao", "idade_exata"): MAX_IDADE_EXATA,
    ("exposicao", "tempo_exposto"): MAX_TEMPO_EXPOSTO,
    ("contribuicao_beneficio", "valor_contribuicao"): MAX_VALOR,
    ("contribuicao_beneficio", "valor_beneficio"): MAX_VALOR,
}


# ---------- 1. leitura e parsing ----------

def _parse_data(texto):
    """(valor, formato_nao_iso, falhou). Aceita ISO e DD/MM/AAAA."""
    if ausente(texto):
        return None, False, False
    texto = texto.strip()
    try:
        return date.fromisoformat(texto[:10]), False, False
    except ValueError:
        pass
    for formato in ("%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(texto, formato).date(), True, False
        except ValueError:
            continue
    return None, False, True


def _parse_decimal(texto):
    if ausente(texto):
        return None, False
    try:
        return Decimal(texto.strip()), False
    except InvalidOperation:
        return None, True


def _parse_inteiro(texto):
    if ausente(texto):
        return None, False
    try:
        return int(texto.strip()), False
    except ValueError:
        return None, True


def parsear(tabela, linhas):
    """Converte as linhas TEXT do staging em registros tipados.

    Nenhum cast roda no servidor: execute_values é um statement único, e
    uma linha ruim derrubaria o lote inteiro. Aqui cada campo falha
    sozinho e o motivo fica registrado na própria linha.
    """
    registros = []
    for linha in linhas:
        rec = {
            "_staging_id": linha["staging_id"],
            "_bruto": {c: linha[c] for c in CAMPOS[tabela]},
            "_formato_nao_iso": set(),
            "_motivos": [],
        }
        for campo, tipo in CAMPOS[tabela].items():
            bruto = linha[campo]
            if tipo == "data":
                valor, nao_iso, falhou = _parse_data(bruto)
                if nao_iso:
                    rec["_formato_nao_iso"].add(campo)
                if falhou:
                    rec["_motivos"].append(f"CAST_INVALIDO:{campo}")
            elif tipo == "decimal":
                valor, falhou = _parse_decimal(bruto)
                if falhou:
                    rec["_motivos"].append(f"CAST_INVALIDO:{campo}")
                elif valor is not None:
                    teto = TETO_DECIMAL.get((tabela, campo))
                    if teto is not None and abs(valor) > Decimal(str(teto)):
                        rec["_motivos"].append(f"FORA_DE_FAIXA:{campo}")
            elif tipo == "inteiro":
                valor, falhou = _parse_inteiro(bruto)
                if falhou:
                    rec["_motivos"].append(f"CAST_INVALIDO:{campo}")
            elif isinstance(tipo, list):
                valor = None if ausente(bruto) else bruto.strip()
                if valor is not None and valor not in tipo:
                    rec["_motivos"].append(f"ENUM_INVALIDO:{campo}")
            else:  # uuid, texto — ficam como string
                valor = None if ausente(bruto) else bruto.strip()
            rec[campo] = valor
        registros.append(rec)
    return registros


def carregar(cur):
    """Lê do staging só o que ainda não foi promovido — reexecução é segura."""
    dados = {}
    for tabela in TABELAS:
        colunas = ["staging_id"] + list(CAMPOS[tabela])
        cur.execute(
            f"SELECT {', '.join(colunas)} FROM staging.{tabela} WHERE NOT promovido"
        )
        linhas = [dict(zip(colunas, r)) for r in cur.fetchall()]
        dados[tabela] = parsear(tabela, linhas)
    return dados


# ---------- 2. execução das regras ----------

def montar_contexto(dados, data_avaliacao):
    participantes = dados["participante"]
    return {
        "participantes": participantes,
        "eventos": dados["evento"],
        "exposicoes": dados["exposicao"],
        "contribuicoes": dados["contribuicao_beneficio"],
        "ids_participantes": {
            p["participante_id"] for p in participantes if p["participante_id"]
        },
        "submassa_por_participante": {
            p["participante_id"]: p["submassa"]
            for p in participantes if p["participante_id"] and p["submassa"]
        },
        "data_avaliacao": data_avaliacao,
    }


def executar_regras(ctx):
    """Roda as 9 regras. Devolve {tipo_erro: (violacoes, universo, hard)}."""
    resultado = {}
    for tipo_erro, (funcao, hard) in mod_regras.REGRAS.items():
        violacoes, universo = funcao(ctx)
        resultado[tipo_erro] = (violacoes, universo, hard)
    return resultado


# ---------- 3. Data Quality Score (§3.7) ----------

# Convenção de preenchimento do referencia_id, documentada também no
# dicionario_dados. Sem uma convenção fixa a tabela fica ilegível.
GRANULARIDADES = {
    "variavel": lambda cel: f"{cel['tabela']}.{cel['campo']}",
    "participante": lambda cel: cel["participante_id"] or "DESCONHECIDO",
    "submassa_plano": lambda cel: cel["submassa"],
    "data_base": lambda cel: cel["data_base"].isoformat(),
}


def calcular_scores(resultados, data_avaliacao):
    """Um score por (granularidade, elemento, regra).

    score = 1 - violações/avaliadas dentro do grupo. Como as regras
    devolvem células (registro × campo), o mesmo agregador serve para as
    4 granularidades do §3.7.
    """
    scores = []
    for tipo_erro, (violacoes, universo, _) in resultados.items():
        regra = REGRA_POR_TIPO_ERRO[tipo_erro]
        dimensao = DIMENSAO_POR_TIPO_ERRO[tipo_erro]
        chaves_violadas = {id(c) for c in violacoes}

        for granularidade, chave_de in GRANULARIDADES.items():
            total, ruins = {}, {}
            for cel in universo:
                k = chave_de(cel)
                total[k] = total.get(k, 0) + 1
                if id(cel) in chaves_violadas:
                    ruins[k] = ruins.get(k, 0) + 1
            for k, n in total.items():
                score = round(1 - ruins.get(k, 0) / n, 3)
                scores.append((granularidade, str(k)[:200], dimensao,
                               score, data_avaliacao, regra))
    return scores


def gravar_scores(cur, scores):
    if not scores:
        return
    psycopg2.extras.execute_values(cur, """
        INSERT INTO data_quality_score (granularidade, referencia_id,
            dimensao_qualidade, score, data_avaliacao, regra_aplicada)
        VALUES %s
        ON CONFLICT (granularidade, referencia_id, dimensao_qualidade,
                     data_avaliacao, regra_aplicada)
        DO UPDATE SET score = EXCLUDED.score
    """, scores)


# ---------- 4. rejeição e promoção ----------

def decidir_rejeicoes(dados, resultados):
    """staging_id -> lista de motivos. Linha com motivo não é promovida."""
    motivos = {}

    def add(staging_id, motivo):
        motivos.setdefault(staging_id, [])
        if motivo not in motivos[staging_id]:
            motivos[staging_id].append(motivo)

    # (a) problemas detectados no parsing: cast, enum, faixa do DECIMAL.
    for registros in dados.values():
        for rec in registros:
            for motivo in rec["_motivos"]:
                add(rec["_staging_id"], motivo)

    # (b) regras marcadas como hard.
    for tipo_erro, (violacoes, _, hard) in resultados.items():
        if not hard:
            continue
        regra = REGRA_POR_TIPO_ERRO[tipo_erro]
        for cel in violacoes:
            add(cel["staging_id"], f"{regra}_{tipo_erro}")

    # (c) duplicidade é o único caso em que a regra flagra o grupo todo
    # mas a curadoria deve preservar uma linha. Sobrevive o menor
    # participante_id do grupo — critério arbitrário, mas determinístico,
    # que é o que a reprodutibilidade do §6 exige.
    regra_dup = f"{REGRA_POR_TIPO_ERRO['duplicidade']}_duplicidade"
    por_cpf = {}
    for rec in dados["participante"]:
        if rec["cpf_sintetico"]:
            por_cpf.setdefault(rec["cpf_sintetico"], []).append(rec)
    for grupo in por_cpf.values():
        if len(grupo) < 2:
            continue
        sobrevivente = min(grupo, key=lambda r: r["participante_id"] or "")
        if regra_dup in motivos.get(sobrevivente["_staging_id"], []):
            motivos[sobrevivente["_staging_id"]].remove(regra_dup)
            if not motivos[sobrevivente["_staging_id"]]:
                del motivos[sobrevivente["_staging_id"]]

    # (d) cascata: filho de participante rejeitado não é promovido, senão
    # entraria como órfão que ninguém injetou.
    rejeitados = {
        rec["participante_id"] for rec in dados["participante"]
        if rec["_staging_id"] in motivos and rec["participante_id"]
    }
    for tabela in ("evento", "exposicao", "contribuicao_beneficio"):
        for rec in dados[tabela]:
            if rec["participante_id"] in rejeitados:
                add(rec["_staging_id"], MOTIVO_PAI_REJEITADO)

    return motivos


def _tratar(tabela, rec):
    """Correções aplicadas na promoção (curadoria propriamente dita)."""
    tratado = dict(rec)
    if "submassa" in CAMPOS[tabela]:
        # R03: grafia divergente vira a grafia canônica. Se não der para
        # reconhecer, mantém o valor original — inventar seria pior.
        tratado["submassa"] = normalizar_submassa(rec["submassa"]) or rec["submassa"]
    return tratado


DESTINO = {
    "participante": ("participante", [
        "participante_id", "cpf_sintetico", "plano_tipo", "submassa", "sexo",
        "data_nascimento", "data_ingresso", "data_desligamento", "status_atual",
        "data_evento_conhecimento", "data_vigencia_inicio", "data_vigencia_fim",
        "versao_registro"]),
    "evento": ("evento", [
        "evento_id", "participante_id", "tipo_evento", "data_evento",
        "data_conhecimento", "fonte"]),
    "exposicao": ("exposicao", [
        "exposicao_id", "participante_id", "submassa", "idade_exata",
        "ano_calendario", "tempo_exposto", "tipo_saida", "data_base"]),
    "contribuicao_beneficio": ("contribuicao_beneficio", [
        "id", "participante_id", "competencia", "valor_contribuicao",
        "valor_beneficio", "status_pagamento"]),
}


def promover(cur, dados, motivos):
    """Copia as linhas aprovadas para as tabelas tipadas.

    Participante primeiro: as demais tabelas referenciam participante_id,
    e a ordem mantém a base consistente mesmo sem FK física (a ausência
    de FK em evento é proposital — é o que permite o erro órfão do §5.1).
    """
    promovidos = {}
    for tabela in ("participante", "evento", "exposicao", "contribuicao_beneficio"):
        destino, colunas = DESTINO[tabela]
        aprovados = [r for r in dados[tabela] if r["_staging_id"] not in motivos]
        promovidos[tabela] = len(aprovados)
        if not aprovados:
            continue
        valores = [
            tuple(_tratar(tabela, r)[c] for c in colunas) for r in aprovados
        ]
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO {destino} ({', '.join(colunas)}) VALUES %s",
            valores,
        )
    return promovidos


def marcar_staging(cur, dados, motivos):
    """Fecha o ciclo no staging: promovido = TRUE ou o porquê da rejeição."""
    for tabela in TABELAS:
        atualizacoes = [
            (rec["_staging_id"],
             rec["_staging_id"] not in motivos,
             motivos.get(rec["_staging_id"]))
            for rec in dados[tabela]
        ]
        if not atualizacoes:
            continue
        psycopg2.extras.execute_values(cur, f"""
            UPDATE staging.{tabela} AS s
               SET promovido = v.promovido, motivos_rejeicao = v.motivos
              FROM (VALUES %s) AS v(staging_id, promovido, motivos)
             WHERE s.staging_id = v.staging_id
        """, atualizacoes, template="(%s::uuid, %s::boolean, %s::text[])")


# ---------- 5. precision/recall contra o gabarito (§5.2) ----------

def avaliar_gabarito(cur, dados, resultados):
    """Compara o que as regras detectaram com o que foi injetado de propósito.

    Só avalia os erros cujo registro está no lote processado agora. Marcar
    como não-detectado um erro de um lote antigo, que estas regras nem
    olharam, corromperia o recall.
    """
    no_lote = {
        (tabela, str(rec[CHAVE_PRIMARIA[tabela]]))
        for tabela, registros in dados.items()
        for rec in registros if rec[CHAVE_PRIMARIA[tabela]]
    }

    cur.execute("""
        SELECT erro_id, tabela_alvo, registro_id, campo_afetado, tipo_erro
          FROM gabarito.registro_erro_injetado
    """)
    injetados = [
        linha for linha in cur.fetchall() if (linha[1], linha[2]) in no_lote
    ]

    detectado_por_tipo = {
        tipo: {(c["tabela"], str(c["registro_id"]), c["campo"]) for c in violacoes}
        for tipo, (violacoes, _, _) in resultados.items()
    }

    marcacoes, relatorio = [], {}
    verdadeiros_por_tipo = {}

    for erro_id, tabela, registro_id, campo, tipo in injetados:
        chave = (tabela, registro_id, campo)
        acertou = chave in detectado_por_tipo.get(tipo, set())
        marcacoes.append((erro_id, acertou))
        verdadeiros_por_tipo.setdefault(tipo, set()).add(chave)
        r = relatorio.setdefault(tipo, {"injetados": 0, "tp": 0})
        r["injetados"] += 1
        r["tp"] += int(acertou)

    for tipo, detectados in detectado_por_tipo.items():
        r = relatorio.setdefault(tipo, {"injetados": 0, "tp": 0})
        r["detectados"] = len(detectados)
        r["fp"] = len(detectados - verdadeiros_por_tipo.get(tipo, set()))

    if marcacoes:
        psycopg2.extras.execute_values(cur, """
            UPDATE gabarito.registro_erro_injetado AS g
               SET detectado_pela_limpeza = v.detectado
              FROM (VALUES %s) AS v(erro_id, detectado)
             WHERE g.erro_id = v.erro_id
        """, marcacoes, template="(%s::uuid, %s::boolean)")

    return relatorio


def imprimir_relatorio(relatorio, promovidos, motivos):
    print("\nPrecision/recall por tipo de imperfeição (§5.2):")
    print(f"  {'tipo':<20} {'injet.':>6} {'detec.':>6} {'TP':>4} {'FP':>4} "
          f"{'recall':>7} {'precis.':>8}")
    for tipo in sorted(relatorio):
        r = relatorio[tipo]
        injetados, tp = r["injetados"], r["tp"]
        detectados, fp = r.get("detectados", 0), r.get("fp", 0)
        recall = tp / injetados if injetados else float("nan")
        precisao = tp / detectados if detectados else float("nan")
        print(f"  {tipo:<20} {injetados:>6} {detectados:>6} {tp:>4} {fp:>4} "
              f"{recall:>7.2f} {precisao:>8.2f}")

    print("\nPromoção staging -> tabelas finais:")
    for tabela, n in promovidos.items():
        print(f"  {tabela:<24} {n:>6} promovidas")
    print(f"  {'linhas rejeitadas':<24} {len(motivos):>6}")


# ---------- orquestração ----------

def main():
    data_avaliacao = date.today()
    conn = conectar()
    cur = conn.cursor()

    dados = carregar(cur)
    total = sum(len(v) for v in dados.values())
    if total == 0:
        print("Nada pendente no staging — pipeline não tem o que fazer.")
        cur.close()
        conn.close()
        return

    ctx = montar_contexto(dados, data_avaliacao)
    resultados = executar_regras(ctx)

    gravar_scores(cur, calcular_scores(resultados, data_avaliacao))
    motivos = decidir_rejeicoes(dados, resultados)
    promovidos = promover(cur, dados, motivos)
    marcar_staging(cur, dados, motivos)
    relatorio = avaliar_gabarito(cur, dados, resultados)

    conn.commit()
    cur.close()
    conn.close()

    print(f"Pipeline de qualidade: {total} linhas avaliadas em {data_avaliacao}.")
    imprimir_relatorio(relatorio, promovidos, motivos)


if __name__ == "__main__":
    main()

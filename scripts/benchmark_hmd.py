"""
Passo 3 — Benchmark externo (HMD, Austrália)

Mesma lógica do benchmark_ibge.py: compara o qx sintético por faixa
etária com o qx de referência, aqui extraído do ano mais recente (2021)
da série HMD Austrália (period life tables, 1x1).

Uso:
    python benchmark_hmd.py

Espera em docs/referencias/:
    hmd_australia_ambos_1x1.txt
    hmd_australia_homens_1x1.txt
    hmd_australia_mulheres_1x1.txt

Formato do arquivo (confirmado por print): linha de título, linha em
branco, cabeçalho "Year Age mx qx ax lx dx Lx Tx ex", dados separados
por espaço. Só usa Year e qx.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from db import conectar

PASTA_REFERENCIAS = Path(__file__).resolve().parent.parent / "docs" / "referencias"
ANO_REFERENCIA = 2021  # ano mais recente disponível na série (1921-2021)

FAIXAS = [(0, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 130)]


def carregar_hmd(nome_arquivo, ano=ANO_REFERENCIA):
    df = pd.read_csv(
        PASTA_REFERENCIAS / nome_arquivo,
        sep=r"\s+", skiprows=1,  # pula só a linha de título; branco e header
    )                            # são resolvidos automaticamente pelo pandas
    df["Age"] = pd.to_numeric(df["Age"], errors="coerce")  # "110+" vira NaN
    df = df.dropna(subset=["Age"])
    df["Age"] = df["Age"].astype(int)
    df = df[df["Year"] == ano]
    return df[["Age", "qx"]].rename(columns={"Age": "idade"})


def qx_hmd_por_faixa(df_hmd):
    resultado = {}
    for lo, hi in FAIXAS:
        fatia = df_hmd[(df_hmd["idade"] >= lo) & (df_hmd["idade"] <= hi)]
        resultado[(lo, hi)] = fatia["qx"].mean() if not fatia.empty else None
    return resultado


def qx_sintetico_por_faixa(cur, sexo=None):
    filtro_sexo = "AND p.sexo = %s" if sexo else ""
    params_base = [sexo] if sexo else []
    resultado = {}
    for lo, hi in FAIXAS:
        cur.execute(f"""
            SELECT COUNT(*) FILTER (WHERE e.tipo_saida = 'obito') AS obitos,
                   COUNT(*) AS exposicao
              FROM exposicao e
              JOIN participante p ON p.participante_id = e.participante_id
             WHERE e.idade_exata >= %s AND e.idade_exata < %s
             {filtro_sexo}
        """, [lo, hi + 1] + params_base)
        obitos, exposicao = cur.fetchone()
        resultado[(lo, hi)] = (obitos / exposicao) if exposicao else None
    return resultado


def main():
    df_total = carregar_hmd("hmd_australia_ambos_1x1.txt")
    df_m = carregar_hmd("hmd_australia_homens_1x1.txt")
    df_f = carregar_hmd("hmd_australia_mulheres_1x1.txt")

    qx_hmd_total = qx_hmd_por_faixa(df_total)
    qx_hmd_m = qx_hmd_por_faixa(df_m)
    qx_hmd_f = qx_hmd_por_faixa(df_f)

    conn = conectar()
    cur = conn.cursor()

    qx_sint_total = qx_sintetico_por_faixa(cur)
    qx_sint_m = qx_sintetico_por_faixa(cur, sexo="M")
    qx_sint_f = qx_sintetico_por_faixa(cur, sexo="F")

    linhas = [
        f"Ordem de grandeza qx sintético vs. HMD Austrália {ANO_REFERENCIA} "
        "(period life tables 1x1), por faixa:",
        "",
        "Total (ambos os sexos):",
    ]
    alertas = []
    for faixa in FAIXAS:
        s, h = qx_sint_total.get(faixa), qx_hmd_total.get(faixa)
        lo, hi = faixa
        if s is None or h is None or h == 0:
            linhas.append(f"  {lo:>3}-{hi:<3}: dado insuficiente")
            continue
        razao = s / h
        linhas.append(f"  {lo:>3}-{hi:<3}: sintético={s:.4f}  hmd={h:.4f}  razao={razao:.1f}x")
        if razao > 10 or razao < 0.1:
            alertas.append(f"total {lo}-{hi}: {razao:.1f}x")

    for rotulo, qx_sint, qx_hmd in [("Homens", qx_sint_m, qx_hmd_m), ("Mulheres", qx_sint_f, qx_hmd_f)]:
        linhas += ["", f"{rotulo}:"]
        for faixa in FAIXAS:
            s, h = qx_sint.get(faixa), qx_hmd.get(faixa)
            lo, hi = faixa
            if s is None or h is None or h == 0:
                linhas.append(f"  {lo:>3}-{hi:<3}: dado insuficiente")
                continue
            razao = s / h
            linhas.append(f"  {lo:>3}-{hi:<3}: sintético={s:.4f}  hmd={h:.4f}  razao={razao:.1f}x")
            if razao > 10 or razao < 0.1:
                alertas.append(f"{rotulo.lower()} {lo}-{hi}: {razao:.1f}x")

    veredito = ("ALERTA: " + "; ".join(alertas)) if alertas else \
        "Nenhuma faixa destoa mais de 10x do HMD Austrália — plausível como ordem de grandeza."
    linhas += [
        "",
        veredito,
        "",
        "Nota: HMD não inclui o Brasil; Austrália usada como referência "
        "metodológica internacional (não como baseline demográfico direto, "
        "esse papel é do IBGE).",
    ]
    resumo = "\n".join(linhas)
    print(resumo)

    cur.execute("""
        UPDATE referencia_externa
           SET versao_tabua = %s,
               resultado_benchmark = %s,
               data_consulta = COALESCE(data_consulta, %s)
         WHERE fonte = 'HMD'
    """, (f"Australia {ANO_REFERENCIA} (period 1x1)", resumo, date.today()))
    conn.commit()
    cur.close()
    conn.close()
    print("\nresultado_benchmark atualizado em referencia_externa (fonte HMD).")


if __name__ == "__main__":
    main()

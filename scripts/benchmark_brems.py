"""
Passo 3 — Benchmark externo (BR-EMS)

Compara o qx sintético por faixa etária/sexo com a tábua BR-EMSsb
v.2026 (sobrevivência, vigência 2026-2031 — a que vale hoje), lida
direto das abas "BR-EMSsb-2026-m" e "BR-EMSsb-2026-f" do workbook único
baixado da SUSEP/FenaPrevi.

Uso:
    python benchmark_brems.py

Espera em docs/referencias/:
    br_ems_2026_sobrevivencia.xlsx (com as abas BR-EMSsb-2026-m e -f)

Formato de cada aba (confirmado por print): linha 1 = título, linha 2 =
cabeçalho (Idade, qx, IC95%inf, IC95%sup, lx, ex), dados a partir da
linha 3. qx já vem como probabilidade direta (não "por mil").
"""

from datetime import date
from pathlib import Path

import pandas as pd

from db import conectar

ARQUIVO = Path(__file__).resolve().parent.parent / "docs" / "referencias" / "br_ems_2026_sobrevivencia.xlsx"
FAIXAS = [(0, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 130)]


def carregar_brems(aba):
    df = pd.read_excel(
        ARQUIVO, sheet_name=aba, header=None, skiprows=2,
        usecols="A:B", names=["idade", "qx"],
    )
    df["idade"] = pd.to_numeric(df["idade"], errors="coerce")
    df = df.dropna(subset=["idade"])
    df["idade"] = df["idade"].astype(int)
    return df[["idade", "qx"]]


def qx_por_faixa(df):
    resultado = {}
    for lo, hi in FAIXAS:
        fatia = df[(df["idade"] >= lo) & (df["idade"] <= hi)]
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


def comparar(linhas, alertas, rotulo, qx_sint, qx_ref):
    linhas.append(f"\n{rotulo}:")
    for lo, hi in FAIXAS:
        s, r = qx_sint.get((lo, hi)), qx_ref.get((lo, hi))
        if s is None or r is None or r == 0:
            linhas.append(f"  {lo:>3}-{hi:<3}: dado insuficiente")
            continue
        razao = s / r
        linhas.append(f"  {lo:>3}-{hi:<3}: sintético={s:.4f}  br-ems={r:.4f}  razao={razao:.1f}x")
        if razao > 10 or razao < 0.1:
            alertas.append(f"{rotulo.lower()} {lo}-{hi}: {razao:.1f}x")


def main():
    qx_brems_m = qx_por_faixa(carregar_brems("BR-EMSsb-2026-m"))
    qx_brems_f = qx_por_faixa(carregar_brems("BR-EMSsb-2026-f"))

    conn = conectar()
    cur = conn.cursor()
    qx_sint_m = qx_sintetico_por_faixa(cur, sexo="M")
    qx_sint_f = qx_sintetico_por_faixa(cur, sexo="F")

    linhas = ["Ordem de grandeza qx sintético vs. BR-EMSsb v.2026 (sobrevivência), por faixa e sexo:"]
    alertas = []
    comparar(linhas, alertas, "Homens", qx_sint_m, qx_brems_m)
    comparar(linhas, alertas, "Mulheres", qx_sint_f, qx_brems_f)

    veredito = ("ALERTA: " + "; ".join(alertas)) if alertas else \
        "Nenhuma faixa destoa mais de 10x da BR-EMSsb 2026 — plausível como ordem de grandeza."
    linhas += [
        "", veredito, "",
        "Nota: BR-EMSsb é tábua de sobrevivência (uso em previdência "
        "complementar), vigência 2026-2031 — a versão que vale na data "
        "deste benchmark.",
    ]
    resumo = "\n".join(linhas)
    print(resumo)

    cur.execute("""
        UPDATE referencia_externa
           SET versao_tabua = %s,
               resultado_benchmark = %s,
               data_consulta = COALESCE(data_consulta, %s)
         WHERE fonte = 'BR_EMS'
    """, ("BR-EMSsb v.2026 (sobrevivência)", resumo, date.today()))
    conn.commit()
    cur.close()
    conn.close()
    print("\nresultado_benchmark atualizado em referencia_externa (fonte BR_EMS).")


if __name__ == "__main__":
    main()

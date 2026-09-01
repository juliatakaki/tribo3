"""
Passo 3 — Benchmark externo (SOA)

Compara o qx sintético por faixa etária/sexo com a RP-2014 Rates-Total
Dataset (mortalidade de participante ativo, EUA), tabelas 3123 (Male) e
3124 (Female) do mort.soa.org.

Uso:
    python benchmark_soa.py

Espera em docs/referencias/:
    soa_rp2014_homens.xls
    soa_rp2014_mulheres.xls

Formato (confirmado por print): 23 linhas de metadados, linha 24 é
cabeçalho de tabela dinâmica, dados a partir da linha 25. Coluna A =
idade (18 a 80 nesta tabela — é mortalidade de ativo, não cobre idades
de aposentadoria avançada), coluna B = qx como probabilidade direta.
"""

from datetime import date
from pathlib import Path

import pandas as pd

from db import conectar

PASTA_REFERENCIAS = Path(__file__).resolve().parent.parent / "docs" / "referencias"
FAIXAS = [(0, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 130)]


def carregar_soa(nome_arquivo):
    df = pd.read_excel(
        PASTA_REFERENCIAS / nome_arquivo, sheet_name=0, header=None,
        skiprows=24, usecols="A:B", names=["idade", "qx"],
    )
    df["idade"] = pd.to_numeric(df["idade"], errors="coerce")
    df["qx"] = pd.to_numeric(df["qx"], errors="coerce")
    df = df.dropna(subset=["idade", "qx"])
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
        linhas.append(f"  {lo:>3}-{hi:<3}: sintético={s:.4f}  soa={r:.4f}  razao={razao:.1f}x")
        if razao > 10 or razao < 0.1:
            alertas.append(f"{rotulo.lower()} {lo}-{hi}: {razao:.1f}x")


def main():
    qx_soa_m = qx_por_faixa(carregar_soa("soa_rp2014_homens.xls"))
    qx_soa_f = qx_por_faixa(carregar_soa("soa_rp2014_mulheres.xls"))

    conn = conectar()
    cur = conn.cursor()
    qx_sint_m = qx_sintetico_por_faixa(cur, sexo="M")
    qx_sint_f = qx_sintetico_por_faixa(cur, sexo="F")

    linhas = ["Ordem de grandeza qx sintético vs. SOA RP-2014 Total Dataset, por faixa e sexo:"]
    alertas = []
    comparar(linhas, alertas, "Homens", qx_sint_m, qx_soa_m)
    comparar(linhas, alertas, "Mulheres", qx_sint_f, qx_soa_f)

    veredito = ("ALERTA: " + "; ".join(alertas)) if alertas else \
        "Nenhuma faixa destoa mais de 10x da SOA RP-2014 — plausível como ordem de grandeza."
    linhas += [
        "", veredito, "",
        "Nota: RP-2014 é tábua de mortalidade de ativo (EUA), cobre idade "
        "18-80. Usada como referência metodológica internacional "
        "adicional, não como baseline demográfico direto (esse papel é "
        "do IBGE).",
    ]
    resumo = "\n".join(linhas)
    print(resumo)

    cur.execute("""
        UPDATE referencia_externa
           SET versao_tabua = %s,
               resultado_benchmark = %s,
               data_consulta = COALESCE(data_consulta, %s)
         WHERE fonte = 'SOA'
    """, ("RP-2014 Rates-Total Dataset (Employee)", resumo, date.today()))
    conn.commit()
    cur.close()
    conn.close()
    print("\nresultado_benchmark atualizado em referencia_externa (fonte SOA).")


if __name__ == "__main__":
    main()

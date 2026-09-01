"""
Passo 3 — Benchmark externo (IBGE)

Calcula o qx sintético por faixa etária e sexo a partir de `exposicao` +
`participante`, compara com a Tábua Completa de Mortalidade IBGE 2024
(Ambos, Homens, Mulheres) e grava o resumo em
referencia_externa.resultado_benchmark (fonte = 'IBGE').

Uso:
    python benchmark_ibge.py

Espera os 3 arquivos baixados em docs/referencias/:
    ibge_2024_ambos.xlsx
    ibge_2024_homens.xlsx
    ibge_2024_mulheres.xlsx

Layout de cada planilha (confirmado por print da usuária): dados começam
na linha 7 (índice 6, 0-based), coluna A = idade exata, coluna B = qx em
"por mil" (dividir por 1000 para virar probabilidade).
"""

from datetime import date
from pathlib import Path

import pandas as pd

from db import conectar

PASTA_REFERENCIAS = Path(__file__).resolve().parent.parent / "docs" / "referencias"

# Faixas usadas para a comparação de ordem de grandeza — bandas largas
# porque a massa sintética tem só ~300 participantes; qx por idade exata
# ficaria estatisticamente vazio na maioria das idades.
FAIXAS = [(0, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 130)]


def carregar_ibge(nome_arquivo):
    """Lê idade (coluna A) e qx em fração (coluna B / 1000)."""
    df = pd.read_excel(
        PASTA_REFERENCIAS / nome_arquivo,
        sheet_name=0, header=None, skiprows=6,
        usecols="A:B", names=["idade", "qx_por_mil"],
    )
    df = df.dropna(subset=["idade"])
    df["idade"] = pd.to_numeric(df["idade"], errors="coerce")
    df = df.dropna(subset=["idade"])  # descarta linhas de nota/rodapé
    df["idade"] = df["idade"].astype(int)
    df["qx"] = df["qx_por_mil"] / 1000
    return df[["idade", "qx"]]


def qx_ibge_por_faixa(df_ibge):
    """Média simples do qx dentro de cada faixa — só ordem de grandeza,
    não uma taxa central de mortalidade ponderada por exposição real."""
    resultado = {}
    for lo, hi in FAIXAS:
        fatia = df_ibge[(df_ibge["idade"] >= lo) & (df_ibge["idade"] <= hi)]
        resultado[(lo, hi)] = fatia["qx"].mean() if not fatia.empty else None
    return resultado


def qx_sintetico_por_faixa(cur, sexo=None):
    """qx sintético = óbitos / total de linhas de exposição, por faixa.
    sexo=None agrega os dois sexos (compara com a tábua 'Ambos')."""
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


def montar_resumo(qx_sint, qx_ibge):
    linhas = ["Ordem de grandeza qx sintético vs. IBGE 2024 (ambos os sexos), por faixa:"]
    alertas = []
    for faixa in FAIXAS:
        s, i = qx_sint.get(faixa), qx_ibge.get(faixa)
        lo, hi = faixa
        if s is None or i is None or i == 0:
            linhas.append(f"  {lo:>3}-{hi:<3}: dado insuficiente para comparar")
            continue
        razao = s / i
        linhas.append(f"  {lo:>3}-{hi:<3}: sintético={s:.4f}  ibge={i:.4f}  razao={razao:.1f}x")
        if razao > 10 or razao < 0.1:
            alertas.append(f"faixa {lo}-{hi} destoa {razao:.1f}x da IBGE")
    veredito = ("ALERTA: " + "; ".join(alertas)) if alertas else \
        "Nenhuma faixa destoa mais de 10x da IBGE — plausível como ordem de grandeza."
    linhas.append("")
    linhas.append(veredito)
    return "\n".join(linhas)


def main():
    df_ambos = carregar_ibge("ibge_2024_ambos.xlsx")
    qx_ibge = qx_ibge_por_faixa(df_ambos)

    conn = conectar()
    cur = conn.cursor()

    qx_sint = qx_sintetico_por_faixa(cur)
    resumo = montar_resumo(qx_sint, qx_ibge)
    print(resumo)

    cur.execute("""
        UPDATE referencia_externa
           SET resultado_benchmark = %s,
               data_consulta = COALESCE(data_consulta, %s)
         WHERE fonte = 'IBGE'
    """, (resumo, date.today()))
    conn.commit()
    cur.close()
    conn.close()
    print("\nresultado_benchmark atualizado em referencia_externa.")


if __name__ == "__main__":
    main()

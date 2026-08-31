"""
Gera o relatório de qualidade e tratamento de exceções (§5) em arquivo,
a partir do que pipeline_qualidade.py já gravou no banco.

Não reprocessa nada — só lê o estado atual de:
  - gabarito.registro_erro_injetado (recall por tipo de imperfeição)
  - data_quality_score              (score médio por dimensão/granularidade)
  - staging.v_rejeitados            (exceções e motivo da rejeição)

Por isso não recalcula falsos positivos/precisão (isso exigiria repetir
a execução das regras) — cobre recall e o tratamento de exceções, que é
o que fica persistido no banco depois de rodar pipeline_qualidade.py.

Uso:
    python gerar_relatorio.py
    (rodar depois de pipeline_qualidade.py, contra o mesmo banco)
"""

from datetime import date
from pathlib import Path

from db import conectar

# Caminho fixo relativo a ESTE arquivo, não à pasta de onde o comando é
# chamado — assim funciona igual rodando de tribo3\ ou de tribo3\scripts\.
PASTA_RELATORIOS = Path(__file__).resolve().parent.parent / "docs" / "relatorios"


def recall_por_tipo(cur):
    cur.execute("""
        SELECT tipo_erro,
               COUNT(*) AS injetados,
               COUNT(*) FILTER (WHERE detectado_pela_limpeza) AS detectados
          FROM gabarito.registro_erro_injetado
         GROUP BY tipo_erro
         ORDER BY tipo_erro
    """)
    return cur.fetchall()


def score_medio(cur):
    cur.execute("""
        SELECT granularidade, dimensao_qualidade,
               ROUND(AVG(score), 3) AS score_medio,
               COUNT(*) AS n_avaliacoes
          FROM data_quality_score
         GROUP BY granularidade, dimensao_qualidade
         ORDER BY granularidade, dimensao_qualidade
    """)
    return cur.fetchall()


def exceptions_rejeitadas(cur):
    cur.execute("""
        SELECT tabela_origem, unnest(motivos_rejeicao) AS motivo, COUNT(*)
          FROM staging.v_rejeitados
         GROUP BY tabela_origem, motivo
         ORDER BY tabela_origem, motivo
    """)
    return cur.fetchall()


def total_rejeitados(cur):
    cur.execute("SELECT COUNT(*) FROM staging.v_rejeitados")
    return cur.fetchone()[0]


def montar_markdown(recall, scores, excecoes, n_rejeitados):
    linhas = [
        f"# Relatório de qualidade — {date.today().isoformat()}",
        "",
        "## 1. Detecção de imperfeições (recall por tipo)",
        "",
        "Compara o que foi injetado de propósito (`gabarito.registro_erro_injetado`)",
        "com o que as 9 regras automatizadas detectaram.",
        "",
        "| tipo de erro | injetados | detectados | recall |",
        "|---|---|---|---|",
    ]
    for tipo, injetados, detectados in recall:
        recall_pct = f"{detectados / injetados:.0%}" if injetados else "n/d"
        linhas.append(f"| {tipo} | {injetados} | {detectados} | {recall_pct} |")

    linhas += [
        "",
        "## 2. Data Quality Score médio por dimensão e granularidade",
        "",
        "| granularidade | dimensão | score médio | nº avaliações |",
        "|---|---|---|---|",
    ]
    for granularidade, dimensao, score_med, n in scores:
        linhas.append(f"| {granularidade} | {dimensao} | {score_med} | {n} |")

    linhas += [
        "",
        "## 3. Tratamento de exceções",
        "",
        f"Total de linhas rejeitadas nesta rodada (não promovidas para as ",
        f"tabelas finais): **{n_rejeitados}**.",
        "",
        "Rejeitadas por tabela e motivo:",
        "",
        "| tabela | motivo (código da regra) | ocorrências |",
        "|---|---|---|",
    ]
    for tabela, motivo, n in excecoes:
        linhas.append(f"| {tabela} | {motivo} | {n} |")

    linhas += [
        "",
        "## Notas",
        "",
        "- Este relatório cobre recall (detecção) e tratamento de exceções,",
        "  lidos do estado persistido no banco. Não recalcula falsos",
        "  positivos/precisão — isso é impresso no console ao rodar",
        "  `pipeline_qualidade.py` diretamente.",
        "- Rodar de novo após qualquer nova execução do gerador ou do",
        "  pipeline para atualizar os números.",
    ]
    return "\n".join(linhas)


def main():
    conn = conectar()
    cur = conn.cursor()

    recall = recall_por_tipo(cur)
    scores = score_medio(cur)
    excecoes = exceptions_rejeitadas(cur)
    n_rejeitados = total_rejeitados(cur)

    cur.close()
    conn.close()

    markdown = montar_markdown(recall, scores, excecoes, n_rejeitados)

    PASTA_RELATORIOS.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_RELATORIOS / f"relatorio_{date.today().isoformat()}.md"
    caminho.write_text(markdown, encoding="utf-8")

    print(f"Relatório salvo em {caminho}")


if __name__ == "__main__":
    main()

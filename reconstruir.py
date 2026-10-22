"""Reconstrói o histórico diário desde o início do campeonato pelas partidas ranqueadas.

Uso:
    RIOT_API_KEY=RGAPI-... python reconstruir.py

A API da Riot não guarda o elo de dias passados, então o script parte do elo de
agora e volta partida por partida. Vitórias e derrotas por dia são exatas; o PDL
é estimado com um ganho/perda fixo por partida. As linhas geradas ficam marcadas
como estimadas e nunca substituem uma coleta real. As partidas baixadas ficam
em dados/partidas.json e alimentam a página de desempenho.
"""

import json
import os
import sys
from datetime import datetime, timedelta

import coletar

GANHO_VITORIA = 22
PERDA_DERROTA = 20
PAUSA = 1.3  # a chave de desenvolvimento aceita 100 chamadas a cada 2 minutos


def de_pontos(p):
    if p >= len(coletar.TIERS) * 400:
        return "MASTER", "I", p - len(coletar.TIERS) * 400
    return coletar.TIERS[p // 400], ["IV", "III", "II", "I"][(p % 400) // 100], p % 100


def reconstruir(jogador, partidas, hoje, chave):
    puuid = coletar.buscar_puuid(jogador, chave)
    atual = coletar.buscar_elo(jogador, chave, puuid)
    coletar.atualizar_partidas(jogador, puuid, chave, partidas, pausa=PAUSA)
    if atual["pontos"] is None:
        print(f"[pulado] {jogador['nome']}: sem rank na SoloQ")
        return []

    rid = jogador["riot_id"].lower()
    minhas = sorted(
        ((datetime.fromisoformat(p["fim"]), p["vitoria"]) for p in partidas
         if p["riot_id"].lower() == rid and not p["remake"]),
        reverse=True,
    )
    p, v, d = atual["pontos"], atual["vitorias"], atual["derrotas"]
    linhas, i = [], 0
    dia = hoje - timedelta(days=1)
    while dia >= coletar.INICIO_CAMPEONATO:
        # Desfaz as partidas que terminaram depois do fim deste dia.
        while i < len(minhas) and minhas[i][0].date() > dia:
            if minhas[i][1]:
                p, v = max(0, p - GANHO_VITORIA), v - 1
            else:
                p, d = p + PERDA_DERROTA, d - 1
            i += 1
        tier, rank, lp = de_pontos(p)
        linhas.append({"data": dia.isoformat(), "nome": jogador["nome"], "riot_id": jogador["riot_id"],
                       "tier": tier, "rank": rank, "lp": lp, "vitorias": v, "derrotas": d,
                       "pontos": p, "estimado": "1"})
        dia -= timedelta(days=1)

    vit = sum(1 for _, w in minhas if w)
    print(f"[ok] {jogador['nome']}: {len(minhas)} partidas desde "
          f"{coletar.INICIO_CAMPEONATO:%d/%m} ({vit}V {len(minhas) - vit}D)")
    return linhas


def main():
    chave = os.environ.get("RIOT_API_KEY", "").strip()
    if not chave:
        sys.exit("Defina a variável de ambiente RIOT_API_KEY.")

    jogadores = json.loads(coletar.ARQ_JOGADORES.read_text(encoding="utf-8"))
    agora = datetime.now(coletar.BRASILIA)
    linhas = coletar.ler_historico()
    partidas = coletar.ler_partidas()

    for j in jogadores:
        try:
            novas = reconstruir(j, partidas, agora.date(), chave)
        except coletar.ChaveInvalida as e:
            sys.exit(str(e))
        except Exception as e:
            print(f"[erro] {j['nome']} ({j['riot_id']}): {e}")
            continue
        rid = j["riot_id"].lower()
        # Estimativas antigas do jogador saem; coletas reais ficam e têm prioridade.
        linhas = [l for l in linhas if not (l["riot_id"].lower() == rid and l.get("estimado") == "1")]
        reais = {l["data"] for l in linhas if l["riot_id"].lower() == rid}
        linhas += [n for n in novas if n["data"] not in reais]
        coletar.salvar_partidas(partidas)  # salva a cada jogador para não perder downloads

    coletar.salvar_historico(linhas)
    coletar.gerar_site(linhas, jogadores, agora)


if __name__ == "__main__":
    main()

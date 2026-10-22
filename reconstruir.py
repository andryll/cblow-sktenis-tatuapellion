"""Reconstrói o histórico diário a partir das partidas ranqueadas (match-v5).

Uso:
    RIOT_API_KEY=RGAPI-... python reconstruir.py [AAAA-MM-DD]

A API da Riot não guarda o elo de dias passados, então o script parte do elo de
agora e volta partida por partida. Vitórias e derrotas por dia são exatas; o PDL
é estimado com um ganho/perda fixo por partida. As linhas geradas ficam marcadas
como estimadas e nunca substituem uma coleta real.
"""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta

import coletar

INICIO_PADRAO = "2026-10-02"  # início do CBLOW
GANHO_VITORIA = 22
PERDA_DERROTA = 20
FILA_SOLO = 420
PAUSA = 1.3  # a chave de desenvolvimento aceita 100 chamadas a cada 2 minutos


def chamar(url, chave):
    time.sleep(PAUSA)
    return coletar.chamar_api(url, chave)


def de_pontos(p):
    if p >= len(coletar.TIERS) * 400:
        return "MASTER", "I", p - len(coletar.TIERS) * 400
    return coletar.TIERS[p // 400], ["IV", "III", "II", "I"][(p % 400) // 100], p % 100


def partidas_desde(jogador, puuid, inicio, chave):
    _, regiao = coletar.rotas(jogador)
    base = f"https://{regiao}.api.riotgames.com/lol/match/v5/matches"
    inicio_ts = int(datetime.combine(inicio, datetime.min.time(), coletar.BRASILIA).timestamp())

    ids, pagina = [], 0
    while True:
        lote = chamar(f"{base}/by-puuid/{puuid}/ids?queue={FILA_SOLO}&startTime={inicio_ts}"
                      f"&start={pagina * 100}&count=100", chave) or []
        ids += lote
        if len(lote) < 100:
            break
        pagina += 1

    partidas = []
    for mid in ids:
        info = (chamar(f"{base}/{mid}", chave) or {}).get("info")
        if not info:
            continue
        eu = next((p for p in info["participants"] if p["puuid"] == puuid), None)
        # Remake não vale PDL nem conta como vitória/derrota.
        if eu is None or eu.get("gameEndedInEarlySurrender") or info["gameDuration"] < 300:
            continue
        fim_ms = info.get("gameEndTimestamp") or info["gameStartTimestamp"] + info["gameDuration"] * 1000
        partidas.append((datetime.fromtimestamp(fim_ms / 1000, coletar.BRASILIA), eu["win"]))
    return sorted(partidas, reverse=True)


def reconstruir(jogador, inicio, hoje, chave):
    puuid = coletar.buscar_puuid(jogador, chave)
    atual = coletar.buscar_elo(jogador, chave, puuid)
    if atual["pontos"] is None:
        print(f"[pulado] {jogador['nome']}: sem rank na SoloQ")
        return []

    partidas = partidas_desde(jogador, puuid, inicio, chave)
    p, v, d = atual["pontos"], atual["vitorias"], atual["derrotas"]
    linhas, i = [], 0
    dia = hoje - timedelta(days=1)
    while dia >= inicio:
        # Desfaz as partidas que terminaram depois do fim deste dia.
        while i < len(partidas) and partidas[i][0].date() > dia:
            if partidas[i][1]:
                p, v = max(0, p - GANHO_VITORIA), v - 1
            else:
                p, d = p + PERDA_DERROTA, d - 1
            i += 1
        tier, rank, lp = de_pontos(p)
        linhas.append({"data": dia.isoformat(), "nome": jogador["nome"], "riot_id": jogador["riot_id"],
                       "tier": tier, "rank": rank, "lp": lp, "vitorias": v, "derrotas": d,
                       "pontos": p, "estimado": "1"})
        dia -= timedelta(days=1)

    vit = sum(1 for _, w in partidas if w)
    print(f"[ok] {jogador['nome']}: {len(partidas)} partidas desde {inicio:%d/%m} ({vit}V {len(partidas) - vit}D)")
    return linhas


def main():
    chave = os.environ.get("RIOT_API_KEY", "").strip()
    if not chave:
        sys.exit("Defina a variável de ambiente RIOT_API_KEY.")
    inicio = date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else INICIO_PADRAO)

    jogadores = json.loads(coletar.ARQ_JOGADORES.read_text(encoding="utf-8"))
    agora = datetime.now(coletar.BRASILIA)
    linhas = coletar.ler_historico()

    for j in jogadores:
        try:
            novas = reconstruir(j, inicio, agora.date(), chave)
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

    coletar.salvar_historico(linhas)
    coletar.gerar_site(linhas, jogadores, agora)


if __name__ == "__main__":
    main()

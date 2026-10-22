"""Coleta o elo de SoloQ dos jogadores listados em jogadores.json.

Uso:
    RIOT_API_KEY=RGAPI-... python coletar.py

Grava uma linha por jogador por dia em dados/historico.csv (rodar de novo no
mesmo dia substitui a linha do dia) e gera site/dados.json para os gráficos.
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).parent
ARQ_JOGADORES = RAIZ / "jogadores.json"
ARQ_HISTORICO = RAIZ / "dados" / "historico.csv"
ARQ_SITE = RAIZ / "site" / "dados.json"

BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019

CAMPOS = ["data", "nome", "riot_id", "tier", "rank", "lp", "vitorias", "derrotas", "pontos"]

# Escala única para o gráfico: cada divisão vale 100 pontos (Ferro IV 0 PDL = 0).
# Do Mestre pra cima não há divisões, então soma-se o PDL a partir de 2800.
TIERS = ["IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND"]
APEX = ["MASTER", "GRANDMASTER", "CHALLENGER"]
DIVISOES = {"IV": 0, "III": 1, "II": 2, "I": 3}

# Roteamento regional da account-v1 a partir da plataforma do jogador.
REGIAO_CONTA = {
    "br1": "americas", "na1": "americas", "la1": "americas", "la2": "americas",
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe",
    "kr": "asia", "jp1": "asia",
}


class ChaveInvalida(Exception):
    pass


def chamar_api(url, chave, tentativas=4):
    req = urllib.request.Request(url, headers={"X-Riot-Token": chave})
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise ChaveInvalida(f"HTTP {e.code}: chave da Riot inválida ou expirada")
            if e.code == 404:
                return None
            if e.code == 429 or e.code >= 500:
                time.sleep(int(e.headers.get("Retry-After", 5)))
                continue
            raise
    raise RuntimeError(f"Falhou depois de {tentativas} tentativas: {url}")


def pontos(tier, rank, lp):
    if tier in TIERS:
        return TIERS.index(tier) * 400 + DIVISOES[rank] * 100 + lp
    if tier in APEX:
        return len(TIERS) * 400 + lp
    return None


def buscar_elo(jogador, chave):
    nome_jogo, tag = jogador["riot_id"].rsplit("#", 1)
    plataforma = jogador.get("servidor", "br1").lower()
    regiao = REGIAO_CONTA.get(plataforma, "americas")

    conta = chamar_api(
        f"https://{regiao}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
        f"{urllib.parse.quote(nome_jogo)}/{urllib.parse.quote(tag)}",
        chave,
    )
    if conta is None:
        raise LookupError(f"Riot ID não encontrado: {jogador['riot_id']}")

    entradas = chamar_api(
        f"https://{plataforma}.api.riotgames.com/lol/league/v4/entries/by-puuid/{conta['puuid']}",
        chave,
    ) or []
    solo = next((e for e in entradas if e["queueType"] == "RANKED_SOLO_5x5"), None)
    if solo is None:
        return {"tier": "UNRANKED", "rank": "", "lp": 0, "vitorias": 0, "derrotas": 0, "pontos": None}
    return {
        "tier": solo["tier"],
        "rank": solo["rank"],
        "lp": solo["leaguePoints"],
        "vitorias": solo["wins"],
        "derrotas": solo["losses"],
        "pontos": pontos(solo["tier"], solo["rank"], solo["leaguePoints"]),
    }


def ler_historico():
    if not ARQ_HISTORICO.exists():
        return []
    with ARQ_HISTORICO.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def salvar_historico(linhas):
    ARQ_HISTORICO.parent.mkdir(exist_ok=True)
    linhas.sort(key=lambda l: (l["data"], l["nome"].lower()))
    with ARQ_HISTORICO.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS)
        w.writeheader()
        w.writerows(linhas)


def gerar_site(linhas, jogadores, agora):
    def inteiro(v):
        return int(v) if v not in ("", None) else None

    saida = {"atualizado_em": agora.isoformat(timespec="minutes"), "jogadores": []}
    for j in jogadores:
        hist = [l for l in linhas if l["riot_id"].lower() == j["riot_id"].lower()]
        saida["jogadores"].append({
            "nome": j["nome"],
            "riot_id": j["riot_id"],
            "funcao": j.get("funcao", ""),
            "historico": [
                {
                    "data": l["data"],
                    "tier": l["tier"],
                    "rank": l["rank"],
                    "lp": inteiro(l["lp"]),
                    "vitorias": inteiro(l["vitorias"]),
                    "derrotas": inteiro(l["derrotas"]),
                    "pontos": inteiro(l["pontos"]),
                }
                for l in hist
            ],
        })
    ARQ_SITE.parent.mkdir(exist_ok=True)
    ARQ_SITE.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    chave = os.environ.get("RIOT_API_KEY", "").strip()
    if not chave:
        sys.exit("Defina a variável de ambiente RIOT_API_KEY.")

    jogadores = json.loads(ARQ_JOGADORES.read_text(encoding="utf-8"))
    agora = datetime.now(BRASILIA)
    hoje = agora.date().isoformat()

    linhas = ler_historico()
    falhas = 0
    for j in jogadores:
        try:
            elo = buscar_elo(j, chave)
        except ChaveInvalida as e:
            sys.exit(str(e))
        except Exception as e:
            falhas += 1
            print(f"[erro] {j['nome']} ({j['riot_id']}): {e}")
            continue

        linhas = [l for l in linhas if not (l["data"] == hoje and l["riot_id"].lower() == j["riot_id"].lower())]
        linhas.append({"data": hoje, "nome": j["nome"], "riot_id": j["riot_id"],
                       **{k: ("" if v is None else v) for k, v in elo.items()}})
        desc = "sem rank" if elo["pontos"] is None else f"{elo['tier']} {elo['rank']} {elo['lp']} PDL"
        print(f"[ok] {j['nome']}: {desc} ({elo['vitorias']}V {elo['derrotas']}D)")

    salvar_historico(linhas)
    gerar_site(linhas, jogadores, agora)
    print(f"{len(jogadores) - falhas}/{len(jogadores)} jogadores atualizados em {hoje}.")
    if falhas == len(jogadores):
        sys.exit(1)


if __name__ == "__main__":
    main()

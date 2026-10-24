"""Coleta o elo de SoloQ dos jogadores listados em jogadores.json.

Uso:
    RIOT_API_KEY=RGAPI-... python coletar.py

Grava uma linha por jogador por dia em dados/historico.csv (rodar de novo no
mesmo dia substitui a linha do dia), baixa as partidas novas (solo, flex e
personalizadas) desde o início do campeonato para dados/partidas.json e gera os
arquivos do site.
"""

import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).parent
ARQ_JOGADORES = RAIZ / "jogadores.json"
ARQ_HISTORICO = RAIZ / "dados" / "historico.csv"
ARQ_PARTIDAS = RAIZ / "dados" / "partidas.json"
ARQ_SITE = RAIZ / "site" / "dados.json"
ARQ_SITE_PARTIDAS = RAIZ / "site" / "partidas.json"
PASTA_FOTOS = RAIZ / "site" / "fotos"
URL_FOTOS = "https://cdn.cblow.xyz/jogadores"  # fotos oficiais do CBLOW

INICIO_CAMPEONATO = date(2026, 10, 2)
# queueId da partida -> fila guardada em partidas.json. Personalizada (inclusive com
# código de torneio) é 0; a Riot só devolve as personalizadas que a API expõe.
FILAS = {420: "solo", 440: "flex", 0: "personalizada"}
# Filtros da lista de partidas por jogador; os resultados são somados.
BUSCAS = ["queue=420", "queue=440", "queue=0", "type=tourney"]

BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019

CAMPOS = ["data", "nome", "riot_id", "tier", "rank", "lp", "vitorias", "derrotas", "pontos", "estimado"]

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
    # O Cloudflare na frente da API bloqueia o User-Agent padrão do urllib (erro 1010).
    req = urllib.request.Request(url, headers={"X-Riot-Token": chave, "User-Agent": "cblow-soloq-tracker/1.0"})
    for _ in range(tentativas):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                corpo = e.read().decode("utf-8", "replace")[:200]
                raise ChaveInvalida(f"HTTP {e.code} da API da Riot (chave inválida ou expirada?): {corpo}")
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


def rotas(jogador):
    plataforma = jogador.get("servidor", "br1").lower()
    return plataforma, REGIAO_CONTA.get(plataforma, "americas")


def buscar_puuid(jogador, chave):
    nome_jogo, tag = jogador["riot_id"].rsplit("#", 1)
    _, regiao = rotas(jogador)
    conta = chamar_api(
        f"https://{regiao}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/"
        f"{urllib.parse.quote(nome_jogo)}/{urllib.parse.quote(tag)}",
        chave,
    )
    if conta is None:
        raise LookupError(f"Riot ID não encontrado: {jogador['riot_id']}")
    return conta["puuid"]


def buscar_elo(jogador, chave, puuid=None):
    plataforma, _ = rotas(jogador)
    puuid = puuid or buscar_puuid(jogador, chave)
    entradas = chamar_api(
        f"https://{plataforma}.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}",
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


def ler_partidas():
    if not ARQ_PARTIDAS.exists():
        return []
    partidas = json.loads(ARQ_PARTIDAS.read_text(encoding="utf-8"))
    for p in partidas:
        p.setdefault("fila", "solo")  # antes só se baixava solo
    return partidas


def salvar_partidas(partidas):
    ARQ_PARTIDAS.parent.mkdir(exist_ok=True)
    partidas.sort(key=lambda p: (p["fim"], p["riot_id"].lower()))
    ARQ_PARTIDAS.write_text(json.dumps(partidas, ensure_ascii=False, indent=0), encoding="utf-8")


def resumir_partida(mid, info, puuid, riot_id):
    eu = next((p for p in info["participants"] if p["puuid"] == puuid), None)
    if eu is None:
        return None
    fim_ms = info.get("gameEndTimestamp") or info["gameStartTimestamp"] + info["gameDuration"] * 1000
    return {
        "id": mid,
        "riot_id": riot_id,
        "fila": FILAS[info["queueId"]],
        "fim": datetime.fromtimestamp(fim_ms / 1000, BRASILIA).isoformat(timespec="minutes"),
        "duracao": info["gameDuration"],
        # Remake não vale PDL nem conta como vitória/derrota.
        "remake": bool(eu.get("gameEndedInEarlySurrender") or info["gameDuration"] < 300),
        "vitoria": eu["win"],
        "campeao": eu["championName"],
        "rota": eu.get("teamPosition") or eu.get("individualPosition") or "",
        "abates": eu["kills"],
        "mortes": eu["deaths"],
        "assistencias": eu["assists"],
        "cs": eu["totalMinionsKilled"] + eu["neutralMinionsKilled"],
        "dano": eu["totalDamageDealtToChampions"],
        "ouro": eu["goldEarned"],
        "visao": eu["visionScore"],
    }


def atualizar_partidas(jogador, puuid, chave, partidas, pausa=0.0):
    """Acrescenta em `partidas` as partidas solo, flex e personalizadas do jogador que ainda não estão lá."""
    rid = jogador["riot_id"].lower()
    conhecidas = {p["id"] for p in partidas if p["riot_id"].lower() == rid}
    _, regiao = rotas(jogador)
    base = f"https://{regiao}.api.riotgames.com/lol/match/v5/matches"
    inicio_ts = int(datetime.combine(INICIO_CAMPEONATO, datetime.min.time(), BRASILIA).timestamp())

    ids = []
    for busca in BUSCAS:
        pagina = 0
        while True:
            time.sleep(pausa)
            try:
                lote = chamar_api(f"{base}/by-puuid/{puuid}/ids?{busca}&startTime={inicio_ts}"
                                  f"&start={pagina * 100}&count=100", chave) or []
            except urllib.error.HTTPError as e:
                # Um filtro recusado (400) não pode derrubar as outras filas.
                print(f"[aviso] {jogador['nome']}: lista de partidas com {busca} recusada (HTTP {e.code})")
                break
            ids += lote
            if len(lote) < 100:
                break
            pagina += 1

    novas = 0
    for mid in dict.fromkeys(ids):
        if mid in conhecidas:
            continue
        time.sleep(pausa)
        partida = chamar_api(f"{base}/{mid}", chave)
        if not partida or partida["info"].get("queueId") not in FILAS:
            continue
        resumo = resumir_partida(mid, partida["info"], puuid, jogador["riot_id"])
        if resumo:
            partidas.append(resumo)
            novas += 1
    return novas


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


def arquivo_foto(jogador):
    return PASTA_FOTOS / f"{jogador['nome']}.webp"


def reduzir_foto(arquivo, lado=192):
    """As fotos do CBLOW vêm com 1254px; o card mostra 44px. Sem Pillow, fica como veio."""
    try:
        from PIL import Image
    except ImportError:
        return
    with Image.open(arquivo) as im:
        im = im.convert("RGB")
        im.thumbnail((lado, lado), Image.LANCZOS)
        im.save(arquivo, quality=82)


def baixar_foto(jogador):
    """Baixa a foto do site do CBLOW para quem ainda não tem; sem foto lá, tenta na próxima coleta."""
    destino = arquivo_foto(jogador)
    if destino.exists():
        return False
    # O CDN não é consistente com maiúsculas (ex.: pastordecalcinha.webp).
    for nome in dict.fromkeys([jogador["nome"], jogador["nome"].lower()]):
        req = urllib.request.Request(f"{URL_FOTOS}/{urllib.parse.quote(nome)}.webp",
                                     headers={"User-Agent": "cblow-soloq-tracker/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                dados = resp.read()
        except urllib.error.URLError:
            continue
        if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
            PASTA_FOTOS.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(dados)
            reduzir_foto(destino)
            return True
    return False


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
            "foto": f"fotos/{arquivo_foto(j).name}" if arquivo_foto(j).exists() else "",
            "historico": [
                {
                    "data": l["data"],
                    "tier": l["tier"],
                    "rank": l["rank"],
                    "lp": inteiro(l["lp"]),
                    "vitorias": inteiro(l["vitorias"]),
                    "derrotas": inteiro(l["derrotas"]),
                    "pontos": inteiro(l["pontos"]),
                    "estimado": l.get("estimado") == "1",
                }
                for l in hist
            ],
        })
    ARQ_SITE.parent.mkdir(exist_ok=True)
    ARQ_SITE.write_text(json.dumps(saida, ensure_ascii=False, indent=1), encoding="utf-8")
    ARQ_SITE_PARTIDAS.write_text(json.dumps(ler_partidas(), ensure_ascii=False), encoding="utf-8")


def main():
    chave = os.environ.get("RIOT_API_KEY", "").strip()
    if not chave:
        sys.exit("Defina a variável de ambiente RIOT_API_KEY.")

    jogadores = json.loads(ARQ_JOGADORES.read_text(encoding="utf-8"))
    agora = datetime.now(BRASILIA)
    hoje = agora.date().isoformat()

    linhas = ler_historico()
    partidas = ler_partidas()
    falhas = 0
    for j in jogadores:
        try:
            puuid = buscar_puuid(j, chave)
            elo = buscar_elo(j, chave, puuid)
        except ChaveInvalida as e:
            sys.exit(str(e))
        except Exception as e:
            falhas += 1
            print(f"[erro] {j['nome']} ({j['riot_id']}): {e}")
            continue

        if baixar_foto(j):
            print(f"[foto] {j['nome']}: baixada do site do CBLOW")

        try:
            novas = atualizar_partidas(j, puuid, chave, partidas)
        except ChaveInvalida as e:
            sys.exit(str(e))
        except Exception as e:
            novas = 0
            print(f"[erro] partidas de {j['nome']}: {e}")

        linhas = [l for l in linhas if not (l["data"] == hoje and l["riot_id"].lower() == j["riot_id"].lower())]
        linhas.append({"data": hoje, "nome": j["nome"], "riot_id": j["riot_id"],
                       **{k: ("" if v is None else v) for k, v in elo.items()}})
        desc = "sem rank" if elo["pontos"] is None else f"{elo['tier']} {elo['rank']} {elo['lp']} PDL"
        print(f"[ok] {j['nome']}: {desc} ({elo['vitorias']}V {elo['derrotas']}D), {novas} partidas novas")

    salvar_historico(linhas)
    salvar_partidas(partidas)
    gerar_site(linhas, jogadores, agora)
    print(f"{len(jogadores) - falhas}/{len(jogadores)} jogadores atualizados em {hoje}.")
    if falhas == len(jogadores):
        sys.exit(1)


if __name__ == "__main__":
    main()

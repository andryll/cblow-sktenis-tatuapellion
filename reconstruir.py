"""Reconstrói o histórico diário desde o início do campeonato até a primeira coleta real.

Uso:
    python reconstruir.py                          # usa dados/partidas.json como está
    RIOT_API_KEY=RGAPI-... python reconstruir.py   # baixa as partidas novas antes

A API da Riot não guarda o elo de dias passados. O script junta quatro fontes:
- as coletas reais de dados/historico.csv (elo exato no fim de cada dia);
- os registros do op.gg em dados/opgg.json (elo exato no momento em que alguém
  atualizou o perfil lá);
- as mudanças de divisão do League of Graphs em dados/leagueofgraphs.json (quando
  o jogador subiu ou caiu de divisão, sem o PDL);
- as partidas de dados/partidas.json (hora e resultado de cada ranqueada).

Entre dois registros conhecidos, o ganho/perda por partida é ajustado para sair de
um e chegar no outro; o que o ajuste não cobrir é distribuído ao longo do trecho.
Antes do primeiro registro, volta partida por partida com o ganho/perda padrão.
Depois, cada partida fica dentro da divisão que o League of Graphs mostra naquela hora.
Vitórias e derrotas por dia são exatas; o PDL continua marcado como estimado e
nunca substitui uma coleta real.

Os dois arquivos externos foram baixados uma vez, à mão, pelo navegador (op.gg e
League of Graphs bloqueiam robôs); só cobrem os dias antes da coleta real.
"""

import json
import os
import sys
from datetime import date, datetime, time, timedelta

import coletar

ARQ_OPGG = coletar.RAIZ / "dados" / "opgg.json"
ARQ_LOG = coletar.RAIZ / "dados" / "leagueofgraphs.json"

GANHO_VITORIA = 22
PERDA_DERROTA = 20
AJUSTE_MAX = 12  # vitória vale entre 10 e 34 PDL; derrota tira entre 8 e 32
PAUSA = 1.3  # a chave de desenvolvimento aceita 100 chamadas a cada 2 minutos

# PDL típico logo depois de subir (sobra da vitória) e de cair (perto do topo da divisão de baixo).
PDL_PROMOCAO = 10
PDL_REBAIXAMENTO = 90
FOLGA_LOG = timedelta(hours=6)  # o League of Graphs percebe a mudança um tempo depois da partida
PERTO_DE_EXATO = timedelta(hours=2)  # perto de um registro exato, a estimativa da mudança é descartada

ROMANOS = {"1": "I", "2": "II", "3": "III", "4": "IV"}
MUITO_ANTES = datetime(2000, 1, 1, tzinfo=coletar.BRASILIA)


def de_pontos(p):
    if p >= len(coletar.TIERS) * 400:
        return "MASTER", "I", p - len(coletar.TIERS) * 400
    return coletar.TIERS[p // 400], ["IV", "III", "II", "I"][(p % 400) // 100], p % 100


def fim_do_dia(dia):
    return datetime.combine(dia, time(23, 59, 59), coletar.BRASILIA)


def ler_opgg():
    if not ARQ_OPGG.exists():
        return []
    return json.loads(ARQ_OPGG.read_text(encoding="utf-8"))


def ler_log():
    if not ARQ_LOG.exists():
        return []
    return json.loads(ARQ_LOG.read_text(encoding="utf-8"))


def base_divisao(texto):
    tier, rank = texto.split(" ")
    return coletar.pontos(tier, rank, 0)


def mudancas_log(rid, log, minhas):
    """(divisão antes, [(momento, divisão nova)]) do League of Graphs, em pontos da base da divisão.

    O momento vira o fim da partida que causou a mudança: a última vitória (subida)
    ou derrota (queda) até algumas horas antes de o site perceber.
    """
    reg = next((r for r in log if r["riot_id"].lower() == rid), None)
    if reg is None:
        return None, []
    anterior = base_divisao(reg["antes"])
    mudancas = []
    for em, div in reg["mudancas"]:
        t = datetime.fromisoformat(em).replace(tzinfo=coletar.BRASILIA)
        nova = base_divisao(div)
        causa = [m for m, vitoria in minhas if t - FOLGA_LOG <= m <= t and vitoria == (nova > anterior)]
        mudancas.append((causa[-1] if causa else t, nova))
        anterior = nova
    return base_divisao(reg["antes"]), mudancas


def ancoras_log(antes, mudancas, exatas):
    """Elo aproximado logo depois de cada mudança de divisão, longe dos registros exatos."""
    saida, anterior = [], antes
    for t, nova in mudancas:
        if not any(abs(t - te) < PERTO_DE_EXATO for te, _ in exatas):
            saida.append((t, nova + (PDL_PROMOCAO if nova > anterior else PDL_REBAIXAMENTO)))
        anterior = nova
    return saida


def limitar_divisao(pontos, antes, mudancas):
    """Mantém cada partida dentro da divisão que o League of Graphs mostra naquele momento."""
    saida = []
    for t, ordem, p in pontos:
        base = antes
        for tm, nova in mudancas:
            if tm > t:
                break
            base = nova
        saida.append((t, ordem, p if ordem == 1 else min(max(p, base), base + 99)))
    return saida


def ancoras(rid, linhas, opgg):
    """Momentos em que o elo é conhecido: registros do op.gg e fim dos dias com coleta real."""
    saida = []
    for o in opgg:
        if o["riot_id"].lower() == rid:
            p = coletar.pontos(o["tier"], ROMANOS[o["divisao"]], o["lp"])
            if p is not None:
                saida.append((datetime.fromisoformat(o["em"]).astimezone(coletar.BRASILIA), p))
    for l in linhas:
        if l["riot_id"].lower() == rid and l.get("estimado") != "1" and l["pontos"] != "":
            saida.append((fim_do_dia(date.fromisoformat(l["data"])), int(l["pontos"])))
    return saida


def simular(p, resultados, ajuste):
    """Pontos depois de cada partida, com ganho e perda deslocados por `ajuste`. Ferro IV 0 PDL é o piso."""
    saida = []
    for vitoria in resultados:
        p = p + GANHO_VITORIA + ajuste if vitoria else max(0, p - PERDA_DERROTA + ajuste)
        saida.append(p)
    return saida


def ajustar(pa, pb, resultados):
    """Pontos depois de cada partida de um trecho que começa em `pa` e termina em `pb`."""
    if not resultados:
        return []
    lo, hi = -AJUSTE_MAX, AJUSTE_MAX
    for _ in range(40):
        meio = (lo + hi) / 2
        if simular(pa, resultados, meio)[-1] < pb:
            lo = meio
        else:
            hi = meio
    valores = simular(pa, resultados, (lo + hi) / 2)
    # O que o ajuste limitado não cobrir (partidas fora da solo, op.gg atrasado) vai em rampa.
    sobra = pb - valores[-1]
    n = len(valores)
    return [max(0, v + sobra * (k + 1) / n) for k, v in enumerate(valores)]


def linha_do_tempo(anc, minhas):
    """(momento, ordem, pontos) depois de cada partida e em cada registro; registros vêm por último no empate."""
    pontos = [(t, 1, p) for t, p in anc]
    for (ta, pa), (tb, pb) in zip(anc, anc[1:]):
        trecho = [(t, v) for t, v in minhas if ta < t <= tb]
        pontos += [(t, 0, p) for (t, _), p in zip(trecho, ajustar(pa, pb, [v for _, v in trecho]))]

    t0, p = anc[0]
    for t, vitoria in sorted((m for m in minhas if m[0] <= t0), reverse=True):
        pontos.append((t, 0, p))
        p = max(0, p - GANHO_VITORIA) if vitoria else p + PERDA_DERROTA
    pontos.append((MUITO_ANTES, 0, p))

    tn, p = anc[-1]
    for t, vitoria in (m for m in minhas if m[0] > tn):
        p = p + GANHO_VITORIA if vitoria else max(0, p - PERDA_DERROTA)
        pontos.append((t, 0, p))
    return sorted(pontos)


def reconstruir(jogador, partidas, linhas, opgg, log, agora, atual=None):
    rid = jogador["riot_id"].lower()
    minhas = sorted(
        (datetime.fromisoformat(p["fim"]), p["vitoria"]) for p in partidas
        if p["riot_id"].lower() == rid and not p["remake"]
    )
    reais = sorted((l for l in linhas if l["riot_id"].lower() == rid
                    and l.get("estimado") != "1" and l["pontos"] != ""), key=lambda l: l["data"])

    # Vitórias e derrotas saem exatas voltando a partir da primeira coleta real (ou do elo de agora).
    if reais:
        base_dia = date.fromisoformat(reais[0]["data"])
        base_t, base_v, base_d = fim_do_dia(base_dia), int(reais[0]["vitorias"]), int(reais[0]["derrotas"])
    elif atual and atual["pontos"] is not None:
        base_dia, base_t, base_v, base_d = agora.date(), agora, atual["vitorias"], atual["derrotas"]
    else:
        print(f"[pulado] {jogador['nome']}: sem coleta real nem rank na SoloQ")
        return []

    anc = ancoras(rid, linhas, opgg)
    if atual and atual["pontos"] is not None:
        anc.append((agora, atual["pontos"]))
    antes, mudancas = mudancas_log(rid, log, minhas)
    aprox = ancoras_log(antes, mudancas, anc) if mudancas else []
    pontos = linha_do_tempo(sorted(anc + aprox), minhas)
    if antes is not None:
        pontos = limitar_divisao(pontos, antes, mudancas)

    novas = []
    dia = coletar.INICIO_CAMPEONATO
    while dia < base_dia:
        limite = fim_do_dia(dia)
        p = round(max(0, [v for t, _, v in pontos if t <= limite][-1]))
        depois = [v for t, v in minhas if limite < t <= base_t]
        tier, rank, lp = de_pontos(p)
        novas.append({"data": dia.isoformat(), "nome": jogador["nome"], "riot_id": jogador["riot_id"],
                      "tier": tier, "rank": rank, "lp": lp,
                      "vitorias": base_v - sum(depois), "derrotas": base_d - (len(depois) - sum(depois)),
                      "pontos": p, "estimado": "1"})
        dia += timedelta(days=1)

    def no_periodo(lista):
        return sum(1 for t, _ in lista if coletar.INICIO_CAMPEONATO <= t.date() < base_dia)
    print(f"[ok] {jogador['nome']}: {len(novas)} dias estimados, {len(minhas)} partidas, "
          f"{no_periodo(anc)} registros do op.gg e {no_periodo(mudancas)} mudanças de divisão no período")
    return novas


def main():
    chave = os.environ.get("RIOT_API_KEY", "").strip()
    jogadores = json.loads(coletar.ARQ_JOGADORES.read_text(encoding="utf-8"))
    agora = datetime.now(coletar.BRASILIA)
    linhas = coletar.ler_historico()
    partidas = coletar.ler_partidas()
    opgg = ler_opgg()
    log = ler_log()

    for j in jogadores:
        atual = None
        if chave:
            try:
                puuid = coletar.buscar_puuid(j, chave)
                atual = coletar.buscar_elo(j, chave, puuid)
                coletar.atualizar_partidas(j, puuid, chave, partidas, pausa=PAUSA)
            except coletar.ChaveInvalida as e:
                sys.exit(str(e))
            except Exception as e:
                print(f"[erro] {j['nome']} ({j['riot_id']}): {e}")
                continue
            coletar.salvar_partidas(partidas)  # salva a cada jogador para não perder downloads

        novas = reconstruir(j, partidas, linhas, opgg, log, agora, atual)
        rid = j["riot_id"].lower()
        # Estimativas antigas do jogador saem; coletas reais ficam e têm prioridade.
        linhas = [l for l in linhas if not (l["riot_id"].lower() == rid and l.get("estimado") == "1")]
        reais = {l["data"] for l in linhas if l["riot_id"].lower() == rid}
        linhas += [n for n in novas if n["data"] not in reais]

    coletar.salvar_historico(linhas)
    coletar.gerar_site(linhas, jogadores, agora)


if __name__ == "__main__":
    main()

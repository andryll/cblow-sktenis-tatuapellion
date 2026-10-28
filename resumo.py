"""Gera os dados da aba 🔒 Resumo: a forma recente do SKTenis e do próximo adversário, os melhores
campeões de cada atleta (SoloQ, Flex e treinos) e, com ANTHROPIC_API_KEY, uma análise escrita pelo Claude.

Uso (depois do coletar.py, que gera privado-saida/partidas.json e scout.json, e antes do privado.py,
que criptografa privado-saida/resumo.json para site/resumo.json):
    ANTHROPIC_API_KEY=... python resumo.py

A análise custa dinheiro, então só é pedida uma vez por semana, na coleta de sexta às 23h (ou na hora,
pelo botão "Run workflow" com "Gerar a análise agora"). Ela fica guardada em privado-fonte/analise.json e
aparece até a próxima. Sem a chave, a aba sai só com os números.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta

import coletar

ARQ_RESUMO = coletar.PASTA_SAIDA_PRIVADA / "resumo.json"
ARQ_ANALISE = coletar.PASTA_PRIVADA / "analise.json"
ARQ_TREINOS = coletar.PASTA_PRIVADA / "treinos.json"

JANELA = 30          # dias de SoloQ, Flex e treinos que entram nos melhores campeões
RECENTE = 7          # dias da forma recente na SoloQ/Flex
MIN_PARTIDAS = 3     # com menos que isso o campeão só entra se faltar opção, marcado como amostra pequena
PRIOR = 4            # partidas fictícias a 50%: puxa o winrate de quem jogou pouco para o meio
PESO_TREINO = 1      # quanto um jogo de treino vale em relação a uma partida de SoloQ/Flex
MELHORES = 4
ULTIMOS_OFICIAIS = 5

MODELO = "claude-opus-5-5"
ANALISE_HORA = 23  # a análise sai na sexta nesse horário (a coleta roda de hora em hora)

normal = coletar.normalizar


def kda(s):
    return round((s["abates"] + s["assistencias"]) / max(1, s["mortes"]), 2)


def somar(linhas):
    s = {"n": 0, "v": 0, "abates": 0, "mortes": 0, "assistencias": 0}
    for l in linhas:
        s["n"] += 1
        s["v"] += 1 if l["vitoria"] else 0
        for c in ("abates", "mortes", "assistencias"):
            s[c] += l[c] or 0
    return {"n": s["n"], "v": s["v"], "d": s["n"] - s["v"], "kda": kda(s)}


def melhores_campeoes(linhas, quantos=MELHORES):
    """Campeões ordenados pelo winrate corrigido (PRIOR jogos a 50%), com o KDA de desempate.

    Treino pesa PESO_TREINO partidas. Quem tem menos de MIN_PARTIDAS só entra para completar a lista.
    """
    por = {}
    for l in linhas:
        c = por.setdefault(normal(l["campeao"]), {"campeao": l["campeao"], "linhas": [], "fontes": {}})
        c["linhas"].append(l)
        c["fontes"][l["fonte"]] = c["fontes"].get(l["fonte"], 0) + 1
    lista = []
    for c in por.values():
        peso = sum(PESO_TREINO if l["fonte"] == "treino" else 1 for l in c["linhas"])
        vitorias = sum(PESO_TREINO if l["fonte"] == "treino" else 1 for l in c["linhas"] if l["vitoria"])
        lista.append({"campeao": c["campeao"], **somar(c["linhas"]), "fontes": c["fontes"],
                      "nota": round((vitorias + PRIOR / 2) / (peso + PRIOR), 3)})
    ordem = lambda c: (c["n"] >= MIN_PARTIDAS, c["nota"], c["kda"], c["n"])
    lista.sort(key=ordem, reverse=True)
    escolhidos = [c for c in lista if c["n"] >= 2][:quantos]
    for c in escolhidos:
        c["amostra_pequena"] = c["n"] < MIN_PARTIDAS
    return escolhidos


def linhas_soloq(partidas, riot_id, desde):
    """Partidas solo e flex do atleta desde `desde`, sem remakes, no formato comum."""
    rid = riot_id.lower()
    return [{**p, "fonte": p["fila"], "data": p["fim"][:10]} for p in partidas
            if p["riot_id"].lower() == rid and p["fila"] in ("solo", "flex") and not p.get("remake")
            and p["fim"][:10] >= desde]


def jogos_de_treino(treinos, time, desde):
    return [j for j in treinos if normal(j["time"]) == normal(time) and j["data"] >= desde]


def linhas_treino(jogos, nome):
    return [{**x, "vitoria": j["vitoria"], "fonte": "treino", "data": j["data"]}
            for j in jogos for x in j["jogadores"] if normal(x["nome"]) == normal(nome)]


def atleta(nome, funcao, foto, soloq, treino, recente):
    tudo = soloq + treino
    return {
        "nome": nome, "funcao": funcao, "foto": foto,
        "soloq": somar(soloq), "treinos": somar(treino),
        "recente": somar([l for l in soloq if l["data"] >= recente]),
        "melhores": melhores_campeoes(tudo),
        # A análise recebe mais campeões que a página mostra.
        "_campeoes": melhores_campeoes(tudo, 6),
    }


def forma_oficial(time_rodizio):
    jogos = (time_rodizio or {}).get("jogos", [])
    return {
        "v": sum(j["vitoria"] for j in jogos), "d": sum(not j["vitoria"] for j in jogos),
        "ultimos": [{"quando": j["quando"], "fase": j["fase"], "adversario": j["adversario"]["tag"],
                     "vitoria": j["vitoria"], "carta": j["carta"],
                     "campeoes": [f"{e['nick']}: {e['campeao']}" for e in j["escalacao"]]}
                    for j in jogos[-ULTIMOS_OFICIAIS:]][::-1],
    }


def forma_treinos(jogos):
    return {"v": sum(j["vitoria"] for j in jogos), "d": sum(not j["vitoria"] for j in jogos),
            "ultimos": [{"data": j["data"], "adversario": j.get("adversario") or "", "vitoria": j["vitoria"],
                         "campeoes": [f"{x['nome']}: {x['campeao']}" for x in j["jogadores"]]}
                        for j in sorted(jogos, key=lambda j: j["data"], reverse=True)[:ULTIMOS_OFICIAIS]]}


def montar_time(nome, tag, elenco, partidas, treinos, rodizio, desde, recente):
    """elenco: [{nome, funcao, foto, riot_id}]; quem não tem Riot ID entra só com os treinos."""
    jogos = jogos_de_treino(treinos, nome, desde)
    soloq_todos = []
    atletas = []
    for a in elenco:
        soloq = linhas_soloq(partidas, a["riot_id"], desde) if a.get("riot_id") else []
        soloq_todos += soloq
        atletas.append(atleta(a["nome"], a["funcao"], a["foto"], soloq, linhas_treino(jogos, a["nome"]), recente))
    # Sem nenhum jogo na janela, o atleta não diz nada sobre o momento do time.
    atletas = [a for a in atletas if a["soloq"]["n"] or a["treinos"]["n"]]
    return {
        "nome": nome, "tag": tag,
        "oficial": forma_oficial(rodizio),
        "soloq_recente": somar([l for l in soloq_todos if l["data"] >= recente]),
        "soloq": somar(soloq_todos),
        "treinos": forma_treinos(jogos),
        "atletas": atletas,
    }


def nosso_elenco(rodizio_nosso):
    saiu = {normal(e["nick"]) for e in (rodizio_nosso or {}).get("elenco", []) if e["saiu"]}
    jogadores = json.loads(coletar.ARQ_JOGADORES.read_text(encoding="utf-8"))
    return [{"nome": j["nome"], "funcao": j.get("funcao", ""), "riot_id": j["riot_id"],
             "foto": f"fotos/{coletar.arquivo_foto(j).name}" if coletar.arquivo_foto(j).exists() else ""}
            for j in jogadores if normal(j["nome"]) not in saiu]


def elenco_adversario(scout):
    return [{"nome": j["nome"], "funcao": j["funcao"], "foto": j["foto"],
             "riot_id": None if j["riot_id"].startswith("cblow:") else j["riot_id"]}
            for j in scout["jogadores"]]


# ---------------------------------------------------------------- análise pelo Claude

SISTEMA = """Você é analista de League of Legends do SKTenis Tatuapellion no CBLOW, campeonato brasileiro \
de low elo (Ferro e Bronze) do streamer Yoda. Escreve para o próprio time, antes do próximo jogo, uma \
análise curta e com opinião: o que os números dizem sobre o momento do SKTenis e do adversário, onde está \
a vantagem de cada lado e o que vale banir ou priorizar.

Contexto do campeonato: as escalações seguem um rodízio obrigatório (todo mundo do elenco precisa jogar \
antes de uma escalação se repetir, e o Pé de Chumbo joga sempre), e antes de cada jogo é sorteada uma \
carta que muda as regras do draft ou da partida. Por isso o elenco que joga muda bastante e os campeões \
do campeonato nem sempre são escolha livre. Treinos são scrims contra outros times, passados à mão das \
prints. SoloQ e Flex são as filas ranqueadas de cada atleta nos últimos dias.

Regras:
- Use só os números recebidos. Não invente partidas, campeões nem resultados.
- Diga quando a amostra é pequena (poucas partidas) em vez de tirar conclusão forte dela.
- Tenha opinião e seja direto, em português do Brasil informal, como quem fala com o time.
- Chame os atletas pelo nick e os campeões pelo nome em português.
- Texto puro, sem markdown."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "manchete": {"type": "string", "description": "Uma frase que resume o confronto."},
        "nosso_time": {"type": "string", "description": "Um parágrafo sobre o momento do SKTenis."},
        "adversario": {"type": "string", "description": "Um parágrafo sobre o momento do adversário."},
        "pontos_chave": {"type": "array", "items": {"type": "string"},
                         "description": "De 3 a 5 pontos que devem decidir o jogo."},
        "bans": {"type": "array", "description": "De 2 a 4 sugestões de ban.",
                 "items": {"type": "object",
                           "properties": {"campeao": {"type": "string"}, "jogador": {"type": "string"},
                                          "motivo": {"type": "string"}},
                           "required": ["campeao", "jogador", "motivo"], "additionalProperties": False}},
        "recomendacoes": {"type": "array", "items": {"type": "string"},
                          "description": "De 2 a 4 recomendações práticas para o SKTenis."},
    },
    "required": ["manchete", "nosso_time", "adversario", "pontos_chave", "bans", "recomendacoes"],
    "additionalProperties": False,
}


def para_analise(resumo):
    """Os números que vão para o Claude: sem fotos, com mais campeões por atleta que a página mostra."""
    def time(t):
        return {**{k: t[k] for k in ("nome", "tag", "oficial", "soloq_recente", "soloq", "treinos")},
                "atletas": [{"nick": a["nome"], "funcao": a["funcao"], "soloq_30_dias": a["soloq"],
                             "soloq_7_dias": a["recente"], "treinos_30_dias": a["treinos"],
                             "campeoes": [{k: c[k] for k in ("campeao", "n", "v", "d", "kda", "fontes")}
                                          for c in a["_campeoes"]]}
                            for a in t["atletas"]]}
    return {"proximo_jogo": resumo["proximo"], "janela_dias": JANELA, "nosso_time": time(resumo["nosso"]),
            "adversario": time(resumo["adversario"])}


def impressao(dados):
    return hashlib.sha256(json.dumps(dados, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def pedir_analise(dados):
    import anthropic  # só quando há chave: sem ela, a coleta roda sem esse pacote

    cliente = anthropic.Anthropic()
    resposta = cliente.beta.messages.create(
        model=MODELO,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # se o modelo recusar, a API refaz o pedido no modelo indicado para isso
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": ESQUEMA}},
        system=SISTEMA,
        messages=[{"role": "user", "content": "Números do confronto (JSON):\n"
                   + json.dumps(dados, ensure_ascii=False, indent=1)}],
    )
    if resposta.stop_reason == "refusal":
        raise RuntimeError("o modelo recusou o pedido")
    if resposta.stop_reason == "max_tokens":
        raise RuntimeError("a resposta passou do limite de tokens")
    texto = next(b.text for b in resposta.content if b.type == "text")
    uso = resposta.usage
    print(f"[resumo] análise pelo {resposta.model}: {uso.input_tokens} tokens de entrada, {uso.output_tokens} de saída")
    return json.loads(texto), resposta.model


def hora_da_analise(agora):
    """Sexta às 23h (Brasília); FORCAR_ANALISE=1 pede na hora (botão do workflow)."""
    return os.environ.get("FORCAR_ANALISE") == "true" or (agora.weekday() == 4 and agora.hour == ANALISE_HORA)


def analise(resumo, agora, adversario, gatilho):
    """A análise guardada; uma nova só sai na hora marcada, uma vez por dia.

    Ela continua aparecendo até a próxima, se o adversário for o mesmo, marcada como desatualizada
    quando entrou treino ou jogo oficial depois dela.
    """
    guardada = json.loads(ARQ_ANALISE.read_text(encoding="utf-8")) if ARQ_ANALISE.exists() else None
    anterior = ({**guardada, "desatualizada": guardada["gatilho"] != gatilho}
                if guardada and guardada.get("adversario") == adversario else None)
    ja_hoje = guardada and guardada["gerado_em"][:10] == agora.date().isoformat() and anterior
    if not hora_da_analise(agora) or (ja_hoje and os.environ.get("FORCAR_ANALISE") != "true"):
        return anterior
    if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        print("[resumo] sem ANTHROPIC_API_KEY: a aba sai sem a análise escrita nova"
              + (" (fica a anterior)" if anterior else ""))
        return anterior
    try:
        texto, modelo = pedir_analise(para_analise(resumo))
    except Exception as e:
        print(f"[resumo] erro na análise: {e}" + (" (fica a anterior)" if anterior else ""))
        return anterior
    nova = {"adversario": adversario, "gatilho": gatilho,
            "gerado_em": agora.isoformat(timespec="minutes"), "modelo": modelo, "analise": texto}
    ARQ_ANALISE.write_text(json.dumps(nova, ensure_ascii=False, indent=1), encoding="utf-8")
    return nova


def main():
    agora = datetime.now(coletar.BRASILIA)
    if not coletar.ARQ_SITE_SCOUT.exists() or not coletar.ARQ_SITE_PARTIDAS.exists():
        print("[resumo] faltam partidas.json ou scout.json em privado-saida/ (rode o coletar.py antes): aba não gerada")
        return
    scout = json.loads(coletar.ARQ_SITE_SCOUT.read_text(encoding="utf-8"))
    partidas = json.loads(coletar.ARQ_SITE_PARTIDAS.read_text(encoding="utf-8"))
    treinos = json.loads(ARQ_TREINOS.read_text(encoding="utf-8"))["jogos"] if ARQ_TREINOS.exists() else []
    rodizio = {t["slug"]: t for t in json.loads(coletar.ARQ_SITE_RODIZIO.read_text(encoding="utf-8"))["times"]}

    saida = {"atualizado_em": agora.isoformat(timespec="minutes"), "janela_dias": JANELA, "recente_dias": RECENTE,
             "min_partidas": MIN_PARTIDAS, "proximo": scout.get("proximo"), "nosso": None, "adversario": None,
             "analise": None}
    if scout.get("proximo"):
        desde = (agora.date() - timedelta(days=JANELA)).isoformat()
        recente = (agora.date() - timedelta(days=RECENTE)).isoformat()
        nosso_rod = rodizio.get(coletar.TIME_CBLOW)
        adv = scout["proximo"]["time"]
        saida["nosso"] = montar_time(nosso_rod["nome"] if nosso_rod else "SKTENIS", nosso_rod and nosso_rod["tag"],
                                     nosso_elenco(nosso_rod), partidas, treinos, nosso_rod, desde, recente)
        saida["adversario"] = montar_time(adv["nome"], adv["tag"], elenco_adversario(scout), scout["partidas"],
                                          treinos, rodizio.get(adv["slug"]), desde, recente)
        # Muda quando troca o adversário ou entra treino ou jogo oficial de um dos dois.
        gatilho = impressao({
            "adversario": adv["slug"],
            "treinos": [j for j in treinos if normal(j["time"]) in (normal(saida["nosso"]["nome"]), normal(adv["nome"]))],
            "oficiais": [j["id"] for slug in (coletar.TIME_CBLOW, adv["slug"]) for j in rodizio.get(slug, {}).get("jogos", [])],
        })
        saida["analise"] = analise(saida, agora, adv["slug"], gatilho)
        for t in (saida["nosso"], saida["adversario"]):
            for a in t["atletas"]:
                del a["_campeoes"]
        print(f"[resumo] {saida['nosso']['nome']} x {adv['nome']}: {len(saida['nosso']['atletas'])} e "
              f"{len(saida['adversario']['atletas'])} atletas com jogos nos últimos {JANELA} dias")
    else:
        print("[resumo] sem próximo adversário: a aba fica vazia")
    coletar.PASTA_SAIDA_PRIVADA.mkdir(exist_ok=True)
    ARQ_RESUMO.write_text(json.dumps(saida, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

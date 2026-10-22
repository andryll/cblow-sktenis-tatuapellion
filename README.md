# CBLOW · SoloQ

Acompanha diariamente o elo de SoloQ dos atletas e publica os gráficos no GitHub Pages.

- `jogadores.json` — lista de atletas (`nome`, `riot_id` no formato `Nick#TAG`, `funcao`; opcional `servidor`, padrão `br1`).
- `coletar.py` — consulta a API da Riot, grava `dados/historico.csv` e gera `site/dados.json`. Só usa a biblioteca padrão do Python.
- `site/index.html` — página dos gráficos.
- `reconstruir.py` — reconstrói os dias passados pelo histórico de partidas (match-v5). Vitórias/derrotas por dia são exatas; o PDL é estimado (+22 por vitória, −20 por derrota) e aparece tracejado no gráfico.
- `.github/workflows/coleta.yml` — roda a cada hora (o gráfico guarda o último valor de cada dia), salva o histórico no repositório e publica o site.

## Configuração

1. Gere uma chave em <https://developer.riotgames.com>. A chave de desenvolvimento expira em 24h; para rodar todo dia, registre um **Personal API Key** (Register Product → Personal).
2. No repositório: Settings → Secrets and variables → Actions → New repository secret, nome `RIOT_API_KEY`.
3. Settings → Pages → Source: **GitHub Actions**.
4. Actions → "Coleta de elo" → **Run workflow** para a primeira coleta. Marque "Reconstruir o histórico" para preencher os dias desde o início do campeonato.

Para adicionar ou trocar atletas, edite `jogadores.json`. O histórico é ligado ao `riot_id`: se alguém trocar de nick, atualize o `riot_id` e, se quiser manter o histórico, troque também o nick antigo em `dados/historico.csv`.

## Rodar localmente

```bash
RIOT_API_KEY=RGAPI-... python coletar.py
python -m http.server --directory site
```

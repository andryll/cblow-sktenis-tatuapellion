# CBLOW · SoloQ

Acompanha diariamente o elo de SoloQ dos atletas e publica os gráficos no GitHub Pages.

- `jogadores.json` — lista de atletas (`nome`, `riot_id` no formato `Nick#TAG`, `funcao`; opcional `servidor`, padrão `br1`). Novos atletas vão no fim da lista para não trocar as cores do gráfico. A foto fica em `site/fotos/<nome>.webp`; quem ainda não tem, a coleta tenta baixar do CDN do cblow.xyz a cada execução.
- `coletar.py` — consulta a API da Riot, grava `dados/historico.csv` e gera `site/dados.json`. Só usa a biblioteca padrão do Python.
- `site/index.html` — página de evolução do elo.
- `site/desempenho.html` — desempenho desde o início do campeonato: winrate, KDA, CS e dano por minuto, campeões jogados (só ranqueadas solo; remakes ficam de fora).
- `site/partidas.html` — últimas partidas de todos os atletas ou de um só, 50 por vez.
- `dados/partidas.json` — resumo de cada ranqueada solo dos atletas desde 02/10 (match-v5); a coleta de hora em hora baixa só as novas.
- `reconstruir.py` — reconstrói os dias antes da primeira coleta real. Vitórias/derrotas por dia são exatas (match-v5); o PDL é estimado e aparece tracejado no gráfico. A linha passa pelos registros exatos do op.gg (`dados/opgg.json`) e pelas coletas reais, com o ganho/perda por partida ajustado entre eles, e fica dentro da divisão que o League of Graphs mostra em cada momento (`dados/leagueofgraphs.json`). Os dois arquivos foram baixados uma vez pelo navegador, porque os sites bloqueiam robôs. Roda sem a chave da Riot (`python reconstruir.py`); com a chave, baixa as partidas novas antes.
- `.github/workflows/coleta.yml` — coleta, salva o histórico no repositório e publica o site. Quem dispara de hora em hora é um cronjob no cron-job.org (POST em `/repos/andryll/cblow-sktenis-tatuapellion/actions/workflows/coleta.yml/dispatches` com `{"ref":"main"}` e um token fine-grained com Actions: read and write). O gráfico guarda o último valor de cada dia.

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

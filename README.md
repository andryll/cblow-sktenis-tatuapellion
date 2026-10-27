# CBLOW · SoloQ

Acompanha diariamente o elo de SoloQ dos atletas e publica os gráficos no GitHub Pages.

- `jogadores.json` — lista de atletas (`nome`, `riot_id` no formato `Nick#TAG`, `funcao`; opcional `servidor`, padrão `br1`). Novos atletas vão no fim da lista para não trocar as cores do gráfico. A foto fica em `site/fotos/<nome>.webp`; quem ainda não tem, a coleta tenta baixar do CDN do cblow.xyz a cada execução.
- `coletar.py` — consulta a API da Riot, grava `dados/historico.csv` e gera `site/dados.json`. Só usa a biblioteca padrão do Python.
- `site/index.html` — página de evolução do elo.
- `site/desempenho.html` (Desempenho SoloQ) e `site/geral.html` (Desempenho geral) — desempenho desde o início do campeonato: winrate, KDA, CS e dano por minuto, campeões jogados. A primeira conta só ranqueadas solo; a geral soma solo, flex e jogos oficiais do campeonato. As duas usam `site/desempenho.js`, e cada página define as filas em `window.FILAS`. Remakes ficam de fora.
- `site/partidas.html` — últimas partidas de todos os atletas ou de um só, 50 por vez, com filtro por tipo (SoloQ, Flex, Personalizada).
- `dados/partidas.json` — resumo de cada partida dos atletas desde 02/10, com o campo `fila`: `solo` e `flex` vêm da Riot (match-v5); `campeonato` são os jogos oficiais do time (`TIME_CBLOW` em `coletar.py`) na API pública do CBLOW (`api.cblow.xyz`), sem dano, ouro e visão. A coleta de hora em hora baixa só as novas. Personalizadas comuns (treinos, scrims) não saem em nenhuma API. A reconstrução do elo usa só as solo.
- `site/rodizio.html` (Rodízio) — ajuda no rodízio obrigatório do CBLOW (regras, art. 2): quem é obrigado a jogar o próximo jogo, o Pé de Chumbo, quem está livre, a última escalação (que não pode se repetir) e quem jogou cada partida, com os ciclos marcados. A coleta grava elenco e escalações em `site/rodizio.json` (API do CBLOW, sem chave); a regra é calculada na página: um ciclo fecha quando todos os inscritos (menos o Pé de Chumbo) jogaram, e o próximo ciclo começa do zero no jogo seguinte; nos playoffs a fila zera. Quem entra no elenco no meio do campeonato vai em `rodizio.json` (`"entradas": {"slug": "AAAA-MM-DD"}`), porque o CBLOW não informa a data de entrada.
- `site/scout.html` (Scout) — próximo adversário do time no CBLOW, descoberto sozinho a cada coleta: para cada jogador do elenco, a tabela de campeões com partidas, winrate, KDA e dano por minuto, com filtros de período (7 dias, 30 dias, tudo) e de tipo de partida. A coleta baixa as solo e flex dos adversários desde 30 dias atrás (ou desde 02/10, se for antes) para `dados/partidas_adversarios.json` e os jogos oficiais deles no CBLOW; gera `site/scout.json`. O Riot ID vem do link do op.gg cadastrado no CBLOW, que costuma estar desatualizado: o log da coleta avisa quem não foi encontrado, e o Riot ID certo vai em `adversarios.json` (slug do jogador no CBLOW -> `Nick#TAG`). Sem Riot ID, só os jogos do campeonato entram. Para escolher o adversário na mão (quando o CBLOW ainda não marcou o jogo, ou para olhar outro time), coloque o slug do time em `proximo_adversario.json` (`{"slug": "sucatainbox"}`); apague o arquivo para voltar ao automático.
- `site/partidas.html` mostra "—" no dano dos jogos do campeonato, e o dano por minuto das páginas de desempenho ignora esses jogos.
- `site/treinos.html` (🔒 Treinos) — scout dos treinos (scrims) dos adversários, no formato da aba Scout: campeões por jogador com partidas, winrate, KDA e CS (dano por minuto quando a print traz), e a lista dos jogos. Cada jogo diz de qual `time` são os dados; a aba abre no próximo adversário da aba Scout e pega foto e função do elenco dele. Os dados ficam em `treinos.json` no repositório **privado** `andryll/cblow-privado`; a coleta baixa esse arquivo, criptografa com `privado.py` (AES-256-GCM, chave da senha por PBKDF2-SHA256) e publica só `site/treinos.json` criptografado, que não vai para o git. A página pede a senha e decifra no navegador. Precisa de dois secrets: `SENHA_PRIVADO` (a senha da aba) e `TOKEN_PRIVADO` (token fine-grained com Contents: read-only só no `cblow-privado`); sem eles, o passo é pulado.
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

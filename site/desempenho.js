// Páginas de desempenho: a página define window.FILAS (filas que entram nas contas).
const FILAS = window.FILAS || ["solo"];
const GERAL = FILAS.length > 1;
const NOME_FILA = { solo: "SoloQ", flex: "Flex", campeonato: "Campeonato" };
const SIGLA_FILA = { solo: "Solo", flex: "Flex", campeonato: "Camp." };
const DESCRICAO = GERAL ? "SoloQ, flex e jogos do campeonato" : "ranqueadas solo";

let jogadores = [], partidas = [], sel = null, grafico = null;
let dd = { versao: null, porId: {} };  // Data Dragon: ícones e nomes em português

const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const el = (tag, props = {}, ...filhos) => {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...filhos);
  return e;
};
const fmt = (v, casas = 1) => v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
const pct = (v, t) => (t ? `${Math.round(100 * v / t)}%` : "—");

function campeao(nome) {
  const c = dd.porId[nome.toLowerCase()];
  return { nome: c?.name || nome, icone: c && dd.versao ? `https://ddragon.leagueoflegends.com/cdn/${dd.versao}/img/champion/${c.id}.png` : null };
}

function somar(lista) {
  // Jogos do campeonato não têm dano: o dano por minuto usa só os minutos de quem tem.
  const s = { n: lista.length, v: 0, k: 0, d: 0, a: 0, cs: 0, dano: 0, minDano: 0, min: 0 };
  for (const p of lista) {
    s.v += p.vitoria ? 1 : 0; s.k += p.abates; s.d += p.mortes; s.a += p.assistencias;
    s.cs += p.cs; s.min += p.duracao / 60;
    if (p.dano != null) { s.dano += p.dano; s.minDano += p.duracao / 60; }
  }
  s.kda = (s.k + s.a) / Math.max(1, s.d);
  return s;
}
const danoMin = s => (s.minDano ? fmt(s.dano / s.minDano, 0) : "—");

const kdaTexto = s => (s.n ? `${fmt(s.k / s.n)} / ${fmt(s.d / s.n)} / ${fmt(s.a / s.n)}` : "—");
const doJogador = j => p => p.riot_id.toLowerCase() === j.riot_id.toLowerCase();
// Partidas antigas não têm "fila": eram todas solo.
const validas = () => partidas.filter(p => !p.remake && FILAS.includes(p.fila || "solo"));
const porFila = lista => FILAS.map(f => `${lista.filter(p => (p.fila || "solo") === f).length} ${NOME_FILA[f].toLowerCase()}`).join(" · ");

function selecionadas() {
  return sel ? validas().filter(doJogador(sel)) : validas();
}

function desenharFiltro() {
  const box = document.getElementById("filtro");
  box.replaceChildren();
  const botao = (j) => {
    const b = el("button", { type: "button" });
    b.setAttribute("aria-pressed", String(sel === j));
    if (j?.foto) b.append(el("img", { src: j.foto, alt: "" }));
    else b.classList.add("sem-foto");
    b.append(j ? j.nome : "Time todo");
    b.addEventListener("click", () => { sel = j; render(); });
    return b;
  };
  box.append(botao(null), ...jogadores.map(botao));
}

function desenharTiles(lista) {
  const s = somar(lista);
  const tile = (rot, val, det) => el("div", { className: "card tile" },
    el("div", { className: "rot", textContent: rot }),
    el("div", { className: "val", textContent: val }),
    el("div", { className: "det", textContent: det }));
  document.getElementById("tiles").replaceChildren(
    tile("Partidas", String(s.n), GERAL ? porFila(lista) : DESCRICAO),
    tile("Winrate", pct(s.v, s.n), `${s.v}V ${s.n - s.v}D`),
    tile("KDA", s.n ? fmt(s.kda, 2) : "—", kdaTexto(s)),
    tile("CS por minuto", s.min ? fmt(s.cs / s.min) : "—", s.n ? `${Math.round(s.cs / s.n)} por partida` : ""),
    tile("Dano por minuto", danoMin(s), GERAL ? "em campeões, sem os jogos do campeonato" : "em campeões"),
  );
}

function desenharGrafico(lista) {
  if (grafico) grafico.destroy();
  const dias = {};
  const inicio = new Date("2026-10-02T12:00:00");
  const fim = new Date();
  fim.setHours(23, 59);
  for (let d = new Date(inicio); d <= fim; d.setDate(d.getDate() + 1)) dias[d.toISOString().slice(0, 10)] = { v: 0, d: 0 };
  for (const p of lista) {
    const dia = p.fim.slice(0, 10);
    if (dias[dia]) dias[dia][p.vitoria ? "v" : "d"]++;
  }
  const chaves = Object.keys(dias);
  const rot = chaves.map(c => `${c.slice(8, 10)}/${c.slice(5, 7)}`);
  grafico = new Chart(document.getElementById("grafico"), {
    type: "bar",
    data: {
      labels: rot,
      datasets: [
        { label: "Vitórias", data: chaves.map(c => dias[c].v), backgroundColor: css("--s1"), borderRadius: 4, borderSkipped: "start" },
        { label: "Derrotas", data: chaves.map(c => -dias[c].d), backgroundColor: css("--s8"), borderRadius: 4, borderSkipped: "start" },
      ],
    },
    options: {
      maintainAspectRatio: false, animation: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { color: css("--muted"), maxRotation: 0, autoSkipPadding: 12 }, border: { color: css("--axis") } },
        y: {
          stacked: true, border: { display: false },
          ticks: { color: css("--muted"), precision: 0, callback: v => Math.abs(v) },
          grid: { color: c => (c.tick.value === 0 ? css("--axis") : css("--grid")) },
        },
      },
      plugins: {
        legend: { position: "top", align: "start", labels: { color: css("--ink-2"), boxWidth: 12, boxHeight: 12 } },
        tooltip: {
          backgroundColor: css("--surface"), borderColor: css("--border"), borderWidth: 1,
          titleColor: css("--ink-2"), bodyColor: css("--ink"), padding: 10,
          callbacks: { label: i => ` ${Math.abs(i.raw)} ${i.dataset.label.toLowerCase()}` },
        },
      },
    },
  });
}

// Ordenação de cada tabela; números começam do maior, nomes em ordem alfabética.
const ordem = { "tab-atletas": { chave: "n", desc: true }, "tab-campeoes": { chave: "n", desc: true } };
let minPartidas = 1;

// cabecalho: [texto, numérico?, chave de ordenação]; linhas: arrays de células ou { cels, val }.
function tabela(id, cabecalho, linhas) {
  const t = document.getElementById(id);
  const o = ordem[id];
  const seletor = document.querySelector(`select.ordem[data-tabela="${id}"]`);
  if (seletor && o) seletor.value = o.chave;
  if (o) {
    linhas = [...linhas].sort((a, b) => {
      const x = a.val[o.chave], y = b.val[o.chave];
      const dif = typeof x === "string" ? x.localeCompare(y, "pt-BR") : x - y;
      return (o.desc ? -dif : dif) || b.val.n - a.val.n;
    });
  }
  const thead = el("thead", {}, el("tr", {}, ...cabecalho.map(([txt, num, chave]) => {
    const th = el("th", { className: num ? "num" : "" });
    if (!o || !chave) { th.textContent = txt; return th; }
    const ativo = o.chave === chave;
    th.setAttribute("aria-sort", ativo ? (o.desc ? "descending" : "ascending") : "none");
    const b = el("button", { type: "button", className: `ordenar${ativo ? " ativo" : ""}`, textContent: txt });
    b.append(el("span", { className: "seta", textContent: ativo ? (o.desc ? " ▼" : " ▲") : "" }));
    b.addEventListener("click", () => {
      ordem[id] = ativo ? { chave, desc: !o.desc } : { chave, desc: chave !== "nome" };
      render();
    });
    th.append(b);
    return th;
  })));
  const tbody = el("tbody");
  for (const l of linhas) {
    const cels = l.cels || l;
    tbody.append(el("tr", {}, ...cels.map((c, i) => {
      const td = el("td", { className: cabecalho[i][1] ? "num" : "" });
      if (c instanceof Node) td.append(c); else td.textContent = c;
      return td;
    })));
  }
  if (!linhas.length) tbody.append(el("tr", {}, el("td", { colSpan: cabecalho.length, className: "muted", textContent: "Nenhuma partida ainda." })));
  t.replaceChildren(thead, tbody);
}

// Valores usados na ordenação; quem não tem partida vai para o fim.
const valores = (nome, s) => ({
  nome, n: s.n,
  wr: s.n ? s.v / s.n : -1,
  kda: s.n ? s.kda : -1,
  cs: s.min ? s.cs / s.min : -1,
  dano: s.minDano ? s.dano / s.minDano : -1,
});

function celCampeao(nome) {
  const c = campeao(nome);
  const box = el("span", { className: "camp" });
  if (c.icone) box.append(el("img", { src: c.icone, alt: "", loading: "lazy" }));
  box.append(c.nome);
  return box;
}

function celJogador(j) {
  const box = el("span");
  if (j.foto) box.append(el("img", { className: "mini", src: j.foto, alt: "" }));
  box.append(j.nome);
  return box;
}

function desenharAtletas() {
  const sec = document.getElementById("sec-atletas");
  sec.hidden = !!sel;
  if (sel) return;
  const todas = validas();
  const linhas = jogadores.map(j => {
    const lista = todas.filter(doJogador(j));
    const s = somar(lista);
    const cont = {};
    lista.forEach(p => { cont[p.campeao] = (cont[p.campeao] || 0) + 1; });
    const top = Object.entries(cont).sort((a, b) => b[1] - a[1])[0];
    const cels = [celJogador(j), String(s.n)];
    if (GERAL) cels.push(FILAS.map(f => lista.filter(p => (p.fila || "solo") === f).length).join(" / "));
    cels.push(s.n ? `${pct(s.v, s.n)} (${s.v}V ${s.n - s.v}D)` : "—",
      s.n ? fmt(s.kda, 2) : "—", s.min ? fmt(s.cs / s.min) : "—", danoMin(s),
      top ? celCampeao(top[0]) : "—");
    return { val: valores(j.nome, s), cels };
  });
  const cab = [["Atleta", 0, "nome"], ["Partidas", 1, "n"]];
  if (GERAL) cab.push([FILAS.map(f => SIGLA_FILA[f]).join(" / "), 1]);
  cab.push(["Winrate", 1, "wr"], ["KDA", 1, "kda"], ["CS/min", 1, "cs"], ["Dano/min", 1, "dano"], ["Mais jogado"]);
  tabela("tab-atletas", cab, linhas);
}

function desenharCampeoes(lista) {
  const grupos = {};
  lista.forEach(p => (grupos[p.campeao] ||= []).push(p));
  const linhas = Object.entries(grupos)
    .filter(([, ps]) => ps.length >= minPartidas)
    .map(([nome, ps]) => {
      const s = somar(ps);
      const quem = new Set(ps.map(p => p.riot_id.toLowerCase()));
      const cels = [celCampeao(nome), String(s.n), `${pct(s.v, s.n)} (${s.v}V ${s.n - s.v}D)`,
        `${fmt(s.kda, 2)}`, kdaTexto(s), fmt(s.cs / s.min), danoMin(s)];
      if (!sel) cels.push(jogadores.filter(j => quem.has(j.riot_id.toLowerCase())).map(j => j.nome).join(", "));
      return { val: valores(campeao(nome).nome, s), cels };
    });
  const cab = [["Campeão", 0, "nome"], ["Partidas", 1, "n"], ["Winrate", 1, "wr"], ["KDA", 1, "kda"],
    ["Abates / Mortes / Assist.", 1], ["CS/min", 1, "cs"], ["Dano/min", 1, "dano"]];
  if (!sel) cab.push(["Quem jogou"]);
  tabela("tab-campeoes", cab, linhas);
}

function render() {
  const lista = selecionadas();
  desenharFiltro();
  desenharTiles(lista);
  desenharGrafico(lista);
  desenharAtletas();
  desenharCampeoes(lista);
}

async function dataDragon() {
  try {
    const versoes = await fetch("https://ddragon.leagueoflegends.com/api/versions.json").then(r => r.json());
    const dados = await fetch(`https://ddragon.leagueoflegends.com/cdn/${versoes[0]}/data/pt_BR/champion.json`).then(r => r.json());
    dd = { versao: versoes[0], porId: Object.fromEntries(Object.values(dados.data).map(c => [c.id.toLowerCase(), c])) };
  } catch { /* sem ícones: mostra só os nomes */ }
}

document.querySelectorAll("select.ordem").forEach(s => s.addEventListener("change", () => {
  ordem[s.dataset.tabela] = { chave: s.value, desc: s.value !== "nome" };
  render();
}));
document.getElementById("min-partidas").addEventListener("change", e => { minPartidas = Number(e.target.value); render(); });
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => jogadores.length && render());

Promise.all([
  fetch("dados.json", { cache: "no-store" }).then(r => r.json()),
  fetch("partidas.json", { cache: "no-store" }).then(r => (r.ok ? r.json() : [])),
  dataDragon(),
]).then(([d, p]) => {
  jogadores = d.jogadores;
  partidas = p;
  const quando = new Date(d.atualizado_em);
  const texto = DESCRICAO[0].toUpperCase() + DESCRICAO.slice(1);
  document.getElementById("sub").textContent =
    `${texto} desde 02/10 · atualizado em ${quando.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}`;
  render();
}).catch(() => {
  document.getElementById("sub").textContent = "Ainda não há dados.";
});

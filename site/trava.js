// Trava das abas privadas: pede a senha e decifra os arquivos que o privado.py publica
// criptografados (AES-256-GCM, chave da senha por PBKDF2-SHA256), tudo no navegador.
// A senha fica na sessionStorage: destrancar uma aba destranca as outras até fechar a aba do navegador.
// Uso: Trava.abrir(["scout.json"]).then(([scout]) => ...). Enquanto não abre, tudo que vem
// depois do menu de abas fica escondido e no lugar aparece a tela de senha.
(() => {
  const CHAVE = "privado-senha";
  const bytes = b64 => Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  const cifrado = d => !!d && typeof d === "object" && "sal" in d && "iv" in d && "dados" in d;
  const lerSenha = () => { try { return sessionStorage.getItem(CHAVE); } catch { return null; } };
  const guardar = s => { try { sessionStorage.setItem(CHAVE, s); } catch {} };
  const esquecer = () => { try { sessionStorage.removeItem(CHAVE); } catch {} };

  async function decifrar(pacote, senha) {
    const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(senha), "PBKDF2", false, ["deriveKey"]);
    const chave = await crypto.subtle.deriveKey(
      { name: "PBKDF2", hash: "SHA-256", salt: bytes(pacote.sal), iterations: pacote.iteracoes },
      base, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    const claro = await crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes(pacote.iv) }, chave, bytes(pacote.dados));
    return JSON.parse(new TextDecoder().decode(claro));
  }

  function el(tag, props = {}, ...filhos) {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...filhos);
    return e;
  }

  // Tudo que vem depois do menu de abas é conteúdo da página.
  function conteudo() {
    const nav = document.querySelector("nav.abas");
    const irmaos = [...nav.parentElement.children];
    return { nav, partes: irmaos.slice(irmaos.indexOf(nav) + 1) };
  }

  function mostrarConteudo() {
    const { nav, partes } = conteudo();
    partes.forEach(p => { if (p.dataset.travaEscondido) { p.hidden = false; delete p.dataset.travaEscondido; } });
    document.getElementById("trava")?.remove();
    if (!document.getElementById("trancar")) {
      const botao = el("button", { type: "button", id: "trancar", className: "botao-trancar", textContent: "🔒 Trancar" });
      botao.addEventListener("click", () => { esquecer(); location.reload(); });
      nav.append(botao);
    }
  }

  function esconderConteudo() {
    conteudo().partes.forEach(p => { if (!p.hidden) { p.hidden = true; p.dataset.travaEscondido = "1"; } });
  }

  function avisar(texto) {
    const sub = document.getElementById("sub");
    if (sub) sub.textContent = texto;
  }

  function telaDeSenha(tentar) {
    const { nav } = conteudo();
    const senha = el("input", { type: "password", autocomplete: "current-password", required: true });
    senha.setAttribute("aria-label", "Senha");
    const botao = el("button", { type: "submit", textContent: "Abrir" });
    const erro = el("p", { className: "erro", hidden: true });
    const form = el("form", {}, senha, botao);
    const card = el("section", { className: "card trava", id: "trava" },
      el("h2", { textContent: "🔒 Aba privada" }),
      el("p", { className: "explica", textContent: "Digite a senha. Ela vale para todas as abas privadas até você fechar esta aba do navegador." }),
      form, erro);
    form.addEventListener("submit", async e => {
      e.preventDefault();
      erro.hidden = true;
      botao.disabled = true;
      botao.textContent = "Abrindo…";
      const ok = await tentar(senha.value);
      botao.disabled = false;
      botao.textContent = "Abrir";
      if (!ok) {
        erro.textContent = "Senha errada.";
        erro.hidden = false;
        senha.select();
      }
    });
    nav.after(card);
    senha.focus();
  }

  async function abrir(arquivos) {
    esconderConteudo();
    let brutos;
    try {
      brutos = await Promise.all(arquivos.map(a => fetch(a, { cache: "no-store" }).then(r => {
        if (!r.ok) throw new Error(`${a}: ${r.status}`);
        return r.json();
      })));
    } catch (e) {
      avisar("Esta aba ainda não foi publicada.");
      throw e;
    }
    // Arquivo sem criptografia (rodando o site localmente): abre direto.
    if (!brutos.some(cifrado)) { mostrarConteudo(); return brutos; }

    const decifrarTodos = senha => Promise.all(brutos.map(b => (cifrado(b) ? decifrar(b, senha) : b)));
    const salva = lerSenha();
    if (salva) {
      try {
        const dados = await decifrarTodos(salva);
        mostrarConteudo();
        return dados;
      } catch { esquecer(); }
    }
    avisar("🔒 Aba privada: só abre com a senha.");
    return new Promise(resolve => telaDeSenha(async senha => {
      try {
        const dados = await decifrarTodos(senha);
        guardar(senha);
        mostrarConteudo();
        resolve(dados);
        return true;
      } catch {
        return false;
      }
    }));
  }

  window.Trava = { abrir };
})();

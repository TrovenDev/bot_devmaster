// Painel de gestão do Bot DevMaster (Supabase: Auth + Postgres com RLS + Realtime).
// Sem framework: o DOM é montado com h() (textContent), nunca com innerHTML.
"use strict";

const raiz = document.getElementById("raiz");
const ONLINE_MS = 10 * 60 * 1000;
let sb = null;
let catalogo = [];
let canalRealtime = null;
let aoVivo = () => {};

// ---------------- Utilitários ----------------
function h(tag, attrs = {}, ...filhos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v === null || v === undefined) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const f of filhos.flat()) if (f !== null && f !== undefined && f !== false) el.append(f.nodeType ? f : String(f));
  return tag === "select" ? seletor(el) : el;
}

// Select do Greta adaptado ao DOM do console, mantendo value/change.
let sequenciaSelect = 0;
function seletor(nativo) {
  const id = nativo.id;
  nativo.removeAttribute("id");
  nativo.hidden = true;
  const listaId = `select-opcoes-${++sequenciaSelect}`;
  const rotulo = h("span", {}, nativo.selectedOptions[0]?.textContent || "Selecionar...");
  const trigger = h("button", { type: "button", class: "select-trigger", id: id || undefined,
    role: "combobox", "aria-haspopup": "listbox", "aria-controls": listaId, "aria-expanded": "false",
    "aria-label": nativo.getAttribute("aria-label") || undefined, disabled: nativo.disabled }, rotulo);
  const lista = h("div", { class: "select-opcoes", id: listaId, role: "listbox", hidden: true,
    "aria-label": nativo.getAttribute("aria-label") || "Op\u00e7\u00f5es" });
  const wrapper = h("div", { class: "select-ui" }, nativo, trigger, lista);
  Object.defineProperty(wrapper, "value", { get: () => nativo.value, set: v => { nativo.value = v; atualizar(); } });
  const fechar = () => { lista.hidden = true; trigger.setAttribute("aria-expanded", "false"); };
  const atualizar = () => {
    rotulo.textContent = nativo.selectedOptions[0]?.textContent || "Selecionar...";
    lista.replaceChildren(...[...nativo.options].map(opcao => h("button", {
      type: "button", class: "select-opcao", role: "option", tabindex: "-1", disabled: opcao.disabled,
      "aria-selected": opcao.selected ? "true" : "false",
      onclick: () => { nativo.value = opcao.value; atualizar(); fechar(); trigger.focus(); nativo.dispatchEvent(new Event("change", { bubbles: true })); }
    }, opcao.textContent)));
  };
  const abrir = (ultimo = false) => {
    atualizar(); lista.hidden = false; trigger.setAttribute("aria-expanded", "true");
    const rect = trigger.getBoundingClientRect();
    lista.classList.toggle("acima", window.innerHeight - rect.bottom < 220 && rect.top > 220);
    const opcoes = [...lista.querySelectorAll("button:not(:disabled)")];
    (ultimo ? opcoes.at(-1) : opcoes.find(b => b.getAttribute("aria-selected") === "true") || opcoes[0])?.focus();
  };
  trigger.addEventListener("click", () => lista.hidden ? abrir() : fechar());
  wrapper.addEventListener("keydown", e => {
    if (e.key === "Escape" && !lista.hidden) { e.preventDefault(); e.stopPropagation(); fechar(); trigger.focus(); }
    else if (e.key === "Tab") fechar();
    else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      if (lista.hidden) { abrir(e.key === "End"); return; }
      const opcoes = [...lista.querySelectorAll("button:not(:disabled)")];
      const index = opcoes.indexOf(document.activeElement);
      const proximo = e.key === "Home" ? 0 : e.key === "End" ? opcoes.length - 1 : (index + (e.key === "ArrowDown" ? 1 : -1) + opcoes.length) % opcoes.length;
      opcoes[proximo]?.focus();
    }
  });
  wrapper.addEventListener("focusout", e => { if (!wrapper.contains(e.relatedTarget)) fechar(); });
  nativo.addEventListener("change", atualizar);
  atualizar();
  return wrapper;
}

function traduzir(erro) {
  const c = erro.code || "";
  const m = erro.message || String(erro);
  if (c === "23503") return "Este registro está em uso por outros dados. Remova ou mude o que depende dele antes.";
  if (c === "23505") return "Já está cadastrado.";
  if (c === "23514") return "Valor inválido. Confira os campos (número com DDI+DDD, ID só com números, arquivo sem pasta).";
  if (c === "23502") return "Preencha os campos obrigatórios.";
  if (c === "42501" || /permission denied|row-level security/i.test(m)) return "Sem permissão para esta operação.";
  if (/JWT expired|invalid JWT/i.test(m)) return "Sessão expirada. Entre de novo.";
  if (/Failed to fetch|NetworkError/i.test(m)) return "Sem conexão com o servidor.";
  return m;
}

/** Executa uma consulta do supabase-js e devolve os dados (ou lança erro em português). */
async function q(consulta) {
  const { data, error } = await consulta;
  if (error) {
    const e = new Error(traduzir(error));
    e.original = error;
    if (/JWT expired|invalid JWT/i.test(error.message || "")) { await sb.auth.signOut(); mostrarLogin(); }
    throw e;
  }
  return data;
}

let tempoToast;
function aviso(texto, erro = false) {
  const t = document.getElementById("toast");
  t.textContent = texto;
  t.className = "mostrar" + (erro ? " erro" : "");
  clearTimeout(tempoToast);
  tempoToast = setTimeout(() => (t.className = ""), erro ? 5000 : 2600);
}

async function tentar(fn) {
  try { return await fn(); } catch (e) { aviso(e.message, true); }
}

function quando(iso) {
  if (!iso) return "nunca";
  const d = new Date(iso);
  const seg = (Date.now() - d.getTime()) / 1000;
  if (seg < 60) return "agora há pouco";
  if (seg < 3600) return `há ${Math.floor(seg / 60)} min`;
  if (seg < 86400) return `há ${Math.floor(seg / 3600)} h`;
  return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

const estaOnline = (s) => !!s.ultimo_contato && Date.now() - new Date(s.ultimo_contato).getTime() < ONLINE_MS;

function janela(titulo, corpo, acoes, sheet = false) {
  const anterior = document.activeElement;
  const painel = h("div", { class: sheet ? "janela sheet" : "janela", tabindex: "-1" });
  const fundo = h("div", { class: "fundo" + (sheet ? " fundo-sheet" : ""), role: "dialog", "aria-modal": "true", "aria-label": titulo }, painel);
  const fechar = () => { fundo.remove(); document.body.style.overflow = ""; anterior?.focus(); };
  painel.append(h("div", { class: "sheet-topo" }, h("h2", {}, titulo), h("button", { class: "btn sec mini", "aria-label": "Fechar", onclick: fechar }, "\u00d7")), h("div", { class: "janela-corpo" }, corpo), h("div", { class: "acoes" }, acoes(fechar)));
  fundo.addEventListener("click", (e) => { if (e.target === fundo) fechar(); });
  fundo.addEventListener("keydown", (e) => {
    if (e.key === "Escape") fechar();
    if (e.key !== "Tab") return;
    const itens = [...painel.querySelectorAll('button, input, select, textarea, a[href]')].filter(el => !el.disabled && !el.closest('[hidden]') && el.tabIndex >= 0);
    const primeiro = itens[0], ultimo = itens.at(-1);
    if (e.shiftKey && (document.activeElement === primeiro || document.activeElement === painel)) { e.preventDefault(); ultimo?.focus(); }
    else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro?.focus(); }
  });
  document.body.append(fundo);
  document.body.style.overflow = "hidden";
  painel.focus();
  return fundo;
}

function confirmar(titulo, mensagem, rotulo, aoConfirmar) {
  janela(titulo, h("p", {}, mensagem), (fechar) => [
    h("button", { class: "btn sec", onclick: fechar }, "Cancelar"),
    h("button", { class: "btn perigo", onclick: () => { fechar(); aoConfirmar(); } }, rotulo),
  ]);
}

// O instalador de cada sistema é montado aqui no navegador: o Setup.exe genérico + "endereço|chave" no fim do
// arquivo (o instalador lê esse trecho). A chave não passa por nenhum servidor.
const MARCA_INSTALADOR = "#DMB" + "KEY#";
async function baixarInstalador(chave, botao) {
  const texto = botao.textContent;
  botao.disabled = true;
  botao.textContent = "Preparando…";
  try {
    const r = await fetch("/api/instalador");
    if (!r.ok) throw new Error("O instalador ainda não foi publicado (publique uma versão no GitHub).");
    const base = new Uint8Array(await r.arrayBuffer());
    const trecho = chave ? new TextEncoder().encode(`
${MARCA_INSTALADOR}${location.origin}|${chave}${MARCA_INSTALADOR}
`) : new Uint8Array();
    const arquivo = new Uint8Array(base.length + trecho.length);
    arquivo.set(base);
    arquivo.set(trecho, base.length);
    const link = h("a", { href: URL.createObjectURL(new Blob([arquivo], { type: "application/octet-stream" })), download: "BotDevMaster-Setup.exe" });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 60000);
    aviso("Instalador baixado");
  } catch (e) {
    aviso(e.message, true);
  } finally {
    botao.disabled = false;
    botao.textContent = texto;
  }
}

function mostrarChave(chave, titulo = "Chave do sistema") {
  janela(titulo,
    h("div", {},
      h("p", {}, "Baixe o instalador abaixo: ele já leva esta chave e o endereço do painel, é só abrir no computador do cliente. Guarde a chave também: por segurança, ela não será mostrada de novo."),
      h("div", { class: "chave" }, h("code", {}, chave))),
    (fechar) => {
      const baixar = h("button", { class: "btn", onclick: () => baixarInstalador(chave, baixar) }, "Baixar instalador com esta chave");
      return [
        baixar,
        h("button", { class: "btn sec", onclick: async () => { await navigator.clipboard.writeText(chave).catch(() => {}); aviso("Chave copiada"); } }, "Copiar chave"),
        h("button", { class: "btn sec", onclick: fechar }, "Já guardei"),
      ];
    });
}

// ---------------- Login e estrutura ----------------
function semConfiguracao() {
  raiz.replaceChildren(h("div", { class: "login" }, h("div", { class: "card aviso-vazio" },
    h("h2", {}, "Painel sem configuração"),
    h("p", {}, "Defina as variáveis do projeto no Cloudflare Pages:"),
    h("pre", {}, "SUPABASE_URL\nSUPABASE_PUBLISHABLE_KEY"),
    h("p", { class: "mudo" }, "Settings › Variables and Secrets. Depois faça um novo deploy."))));
}

function mostrarLogin(mensagem = "") {
  if (canalRealtime) { sb.removeChannel(canalRealtime); canalRealtime = null; }
  raiz.replaceChildren(
    h("div", { class: "login" },
      h("form", {
        onsubmit: async (e) => {
          e.preventDefault();
          const msg = e.target.querySelector(".msg");
          msg.textContent = "";
          const { error } = await sb.auth.signInWithPassword({ email: e.target.email.value.trim(), password: e.target.senha.value });
          if (error) { msg.textContent = /invalid login/i.test(error.message) ? "E-mail ou senha incorretos." : traduzir(error); return; }
          iniciar();
        },
      },
        h("img", { src: "/troven-horizontal-negativo.svg", alt: "Troven" }),
        h("h1", {}, "Gestão do Bot DevMaster"),
        h("p", {}, "Entre para gerenciar empresas, sistemas e chaves."),
        h("label", { for: "email" }, "E-mail"),
        h("input", { id: "email", name: "email", type: "email", autocomplete: "username", required: true, autofocus: true }),
        h("label", { for: "senha" }, "Senha"),
        h("input", { id: "senha", name: "senha", type: "password", autocomplete: "current-password", required: true }),
        h("button", { class: "btn", type: "submit" }, "Entrar"),
        h("div", { class: "msg", role: "alert" }, mensagem))));
}

function semAcesso(usuario) {
  raiz.replaceChildren(h("div", { class: "login" }, h("div", { class: "card aviso-vazio" },
    h("h2", {}, "Seu usuário ainda não é administrador"),
    h("p", {}, "O login funcionou, mas falta liberar o acesso. No Supabase, abra o SQL Editor e rode:"),
    h("pre", {}, `insert into public.administradores (usuario_id, nome)\nvalues ('${usuario.id}', 'Seu nome');`),
    h("div", { class: "linha" },
      h("button", { class: "btn", onclick: () => iniciar() }, "Já liberei, entrar"),
      h("button", { class: "btn sec", onclick: async () => { await sb.auth.signOut(); mostrarLogin(); } }, "Sair")))));
}

function estrutura(usuario) {
  const link = (href, texto) => h("a", { href, "data-rota": href }, texto);
  const vivo = h("span", { class: "vivo", title: "Atualização em tempo real" }, "ao vivo");
  aoVivo = (ligado) => vivo.classList.toggle("ligado", ligado);
  raiz.replaceChildren(
    h("header", { class: "topo" },
      h("img", { src: "/troven-horizontal-negativo.svg", alt: "Troven" }),
      h("nav", {}, link("#/", "Sistemas"), link("#/empresas", "Empresas"), link("#/execucoes", "Execuções")),
      vivo,
      h("button", { title: usuario.email, onclick: async () => { await sb.auth.signOut(); mostrarLogin(); } }, "Sair")),
    h("main", { id: "conteudo" }));
}

function marcarMenu() {
  const rota = location.hash || "#/";
  for (const a of document.querySelectorAll(".topo nav a")) {
    const alvo = a.dataset.rota;
    a.classList.toggle("ativo", alvo === "#/" ? rota === "#/" || rota.startsWith("#/sistema") : rota.startsWith(alvo));
  }
}

// ---------------- Realtime ----------------
let atualizadores = []; // funções da página atual chamadas quando algo muda no banco
let tempoRefresh;

function escutarMudancas() {
  if (canalRealtime) sb.removeChannel(canalRealtime);
  const aoMudar = () => {
    clearTimeout(tempoRefresh);
    tempoRefresh = setTimeout(() => atualizadores.forEach((f) => f().catch(() => {})), 400);
  };
  canalRealtime = sb.channel("painel");
  for (const tabela of ["empresas", "sistemas", "sistema_comandos", "sistema_canais", "contatos", "execucoes"]) {
    canalRealtime.on("postgres_changes", { event: "*", schema: "public", table: tabela }, aoMudar);
  }
  canalRealtime.subscribe((estado) => aoVivo(estado === "SUBSCRIBED"));
}

// o "online" depende do relógio: reavalia a cada minuto sem precisar de evento no banco
setInterval(() => atualizadores.forEach((f) => f().catch(() => {})), 60_000);

// ---------------- Páginas ----------------
const numero = (valor, rotulo, alerta = false) => h("div", { class: "numero" + (alerta ? " alerta" : "") }, h("b", {}, valor), h("span", {}, rotulo));
const tabela = (cabecas, linhas) => h("table", {}, h("thead", {}, h("tr", {}, cabecas.map((t) => h("th", {}, t)))), h("tbody", {}, linhas));
const seloSistema = (s) => (!s.ativo ? h("span", { class: "selo erro" }, "desativado") : estaOnline(s) ? h("span", { class: "selo online" }, "online") : h("span", { class: "selo offline" }, "offline"));

async function paginaSistemas(c) {
  const cabeca = h("div", { class: "cabeca" }, h("div", {}, h("div", { class: "sobre" }, "Visão geral"), h("h1", {}, "Sistemas")),
    h("button", { class: "btn", onclick: () => (location.hash = "#/sistema/novo") }, "+ Novo sistema"));
  const numeros = h("div", { class: "grade" });
  const lista = h("div", { class: "card tabela-rolagem" });
  c.replaceChildren(cabeca, numeros, lista);

  const carregar = async () => {
    const [resumo, sistemas] = await Promise.all([q(sb.rpc("painel_resumo")), q(sb.from("sistemas").select("*, empresas(nome)").order("nome"))]);
    numeros.replaceChildren(
      numero(`${resumo.online}/${resumo.sistemas}`, "sistemas online"), numero(resumo.empresas, "empresas"),
      numero(resumo.execucoes_24h, "execuções em 24 h"), numero(resumo.falhas_24h, "falhas em 24 h", resumo.falhas_24h > 0));
    lista.replaceChildren(sistemas.length ? tabela(["Sistema", "Empresa", "Situação", "Versão", "Último contato"],
      sistemas.map((s) => h("tr", { class: "clicavel", tabindex: "0", onclick: () => (location.hash = `#/sistema/${s.id}`),
        onkeydown: (e) => { if (e.key === "Enter") location.hash = `#/sistema/${s.id}`; } },
        h("td", {}, h("b", {}, s.nome)), h("td", {}, s.empresas?.nome), h("td", {}, seloSistema(s)),
        h("td", { class: "mono" }, s.versao || "—"), h("td", { class: "mudo" }, quando(s.ultimo_contato)))))
      : h("div", { class: "vazio" }, "Nenhum sistema ainda. Cadastre uma empresa e crie o primeiro sistema."));
  };
  atualizadores = [carregar];
  await carregar();
}

const CONECTORES = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'em', 'com', 'para', 'a', 'o'])
const SIGLAS = new Set(['ltda', 'me', 'epp', 'mei', 'eireli', 'sa', 's/a', 'ei'])

const VOGAIS = /[aeiouáéíóúâêôãõà]/i

// Sigla/iniciais (JF, GHR, DBM): 2 a 4 letras e nenhuma vogal — continua em maiúsculo em vez de virar "Jf".
function ehSigla(palavra) {
  const letras = palavra.replace(/[.,/-]/g, '')
  return /^[a-zà-ú]{2,4}$/i.test(letras) && !VOGAIS.test(letras)
}

// MEI e empresário individual vêm da Receita como "NOME 12345678000190": tira do começo e do fim do nome
// o que for número (parte do CNPJ), sem mexer em números que fazem parte do nome de verdade.
function tirarNumeroDoCnpj(texto, cnpj) {
  const digitosCnpj = cnpj.replace(/\D/g, '')
  const ehNumeroDoCnpj = (token) => {
    const digitos = token.replace(/\D/g, '')
    return digitos.length > 0 && /^[\d.\-/]+$/.test(token) && (digitos.length >= 6 || digitosCnpj.includes(digitos))
  }
  const palavras = texto.trim().split(/\s+/)
  while (palavras.length > 1 && ehNumeroDoCnpj(palavras[palavras.length - 1])) palavras.pop()
  while (palavras.length > 1 && ehNumeroDoCnpj(palavras[0])) palavras.shift()
  return palavras.join(' ')
}

function paraTitleCase(texto) {
  return texto
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map((palavra, i) => {
      const semPontuacao = palavra.replace(/[.,/]/g, '')
      if (SIGLAS.has(semPontuacao) || ehSigla(palavra)) return palavra.toUpperCase()
      if (i > 0 && CONECTORES.has(palavra)) return palavra
      return palavra.charAt(0).toUpperCase() + palavra.slice(1)
    })
    .join(' ')
}



async function paginaEmpresas(c) {
  const editar = (e = {}) => {
    const nome = h("input", { type: "text", id: "en", value: e.nome || "", maxlength: 120, required: true });
    const doc = h("input", { type: "text", id: "ed", value: e.documento || "", maxlength: 18, inputmode: "numeric", autocomplete: "off", placeholder: "00.000.000/0000-00", "aria-describedby": "cnpj-status" });
    const obs = h("input", { type: "text", id: "eo", value: e.observacao || "", maxlength: 500 });
    const ativa = h("input", { type: "checkbox", role: "switch", class: "toggle", id: "empresa-ativa", checked: e.id ? !!e.ativa : true });
    const situacao = h("span", {}, ativa.checked ? "Ativa" : "Inativa");
    ativa.addEventListener("change", () => { situacao.textContent = ativa.checked ? "Ativa" : "Inativa"; });
    const status = h("p", { id: "cnpj-status", class: "mudo", role: "status", "aria-live": "polite" }, "Informe o CNPJ para preencher o nome automaticamente.");
    let consulta = 0;
    let ultimoCnpj = "";
    doc.addEventListener("input", async () => {
      const cnpj = doc.value.replace(/\D/g, "").slice(0, 14);
      doc.value = cnpj.replace(/^(\d{2})(\d)/, "$1.$2").replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3").replace(/\.(\d{3})(\d)/, ".$1/$2").replace(/(\d{4})(\d)/, "$1-$2");
      if (cnpj === ultimoCnpj) return;
      ultimoCnpj = cnpj;
      const atual = ++consulta;
      if (cnpj.length !== 14) { status.textContent = "Informe os 14 d\u00edgitos do CNPJ."; return; }
      status.textContent = "Consultando CNPJ\u2026";
      try {
        const r = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${cnpj}`, { signal: AbortSignal.timeout(15000) });
        if (atual !== consulta || !doc.isConnected) return;
        if (!r.ok) throw new Error(r.status === 404 ? "CNPJ n\u00e3o encontrado." : r.status === 429 ? "Limite de consultas atingido. Tente novamente mais tarde." : "Consulta de CNPJ indispon\u00edvel no momento.");
        const dados = await r.json();
        if (atual !== consulta || !doc.isConnected) return;
        const encontrado = dados.nome_fantasia || dados.razao_social;
        if (typeof encontrado !== "string" || !encontrado.trim()) throw new Error("A consulta n\u00e3o retornou o nome da empresa.");
        nome.value = paraTitleCase(tirarNumeroDoCnpj(encontrado, cnpj)).slice(0, 120);
        status.textContent = "Empresa encontrada. Confira os dados antes de salvar.";
      } catch (erro) {
        if (atual !== consulta || !doc.isConnected) return;
        status.textContent = erro.name === "TimeoutError" ? "A consulta demorou demais. Tente novamente." : /Failed to fetch|NetworkError/i.test(erro.message) ? "Sem conex\u00e3o com a BrasilAPI. Tente novamente." : erro.message;
        ultimoCnpj = "";
      }
    });
    janela(e.id ? "Editar empresa" : "Nova empresa",
      h("div", { class: "campos" }, h("div", {}, h("label", { for: "ed" }, "CNPJ"), doc, status), h("div", {}, h("label", { for: "en" }, "Nome"), nome),
        h("div", {}, h("label", { for: "eo" }, "Observação"), obs), h("div", {}, h("label", { for: "empresa-ativa" }, "Status"), h("label", { class: "marcar toggle-label" }, ativa, situacao))),
      (fechar) => [h("button", { class: "btn sec", onclick: fechar }, "Cancelar"),
        h("button", { class: "btn", onclick: () => tentar(async () => {
          if (!nome.value.trim()) { nome.focus(); throw new Error("Informe o nome da empresa."); }
          const corpo = { nome: nome.value.trim(), documento: doc.value.trim(), observacao: obs.value.trim(), ativa: ativa.checked };
          await q(e.id ? sb.from("empresas").update(corpo).eq("id", e.id) : sb.from("empresas").insert(corpo));
          fechar(); aviso("Empresa salva");
        }) }, "Salvar")], true);
  };
  let registros = [], pagina = 1, ordem = "nome", ascendente = true;
  const selecionados = new Set();
  const lista = h("div", { class: "empresas-lista" });
  const busca = h("input", { type: "search", placeholder: "Pesquisar por nome ou CNPJ...", "aria-label": "Pesquisar empresas" });
  const barraSelecao = h("div", { class: "empresas-selecao", hidden: true });
  const normalizar = texto => String(texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const atualizar = () => {
    const termo = normalizar(busca.value.trim());
    const filtrados = registros.filter(e => normalizar(e.nome).includes(termo) || normalizar(e.documento).includes(termo) || (termo.replace(/\D/g, "") && String(e.documento || "").replace(/\D/g, "").includes(termo.replace(/\D/g, ""))));
    const valor = e => ordem === "sistemas" ? e.sistemas?.[0]?.count || 0 : ordem === "ativa" ? Number(e.ativa) : e[ordem] || "";
    filtrados.sort((a,b) => (typeof valor(a) === "number" ? valor(a) - valor(b) : String(valor(a)).localeCompare(String(valor(b)), "pt-BR")) * (ascendente ? 1 : -1));
    const total = Math.max(1, Math.ceil(filtrados.length / 10));
    pagina = Math.min(pagina, total);
    const visiveis = filtrados.slice((pagina - 1) * 10, pagina * 10);
    const selecionar = (id, marcada) => { marcada ? selecionados.add(id) : selecionados.delete(id); atualizar(); };
    const todos = h("input", { type: "checkbox", "aria-label": "Selecionar todas as empresas desta p\u00e1gina", checked: visiveis.length > 0 && visiveis.every(e => selecionados.has(e.id)), onchange: ev => { visiveis.forEach(e => ev.target.checked ? selecionados.add(e.id) : selecionados.delete(e.id)); atualizar(); } });
    todos.indeterminate = visiveis.some(e => selecionados.has(e.id)) && !visiveis.every(e => selecionados.has(e.id));
    const cabecalho = (titulo, chave) => h("th", { scope: "col", "aria-sort": ordem === chave ? ascendente ? "ascending" : "descending" : "none" }, h("button", { class: "ordenar", onclick: () => { ascendente = ordem === chave ? !ascendente : true; ordem = chave; atualizar(); } }, titulo, ordem === chave ? ascendente ? " \u2191" : " \u2193" : ""));
    const tabelaEmpresas = h("table", { class: "empresas-tabela" },
      h("thead", {}, h("tr", {}, h("th", { class: "col-selecao" }, todos), cabecalho("Nome", "nome"), cabecalho("CNPJ", "documento"), cabecalho("Sistemas", "sistemas"), cabecalho("Status", "ativa"))),
      h("tbody", {}, visiveis.map(e => {
        const toggle = h("input", { type: "checkbox", role: "switch", class: "toggle", checked: !!e.ativa, "aria-label": `Empresa ${e.nome} ativa`, onchange: async () => {
          toggle.disabled = true;
          try { await q(sb.from("empresas").update({ ativa: toggle.checked }).eq("id", e.id)); e.ativa = toggle.checked; atualizar(); aviso("Status atualizado"); }
          catch (erro) { toggle.checked = !!e.ativa; aviso(erro.message, true); }
          finally { toggle.disabled = false; }
        } });
        return h("tr", { class: selecionados.has(e.id) ? "selecionada" : "" },
          h("td", { class: "col-selecao" }, h("input", { type: "checkbox", checked: selecionados.has(e.id), "aria-label": `Selecionar ${e.nome}`, onchange: ev => selecionar(e.id, ev.target.checked) })),
          h("td", { "data-label": "Nome" }, h("button", { class: "empresa-nome", onclick: () => editar(e), title: "Editar empresa" }, e.nome), e.observacao ? h("div", { class: "mudo" }, e.observacao) : null),
          h("td", { "data-label": "CNPJ", class: "tabular" }, e.documento || "Sem cadastro"),
          h("td", { "data-label": "Sistemas", class: "tabular" }, e.sistemas?.[0]?.count ?? 0),
          h("td", { "data-label": "Status" }, h("label", { class: "marcar toggle-label" }, toggle, h("span", {}, e.ativa ? "Ativa" : "Inativa"))));
      })));
    const ir = numero => { pagina = numero; atualizar(); };
    const paginas = [...new Set([1, pagina - 1, pagina, pagina + 1, total])].filter(n => n >= 1 && n <= total).sort((a,b) => a-b);
    const botoesPaginas = [];
    paginas.forEach((n,i) => {
      if (i && n - paginas[i-1] > 1) botoesPaginas.push(h("span", {}, "\u2026"));
      botoesPaginas.push(h("button", { class: n === pagina ? "atual" : "", "aria-label": `P\u00e1gina ${n}`, "aria-current": n === pagina ? "page" : undefined, onclick: () => ir(n) }, n));
    });
    const rodape = h("div", { class: "empresas-paginacao" },
      h("nav", { "aria-label": "Pagina\u00e7\u00e3o de empresas" }, h("button", { "aria-label": "P\u00e1gina anterior", disabled: pagina === 1, onclick: () => ir(pagina-1) }, "\u2039"), botoesPaginas, h("button", { "aria-label": "Pr\u00f3xima p\u00e1gina", disabled: pagina === total, onclick: () => ir(pagina+1) }, "\u203a")),
      h("span", { class: "mudo" }, `${filtrados.length} ${filtrados.length === 1 ? "empresa" : "empresas"}`));
    lista.replaceChildren(filtrados.length ? h("div", { class: "empresas-scroll" }, tabelaEmpresas) : h("div", { class: "empresas-vazio" }, h("h2", {}, "Nenhuma empresa"), h("p", { class: "mudo" }, termo ? "Nenhum resultado para esta busca." : "Adicione a primeira empresa para come\u00e7ar.")), rodape);
    barraSelecao.hidden = !selecionados.size;
    barraSelecao.replaceChildren(h("span", {}, `${selecionados.size} ${selecionados.size === 1 ? "item selecionado" : "itens selecionados"}`),
      h("button", { class: "btn sec", onclick: () => { selecionados.clear(); atualizar(); } }, "Limpar sele\u00e7\u00e3o"),
      h("button", { class: "acao-excluir", onclick: () => {
        const ids = [...selecionados];
        confirmar("Excluir empresas", `Excluir ${ids.length} ${ids.length === 1 ? "empresa selecionada" : "empresas selecionadas"}?`, "Excluir", () => tentar(async () => { await q(sb.from("empresas").delete().in("id", ids)); ids.forEach(id => selecionados.delete(id)); await carregar(); aviso("Empresas exclu?das"); }));
      } }, "Excluir"));
  };
  busca.addEventListener("input", () => { pagina = 1; atualizar(); });
  c.replaceChildren(h("section", { class: "empresas-pagina", "aria-label": "Empresas" },
    h("div", { class: "empresas-toolbar" }, h("button", { class: "btn", onclick: () => editar() }, "+ Adicionar"), h("div", { class: "empresas-busca" }, h("span", { "aria-hidden": "true", class: "busca-icone" }), busca)), lista, barraSelecao));
  const carregar = async () => {
    registros = await q(sb.from("empresas").select("*, sistemas(count)").order("nome"));
    const ids = new Set(registros.map(e => e.id));
    selecionados.forEach(id => { if (!ids.has(id)) selecionados.delete(id); });
    atualizar();
  };
  atualizadores = [carregar];
  await carregar();
}

function tabelaExecucoes(lista, comSistema) {
  return tabela([comSistema ? "Sistema" : null, "Quando", "Comando", "Canal", "Solicitante", "Resultado", "Duração"].filter(Boolean),
    lista.map((x) => h("tr", {}, comSistema ? h("td", {}, x.sistemas?.nome) : null, h("td", { class: "mudo" }, quando(x.criada_em)), h("td", {}, x.comando),
      h("td", {}, x.canal || "—"), h("td", { class: "mono" }, x.solicitante || "—"),
      h("td", {}, x.sucesso ? h("span", { class: "selo ok" }, "ok") : h("span", { class: "selo erro", title: x.erro }, "falhou")),
      h("td", { class: "mudo" }, x.duracao_ms ? `${(x.duracao_ms / 1000).toFixed(0)} s` : "—"))));
}

async function paginaExecucoes(c) {
  const lista = h("div", { class: "card tabela-rolagem" });
  c.replaceChildren(h("div", { class: "cabeca" }, h("div", {}, h("div", { class: "sobre" }, "Histórico"), h("h1", {}, "Execuções"))), lista);
  const carregar = async () => {
    const dados = await q(sb.from("execucoes").select("*, sistemas(nome)").order("id", { ascending: false }).limit(200));
    lista.replaceChildren(dados.length ? tabelaExecucoes(dados, true) : h("div", { class: "vazio" }, "Nenhuma execução registrada ainda."));
  };
  atualizadores = [carregar];
  await carregar();
}

async function paginaSistema(c, idTexto) {
  const novo = idTexto === "novo";
  const empresas = await q(sb.from("empresas").select("id, nome").order("nome"));
  if (!empresas.length) {
    c.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Cadastre uma empresa primeiro"), h("p", {}, "Todo sistema pertence a uma empresa."), h("a", { href: "#/empresas" }, "Ir para Empresas")));
    return;
  }
  const [sistemaBD, comandosBD, canaisBD] = novo ? [null, [], null] : await Promise.all([
    q(sb.from("sistemas").select("*, empresas(nome)").eq("id", idTexto).maybeSingle()),
    q(sb.from("sistema_comandos").select("*").eq("sistema_id", idTexto)),
    q(sb.from("sistema_canais").select("*").eq("sistema_id", idTexto).maybeSingle()),
  ]);
  if (!novo && !sistemaBD) { c.replaceChildren(h("div", { class: "card" }, "Sistema não encontrado.")); return; }
  const s = sistemaBD || { nome: "", empresa_id: empresas[0].id, ativo: true, empresa_devmaster: "Loja/Gerencial", modulo_devmaster: "Gestão Varejo Atacado" };

  const nome = h("input", { type: "text", id: "sn", value: s.nome, maxlength: 120, required: true });
  const empresa = h("select", { id: "se" }, empresas.map((e) => h("option", { value: e.id, selected: e.id === s.empresa_id }, e.nome)));
  const dmEmpresa = h("input", { type: "text", id: "sde", value: s.empresa_devmaster, maxlength: 80 });
  const dmModulo = h("input", { type: "text", id: "sdm", value: s.modulo_devmaster, maxlength: 80 });
  const ativo = h("input", { type: "checkbox", checked: !!s.ativo });
  const cn = canaisBD || { evo_url: "", evo_instancia: "", evo_key: "", whatsapp_menu: "botoes", telegram_token: "" };
  const evoUrl = h("input", { type: "url", id: "seu", value: cn.evo_url, maxlength: 300, placeholder: "https://evolution.seudominio.com.br" });
  const evoInst = h("input", { type: "text", id: "sei", value: cn.evo_instancia, maxlength: 120 });
  const evoKey = h("input", { type: "password", id: "sek", value: cn.evo_key, maxlength: 300, autocomplete: "off" });
  const zapMenu = h("select", { id: "szm" }, h("option", { value: "botoes", selected: cn.whatsapp_menu !== "texto" }, "Botões / lista"), h("option", { value: "texto", selected: cn.whatsapp_menu === "texto" }, "Texto"));
  const tgToken = h("input", { type: "password", id: "stt", value: cn.telegram_token, maxlength: 80, autocomplete: "off", placeholder: "123456789:AA…" });
  const canais = () => ({ evo_url: evoUrl.value.trim().replace(/\/+$/, ""), evo_instancia: evoInst.value.trim(), evo_key: evoKey.value.trim(), whatsapp_menu: zapMenu.value, telegram_token: tgToken.value.trim() });
  const salvarCanais = (id) => q(sb.from("sistema_canais").upsert({ sistema_id: id, ...canais() }));

  const marcados = new Map(comandosBD.map((x) => [x.comando, x]));
  const blocos = catalogo.map((info) => {
    const atual = marcados.get(info.comando);
    return { info, marca: h("input", { type: "checkbox", checked: novo ? true : !!atual }),
      titulo: h("input", { type: "text", value: atual?.titulo || "", placeholder: info.titulo, maxlength: 40, "aria-label": "Título do botão" }),
      arquivo: h("input", { type: "text", value: atual?.arquivo || "", placeholder: info.arquivo_padrao, maxlength: 80, "aria-label": "Nome do arquivo gerado" }) };
  });
  const comandos = () => blocos.filter((b) => b.marca.checked).map((b) => ({ comando: b.info.comando, titulo: b.titulo.value.trim(), arquivo: b.arquivo.value.trim() }));

  const salvar = () => tentar(async () => {
    if (!nome.value.trim()) throw new Error("Informe o nome do sistema");
    if (novo) {
      const r = await q(sb.rpc("criar_sistema", { p_empresa_id: empresa.value, p_nome: nome.value.trim(), p_empresa_devmaster: dmEmpresa.value.trim(), p_modulo_devmaster: dmModulo.value.trim(), p_comandos: comandos() }));
      await salvarCanais(r.id);
      location.hash = `#/sistema/${r.id}`;
      mostrarChave(r.chave, "Sistema criado");
    } else {
      await q(sb.from("sistemas").update({ empresa_id: empresa.value, nome: nome.value.trim(), ativo: ativo.checked, empresa_devmaster: dmEmpresa.value.trim(), modulo_devmaster: dmModulo.value.trim() }).eq("id", s.id));
      await q(sb.rpc("salvar_comandos", { p_sistema_id: s.id, p_comandos: comandos() }));
      await salvarCanais(s.id);
      aviso("Sistema salvo");
    }
  });

  const partes = [
    h("div", { class: "cabeca" }, h("div", {}, h("div", { class: "sobre" }, novo ? "Novo" : sistemaBD.empresas?.nome), h("h1", {}, novo ? "Novo sistema" : s.nome)),
      h("a", { href: "#/" }, "← Voltar")),
    h("div", { class: "card" }, h("h2", {}, "Dados"),
      h("div", { class: "campos" },
        h("div", {}, h("label", { for: "sn" }, "Nome do sistema"), nome), h("div", {}, h("label", { for: "se" }, "Empresa"), empresa),
        h("div", {}, h("label", { for: "sde" }, "Empresa no login do DevMaster"), dmEmpresa), h("div", {}, h("label", { for: "sdm" }, "Módulo no login do DevMaster"), dmModulo)),
      h("p", { class: "mudo" }, "O robô escolhe esta empresa e este módulo na tela de login do DevMaster, e só depois gera o arquivo."),
      h("label", { class: "marcar" }, ativo, "Sistema ativo (desmarcar bloqueia os comandos na hora)")),
    h("div", { class: "card" }, h("h2", {}, "WhatsApp e Telegram"),
      h("div", { class: "campos" },
        h("div", {}, h("label", { for: "seu" }, "URL da Evolution API"), evoUrl), h("div", {}, h("label", { for: "sei" }, "Instância"), evoInst),
        h("div", {}, h("label", { for: "sek" }, "API key da Evolution"), evoKey), h("div", {}, h("label", { for: "szm" }, "Menu no WhatsApp"), zapMenu),
        h("div", {}, h("label", { for: "stt" }, "Token do bot do Telegram"), tgToken)),
      h("p", { class: "mudo" }, "Vão para o programa junto com a chave: no cliente só é preciso instalar e colar a chave. Deixe em branco o canal que não usa.")),
    h("div", { class: "card" }, h("h2", {}, "Arquivos que este sistema gera"),
      blocos.map((b) => h("div", { class: "linha" }, h("label", { class: "marcar fixo" }, b.marca, h("b", {}, b.info.comando)),
        h("div", {}, h("label", {}, "Texto do botão"), b.titulo), h("div", {}, h("label", {}, "Nome do arquivo (.xlsx)"), b.arquivo))),
      h("p", { class: "mudo" }, "Deixe em branco para usar o padrão. O arquivo é salvo em Downloads e enviado a quem pediu.")),
    h("div", { class: "linha" }, h("button", { class: "btn fixo", onclick: salvar }, novo ? "Criar sistema e gerar chave" : "Salvar alterações")),
  ];

  if (novo) { c.replaceChildren(...partes); atualizadores = []; return; }

  // Áreas que se atualizam ao vivo sem apagar o que você está digitando
  const areaChave = h("div", { class: "card" });
  const areaContatos = h("div", { class: "card" });
  const areaExec = h("div", { class: "card" });
  const carregarVivo = async () => {
    const [sis, contatos, execs] = await Promise.all([
      q(sb.from("sistemas").select("*").eq("id", s.id).maybeSingle()),
      q(sb.from("contatos").select("*").eq("sistema_id", s.id).order("canal").order("nome")),
      q(sb.from("execucoes").select("*").eq("sistema_id", s.id).order("id", { ascending: false }).limit(30)),
    ]);
    if (!sis) { location.hash = "#/"; return; }
    areaChave.replaceChildren(...conteudoChave(sis));
    areaContatos.replaceChildren(...conteudoContatos(sis, contatos));
    areaExec.replaceChildren(h("h2", {}, "Últimas execuções"), execs.length ? h("div", { class: "tabela-rolagem" }, tabelaExecucoes(execs, false)) : h("div", { class: "vazio" }, "Nada executado ainda."));
  };
  const risco = h("div", { class: "card" }, h("h2", {}, "Zona de risco"), h("button", { class: "btn perigo",
    onclick: () => confirmar("Excluir sistema", `Excluir “${s.nome}”? O programa instalado perde o acesso imediatamente.`, "Excluir", () => tentar(async () => { await q(sb.from("sistemas").delete().eq("id", s.id)); aviso("Sistema excluído"); location.hash = "#/"; })) }, "Excluir este sistema"));
  partes.splice(3, 0, areaChave, areaContatos, areaExec);
  partes.push(risco);
  c.replaceChildren(...partes);
  atualizadores = [carregarVivo];
  await carregarVivo();
}

function conteudoChave(s) {
  const baixar = h("button", { class: "btn", onclick: () => baixarInstalador(null, baixar) }, "Baixar instalador (.exe)");
  return [h("h2", {}, "Instala\u00e7\u00e3o e acesso"),
    baixar,
    h("p", { class: "mudo" }, "Instale no Windows e informe a chave deste sistema. Para baixar um instalador j\u00e1 configurado, gere uma nova chave e use o download exibido na confirma\u00e7\u00e3o."),
    h("p", {}, "Final ", h("span", { class: "mono" }, `••••${s.chave_final}`), " · criada ", quando(s.chave_criada_em)),
    s.computador ? h("p", { class: "mudo" }, `Computador: ${s.computador} · versão ${s.versao || "?"} · ${estaOnline(s) ? "online" : "offline"} (${quando(s.ultimo_contato)})`) : h("p", { class: "mudo" }, "O programa ainda não se conectou."),
    h("button", { class: "btn sec", onclick: () => confirmar("Gerar nova chave", "A chave atual para de funcionar na hora. Você precisará colar a nova no programa deste cliente.", "Gerar nova chave",
      () => tentar(async () => { const chave = await q(sb.rpc("gerar_nova_chave", { p_sistema_id: s.id })); mostrarChave(chave, "Nova chave"); })) }, "Gerar nova chave")];
}

function conteudoContatos(s, contatos) {
  const canal = h("select", { id: "cc", "aria-label": "Canal" }, h("option", { value: "whatsapp" }, "WhatsApp (número)"), h("option", { value: "telegram" }, "Telegram (ID)"));
  const ident = h("input", { type: "text", id: "ci", placeholder: "5511999998888", inputmode: "numeric", maxlength: 24 });
  const nomeC = h("input", { type: "text", id: "cn", placeholder: "Quem é (opcional)", maxlength: 80 });
  canal.addEventListener("change", () => (ident.placeholder = canal.value === "whatsapp" ? "5511999998888" : "ID numérico do Telegram"));
  const grupo = (cn, titulo) => {
    const lista = contatos.filter((x) => x.canal === cn);
    return h("div", {}, h("h3", { class: "mudo" }, titulo), lista.length ? tabela(["Nome", "Identificador", "Situação", ""], lista.map((x) => h("tr", {},
      h("td", {}, x.nome || "—"), h("td", { class: "mono" }, x.identificador),
      h("td", {}, h("span", { class: "selo " + (x.ativo ? "ok" : "offline") }, x.ativo ? "permitido" : "pausado")),
      h("td", {}, h("div", { class: "linha" },
        h("button", { class: "btn sec mini fixo", onclick: () => tentar(async () => { await q(sb.from("contatos").update({ ativo: !x.ativo }).eq("id", x.id)); }) }, x.ativo ? "Pausar" : "Permitir"),
        h("button", { class: "btn perigo mini fixo", onclick: () => confirmar("Remover", `Remover ${x.nome || x.identificador}?`, "Remover", () => tentar(async () => { await q(sb.from("contatos").delete().eq("id", x.id)); })) }, "Remover"))))))
      : h("div", { class: "vazio" }, "Ninguém cadastrado."));
  };
  return [h("h2", {}, "Quem pode pedir (números e IDs permitidos)"),
    h("div", { class: "tabela-rolagem" }, grupo("whatsapp", "WhatsApp"), grupo("telegram", "Telegram")),
    h("div", { class: "linha contato-form" }, h("div", {}, h("label", { for: "cc" }, "Canal"), canal), h("div", {}, h("label", { for: "ci" }, "Número / ID"), ident), h("div", {}, h("label", { for: "cn" }, "Nome"), nomeC),
      h("button", { class: "btn fixo", onclick: () => tentar(async () => {
        const digitos = ident.value.replace(/\D/g, ""); // aceita +55 (11) 99999-8888
        await q(sb.from("contatos").insert({ sistema_id: s.id, canal: canal.value, identificador: digitos, nome: nomeC.value.trim() }));
        ident.value = ""; nomeC.value = ""; aviso("Contato adicionado");
      }) }, "Adicionar")),
    h("p", { class: "mudo" }, "As mudanças chegam ao programa em até 5 minutos. Quem não está na lista não recebe resposta.")];
}

// ---------------- Rotas ----------------
async function rota() {
  const c = document.getElementById("conteudo");
  if (!c) return;
  marcarMenu();
  atualizadores = [];
  const hash = location.hash || "#/";
  try {
    let m;
    if (hash === "#/" || hash === "") await paginaSistemas(c);
    else if (hash === "#/empresas") await paginaEmpresas(c);
    else if (hash === "#/execucoes") await paginaExecucoes(c);
    else if ((m = /^#\/sistema\/(novo|[0-9a-f-]{36})$/.exec(hash))) await paginaSistema(c, m[1]);
    else c.replaceChildren(h("div", { class: "card" }, "Página não encontrada."));
  } catch (e) { c.replaceChildren(h("div", { class: "card" }, h("p", {}, e.message))); }
}

async function iniciar() {
  const { data } = await sb.auth.getSession();
  const usuario = data.session?.user;
  if (!usuario) return mostrarLogin();
  try {
    const admin = await q(sb.from("administradores").select("usuario_id").maybeSingle());
    if (!admin) return semAcesso(usuario);
    catalogo = await q(sb.from("catalogo_comandos").select("*").order("comando"));
  } catch (e) { return mostrarLogin(e.message); }
  estrutura(usuario);
  escutarMudancas();
  rota();
}

if (!window.CONFIG?.SUPABASE_URL || !window.CONFIG?.SUPABASE_PUBLISHABLE_KEY) {
  semConfiguracao();
} else {
  sb = window.supabase.createClient(window.CONFIG.SUPABASE_URL, window.CONFIG.SUPABASE_PUBLISHABLE_KEY, {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
  });
  window.addEventListener("hashchange", rota);
  iniciar();
}

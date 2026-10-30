// Painel de gestão do Bot DevMaster. Sem framework: o DOM é montado com h() (textContent), nunca com innerHTML.
"use strict";

const raiz = document.getElementById("raiz");
let catalogo = {};

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
  return el;
}

async function api(metodo, caminho, corpo) {
  const r = await fetch(`/api${caminho}`, {
    method: metodo,
    headers: corpo ? { "Content-Type": "application/json" } : {},
    body: corpo ? JSON.stringify(corpo) : undefined,
    credentials: "same-origin",
  });
  const dados = await r.json().catch(() => ({}));
  if (r.status === 401 && caminho !== "/login") { mostrarLogin(); throw new Error("Sessão expirada"); }
  if (!r.ok) throw new Error(dados.erro || `Erro ${r.status}`);
  return dados;
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
  const d = new Date(iso.replace(" ", "T") + "Z");
  const seg = (Date.now() - d.getTime()) / 1000;
  if (seg < 60) return "agora há pouco";
  if (seg < 3600) return `há ${Math.floor(seg / 60)} min`;
  if (seg < 86400) return `há ${Math.floor(seg / 3600)} h`;
  return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function janela(titulo, corpo, acoes) {
  const fundo = h("div", { class: "fundo", role: "dialog", "aria-modal": "true", "aria-label": titulo },
    h("div", { class: "janela" }, h("h2", {}, titulo), corpo, h("div", { class: "acoes" }, acoes(() => fundo.remove()))));
  fundo.addEventListener("click", (e) => { if (e.target === fundo) fundo.remove(); });
  document.body.append(fundo);
  return fundo;
}

function confirmar(titulo, mensagem, rotulo, aoConfirmar) {
  janela(titulo, h("p", {}, mensagem), (fechar) => [
    h("button", { class: "btn sec", onclick: fechar }, "Cancelar"),
    h("button", { class: "btn perigo", onclick: () => { fechar(); aoConfirmar(); } }, rotulo),
  ]);
}

function mostrarChave(chave, titulo = "Chave do sistema") {
  const code = h("code", {}, chave);
  janela(titulo,
    h("div", {},
      h("p", {}, "Copie e guarde agora: por segurança, esta chave não será mostrada de novo. Cole no campo “Chave deste sistema” do programa."),
      h("div", { class: "chave" }, code)),
    (fechar) => [
      h("button", { class: "btn sec", onclick: async () => { await navigator.clipboard.writeText(chave).catch(() => {}); aviso("Chave copiada"); } }, "Copiar"),
      h("button", { class: "btn", onclick: fechar }, "Já guardei"),
    ]);
}

// ---------------- Login e estrutura ----------------
function mostrarLogin() {
  raiz.replaceChildren(
    h("div", { class: "login" },
      h("form", {
        onsubmit: async (e) => {
          e.preventDefault();
          const msg = e.target.querySelector(".msg");
          msg.textContent = "";
          try {
            await api("POST", "/login", { senha: e.target.senha.value });
            iniciar();
          } catch (err) { msg.textContent = err.message; }
        },
      },
        h("img", { src: "/troven-horizontal-negativo.svg", alt: "Troven" }),
        h("h1", {}, "Gestão do Bot DevMaster"),
        h("p", {}, "Entre para gerenciar empresas, sistemas e chaves."),
        h("label", { for: "senha" }, "Senha"),
        h("input", { id: "senha", name: "senha", type: "password", autocomplete: "current-password", required: true, autofocus: true }),
        h("button", { class: "btn", type: "submit" }, "Entrar"),
        h("div", { class: "msg", role: "alert" }))));
}

function estrutura() {
  const link = (href, texto) => h("a", { href, "data-rota": href }, texto);
  raiz.replaceChildren(
    h("header", { class: "topo" },
      h("img", { src: "/troven-horizontal-negativo.svg", alt: "Troven" }),
      h("nav", {}, link("#/", "Sistemas"), link("#/empresas", "Empresas"), link("#/execucoes", "Execuções")),
      h("button", { onclick: async () => { await api("POST", "/logout").catch(() => {}); mostrarLogin(); } }, "Sair")),
    h("main", { id: "conteudo" }));
}

function marcarMenu() {
  const rota = location.hash || "#/";
  for (const a of document.querySelectorAll(".topo nav a")) {
    const alvo = a.dataset.rota;
    a.classList.toggle("ativo", alvo === "#/" ? rota === "#/" || rota.startsWith("#/sistema") : rota.startsWith(alvo));
  }
}

// ---------------- Páginas ----------------
async function paginaSistemas(c) {
  const [resumo, sistemas] = await Promise.all([api("GET", "/resumo"), api("GET", "/sistemas")]);
  c.replaceChildren(
    h("div", { class: "cabeca" }, h("div", {}, h("div", { class: "sobre" }, "Visão geral"), h("h1", {}, "Sistemas")),
      h("button", { class: "btn", onclick: () => (location.hash = "#/sistema/novo") }, "+ Novo sistema")),
    h("div", { class: "grade" },
      numero(`${resumo.online}/${resumo.sistemas}`, "sistemas online"),
      numero(resumo.empresas, "empresas"),
      numero(resumo.execucoes_24h, "execuções em 24 h"),
      numero(resumo.falhas_24h, "falhas em 24 h", resumo.falhas_24h > 0)),
    h("div", { class: "card tabela-rolagem" }, sistemas.length ? tabela(
      ["Sistema", "Empresa", "Situação", "Versão", "Último contato"],
      sistemas.map((s) => h("tr", { class: "clicavel", tabindex: "0", onclick: () => (location.hash = `#/sistema/${s.id}`),
        onkeydown: (e) => { if (e.key === "Enter") location.hash = `#/sistema/${s.id}`; } },
        h("td", {}, h("b", {}, s.nome)), h("td", {}, s.empresa_nome),
        h("td", {}, !s.ativo ? h("span", { class: "selo erro" }, "desativado") : s.online ? h("span", { class: "selo online" }, "online") : h("span", { class: "selo offline" }, "offline")),
        h("td", { class: "mono" }, s.versao || "—"), h("td", { class: "mudo" }, quando(s.ultimo_contato))))) : h("div", { class: "vazio" }, "Nenhum sistema ainda. Cadastre uma empresa e crie o primeiro sistema.")));
}

const numero = (valor, rotulo, alerta = false) => h("div", { class: "numero" + (alerta ? " alerta" : "") }, h("b", {}, valor), h("span", {}, rotulo));
const tabela = (cabecas, linhas) => h("table", {}, h("thead", {}, h("tr", {}, cabecas.map((t) => h("th", {}, t)))), h("tbody", {}, linhas));

async function paginaEmpresas(c) {
  const empresas = await api("GET", "/empresas");
  const editar = (e = {}) => {
    const nome = h("input", { type: "text", id: "en", value: e.nome || "", maxlength: 120 });
    const doc = h("input", { type: "text", id: "ed", value: e.documento || "", maxlength: 30 });
    const obs = h("input", { type: "text", id: "eo", value: e.observacao || "", maxlength: 500 });
    const ativo = h("input", { type: "checkbox", checked: e.id ? !!e.ativo : true });
    janela(e.id ? "Editar empresa" : "Nova empresa",
      h("div", { class: "campos" }, h("div", {}, h("label", { for: "en" }, "Nome"), nome), h("div", {}, h("label", { for: "ed" }, "CNPJ / documento"), doc),
        h("div", {}, h("label", { for: "eo" }, "Observação"), obs), h("label", { class: "marcar" }, ativo, "Empresa ativa")),
      (fechar) => [h("button", { class: "btn sec", onclick: fechar }, "Cancelar"),
        h("button", { class: "btn", onclick: () => tentar(async () => {
          const corpo = { nome: nome.value, documento: doc.value, observacao: obs.value, ativo: ativo.checked };
          if (e.id) await api("PUT", `/empresas/${e.id}`, corpo); else await api("POST", "/empresas", corpo);
          fechar(); aviso("Empresa salva"); rota();
        }) }, "Salvar")]);
  };
  c.replaceChildren(
    h("div", { class: "cabeca" }, h("div", {}, h("div", { class: "sobre" }, "Clientes"), h("h1", {}, "Empresas")),
      h("button", { class: "btn", onclick: () => editar() }, "+ Nova empresa")),
    h("div", { class: "card tabela-rolagem" }, empresas.length ? tabela(["Empresa", "Documento", "Sistemas", "Situação", ""],
      empresas.map((e) => h("tr", {}, h("td", {}, h("b", {}, e.nome), e.observacao ? h("div", { class: "mudo" }, e.observacao) : null),
        h("td", { class: "mono" }, e.documento || "—"), h("td", {}, e.sistemas),
        h("td", {}, h("span", { class: "selo " + (e.ativo ? "ok" : "erro") }, e.ativo ? "ativa" : "inativa")),
        h("td", {}, h("div", { class: "linha" },
          h("button", { class: "btn sec mini fixo", onclick: () => editar(e) }, "Editar"),
          h("button", { class: "btn perigo mini fixo", onclick: () => confirmar("Excluir empresa", `Excluir “${e.nome}”?`, "Excluir", () => tentar(async () => { await api("DELETE", `/empresas/${e.id}`); aviso("Empresa excluída"); rota(); })) }, "Excluir")))))) : h("div", { class: "vazio" }, "Nenhuma empresa cadastrada.")));
}

async function paginaExecucoes(c) {
  const lista = await api("GET", "/execucoes?limite=200");
  c.replaceChildren(
    h("div", { class: "cabeca" }, h("div", {}, h("div", { class: "sobre" }, "Histórico"), h("h1", {}, "Execuções"))),
    h("div", { class: "card tabela-rolagem" }, lista.length ? tabelaExecucoes(lista, true) : h("div", { class: "vazio" }, "Nenhuma execução registrada ainda.")));
}

function tabelaExecucoes(lista, comSistema) {
  return tabela([comSistema ? "Sistema" : null, "Quando", "Comando", "Canal", "Solicitante", "Resultado", "Duração"].filter(Boolean),
    lista.map((x) => h("tr", {}, comSistema ? h("td", {}, x.sistema_nome) : null, h("td", { class: "mudo" }, quando(x.criado_em)), h("td", {}, x.comando),
      h("td", {}, x.canal || "—"), h("td", { class: "mono" }, x.solicitante || "—"),
      h("td", {}, x.ok ? h("span", { class: "selo ok" }, "ok") : h("span", { class: "selo erro", title: x.erro }, "falhou")),
      h("td", { class: "mudo" }, x.duracao_ms ? `${(x.duracao_ms / 1000).toFixed(0)} s` : "—"))));
}

async function paginaSistema(c, idTexto) {
  const novo = idTexto === "novo";
  const empresas = await api("GET", "/empresas");
  const det = novo ? null : await api("GET", `/sistemas/${idTexto}`);
  const s = det ? det.sistema : { nome: "", empresa_id: empresas[0]?.id, ativo: 1, devmaster_empresa: "Loja/Gerencial", devmaster_modulo: "Gestão Varejo Atacado" };
  if (!empresas.length) {
    c.replaceChildren(h("div", { class: "card" }, h("h2", {}, "Cadastre uma empresa primeiro"), h("p", {}, "Todo sistema pertence a uma empresa."), h("a", { href: "#/empresas" }, "Ir para Empresas")));
    return;
  }

  const nome = h("input", { type: "text", id: "sn", value: s.nome, maxlength: 120, required: true });
  const empresa = h("select", { id: "se" }, empresas.map((e) => h("option", { value: e.id, selected: e.id === s.empresa_id }, e.nome)));
  const dmEmpresa = h("input", { type: "text", id: "sde", value: s.devmaster_empresa, maxlength: 80 });
  const dmModulo = h("input", { type: "text", id: "sdm", value: s.devmaster_modulo, maxlength: 80 });
  const ativo = h("input", { type: "checkbox", checked: !!s.ativo });

  // comandos: um bloco por item do catálogo
  const ativosCmd = new Map((det?.comandos || []).map((x) => [x.comando, x]));
  const blocos = Object.entries(catalogo).map(([nomeCmd, info]) => {
    const atual = ativosCmd.get(nomeCmd);
    return { nomeCmd, marca: h("input", { type: "checkbox", checked: novo ? true : !!atual }),
      titulo: h("input", { type: "text", value: atual?.titulo || "", placeholder: info.titulo, maxlength: 40, "aria-label": "Título do botão" }),
      arquivo: h("input", { type: "text", value: atual?.arquivo || "", placeholder: info.arquivo, maxlength: 80, "aria-label": "Nome do arquivo gerado" }), info };
  });
  const comandos = () => blocos.filter((b) => b.marca.checked).map((b) => ({ comando: b.nomeCmd, titulo: b.titulo.value, arquivo: b.arquivo.value }));

  const salvar = () => tentar(async () => {
    const corpo = { nome: nome.value, empresa_id: Number(empresa.value), ativo: ativo.checked, devmaster_empresa: dmEmpresa.value, devmaster_modulo: dmModulo.value, comandos: comandos() };
    if (novo) {
      const r = await api("POST", "/sistemas", corpo);
      location.hash = `#/sistema/${r.id}`;
      mostrarChave(r.chave, "Sistema criado");
    } else { await api("PUT", `/sistemas/${s.id}`, corpo); aviso("Sistema salvo"); rota(); }
  });

  const partes = [
    h("div", { class: "cabeca" }, h("div", {}, h("div", { class: "sobre" }, novo ? "Novo" : s.empresa_nome), h("h1", {}, novo ? "Novo sistema" : s.nome)),
      h("a", { href: "#/" }, "← Voltar")),
    h("div", { class: "card" }, h("h2", {}, "Dados"),
      h("div", { class: "campos" },
        h("div", {}, h("label", { for: "sn" }, "Nome do sistema"), nome),
        h("div", {}, h("label", { for: "se" }, "Empresa"), empresa),
        h("div", {}, h("label", { for: "sde" }, "Empresa no login do DevMaster"), dmEmpresa),
        h("div", {}, h("label", { for: "sdm" }, "Módulo no login do DevMaster"), dmModulo)),
      h("p", { class: "mudo" }, "O robô escolhe esta empresa e este módulo na tela de login do DevMaster, e só depois gera o arquivo."),
      h("label", { class: "marcar" }, ativo, "Sistema ativo (desmarcar bloqueia os comandos na hora)")),
    h("div", { class: "card" }, h("h2", {}, "Arquivos que este sistema gera"),
      blocos.map((b) => h("div", { class: "linha", style: null },
        h("label", { class: "marcar fixo" }, b.marca, h("b", {}, b.nomeCmd)),
        h("div", {}, h("label", {}, "Texto do botão"), b.titulo),
        h("div", {}, h("label", {}, "Nome do arquivo (.xlsx)"), b.arquivo))),
      h("p", { class: "mudo" }, "Deixe em branco para usar o padrão. O arquivo é salvo em Downloads e enviado a quem pediu.")),
    h("div", { class: "linha" }, h("button", { class: "btn fixo", onclick: salvar }, novo ? "Criar sistema e gerar chave" : "Salvar alterações")),
  ];
  if (!novo) partes.splice(3, 0, cartaoChave(s), cartaoContatos(s, det.contatos), h("div", { class: "card" }, h("h2", {}, "Últimas execuções"),
    det.execucoes.length ? h("div", { class: "tabela-rolagem" }, tabelaExecucoes(det.execucoes, false)) : h("div", { class: "vazio" }, "Nada executado ainda.")),
    h("div", { class: "card" }, h("h2", {}, "Zona de risco"), h("button", { class: "btn perigo",
      onclick: () => confirmar("Excluir sistema", `Excluir “${s.nome}”? O programa instalado perde o acesso imediatamente.`, "Excluir", () => tentar(async () => { await api("DELETE", `/sistemas/${s.id}`); aviso("Sistema excluído"); location.hash = "#/"; })) }, "Excluir este sistema")));
  c.replaceChildren(...partes);
}

function cartaoChave(s) {
  return h("div", { class: "card" }, h("h2", {}, "Chave de acesso"),
    h("p", {}, "Final ", h("span", { class: "mono" }, `••••${s.chave_final}`), " · criada ", quando(s.chave_criada_em)),
    s.host ? h("p", { class: "mudo" }, `Computador: ${s.host} · versão ${s.versao || "?"} · ${s.online ? "online" : "offline"} (${quando(s.ultimo_contato)})`) : h("p", { class: "mudo" }, "O programa ainda não se conectou."),
    h("button", { class: "btn sec", onclick: () => confirmar("Gerar nova chave", "A chave atual para de funcionar na hora. Você precisará colar a nova no programa deste cliente.", "Gerar nova chave",
      () => tentar(async () => { const r = await api("POST", `/sistemas/${s.id}/chave`); mostrarChave(r.chave, "Nova chave"); rota(); })) }, "Gerar nova chave"));
}

function cartaoContatos(s, contatos) {
  const canal = h("select", { id: "cc", "aria-label": "Canal" }, h("option", { value: "whatsapp" }, "WhatsApp (número)"), h("option", { value: "telegram" }, "Telegram (ID)"));
  const ident = h("input", { type: "text", id: "ci", placeholder: "5511999998888", inputmode: "numeric", maxlength: 20 });
  const nomeC = h("input", { type: "text", id: "cn", placeholder: "Quem é (opcional)", maxlength: 80 });
  canal.addEventListener("change", () => (ident.placeholder = canal.value === "whatsapp" ? "5511999998888" : "ID numérico do Telegram"));
  const grupo = (cn, titulo) => {
    const lista = contatos.filter((x) => x.canal === cn);
    return h("div", {}, h("h3", { class: "mudo" }, titulo), lista.length ? tabela(["Nome", "Identificador", "Situação", ""], lista.map((x) => h("tr", {},
      h("td", {}, x.nome || "—"), h("td", { class: "mono" }, x.identificador),
      h("td", {}, h("span", { class: "selo " + (x.ativo ? "ok" : "offline") }, x.ativo ? "permitido" : "pausado")),
      h("td", {}, h("div", { class: "linha" },
        h("button", { class: "btn sec mini fixo", onclick: () => tentar(async () => { await api("PUT", `/contatos/${x.id}`, { identificador: x.identificador, nome: x.nome, ativo: !x.ativo }); rota(); }) }, x.ativo ? "Pausar" : "Permitir"),
        h("button", { class: "btn perigo mini fixo", onclick: () => confirmar("Remover", `Remover ${x.nome || x.identificador}?`, "Remover", () => tentar(async () => { await api("DELETE", `/contatos/${x.id}`); rota(); })) }, "Remover"))))))
      : h("div", { class: "vazio" }, "Ninguém cadastrado."));
  };
  return h("div", { class: "card" }, h("h2", {}, "Quem pode pedir (números e IDs permitidos)"),
    h("div", { class: "tabela-rolagem" }, grupo("whatsapp", "WhatsApp"), grupo("telegram", "Telegram")),
    h("div", { class: "linha", style: null }, h("div", {}, h("label", { for: "cc" }, "Canal"), canal), h("div", {}, h("label", { for: "ci" }, "Número / ID"), ident), h("div", {}, h("label", { for: "cn" }, "Nome"), nomeC),
      h("button", { class: "btn fixo", onclick: () => tentar(async () => { await api("POST", `/sistemas/${s.id}/contatos`, { canal: canal.value, identificador: ident.value, nome: nomeC.value }); aviso("Contato adicionado"); rota(); }) }, "Adicionar")),
    h("p", { class: "mudo" }, "As mudanças chegam ao programa em até 5 minutos. Quem não está na lista não recebe resposta."));
}

// ---------------- Rotas ----------------
async function rota() {
  const c = document.getElementById("conteudo");
  if (!c) return;
  marcarMenu();
  const hash = location.hash || "#/";
  try {
    let m;
    if (hash === "#/" || hash === "") await paginaSistemas(c);
    else if (hash === "#/empresas") await paginaEmpresas(c);
    else if (hash === "#/execucoes") await paginaExecucoes(c);
    else if ((m = /^#\/sistema\/(novo|\d+)$/.exec(hash))) await paginaSistema(c, m[1]);
    else c.replaceChildren(h("div", { class: "card" }, "Página não encontrada."));
  } catch (e) { if (e.message !== "Sessão expirada") c.replaceChildren(h("div", { class: "card" }, h("p", {}, e.message))); }
}

async function iniciar() {
  try {
    const sessao = await api("GET", "/sessao");
    if (!sessao.autenticado) return mostrarLogin();
    catalogo = await api("GET", "/catalogo");
    estrutura();
    rota();
  } catch { mostrarLogin(); }
}

window.addEventListener("hashchange", rota);
iniciar();

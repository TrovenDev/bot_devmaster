// Teste de integração: rode `npm run dev` (com .dev.vars) e depois `npm test`.
import assert from "node:assert/strict";
import { before, describe, it } from "node:test";

const BASE = process.env.CONSOLE_URL || "http://127.0.0.1:8799";
const SENHA = process.env.ADMIN_PASSWORD || "senha-de-teste-local";
const IP = `10.${Math.floor(Math.random() * 250)}.${Math.floor(Math.random() * 250)}.1`; // isola o limite de tentativas

let cookie = "";
async function chamar(metodo, caminho, corpo, extra = {}) {
  const r = await fetch(BASE + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", "CF-Connecting-IP": IP, ...(cookie ? { Cookie: cookie } : {}), ...extra },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  return { status: r.status, dados: await r.json().catch(() => ({})), r };
}
const cliente = (chave, metodo, caminho, corpo) =>
  chamar(metodo, caminho, corpo, { Authorization: `Bearer ${chave}`, Cookie: "" });

describe("painel de gestão", () => {
  let empresaId, sistemaId, chave;

  it("bloqueia a API do painel sem login", async () => {
    assert.equal((await chamar("GET", "/api/sistemas")).status, 401);
    assert.equal((await chamar("GET", "/api/sessao")).dados.autenticado, false);
  });

  it("recusa senha errada e aceita a certa", async () => {
    assert.equal((await chamar("POST", "/api/login", { senha: "errada" })).status, 401);
    const ok = await chamar("POST", "/api/login", { senha: SENHA });
    assert.equal(ok.status, 200);
    cookie = ok.r.headers.get("set-cookie").split(";")[0];
    assert.match(ok.r.headers.get("set-cookie"), /HttpOnly/);
    assert.match(ok.r.headers.get("set-cookie"), /SameSite=Strict/);
    assert.equal((await chamar("GET", "/api/sessao")).dados.autenticado, true);
  });

  it("recusa cookie adulterado", async () => {
    const guardado = cookie;
    cookie = cookie.replace(/.$/, (c) => (c === "A" ? "B" : "A"));
    assert.equal((await chamar("GET", "/api/sistemas")).status, 401);
    cookie = guardado;
  });

  it("recusa mudanças vindas de outra origem (CSRF)", async () => {
    const r = await chamar("POST", "/api/empresas", { nome: "X" }, { Origin: "https://evil.example" });
    assert.equal(r.status, 403);
  });

  it("cria empresa e sistema com chave mostrada uma vez", async () => {
    assert.equal((await chamar("POST", "/api/empresas", { nome: "" })).status, 400);
    const e = await chamar("POST", "/api/empresas", { nome: "Loja Teste <b>", documento: "00.000.000/0001-00" });
    assert.equal(e.status, 201);
    empresaId = e.dados.id;
    const s = await chamar("POST", "/api/sistemas", { nome: "PC do caixa", empresa_id: empresaId, devmaster_empresa: "Loja Centro" });
    assert.equal(s.status, 201);
    sistemaId = s.dados.id;
    chave = s.dados.chave;
    assert.match(chave, /^dmb_[A-Za-z0-9_-]{40,}$/);
    const det = (await chamar("GET", `/api/sistemas/${sistemaId}`)).dados;
    assert.equal(JSON.stringify(det).includes(chave), false, "a chave não pode voltar na consulta");
    assert.equal(det.sistema.chave_final, chave.slice(-4));
    assert.deepEqual(det.comandos.map((c) => c.comando), ["estoque"]);
  });

  it("gerencia números de WhatsApp e IDs do Telegram", async () => {
    const base = `/api/sistemas/${sistemaId}/contatos`;
    assert.equal((await chamar("POST", base, { canal: "whatsapp", identificador: "abc" })).status, 400);
    assert.equal((await chamar("POST", base, { canal: "telegram", identificador: "12x" })).status, 400);
    assert.equal((await chamar("POST", base, { canal: "sms", identificador: "123456" })).status, 400);
    const w = await chamar("POST", base, { canal: "whatsapp", identificador: "+55 (11) 99999-8888", nome: "Maria" });
    assert.equal(w.status, 201);
    assert.equal((await chamar("POST", base, { canal: "whatsapp", identificador: "5511999998888" })).status, 409);
    const t = await chamar("POST", base, { canal: "telegram", identificador: "123456789", nome: "Maria" });
    assert.equal(t.status, 201);
    const outro = await chamar("POST", base, { canal: "whatsapp", identificador: "5511888887777", nome: "Pausado" });
    await chamar("PUT", `/api/contatos/${outro.dados.id}`, { identificador: "5511888887777", nome: "Pausado", ativo: false });
  });

  it("entrega a configuração ao programa (só contatos ativos)", async () => {
    const c = await cliente(chave, "GET", "/api/v1/config");
    assert.equal(c.status, 200);
    assert.equal(c.dados.sistema.ativo, true);
    assert.equal(c.dados.empresa.nome, "Loja Teste <b>");
    assert.deepEqual(c.dados.devmaster, { empresa: "Loja Centro", modulo: "Gestão Varejo Atacado" });
    assert.deepEqual(c.dados.whatsapp.numeros, ["5511999998888"]);
    assert.deepEqual(c.dados.telegram.ids, ["123456789"]);
    assert.equal(c.dados.comandos[0].nome, "estoque");
    assert.equal(c.dados.comandos[0].arquivo, "Estoque Geral.xlsx");
  });

  it("aplica nome de arquivo e título por sistema, sem pastas", async () => {
    const det = (await chamar("GET", `/api/sistemas/${sistemaId}`)).dados.sistema;
    const r = await chamar("PUT", `/api/sistemas/${sistemaId}`, {
      nome: det.nome, empresa_id: empresaId, ativo: true, devmaster_empresa: "Loja Centro", devmaster_modulo: "Gestão Varejo Atacado",
      comandos: [{ comando: "estoque", titulo: "Estoque Centro", arquivo: "..\\..\\Windows\\Estoque Centro" }],
    });
    assert.equal(r.status, 200);
    const c = (await cliente(chave, "GET", "/api/v1/config")).dados;
    assert.equal(c.comandos[0].titulo, "Estoque Centro");
    assert.equal(c.comandos[0].arquivo, "Estoque Centro.xlsx");
    assert.equal((await chamar("PUT", `/api/sistemas/${sistemaId}`, { nome: "x", empresa_id: empresaId, ativo: true, devmaster_empresa: "a", devmaster_modulo: "b", comandos: [{ comando: "apagar_tudo" }] })).status, 400);
  });

  it("recebe heartbeat e execuções do programa", async () => {
    assert.equal((await cliente(chave, "POST", "/api/v1/heartbeat", { versao: "1.0.0", host: "PC-CAIXA", estado: { whatsapp: true } })).status, 200);
    assert.equal((await cliente(chave, "POST", "/api/v1/execucoes", { comando: "estoque", canal: "whatsapp", solicitante: "…8888", ok: false, erro: "falha de teste", duracao_ms: 4200 })).status, 201);
    const s = (await chamar("GET", "/api/sistemas")).dados.find((x) => x.id === sistemaId);
    assert.equal(s.online, 1);
    assert.equal(s.versao, "1.0.0");
    const ex = (await chamar("GET", `/api/execucoes?sistema=${sistemaId}`)).dados;
    assert.equal(ex[0].ok, 0);
    assert.equal((await chamar("GET", "/api/resumo")).dados.falhas_24h >= 1, true);
  });

  it("rejeita chave inválida, ausente ou de outro formato", async () => {
    assert.equal((await cliente("dmb_" + "x".repeat(43), "GET", "/api/v1/config")).status, 401);
    assert.equal((await cliente("qualquer", "GET", "/api/v1/config")).status, 401);
    assert.equal((await chamar("GET", "/api/v1/config")).status, 401);
    assert.equal((await cliente(chave, "GET", "/api/v1/config' OR 1=1")).status, 404);
  });

  it("desativar o sistema esvazia a configuração na hora", async () => {
    const det = (await chamar("GET", `/api/sistemas/${sistemaId}`)).dados.sistema;
    await chamar("PUT", `/api/sistemas/${sistemaId}`, { nome: det.nome, empresa_id: empresaId, ativo: false, devmaster_empresa: "Loja Centro", devmaster_modulo: "Gestão Varejo Atacado" });
    const c = (await cliente(chave, "GET", "/api/v1/config")).dados;
    assert.equal(c.sistema.ativo, false);
    assert.deepEqual([c.comandos, c.whatsapp.numeros, c.telegram.ids], [[], [], []]);
    await chamar("PUT", `/api/sistemas/${sistemaId}`, { nome: det.nome, empresa_id: empresaId, ativo: true, devmaster_empresa: "Loja Centro", devmaster_modulo: "Gestão Varejo Atacado" });
  });

  it("gerar nova chave invalida a antiga", async () => {
    const nova = (await chamar("POST", `/api/sistemas/${sistemaId}/chave`)).dados.chave;
    assert.notEqual(nova, chave);
    assert.equal((await cliente(chave, "GET", "/api/v1/config")).status, 401);
    assert.equal((await cliente(nova, "GET", "/api/v1/config")).status, 200);
    chave = nova;
  });

  it("não exclui empresa com sistemas; excluir o sistema revoga a chave", async () => {
    assert.equal((await chamar("DELETE", `/api/empresas/${empresaId}`)).status, 409);
    assert.equal((await chamar("DELETE", `/api/sistemas/${sistemaId}`)).status, 200);
    assert.equal((await cliente(chave, "GET", "/api/v1/config")).status, 401);
    assert.equal((await chamar("DELETE", `/api/empresas/${empresaId}`)).status, 200);
  });

  it("limita tentativas de login", async () => {
    cookie = "";
    const ip = `192.0.2.${Math.floor(Math.random() * 250)}`;
    let ultimo = 0;
    for (let i = 0; i < 7; i++) {
      ultimo = (await chamar("POST", "/api/login", { senha: "x" }, { "CF-Connecting-IP": ip })).status;
    }
    assert.equal(ultimo, 429);
  });
});

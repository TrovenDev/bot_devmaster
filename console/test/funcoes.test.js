// Testes da API do programa (Pages Function) com o Supabase simulado: node --test test/
import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";
import { onRequest } from "../functions/api/v1/[[rota]].js";
import { onRequestGet as configJs } from "../functions/config.js.js";

const CHAVE = "dmb_" + "a1".repeat(32);
const env = { SUPABASE_URL: "https://projeto.supabase.co", SUPABASE_PUBLISHABLE_KEY: "sb_publishable_teste" };
let chamadas = [];
let resposta = { ok: true, status: 200, json: async () => null };

beforeEach(() => {
  chamadas = [];
  resposta = { ok: true, status: 200, json: async () => null };
  globalThis.fetch = async (url, opcoes) => {
    chamadas.push({ url, corpo: JSON.parse(opcoes.body), headers: opcoes.headers });
    return resposta;
  };
});

const pedir = (metodo, rota, { chave = CHAVE, corpo, e = env } = {}) =>
  onRequest({
    request: new Request(`https://painel.exemplo/api/v1/${rota}`, {
      method: metodo,
      headers: { ...(chave ? { Authorization: `Bearer ${chave}` } : {}), "Content-Type": "application/json" },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    }),
    env: e,
    params: { rota: rota.split("/") },
  });

describe("API do programa instalado", () => {
  it("entrega a configuração quando a chave existe", async () => {
    resposta = { ok: true, status: 200, json: async () => ({ sistema: { id: "1", ativo: true }, comandos: [] }) };
    const r = await pedir("GET", "config");
    assert.equal(r.status, 200);
    assert.equal((await r.json()).sistema.ativo, true);
    assert.equal(chamadas[0].url, "https://projeto.supabase.co/rest/v1/rpc/bot_configuracao");
    assert.deepEqual(chamadas[0].corpo, { p_chave: CHAVE });
    assert.equal(chamadas[0].headers.apikey, "sb_publishable_teste");
  });

  it("responde 401 quando o banco devolve null (chave revogada)", async () => {
    assert.equal((await pedir("GET", "config")).status, 401);
  });

  it("rejeita chave ausente ou em formato errado sem consultar o banco", async () => {
    for (const chave of [null, "qualquer", "dmb_curta", "dmb_" + "Z".repeat(64), `${CHAVE}; drop table x`]) {
      assert.equal((await pedir("GET", "config", { chave })).status, 401, String(chave));
    }
    assert.equal(chamadas.length, 0);
  });

  it("recebe o batimento e limita os tamanhos", async () => {
    resposta = { ok: true, status: 200, json: async () => true };
    const r = await pedir("POST", "heartbeat", { corpo: { versao: "1.0.0", host: "PC".repeat(100), estado: { whatsapp: true } } });
    assert.equal(r.status, 200);
    assert.equal(chamadas[0].corpo.p_computador.length, 80);
    assert.deepEqual(chamadas[0].corpo.p_estado, { whatsapp: true });
    assert.equal(chamadas[0].corpo.p_versao, "1.0.0");
  });

  it("registra a execução (ok falso vira falha; duração limitada)", async () => {
    resposta = { ok: true, status: 200, json: async () => true };
    const r = await pedir("POST", "execucoes", { corpo: { comando: "estoque", canal: "whatsapp", solicitante: "…8888", ok: false, erro: "x".repeat(900), duracao_ms: 99999999999 } });
    assert.equal(r.status, 201);
    const c = chamadas[0].corpo;
    assert.equal(c.p_sucesso, false);
    assert.equal(c.p_erro.length, 300);
    assert.equal(c.p_duracao_ms, 3_600_000);
    assert.equal((await pedir("POST", "execucoes", { corpo: {} })).status, 400);
  });

  it("corpo inválido ou grande demais dá 400", async () => {
    const r = await onRequest({
      request: new Request("https://painel.exemplo/api/v1/heartbeat", { method: "POST", headers: { Authorization: `Bearer ${CHAVE}` }, body: "{nao-json" }),
      env, params: { rota: ["heartbeat"] },
    });
    assert.equal(r.status, 400);
    assert.equal((await pedir("POST", "heartbeat", { corpo: { estado: "x".repeat(20_000) } })).status, 400);
  });

  it("rota ou método desconhecido dá 404", async () => {
    assert.equal((await pedir("GET", "apagar")).status, 404);
    assert.equal((await pedir("DELETE", "config")).status, 404);
  });

  it("se o Supabase cair, responde 502 sem vazar detalhes", async () => {
    resposta = { ok: false, status: 500, json: async () => ({}) };
    const r = await pedir("GET", "config");
    assert.equal(r.status, 502);
    assert.deepEqual(await r.json(), { erro: "Servidor de dados indisponível" });
  });

  it("sem variáveis do Supabase responde 500", async () => {
    assert.equal((await pedir("GET", "config", { e: {} })).status, 500);
  });
});

describe("config.js do painel", () => {
  it("publica só a URL e a chave pública", async () => {
    const r = configJs({ env: { ...env, SUPABASE_SECRET_KEY: "nao-pode-vazar" } });
    const texto = await r.text();
    assert.match(texto, /^window\.CONFIG = \{/);
    assert.ok(texto.includes("sb_publishable_teste") && texto.includes("projeto.supabase.co"));
    assert.equal(texto.includes("nao-pode-vazar"), false);
    assert.match(r.headers.get("content-type"), /javascript/);
  });
});

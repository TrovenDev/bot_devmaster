// Testes da entrega do instalador: node --test test/
import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { onRequestGet } from "../functions/api/instalador.js";

const original = globalThis.fetch;
afterEach(() => { globalThis.fetch = original; });

describe("GET /api/instalador", () => {
  it("repassa o arquivo da última release", async () => {
    let url;
    globalThis.fetch = async (u) => { url = u; return new Response(new Uint8Array([77, 90, 1, 2])); };
    const r = await onRequestGet();
    assert.equal(r.status, 200);
    assert.equal(url, "https://github.com/TrovenDev/bot_devmaster/releases/latest/download/BotDevMaster-Setup.exe");
    assert.deepEqual([...new Uint8Array(await r.arrayBuffer())], [77, 90, 1, 2]);
  });

  it("avisa quando ainda não há release", async () => {
    globalThis.fetch = async () => new Response("nao", { status: 404 });
    const r = await onRequestGet();
    assert.equal(r.status, 502);
  });
});

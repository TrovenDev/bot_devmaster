import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import vm from "node:vm";

const publicFile = name => new URL(`../public/${name}`, import.meta.url);

test("manifest aponta para ícones PNG válidos e abre como aplicativo", () => {
  const manifest = JSON.parse(readFileSync(publicFile("manifest.webmanifest")));
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.scope, "/");
  for (const icon of manifest.icons) {
    assert.ok(existsSync(publicFile(icon.src.slice(1))));
    const png = readFileSync(publicFile(icon.src.slice(1)));
    assert.equal(png.subarray(1, 4).toString(), "PNG");
    assert.equal(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`, icon.sizes);
  }
});

function worker(fetch) {
  const handlers = {};
  vm.runInNewContext(readFileSync(publicFile("sw.js"), "utf8"), {
    self: { location: { origin: "https://painel.test" }, addEventListener: (event, fn) => handlers[event] = fn },
    URL, fetch, caches: { match: async () => "offline" },
  });
  return handlers;
}

test("service worker não intercepta APIs ou recursos autenticados", () => {
  const handlers = worker(() => { throw new Error("Não deveria consultar"); });
  for (const url of ["https://painel.test/api/instalador", "https://projeto.supabase.co/rest/v1/empresas"]) {
    handlers.fetch({ request: { mode: "cors", url }, respondWith: () => assert.fail("Dados privados interceptados") });
  }
});

test("navegação offline mostra fallback e online recebe conteúdo novo", async () => {
  for (const online of [true, false]) {
    const handlers = worker(async () => { if (!online) throw new Error("offline"); return "novo"; });
    let result;
    handlers.fetch({ request: { mode: "navigate", url: "https://painel.test/" }, respondWith: value => result = value });
    assert.equal(await result, online ? "novo" : "offline");
  }
});

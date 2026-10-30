import { test } from 'node:test';
import assert from 'node:assert/strict';
import { onRequestGet } from '../functions/api/cnpj/[cnpj].js';
const env = { SUPABASE_URL: 'https://teste.supabase.co', SUPABASE_PUBLISHABLE_KEY: 'public' };
const pedir = (auth = 'Bearer token') => onRequestGet({ request: new Request('https://teste/api/cnpj/12345678000190', { headers: auth ? { Authorization: auth } : {} }), env, params: { cnpj: '12345678000190' } });
test('consulta exige login antes de acessar o provedor', async () => { assert.equal((await pedir('')).status, 401); });
test('bloqueia acesso sem permissao antes de consultar BrasilAPI', async () => {
  const anterior = globalThis.fetch;
  let chamadas = 0;
  globalThis.fetch = async () => new Response(JSON.stringify(++chamadas === 1 ? { id: 'usuario' } : []));
  try { assert.equal((await pedir()).status, 403); assert.equal(chamadas, 2); } finally { globalThis.fetch = anterior; }
});
test('consulta BrasilAPI sem chave e normaliza o nome', async () => {
  const anterior = globalThis.fetch;
  const chamadas = [];
  globalThis.fetch = async (url, options) => {
    chamadas.push({ url: String(url), options });
    return new Response(JSON.stringify(chamadas.length === 1 ? { id: 'usuario' } : chamadas.length === 2 ? [{ usuario_id: 'usuario' }] : { razao_social: 'EMPRESA DE TESTE LTDA 12345678000190', outro: 'interno' }));
  };
  try {
    const r = await pedir();
    assert.deepEqual(await r.json(), { cnpj: '12345678000190', nome: 'Empresa de Teste LTDA' });
    assert.equal(chamadas[2].url, 'https://brasilapi.com.br/api/cnpj/v1/12345678000190');
    assert.equal(chamadas[2].options.headers, undefined);
    assert.equal(r.headers.get('Cache-Control'), 'no-store');
  } finally { globalThis.fetch = anterior; }
});

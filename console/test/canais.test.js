import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const fonte = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
const trecho = fonte.slice(fonte.indexOf('function validarCanais('), fonte.indexOf('/** Executa uma consulta'));
const contexto = vm.createContext({ URL });
vm.runInContext(trecho, contexto);
const canais = { evo_url: 'https://evolution.exemplo.com', evo_instancia: 'Loja', evo_key: 'chave', whatsapp_menu: 'botoes', telegram_token: '' };
test('canal sem Telegram permite token vazio', () => {
  assert.equal(contexto.validarCanais(canais), canais);
});
test('valida URL e token antes de persistir', () => {
  assert.throws(() => contexto.validarCanais({ ...canais, evo_url: 'evolution.exemplo.com' }), /URL da Evolution/);
  assert.throws(() => contexto.validarCanais({ ...canais, telegram_token: 'token incompleto' }), /Token do Telegram/);
});
test('erro do banco identifica canal sem revelar segredos', () => {
  const texto = contexto.traduzir({ code: '23514', message: 'new row violates check constraint sistema_canais_telegram_token_check' });
  assert.match(texto, /Token do Telegram/);
  assert.doesNotMatch(texto, /DDI/);
});

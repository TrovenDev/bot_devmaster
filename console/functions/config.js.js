// Entrega ao painel o endereço do Supabase e a chave PÚBLICA (publishable). Vêm das variáveis do projeto no
// Cloudflare Pages, para o repositório não carregar dados do seu projeto. A chave publishable foi feita para
// ficar no navegador: quem protege os dados é o RLS do banco.
export function onRequestGet({ env }) {
  const config = { SUPABASE_URL: env.SUPABASE_URL || "", SUPABASE_PUBLISHABLE_KEY: env.SUPABASE_PUBLISHABLE_KEY || "" };
  return new Response(`window.CONFIG = ${JSON.stringify(config)};\n`, {
    headers: { "Content-Type": "application/javascript; charset=utf-8", "Cache-Control": "no-store" },
  });
}

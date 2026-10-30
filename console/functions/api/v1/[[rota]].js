// API usada pelo programa Bot DevMaster instalado em cada cliente.
// O programa só conhece este endereço e a chave do sistema; aqui a chave é conferida no banco (Supabase)
// pelas funções bot_*, que devolvem a configuração ou null (chave inválida/revogada).

const CHAVE = /^Bearer\s+(dmb_[0-9a-f]{64})$/;
const CABECALHOS = { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" };

const resposta = (dados, status = 200) => new Response(JSON.stringify(dados), { status, headers: CABECALHOS });

async function rpc(env, nome, corpo) {
  const r = await fetch(`${env.SUPABASE_URL}/rest/v1/rpc/${nome}`, {
    method: "POST",
    headers: {
      apikey: env.SUPABASE_PUBLISHABLE_KEY,
      Authorization: `Bearer ${env.SUPABASE_PUBLISHABLE_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(corpo),
  });
  if (!r.ok) throw new Error(`Supabase respondeu ${r.status}`);
  return r.json();
}

async function lerCorpo(request, limite = 16 * 1024) {
  const texto = await request.text();
  if (texto.length > limite) return null;
  try {
    const dados = JSON.parse(texto || "{}");
    return dados && typeof dados === "object" && !Array.isArray(dados) ? dados : null;
  } catch {
    return null;
  }
}

const texto = (v, max) => String(v ?? "").slice(0, max);

export async function onRequest({ request, env, params }) {
  if (!env.SUPABASE_URL || !env.SUPABASE_PUBLISHABLE_KEY) return resposta({ erro: "Servidor sem configuração do Supabase" }, 500);

  const m = CHAVE.exec(request.headers.get("Authorization") || "");
  if (!m) return resposta({ erro: "Chave ausente ou inválida" }, 401);
  const chave = m[1];
  const rota = [].concat(params.rota || []).join("/");

  try {
    if (rota === "config" && request.method === "GET") {
      const config = await rpc(env, "bot_configuracao", { p_chave: chave });
      return config ? resposta(config) : resposta({ erro: "Chave ausente ou inválida" }, 401);
    }

    if (rota === "heartbeat" && request.method === "POST") {
      const d = await lerCorpo(request);
      if (!d) return resposta({ erro: "JSON inválido" }, 400);
      const ok = await rpc(env, "bot_batimento", {
        p_chave: chave,
        p_versao: texto(d.versao, 30),
        p_computador: texto(d.host, 80),
        p_estado: d.estado && typeof d.estado === "object" && !Array.isArray(d.estado) ? d.estado : {},
      });
      return ok ? resposta({ ok: true }) : resposta({ erro: "Chave ausente ou inválida" }, 401);
    }

    if (rota === "execucoes" && request.method === "POST") {
      const d = await lerCorpo(request);
      if (!d || !String(d.comando || "").trim()) return resposta({ erro: "Informe o comando" }, 400);
      const ok = await rpc(env, "bot_registrar_execucao", {
        p_chave: chave,
        p_comando: texto(d.comando, 40),
        p_canal: texto(d.canal, 20),
        p_solicitante: texto(d.solicitante, 40),
        p_sucesso: d.ok !== false && d.ok !== 0,
        p_erro: texto(d.erro, 300),
        p_duracao_ms: Math.max(0, Math.min(Number(d.duracao_ms) || 0, 3_600_000)),
      });
      return ok ? resposta({ ok: true }, 201) : resposta({ erro: "Chave ausente ou inválida" }, 401);
    }
  } catch (e) {
    console.error("falha ao falar com o Supabase:", e?.message || e);
    return resposta({ erro: "Servidor de dados indisponível" }, 502);
  }

  return resposta({ erro: "Rota não encontrada" }, 404);
}

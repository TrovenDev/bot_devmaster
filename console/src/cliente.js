// API usada pelo programa Bot DevMaster instalado em cada cliente (autenticada pela chave do sistema).
import { CATALOGO, ErroHttp, json, lerJson, sha256hex, texto } from "./util.js";

async function autenticar(request, env) {
  const m = /^Bearer\s+(dmb_[A-Za-z0-9_-]{20,80})$/.exec(request.headers.get("Authorization") || "");
  if (!m) throw new ErroHttp(401, "Chave ausente ou inválida");
  const hash = await sha256hex(m[1]);
  const sistema = await env.DB.prepare(
    `SELECT s.*, e.nome AS empresa_nome, e.ativo AS empresa_ativa
       FROM sistemas s JOIN empresas e ON e.id = s.empresa_id WHERE s.chave_hash = ?`,
  )
    .bind(hash)
    .first();
  if (!sistema) throw new ErroHttp(401, "Chave ausente ou inválida");
  return sistema;
}

async function config(sistema, env) {
  const [comandos, contatos] = await Promise.all([
    env.DB.prepare("SELECT comando, titulo, arquivo FROM sistema_comandos WHERE sistema_id = ?").bind(sistema.id).all(),
    env.DB.prepare("SELECT canal, identificador FROM contatos WHERE sistema_id = ? AND ativo = 1").bind(sistema.id).all(),
  ]);
  const ativo = !!sistema.ativo && !!sistema.empresa_ativa;
  return {
    sistema: { id: sistema.id, nome: sistema.nome, ativo },
    empresa: { id: sistema.empresa_id, nome: sistema.empresa_nome },
    devmaster: { empresa: sistema.devmaster_empresa, modulo: sistema.devmaster_modulo },
    comandos: ativo
      ? comandos.results
          .filter((c) => CATALOGO[c.comando])
          .map((c) => ({
            nome: c.comando,
            titulo: c.titulo || CATALOGO[c.comando].titulo,
            descricao: CATALOGO[c.comando].descricao,
            arquivo: c.arquivo || CATALOGO[c.comando].arquivo,
          }))
      : [],
    whatsapp: { numeros: ativo ? contatos.results.filter((c) => c.canal === "whatsapp").map((c) => c.identificador) : [] },
    telegram: { ids: ativo ? contatos.results.filter((c) => c.canal === "telegram").map((c) => c.identificador) : [] },
    gerado_em: new Date().toISOString(),
  };
}

export async function rotaCliente(request, env, caminho) {
  const sistema = await autenticar(request, env);

  if (caminho === "/api/v1/config" && request.method === "GET") {
    return json(await config(sistema, env));
  }

  if (caminho === "/api/v1/heartbeat" && request.method === "POST") {
    const d = await lerJson(request);
    const estado = JSON.stringify(d.estado && typeof d.estado === "object" ? d.estado : {}).slice(0, 500);
    await env.DB.prepare("UPDATE sistemas SET versao = ?, host = ?, estado = ?, ultimo_contato = datetime('now') WHERE id = ?")
      .bind(texto(d.versao, "versao", { max: 30 }), texto(d.host, "host", { max: 80 }), estado, sistema.id)
      .run();
    if (Math.random() < 0.02) {
      // limpeza ocasional do histórico antigo
      await env.DB.prepare("DELETE FROM execucoes WHERE criado_em < datetime('now', '-90 days')").run();
      await env.DB.prepare("DELETE FROM tentativas_login WHERE quando < ?").bind(Math.floor(Date.now() / 1000) - 86400).run();
    }
    return json({ ok: true });
  }

  if (caminho === "/api/v1/execucoes" && request.method === "POST") {
    const d = await lerJson(request);
    const comando = texto(d.comando, "comando", { max: 40, obrigatorio: true });
    await env.DB.prepare(
      "INSERT INTO execucoes (sistema_id, comando, canal, solicitante, ok, erro, duracao_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
    )
      .bind(
        sistema.id,
        comando,
        texto(d.canal, "canal", { max: 20 }),
        texto(d.solicitante, "solicitante", { max: 40 }),
        d.ok ? 1 : 0,
        texto(d.erro, "erro", { max: 300 }),
        Math.max(0, Math.min(Number(d.duracao_ms) || 0, 3_600_000)),
      )
      .run();
    return json({ ok: true }, 201);
  }

  throw new ErroHttp(404, "Rota não encontrada");
}

// API do painel de gestão (autenticada por sessão com cookie assinado).
import {
  bool01, CATALOGO, ErroHttp, hmacBase64url, identificadorContato, iguais, inteiro, json, lerJson, nomeArquivo,
  novaChave, sha256hex, texto,
} from "./util.js";

const SESSAO_HORAS = 12;
const COOKIE = "__Host-sid";
const ONLINE_MINUTOS = 10;

// ---------------- Sessão ----------------
async function criarSessao(env) {
  const expira = Math.floor(Date.now() / 1000) + SESSAO_HORAS * 3600;
  const assinatura = await hmacBase64url(env.SESSION_SECRET, `s.${expira}`);
  return `${expira}.${assinatura}`;
}

async function sessaoValida(request, env) {
  const cookie = /(?:^|;\s*)__Host-sid=([^;]+)/.exec(request.headers.get("Cookie") || "");
  if (!cookie) return false;
  const [expira, assinatura] = cookie[1].split(".");
  if (!/^\d+$/.test(expira || "") || Number(expira) < Date.now() / 1000) return false;
  return iguais(assinatura || "", await hmacBase64url(env.SESSION_SECRET, `s.${expira}`));
}

function cookieSessao(valor, segundos) {
  return `${COOKIE}=${valor}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${segundos}`;
}

function conferirOrigem(request) {
  // Proteção extra contra CSRF nas operações que alteram dados
  if (["POST", "PUT", "PATCH", "DELETE"].includes(request.method)) {
    const origem = request.headers.get("Origin");
    if (origem && new URL(origem).host !== new URL(request.url).host) throw new ErroHttp(403, "Origem não permitida");
  }
}

async function login(request, env) {
  if (!env.ADMIN_PASSWORD || !env.SESSION_SECRET) throw new ErroHttp(500, "Servidor sem ADMIN_PASSWORD/SESSION_SECRET configurados");
  const ip = request.headers.get("CF-Connecting-IP") || "local";
  const agora = Math.floor(Date.now() / 1000);
  const { total } = await env.DB.prepare("SELECT COUNT(*) AS total FROM tentativas_login WHERE ip = ? AND quando > ?")
    .bind(ip, agora - 600)
    .first();
  if (total >= 5) throw new ErroHttp(429, "Muitas tentativas. Aguarde 10 minutos.");
  const { senha } = await lerJson(request, 2048);
  if (!(await iguais(String(senha || ""), env.ADMIN_PASSWORD))) {
    await env.DB.prepare("INSERT INTO tentativas_login (ip, quando) VALUES (?, ?)").bind(ip, agora).run();
    throw new ErroHttp(401, "Senha incorreta");
  }
  await env.DB.prepare("DELETE FROM tentativas_login WHERE ip = ?").bind(ip).run();
  return json({ ok: true }, 200, { "Set-Cookie": cookieSessao(await criarSessao(env), SESSAO_HORAS * 3600) });
}

// ---------------- Consultas ----------------
const SELECT_SISTEMA = `
  SELECT s.id, s.empresa_id, e.nome AS empresa_nome, s.nome, s.ativo, s.devmaster_empresa, s.devmaster_modulo,
         s.chave_final, s.chave_criada_em, s.versao, s.host, s.estado, s.ultimo_contato, s.criado_em,
         (s.ultimo_contato IS NOT NULL AND s.ultimo_contato > datetime('now', '-${ONLINE_MINUTOS} minutes')) AS online
    FROM sistemas s JOIN empresas e ON e.id = s.empresa_id`;

async function sistemaOu404(env, id) {
  const s = await env.DB.prepare(`${SELECT_SISTEMA} WHERE s.id = ?`).bind(id).first();
  if (!s) throw new ErroHttp(404, "Sistema não encontrado");
  return s;
}

async function detalheSistema(env, id) {
  const sistema = await sistemaOu404(env, id);
  const [comandos, contatos, execucoes] = await Promise.all([
    env.DB.prepare("SELECT comando, titulo, arquivo FROM sistema_comandos WHERE sistema_id = ? ORDER BY comando").bind(id).all(),
    env.DB.prepare("SELECT id, canal, identificador, nome, ativo FROM contatos WHERE sistema_id = ? ORDER BY canal, nome, id").bind(id).all(),
    env.DB.prepare("SELECT id, comando, canal, solicitante, ok, erro, duracao_ms, criado_em FROM execucoes WHERE sistema_id = ? ORDER BY id DESC LIMIT 30")
      .bind(id)
      .all(),
  ]);
  return { sistema, comandos: comandos.results, contatos: contatos.results, execucoes: execucoes.results };
}

async function salvarComandos(env, sistemaId, lista) {
  if (!Array.isArray(lista) || lista.length > 50) throw new ErroHttp(400, "Lista de comandos inválida");
  const vistos = new Set();
  const linhas = lista.map((c) => {
    const comando = texto(c.comando, "comando", { max: 40, obrigatorio: true });
    if (!CATALOGO[comando]) throw new ErroHttp(400, `Comando desconhecido: ${comando}`);
    if (vistos.has(comando)) throw new ErroHttp(400, `Comando repetido: ${comando}`);
    vistos.add(comando);
    return [comando, texto(c.titulo, "título", { max: 40 }), nomeArquivo(c.arquivo)];
  });
  await env.DB.batch([
    env.DB.prepare("DELETE FROM sistema_comandos WHERE sistema_id = ?").bind(sistemaId),
    ...linhas.map(([comando, titulo, arquivo]) =>
      env.DB.prepare("INSERT INTO sistema_comandos (sistema_id, comando, titulo, arquivo) VALUES (?, ?, ?, ?)").bind(sistemaId, comando, titulo, arquivo),
    ),
  ]);
}

async function empresaOu400(env, id) {
  const e = await env.DB.prepare("SELECT id FROM empresas WHERE id = ?").bind(id).first();
  if (!e) throw new ErroHttp(400, "Empresa não encontrada");
}

// ---------------- Rotas ----------------
export async function rotaAdmin(request, env, caminho) {
  const metodo = request.method;
  conferirOrigem(request);

  if (caminho === "/api/login" && metodo === "POST") return login(request, env);
  if (caminho === "/api/logout" && metodo === "POST") return json({ ok: true }, 200, { "Set-Cookie": cookieSessao("", 0) });
  if (!(await sessaoValida(request, env))) {
    if (caminho === "/api/sessao") return json({ autenticado: false });
    throw new ErroHttp(401, "Faça login");
  }
  if (caminho === "/api/sessao") return json({ autenticado: true });
  if (caminho === "/api/catalogo") return json(CATALOGO);

  let m;
  // ----- Resumo -----
  if (caminho === "/api/resumo" && metodo === "GET") {
    const [sist, emp, exec] = await Promise.all([
      env.DB.prepare(`SELECT COUNT(*) AS total, SUM(ultimo_contato > datetime('now', '-${ONLINE_MINUTOS} minutes')) AS online FROM sistemas`).first(),
      env.DB.prepare("SELECT COUNT(*) AS total FROM empresas").first(),
      env.DB.prepare("SELECT COUNT(*) AS total, SUM(ok = 0) AS falhas FROM execucoes WHERE criado_em > datetime('now', '-1 day')").first(),
    ]);
    return json({ sistemas: sist.total, online: sist.online || 0, empresas: emp.total, execucoes_24h: exec.total, falhas_24h: exec.falhas || 0 });
  }

  // ----- Empresas -----
  if (caminho === "/api/empresas" && metodo === "GET") {
    const r = await env.DB.prepare(
      "SELECT e.*, (SELECT COUNT(*) FROM sistemas s WHERE s.empresa_id = e.id) AS sistemas FROM empresas e ORDER BY e.nome",
    ).all();
    return json(r.results);
  }
  if (caminho === "/api/empresas" && metodo === "POST") {
    const d = await lerJson(request);
    const r = await env.DB.prepare("INSERT INTO empresas (nome, documento, observacao) VALUES (?, ?, ?)")
      .bind(texto(d.nome, "nome", { obrigatorio: true }), texto(d.documento, "documento", { max: 30 }), texto(d.observacao, "observação", { max: 500 }))
      .run();
    return json({ id: r.meta.last_row_id }, 201);
  }
  if ((m = /^\/api\/empresas\/(\d+)$/.exec(caminho))) {
    const id = inteiro(m[1], "id");
    if (metodo === "PUT") {
      const d = await lerJson(request);
      await env.DB.prepare("UPDATE empresas SET nome = ?, documento = ?, observacao = ?, ativo = ? WHERE id = ?")
        .bind(texto(d.nome, "nome", { obrigatorio: true }), texto(d.documento, "documento", { max: 30 }), texto(d.observacao, "observação", { max: 500 }), bool01(d.ativo), id)
        .run();
      return json({ ok: true });
    }
    if (metodo === "DELETE") {
      const { total } = await env.DB.prepare("SELECT COUNT(*) AS total FROM sistemas WHERE empresa_id = ?").bind(id).first();
      if (total) throw new ErroHttp(409, "Exclua ou mude os sistemas desta empresa antes");
      await env.DB.prepare("DELETE FROM empresas WHERE id = ?").bind(id).run();
      return json({ ok: true });
    }
  }

  // ----- Sistemas -----
  if (caminho === "/api/sistemas" && metodo === "GET") {
    const r = await env.DB.prepare(`${SELECT_SISTEMA} ORDER BY e.nome, s.nome`).all();
    return json(r.results);
  }
  if (caminho === "/api/sistemas" && metodo === "POST") {
    const d = await lerJson(request);
    const empresaId = inteiro(d.empresa_id, "empresa");
    await empresaOu400(env, empresaId);
    const chave = novaChave();
    const r = await env.DB.prepare(
      "INSERT INTO sistemas (empresa_id, nome, devmaster_empresa, devmaster_modulo, chave_hash, chave_final) VALUES (?, ?, ?, ?, ?, ?)",
    )
      .bind(
        empresaId,
        texto(d.nome, "nome", { obrigatorio: true }),
        texto(d.devmaster_empresa, "empresa do DevMaster", { max: 80 }) || "Loja/Gerencial",
        texto(d.devmaster_modulo, "módulo do DevMaster", { max: 80 }) || "Gestão Varejo Atacado",
        await sha256hex(chave),
        chave.slice(-4),
      )
      .run();
    const id = r.meta.last_row_id;
    await salvarComandos(env, id, d.comandos ?? Object.keys(CATALOGO).map((comando) => ({ comando })));
    return json({ id, chave }, 201); // a chave só aparece agora
  }
  if ((m = /^\/api\/sistemas\/(\d+)$/.exec(caminho))) {
    const id = inteiro(m[1], "id");
    if (metodo === "GET") return json(await detalheSistema(env, id));
    if (metodo === "PUT") {
      await sistemaOu404(env, id);
      const d = await lerJson(request);
      const empresaId = inteiro(d.empresa_id, "empresa");
      await empresaOu400(env, empresaId);
      await env.DB.prepare("UPDATE sistemas SET empresa_id = ?, nome = ?, ativo = ?, devmaster_empresa = ?, devmaster_modulo = ? WHERE id = ?")
        .bind(
          empresaId,
          texto(d.nome, "nome", { obrigatorio: true }),
          bool01(d.ativo),
          texto(d.devmaster_empresa, "empresa do DevMaster", { max: 80, obrigatorio: true }),
          texto(d.devmaster_modulo, "módulo do DevMaster", { max: 80, obrigatorio: true }),
          id,
        )
        .run();
      if (d.comandos !== undefined) await salvarComandos(env, id, d.comandos);
      return json({ ok: true });
    }
    if (metodo === "DELETE") {
      await sistemaOu404(env, id);
      await env.DB.prepare("DELETE FROM sistemas WHERE id = ?").bind(id).run();
      return json({ ok: true });
    }
  }
  if ((m = /^\/api\/sistemas\/(\d+)\/chave$/.exec(caminho)) && metodo === "POST") {
    const id = inteiro(m[1], "id");
    await sistemaOu404(env, id);
    const chave = novaChave(); // a chave antiga deixa de valer na hora
    await env.DB.prepare("UPDATE sistemas SET chave_hash = ?, chave_final = ?, chave_criada_em = datetime('now') WHERE id = ?")
      .bind(await sha256hex(chave), chave.slice(-4), id)
      .run();
    return json({ chave });
  }

  // ----- Contatos (números de WhatsApp e IDs do Telegram permitidos) -----
  if ((m = /^\/api\/sistemas\/(\d+)\/contatos$/.exec(caminho)) && metodo === "POST") {
    const id = inteiro(m[1], "id");
    await sistemaOu404(env, id);
    const d = await lerJson(request);
    const canal = texto(d.canal, "canal", { obrigatorio: true });
    const ident = identificadorContato(canal, d.identificador);
    try {
      const r = await env.DB.prepare("INSERT INTO contatos (sistema_id, canal, identificador, nome) VALUES (?, ?, ?, ?)")
        .bind(id, canal, ident, texto(d.nome, "nome", { max: 80 }))
        .run();
      return json({ id: r.meta.last_row_id }, 201);
    } catch (e) {
      if (String(e).includes("UNIQUE")) throw new ErroHttp(409, "Este contato já está cadastrado");
      throw e;
    }
  }
  if ((m = /^\/api\/contatos\/(\d+)$/.exec(caminho))) {
    const id = inteiro(m[1], "id");
    if (metodo === "PUT") {
      const atual = await env.DB.prepare("SELECT canal FROM contatos WHERE id = ?").bind(id).first();
      if (!atual) throw new ErroHttp(404, "Contato não encontrado");
      const d = await lerJson(request);
      await env.DB.prepare("UPDATE contatos SET identificador = ?, nome = ?, ativo = ? WHERE id = ?")
        .bind(identificadorContato(atual.canal, d.identificador), texto(d.nome, "nome", { max: 80 }), bool01(d.ativo), id)
        .run();
      return json({ ok: true });
    }
    if (metodo === "DELETE") {
      await env.DB.prepare("DELETE FROM contatos WHERE id = ?").bind(id).run();
      return json({ ok: true });
    }
  }

  // ----- Execuções -----
  if (caminho === "/api/execucoes" && metodo === "GET") {
    const url = new URL(request.url);
    const sistema = url.searchParams.get("sistema");
    const limite = Math.min(Number(url.searchParams.get("limite")) || 100, 500);
    const r = sistema
      ? await env.DB.prepare(
          `SELECT x.*, s.nome AS sistema_nome FROM execucoes x JOIN sistemas s ON s.id = x.sistema_id WHERE x.sistema_id = ? ORDER BY x.id DESC LIMIT ?`,
        ).bind(inteiro(sistema, "sistema"), limite).all()
      : await env.DB.prepare(
          `SELECT x.*, s.nome AS sistema_nome FROM execucoes x JOIN sistemas s ON s.id = x.sistema_id ORDER BY x.id DESC LIMIT ?`,
        ).bind(limite).all();
    return json(r.results);
  }

  throw new ErroHttp(404, "Rota não encontrada");
}

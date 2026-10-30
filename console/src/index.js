// Console de gestão do Bot DevMaster (Cloudflare Worker + D1).
import { rotaAdmin } from "./admin.js";
import { rotaCliente } from "./cliente.js";
import { ErroHttp, json } from "./util.js";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const caminho = url.pathname.replace(/\/+$/, "") || "/";
    try {
      if (caminho.startsWith("/api/v1/")) return await rotaCliente(request, env, caminho);
      if (caminho.startsWith("/api/")) return await rotaAdmin(request, env, caminho);
      return env.ASSETS.fetch(request); // painel (arquivos estáticos)
    } catch (e) {
      if (e instanceof ErroHttp) return json({ erro: e.message }, e.status);
      console.error("erro interno", e?.stack || e);
      return json({ erro: "Erro interno" }, 500);
    }
  },
};

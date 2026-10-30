// Entrega o instalador genérico (BotDevMaster-Setup.exe) da última release do GitHub.
// O painel baixa por aqui (mesma origem, sem CORS) e anexa a chave do sistema no navegador:
// a chave nunca passa por este servidor.

const REPOSITORIO = "TrovenDev/bot_devmaster";
const ARQUIVO = "BotDevMaster-Setup.exe";

export async function onRequestGet() {
  const origem = await fetch(`https://github.com/${REPOSITORIO}/releases/latest/download/${ARQUIVO}`, {
    headers: { "User-Agent": "BotDevMaster-Painel" },
    redirect: "follow",
  });
  if (!origem.ok || !origem.body) {
    return new Response(JSON.stringify({ erro: "Instalador ainda não publicado" }), {
      status: 502,
      headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
    });
  }
  return new Response(origem.body, {
    headers: { "Content-Type": "application/octet-stream", "Cache-Control": "no-store" },
  });
}

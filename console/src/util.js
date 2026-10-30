// Utilitários: respostas JSON, criptografia (Web Crypto) e validação.

export const CABECALHOS_JSON = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store",
};

export function json(dados, status = 200, extra = {}) {
  return new Response(JSON.stringify(dados), { status, headers: { ...CABECALHOS_JSON, ...extra } });
}

export class ErroHttp extends Error {
  constructor(status, mensagem) {
    super(mensagem);
    this.status = status;
  }
}

const enc = new TextEncoder();

export async function sha256hex(texto) {
  const buf = await crypto.subtle.digest("SHA-256", enc.encode(texto));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function base64url(bytes) {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export async function hmacBase64url(segredo, texto) {
  const chave = await crypto.subtle.importKey("raw", enc.encode(segredo), { name: "HMAC", hash: "SHA-256" }, false, [
    "sign",
  ]);
  return base64url(new Uint8Array(await crypto.subtle.sign("HMAC", chave, enc.encode(texto))));
}

/** Comparação em tempo constante (compara os SHA-256 para igualar os tamanhos). */
export async function iguais(a, b) {
  const [ha, hb] = await Promise.all([crypto.subtle.digest("SHA-256", enc.encode(a)), crypto.subtle.digest("SHA-256", enc.encode(b))]);
  return crypto.subtle.timingSafeEqual(ha, hb);
}

export function novaChave() {
  return "dmb_" + base64url(crypto.getRandomValues(new Uint8Array(32)));
}

export async function lerJson(request, limite = 64 * 1024) {
  const texto = await request.text();
  if (texto.length > limite) throw new ErroHttp(413, "Corpo grande demais");
  try {
    const dados = JSON.parse(texto || "{}");
    if (dados === null || typeof dados !== "object" || Array.isArray(dados)) throw new Error();
    return dados;
  } catch {
    throw new ErroHttp(400, "JSON inválido");
  }
}

export function texto(valor, campo, { max = 120, obrigatorio = false } = {}) {
  const v = valor === undefined || valor === null ? "" : String(valor).trim();
  if (obrigatorio && !v) throw new ErroHttp(400, `Informe: ${campo}`);
  if (v.length > max) throw new ErroHttp(400, `${campo} passa de ${max} caracteres`);
  return v;
}

export function inteiro(valor, campo) {
  const n = Number(valor);
  if (!Number.isInteger(n) || n <= 0) throw new ErroHttp(400, `${campo} inválido`);
  return n;
}

export const bool01 = (v) => (v === true || v === 1 || v === "1" || v === "true" ? 1 : 0);

/** Nome de arquivo seguro (sem pastas), terminado em .xlsx. */
export function nomeArquivo(valor) {
  const base = String(valor || "")
    .split(/[\\/]/)
    .pop()
    .replace(/[<>:"|?*\u0000-\u001f]+/g, "")
    .trim()
    .slice(0, 80);
  if (!base) return "";
  return base.toLowerCase().endsWith(".xlsx") ? base : `${base}.xlsx`;
}

export function identificadorContato(canal, valor) {
  const v = String(valor ?? "").trim();
  if (canal === "whatsapp") {
    const digitos = v.replace(/\D/g, "");
    if (digitos.length < 8 || digitos.length > 20) throw new ErroHttp(400, "Número de WhatsApp inválido (use DDI + DDD + número)");
    return digitos;
  }
  if (canal === "telegram") {
    if (!/^\d{3,15}$/.test(v)) throw new ErroHttp(400, "ID do Telegram inválido (só números)");
    return v;
  }
  throw new ErroHttp(400, "Canal inválido");
}

/** Catálogo dos comandos que o programa cliente sabe executar. */
export const CATALOGO = {
  estoque: {
    titulo: "Estoque Geral",
    descricao: "Gera o Saldos em Estoque (Excel) e envia aqui",
    arquivo: "Estoque Geral.xlsx",
  },
};

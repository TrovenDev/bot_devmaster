const CONECTORES = new Set(['de', 'da', 'do', 'das', 'dos', 'e', 'em', 'com', 'para', 'a', 'o'])
const SIGLAS = new Set(['ltda', 'me', 'epp', 'mei', 'eireli', 'sa', 's/a', 'ei'])

const VOGAIS = /[aeiouáéíóúâêôãõà]/i

// Sigla/iniciais (JF, GHR, DBM): 2 a 4 letras e nenhuma vogal — continua em maiúsculo em vez de virar "Jf".
function ehSigla(palavra) {
  const letras = palavra.replace(/[.,/-]/g, '')
  return /^[a-zà-ú]{2,4}$/i.test(letras) && !VOGAIS.test(letras)
}

// MEI e empresário individual vêm da Receita como "NOME 12345678000190": tira do começo e do fim do nome
// o que for número (parte do CNPJ), sem mexer em números que fazem parte do nome de verdade.
function tirarNumeroDoCnpj(texto, cnpj) {
  const digitosCnpj = cnpj.replace(/\D/g, '')
  const ehNumeroDoCnpj = (token) => {
    const digitos = token.replace(/\D/g, '')
    return digitos.length > 0 && /^[\d.\-/]+$/.test(token) && (digitos.length >= 6 || digitosCnpj.includes(digitos))
  }
  const palavras = texto.trim().split(/\s+/)
  while (palavras.length > 1 && ehNumeroDoCnpj(palavras[palavras.length - 1])) palavras.pop()
  while (palavras.length > 1 && ehNumeroDoCnpj(palavras[0])) palavras.shift()
  return palavras.join(' ')
}

function paraTitleCase(texto) {
  return texto
    .toLowerCase()
    .split(' ')
    .filter(Boolean)
    .map((palavra, i) => {
      const semPontuacao = palavra.replace(/[.,/]/g, '')
      if (SIGLAS.has(semPontuacao) || ehSigla(palavra)) return palavra.toUpperCase()
      if (i > 0 && CONECTORES.has(palavra)) return palavra
      return palavra.charAt(0).toUpperCase() + palavra.slice(1)
    })
    .join(' ')
}


const json = (dados, status = 200) => new Response(JSON.stringify(dados), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });

export async function onRequestGet({ request, env, params }) {
  const cnpj = String(params.cnpj || '');
  if (!/^\d{14}$/.test(cnpj)) return json({ erro: 'Informe um CNPJ com 14 dígitos.' }, 400);
  const auth = request.headers.get('Authorization');
  if (!auth || !/^Bearer \S+$/.test(auth)) return json({ erro: 'Entre para consultar empresas.' }, 401);
  if (!env.SUPABASE_URL || !env.SUPABASE_PUBLISHABLE_KEY) return json({ erro: 'Supabase não configurado.' }, 503);
  try {
    const headers = { apikey: env.SUPABASE_PUBLISHABLE_KEY, Authorization: auth };
    const usuario = await fetch(`${env.SUPABASE_URL}/auth/v1/user`, { headers, signal: AbortSignal.timeout(10000) });
    if (!usuario.ok) return json({ erro: 'Sessão expirada. Entre novamente.' }, 401);
    const { id } = await usuario.json();
    if (!id) return json({ erro: 'Sessão inválida.' }, 401);
    const admin = await fetch(`${env.SUPABASE_URL}/rest/v1/administradores?select=usuario_id&usuario_id=eq.${encodeURIComponent(id)}`, { headers, signal: AbortSignal.timeout(10000) });
    if (!admin.ok || !(await admin.json()).length) return json({ erro: 'Acesso restrito a administradores.' }, 403);
    const r = await fetch(`https://brasilapi.com.br/api/cnpj/v1/${cnpj}`, { signal: AbortSignal.timeout(12000), redirect: 'error' });
    if (!r.ok) return json({ erro: r.status === 404 ? 'CNPJ não encontrado.' : r.status === 429 ? 'Limite de consultas atingido. Tente novamente mais tarde.' : 'Consulta de CNPJ indisponível.' }, r.status === 404 ? 404 : 502);
    const d = await r.json();
    const nome = d.nome_fantasia || d.razao_social;
    if (typeof nome !== 'string' || !nome.trim()) return json({ erro: 'O provedor não retornou o nome da empresa. Confira o formato da integração.' }, 502);
    return json({ cnpj, nome: paraTitleCase(tirarNumeroDoCnpj(nome, cnpj)).slice(0, 120) });
  } catch { return json({ erro: 'Consulta indisponível no momento. Tente novamente.' }, 502); }
}

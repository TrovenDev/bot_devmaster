# Console de gestão do Bot DevMaster

Painel web para gerenciar **empresas**, **sistemas** (cada instalação do bot), **chaves**, os **arquivos/comandos** de
cada sistema e **quem pode pedir** (números de WhatsApp e IDs do Telegram). Roda no **Cloudflare Pages** e guarda
os dados no **Supabase** (Postgres + Auth + Realtime). O painel atualiza ao vivo: sistemas online, execuções e contatos.

```
Navegador (painel estático)  ──supabase-js + Auth + Realtime──▶  Supabase (tabelas em português, RLS)
Programa instalado (.exe)    ──/api/v1/*──▶ Pages Functions ──RPC bot_*──▶  Supabase
```

## 1. Banco (Supabase)

O esquema está em [`../supabase/migrations/`](../supabase/migrations/). Tabelas: `empresas`, `sistemas`,
`sistema_chaves`, `catalogo_comandos`, `sistema_comandos`, `contatos`, `execucoes`, `administradores`.

```bash
npx supabase login
npx supabase db query --linked --project-ref SEU_REF -f supabase/migrations/20261030170000_estrutura_inicial.sql
```

Ou cole o arquivo no **SQL Editor** do projeto. Pode rodar mais de uma vez.

**Primeiro administrador** (o painel só abre para quem está em `administradores`):

1. Supabase › **Authentication › Users › Add user** (e-mail e senha; marque *Auto Confirm*).
2. Entre no painel com esse usuário. Ele mostra o SQL pronto, com o seu `id`. Rode no SQL Editor:
   ```sql
   insert into public.administradores (usuario_id, nome) values ('SEU-ID-AQUI', 'Seu nome');
   ```
3. Em **Authentication › Providers › Email**, desligue *Allow new users to sign up*: só você cria usuários.

## 2. Publicar no Cloudflare Pages

**Pelo painel da Cloudflare (recomendado, publica a cada `git push`):**

1. **Workers & Pages › Create › Pages › Connect to Git** e escolha `TrovenDev/bot_devmaster`.
2. Configure:
   - **Production branch:** `main`
   - **Root directory:** `console`
   - **Build command:** *(vazio)*
   - **Build output directory:** `public`
3. **Settings › Variables and Secrets** (Production e Preview), em *Plaintext*:
   - `SUPABASE_URL` = `https://SEU_REF.supabase.co`
   - `SUPABASE_PUBLISHABLE_KEY` = a chave `sb_publishable_…` (Supabase › Project Settings › API Keys)
4. **Deployments › Retry deployment** para aplicar as variáveis.
5. **Custom domains** para usar um endereço seu (ex.: `bots.seudominio.com.br`).

**Ou pela linha de comando:**

```bash
cd console
npm install
npx wrangler pages project create bot-devmaster-console --production-branch main
npx wrangler pages deploy public --project-name bot-devmaster-console
```
e depois defina as duas variáveis no painel (passo 3).

Nunca coloque a chave `sb_secret_…` (nem a `service_role`) no Pages: o painel e a API só usam a chave pública, e a
segurança vem das políticas RLS do banco.

## 3. Ligar o programa

No programa (aba **Gestão**): **Endereço do servidor** = a URL do Pages e **Chave deste sistema** = a chave mostrada
uma única vez ao criar o sistema no painel.

## Rodar local

```bash
npm install
printf 'SUPABASE_URL=https://SEU_REF.supabase.co\nSUPABASE_PUBLISHABLE_KEY=sb_publishable_...\n' > .dev.vars
npm run dev          # http://127.0.0.1:8788
npm test             # testes da API do programa (Supabase simulado)
```

`npm run vendorizar` atualiza `public/vendor/supabase.js` (o painel não usa CDN: a CSP só aceita `'self'`).

## Segurança

- RLS ligado em todas as tabelas; sem login nada é lido. O hash das chaves fica em `sistema_chaves`, sem nenhum acesso
  pela API (só as funções `bot_*`, que recebem a chave).
- Chaves de 244 bits, mostradas uma vez; gerar outra invalida a anterior. Desativar o sistema ou a empresa esvazia
  comandos e contatos na próxima consulta; excluir o sistema bloqueia o programa na hora.
- O histórico de execuções é apagado depois de 90 dias (pg_cron).

## Consulta de CNPJ (BrasilAPI)

O cadastro consulta a BrasilAPI, sem chave de API, pelo endpoint
`https://brasilapi.com.br/api/cnpj/v1/{cnpj}`. A consulta acontece diretamente no navegador, como no Vitalicia, sem depender
de uma chamada externa pela funcao do Cloudflare.
Nao e necessario configurar variaveis RAPIDAPI no Cloudflare.

Como no Vitalicia, os nomes recebem tratamento de maiusculas, conectores e
siglas societarias, removendo numeros de CNPJ nas extremidades do nome.
O nome fantasia tem preferencia; na ausencia dele, usa a razao social.

Empresas e contatos usam sheets laterais; sistemas usam pagina propria.

## PWA e dispositivos móveis

O painel pode ser instalado no iPhone/iPad: abra a URL HTTPS no Safari, toque em
Compartilhar, Adicionar à Tela de Início e Adicionar. O botão “Instalar app” no painel
mostra essas instruções ou abre o convite de instalação quando disponível.

As listas se adaptam ao celular, com controles de toque e espaço para as áreas seguras
e o teclado. O painel exige conexão para ler e salvar dados. O service worker armazena
somente a página e o estilo do aviso offline; não armazena APIs, chaves ou dados de clientes.
Novas versões entram na próxima abertura, sem recarregar formulários em edição.

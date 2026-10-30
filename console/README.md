# Console de gestão do Bot DevMaster

Painel web (Cloudflare Worker + banco D1) para gerenciar **empresas**, **sistemas** (cada instalação do bot),
**chaves**, os **arquivos/comandos** de cada sistema e **quem pode pedir** (números de WhatsApp e IDs do Telegram).
Os programas instalados buscam a configuração aqui a cada 5 minutos e avisam que estão online.

## Rodar local

```bash
npm install
printf 'ADMIN_PASSWORD=troque-esta-senha\nSESSION_SECRET=um-texto-longo-e-aleatorio\n' > .dev.vars
npm run migrar:local
npm run dev            # http://127.0.0.1:8787
npm test               # com o dev rodando (ajuste CONSOLE_URL e ADMIN_PASSWORD se mudou)
```

## Publicar na Cloudflare

```bash
npx wrangler login
npx wrangler d1 create bot-devmaster            # cole o database_id em wrangler.jsonc ("database_id": "...")
npm run migrar                                  # cria as tabelas no banco remoto
npx wrangler secret put ADMIN_PASSWORD          # senha do painel
npx wrangler secret put SESSION_SECRET          # texto aleatório longo (assina o cookie de sessão)
npm run deploy
```

Depois, em **Workers › bot-devmaster-console › Settings › Domains**, adicione o domínio que preferir
(ex.: `bots.seudominio.com.br`). Use sempre HTTPS: o cookie de sessão é `Secure`.

## Como funciona

| Quem | Rota | Autenticação |
|------|------|--------------|
| Você (painel) | `/api/*` | senha → cookie de sessão assinado (12 h), 5 tentativas/10 min |
| Programa instalado | `/api/v1/config`, `/heartbeat`, `/execucoes` | `Authorization: Bearer dmb_…` (chave do sistema) |

- A chave é mostrada **uma vez** (ao criar ou gerar outra) e só o hash SHA-256 fica no banco.
- Desativar um sistema (ou a empresa) esvazia comandos e contatos na próxima consulta; excluir ou trocar a chave
  bloqueia o programa na hora.
- O programa guarda a última configuração em cache e continua funcionando se o console ficar fora do ar.

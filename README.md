# Bot DevMaster

Peça um relatório do **DevMaster Business** por mensagem. Quem está na lista de permitidos manda "oi" no
**WhatsApp** (Evolution API) ou no **Telegram**, escolhe a opção em um botão (ou lista, com mais de 3 opções) e o
robô abre o DevMaster, faz o login, gera o arquivo e devolve o Excel no mesmo chat. Toda mensagem é assinada
**Bot DevMaster**.

```
WhatsApp / Telegram  →  Bot DevMaster (.exe no servidor Windows)  →  DevMaster (automação da tela)
                              ↕
                  Console web (Cloudflare Pages + Supabase): empresas, sistemas, chaves, pessoas permitidas
```

## O que tem

- **Atendimento:** menu com botões (até 3 comandos) ou lista (mais de 3); comando direto (`estoque`) pula o menu.
- **Robô:** abre o DevMaster pelo atalho, faz o login (sem marcar "Lembrar-me"), escolhe a empresa e o módulo, gera o
  arquivo, salva em Downloads, responde ao aviso "abrir arquivo?" e sai por Programa › Sair.
- **Gaveta de apps:** fechar ou minimizar esconde a janela; o programa continua rodando. Pode abrir com o Windows.
- **Atualização automática:** consulta as [Releases](../../releases) deste repositório, confere o SHA-256 e troca o
  `.exe` quando nenhum comando está rodando.
- **Gestão pela web:** empresas, sistemas (cada instalação), chaves, comandos/arquivos de cada sistema e quem pode
  pedir (números de WhatsApp e IDs do Telegram). Veja [`console/`](console/).

## Instalar (no servidor Windows)

1. Baixe o `DevMasterBot.exe` da [última release](../../releases/latest) e coloque em uma pasta, por exemplo `C:\BotDevMaster\`.
2. Abra e preencha as abas (ou apenas **Gestão**, se usar o console web):
   - **Gestão:** endereço do console e a chave do sistema (criada no console).
   - **WhatsApp:** URL, instância e API key da Evolution API.
   - **Telegram:** token do bot.
   - **DevMaster:** usuário e senha, empresa e módulo do login.
3. **Iniciar**. Marque "Abrir junto com o Windows" para subir sozinho já na bandeja.

As configurações ficam em um `.env` ao lado do `.exe` (modelo em [`.env.example`](.env.example)). O programa precisa
de uma sessão do Windows aberta e desbloqueada, porque opera a tela do DevMaster.

## Desenvolver

```bash
pip install -r requirements-build.txt
python app/gui.py                      # roda o painel
python scripts/build_windows.py        # gera dist/DevMasterBot.exe
```

Para criar um comando novo: escreva a função em `app/devmaster.py` (devolve o caminho do arquivo gerado),
registre em `app/comandos.py` e inclua no `CATALOGO` de `console/src/util.js`.

## Publicar uma versão

1. Aumente `VERSION` em `app/versao.py` (ex.: `1.1.0`).
2. `git tag v1.1.0 && git push origin v1.1.0`
3. O GitHub Actions gera o `.exe` e publica a release; os programas instalados atualizam sozinhos.

## Segurança

- Só responde a números/IDs cadastrados; os demais são ignorados.
- Chaves dos sistemas são mostradas uma vez e guardadas como hash; gerar outra revoga a anterior.
- Segredos (`.env`, tokens, senhas) nunca entram no Git. Veja o `.gitignore`.

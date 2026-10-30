"""WhatsApp via Evolution API (v2): lê as mensagens recebidas por polling (não precisa
abrir porta no servidor), mostra o menu e executa os comandos. A resposta (e o arquivo)
vai sempre para quem pediu. Toda mensagem leva a assinatura "Bot DevMaster"."""
import base64
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import comandos
from configuracao import CONFIG, so_digitos
from versao import assinar_whatsapp

log = logging.getLogger("whatsapp")

INTERVALO = 3          # segundos entre consultas
JANELA = 100           # quantas mensagens recentes olhar a cada consulta


class EvolutionErro(Exception):
    pass


class WhatsApp:
    def __init__(self, url: str, instancia: str, chave: str, formato_menu: str = "botoes"):
        self.url = url.rstrip("/")
        self.instancia = urllib.parse.quote(instancia)
        self.chave = chave
        self.formato_menu = formato_menu  # "botoes" (botões até 3 opções, lista acima disso) ou "texto"
        self._parar = threading.Event()
        self._vistos: dict[str, int] = {}
        self._ultimo_menu: dict[str, float] = {}
        self._inicio = int(time.time())

    # ---------------- API ----------------
    def _chamar(self, caminho: str, corpo: dict) -> dict:
        req = urllib.request.Request(
            f"{self.url}{caminho}/{self.instancia}", method="POST",
            headers={"apikey": self.chave, "Content-Type": "application/json"},
            data=json.dumps(corpo).encode("utf-8"))
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            raise EvolutionErro(f"{e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        except Exception as e:
            raise EvolutionErro(str(e))

    def enviar_texto(self, numero: str, texto: str):
        self._chamar("/message/sendText", {"number": numero, "text": assinar_whatsapp(texto)})

    def enviar_arquivo(self, numero: str, caminho: str, mimetype: str, legenda: str = ""):
        with open(caminho, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        self._chamar("/message/sendMedia", {
            "number": numero, "mediatype": "document", "mimetype": mimetype,
            "caption": assinar_whatsapp(legenda), "fileName": os.path.basename(caminho), "media": b64})

    def enviar_menu(self, numero: str):
        cmds = list(comandos.disponiveis().values())
        if not cmds:
            self.enviar_texto(numero, "Nenhum comando está liberado para este sistema.")
            return
        linhas = [f"• *{c.nome}* - {c.titulo}: {c.descricao}" for c in cmds]
        texto = "Olá! Veja o que está disponível:\n\n" + "\n".join(linhas) + "\n\nResponda com o nome do comando."
        if self.formato_menu != "texto":
            try:
                if len(cmds) <= 3:
                    # até 3 opções: botões de resposta rápida
                    self._chamar("/message/sendButtons", {
                        "number": numero,
                        "title": "Bot | DevMaster",
                        "description": "Olá! O que você precisa?",
                        "footer": "",
                        "buttons": [{"type": "reply", "displayText": c.titulo[:20], "id": c.nome} for c in cmds],
                    })
                else:
                    # mais de 3: botão que abre uma lista para escolher
                    self._chamar("/message/sendList", {
                        "number": numero,
                        "title": "Bot | DevMaster",
                        "description": "Olá! O que você precisa?",
                        "buttonText": "Ver opções",
                        "footerText": "",
                        "sections": [{
                            "title": "Disponível",
                            "rows": [{"title": c.titulo[:24], "description": c.descricao[:72], "rowId": c.nome}
                                     for c in cmds],
                        }],
                    })
                return
            except EvolutionErro as e:
                log.warning("Botões/lista não aceitos pela API (%s); enviando menu em texto.", e)
        self.enviar_texto(numero, texto)

    # ---------------- Mensagens recebidas ----------------
    @staticmethod
    def _texto(msg: dict) -> str:
        """Texto digitado ou opção escolhida (lista/botão) em uma mensagem."""
        m = msg.get("message") or {}
        for valor in (
            m.get("conversation"),
            (m.get("extendedTextMessage") or {}).get("text"),
            ((m.get("listResponseMessage") or {}).get("singleSelectReply") or {}).get("selectedRowId"),
            (m.get("buttonsResponseMessage") or {}).get("selectedButtonId"),
            (m.get("templateButtonReplyMessage") or {}).get("selectedId"),
        ):
            if valor:
                return str(valor)
        return ""

    @staticmethod
    def _remetente(key: dict):
        """(destino da resposta, candidatos para conferir a permissão)."""
        jid = key.get("remoteJid", "")
        alt = key.get("remoteJidAlt") or ""
        cand = [so_digitos(x.split("@")[0]) for x in (jid, alt) if x]
        resposta = alt if jid.endswith("@lid") and alt else jid
        return resposta, cand

    @staticmethod
    def _permitido(candidatos) -> bool:
        permitidos = CONFIG.numeros_whatsapp()
        for c in candidatos:
            for p in permitidos:
                # números: compara os últimos 8 dígitos (tolera o 9º dígito e o código do país)
                if (len(p) <= 13 and len(c) <= 13 and c[-8:] == p[-8:]) or c == p:
                    return True
        return False

    def _buscar(self) -> list[dict]:
        dados = self._chamar("/chat/findMessages", {
            "where": {"key": {"fromMe": False}}, "page": 1, "offset": JANELA})
        recs = (dados.get("messages") or {}).get("records") or []
        novas = []
        for r in recs:
            key = r.get("key") or {}
            if key.get("fromMe"):
                continue  # a API nem sempre aplica o filtro: sem isto o bot responde a si mesmo
            jid = key.get("remoteJid", "")
            if not jid or jid.endswith("@g.us") or jid.endswith("@broadcast"):
                continue  # ignora grupos e status
            ts = int(r.get("messageTimestamp") or 0)
            mid = key.get("id") or r.get("id")
            if ts < self._inicio - 5 or mid in self._vistos:
                continue
            self._vistos[mid] = ts
            novas.append(r)
        corte = int(time.time()) - 3600  # esquece ids antigos
        for k in [k for k, t in self._vistos.items() if t < corte]:
            del self._vistos[k]
        return sorted(novas, key=lambda r: int(r.get("messageTimestamp") or 0))

    def _tratar(self, msg: dict):
        resposta, cand = self._remetente(msg.get("key") or {})
        if not self._permitido(cand):
            log.warning("WhatsApp: mensagem de número não autorizado (%s) ignorada.", ",".join(cand))
            return
        texto = self._texto(msg).strip().lower()
        nome = re.sub(r"^[/!#]", "", texto)
        disponiveis = comandos.disponiveis()
        nomes = list(disponiveis)
        if nome.isdigit() and 1 <= int(nome) <= len(nomes):
            nome = nomes[int(nome) - 1]
        log.info("WhatsApp de %s: %r", cand[0] if cand else "?", texto[:40])

        if nome in disponiveis:
            quem = (cand[0] if cand else "")[-4:]
            threading.Thread(target=self._rodar, args=(resposta, nome, quem), daemon=True).start()
        elif time.time() - self._ultimo_menu.get(resposta, 0) > 20:
            # no máximo um menu a cada 20 s por conversa (evita rajadas)
            self._ultimo_menu[resposta] = time.time()
            self.enviar_menu(resposta)

    def _rodar(self, numero: str, nome: str, quem: str):
        cmd = comandos.disponiveis()[nome]
        try:
            self.enviar_texto(numero, f"Gerando {cmd.titulo.lower()}, aguarde...")
            arquivo = comandos.executar(nome, canal="whatsapp", solicitante=f"…{quem}")
            self.enviar_arquivo(numero, arquivo, cmd.mimetype, cmd.titulo)
            log.info("WhatsApp: %s enviado para %s", os.path.basename(arquivo), numero)
        except comandos.Ocupado:
            self._avisar(numero, "Já tem uma tarefa rodando no DevMaster, aguarde e tente de novo.")
        except comandos.Desativado:
            self._avisar(numero, "Este sistema está desativado. Fale com o administrador.")
        except Exception as e:
            log.exception("Falha no comando %s (WhatsApp)", nome)
            self._avisar(numero, f"Falhou: {e}")

    def _avisar(self, numero: str, texto: str):
        try:
            self.enviar_texto(numero, texto)
        except EvolutionErro:
            log.exception("Não consegui responder no WhatsApp")

    # ---------------- Laço principal ----------------
    def run(self):
        """Bloqueia até parar(); chame em uma thread."""
        log.info("WhatsApp conectado (instância %s).", urllib.parse.unquote(self.instancia))
        while not self._parar.is_set():
            try:
                for msg in self._buscar():
                    try:
                        self._tratar(msg)
                    except Exception:
                        log.exception("Erro ao tratar mensagem do WhatsApp")
            except EvolutionErro as e:
                log.warning("WhatsApp: falha ao consultar mensagens: %s", e)
            self._parar.wait(INTERVALO)
        log.info("WhatsApp parado.")

    def parar(self):
        self._parar.set()

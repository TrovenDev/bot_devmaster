"""Configuração efetiva: valores locais (painel/.env) com a configuração do servidor de
gestão por cima, quando conectado. Quem consulta (bot, WhatsApp, robô) sempre lê daqui."""
import re
import threading

PADRAO_ARQUIVO = "Estoque Geral.xlsx"


def so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto))


class Configuracao:
    def __init__(self):
        self._lock = threading.Lock()
        self._local: dict = {}
        self._remota: dict | None = None

    # ---- entrada ----
    def definir_local(self, valores: dict):
        with self._lock:
            self._local = dict(valores)

    def definir_remota(self, dados: dict | None):
        with self._lock:
            self._remota = dados

    # ---- leitura ----
    @property
    def remota(self) -> dict | None:
        with self._lock:
            return self._remota

    def _r(self, *caminho, padrao=None):
        with self._lock:
            atual = self._remota
        for c in caminho:
            if not isinstance(atual, dict) or c not in atual:
                return padrao
            atual = atual[c]
        return atual

    def ativo(self) -> bool:
        return bool(self._r("sistema", "ativo", padrao=True))

    def empresa_login(self) -> str:
        """Empresa a escolher na tela de login do DevMaster (ex.: Loja/Gerencial)."""
        return (self._r("devmaster", "empresa") or self._local.get("DEVMASTER_EMPRESA") or "").strip()

    def modulo_login(self) -> str:
        return (self._r("devmaster", "modulo") or self._local.get("DEVMASTER_MODULO") or "").strip()

    def nome_empresa(self) -> str:
        return self._r("empresa", "nome", padrao="") or ""

    def ids_telegram(self) -> set[int]:
        remoto = self._r("telegram", "ids")
        if remoto is not None:
            return {int(x) for x in remoto if str(x).strip().lstrip("-").isdigit()}
        return {int(x) for x in re.split(r"[,\s]+", self._local.get("ALLOWED_IDS", "")) if x.strip().isdigit()}

    def numeros_whatsapp(self) -> set[str]:
        remoto = self._r("whatsapp", "numeros")
        # sem servidor: separa por vírgula, ponto e vírgula ou linha (espaço faz parte do número)
        bruto = remoto if remoto is not None else re.split(r"[,;\n]+", self._local.get("WHATSAPP_NUMEROS", ""))
        return {so_digitos(x) for x in bruto if so_digitos(x)}

    def comandos_remotos(self) -> dict | None:
        """{nome: {titulo, descricao, arquivo}} liberados para este sistema, ou None
        (sem servidor: todos os comandos do programa)."""
        lista = self._r("comandos")
        if lista is None:
            return None
        return {c["nome"]: c for c in lista if isinstance(c, dict) and c.get("nome")}


CONFIG = Configuracao()

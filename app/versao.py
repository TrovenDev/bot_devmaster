"""Versão do programa. Cada release no GitHub usa a tag v<VERSION> (ex.: v1.0.0)."""
VERSION = "1.1.0"
REPOSITORY = "TrovenDev/bot_devmaster"
NOME = "Bot DevMaster"      # nome do programa e assinatura das mensagens


def assinar(texto: str, italico: bool = False) -> str:
    """Rodapé 'Bot DevMaster' em toda mensagem enviada (WhatsApp usa _itálico_)."""
    marca = f"_{NOME}_" if italico else f"— {NOME}"
    return f"{texto}\n\n{marca}" if texto else marca

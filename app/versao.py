"""Versão do programa. Cada release no GitHub usa a tag v<VERSION> (ex.: v1.0.0)."""
VERSION = "1.1.11"
REPOSITORY = "TrovenDev/bot_devmaster"
NOME = "Bot DevMaster"      # nome do programa e assinatura das mensagens


def assinar(texto: str, italico: bool = False) -> str:
    """Rodapé 'Bot DevMaster' em toda mensagem enviada (WhatsApp usa _itálico_)."""
    marca = f"_{NOME}_" if italico else f"— {NOME}"
    return f"{texto}\n\n{marca}" if texto else marca


def assinar_whatsapp(texto: str) -> str:
    """Cabecalho em negrito seguido da mensagem no WhatsApp."""
    cabecalho = "*Bot | DevMaster:*"
    return f"{cabecalho}\n\n{texto}" if texto else cabecalho

import asyncio
import logging
import os

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes,
                          MessageHandler, filters)

import comandos
from configuracao import CONFIG
from versao import assinar

log = logging.getLogger("bot")


class Bot:
    """Bot do Telegram rodando no próprio event loop (dentro de uma thread da GUI).
    Mostra o menu em botões (igual ao WhatsApp) e assina as mensagens como Bot DevMaster."""

    def __init__(self, token: str):
        self.loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("id", self.meu_id))
        self.app.add_handler(CommandHandler(list(comandos.COMANDOS), self.comando))
        self.app.add_handler(CallbackQueryHandler(self.botao))
        # Qualquer outra mensagem (ou /start) mostra o menu com botões
        self.app.add_handler(MessageHandler(filters.ALL, self.menu))

    @staticmethod
    def autorizado(update: Update) -> bool:
        uid = update.effective_user.id if update.effective_user else None
        if uid not in CONFIG.ids_telegram():
            log.warning("Acesso negado: user_id=%s", uid)
            return False
        return True

    async def menu(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self.autorizado(update) or not update.effective_message:
            return
        cmds = list(comandos.disponiveis().values())
        if not cmds:
            await update.effective_message.reply_text(assinar("Nenhum comando está liberado para este sistema."))
            return
        teclado = InlineKeyboardMarkup([[InlineKeyboardButton(c.titulo, callback_data=c.nome)] for c in cmds])
        await update.effective_message.reply_text(assinar("Olá! O que você precisa?"), reply_markup=teclado)

    async def meu_id(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        # Aberto de propósito: serve para descobrir o ID e cadastrá-lo
        log.info("/id pedido por %s", update.effective_user.id)
        await update.message.reply_text(assinar(f"Seu ID: {update.effective_user.id}"))

    async def comando(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not self.autorizado(update):
            return
        nome = update.message.text.split()[0].lstrip("/").split("@")[0].lower()
        await self._rodar(update, nome)

    async def botao(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.callback_query.answer()
        if not self.autorizado(update):
            return
        await self._rodar(update, update.callback_query.data)

    async def _rodar(self, update: Update, nome: str):
        msg = update.effective_message
        cmd = comandos.disponiveis().get(nome)
        if cmd is None:
            await msg.reply_text(assinar("Este comando não está liberado para este sistema."))
            return
        await msg.reply_text(assinar(f"Gerando {cmd.titulo.lower()}, aguarde..."))
        log.info("%s por %s (Telegram)", nome, update.effective_user.id)
        try:
            arquivo = await asyncio.to_thread(comandos.executar, nome, "telegram",
                                              f"…{str(update.effective_user.id)[-4:]}")
            with open(arquivo, "rb") as f:
                await msg.reply_document(f, filename=os.path.basename(arquivo), caption=assinar(cmd.titulo))
            log.info("Enviado: %s", arquivo)
        except comandos.Ocupado:
            await msg.reply_text(assinar("Já tem uma tarefa rodando no DevMaster, aguarde e tente de novo."))
        except comandos.Desativado:
            await msg.reply_text(assinar("Este sistema está desativado. Fale com o administrador."))
        except Exception as e:
            log.exception("Falha no comando %s (Telegram)", nome)
            await msg.reply_text(assinar(f"Falhou: {e}"))

    async def _main(self):
        self._stop = asyncio.Event()
        async with self.app:
            await self.app.start()
            await self.app.updater.start_polling()
            log.info("Bot conectado ao Telegram.")
            await self._stop.wait()
            await self.app.updater.stop()
            await self.app.stop()
        log.info("Bot parado.")

    def run(self):
        """Bloqueia até stop(); chame em uma thread."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
        finally:
            self.loop.close()

    def stop(self):
        if self.loop and self._stop:
            self.loop.call_soon_threadsafe(self._stop.set)

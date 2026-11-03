"""Testes das regras que não dependem do DevMaster: python -m unittest discover -s app"""
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))

import atualizador  # noqa: E402
import comandos  # noqa: E402
import devmaster  # noqa: E402
import remoto  # noqa: E402
import whatsapp  # noqa: E402
from configuracao import CONFIG  # noqa: E402
from versao import assinar  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        CONFIG.definir_local({})
        CONFIG.definir_remota(None)


class TestConfiguracao(Base):
    def test_local_sem_servidor(self):
        CONFIG.definir_local({"ALLOWED_IDS": "1, 2 x 3", "WHATSAPP_NUMEROS": "+55 (11) 99999-8888; 5511888887777",
                              "DEVMASTER_EMPRESA": "Loja/Gerencial"})
        self.assertEqual(CONFIG.ids_telegram(), {1, 2, 3})
        self.assertEqual(CONFIG.numeros_whatsapp(), {"5511999998888", "5511888887777"})
        self.assertEqual(CONFIG.empresa_login(), "Loja/Gerencial")
        self.assertEqual(set(comandos.disponiveis()), {"estoque"})

    def test_servidor_manda_mais_que_o_local(self):
        CONFIG.definir_local({"ALLOWED_IDS": "1", "WHATSAPP_NUMEROS": "5511000000000", "DEVMASTER_EMPRESA": "Local"})
        CONFIG.definir_remota({"sistema": {"ativo": True}, "devmaster": {"empresa": "Loja Centro", "modulo": "Atacado"},
                               "telegram": {"ids": ["77"]}, "whatsapp": {"numeros": ["5511999998888"]},
                               "comandos": [{"nome": "estoque", "titulo": "Estoque Centro", "arquivo": "Centro.xlsx"}]})
        self.assertEqual(CONFIG.ids_telegram(), {77})
        self.assertEqual(CONFIG.numeros_whatsapp(), {"5511999998888"})
        self.assertEqual(CONFIG.empresa_login(), "Loja Centro")
        cmd = comandos.disponiveis()["estoque"]
        self.assertEqual((cmd.titulo, cmd.arquivo_padrao), ("Estoque Centro", "Centro.xlsx"))

    def test_comando_nao_liberado_some(self):
        CONFIG.definir_remota({"sistema": {"ativo": True}, "comandos": []})
        self.assertEqual(comandos.disponiveis(), {})
        with self.assertRaises(KeyError):
            comandos.executar("estoque")

    def test_sistema_desativado_bloqueia(self):
        CONFIG.definir_remota({"sistema": {"ativo": False}, "comandos": [{"nome": "estoque"}]})
        with self.assertRaises(comandos.Desativado):
            comandos.executar("estoque")

    def test_credenciais_do_painel_tem_prioridade(self):
        CONFIG.definir_local({"EVO_URL": "http://local/", "EVO_INSTANCIA": "loja", "EVO_KEY": "k1",
                              "TELEGRAM_TOKEN": "111:local"})
        self.assertEqual(CONFIG.evolution(), ("http://local", "loja", "k1", "botoes"))
        CONFIG.definir_remota({"whatsapp": {"url": "https://evo.exemplo/", "instancia": "", "apikey": "k2",
                                            "menu": "texto"}, "telegram": {"token": "222:painel"}})
        # vazio no painel = usa o deste computador
        self.assertEqual(CONFIG.evolution(), ("https://evo.exemplo", "loja", "k2", "texto"))
        self.assertEqual(CONFIG.telegram_token(), "222:painel")

    def test_assinatura(self):
        self.assertTrue(assinar("oi").endswith("— Bot DevMaster"))
        self.assertTrue(assinar("oi", italico=True).endswith("_Bot DevMaster_"))


class TestComandos(Base):
    def test_execucao_avisa_observadores_e_respeita_a_trava(self):
        vistos = []
        comandos.observar(vistos.append)
        com = comandos.Comando("estoque", "T", "d", lambda o: f"{o.empresa}|{o.arquivo}")
        CONFIG.definir_local({"DEVMASTER_EMPRESA": "Loja X"})
        with mock.patch.dict(comandos.COMANDOS, {"estoque": com}):
            self.assertEqual(comandos.executar("estoque", "whatsapp", "…8888"), "Loja X|Estoque Geral.xlsx")
            comandos._trava.acquire()
            try:
                with self.assertRaises(comandos.Ocupado):
                    comandos.executar("estoque")
            finally:
                comandos._trava.release()
        self.assertTrue(vistos[-1]["ok"])
        self.assertEqual(vistos[-1]["canal"], "whatsapp")
        comandos._observadores.remove(vistos.append) if vistos.append in comandos._observadores else None


class TestDevMaster(unittest.TestCase):
    def test_modal_nativo_e_localizado_sem_busca_uia(self):
        modal = mock.Mock()
        with mock.patch.object(devmaster, "_dialogo_nativo", return_value=modal), \
             mock.patch.object(devmaster, "_achar") as uia, \
             mock.patch.object(devmaster, "ButtonWrapper") as botao:
            self.assertIs(devmaster._abrir_dialogo(123, {"native_title_re": "XLSX"}, {"native_title_re": "Salvar"}), modal)
            uia.assert_not_called()

    def test_pid_em_cache_nao_resolve_janela_principal_modal(self):
        from types import SimpleNamespace
        janela = SimpleNamespace(_devmaster_pid=123, process_id=mock.Mock(side_effect=RuntimeError("janela indisponivel")))
        self.assertEqual(devmaster._processo(janela), 123)
        janela.process_id.assert_not_called()

    def test_falha_de_limpeza_nao_esconde_erro_de_exportacao(self):
        with tempfile.TemporaryDirectory() as pasta, \
             mock.patch.object(devmaster, "PASTA_SAIDA", pasta), \
             mock.patch.object(devmaster, "_abrir_sistema", return_value=(mock.Mock(), False)), \
             mock.patch.object(devmaster, "_abrir_relatorio"), \
             mock.patch.object(devmaster, "_preencher_filtros"), \
             mock.patch.object(devmaster, "_exportar_xlsx", side_effect=RuntimeError("erro original XLSX")), \
             mock.patch.object(devmaster, "_fechar_relatorio", side_effect=RuntimeError("erro limpeza")):
            with self.assertRaisesRegex(RuntimeError, "erro original XLSX"):
                devmaster.gerar_estoque()

    def test_modal_aparece_antes_de_invoke_retornar(self):
        import threading
        acionado = threading.Event()
        liberar = threading.Event()
        terminou = threading.Event()
        origem, destino = object(), object()
        def achar(janela, **criterios):
            if criterios.get("title") == "XLSX":
                return origem
            self.assertTrue(acionado.wait(2))
            return destino
        def clicar(controle):
            acionado.set()
            liberar.wait(3)
            terminou.set()
        try:
            with mock.patch.object(devmaster, "_achar", side_effect=achar), \
                 mock.patch.object(devmaster, "_clicar", side_effect=clicar):
                resultado = devmaster._abrir_dialogo(123, {"title": "XLSX"}, {"auto_id": "btnOK"})
                self.assertIs(resultado, destino)
                self.assertFalse(terminou.is_set())
        finally:
            liberar.set()
            self.assertTrue(terminou.wait(2))

    def test_favorito_nao_abre_apenas_selecionando_card(self):
        card = mock.Mock()
        card.invoke.side_effect = RuntimeError("sem invoke")
        devmaster._ativar_favorito(card)
        card.iface_legacy_iaccessible.DoDefaultAction.assert_called_once()
        card.iface_selection_item.Select.assert_not_called()

    def test_favorito_sem_filtros_tenta_menu(self):
        janela = mock.Mock()
        with mock.patch.object(devmaster, "_aguardar_filtros", side_effect=[False, False, True]), \
             mock.patch.object(devmaster, "_achar", return_value=mock.Mock()), \
             mock.patch.object(devmaster, "_clicar"), \
             mock.patch.object(devmaster, "_ativar_favorito"), \
             mock.patch.object(devmaster, "_clicar_menu") as menu:
            devmaster._abrir_relatorio(janela)
        self.assertEqual(menu.call_count, 2)

    def test_relatorio_nao_confirmado_nao_avanca_para_filtros(self):
        with mock.patch.object(devmaster, "_aguardar_filtros", return_value=False), \
             mock.patch.object(devmaster, "_achar", return_value=mock.Mock()), \
             mock.patch.object(devmaster, "_clicar"), \
             mock.patch.object(devmaster, "_ativar_favorito"), \
             mock.patch.object(devmaster, "_clicar_menu"):
            with self.assertRaisesRegex(RuntimeError, "nao abriu"):
                devmaster._abrir_relatorio(mock.Mock())

    def test_clique_uia_nao_usa_cursor(self):
        controle = mock.Mock()
        devmaster._clicar(controle)
        controle.invoke.assert_called_once()
        controle.click_input.assert_not_called()
        controle.set_focus.assert_not_called()

    def test_preenchimento_direto_sem_foco(self):
        controle = mock.Mock()
        devmaster._escrever(controle, "senha com espacos ")
        controle.iface_value.SetValue.assert_called_once_with("senha com espacos ")
        controle.set_focus.assert_not_called()

    def test_controle_sem_acao_nao_simula_sucesso_por_foco(self):
        from types import SimpleNamespace
        controle = SimpleNamespace()
        with self.assertRaises(RuntimeError):
            devmaster._clicar(controle)

    def test_teclas_sao_enviadas_apenas_ao_hwnd_alvo(self):
        from types import SimpleNamespace
        with mock.patch.object(devmaster, "HwndWrapper") as wrapper:
            devmaster._teclas(SimpleNamespace(handle=123), "{TAB}")
        wrapper.assert_called_once_with(123)
        wrapper.return_value.send_keystrokes.assert_called_once_with("{TAB}")

    def test_busca_atalho_ignora_o_bot_e_prefere_devmaster(self):
        with tempfile.TemporaryDirectory() as d:
            for nome in ("Bot DevMaster.lnk", "DevMasterBot.exe", "DevMaster Business.lnk", "DevMaster.lnk"):
                Path(d, nome).touch()
            with mock.patch.object(devmaster, "_pasta_windows", return_value=d), \
                 mock.patch.dict(os.environ, {"DEVMASTER_ATALHO": str(Path(d, "Bot DevMaster.lnk"))}):
                self.assertEqual(devmaster._achar_atalho(), str(Path(d, "DevMaster.lnk")))

    def test_bot_e_instalador_nao_sao_atalhos_do_sistema(self):
        for nome in ("Bot DevMaster.lnk", "DevMasterBot.exe", "BotDevMaster-Setup.exe"):
            self.assertFalse(devmaster._atalho_do_sistema(nome))
        self.assertTrue(devmaster._atalho_do_sistema("DevMaster Business.lnk"))

    def test_nome_do_arquivo_e_seguro(self):
        b = chr(92)
        self.assertEqual(devmaster._nome_seguro(""), "Estoque Geral.xlsx")
        self.assertEqual(devmaster._nome_seguro("Centro"), "Centro.xlsx")
        self.assertEqual(devmaster._nome_seguro(f"..{b}..{b}Windows{b}evil"), "evil.xlsx")
        self.assertEqual(devmaster._nome_seguro("a/b/c.xlsx"), "c.xlsx")


class TestWhatsApp(Base):
    def test_polling_nao_reprocessa_mensagem_apos_uma_hora(self):
        bot = whatsapp.WhatsApp("https://evolution", "instancia", "chave")
        bot._inicio = 1000
        mensagem = {"key": {"id": "msg1", "remoteJid": "5511999998888@s.whatsapp.net"}, "messageTimestamp": 1001}
        with mock.patch.object(bot, "_chamar", return_value={"messages": {"records": [mensagem]}}):
            with mock.patch.object(whatsapp.time, "time", return_value=1002):
                self.assertEqual(len(bot._buscar()), 1)
            with mock.patch.object(whatsapp.time, "time", return_value=5000):
                self.assertEqual(bot._buscar(), [])
                self.assertEqual(bot._buscar(), [])

    def test_conexao_fechada_nao_tenta_avisar_no_canal_desconectado(self):
        bot = whatsapp.WhatsApp("https://evolution", "instancia", "chave")
        with mock.patch.object(bot, "enviar_texto", side_effect=whatsapp.ConexaoFechada("Connection Closed")) as enviar, \
             mock.patch.object(bot, "_avisar") as avisar, \
             mock.patch.object(whatsapp.comandos, "executar") as executar:
            bot._rodar("5511999998888", "estoque", "8888")
        enviar.assert_called_once()
        avisar.assert_not_called()
        executar.assert_not_called()

    def test_connection_closed_vira_erro_de_conexao(self):
        import io
        erro = urllib.error.HTTPError("https://evolution", 500, "erro", {}, io.BytesIO(b'{"response":{"message":"Connection Closed"}}'))
        bot = whatsapp.WhatsApp("https://evolution", "instancia", "chave")
        with mock.patch.object(whatsapp.urllib.request, "urlopen", side_effect=erro):
            with self.assertRaises(whatsapp.ConexaoFechada):
                bot.enviar_texto("5511999998888", "oi")

    def test_menu_nao_repete_envio_quando_conexao_fechada(self):
        bot = whatsapp.WhatsApp("https://evolution", "instancia", "chave")
        with mock.patch.object(bot, "_chamar", side_effect=whatsapp.ConexaoFechada("Connection Closed")) as chamar:
            with self.assertRaises(whatsapp.ConexaoFechada):
                bot.enviar_menu("5511999998888")
        chamar.assert_called_once()

    def test_assinatura_no_inicio_do_texto_e_legenda(self):
        bot = whatsapp.WhatsApp("https://evolution", "instancia", "chave", "texto")
        with mock.patch.object(bot, "_chamar") as chamar:
            bot.enviar_texto("5511999998888", "Mensagem")
            self.assertEqual(chamar.call_args.args[1]["text"], "*Bot | DevMaster:*\n\nMensagem")
            with tempfile.TemporaryDirectory() as d:
                arquivo = Path(d, "relatorio.xlsx")
                arquivo.write_bytes(b"arquivo")
                bot.enviar_arquivo("5511999998888", str(arquivo), "application/octet-stream", "Relatorio")
            self.assertEqual(chamar.call_args.args[1]["caption"], "*Bot | DevMaster:*\n\nRelatorio")

    def test_texto_de_lista_e_botao(self):
        t = whatsapp.WhatsApp._texto
        self.assertEqual(t({"message": {"conversation": "estoque"}}), "estoque")
        self.assertEqual(t({"message": {"listResponseMessage": {"singleSelectReply": {"selectedRowId": "estoque"}}}}), "estoque")
        self.assertEqual(t({"message": {"buttonsResponseMessage": {"selectedButtonId": "estoque"}}}), "estoque")
        self.assertEqual(t({"message": {"imageMessage": {}}}), "")

    def test_permissao_por_numero(self):
        CONFIG.definir_remota({"whatsapp": {"numeros": ["5511999998888"]}})
        ok = whatsapp.WhatsApp._permitido
        self.assertTrue(ok(["5511999998888"]))
        self.assertTrue(ok(["551199998888"]))        # sem o 9º dígito
        self.assertTrue(ok(["11999998888"]))         # sem o DDI
        self.assertFalse(ok(["5511999990000"]))
        self.assertFalse(ok([]))

    def test_remetente_lid_usa_o_numero_alternativo(self):
        r = whatsapp.WhatsApp._remetente({"remoteJid": "123@lid", "remoteJidAlt": "5511999998888@s.whatsapp.net"})
        self.assertEqual(r[0], "5511999998888@s.whatsapp.net")
        self.assertIn("5511999998888", r[1])


class TestAtualizador(unittest.TestCase):
    def test_reinicio_extrai_python_em_nova_pasta_temporaria(self):
        with tempfile.TemporaryDirectory() as d:
            a = atualizador.Atualizador(d)
            a.congelado = True
            a._pronto = Path(d, "novo.exe")
            a._pronto.write_bytes(b"MZ")
            a._pasta.mkdir()
            with mock.patch.object(atualizador.subprocess, "Popen") as iniciar:
                self.assertTrue(a.aplicar())
            self.assertEqual(iniciar.call_args.kwargs["env"]["PYINSTALLER_RESET_ENVIRONMENT"], "1")
            self.assertIn('set "PYINSTALLER_RESET_ENVIRONMENT=1"', (a._pasta / "atualizar.bat").read_text())

    def test_atualizacao_pronta_aguarda_clique_e_nao_interrompe_tarefa(self):
        with tempfile.TemporaryDirectory() as d:
            a = atualizador.Atualizador(d, ocupado=lambda: True)
            a.congelado = True
            a._pronto = Path(d, "novo.exe")
            self.assertFalse(a.pronta)
            a._pronto.write_bytes(b"MZ")
            self.assertTrue(a.pronta)
            with mock.patch.object(atualizador.subprocess, "Popen") as iniciar:
                self.assertFalse(a.aplicar())
                iniciar.assert_not_called()

    def test_verificacao_periodica_nao_instala_sem_clique(self):
        a = atualizador.Atualizador(".")
        a._parar = mock.Mock()
        a._parar.is_set.side_effect = [False, True]
        with mock.patch.object(a, "verificar", return_value=True) as verificar, \
             mock.patch.object(a, "aplicar") as aplicar:
            a.run()
        verificar.assert_called_once()
        aplicar.assert_not_called()

    def test_https_verifica_certificado_com_raizes_empacotadas(self):
        contexto = mock.Mock()
        with mock.patch.object(atualizador.ssl, "create_default_context", return_value=contexto), \
             mock.patch.object(atualizador.certifi, "where", return_value="raizes.pem"), \
             mock.patch.object(atualizador.urllib.request, "urlopen") as abrir:
            atualizador.Atualizador._abrir("https://api.github.com")
        contexto.load_verify_locations.assert_called_once_with(cafile="raizes.pem")
        self.assertIs(abrir.call_args.kwargs["context"], contexto)

    def test_versoes(self):
        v = atualizador.versao_tupla
        self.assertEqual(v("v1.2.3"), (1, 2, 3))
        self.assertGreater(v("1.10.0"), v("1.9.9"))
        self.assertEqual(v("lixo"), (0, 0, 0))

    def test_script_de_troca(self):
        s = atualizador.Atualizador._script(Path("C:/x/novo.exe"), Path("C:/x/bot.exe"), 123)
        self.assertIn('copy /y "%NOVO%" "%ALVO%"', s)
        self.assertIn("--minimizado", s)
        self.assertIn("System32", s)

    def test_baixar_exige_sha256_e_executavel(self):
        with tempfile.TemporaryDirectory() as d:
            a = atualizador.Atualizador(d)
            conteudo = b"MZ" + b"x" * 100

            class Resposta:
                def __init__(self, dados): self.dados, self.i = dados, 0
                def read(self, n=-1):
                    bloco, self.dados = self.dados[:n], self.dados[n:]
                    return bloco
                def __enter__(self): return self
                def __exit__(self, *_): pass

            import hashlib
            certo = hashlib.sha256(conteudo).hexdigest()
            destino = Path(d) / "novo.exe"
            with mock.patch.object(atualizador.Atualizador, "_abrir", return_value=Resposta(conteudo)):
                a._baixar({"browser_download_url": "https://x"}, destino, certo)
            self.assertTrue(destino.exists())
            ruim = Path(d) / "ruim.exe"
            with mock.patch.object(atualizador.Atualizador, "_abrir", return_value=Resposta(conteudo)):
                with self.assertRaises(ValueError):
                    a._baixar({"browser_download_url": "https://x"}, ruim, "0" * 64)
            self.assertFalse(ruim.exists())


class TestRemoto(Base):
    def test_permissoes_mudam_sem_reiniciar_o_bot(self):
        with tempfile.TemporaryDirectory() as d:
            g = remoto.Gestao("https://painel", "dmb_chave", d, "1.0.0")
            inicial = {"whatsapp": {"numeros": ["5511999991234"]}, "telegram": {"ids": [123]}}
            nova = {"whatsapp": {"numeros": ["5511888885678"]}, "telegram": {"ids": [456]}}
            g.ao_mudar = mock.Mock()
            with mock.patch.object(g, "_pedir", side_effect=[inicial, nova]):
                g._atualizar_config()
                self.assertTrue(whatsapp.WhatsApp._permitido(["5511999991234"]))
                self.assertEqual(CONFIG.ids_telegram(), {123})
                g._atualizar_config()
                self.assertFalse(whatsapp.WhatsApp._permitido(["5511999991234"]))
                self.assertTrue(whatsapp.WhatsApp._permitido(["5511888885678"]))
                self.assertEqual(CONFIG.ids_telegram(), {456})
            self.assertEqual(json.loads(g._cache.read_text(encoding="utf-8")), nova)
            self.assertGreaterEqual(g.ao_mudar.call_count, 2)

    def test_gestao_usa_certificados_sem_desativar_https(self):
        with tempfile.TemporaryDirectory() as d:
            g = remoto.Gestao("https://painel", "dmb_chave", d, "1.0.0")
            contexto = mock.Mock()
            with mock.patch.object(remoto.ssl, "create_default_context", return_value=contexto), \
                 mock.patch.object(remoto.certifi, "where", return_value="raizes.pem"), \
                 mock.patch.object(remoto.urllib.request, "urlopen") as abrir:
                abrir.return_value.__enter__.return_value.read.return_value = b'{}'
                self.assertEqual(g._pedir("GET", "/config"), {})
            contexto.load_verify_locations.assert_called_once_with(cafile="raizes.pem")
            self.assertIs(abrir.call_args.kwargs["context"], contexto)

    def test_chave_revogada_bloqueia_e_servidor_fora_usa_cache(self):
        with tempfile.TemporaryDirectory() as d:
            g = remoto.Gestao("http://x", "dmb_chave", d, "1.0.0")
            erro401 = urllib.error.HTTPError("http://x", 401, "no", {}, None)
            with mock.patch.object(g, "_pedir", side_effect=erro401):
                g._atualizar_config()
            self.assertFalse(CONFIG.ativo())
            self.assertEqual(CONFIG.numeros_whatsapp(), set())

            CONFIG.definir_remota(None)
            dados = {"sistema": {"ativo": True, "nome": "S"}, "empresa": {"nome": "E"}, "comandos": []}
            with mock.patch.object(g, "_pedir", return_value=dados):
                g._atualizar_config()
            self.assertIn("conectado", g.status)
            CONFIG.definir_remota(None)
            with mock.patch.object(g, "_pedir", side_effect=OSError("sem rede")):
                g._atualizar_config()
            self.assertIn("offline", g.status)
            self.assertEqual(CONFIG.nome_empresa(), "E")  # veio do cache em disco


if __name__ == "__main__":
    unittest.main()

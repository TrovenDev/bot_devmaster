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
    def test_nome_do_arquivo_e_seguro(self):
        b = chr(92)
        self.assertEqual(devmaster._nome_seguro(""), "Estoque Geral.xlsx")
        self.assertEqual(devmaster._nome_seguro("Centro"), "Centro.xlsx")
        self.assertEqual(devmaster._nome_seguro(f"..{b}..{b}Windows{b}evil"), "evil.xlsx")
        self.assertEqual(devmaster._nome_seguro("a/b/c.xlsx"), "c.xlsx")


class TestWhatsApp(Base):
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

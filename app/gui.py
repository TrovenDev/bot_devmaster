"""Bot DevMaster: painel de configuração, WhatsApp/Telegram, servidor de gestão,
atualização automática e bandeja do sistema. Visual na identidade Troven (marca.py)."""
import contextlib
import logging
import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from dotenv import dotenv_values

# Pasta do .exe (PyInstaller) ou do script: .env, logs e inspeções ficam ao lado dele
BASE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
os.chdir(BASE)
ENV = os.path.join(BASE, ".env")
INSTALACAO = os.path.join(BASE, "instalacao.env")   # deixado pelo instalador (endereço do painel e chave)
PASTA_INSPECAO = os.path.join(BASE, "inspecoes")

import bandeja  # noqa: E402
import comandos  # noqa: E402
import devmaster  # noqa: E402
import marca as M  # noqa: E402
from atualizador import Atualizador  # noqa: E402
from bot import Bot  # noqa: E402
from configuracao import CONFIG  # noqa: E402
from remoto import Gestao  # noqa: E402
from versao import NOME, VERSION  # noqa: E402
from whatsapp import WhatsApp  # noqa: E402

fila_log: queue.Queue[str] = queue.Queue()


class FilaHandler(logging.Handler):
    def emit(self, record):
        fila_log.put(self.format(record))


fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%H:%M:%S")
for h in (logging.FileHandler(os.path.join(BASE, "bot.log"), encoding="utf-8"), FilaHandler()):
    h.setFormatter(fmt)
    logging.getLogger().addHandler(h)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("gui")

# Campos do .env: (chave, rótulo, padrão, secreto)
CAMPOS = {
    "gestao": [("GESTAO_URL", "Endereço do servidor", "", False),
               ("GESTAO_CHAVE", "Chave deste sistema", "", True)],
    "whatsapp": [("EVO_URL", "URL da Evolution API", "", False),
                 ("EVO_INSTANCIA", "Instância", "", False),
                 ("EVO_KEY", "API key", "", True),
                 ("WHATSAPP_NUMEROS", "Números permitidos (vírgula)", "", False),
                 ("WHATSAPP_MENU", "Menu (botoes ou texto)", "botoes", False)],
    "telegram": [("TELEGRAM_TOKEN", "Token do bot", "", True),
                 ("ALLOWED_IDS", "IDs permitidos (vírgula)", "", False)],
    "devmaster": [("DEVMASTER_USER", "Usuário", "", False),
                  ("DEVMASTER_PASS", "Senha", "", True),
                  ("DEVMASTER_EMPRESA", "Empresa no login", "Loja/Gerencial", False),
                  ("DEVMASTER_MODULO", "Módulo no login", "Gestão Varejo Atacado", False),
                  ("DEVMASTER_ATALHO", "Atalho (opcional)", "", False)],
}
SECRETOS_SEM_TRIM = {"DEVMASTER_PASS"}   # a senha não pode perder espaços


def _estilos(raiz):
    s = ttk.Style(raiz)
    s.theme_use("clam")
    raiz.configure(bg=M.PAPEL)
    s.configure(".", background=M.PAPEL, foreground=M.NOITE, font=M.FONTE)
    s.configure("TFrame", background=M.PAPEL)
    s.configure("Card.TFrame", background=M.BRANCO)
    s.configure("TLabel", background=M.PAPEL, foreground=M.NOITE)
    s.configure("Card.TLabel", background=M.BRANCO, foreground=M.NOITE)
    s.configure("Dica.TLabel", background=M.BRANCO, foreground=M.GRAFITE)
    s.configure("Sobre.TLabel", background=M.BRANCO, foreground=M.COBALTO, font=M.FONTE_SOBRE)
    s.configure("TCheckbutton", background=M.BRANCO, foreground=M.NOITE)
    s.configure("TEntry", fieldbackground=M.BRANCO, bordercolor=M.LINHA, lightcolor=M.LINHA,
                darkcolor=M.LINHA, padding=6)
    s.map("TEntry", bordercolor=[("focus", M.COBALTO)], lightcolor=[("focus", M.COBALTO)])
    s.configure("TNotebook", background=M.PAPEL, borderwidth=0, tabmargins=(0, 8, 0, 0))
    s.configure("TNotebook.Tab", background=M.PAPEL, foreground=M.GRAFITE, padding=(14, 8),
                borderwidth=0, font=M.FONTE_FORTE)
    s.map("TNotebook.Tab", background=[("selected", M.BRANCO)], foreground=[("selected", M.COBALTO)])
    s.configure("Primario.TButton", background=M.COBALTO, foreground=M.BRANCO, borderwidth=0,
                focuscolor=M.COBALTO, padding=(14, 8), font=M.FONTE_FORTE)
    s.map("Primario.TButton", background=[("active", M.COBALTO_ESCURO), ("disabled", M.LINHA)],
          foreground=[("disabled", M.GRAFITE)])
    s.configure("Secundario.TButton", background=M.BRANCO, foreground=M.NOITE, bordercolor=M.LINHA,
                lightcolor=M.BRANCO, darkcolor=M.BRANCO, focuscolor=M.BRANCO, padding=(14, 8))
    s.map("Secundario.TButton", background=[("active", M.PAPEL), ("disabled", M.PAPEL)],
          foreground=[("disabled", M.NEVOA)], bordercolor=[("active", M.COBALTO)])


class Painel(tk.Tk):
    def __init__(self, minimizado=False):
        super().__init__()
        self.title(NOME)
        self.geometry("840x740")
        self.minsize(740, 620)
        M.carregar_fontes(self)   # Inter e Unbounded da marca
        M.definir_icone(self)     # ícone da janela e da barra de tarefas
        _estilos(self)

        self.bot: Bot | None = None
        self.zap: WhatsApp | None = None
        self.gestao: Gestao | None = None
        self.vars: dict[str, tk.StringVar] = {}
        cfg = dotenv_values(ENV) if os.path.exists(ENV) else {}
        if os.path.exists(INSTALACAO):
            cfg.update({k: v for k, v in dotenv_values(INSTALACAO).items() if k in ("GESTAO_URL", "GESTAO_CHAVE") and v})
        for grupo in CAMPOS.values():
            for chave, _, padrao, _ in grupo:
                self.vars[chave] = tk.StringVar(value=cfg.get(chave) or padrao)
        self._publicar_config()
        if os.path.exists(INSTALACAO):
            self.salvar(reconectar=False)  # guarda no .env; a gestão conecta logo abaixo
            with contextlib.suppress(OSError):
                os.remove(INSTALACAO)
            log.info("Chave do instalador aplicada.")

        self._cabecalho()
        abas = ttk.Notebook(self)
        abas.pack(fill="x", padx=16)
        abas.add(self._aba_inicio(abas), text="Início")
        abas.add(self._aba_inspecao(abas), text="Inspecionar")
        self._area_log()

        # Bandeja: fechar ou minimizar esconde a janela; o programa continua rodando
        self.bandeja = bandeja.Bandeja(self, self.sair, [("Verificar atualização", self.verificar_agora)])
        self.bandeja.iniciar()
        self.protocol("WM_DELETE_WINDOW", self.bandeja.esconder)
        self.bind("<Unmap>", self._ao_minimizar)

        self.atualizador = Atualizador(BASE, ocupado=comandos.ocupado, ao_reiniciar=lambda: self.after(0, self.sair))
        self.atualizador.ao_mudar = lambda: self.after(0, self._mostrar_atualizacao)
        threading.Thread(target=self.atualizador.run, daemon=True).start()

        self.after(200, self._puxar_log)
        self._iniciar_gestao()
        self._canais_em_uso = None
        self._reiniciar = False
        if self._tem_telegram() or self._tem_whatsapp():
            self.after(500, self.iniciar)  # inicia sozinho se já configurado
        self.after(5000, self._vigiar_canais)  # ou quando as credenciais chegarem do painel web
        if minimizado:
            self.after(100, self.bandeja.esconder)

    def _ao_minimizar(self, _e):
        if self.state() == "iconic":
            self.after_idle(self.bandeja.esconder)

    # ---------------- Layout ----------------
    def _cabecalho(self):
        topo = tk.Frame(self, bg=M.NOITE, height=72)
        topo.pack(fill="x")
        topo.pack_propagate(False)
        try:
            self._logo = tk.PhotoImage(file=str(M.LOGO_NEGATIVO))  # logo oficial (negativo)
            tk.Label(topo, image=self._logo, bg=M.NOITE).pack(side="left", padx=(20, 10))
        except Exception:
            tk.Label(topo, text="troven", bg=M.NOITE, fg=M.BRANCO, font=M.FONTE_TITULO).pack(
                side="left", padx=(20, 10))
        tk.Label(topo, text=NOME, bg=M.NOITE, fg=M.NEVOA, font=M.FONTE).pack(side="left", pady=(6, 0))
        self.lb_status = tk.Label(topo, text="● parado", bg=M.NOITE_2, fg=M.NEVOA, font=M.FONTE_FORTE,
                                  padx=12, pady=4)
        self.lb_status.pack(side="right", padx=20)

    def _card(self, pai, sobretitulo):
        f = ttk.Frame(pai, style="Card.TFrame", padding=18)
        ttk.Label(f, text="◆  " + sobretitulo, style="Sobre.TLabel").grid(row=0, column=0, columnspan=2,
                                                                          sticky="w", pady=(0, 10))
        f.columnconfigure(1, weight=1)
        return f

    def _aba_inicio(self, pai):
        f = self._card(pai, "CONTROLE")
        ttk.Label(f, text="Atende no WhatsApp e no Telegram. Ao fechar a janela, o programa continua "
                          "na bandeja do sistema (use Sair no ícone para encerrar).",
                  style="Dica.TLabel", wraplength=700).grid(row=1, column=0, columnspan=2, sticky="w")
        botoes = ttk.Frame(f, style="Card.TFrame")
        botoes.grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 8))
        self.bt_iniciar = ttk.Button(botoes, text="▶  Iniciar", style="Primario.TButton", command=self.iniciar)
        self.bt_iniciar.pack(side="left", padx=(0, 8))
        self.bt_parar = ttk.Button(botoes, text="■  Parar", style="Secundario.TButton", command=self.parar,
                                   state="disabled")
        self.bt_parar.pack(side="left", padx=(0, 8))
        ttk.Button(botoes, text="Testar estoque aqui", style="Secundario.TButton",
                   command=self.testar_estoque).pack(side="left")

        self.var_inicio = tk.BooleanVar(value=bandeja.inicio_com_windows())
        ttk.Checkbutton(f, text="Abrir junto com o Windows (já na bandeja)", variable=self.var_inicio,
                        command=self._alternar_inicio, style="TCheckbutton").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 10))

        ttk.Label(f, text=f"Versão {VERSION}", style="Card.TLabel").grid(row=4, column=0, sticky="w")
        self.lb_atualizacao = ttk.Label(f, text="Atualização: " + "ainda não verificada", style="Dica.TLabel")
        self.lb_atualizacao.grid(row=4, column=1, sticky="w")
        ttk.Button(f, text="Verificar atualização agora", style="Secundario.TButton",
                   command=self.verificar_agora).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8, 0))
        self.bt_atualizar = ttk.Button(f, text="Atualizar agora", style="Primario.TButton",
                                      command=self.atualizar_agora)
        self.bt_atualizar.grid(row=5, column=1, sticky="w", pady=(8, 0))
        self.bt_atualizar.grid_remove()
        self.lb_gestao = ttk.Label(f, text="Status: aguardando painel", style="Dica.TLabel", wraplength=700)
        self.lb_gestao.grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 0))
        return f

    def _aba_gestao(self, pai):
        f = self._aba_campos(pai, "gestao", "SERVIDOR DE GESTÃO",
                             "Com o servidor, a empresa, os comandos liberados, as credenciais do WhatsApp "
                             "e do Telegram e as pessoas permitidas vêm do painel web. O instalador já "
                             "preenche esta aba.")
        self.lb_gestao = ttk.Label(f, text="Status: não configurado", style="Dica.TLabel", wraplength=700)
        self.lb_gestao.grid(row=20, column=0, columnspan=2, sticky="w", pady=(10, 0))
        return f

    def _aba_campos(self, pai, grupo, sobretitulo, dica):
        f = self._card(pai, sobretitulo)
        linha = 1
        for chave, rotulo, _, secreto in CAMPOS[grupo]:
            ttk.Label(f, text=rotulo, style="Card.TLabel").grid(row=linha, column=0, sticky="w", padx=(0, 12),
                                                                 pady=4)
            ttk.Entry(f, textvariable=self.vars[chave], show="•" if secreto else "").grid(
                row=linha, column=1, sticky="we", pady=4)
            linha += 1
        ttk.Label(f, text=dica, style="Dica.TLabel", wraplength=700).grid(row=linha, column=0, columnspan=2,
                                                                         sticky="w", pady=(6, 0))
        ttk.Button(f, text="Salvar", style="Primario.TButton", command=self.salvar).grid(
            row=linha + 1, column=0, sticky="w", pady=(12, 0))
        return f

    def _area_log(self):
        f = ttk.Frame(self, padding=(16, 12, 16, 16))
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="REGISTRO", foreground=M.GRAFITE, font=M.FONTE_SOBRE).pack(anchor="w", pady=(0, 6))
        self.txt_log = ScrolledText(f, state="disabled", font=("Consolas", 9), bg=M.NOITE, fg=M.PAPEL,
                                    insertbackground=M.LIMA, relief="flat", borderwidth=0, padx=10, pady=8)
        self.txt_log.pack(fill="both", expand=True)
        self.txt_log.tag_config("erro", foreground="#FF8A8A")
        self.txt_log.tag_config("aviso", foreground=M.LIMA)

    # ---------------- Configuração ----------------
    def _v(self, chave) -> str:
        valor = self.vars[chave].get()
        return valor if chave in SECRETOS_SEM_TRIM else valor.strip()

    def _publicar_config(self):
        """Entrega os valores locais à configuração usada pelo robô e pelos bots."""
        valores = {c: self._v(c) for grupo in CAMPOS.values() for c, *_ in grupo}
        CONFIG.definir_local(valores)
        for chave in ("DEVMASTER_USER", "DEVMASTER_PASS", "DEVMASTER_ATALHO"):
            os.environ[chave] = valores[chave]

    @staticmethod
    def _canais():
        """Credenciais em uso (servidor de gestão por cima das deste computador)."""
        return CONFIG.evolution(), CONFIG.telegram_token()

    def _tem_telegram(self):
        return bool(CONFIG.telegram_token())

    def _tem_whatsapp(self):
        url, instancia, chave, _ = CONFIG.evolution()
        return bool(url and instancia and chave)

    def _vigiar_canais(self):
        """Aplica sozinho as credenciais que chegam do painel web: inicia ou reinicia os canais."""
        atual = self._canais()
        if atual != self._canais_em_uso:
            if self.bot or self.zap:
                log.info("Credenciais do WhatsApp/Telegram mudaram: reiniciando os canais.")
                self.parar()
                self._reiniciar = True
            elif self._tem_telegram() or self._tem_whatsapp():
                self.iniciar()
        if self._reiniciar and not (self.bot or self.zap):
            self._reiniciar = False
            self.iniciar()
        self.after(5000, self._vigiar_canais)

    def salvar(self, reconectar=True):
        with open(ENV, "w", encoding="utf-8") as fp:
            for grupo in CAMPOS.values():
                for chave, *_ in grupo:
                    fp.write(f"{chave}={self._v(chave)}\n")
        self._publicar_config()
        log.info("Configuração salva.")
        if reconectar and (self.gestao is None or (self.gestao.url, self.gestao.chave) != (
                self._v("GESTAO_URL").rstrip("/"), self._v("GESTAO_CHAVE"))):
            self._iniciar_gestao()

    # ---------------- Servidor de gestão ----------------
    def _iniciar_gestao(self):
        if self.gestao:
            self.gestao.parar()
            self.gestao = None
            CONFIG.definir_remota(None)
        url, chave = self._v("GESTAO_URL"), self._v("GESTAO_CHAVE")
        if not (url and chave):
            self._mostrar_gestao()
            return
        self.gestao = Gestao(url, chave, BASE, VERSION,
                             estado=lambda: {"whatsapp": bool(self.zap), "telegram": bool(self.bot),
                                             "ocupado": comandos.ocupado()})
        self.gestao.ao_mudar = lambda: self.after(0, self._mostrar_gestao)
        comandos.observar(self.gestao.registrar_execucao)
        threading.Thread(target=self.gestao.run, daemon=True).start()

    def _mostrar_gestao(self):
        if not self.gestao:
            texto = "Status: não configurado (usando só a configuração deste computador)"
        else:
            texto = "Status: " + self.gestao.status
            remota = CONFIG.remota
            if remota:
                nomes = ", ".join(sorted(comandos.disponiveis())) or "nenhum"
                texto += (f"\nEmpresa no DevMaster: {CONFIG.empresa_login() or '(padrão)'} · "
                          f"comandos: {nomes} · WhatsApp: {len(CONFIG.numeros_whatsapp())} números · "
                          f"Telegram: {len(CONFIG.ids_telegram())} IDs")
                origem = [n for n, campo in (("WhatsApp", ("whatsapp", "apikey")), ("Telegram", ("telegram", "token")))
                          if CONFIG._r(*campo)]
                if origem:
                    texto += f"\nCredenciais vindas do painel: {', '.join(origem)}"
        self.lb_gestao.config(text=texto)

    # ---------------- Atualização e início com o Windows ----------------
    def _mostrar_atualizacao(self):
        self.lb_atualizacao.config(text="Atualização: " + self.atualizador.status)

        if self.atualizador.pronta:
            self.bt_atualizar.grid()
        else:
            self.bt_atualizar.grid_remove()

    def atualizar_agora(self):
        if comandos.ocupado():
            messagebox.showinfo("Atualizar", "Aguarde a tarefa atual terminar e clique em Atualizar agora novamente.")
            return
        try:
            if not self.atualizador.aplicar():
                messagebox.showinfo("Atualizar", "A atualizacao ainda nao esta pronta ou ha uma tarefa em andamento.")
        except OSError as erro:
            log.exception("Falha ao iniciar a atualizacao")
            messagebox.showerror("Atualizar", str(erro))

    def verificar_agora(self):
        threading.Thread(target=self.atualizador.verificar, daemon=True).start()

    def _alternar_inicio(self):
        try:
            estado = bandeja.definir_inicio_com_windows(self.var_inicio.get())
        except OSError as e:
            estado = False
            log.error("Não consegui alterar o início com o Windows: %s", e)
        if self.var_inicio.get() and not estado:
            messagebox.showinfo("Abrir com o Windows", "Só funciona no programa instalado (.exe).")
        self.var_inicio.set(estado)

    # ---------------- Iniciar / parar ----------------
    def iniciar(self):
        if self.bot or self.zap:
            return
        if not (self._tem_telegram() or self._tem_whatsapp()):
            messagebox.showwarning("Iniciar", "Configure o WhatsApp ou o Telegram primeiro.")
            return
        self.salvar()
        self._canais_em_uso = self._canais()
        (url, instancia, chave, menu), token = self._canais_em_uso
        if token:
            try:
                self.bot = Bot(token)
                threading.Thread(target=self._rodar, args=(self.bot.run, "bot"), daemon=True).start()
            except Exception as e:
                self.bot = None
                log.error("Telegram não iniciou: %s", e)
        if url and instancia and chave:
            self.zap = WhatsApp(url, instancia, chave, menu)
            threading.Thread(target=self._rodar, args=(self.zap.run, "zap"), daemon=True).start()
        self._atualizar_status()

    def _rodar(self, alvo, atributo):
        try:
            alvo()
        except Exception:
            log.exception("Parou com erro")
        finally:
            setattr(self, atributo, None)
            self.after(0, self._atualizar_status)

    def _atualizar_status(self):
        ativos = [n for n, o in (("WhatsApp", self.zap), ("Telegram", self.bot)) if o]
        if ativos:
            self.lb_status.config(text="● " + " + ".join(ativos), fg=M.NOITE, bg=M.LIMA)
            self.bt_iniciar.config(state="disabled")
            self.bt_parar.config(state="normal")
        else:
            self.lb_status.config(text="● parado", fg=M.NEVOA, bg=M.NOITE_2)
            self.bt_iniciar.config(state="normal")
            self.bt_parar.config(state="disabled")

    def parar(self):
        if self.bot:
            self.bot.stop()
        if self.zap:
            self.zap.parar()

    def testar_estoque(self):
        if not messagebox.askyesno("Teste", "Vou operar o DevMaster agora. Não mexa no mouse. Continuar?"):
            return

        def rodar():
            try:
                arq = comandos.executar("estoque", canal="painel", solicitante="teste")
                log.info("Teste OK: %s", arq)
            except Exception:
                log.exception("Teste falhou")

        threading.Thread(target=rodar, daemon=True).start()

    # ---------------- Aba Inspeção ----------------
    def _aba_inspecao(self, pai):
        f = self._card(pai, "INSPECIONAR TELAS")
        ttk.Label(f, text="Abra a tela do DevMaster que quer mapear e clique em Capturar (5 s para abrir menus).",
                  style="Dica.TLabel").grid(row=1, column=0, columnspan=2, sticky="w")
        barra = ttk.Frame(f, style="Card.TFrame")
        barra.grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 8))
        ttk.Button(barra, text="Capturar tudo em 5s", style="Primario.TButton",
                   command=self.capturar_tudo).pack(side="left", padx=(0, 8))
        ttk.Button(barra, text="Atualizar janelas", style="Secundario.TButton",
                   command=self.listar_janelas).pack(side="left", padx=(0, 8))
        ttk.Button(barra, text="Salvar selecionada", style="Secundario.TButton",
                   command=self.salvar_controles).pack(side="left", padx=(0, 8))
        ttk.Button(barra, text="Abrir pasta", style="Secundario.TButton",
                   command=lambda: (os.makedirs(PASTA_INSPECAO, exist_ok=True), os.startfile(PASTA_INSPECAO))).pack(
            side="left")
        self.lst_janelas = tk.Listbox(f, font=("Consolas", 9), height=5, relief="flat", bg=M.PAPEL,
                                      selectbackground=M.COBALTO, highlightthickness=1, highlightcolor=M.LINHA,
                                      highlightbackground=M.LINHA)
        self.lst_janelas.grid(row=3, column=0, columnspan=2, sticky="we")
        return f

    def listar_janelas(self):
        from pywinauto import Desktop
        self.lst_janelas.delete(0, "end")
        for w in Desktop(backend="uia").windows():
            if w.window_text().strip():
                self.lst_janelas.insert("end", w.window_text())

    def _capturar(self, nome_arquivo, gravar):
        """Executa uma captura em segundo plano (uma por vez: duas juntas misturam a saída)."""
        if getattr(self, "_capturando", False):
            log.info("Já tem uma captura em andamento, aguarde.")
            return
        self._capturando = True

        def rodar():
            try:
                os.makedirs(PASTA_INSPECAO, exist_ok=True)
                caminho = os.path.join(PASTA_INSPECAO, f"{nome_arquivo}_{time.strftime('%H%M%S')}.txt")
                with open(caminho, "w", encoding="utf-8") as fp, contextlib.redirect_stdout(fp):
                    gravar()
                log.info("Captura salva: %s", caminho)
            except Exception:
                log.exception("Falha na captura")
            finally:
                self._capturando = False

        threading.Thread(target=rodar, daemon=True).start()

    def salvar_controles(self):
        sel = self.lst_janelas.curselection()
        if not sel:
            messagebox.showinfo("Inspecionar", "Selecione uma janela na lista.")
            return
        titulo = self.lst_janelas.get(sel[0])

        def gravar():
            from pywinauto import Desktop
            Desktop(backend="uia").window(title=titulo).print_control_identifiers()

        self._capturar(re.sub(r"[^\w-]+", "_", titulo)[:40], gravar)

    def capturar_tudo(self, atraso=5):
        """Salva TODAS as janelas do processo do DevMaster (inclui menus suspensos e
        diálogos, que são janelas separadas) em um único arquivo."""
        def gravar():
            from pywinauto import Desktop
            log.info("Capturando em %ss... abra o menu/tela agora.", atraso)
            time.sleep(atraso)
            d = Desktop(backend="uia")
            pid = devmaster._pid_devmaster()
            if pid is None:
                raise RuntimeError("DevMaster não está aberto.")
            for w in d.windows(process=pid):
                print(f"\n{'=' * 20} JANELA: {w.window_text()!r} ({w.element_info.control_type}) {'=' * 20}")
                try:
                    # windows() devolve wrappers; o dump só existe no "spec"
                    d.window(handle=w.handle).print_control_identifiers()
                except Exception as e:
                    print(f"(falha: {e})")

        self._capturar("tudo", gravar)

    # ---------------- Geral ----------------
    def _puxar_log(self):
        while not fila_log.empty():
            linha = fila_log.get()
            tag = "erro" if " ERROR " in linha else "aviso" if " WARNING " in linha else ""
            self.txt_log.config(state="normal")
            self.txt_log.insert("end", linha + "\n", tag)
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")
        self.after(200, self._puxar_log)

    def sair(self):
        """Encerra de verdade (o X da janela só esconde na bandeja)."""
        self.parar()
        if self.gestao:
            self.gestao.parar()
        self.atualizador.parar()
        self.bandeja.encerrar()
        self.destroy()


def main():
    minimizado = "--minimizado" in sys.argv
    holder: dict = {}
    if not bandeja.instancia_unica(lambda: holder["app"].after(0, holder["app"].bandeja.mostrar)):
        return  # já aberto: a outra instância foi chamada para a frente
    app = Painel(minimizado=minimizado)
    holder["app"] = app
    app.mainloop()


if __name__ == "__main__":
    main()

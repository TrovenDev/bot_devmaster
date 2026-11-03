"""RPA do DevMaster com pywinauto.

Fluxo do /estoque (Gestão Varejo Atacado):
Estoque > Relatórios > Saldos em Estoque - Colunas > filtros (Nome Layout = Geral,
Tab. Preços = 001) > Confirmar > seta do botão exportar > Arquivo do Excel (Xlsx)
> Enter > salva em Downloads como "Estoque Geral.xlsx".

Itens marcados com CALIBRAR dependem de como o DevMaster expõe os controles; se algum
passo falhar, use "Capturar TUDO" na aba Inspecionar com aquela tela aberta.
"""
import logging
import os
import re
import time
import threading
import queue

from pywinauto import Application, Desktop
from pywinauto.controls.hwndwrapper import HwndWrapper
from pywinauto.controls.win32_controls import ButtonWrapper

log = logging.getLogger("devmaster")

# ---------------- CONFIG ----------------
JANELA_PRINCIPAL = r"DevMaster Business.*"
MENU_ESTOQUE = "Estoque"
MENU_RELATORIOS = "Relatórios"
MENU_SALDO = "Saldos em Estoque - Colunas"
POSICAO_SALDO = 5   # posição dele no submenu Relatórios (1 = Relação de Produtos)
JANELA_FILTROS = r".*Parâmetros.*"            # "rel:relEst901 - Parâmetros"
LAYOUT = "Geral"
TAB_PRECOS = "001"
ITEM_EXPORTAR = "Arquivo do Excel (Xlsx)"
ABA_RELATORIO = r"Relatório de Saldos em Estoque.*"
NOME_ARQUIVO = "Estoque Geral.xlsx"
PASTA_SAIDA = os.path.join(os.path.expanduser("~"), "Downloads")
TIMEOUT = 90
# ----------------------------------------


def _desktop():
    return Desktop(backend="uia")


def _conectar():
    app = Application(backend="uia").connect(title_re=JANELA_PRINCIPAL, timeout=15)
    janela = app.window(title_re=JANELA_PRINCIPAL)
    janela._devmaster_pid = app.process
    if janela.is_minimized():
        janela.restore()
    return janela


def _processo(janela):
    if isinstance(janela, int):
        return janela
    return vars(janela).get("_devmaster_pid") or janela.process_id()


def _achar(janela, timeout=10, **criterios):
    """Procura um controle em TODAS as janelas do processo do DevMaster (menus
    suspensos, diálogos e a janela principal são janelas separadas). `janela` pode
    ser uma janela ou o número do processo (pid)."""
    criterios.setdefault("found_index", 0)  # se houver vários iguais, pega o primeiro
    pid = _processo(janela)
    d = _desktop()
    fim = time.time() + timeout
    while time.time() < fim:
        for w in d.windows(process=pid):
            # windows() devolve wrappers; child_window só existe no "spec"
            c = d.window(handle=w.handle).child_window(**criterios)
            if c.exists(timeout=0.3):
                return c
        time.sleep(0.3)
    # Ajuda no diagnóstico: lista os itens de menu visíveis no momento
    vistos = []
    for w in d.windows(process=pid):
        try:
            vistos += [m.window_text() for m in w.descendants(control_type="MenuItem")]
        except Exception:
            pass
    raise RuntimeError(f"Controle não encontrado: {criterios}. Itens de menu visíveis: {vistos}")


def _clicar(ctrl):
    """Aciona o controle sem cursor e sem alterar o foco global."""
    for acao in (lambda: ctrl.invoke(), lambda: ctrl.iface_selection_item.Select(),
                 lambda: ctrl.iface_toggle.Toggle(), lambda: ctrl.iface_expand_collapse.Expand(),
                 lambda: ctrl.iface_legacy_iaccessible.DoDefaultAction()):
        try:
            acao()
            return
        except Exception:
            pass
    try:
        if ctrl.element_info.control_type == "Button" and ctrl.handle:
            ButtonWrapper(ctrl.handle).click()
            return
    except Exception:
        pass
    raise RuntimeError("Este controle nao oferece acao sem mouse. Capture a tela pela aba Inspecionar para ajustar a automacao.")


def _abrir_dialogo(janela, origem, destino, timeout=20):
    """Invoke pode esperar o fechamento do modal: nunca bloquear quem deve confirma-lo."""
    pid = _processo(janela)
    falhas = queue.Queue()
    def acionar():
        import pythoncom
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)
        try:
            # Resolver o controle na propria thread evita reutilizar interfaces COM de outra thread.
            _clicar(_achar(pid, timeout=5, **origem))
        except Exception as erro:
            falhas.put(erro)
        finally:
            pythoncom.CoUninitialize()
    threading.Thread(target=acionar, daemon=True).start()
    fim = time.monotonic() + timeout
    while time.monotonic() < fim:
        try:
            return _achar(pid, timeout=1, **destino)
        except RuntimeError:
            if not falhas.empty():
                raise RuntimeError("Falha ao abrir a proxima janela do relatorio.") from falhas.get()
    raise TimeoutError("A proxima janela do relatorio nao apareceu apos o acionamento.")


def _escrever(ctrl, texto):
    """Preenche pelo ValuePattern, sem teclado global (inclusive senha)."""
    for acao in (lambda: ctrl.iface_value.SetValue(str(texto)), lambda: ctrl.set_edit_text(str(texto))):
        try:
            acao()
            return
        except Exception:
            pass
    raise RuntimeError("Campo sem suporte a preenchimento direto; requer ajuste pela aba Inspecionar.")


def _teclas(ctrl, teclas):
    """Envia mensagens de teclado apenas ao HWND alvo, sem SendInput/foco."""
    try:
        if not ctrl.handle:
            raise ValueError("Controle sem HWND")
        HwndWrapper(ctrl.handle).send_keystrokes(teclas)
    except Exception as erro:
        raise RuntimeError("Controle nao aceita teclas em segundo plano; requer ajuste pela aba Inspecionar.") from erro


def _pid_devmaster():
    """Processo do DevMaster: qualquer janela com 'devmaster' no título (o nome do
    sistema pode mudar, mas sempre tem 'devmaster')."""
    # Exige o formulário do sistema (auto_id FormPrincipal, usado no login e no menu):
    # só o título pegaria também uma pasta "DevMaster" aberta no Explorer, ou este painel.
    for w in _desktop().windows():
        try:
            if ("devmaster" in w.window_text().lower()
                    and w.element_info.automation_id == "FormPrincipal"
                    and w.process_id() != os.getpid()):
                return w.process_id()
        except Exception:
            pass
    return None


def _no_menu_principal(pid):
    """True quando o sistema já está logado (a barra de menus 'Programa' existe)."""
    try:
        _achar(pid, timeout=1, title="Programa", control_type="MenuItem")
        return True
    except RuntimeError:
        return False


def _atalho_do_sistema(caminho):
    nome = os.path.basename(caminho).casefold()
    return (nome.endswith((".lnk", ".appref-ms", ".url", ".exe"))
            and "devmaster" in nome
            and not any(termo in nome for termo in ("bot", "setup", "instalador")))


def _achar_atalho():
    """Atalho do DevMaster: o configurado ou um .lnk com 'devmaster' no nome na
    Área de Trabalho / Menu Iniciar."""
    manual = os.environ.get("DEVMASTER_ATALHO", "").strip().strip('"')
    if manual and _atalho_do_sistema(manual) and os.path.isfile(manual):
        return manual
    if manual:
        log.warning("Atalho configurado ignorado: nao corresponde ao sistema DevMaster.")
    pastas = [
        _pasta_windows(0x10),  # Área de Trabalho real do usuário (inclui OneDrive)
        _pasta_windows(0x19),  # Área de Trabalho pública
        os.path.join(os.path.expanduser("~"), "Desktop"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
        os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Desktop"),
    ]
    extensoes = (".lnk", ".appref-ms", ".url", ".exe")  # .appref-ms = instalação ClickOnce
    olhadas = []
    for pasta in pastas:
        if not pasta or pasta in olhadas or not os.path.isdir(pasta):
            continue
        olhadas.append(pasta)
        for raiz, _, arquivos in os.walk(pasta):
            for nome in sorted(arquivos, key=lambda n: (os.path.splitext(n)[0].casefold() != "devmaster", n.casefold())):
                if _atalho_do_sistema(nome):
                    return os.path.join(raiz, nome)
    raise RuntimeError("Atalho do DevMaster não encontrado em: " + "; ".join(olhadas)
                       + ". Crie na area de trabalho um atalho chamado DevMaster para o sistema.")


def _pasta_windows(csidl):
    """Caminho de uma pasta especial do Windows (ex.: Área de Trabalho)."""
    import ctypes
    buf = ctypes.create_unicode_buffer(260)
    try:
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
            return buf.value
    except Exception:
        pass
    return ""


def _valor(ctrl):
    """Texto atual de um campo de edição (vazio se não for possível ler)."""
    for ler in (lambda: ctrl.get_value(), lambda: ctrl.iface_value.CurrentValue,
                lambda: ctrl.window_text()):
        try:
            v = ler()
            if v:
                return str(v)
        except Exception:
            pass
    return ""


def _selecionar_combo(pid, auto_id, desejado):
    """Escolhe uma opção de um combo da tela de login (ex.: a empresa). Não mexe se já
    está selecionada; sem valor desejado mantém o que o sistema trouxe."""
    if not desejado:
        return
    combo = _achar(pid, timeout=5, auto_id=auto_id, control_type="ComboBox")
    if desejado.lower() in _valor_combo(combo).lower():
        return
    log.info("  selecionando %r (%s)", desejado, auto_id)
    _clicar(combo)
    time.sleep(0.6)
    try:
        _clicar(_achar(pid, timeout=3, title=desejado))  # opção da lista aberta
    except RuntimeError:
        _escrever(combo, desejado)
        _teclas(combo, "{ENTER}")
    time.sleep(0.5)
    if desejado.lower() not in _valor_combo(combo).lower():
        log.warning("  não consegui confirmar a seleção de %r; seguindo com o valor atual.", desejado)


def _login(pid, empresa="", modulo=""):
    """Tela 1: usuário e senha, sem Lembrar-me / Salvar minha senha, e LOGIN.
    Tela 2: empresa (ex.: Loja/Gerencial) e módulo (Gestão Varejo Atacado) e LOGIN.
    Ambas são a mesma janela; o botão LOGIN tem o mesmo auto_id (btnAvancar)."""
    usuario = os.environ.get("DEVMASTER_USER", "")
    senha = os.environ.get("DEVMASTER_PASS", "")
    if not usuario or not senha:
        raise RuntimeError("Informe o usuário e a senha do DevMaster no painel.")

    fim = time.time() + TIMEOUT
    tela1_feita = False
    while time.time() < fim:
        if _no_menu_principal(pid):
            return
        try:
            campo_usuario = _achar(pid, timeout=2, auto_id="textUsuario", control_type="Edit")
        except RuntimeError:
            campo_usuario = None

        if campo_usuario is not None and not tela1_feita:
            log.info("  tela de login: usuário e senha")
            # "Lembrar-me" / "Salvar minha senha" são desenhos sem estado legível. Quando o
            # usuário já vem preenchido é porque ficaram marcados na vez anterior: clica
            # para desmarcar. (Sem usuário preenchido já estão desmarcados.)
            marcado = bool(_valor(campo_usuario).strip())
            _escrever(campo_usuario, usuario)
            campo_senha = _achar(pid, timeout=5, auto_id="textSenha", control_type="Edit")
            _escrever(campo_senha, senha)
            if marcado:
                for caixa in ("pictureBoxLembrarMe", "pictureBoxSalvarSenha"):
                    _clicar(_achar(pid, timeout=5, auto_id=caixa))
                log.info("  desmarcou Lembrar-me e Salvar minha senha")
            _clicar(_achar(pid, timeout=10, auto_id="btnAvancar", control_type="Button"))
            tela1_feita = True
            time.sleep(2)
        elif campo_usuario is None:
            try:  # tela 2: empresa e módulo, depois confirma
                botao = _achar(pid, timeout=2, auto_id="btnAvancar", control_type="Button")
                _selecionar_combo(pid, "lookUpEditEmpresa", empresa)
                _selecionar_combo(pid, "lookUpEditModulo", modulo)
                _clicar(botao)
                log.info("  tela de login: empresa e módulo confirmados")
                time.sleep(3)
            except RuntimeError:
                time.sleep(1)
        else:
            time.sleep(1)
    raise TimeoutError("O DevMaster não chegou ao menu principal depois do login.")


def _abrir_sistema(empresa="", modulo=""):
    """Abre o DevMaster (se já estiver aberto, reaproveita) e faz o login.
    Devolve (janela principal, True se fomos nós que abrimos)."""
    pid = _pid_devmaster()
    fomos_nos = False
    if pid is None:
        atalho = _achar_atalho()
        log.info("  abrindo o DevMaster: %s", atalho)
        os.startfile(atalho)
        fomos_nos = True
        fim = time.time() + TIMEOUT
        while pid is None and time.time() < fim:
            time.sleep(1)
            pid = _pid_devmaster()
        if pid is None:
            raise TimeoutError("O DevMaster não abriu.")
        time.sleep(3)
    _login(pid, empresa, modulo)
    return _conectar(), fomos_nos


def _sair_do_sistema(janela):
    """Programa > Sair. Se houver abas abertas aparece uma mensagem: Sim."""
    pid = janela.process_id()
    _clicar_menu(janela, "Programa")
    # Os itens do menu Programa aparecem como botões dentro de um "Menu" suspenso
    # (não como MenuItem); busca o "Sair" dentro dele para não pegar o Sair do relatório.
    menu = _achar(pid, timeout=5, control_type="Menu")
    _clicar(menu.child_window(title="Sair", control_type="Button"))
    log.info("  Programa > Sair")
    try:
        _clicar(_achar(pid, timeout=5, title_re=r"(?i)^&?sim$", control_type="Button"))
        log.info("  confirmou o aviso de abas abertas (Sim)")
    except Exception:
        pass  # sem aviso: o sistema já saiu


def _regex_texto(nome):
    # Tolera hífen/traço diferente, espaços extras e o "&" de atalho do menu
    partes = [re.escape(p) for p in re.split(r"\s*-\s*|\s+", nome) if p]
    return r"^\s*&?" + r"[\s\-–—&]*".join(partes) + r"\s*$"


def _clicar_menu(janela, nome):
    _clicar(_achar(janela, title_re=_regex_texto(nome), control_type="MenuItem"))
    time.sleep(0.8)


def _aguardar_filtros(janela, timeout=8):
    """O clique so terminou quando o campo especifico do relatorio apareceu."""
    try:
        _achar(janela, timeout=timeout, auto_id="edit_nome_layout", control_type="ComboBox")
        return True
    except RuntimeError:
        return False


def _ativar_favorito(card):
    # SelectionItem.Select apenas seleciona o card; nao abre o relatorio.
    for acao in (lambda: card.invoke(), lambda: card.iface_legacy_iaccessible.DoDefaultAction()):
        try:
            acao()
            return
        except Exception:
            pass
    raise RuntimeError("Favorito nao oferece acao de abertura sem mouse.")


def _abrir_relatorio(janela):
    if _aguardar_filtros(janela, timeout=1):
        return
    try:
        _clicar(_achar(janela, timeout=3, title="Menu", control_type="TabItem"))
        card = _achar(janela, timeout=5, title_re=r"^" + re.escape(MENU_SALDO) + r"(?:,.*)?$", control_type="ListItem")
        _ativar_favorito(card)
        if _aguardar_filtros(janela):
            log.info("  filtros do relatorio confirmados via Favoritos")
            return
        log.warning("Favorito acionado, mas filtros nao apareceram; tentando menu Estoque.")
    except RuntimeError as erro:
        log.info("  tentando abrir pelo menu Estoque: %s", erro)
    _clicar_menu(janela, MENU_ESTOQUE)
    _clicar_menu(janela, MENU_RELATORIOS)
    try:
        item = _achar(janela, timeout=3, title_re=_regex_texto(MENU_SALDO))
        _clicar(item)
    except RuntimeError:
        _teclas(_achar(janela, control_type="Menu"), "{RIGHT}{DOWN %d}{ENTER}" % (POSICAO_SALDO - 1))
    if not _aguardar_filtros(janela, timeout=15):
        raise RuntimeError("O relatorio Saldos em Estoque - Colunas nao abriu: campo Nome Layout ausente. Capture os controles em Inspecionar com o menu/relatorio aberto.")
    log.info("  filtros do relatorio confirmados via menu Estoque")


def _valor_combo(combo):
    """Texto atual de um combo (o DevMaster não o expõe como título)."""
    for tentativa in (lambda: combo.selected_text(), lambda: combo.get_value(),
                      lambda: combo.iface_value.CurrentValue, lambda: combo.window_text()):
        try:
            v = tentativa()
            if v:
                return str(v)
        except Exception:
            pass
    return ""


def _preencher_filtros(janela):
    # A tela de filtros é uma janela filha da principal (auto_id "ucForm"), não uma
    # janela de nível superior, e os campos têm auto_id próprio.
    filtros = janela.child_window(auto_id="ucForm", control_type="Window")
    filtros.wait("exists", timeout=15)

    # Nome Layout: se já está em "Geral" não mexe; senão abre a lista e escolhe
    combo = filtros.child_window(auto_id="edit_nome_layout", control_type="ComboBox")
    if LAYOUT.lower() not in _valor_combo(combo).lower():
        _clicar(combo)
        time.sleep(0.6)
        try:
            _clicar(_achar(janela, timeout=3, title=LAYOUT))
        except RuntimeError:
            _escrever(combo, LAYOUT)
            _teclas(combo, "{ENTER}")
        time.sleep(0.4)

    # Tab. Preços: sempre 001 (seleciona tudo e digita por cima)
    preco = filtros.child_window(auto_id="edit_tab_preco", control_type="Edit")
    _escrever(preco, TAB_PRECOS)
    _teclas(preco, "{TAB}")

    _clicar(filtros.child_window(title="Confirmar", control_type="Button"))
    # Espera a tela de filtros fechar (o relatório começa a ser gerado)
    fim = time.time() + TIMEOUT
    while time.time() < fim and filtros.exists(timeout=0.5):
        time.sleep(0.5)


def _exportar_xlsx(janela, destino):
    time.sleep(3)  # deixa o relatório terminar de montar

    # Seta (dropdown) ao lado do botão de exportar. CALIBRAR: ajuste o título se
    # o botão tiver outro nome na captura.
    log.info("  clicando na setinha de exportar")
    botao = _achar(janela, timeout=TIMEOUT, title="Exportar Relatório", control_type="SplitButton")
    # a setinha é o botão filho "Abrir" do SplitButton
    _clicar(botao.child_window(title="Abrir", control_type="Button"))
    time.sleep(0.6)

    log.info("  escolhendo %s", ITEM_EXPORTAR)
    _abrir_dialogo(janela, {"title": ITEM_EXPORTAR},
                   {"auto_id": "btnOK", "control_type": "Button"})
    log.info("  confirmando as opcoes de exportacao (OK)")
    dlg = _abrir_dialogo(janela, {"auto_id": "btnOK", "control_type": "Button"},
                         {"title_re": r"(?i)salvar como|save as", "control_type": "Window"})
    log.info("  janela Salvar Como confirmada")
    nome = dlg.child_window(auto_id="1001", control_type="Edit")
    _escrever(nome, destino)
    _teclas(nome, "{TAB}")
    time.sleep(0.5)
    # window_text() devolve o rótulo ("Nome:"), não o conteúdo: lê o valor do campo
    digitado = ""
    for ler in (lambda: nome.get_value(), lambda: nome.iface_value.CurrentValue,
                lambda: nome.legacy_properties().get("Value")):
        try:
            digitado = ler() or ""
            if digitado:
                break
        except Exception:
            pass
    log.info("  campo Nome: %r", digitado)
    if digitado and os.path.normcase(digitado.strip()) != os.path.normcase(destino):
        raise RuntimeError(f"Não consegui preencher o nome na janela Salvar Como (ficou {digitado!r}).")
    log.info("  clicando em Salvar")
    _clicar(dlg.child_window(title_re=r"(?i)^&?salvar$|^&?save$", control_type="Button"))

    # Se o arquivo antigo não pôde ser apagado, o Windows pergunta se substitui: Sim
    try:
        aviso = _achar(janela, timeout=3, title_re=r"(?i)confirmar|confirm", control_type="Window")
        _clicar(aviso.child_window(title_re=r"(?i)^&?(sim|yes)$", control_type="Button"))
    except RuntimeError:
        pass

    # Depois de salvar o DevMaster pergunta "Você quer abrir este arquivo?": Não
    try:
        aviso = _achar(janela, timeout=30, title="Exportar", control_type="Window")
        _clicar(aviso.child_window(title="Não", control_type="Button"))
        log.info("  respondeu Não a 'Você quer abrir este arquivo?'")
    except RuntimeError:
        log.warning("  janela 'Você quer abrir este arquivo?' não encontrada")


def _fechar_relatorio(janela):
    """Fecha o relatório (botão vermelho 'Sair' da barra), para não acumular abas."""
    try:
        _clicar(_achar(janela, timeout=5, title="Sair", control_type="Button"))
        log.info("relatório fechado")
    except RuntimeError:
        log.warning("botão Sair (fechar relatório) não encontrado")


def _nome_seguro(nome):
    """Nome do arquivo vindo da configuração: só o nome (sem pastas) e terminado em .xlsx."""
    base = re.sub(r'[<>:"/\|?*]+', "", os.path.basename(nome or "").strip()) or NOME_ARQUIVO
    return base if base.lower().endswith(".xlsx") else base + ".xlsx"


def gerar_estoque(empresa="", modulo="", nome_arquivo="") -> str:
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    destino = os.path.join(PASTA_SAIDA, _nome_seguro(nome_arquivo))
    if os.path.exists(destino):
        try:
            os.remove(destino)  # substitui o anterior; evita o aviso de "substituir"
        except OSError:
            pass  # em uso (ex.: aberto no Excel): o "Sim" do aviso cobre esse caso

    log.info("1/5 abrindo o DevMaster e fazendo login")
    janela, fomos_nos = _abrir_sistema(empresa, modulo)
    try:
        log.info("2/5 abrindo o relatório (Favoritos)")
        _abrir_relatorio(janela)
        log.info("3/5 preenchendo os filtros")
        _preencher_filtros(janela)
        log.info("4/5 exportando para %s", destino)
        _exportar_xlsx(janela, destino)
        log.info("exportação concluída; aguardando o arquivo")

        # Espera o arquivo aparecer e parar de crescer
        fim = time.time() + TIMEOUT
        tamanho = -1
        while time.time() < fim:
            if os.path.exists(destino):
                atual = os.path.getsize(destino)
                if atual > 0 and atual == tamanho:
                    return destino
                tamanho = atual
            time.sleep(1.5)
        raise TimeoutError(f"O arquivo não apareceu em {destino}.")
    finally:
        try:
            _fechar_relatorio(janela)
        except Exception:
            log.warning("Falha na limpeza do relatorio; preservando o erro original.", exc_info=True)
        if fomos_nos:  # só fecha o sistema se foi o robô que abriu
            log.info("5/5 saindo do DevMaster")
            try:
                _sair_do_sistema(janela)
            except Exception:
                log.exception("Não consegui sair do DevMaster")

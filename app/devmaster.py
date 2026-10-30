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

from pywinauto import Application, Desktop, mouse
from pywinauto.keyboard import send_keys

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
    if janela.is_minimized():
        janela.restore()
    janela.set_focus()
    return janela


def _achar(janela, timeout=10, **criterios):
    """Procura um controle em TODAS as janelas do processo do DevMaster (menus
    suspensos, diálogos e a janela principal são janelas separadas). `janela` pode
    ser uma janela ou o número do processo (pid)."""
    criterios.setdefault("found_index", 0)  # se houver vários iguais, pega o primeiro
    pid = janela if isinstance(janela, int) else janela.process_id()
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


def _digitar(texto):
    """Digita no campo em foco (escapa os caracteres especiais do send_keys)."""
    send_keys("".join("{" + ch + "}" if ch in "+^%~(){}[]" else ch for ch in texto),
              with_spaces=True, pause=0.02)


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
    combo.click_input()
    time.sleep(0.6)
    try:
        _achar(pid, timeout=3, title=desejado).click_input()  # opção da lista aberta
    except RuntimeError:
        send_keys("^a")  # lista não exposta: digita o nome e confirma
        _digitar(desejado)
        send_keys("{ENTER}")
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
            campo_usuario.click_input()
            send_keys("^a{BACKSPACE}")
            _digitar(usuario)
            campo_senha = _achar(pid, timeout=5, auto_id="textSenha", control_type="Edit")
            campo_senha.click_input()
            send_keys("^a{BACKSPACE}")
            _digitar(senha)
            if marcado:
                for caixa in ("pictureBoxLembrarMe", "pictureBoxSalvarSenha"):
                    _achar(pid, timeout=5, auto_id=caixa).click_input()
                log.info("  desmarcou Lembrar-me e Salvar minha senha")
            _achar(pid, timeout=10, auto_id="btnAvancar", control_type="Button").click_input()
            tela1_feita = True
            time.sleep(2)
        elif campo_usuario is None:
            try:  # tela 2: empresa e módulo, depois confirma
                botao = _achar(pid, timeout=2, auto_id="btnAvancar", control_type="Button")
                _selecionar_combo(pid, "lookUpEditEmpresa", empresa)
                _selecionar_combo(pid, "lookUpEditModulo", modulo)
                botao.click_input()
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
    menu.child_window(title="Sair", control_type="Button").click_input()
    log.info("  Programa > Sair")
    try:
        _achar(pid, timeout=5, title_re=r"(?i)^&?sim$", control_type="Button").click_input()
        log.info("  confirmou o aviso de abas abertas (Sim)")
    except Exception:
        pass  # sem aviso: o sistema já saiu


def _regex_texto(nome):
    # Tolera hífen/traço diferente, espaços extras e o "&" de atalho do menu
    partes = [re.escape(p) for p in re.split(r"\s*-\s*|\s+", nome) if p]
    return r"^\s*&?" + r"[\s\-–—&]*".join(partes) + r"\s*$"


def _clicar_menu(janela, nome):
    _achar(janela, title_re=_regex_texto(nome), control_type="MenuItem").click_input()
    time.sleep(0.8)


def _abrir_relatorio(janela):
    """Abre o relatório pelo card em Favoritos (aba Menu). Se não achar o card,
    cai no caminho Estoque > Relatórios, entrando no submenu pelo teclado (os itens
    do submenu Relatórios não aparecem para a automação)."""
    try:
        _achar(janela, timeout=3, title="Menu", control_type="TabItem").click_input()
        time.sleep(1)
        card = _achar(janela, timeout=8, title_re=r"^" + re.escape(MENU_SALDO) + r",.*",
                      control_type="ListItem")
        card.click_input()
    except RuntimeError:
        _clicar_menu(janela, MENU_ESTOQUE)
        _clicar_menu(janela, MENU_RELATORIOS)
        send_keys("{RIGHT}{DOWN %d}{ENTER}" % (POSICAO_SALDO - 1))
    time.sleep(1)


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
    filtros.wait("visible", timeout=TIMEOUT)

    # Nome Layout: se já está em "Geral" não mexe; senão abre a lista e escolhe
    combo = filtros.child_window(auto_id="edit_nome_layout", control_type="ComboBox")
    if LAYOUT.lower() not in _valor_combo(combo).lower():
        combo.click_input()
        time.sleep(0.6)
        try:
            _achar(janela, timeout=3, title=LAYOUT).click_input()
        except RuntimeError:
            send_keys(LAYOUT + "{ENTER}")  # lista não exposta: digita o valor
        time.sleep(0.4)

    # Tab. Preços: sempre 001 (seleciona tudo e digita por cima)
    preco = filtros.child_window(auto_id="edit_tab_preco", control_type="Edit")
    preco.click_input()
    send_keys("^a" + TAB_PRECOS + "{TAB}")

    filtros.child_window(title="Confirmar", control_type="Button").click_input()
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
    botao.child_window(title="Abrir", control_type="Button").click_input()
    time.sleep(0.6)

    log.info("  escolhendo %s", ITEM_EXPORTAR)
    _achar(janela, title=ITEM_EXPORTAR).click_input()
    # Depois de escolher o formato abre "Opções de Exportação XLSX": OK (o Enter do
    # passo a passo manual) antes de abrir a janela "Salvar Como".
    log.info("  confirmando as opções de exportação (OK)")
    _achar(janela, timeout=15, auto_id="btnOK", control_type="Button").click_input()

    # Janela "Salvar Como": espera abrir, preenche o caminho completo no campo Nome
    # (sobrepõe a pasta que ela abriu) e clica em Salvar.
    log.info("  aguardando a janela Salvar Como")
    dlg = _achar(janela, timeout=20, title_re=r"(?i)salvar como|save as", control_type="Window")
    dlg.set_focus()
    nome = dlg.child_window(auto_id="1001", control_type="Edit")
    # Digita pelo teclado: preencher o campo "por baixo" (set_edit_text) muda o texto
    # mas a janela salva com o nome antigo (relEst901_G) na pasta que estava aberta.
    nome.click_input()
    send_keys("^a{BACKSPACE}")
    escapado = "".join("{" + ch + "}" if ch in "+^%~(){}[]" else ch for ch in destino)
    send_keys(escapado, with_spaces=True, pause=0.02)
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
    dlg.child_window(title_re=r"(?i)^&?salvar$|^&?save$", control_type="Button").click_input()

    # Se o arquivo antigo não pôde ser apagado, o Windows pergunta se substitui: Sim
    try:
        aviso = _achar(janela, timeout=3, title_re=r"(?i)confirmar|confirm", control_type="Window")
        aviso.child_window(title_re=r"(?i)^&?(sim|yes)$", control_type="Button").click_input()
    except RuntimeError:
        pass

    # Depois de salvar o DevMaster pergunta "Você quer abrir este arquivo?": Não
    try:
        aviso = _achar(janela, timeout=30, title="Exportar", control_type="Window")
        aviso.child_window(title="Não", control_type="Button").click_input()
        log.info("  respondeu Não a 'Você quer abrir este arquivo?'")
    except RuntimeError:
        log.warning("  janela 'Você quer abrir este arquivo?' não encontrada")


def _fechar_relatorio(janela):
    """Fecha o relatório (botão vermelho 'Sair' da barra), para não acumular abas."""
    try:
        _achar(janela, timeout=5, title="Sair", control_type="Button").click_input()
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
        _fechar_relatorio(janela)
        if fomos_nos:  # só fecha o sistema se foi o robô que abriu
            log.info("5/5 saindo do DevMaster")
            try:
                _sair_do_sistema(janela)
            except Exception:
                log.exception("Não consegui sair do DevMaster")

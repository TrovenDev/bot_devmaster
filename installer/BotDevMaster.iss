; Instalador do Bot DevMaster (identidade Troven). Gerado por scripts/build_windows.py com o Inno Setup 6:
;   iscc /DVersao=1.0.0 installer\BotDevMaster.iss
;
; Instala por usuário (sem pedir administrador) em %LOCALAPPDATA%\Programs\Troven\Bot DevMaster: o programa grava o
; .env ao lado do .exe e o atualizador troca o .exe sozinho, então a pasta precisa ser do usuário.
; A chave vem embutida (o painel web gera o instalador de cada sistema); WhatsApp, Telegram, comandos e contatos
; vêm do painel. Sem chave embutida: Setup.exe [/VERYSILENT] /CHAVE=dmb_... /PAINEL=https://...

#ifndef Versao
  #define Versao "0.0.0"
#endif

#define Nome "Bot DevMaster"
#define Exe "DevMasterBot.exe"

[Setup]
AppId={{1589BBB0-72B9-4EEB-989B-0EA3444BD843}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher=Troven
AppPublisherURL=https://troven.com.br
VersionInfoCompany=Troven
VersionInfoProductName={#Nome}
VersionInfoVersion={#Versao}
DefaultDirName={localappdata}\Programs\Troven\{#Nome}
DefaultGroupName=Troven
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=BotDevMaster-Setup
SetupIconFile=..\app\assets\troven-app.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nome} (Troven)
WizardStyle=modern
WizardImageFile=..\build\instalador\lateral.bmp,..\build\instalador\lateral@2x.bmp
WizardSmallImageFile=..\build\instalador\icone.bmp,..\build\instalador\icone@2x.bmp
WizardImageStretch=no
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
pt.WelcomeLabel1=Bem-vindo ao [name]
pt.WelcomeLabel2=Este assistente instala o [name/ver], da Troven.%n%nEste instalador já traz a chave do seu sistema: o WhatsApp, o Telegram e os comandos são configurados pelo painel e o programa se atualiza sozinho.

[Tasks]
Name: "inicio"; Description: "Abrir junto com o Windows (já na bandeja)"
Name: "atalho"; Description: "Criar atalho na área de trabalho"

[Files]
Source: "..\dist\{#Exe}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Troven\{#Nome}"; Filename: "{app}\{#Exe}"
Name: "{userdesktop}\{#Nome}"; Filename: "{app}\{#Exe}"; Tasks: atalho

[Registry]
; mesmo valor que o painel usa em "Abrir junto com o Windows" (app/bandeja.py)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BotDevMaster"; \
  ValueData: """{app}\{#Exe}"" --minimizado"; Tasks: inicio; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#Exe}"; Description: "Abrir o {#Nome} agora"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#Exe}"; Parameters: "--minimizado"; Flags: nowait skipifnotsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#Exe}"; Flags: runhidden; RunOnceId: "FecharBot"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\atualizacoes"
Type: files; Name: "{app}\instalacao.env"

[Code]
// A chave vem embutida: o painel anexa ao fim deste Setup.exe a linha  <marca>endereço|chave<marca>
// (o painel gera o instalador de cada sistema no navegador). Sem isso, pergunta a chave.
var
  PaginaChave: TInputQueryWizardPage;
  Embutido: Boolean;
  UrlPainel, ChaveSistema: String;

function Marca: String;
begin
  Result := '#DMB' + 'KEY#';   // montada em partes para não aparecer inteira dentro do executável
end;

function LerEmbutido: Boolean;
var
  Bruto: AnsiString;
  Cauda, Dados: String;
  Fim, Ini, Barra: Integer;
begin
  Result := False;
  if not LoadStringFromFile(ExpandConstant('{srcexe}'), Bruto) then Exit;
  Cauda := Copy(Bruto, Length(Bruto) - 599, 600);
  Cauda := TrimRight(Cauda);
  Fim := Length(Cauda) - Length(Marca) + 1;          // a marca final fecha o trecho
  if (Fim < 1) or (Copy(Cauda, Fim, Length(Marca)) <> Marca) then Exit;
  Cauda := Copy(Cauda, 1, Fim - 1);
  Ini := Length(Cauda) - Length(Marca) + 1;          // procura a marca de abertura
  while (Ini > 0) and (Copy(Cauda, Ini, Length(Marca)) <> Marca) do Ini := Ini - 1;
  if Ini < 1 then Exit;
  Dados := Copy(Cauda, Ini + Length(Marca), Length(Cauda));
  Barra := Pos('|', Dados);
  if Barra = 0 then Exit;
  UrlPainel := Copy(Dados, 1, Barra - 1);
  ChaveSistema := Copy(Dados, Barra + 1, Length(Dados));
  Result := True;
end;

function ChaveValida(const Chave: String): Boolean;
var
  I: Integer;
begin
  Result := (Length(Chave) = 68) and (Copy(Chave, 1, 4) = 'dmb_');
  if Result then
    for I := 5 to 68 do
      if Pos(Chave[I], '0123456789abcdef') = 0 then
      begin
        Result := False;
        Exit;
      end;
end;

function UrlValida(const Url: String): Boolean;
begin
  Result := (Pos('https://', Lowercase(Url)) = 1) or (Pos('http://', Lowercase(Url)) = 1);
end;

function JaTemChave: Boolean;
var
  Env: AnsiString;
begin
  Result := LoadStringFromFile(AddBackslash(WizardDirValue) + '.env', Env) and (Pos('GESTAO_CHAVE=dmb_', Env) > 0);
end;

procedure InitializeWizard;
begin
  Embutido := LerEmbutido and ChaveValida(ChaveSistema) and UrlValida(UrlPainel);
  if Embutido then Exit;
  UrlPainel := ExpandConstant('{param:PAINEL|}');
  ChaveSistema := ExpandConstant('{param:CHAVE|}');
  PaginaChave := CreateInputQueryPage(wpSelectTasks, 'Chave do sistema',
    'Liga este computador ao painel de gestão da Troven.',
    'Este instalador não veio com a chave. Baixe-o de novo pelo painel (já vem pronto) ou cole aqui a chave ' +
    'do sistema, que começa com dmb_. Reinstalando? Deixe em branco para manter a chave atual.');
  PaginaChave.Add('Chave do sistema:', False);
  PaginaChave.Add('Endereço do painel:', False);
  PaginaChave.Values[0] := ChaveSistema;
  PaginaChave.Values[1] := UrlPainel;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (not Embutido) and WizardSilent and (PageID = PaginaChave.ID);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (not Embutido) and (CurPageID = PaginaChave.ID) then
  begin
    ChaveSistema := Trim(PaginaChave.Values[0]);
    UrlPainel := Trim(PaginaChave.Values[1]);
    if (ChaveSistema = '') and JaTemChave then Exit;
    if not ChaveValida(ChaveSistema) then
    begin
      MsgBox('Chave inválida. Copie a chave completa do painel (dmb_ seguido de 64 letras e números).', mbError, MB_OK);
      Result := False;
    end
    else if not UrlValida(UrlPainel) then
    begin
      MsgBox('Informe o endereço do painel, começando com https://', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  Result := '';
  // fecha o programa (inclusive o da bandeja) para trocar o .exe
  Exec(ExpandConstant('{sys}	askkill.exe'), '/F /IM {#Exe}', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Sleep(800);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Url: String;
begin
  // O programa lê instalacao.env ao abrir, guarda no .env (preservando o resto) e apaga o arquivo.
  if (CurStep = ssPostInstall) and ChaveValida(ChaveSistema) then
  begin
    Url := UrlPainel;
    while (Length(Url) > 0) and (Url[Length(Url)] = '/') do
      Delete(Url, Length(Url), 1);
    SaveStringToFile(ExpandConstant('{app}\instalacao.env'),
      'GESTAO_URL=' + Url + #13#10 + 'GESTAO_CHAVE=' + ChaveSistema + #13#10, False);
  end;
end;

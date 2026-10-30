-- Empresas (clientes) e os sistemas (instalações do Bot DevMaster) de cada uma.
CREATE TABLE empresas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  documento TEXT NOT NULL DEFAULT '',
  observacao TEXT NOT NULL DEFAULT '',
  ativo INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE sistemas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  empresa_id INTEGER NOT NULL REFERENCES empresas(id),
  nome TEXT NOT NULL,
  ativo INTEGER NOT NULL DEFAULT 1,
  -- o que o robô escolhe na tela de login do DevMaster
  devmaster_empresa TEXT NOT NULL DEFAULT 'Loja/Gerencial',
  devmaster_modulo TEXT NOT NULL DEFAULT 'Gestão Varejo Atacado',
  -- a chave só é mostrada uma vez; aqui fica o hash (SHA-256) e o final para identificar
  chave_hash TEXT NOT NULL UNIQUE,
  chave_final TEXT NOT NULL,
  chave_criada_em TEXT NOT NULL DEFAULT (datetime('now')),
  versao TEXT NOT NULL DEFAULT '',
  host TEXT NOT NULL DEFAULT '',
  estado TEXT NOT NULL DEFAULT '',
  ultimo_contato TEXT,
  criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_sistemas_empresa ON sistemas(empresa_id);

-- Comandos liberados por sistema e o nome do arquivo que cada um gera.
CREATE TABLE sistema_comandos (
  sistema_id INTEGER NOT NULL REFERENCES sistemas(id) ON DELETE CASCADE,
  comando TEXT NOT NULL,
  titulo TEXT NOT NULL DEFAULT '',
  arquivo TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (sistema_id, comando)
);

-- Quem pode pedir: números de WhatsApp e IDs do Telegram.
CREATE TABLE contatos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sistema_id INTEGER NOT NULL REFERENCES sistemas(id) ON DELETE CASCADE,
  canal TEXT NOT NULL CHECK (canal IN ('whatsapp', 'telegram')),
  identificador TEXT NOT NULL,
  nome TEXT NOT NULL DEFAULT '',
  ativo INTEGER NOT NULL DEFAULT 1,
  criado_em TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (sistema_id, canal, identificador)
);

CREATE TABLE execucoes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sistema_id INTEGER NOT NULL REFERENCES sistemas(id) ON DELETE CASCADE,
  comando TEXT NOT NULL,
  canal TEXT NOT NULL DEFAULT '',
  solicitante TEXT NOT NULL DEFAULT '',
  ok INTEGER NOT NULL DEFAULT 1,
  erro TEXT NOT NULL DEFAULT '',
  duracao_ms INTEGER NOT NULL DEFAULT 0,
  criado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_execucoes_sistema ON execucoes(sistema_id, id DESC);

-- Limite de tentativas de login no painel.
CREATE TABLE tentativas_login (
  ip TEXT NOT NULL,
  quando INTEGER NOT NULL
);
CREATE INDEX idx_tentativas ON tentativas_login(ip, quando);

-- Bot DevMaster · estrutura inicial (tabelas e colunas em português)
--
-- Empresas (clientes) › sistemas (cada instalação do bot) › comandos liberados, contatos permitidos e execuções.
-- Segurança: RLS ligado em tudo; só administradores (tabela `administradores`, ligada ao Supabase Auth) mexem
-- nos dados. O programa instalado fala só com as funções `bot_*`, autenticadas pela chave do sistema.
-- Realtime: o painel recebe as mudanças ao vivo (sistemas online, execuções, contatos).
-- Seguro para rodar de novo (idempotente).

-- ---------------------------------------------------------------- administradores
create table if not exists public.administradores (
  usuario_id uuid primary key references auth.users (id) on delete cascade,
  nome       text not null default '',
  criado_em  timestamptz not null default now()
);
comment on table public.administradores is 'Quem pode usar o painel de gestão (usuários do Supabase Auth).';

create or replace function public.eh_administrador()
returns boolean
language sql stable security definer
set search_path = ''
as $$
  select exists (select 1 from public.administradores a where a.usuario_id = (select auth.uid()))
$$;

create or replace function public.definir_atualizado_em()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.atualizado_em := now();
  return new;
end
$$;

-- ---------------------------------------------------------------- empresas
create table if not exists public.empresas (
  id            uuid primary key default gen_random_uuid(),
  nome          text not null check (length(btrim(nome)) between 1 and 120),
  documento     text not null default '' check (length(documento) <= 30),
  observacao    text not null default '' check (length(observacao) <= 500),
  ativa         boolean not null default true,
  criada_em     timestamptz not null default now(),
  atualizado_em timestamptz not null default now()
);
comment on table public.empresas is 'Clientes. Desativar uma empresa bloqueia todos os sistemas dela.';

-- ---------------------------------------------------------------- catálogo de comandos
create table if not exists public.catalogo_comandos (
  comando        text primary key check (comando ~ '^[a-z][a-z0-9_]{0,39}$'),
  titulo         text not null check (length(btrim(titulo)) between 1 and 40),
  descricao      text not null default '' check (length(descricao) <= 200),
  arquivo_padrao text not null default '' check (length(arquivo_padrao) <= 80)
);
comment on table public.catalogo_comandos is 'Comandos que o programa sabe executar. Novo comando = nova linha aqui + código no programa.';

insert into public.catalogo_comandos (comando, titulo, descricao, arquivo_padrao)
values ('estoque', 'Estoque Geral', 'Gera o Saldos em Estoque (Excel) e envia aqui', 'Estoque Geral.xlsx')
on conflict (comando) do nothing;

-- ---------------------------------------------------------------- sistemas
create table if not exists public.sistemas (
  id                uuid primary key default gen_random_uuid(),
  empresa_id        uuid not null references public.empresas (id) on delete restrict,
  nome              text not null check (length(btrim(nome)) between 1 and 120),
  ativo             boolean not null default true,
  -- o que o robô escolhe na tela de login do DevMaster
  empresa_devmaster text not null default 'Loja/Gerencial' check (length(btrim(empresa_devmaster)) between 1 and 80),
  modulo_devmaster  text not null default 'Gestão Varejo Atacado' check (length(btrim(modulo_devmaster)) between 1 and 80),
  chave_final       text not null default '',
  chave_criada_em   timestamptz not null default now(),
  versao            text not null default '' check (length(versao) <= 30),
  computador        text not null default '' check (length(computador) <= 80),
  estado            jsonb not null default '{}'::jsonb,
  ultimo_contato    timestamptz,
  criado_em         timestamptz not null default now(),
  atualizado_em     timestamptz not null default now()
);
create index if not exists idx_sistemas_empresa on public.sistemas (empresa_id);
comment on table public.sistemas is 'Cada instalação do Bot DevMaster. A chave (hash) fica em sistema_chaves.';

-- O hash da chave fica à parte, sem nenhum acesso pela API: só as funções abaixo o enxergam.
create table if not exists public.sistema_chaves (
  sistema_id uuid primary key references public.sistemas (id) on delete cascade,
  chave_hash text not null unique
);
comment on table public.sistema_chaves is 'SHA-256 da chave de cada sistema. Sem políticas de RLS: inacessível pela API.';

-- ---------------------------------------------------------------- comandos de cada sistema
create table if not exists public.sistema_comandos (
  sistema_id uuid not null references public.sistemas (id) on delete cascade,
  comando    text not null references public.catalogo_comandos (comando) on update cascade on delete cascade,
  titulo     text not null default '' check (length(titulo) <= 40),
  arquivo    text not null default '' check (length(arquivo) <= 80 and arquivo !~ '[\\/:*?"<>|]'),
  primary key (sistema_id, comando)
);
comment on table public.sistema_comandos is 'Comandos liberados para o sistema, com o texto do botão e o nome do arquivo gerado (vazio = padrão).';

-- ---------------------------------------------------------------- contatos permitidos
create table if not exists public.contatos (
  id            uuid primary key default gen_random_uuid(),
  sistema_id    uuid not null references public.sistemas (id) on delete cascade,
  canal         text not null check (canal in ('whatsapp', 'telegram')),
  identificador text not null,
  nome          text not null default '' check (length(nome) <= 80),
  ativo         boolean not null default true,
  criado_em     timestamptz not null default now(),
  unique (sistema_id, canal, identificador),
  check (
    (canal = 'whatsapp' and identificador ~ '^[0-9]{8,20}$')
    or (canal = 'telegram' and identificador ~ '^[0-9]{3,15}$')
  )
);
comment on table public.contatos is 'Quem pode pedir: números de WhatsApp (DDI+DDD+número) e IDs do Telegram.';

-- ---------------------------------------------------------------- execuções
create table if not exists public.execucoes (
  id          bigint generated always as identity primary key,
  sistema_id  uuid not null references public.sistemas (id) on delete cascade,
  comando     text not null,
  canal       text not null default '',
  solicitante text not null default '',
  sucesso     boolean not null default true,
  erro        text not null default '',
  duracao_ms  integer not null default 0 check (duracao_ms >= 0),
  criada_em   timestamptz not null default now()
);
create index if not exists idx_execucoes_sistema on public.execucoes (sistema_id, id desc);
create index if not exists idx_execucoes_criada on public.execucoes (criada_em desc);
comment on table public.execucoes is 'Histórico de comandos executados (guardado por 90 dias).';

-- ---------------------------------------------------------------- gatilhos
drop trigger if exists trg_empresas_atualizado on public.empresas;
create trigger trg_empresas_atualizado before update on public.empresas
  for each row execute function public.definir_atualizado_em();

drop trigger if exists trg_sistemas_atualizado on public.sistemas;
create trigger trg_sistemas_atualizado before update on public.sistemas
  for each row execute function public.definir_atualizado_em();

-- ---------------------------------------------------------------- segurança por linha (RLS)
alter table public.administradores  enable row level security;
alter table public.empresas         enable row level security;
alter table public.catalogo_comandos enable row level security;
alter table public.sistemas         enable row level security;
alter table public.sistema_chaves   enable row level security;
alter table public.sistema_comandos enable row level security;
alter table public.contatos         enable row level security;
alter table public.execucoes        enable row level security;

-- ninguém sem login acessa tabela nenhuma; o hash das chaves não é acessível nem logado
revoke all on public.administradores, public.empresas, public.catalogo_comandos, public.sistemas,
              public.sistema_chaves, public.sistema_comandos, public.contatos, public.execucoes from anon;
revoke all on public.sistema_chaves from authenticated;
grant select on public.administradores to authenticated;
grant select, insert, update, delete on public.empresas, public.catalogo_comandos, public.sistemas,
              public.sistema_comandos, public.contatos, public.execucoes to authenticated;

drop policy if exists "ver o próprio cadastro de administrador" on public.administradores;
create policy "ver o próprio cadastro de administrador" on public.administradores
  for select to authenticated using (usuario_id = (select auth.uid()));

drop policy if exists "administradores gerenciam empresas" on public.empresas;
create policy "administradores gerenciam empresas" on public.empresas
  for all to authenticated using (public.eh_administrador()) with check (public.eh_administrador());

drop policy if exists "administradores gerenciam o catálogo" on public.catalogo_comandos;
create policy "administradores gerenciam o catálogo" on public.catalogo_comandos
  for all to authenticated using (public.eh_administrador()) with check (public.eh_administrador());

drop policy if exists "administradores gerenciam sistemas" on public.sistemas;
create policy "administradores gerenciam sistemas" on public.sistemas
  for all to authenticated using (public.eh_administrador()) with check (public.eh_administrador());

drop policy if exists "administradores gerenciam comandos dos sistemas" on public.sistema_comandos;
create policy "administradores gerenciam comandos dos sistemas" on public.sistema_comandos
  for all to authenticated using (public.eh_administrador()) with check (public.eh_administrador());

drop policy if exists "administradores gerenciam contatos" on public.contatos;
create policy "administradores gerenciam contatos" on public.contatos
  for all to authenticated using (public.eh_administrador()) with check (public.eh_administrador());

drop policy if exists "administradores gerenciam execuções" on public.execucoes;
create policy "administradores gerenciam execuções" on public.execucoes
  for all to authenticated using (public.eh_administrador()) with check (public.eh_administrador());

-- ---------------------------------------------------------------- chaves
-- 244 bits aleatórios (dois UUIDs v4): "dmb_" + 64 caracteres. Uso interno.
create or replace function public.nova_chave_sistema()
returns text
language sql volatile
set search_path = ''
as $$
  select 'dmb_' || replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
$$;

create or replace function public.hash_da_chave(p_chave text)
returns text
language sql immutable
set search_path = ''
as $$
  select encode(sha256(convert_to(coalesce(p_chave, ''), 'utf8')), 'hex')
$$;

-- ---------------------------------------------------------------- funções do painel (só administradores)
create or replace function public.criar_sistema(
  p_empresa_id uuid,
  p_nome text,
  p_empresa_devmaster text default 'Loja/Gerencial',
  p_modulo_devmaster text default 'Gestão Varejo Atacado',
  p_comandos jsonb default null
)
returns jsonb
language plpgsql security definer
set search_path = ''
as $$
declare
  v_id uuid;
  v_chave text := public.nova_chave_sistema();
begin
  if not public.eh_administrador() then
    raise exception 'Sem permissão' using errcode = '42501';
  end if;

  insert into public.sistemas (empresa_id, nome, empresa_devmaster, modulo_devmaster, chave_final)
  values (p_empresa_id, p_nome,
          coalesce(nullif(btrim(p_empresa_devmaster), ''), 'Loja/Gerencial'),
          coalesce(nullif(btrim(p_modulo_devmaster), ''), 'Gestão Varejo Atacado'),
          right(v_chave, 4))
  returning id into v_id;

  insert into public.sistema_chaves (sistema_id, chave_hash) values (v_id, public.hash_da_chave(v_chave));

  if p_comandos is null then
    insert into public.sistema_comandos (sistema_id, comando) select v_id, comando from public.catalogo_comandos;
  else
    perform public.salvar_comandos(v_id, p_comandos);
  end if;

  return jsonb_build_object('id', v_id, 'chave', v_chave); -- a chave só aparece agora
end
$$;

create or replace function public.gerar_nova_chave(p_sistema_id uuid)
returns text
language plpgsql security definer
set search_path = ''
as $$
declare
  v_chave text := public.nova_chave_sistema();
begin
  if not public.eh_administrador() then
    raise exception 'Sem permissão' using errcode = '42501';
  end if;
  perform 1 from public.sistemas where id = p_sistema_id;
  if not found then
    raise exception 'Sistema não encontrado' using errcode = 'P0002';
  end if;

  insert into public.sistema_chaves (sistema_id, chave_hash) values (p_sistema_id, public.hash_da_chave(v_chave))
  on conflict (sistema_id) do update set chave_hash = excluded.chave_hash; -- a chave antiga deixa de valer na hora
  update public.sistemas set chave_final = right(v_chave, 4), chave_criada_em = now() where id = p_sistema_id;
  return v_chave;
end
$$;

-- p_comandos: [{"comando": "estoque", "titulo": "", "arquivo": ""}, ...] (substitui a lista inteira)
create or replace function public.salvar_comandos(p_sistema_id uuid, p_comandos jsonb)
returns void
language plpgsql security definer
set search_path = ''
as $$
begin
  if not public.eh_administrador() then
    raise exception 'Sem permissão' using errcode = '42501';
  end if;
  if jsonb_typeof(p_comandos) is distinct from 'array' then
    raise exception 'Lista de comandos inválida' using errcode = '22023';
  end if;

  delete from public.sistema_comandos where sistema_id = p_sistema_id;
  insert into public.sistema_comandos (sistema_id, comando, titulo, arquivo)
  select p_sistema_id, c ->> 'comando', coalesce(btrim(c ->> 'titulo'), ''), coalesce(btrim(c ->> 'arquivo'), '')
  from jsonb_array_elements(p_comandos) as c;
end
$$;

create or replace function public.painel_resumo()
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
begin
  if not public.eh_administrador() then
    raise exception 'Sem permissão' using errcode = '42501';
  end if;
  return jsonb_build_object(
    'sistemas', (select count(*) from public.sistemas),
    'online', (select count(*) from public.sistemas where ultimo_contato > now() - interval '10 minutes'),
    'empresas', (select count(*) from public.empresas),
    'execucoes_24h', (select count(*) from public.execucoes where criada_em > now() - interval '24 hours'),
    'falhas_24h', (select count(*) from public.execucoes where criada_em > now() - interval '24 hours' and not sucesso)
  );
end
$$;

-- ---------------------------------------------------------------- funções do programa instalado (autenticadas pela chave)
-- Devolve null se a chave não existir (revogada, trocada ou sistema excluído).
create or replace function public.bot_configuracao(p_chave text)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  v_sis public.sistemas%rowtype;
  v_emp public.empresas%rowtype;
  v_ativo boolean;
begin
  select s.* into v_sis
  from public.sistemas s
  join public.sistema_chaves k on k.sistema_id = s.id
  where k.chave_hash = public.hash_da_chave(p_chave);
  if not found then
    return null;
  end if;

  select * into v_emp from public.empresas where id = v_sis.empresa_id;
  v_ativo := v_sis.ativo and v_emp.ativa;

  return jsonb_build_object(
    'sistema',   jsonb_build_object('id', v_sis.id, 'nome', v_sis.nome, 'ativo', v_ativo),
    'empresa',   jsonb_build_object('id', v_emp.id, 'nome', v_emp.nome),
    'devmaster', jsonb_build_object('empresa', v_sis.empresa_devmaster, 'modulo', v_sis.modulo_devmaster),
    'comandos',  case when v_ativo then coalesce((
                   select jsonb_agg(jsonb_build_object(
                            'nome', c.comando,
                            'titulo', coalesce(nullif(sc.titulo, ''), c.titulo),
                            'descricao', c.descricao,
                            'arquivo', coalesce(nullif(sc.arquivo, ''), c.arquivo_padrao)) order by c.comando)
                   from public.sistema_comandos sc
                   join public.catalogo_comandos c on c.comando = sc.comando
                   where sc.sistema_id = v_sis.id), '[]'::jsonb)
                 else '[]'::jsonb end,
    'whatsapp',  jsonb_build_object('numeros', case when v_ativo then coalesce((
                   select jsonb_agg(identificador order by criado_em, id) from public.contatos
                   where sistema_id = v_sis.id and canal = 'whatsapp' and ativo), '[]'::jsonb)
                 else '[]'::jsonb end),
    'telegram',  jsonb_build_object('ids', case when v_ativo then coalesce((
                   select jsonb_agg(identificador order by criado_em, id) from public.contatos
                   where sistema_id = v_sis.id and canal = 'telegram' and ativo), '[]'::jsonb)
                 else '[]'::jsonb end),
    'gerado_em', now()
  );
end
$$;

create or replace function public.bot_batimento(p_chave text, p_versao text, p_computador text, p_estado jsonb default '{}'::jsonb)
returns boolean
language plpgsql security definer
set search_path = ''
as $$
declare
  v_id uuid;
begin
  select k.sistema_id into v_id from public.sistema_chaves k where k.chave_hash = public.hash_da_chave(p_chave);
  if v_id is null then
    return false;
  end if;
  update public.sistemas
     set versao = left(coalesce(p_versao, ''), 30),
         computador = left(coalesce(p_computador, ''), 80),
         estado = case when jsonb_typeof(p_estado) = 'object' then p_estado else '{}'::jsonb end,
         ultimo_contato = now()
   where id = v_id;
  return true;
end
$$;

create or replace function public.bot_registrar_execucao(
  p_chave text, p_comando text, p_canal text, p_solicitante text,
  p_sucesso boolean, p_erro text, p_duracao_ms integer
)
returns boolean
language plpgsql security definer
set search_path = ''
as $$
declare
  v_id uuid;
begin
  select k.sistema_id into v_id from public.sistema_chaves k where k.chave_hash = public.hash_da_chave(p_chave);
  if v_id is null then
    return false;
  end if;
  insert into public.execucoes (sistema_id, comando, canal, solicitante, sucesso, erro, duracao_ms)
  values (v_id, left(coalesce(nullif(btrim(p_comando), ''), '?'), 40), left(coalesce(p_canal, ''), 20),
          left(coalesce(p_solicitante, ''), 40), coalesce(p_sucesso, true), left(coalesce(p_erro, ''), 300),
          greatest(0, least(coalesce(p_duracao_ms, 0), 3600000)));
  return true;
end
$$;

-- ---------------------------------------------------------------- permissões das funções
revoke execute on function public.eh_administrador(), public.definir_atualizado_em(), public.nova_chave_sistema(),
  public.hash_da_chave(text), public.criar_sistema(uuid, text, text, text, jsonb), public.gerar_nova_chave(uuid),
  public.salvar_comandos(uuid, jsonb), public.painel_resumo(), public.bot_configuracao(text),
  public.bot_batimento(text, text, text, jsonb),
  public.bot_registrar_execucao(text, text, text, text, boolean, text, integer) from public, anon, authenticated;

grant execute on function public.eh_administrador(),
  public.criar_sistema(uuid, text, text, text, jsonb), public.gerar_nova_chave(uuid),
  public.salvar_comandos(uuid, jsonb), public.painel_resumo() to authenticated;
grant execute on function public.bot_configuracao(text), public.bot_batimento(text, text, text, jsonb),
  public.bot_registrar_execucao(text, text, text, text, boolean, text, integer) to anon, authenticated;

-- ---------------------------------------------------------------- Realtime (o painel atualiza ao vivo)
do $$
declare
  t text;
begin
  foreach t in array array['empresas', 'sistemas', 'sistema_comandos', 'contatos', 'execucoes'] loop
    if not exists (select 1 from pg_publication_tables
                   where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end
$$;

-- ---------------------------------------------------------------- limpeza automática (90 dias) se o pg_cron estiver disponível
do $$
begin
  create extension if not exists pg_cron;
  perform cron.schedule('limpar-execucoes-antigas', '0 3 * * *',
                        $job$delete from public.execucoes where criada_em < now() - interval '90 days'$job$);
exception when others then
  raise notice 'pg_cron indisponível (%): a limpeza das execuções antigas não foi agendada.', sqlerrm;
end
$$;

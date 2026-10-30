-- Bot DevMaster · WhatsApp (Evolution API) e Telegram configurados no painel
--
-- As credenciais de cada sistema ficam aqui e chegam ao programa instalado junto com a configuração
-- (bot_configuracao), autenticadas pela chave do sistema. Assim o instalador só precisa da chave.
-- Seguro para rodar de novo (idempotente).

create table if not exists public.sistema_canais (
  sistema_id     uuid primary key references public.sistemas (id) on delete cascade,
  evo_url        text not null default '' check (length(evo_url) <= 300 and (evo_url = '' or evo_url ~* '^https?://')),
  evo_instancia  text not null default '' check (length(evo_instancia) <= 120),
  evo_key        text not null default '' check (length(evo_key) <= 300),
  whatsapp_menu  text not null default 'botoes' check (whatsapp_menu in ('botoes', 'texto')),
  telegram_token text not null default '' check (telegram_token = '' or telegram_token ~ '^[0-9]{5,15}:[A-Za-z0-9_-]{30,60}$'),
  atualizado_em  timestamptz not null default now()
);
comment on table public.sistema_canais is 'Credenciais do WhatsApp (Evolution API) e do Telegram de cada sistema. Vazio = usa o que estiver no computador.';

drop trigger if exists trg_sistema_canais_atualizado on public.sistema_canais;
create trigger trg_sistema_canais_atualizado before update on public.sistema_canais
  for each row execute function public.definir_atualizado_em();

alter table public.sistema_canais enable row level security;
revoke all on public.sistema_canais from anon;
grant select, insert, update, delete on public.sistema_canais to authenticated;

drop policy if exists "administradores gerenciam canais" on public.sistema_canais;
create policy "administradores gerenciam canais" on public.sistema_canais
  for all to authenticated using (public.eh_administrador()) with check (public.eh_administrador());

-- Mesma resposta de antes, com as credenciais dos canais em whatsapp/telegram (só para sistema ativo).
create or replace function public.bot_configuracao(p_chave text)
returns jsonb
language plpgsql stable security definer
set search_path = ''
as $$
declare
  v_sis public.sistemas%rowtype;
  v_emp public.empresas%rowtype;
  v_can public.sistema_canais%rowtype;
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
  select * into v_can from public.sistema_canais where sistema_id = v_sis.id;
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
    'whatsapp',  jsonb_build_object(
                   'numeros', case when v_ativo then coalesce((
                     select jsonb_agg(identificador order by criado_em, id) from public.contatos
                     where sistema_id = v_sis.id and canal = 'whatsapp' and ativo), '[]'::jsonb)
                   else '[]'::jsonb end,
                   'url', case when v_ativo then coalesce(v_can.evo_url, '') else '' end,
                   'instancia', case when v_ativo then coalesce(v_can.evo_instancia, '') else '' end,
                   'apikey', case when v_ativo then coalesce(v_can.evo_key, '') else '' end,
                   'menu', coalesce(v_can.whatsapp_menu, 'botoes')),
    'telegram',  jsonb_build_object(
                   'ids', case when v_ativo then coalesce((
                     select jsonb_agg(identificador order by criado_em, id) from public.contatos
                     where sistema_id = v_sis.id and canal = 'telegram' and ativo), '[]'::jsonb)
                   else '[]'::jsonb end,
                   'token', case when v_ativo then coalesce(v_can.telegram_token, '') else '' end),
    'gerado_em', now()
  );
end
$$;

revoke execute on function public.bot_configuracao(text) from public;
grant execute on function public.bot_configuracao(text) to anon, authenticated;

do $$
begin
  if not exists (select 1 from pg_publication_tables
                 where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'sistema_canais') then
    alter publication supabase_realtime add table public.sistema_canais;
  end if;
end
$$;

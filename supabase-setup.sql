create table if not exists public.dashboard_profiles (
  profile text primary key check (profile in ('andres', 'wife')),
  data jsonb not null,
  updated_at timestamptz not null default now()
);

alter table public.dashboard_profiles enable row level security;

drop policy if exists "Public read dashboard profiles" on public.dashboard_profiles;
drop policy if exists "Public insert dashboard profiles" on public.dashboard_profiles;
drop policy if exists "Public update dashboard profiles" on public.dashboard_profiles;

create policy "Public read dashboard profiles"
  on public.dashboard_profiles
  for select
  to anon, authenticated
  using (true);

create policy "Public insert dashboard profiles"
  on public.dashboard_profiles
  for insert
  to anon, authenticated
  with check (true);

create policy "Public update dashboard profiles"
  on public.dashboard_profiles
  for update
  to anon, authenticated
  using (true)
  with check (true);

grant select, insert, update on public.dashboard_profiles to anon, authenticated;

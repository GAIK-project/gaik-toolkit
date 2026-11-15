-- Access rules for public.access_requests (the demo's approval table).
--
-- A signed-in user may read their own row and nothing else, and may not write
-- the table at all: the approval status, the Solution Wizard flag, the report
-- counters and the report cap are set only by the server with the service key
-- (sign-up in app/(auth)/actions.ts, the admin dashboard in app/admin/actions.ts,
-- report usage in lib/report-writer/gate.ts). The service key bypasses these
-- rules.
--
-- Run it in the Supabase SQL editor of the demo project. It is safe to run again.
-- Then run `bun scripts/check-access-rules.ts` (see its header) to check the
-- rules with a test account.

alter table public.access_requests enable row level security;

-- Writes: no table privilege for browser roles, whatever policies say.
revoke insert, update, delete, truncate on public.access_requests from anon, authenticated;

-- Reads: no anonymous reads; a signed-in user reads only their own row.
revoke select on public.access_requests from anon;
grant select on public.access_requests to authenticated;

do $$
declare
  p record;
begin
  -- A policy that lets a browser role read other rows or write any row is
  -- removed; the one read policy below replaces it.
  for p in
    select policyname
    from pg_policies
    where schemaname = 'public'
      and tablename = 'access_requests'
      and policyname <> 'access_requests: read own row'
      and (cmd <> 'SELECT' or roles && array['anon', 'authenticated', 'public']::name[])
  loop
    execute format('drop policy %I on public.access_requests', p.policyname);
  end loop;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'access_requests'
      and policyname = 'access_requests: read own row'
  ) then
    create policy "access_requests: read own row"
      on public.access_requests
      for select
      to authenticated
      using (user_id = (select auth.uid()));
  end if;
end
$$;

-- Lists what is in force now: one SELECT policy for authenticated.
select policyname, cmd, roles, qual, with_check
from pg_policies
where schemaname = 'public' and tablename = 'access_requests';

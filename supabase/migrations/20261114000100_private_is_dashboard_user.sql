-- Move is_dashboard_user() out of the API-exposed public schema, so it can't
-- be called as /rest/v1/rpc/is_dashboard_user (Supabase advisors 0028, 0029).
-- RLS policies reference the function itself, so they follow the move.

create schema if not exists private;
grant usage on schema private to authenticated;

alter function public.is_dashboard_user() set schema private;

revoke execute on function private.is_dashboard_user() from public, anon;
grant execute on function private.is_dashboard_user() to authenticated;

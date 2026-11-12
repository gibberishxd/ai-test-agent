-- Run 5, K3: what the web app may do outside one workspace, and nothing more.
--
-- The web app (ata_web) reaches tenant data only inside a transaction that sets
-- app.workspace_id (lib/tenant-db.ts). A few things happen before the workspace is known, or
-- span two workspaces. Each one is a narrow, documented exception (docs/DATABASE.md,
-- "Justified bypasses"):
--   1. Sign-in reads users by id, email or OAuth account (read-only policy below).
--   2. An API key is looked up by its hash (api_key_by_hash).
--   3. A public share link is looked up by its token (shared_run).
--   4. Accepting an invitation moves a user into the inviting workspace (accept_invitation).
--   5. Removing a member moves them into a new workspace of their own (remove_member).
--   6. Visitors try the demo in the shared demo workspace (demo_workspace).
--   7. /api/metrics reports totals across all workspaces (service_metrics).

-- 1. Sign-in: Auth.js looks a user up before any workspace is set. Read-only, and only the
--    identity columns matter to it; every write to users still goes through a tenant.
CREATE POLICY sign_in_lookup ON users FOR SELECT TO ata_web USING (true);

-- 2. API keys: the key's hash is the credential. Returns the key's id and workspace, or
--    nothing for an unknown hash. The caller then works inside that workspace.
CREATE OR REPLACE FUNCTION api_key_by_hash(p_hash text)
  RETURNS TABLE (id uuid, workspace_id uuid, created_by_id uuid, revoked_at timestamptz)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ SELECT k.id, k.workspace_id, k.created_by_id, k.revoked_at FROM api_keys k WHERE k.key_hash = p_hash $$;

-- 3. Share links: the token is the credential (unguessable, revocable).
CREATE OR REPLACE FUNCTION shared_run(p_token text)
  RETURNS TABLE (id uuid, workspace_id uuid)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$ SELECT r.id, r.workspace_id FROM runs r WHERE r.share_token = p_token AND p_token <> '' $$;

-- 4. Invitations: look one up by its token hash (to show who invites you), and accept it.
--    Accepting moves the user from their own workspace into the inviting one, which no single
--    tenant may do, so it is one function that checks everything in one transaction.
CREATE OR REPLACE FUNCTION invitation_by_token(p_hash text)
  RETURNS TABLE (id uuid, workspace_id uuid, workspace_name text, role workspace_role,
                 expires_at timestamptz, accepted_at timestamptz, revoked_at timestamptz)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
  SELECT i.id, i.workspace_id, w.name, i.role, i.expires_at, i.accepted_at, i.revoked_at
    FROM invitations i JOIN workspaces w ON w.id = i.workspace_id
   WHERE i.token_hash = p_hash
$$;

-- Returns the workspace joined, or raises with a message the app shows as is.
CREATE OR REPLACE FUNCTION accept_invitation(p_hash text, p_user uuid)
  RETURNS TABLE (workspace_id uuid, role workspace_role)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  inv invitations%ROWTYPE;
  member users%ROWTYPE;
BEGIN
  SELECT * INTO inv FROM invitations i WHERE i.token_hash = p_hash FOR UPDATE;
  IF NOT FOUND OR inv.revoked_at IS NOT NULL OR inv.accepted_at IS NOT NULL OR inv.expires_at < now() THEN
    RAISE EXCEPTION 'This invitation link is no longer valid. Ask for a new one.' USING ERRCODE = 'P0001';
  END IF;
  SELECT * INTO member FROM users u WHERE u.id = p_user FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Sign in first.' USING ERRCODE = 'P0001';
  END IF;
  IF member.workspace_id = inv.workspace_id THEN
    RAISE EXCEPTION 'You are already a member of this workspace.' USING ERRCODE = 'P0001';
  END IF;
  IF member.role = 'owner' AND EXISTS (
    SELECT 1 FROM users o WHERE o.workspace_id = member.workspace_id AND o.id <> member.id
  ) THEN
    RAISE EXCEPTION 'You own a workspace with other members: transfer ownership first.'
      USING ERRCODE = 'P0001';
  END IF;
  PERFORM set_config('app.user_id', p_user::text, true);
  UPDATE users u SET workspace_id = inv.workspace_id, role = inv.role WHERE u.id = p_user;
  UPDATE invitations i SET accepted_at = now(), accepted_by_id = p_user WHERE i.id = inv.id;
  RETURN QUERY SELECT inv.workspace_id, inv.role;
END
$$;

-- 5. Removing a member: they keep their account, in a new workspace they own. Acts only in
--    the caller's current workspace (app.workspace_id), on a member of it who isn't the owner.
CREATE OR REPLACE FUNCTION remove_member(p_target uuid) RETURNS uuid
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  member users%ROWTYPE;
  own uuid;
BEGIN
  SELECT * INTO member FROM users u
   WHERE u.id = p_target AND u.workspace_id = app_current_workspace() FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Member not found.' USING ERRCODE = 'P0002';
  END IF;
  IF member.role = 'owner' THEN
    RAISE EXCEPTION 'The owner can''t be removed: transfer ownership first.' USING ERRCODE = 'P0001';
  END IF;
  INSERT INTO workspaces (name, slug)
  VALUES (coalesce(NULLIF(member.name, ''), split_part(member.email, '@', 1)) || '''s workspace',
          regexp_replace(lower(split_part(member.email, '@', 1)), '[^a-z0-9]+', '-', 'g')
            || '-' || substr(md5(random()::text), 1, 4))
  RETURNING id INTO own;
  UPDATE users u SET workspace_id = own, role = 'owner' WHERE u.id = p_target;
  RETURN own;
END
$$;

-- 6. The shared demo workspace visitors' runs belong to (created on first use).
CREATE OR REPLACE FUNCTION demo_workspace() RETURNS uuid
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  ws uuid;
BEGIN
  INSERT INTO workspaces (name, slug) VALUES ('Public demo', 'demo')
  ON CONFLICT (slug) DO NOTHING;
  SELECT w.id INTO ws FROM workspaces w WHERE w.slug = 'demo';
  RETURN ws;
END
$$;

-- 7. Service metrics: totals only, no tenant rows.
CREATE OR REPLACE FUNCTION service_metrics()
  RETURNS TABLE (metric text, label text, value double precision)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
  SELECT 'runs', status::text, count(*)::double precision FROM runs GROUP BY status
  UNION ALL
  SELECT 'webhook_deliveries', status, count(*)::double precision FROM webhook_deliveries GROUP BY status
  UNION ALL
  SELECT 'run_seconds_sum', '', coalesce(sum(extract(epoch FROM finished_at - started_at)), 0)
    FROM runs WHERE finished_at IS NOT NULL AND started_at IS NOT NULL
  UNION ALL
  SELECT 'runs_finished', '', count(*)::double precision
    FROM runs WHERE finished_at IS NOT NULL AND started_at IS NOT NULL
  UNION ALL
  SELECT 'input_tokens', '', coalesce(sum(input_tokens), 0)::double precision FROM runs
  UNION ALL
  SELECT 'output_tokens', '', coalesce(sum(output_tokens), 0)::double precision FROM runs
  UNION ALL
  SELECT 'cost_usd', '', coalesce(sum(cost_usd), 0)::double precision FROM runs
$$;

REVOKE EXECUTE ON FUNCTION api_key_by_hash(text), shared_run(text), invitation_by_token(text),
  accept_invitation(text, uuid), remove_member(uuid), demo_workspace(), service_metrics() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION api_key_by_hash(text), shared_run(text), invitation_by_token(text),
  accept_invitation(text, uuid), demo_workspace(), service_metrics() TO ata_web;
-- remove_member runs inside a tenant transaction (as app_tenant) and acts only in its workspace.
GRANT EXECUTE ON FUNCTION remove_member(uuid) TO app_tenant;

DO $$
DECLARE
  f text;
BEGIN
  IF current_user = 'ata_owner' THEN
    RETURN;
  END IF;
  FOREACH f IN ARRAY ARRAY['api_key_by_hash(text)', 'shared_run(text)', 'invitation_by_token(text)',
                           'accept_invitation(text, uuid)', 'remove_member(uuid)', 'demo_workspace()',
                           'service_metrics()'] LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO ata_owner', f);
  END LOOP;
END
$$;

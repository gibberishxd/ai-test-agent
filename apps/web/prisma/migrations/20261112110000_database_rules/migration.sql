-- Run 5, K3: a database that enforces its own rules (docs/DATABASE.md, "Rules in the database").
--
-- 1. Roles: ata_owner owns the schema and runs migrations; ata_web and ata_worker are the apps.
--    None is a superuser, none bypasses row-level security. The app roles are members of
--    app_tenant, so the tenant policies apply to them: without app.workspace_id they see no
--    tenant rows at all (fail closed).
-- 2. Functions the worker and web call instead of repeating the logic in app code:
--    claim_next_run, recover_runs, renew_lease, consume_quota, apply_retention.
-- 3. Triggers: updated_at, the audit log, triage carry-forward to later runs.
-- 4. Views: target_bug_history (per target), model_leaderboard (materialized, refreshed on write).
-- 5. Check constraints for fixed sets and ranges.
--
-- Roles are cluster-wide and need CREATEROLE. A superuser running this (dev, CI, the first
-- production deploy) creates them; without that privilege they must already exist
-- (scripts/db/roles.sql). Passwords are never in a migration: they are set by that script.

-- ---------------------------------------------------------------------------------------------
-- 1. Roles and ownership
-- ---------------------------------------------------------------------------------------------
DO $$
DECLARE
  r text;
BEGIN
  -- Only a role that may manage roles does this (dev, CI, the production bootstrap). The
  -- migration owner can't, and doesn't need to: scripts/db/roles.sql has run before it.
  IF NOT (SELECT rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = current_user) THEN
    RETURN;
  END IF;
  FOREACH r IN ARRAY ARRAY['ata_owner', 'ata_web', 'ata_worker'] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', r);
    END IF;
  END LOOP;
  GRANT app_tenant TO ata_web, ata_worker;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO ata_owner, ata_web, ata_worker', current_database());
  GRANT USAGE, CREATE ON SCHEMA public TO ata_owner;
  GRANT USAGE ON SCHEMA public TO ata_web, ata_worker;
END
$$;

-- Tables created by later migrations (run as ata_owner) get the same grants.
ALTER DEFAULT PRIVILEGES FOR ROLE ata_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_tenant;
ALTER DEFAULT PRIVILEGES FOR ROLE ata_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO app_tenant;
ALTER DEFAULT PRIVILEGES FOR ROLE ata_owner IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- The audit log is append-only for the apps: what happened can't be edited or erased.
REVOKE UPDATE, DELETE ON audit_log FROM app_tenant;
-- The leaderboard is written by the benchmark (the worker), read by everyone.
REVOKE INSERT, UPDATE, DELETE ON benchmark_results FROM app_tenant;
GRANT SELECT ON benchmark_results TO app_tenant;
GRANT INSERT, UPDATE ON benchmark_results TO ata_worker;
-- Sign-in data (OAuth accounts, email tokens) is the web app's alone; the worker never needs it.
REVOKE ALL ON accounts, verification_tokens FROM app_tenant;
GRANT SELECT, INSERT, UPDATE, DELETE ON accounts, verification_tokens TO ata_web;
-- Migration bookkeeping is the owner's alone.
DO $$
BEGIN
  IF to_regclass('public._prisma_migrations') IS NOT NULL THEN
    REVOKE ALL ON _prisma_migrations FROM app_tenant;
  END IF;
END
$$;

-- ---------------------------------------------------------------------------------------------
-- 2. Helpers
-- ---------------------------------------------------------------------------------------------
-- scheme://host[:port] of a URL, exactly like the worker's origin_of (urlsplit).
CREATE OR REPLACE FUNCTION url_origin(url text) RETURNS text
  LANGUAGE sql IMMUTABLE STRICT
  AS $$ SELECT substring(url FROM '^[A-Za-z][A-Za-z0-9+.-]*://[^/?#]*') $$;

-- The user acting in this transaction (set by the apps), or NULL.
CREATE OR REPLACE FUNCTION app_current_user() RETURNS uuid
  LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting('app.user_id', true), '')::uuid $$;

-- ---------------------------------------------------------------------------------------------
-- 3. The queue: claim_next_run, renew_lease, recover_runs (worker only)
-- ---------------------------------------------------------------------------------------------
-- Claim the oldest queued run (SKIP LOCKED: two workers never get the same run, none waits).
-- SECURITY DEFINER: a worker doesn't know the workspace before it has a run, so the claim is
-- the one place that looks across workspaces; it returns only the run's id and workspace.
CREATE OR REPLACE FUNCTION claim_next_run(p_worker text, p_only uuid[], p_skip_benchmark boolean)
  RETURNS TABLE (id uuid, workspace_id uuid)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  chosen uuid;
BEGIN
  SELECT r.id INTO chosen
  FROM runs r
  WHERE r.status = 'queued'
    AND (p_only IS NULL OR r.id = ANY (p_only))
    AND (NOT p_skip_benchmark
         OR r.workspace_id NOT IN (SELECT w.id FROM workspaces w WHERE w.slug = 'benchmark'))
  ORDER BY r.created_at
  LIMIT 1
  FOR UPDATE OF r SKIP LOCKED;
  IF chosen IS NULL THEN
    RETURN;
  END IF;
  RETURN QUERY
  UPDATE runs r
     SET status = 'running', claimed_by = p_worker, started_at = now(), heartbeat_at = now()
   WHERE r.id = chosen
  RETURNING r.id, r.workspace_id;
END
$$;

-- Renew a run's lease, only while it is still running (it can't revive a failed run).
CREATE OR REPLACE FUNCTION renew_lease(p_run uuid) RETURNS boolean
  LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
  UPDATE runs SET heartbeat_at = now() WHERE id = p_run AND status = 'running' RETURNING true
$$;

-- Fail running runs whose worker stopped renewing the lease. One UPDATE: two workers
-- recovering at once can't both fail the same run. Returns how many runs were failed.
CREATE OR REPLACE FUNCTION recover_runs(p_lease_s integer) RETURNS integer
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  n integer;
BEGIN
  UPDATE runs
     SET status = 'failed', finished_at = now(),
         error = format('the worker stopped responding (no heartbeat for %s s)', p_lease_s)
   WHERE status = 'running'
     AND coalesce(heartbeat_at, started_at) < now() - make_interval(secs => p_lease_s);
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END
$$;

-- ---------------------------------------------------------------------------------------------
-- 4. consume_quota: check and use a workspace's monthly runs atomically
-- ---------------------------------------------------------------------------------------------
-- Locks the workspace row (FOR UPDATE) for the rest of the caller's transaction, so concurrent
-- starts for one workspace queue up and each counts the runs the others inserted. The caller
-- inserts its run in the same transaction when `allowed`. SECURITY INVOKER: under row-level
-- security a tenant can only lock and count its own workspace; another one raises.
CREATE OR REPLACE FUNCTION consume_quota(p_workspace uuid)
  RETURNS TABLE (allowed boolean, used integer, quota integer)
  LANGUAGE plpgsql
  AS $$
DECLARE
  q integer;
  n integer;
BEGIN
  SELECT w.monthly_run_quota INTO q FROM workspaces w WHERE w.id = p_workspace FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'workspace % not found', p_workspace USING ERRCODE = 'no_data_found';
  END IF;
  SELECT count(*) INTO n FROM runs r
   WHERE r.workspace_id = p_workspace AND r.created_at >= date_trunc('month', now());
  RETURN QUERY SELECT n < q, n, q;
END
$$;

-- ---------------------------------------------------------------------------------------------
-- 5. apply_retention: purge what workspaces no longer keep
-- ---------------------------------------------------------------------------------------------
-- For finished runs older than their workspace's retention_days: delete the step timeline,
-- clear the findings' screenshot references, mark the run purged, and return the run ids so
-- the worker deletes their files from storage. Runs and findings stay (fingerprints compare
-- releases). Rate-limit windows older than an hour go too. Cross-workspace by nature, so
-- SECURITY DEFINER and executable by the worker only.
CREATE OR REPLACE FUNCTION apply_retention(p_now timestamptz, p_batch integer)
  RETURNS TABLE (run_id uuid)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  expired uuid[];
BEGIN
  SELECT array_agg(x.id) INTO expired FROM (
    SELECT r.id FROM runs r JOIN workspaces w ON w.id = r.workspace_id
     WHERE r.status IN ('done', 'failed', 'stopped')
       AND r.purged_at IS NULL
       AND r.finished_at < p_now - make_interval(days => w.retention_days)
     ORDER BY r.finished_at
     LIMIT p_batch
     FOR UPDATE OF r SKIP LOCKED
  ) x;
  DELETE FROM api_rate_windows WHERE window_start < p_now - interval '1 hour';
  IF expired IS NULL THEN
    RETURN;
  END IF;
  DELETE FROM steps s WHERE s.run_id = ANY (expired);
  UPDATE bugs b SET screenshot = NULL WHERE b.run_id = ANY (expired);
  UPDATE runs r SET purged_at = p_now WHERE r.id = ANY (expired);
  RETURN QUERY SELECT unnest(expired);
END
$$;

REVOKE EXECUTE ON FUNCTION claim_next_run(text, uuid[], boolean), renew_lease(uuid),
  recover_runs(integer), apply_retention(timestamptz, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION claim_next_run(text, uuid[], boolean), renew_lease(uuid),
  recover_runs(integer), apply_retention(timestamptz, integer) TO ata_worker;
REVOKE EXECUTE ON FUNCTION consume_quota(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consume_quota(uuid) TO app_tenant;
GRANT EXECUTE ON FUNCTION url_origin(text), app_current_user(), app_current_workspace() TO app_tenant;

-- ---------------------------------------------------------------------------------------------
-- 6. Triggers
-- ---------------------------------------------------------------------------------------------
-- updated_at: maintained by the database for every writer.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
  LANGUAGE plpgsql
  AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END
$$;

CREATE TRIGGER login_setups_updated_at BEFORE UPDATE ON login_setups
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER model_configs_updated_at BEFORE UPDATE ON model_configs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER finding_triage_updated_at BEFORE UPDATE ON finding_triage
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Triage carry-forward: a finding whose fingerprint the workspace marked a false positive on
-- this target is stored suppressed, in every later run, whoever inserts it.
CREATE OR REPLACE FUNCTION carry_triage_forward() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
BEGIN
  IF NEW.fingerprint IS NOT NULL AND EXISTS (
    SELECT 1 FROM runs r JOIN finding_triage t
      ON t.workspace_id = r.workspace_id AND t.origin = url_origin(r.target_url)
     WHERE r.id = NEW.run_id AND t.fingerprint = NEW.fingerprint AND t.state = 'false_positive'
  ) THEN
    NEW.suppressed := true;
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER bugs_carry_triage BEFORE INSERT OR UPDATE OF fingerprint ON bugs
  FOR EACH ROW EXECUTE FUNCTION carry_triage_forward();

-- The audit log, written by the database. Who: app.user_id. Extra context the app knows
-- (the visitor's IP, the API key): app.audit_metadata, a JSON object. Never a secret column's
-- value: only the names of what changed. SECURITY DEFINER so the row is written even though
-- the app roles may only append, and always in the changed row's own workspace.
CREATE OR REPLACE FUNCTION audit_change() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  entity text := TG_ARGV[0];
  rec jsonb := to_jsonb(CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END);
  old_rec jsonb := CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(OLD) ELSE NULL END;
  ws uuid;
  act text;
  meta jsonb := coalesce(NULLIF(current_setting('app.audit_metadata', true), '')::jsonb, '{}');
  url text;
  mode run_mode;
  run uuid;
BEGIN
  ws := CASE WHEN entity = 'workspace' THEN (rec ->> 'id')::uuid ELSE (rec ->> 'workspace_id')::uuid END;
  IF entity = 'run' THEN
    run := (rec ->> 'id')::uuid;
    IF TG_OP = 'INSERT' THEN
      act := 'run.started';
      url := rec ->> 'target_url';
      mode := (rec ->> 'mode')::run_mode;
    ELSIF old_rec ->> 'share_token' IS NULL AND rec ->> 'share_token' IS NOT NULL THEN
      act := 'share.created';
    ELSIF old_rec ->> 'share_token' IS NOT NULL AND rec ->> 'share_token' IS NULL THEN
      act := 'share.revoked';
    END IF;
  ELSIF entity = 'domain' THEN
    url := 'https://' || (rec ->> 'hostname');
    IF TG_OP = 'INSERT' THEN act := 'domain.added';
    ELSIF TG_OP = 'DELETE' THEN act := 'domain.deleted';
    ELSIF old_rec ->> 'verified_at' IS NULL AND rec ->> 'verified_at' IS NOT NULL THEN
      act := 'domain.verified';
      meta := meta || jsonb_build_object('method', rec ->> 'method');
    END IF;
  ELSIF entity = 'model' THEN
    meta := meta || jsonb_build_object('model', rec ->> 'model');
    IF TG_OP = 'INSERT' THEN act := 'model.added';
    ELSIF TG_OP = 'DELETE' THEN act := 'model.deleted';
    ELSIF old_rec ->> 'api_key_ciphertext' IS DISTINCT FROM rec ->> 'api_key_ciphertext' THEN
      act := 'model.key_replaced';
    END IF;
  ELSIF entity = 'login_setup' THEN
    meta := meta || jsonb_build_object('origin', rec ->> 'origin');
    IF TG_OP = 'DELETE' THEN act := 'login_setup.deleted';
    ELSIF TG_OP = 'INSERT' OR (old_rec - ARRAY['check_requested_at', 'last_check', 'updated_at'])
                               IS DISTINCT FROM (rec - ARRAY['check_requested_at', 'last_check', 'updated_at']) THEN
      act := 'login_setup.saved';
    END IF;
  ELSIF entity = 'api_key' THEN
    meta := meta || jsonb_build_object('name', rec ->> 'name', 'prefix', rec ->> 'prefix');
    IF TG_OP = 'INSERT' THEN act := 'api_key.created';
    ELSIF TG_OP = 'DELETE' THEN act := 'api_key.deleted';
    ELSIF old_rec ->> 'revoked_at' IS NULL AND rec ->> 'revoked_at' IS NOT NULL THEN
      act := 'api_key.revoked';
    END IF;
  ELSIF entity = 'webhook' THEN
    meta := meta || jsonb_build_object('url', rec ->> 'url');
    IF TG_OP = 'INSERT' THEN act := 'webhook.created';
    ELSIF TG_OP = 'DELETE' THEN act := 'webhook.deleted';
    ELSIF old_rec ->> 'enabled' IS DISTINCT FROM rec ->> 'enabled' THEN
      act := CASE WHEN (rec ->> 'enabled')::boolean THEN 'webhook.enabled' ELSE 'webhook.disabled' END;
    END IF;
  ELSIF entity = 'invitation' THEN
    meta := meta || jsonb_build_object('role', rec ->> 'role', 'id', rec ->> 'id');
    IF TG_OP = 'INSERT' THEN act := 'member.invited';
    ELSIF old_rec ->> 'revoked_at' IS NULL AND rec ->> 'revoked_at' IS NOT NULL THEN
      act := 'member.invitation_revoked';
    END IF;
  ELSIF entity = 'member' THEN
    meta := meta || jsonb_build_object('member', rec ->> 'email');
    IF TG_OP = 'INSERT' AND rec ->> 'workspace_id' IS NOT NULL THEN
      act := 'member.joined';
      meta := meta || jsonb_build_object('role', rec ->> 'role');
    ELSIF TG_OP = 'DELETE' THEN
      act := 'member.removed';
    ELSIF old_rec ->> 'workspace_id' IS DISTINCT FROM rec ->> 'workspace_id' THEN
      IF rec ->> 'workspace_id' IS NOT NULL THEN
        act := 'member.joined';
        meta := meta || jsonb_build_object('role', rec ->> 'role');
      END IF;
      IF old_rec ->> 'workspace_id' IS NOT NULL THEN  -- left the old workspace
        INSERT INTO audit_log (workspace_id, user_id, action, metadata)
        VALUES ((old_rec ->> 'workspace_id')::uuid, app_current_user(), 'member.removed',
                jsonb_build_object('member', rec ->> 'email'));
      END IF;
    ELSIF old_rec ->> 'role' IS DISTINCT FROM rec ->> 'role' THEN
      act := 'member.role_changed';
      meta := meta || jsonb_build_object('from', old_rec ->> 'role', 'to', rec ->> 'role');
    END IF;
  ELSIF entity = 'triage' THEN
    act := 'triage.changed';
    meta := meta || jsonb_build_object('fingerprint', rec ->> 'fingerprint', 'state', rec ->> 'state',
                                       'title', rec ->> 'title');
  ELSIF entity = 'workspace' THEN
    IF TG_OP = 'UPDATE' AND (old_rec ->> 'retention_days' IS DISTINCT FROM rec ->> 'retention_days'
                             OR old_rec ->> 'name' IS DISTINCT FROM rec ->> 'name') THEN
      act := 'workspace.settings_changed';
    END IF;
  END IF;

  IF act IS NOT NULL AND ws IS NOT NULL THEN
    INSERT INTO audit_log (workspace_id, user_id, action, target_url, mode, run_id, metadata)
    VALUES (ws, app_current_user(), act, url, mode, run, meta);
  END IF;
  RETURN NULL;
END
$$;

CREATE TRIGGER runs_audit AFTER INSERT OR UPDATE OF share_token ON runs
  FOR EACH ROW EXECUTE FUNCTION audit_change('run');
CREATE TRIGGER domains_audit AFTER INSERT OR UPDATE OR DELETE ON domains
  FOR EACH ROW EXECUTE FUNCTION audit_change('domain');
CREATE TRIGGER model_configs_audit AFTER INSERT OR UPDATE OR DELETE ON model_configs
  FOR EACH ROW EXECUTE FUNCTION audit_change('model');
CREATE TRIGGER login_setups_audit AFTER INSERT OR UPDATE OR DELETE ON login_setups
  FOR EACH ROW EXECUTE FUNCTION audit_change('login_setup');
CREATE TRIGGER api_keys_audit AFTER INSERT OR UPDATE OR DELETE ON api_keys
  FOR EACH ROW EXECUTE FUNCTION audit_change('api_key');
CREATE TRIGGER webhook_endpoints_audit AFTER INSERT OR UPDATE OR DELETE ON webhook_endpoints
  FOR EACH ROW EXECUTE FUNCTION audit_change('webhook');
CREATE TRIGGER invitations_audit AFTER INSERT OR UPDATE ON invitations
  FOR EACH ROW EXECUTE FUNCTION audit_change('invitation');
CREATE TRIGGER users_audit AFTER INSERT OR UPDATE OF role, workspace_id OR DELETE ON users
  FOR EACH ROW EXECUTE FUNCTION audit_change('member');
CREATE TRIGGER finding_triage_audit AFTER INSERT OR UPDATE ON finding_triage
  FOR EACH ROW EXECUTE FUNCTION audit_change('triage');
CREATE TRIGGER workspaces_audit AFTER UPDATE ON workspaces
  FOR EACH ROW EXECUTE FUNCTION audit_change('workspace');

-- ---------------------------------------------------------------------------------------------
-- 7. Views
-- ---------------------------------------------------------------------------------------------
-- Every finding a target has had, by fingerprint: when it was first and last seen, in how many
-- runs, its latest title and status, and its triage. security_invoker: the caller's row-level
-- security applies, so a tenant sees only its own history.
CREATE VIEW target_bug_history WITH (security_invoker = true) AS
SELECT r.workspace_id,
       url_origin(r.target_url) AS origin,
       b.fingerprint,
       (array_agg(b.title ORDER BY r.created_at DESC))[1] AS title,
       (array_agg(b.status ORDER BY r.created_at DESC))[1] AS latest_status,
       min(r.created_at) AS first_seen_at,  -- dated by the runs (the releases tested)
       max(r.created_at) AS last_seen_at,
       count(DISTINCT b.run_id)::integer AS runs_seen,
       (array_agg(b.run_id ORDER BY r.created_at DESC))[1] AS last_run_id,
       t.state AS triage_state
  FROM bugs b
  JOIN runs r ON r.id = b.run_id
  LEFT JOIN finding_triage t
    ON t.workspace_id = r.workspace_id AND t.origin = url_origin(r.target_url)
   AND t.fingerprint = b.fingerprint
 WHERE b.fingerprint IS NOT NULL AND b.duplicate_of_id IS NULL
 GROUP BY r.workspace_id, url_origin(r.target_url), b.fingerprint, t.state;

GRANT SELECT ON target_bug_history TO app_tenant;

-- The model leaderboard: one row per (provider, model, judge, reviewer) with its latest valid
-- benchmark result and how many results it has. Materialized: the benchmark page reads it on
-- every visit, results arrive a few times a day. Refresh strategy: a statement trigger on
-- benchmark_results refreshes it after every write, so it is never stale; results marked
-- details.invalid (a broken run kept for history) are left out.
CREATE MATERIALIZED VIEW model_leaderboard AS
SELECT DISTINCT ON (provider, model, judge, reviewer)
       provider, model, judge, reviewer,
       id AS latest_result_id, created_at AS latest_at, git_commit,
       ai_recall, recall, precision, false_alarms,
       holdout_ai_recall, holdout_recall, holdout_false_alarms,
       avg_cost_usd, avg_duration_s,
       count(*) OVER (PARTITION BY provider, model, judge, reviewer)::integer AS results
  FROM (SELECT *, details ->> 'reviewer' AS reviewer FROM benchmark_results
         WHERE NOT (details ? 'invalid')) valid
 ORDER BY provider, model, judge, reviewer, created_at DESC;

CREATE UNIQUE INDEX model_leaderboard_key
  ON model_leaderboard (coalesce(provider, ''), coalesce(model, ''), coalesce(judge, ''), coalesce(reviewer, ''));
GRANT SELECT ON model_leaderboard TO app_tenant;

CREATE OR REPLACE FUNCTION refresh_model_leaderboard() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
BEGIN
  REFRESH MATERIALIZED VIEW model_leaderboard;
  RETURN NULL;
END
$$;

CREATE TRIGGER benchmark_results_refresh_leaderboard
  AFTER INSERT OR UPDATE OR DELETE OR TRUNCATE ON benchmark_results
  FOR EACH STATEMENT EXECUTE FUNCTION refresh_model_leaderboard();

-- ---------------------------------------------------------------------------------------------
-- 8. Check constraints: fixed sets and ranges
-- ---------------------------------------------------------------------------------------------
ALTER TABLE runs
  ADD CONSTRAINT runs_counts_not_negative CHECK (
    pages_visited >= 0 AND step_count >= 0 AND input_tokens >= 0 AND output_tokens >= 0
    AND cost_usd >= 0 AND reviewer_input_tokens >= 0 AND reviewer_output_tokens >= 0
    AND reviewer_cost_usd >= 0),
  ADD CONSTRAINT runs_limits_in_range CHECK (
    (max_steps IS NULL OR max_steps BETWEEN 1 AND 500)
    AND (max_seconds IS NULL OR max_seconds BETWEEN 1 AND 86400)),
  ADD CONSTRAINT runs_finished_after_started CHECK (
    finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at);

ALTER TABLE steps
  ADD CONSTRAINT steps_counts_not_negative CHECK (
    index >= 0 AND input_tokens >= 0 AND output_tokens >= 0 AND cost_usd >= 0);

ALTER TABLE bugs
  ADD CONSTRAINT bugs_category_length CHECK (char_length(category) BETWEEN 1 AND 40),
  ADD CONSTRAINT bugs_title_not_empty CHECK (char_length(title) >= 1);

ALTER TABLE workspaces
  ADD CONSTRAINT workspaces_quota_not_negative CHECK (monthly_run_quota >= 0),
  ADD CONSTRAINT workspaces_retention_in_range CHECK (retention_days BETWEEN 1 AND 3650);

ALTER TABLE login_setups
  ADD CONSTRAINT login_setups_kind CHECK (kind IN ('form', 'storage_state'));

ALTER TABLE model_configs
  ADD CONSTRAINT model_configs_provider CHECK (provider IN ('claude', 'ollama', 'openai-compat', 'claude-cli')),
  ADD CONSTRAINT model_configs_prices_not_negative CHECK (
    (input_price IS NULL OR input_price >= 0) AND (output_price IS NULL OR output_price >= 0));

ALTER TABLE domains
  ADD CONSTRAINT domains_method CHECK (method IS NULL OR method IN ('dns', 'file'));

ALTER TABLE webhook_deliveries
  ADD CONSTRAINT webhook_deliveries_status CHECK (status IN ('pending', 'delivered', 'failed')),
  ADD CONSTRAINT webhook_deliveries_attempts_not_negative CHECK (attempts >= 0);

ALTER TABLE api_rate_windows
  ADD CONSTRAINT api_rate_windows_count_not_negative CHECK (count >= 0);

ALTER TABLE invitations
  ADD CONSTRAINT invitations_expire_after_creation CHECK (expires_at > created_at);

ALTER TABLE benchmark_results
  ADD CONSTRAINT benchmark_results_rates_in_range CHECK (
    (recall IS NULL OR recall BETWEEN 0 AND 1) AND (precision IS NULL OR precision BETWEEN 0 AND 1)
    AND (ai_recall IS NULL OR ai_recall BETWEEN 0 AND 1)
    AND (holdout_recall IS NULL OR holdout_recall BETWEEN 0 AND 1)
    AND (holdout_ai_recall IS NULL OR holdout_ai_recall BETWEEN 0 AND 1)
    AND (holdout_precision IS NULL OR holdout_precision BETWEEN 0 AND 1));

-- ---------------------------------------------------------------------------------------------
-- 9. Ownership: every table, view, sequence, type and function in public belongs to ata_owner
-- ---------------------------------------------------------------------------------------------
-- Only the owner (and a superuser) can change the schema or switch row-level security off. The
-- SECURITY DEFINER functions above run as their owner, which owns the tables and so is not
-- filtered by row-level security: that is what lets claim_next_run see every queued run.
DO $$
DECLARE
  obj record;
BEGIN
  IF current_user = 'ata_owner' THEN
    RETURN;  -- everything it created is already its own
  END IF;
  FOR obj IN
    SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'S')
  LOOP
    EXECUTE format('ALTER %s public.%I OWNER TO ata_owner',
      CASE obj.relkind WHEN 'r' THEN 'TABLE' WHEN 'v' THEN 'VIEW'
                       WHEN 'm' THEN 'MATERIALIZED VIEW' ELSE 'SEQUENCE' END, obj.relname);
  END LOOP;
  FOR obj IN
    SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
     WHERE n.nspname = 'public' AND t.typtype = 'e'
  LOOP
    EXECUTE format('ALTER TYPE public.%I OWNER TO ata_owner', obj.typname);
  END LOOP;
  FOR obj IN
    SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'public'
  LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO ata_owner', obj.sig);
  END LOOP;
END
$$;

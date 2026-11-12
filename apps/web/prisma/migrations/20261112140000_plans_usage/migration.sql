-- Run 5, K4: plans with limits, usage you could bill for (docs/DATABASE.md, "Plans and usage").
--
-- plans: what a workspace may do per month. Every workspace is on one (free by default).
-- usage_events: one row per finished run, written by a trigger, with the explorer's and the
-- reviewer's tokens and cost apart: the record a bill would be computed from.
-- consume_quota now enforces the plan (runs per month, allowed model providers, steps per run);
-- seats are enforced when an invitation is accepted, retention never exceeds the plan's.
-- The plan numbers are placeholders until the owner sets prices (DECISIONS D85).

CREATE TABLE "plans" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "runs_per_month" INTEGER NOT NULL,
    "max_steps_per_run" INTEGER NOT NULL,
    -- Model providers a run may use; empty = every provider.
    "allowed_providers" TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    "seats" INTEGER NOT NULL,
    "retention_days" INTEGER NOT NULL,
    -- What the plan would cost; no billing provider is connected (ROADMAP.md, "Billing").
    "price_usd_month" DOUBLE PRECISION,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "plans_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "plans_limits_in_range" CHECK (
      runs_per_month > 0 AND max_steps_per_run BETWEEN 1 AND 500 AND seats > 0
      AND retention_days BETWEEN 1 AND 3650 AND (price_usd_month IS NULL OR price_usd_month >= 0)),
    CONSTRAINT "plans_providers_known" CHECK (
      allowed_providers <@ ARRAY['claude', 'ollama', 'openai-compat', 'claude-cli']::TEXT[])
);

INSERT INTO "plans" (id, name, runs_per_month, max_steps_per_run, allowed_providers, seats, retention_days, price_usd_month) VALUES
  ('free', 'Free', 30, 40, ARRAY['ollama'], 3, 7, 0),
  ('team', 'Team', 300, 80, ARRAY[]::TEXT[], 10, 30, NULL),
  ('business', 'Business', 2000, 150, ARRAY[]::TEXT[], 50, 90, NULL);

ALTER TABLE "workspaces" ADD COLUMN "plan_id" TEXT NOT NULL DEFAULT 'free';
ALTER TABLE "workspaces" ADD CONSTRAINT "workspaces_plan_id_fkey"
  FOREIGN KEY ("plan_id") REFERENCES "plans"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- Operators of the service (not of a workspace): see usage across workspaces. Set from the
-- command line only (`worker make-admin <email>`), never from the web app.
ALTER TABLE "users" ADD COLUMN "is_platform_admin" BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE "usage_events" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),
    "workspace_id" UUID NOT NULL,
    "run_id" UUID,
    "kind" TEXT NOT NULL DEFAULT 'run',
    "explorer_provider" TEXT,
    "explorer_model" TEXT,
    "explorer_input_tokens" INTEGER NOT NULL DEFAULT 0,
    "explorer_output_tokens" INTEGER NOT NULL DEFAULT 0,
    "explorer_cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "reviewer_provider" TEXT,
    "reviewer_model" TEXT,
    "reviewer_input_tokens" INTEGER NOT NULL DEFAULT 0,
    "reviewer_output_tokens" INTEGER NOT NULL DEFAULT 0,
    "reviewer_cost_usd" DOUBLE PRECISION NOT NULL DEFAULT 0,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "usage_events_pkey" PRIMARY KEY ("id"),
    CONSTRAINT "usage_events_kind" CHECK (kind IN ('run')),
    CONSTRAINT "usage_events_not_negative" CHECK (
      explorer_input_tokens >= 0 AND explorer_output_tokens >= 0 AND explorer_cost_usd >= 0
      AND reviewer_input_tokens >= 0 AND reviewer_output_tokens >= 0 AND reviewer_cost_usd >= 0)
);
CREATE UNIQUE INDEX "usage_events_run_id_key" ON "usage_events"("run_id");
CREATE INDEX "usage_events_workspace_id_created_at_idx" ON "usage_events"("workspace_id", "created_at");
ALTER TABLE "usage_events" ADD CONSTRAINT "usage_events_workspace_id_fkey"
  FOREIGN KEY ("workspace_id") REFERENCES "workspaces"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "usage_events" ADD CONSTRAINT "usage_events_run_id_fkey"
  FOREIGN KEY ("run_id") REFERENCES "runs"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- Tenant data: each workspace reads only its own usage. Written only by the trigger below;
-- the apps can't insert, change or delete a billing record.
ALTER TABLE "usage_events" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "usage_events" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());
REVOKE INSERT, UPDATE, DELETE ON usage_events FROM app_tenant;
GRANT SELECT ON usage_events TO app_tenant;
-- Plans are public reference data (the pricing page would show them); only the owner edits them.
REVOKE INSERT, UPDATE, DELETE ON plans FROM app_tenant;
GRANT SELECT ON plans TO app_tenant;

-- One usage event per run, when it reaches a final status. Explorer = total minus reviewer.
CREATE OR REPLACE FUNCTION record_run_usage() RETURNS trigger
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
BEGIN
  INSERT INTO usage_events (workspace_id, run_id, explorer_provider, explorer_model,
      explorer_input_tokens, explorer_output_tokens, explorer_cost_usd,
      reviewer_provider, reviewer_model, reviewer_input_tokens, reviewer_output_tokens, reviewer_cost_usd)
  VALUES (NEW.workspace_id, NEW.id, NEW.provider, NEW.model,
      greatest(NEW.input_tokens - NEW.reviewer_input_tokens, 0),
      greatest(NEW.output_tokens - NEW.reviewer_output_tokens, 0),
      greatest(NEW.cost_usd - NEW.reviewer_cost_usd, 0),
      NEW.reviewer_provider, NEW.reviewer_model, NEW.reviewer_input_tokens,
      NEW.reviewer_output_tokens, NEW.reviewer_cost_usd)
  ON CONFLICT (run_id) DO NOTHING;
  RETURN NULL;
END
$$;

CREATE TRIGGER runs_record_usage AFTER UPDATE OF status ON runs
  FOR EACH ROW
  WHEN (OLD.status NOT IN ('done', 'failed', 'stopped') AND NEW.status IN ('done', 'failed', 'stopped'))
  EXECUTE FUNCTION record_run_usage();

-- consume_quota, now with the plan: runs per month (the lower of the plan's and the workspace's
-- own quota), the model provider, and the steps a run may take.
DROP FUNCTION consume_quota(uuid);
CREATE FUNCTION consume_quota(p_workspace uuid, p_provider text DEFAULT NULL)
  RETURNS TABLE (allowed boolean, used integer, quota integer, max_steps integer, reason text)
  LANGUAGE plpgsql
  AS $$
DECLARE
  ws_quota integer;
  plan plans%ROWTYPE;
  n integer;
BEGIN
  -- The lock on the workspace row is what makes check-and-use atomic.
  SELECT w.monthly_run_quota INTO ws_quota FROM workspaces w WHERE w.id = p_workspace FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'workspace % not found', p_workspace USING ERRCODE = 'no_data_found';
  END IF;
  SELECT p.* INTO plan FROM workspaces w JOIN plans p ON p.id = w.plan_id WHERE w.id = p_workspace;
  SELECT count(*) INTO n FROM runs r
   WHERE r.workspace_id = p_workspace AND r.created_at >= date_trunc('month', now());
  quota := least(ws_quota, plan.runs_per_month);
  used := n;
  max_steps := plan.max_steps_per_run;
  IF p_provider IS NOT NULL AND cardinality(plan.allowed_providers) > 0
     AND NOT p_provider = ANY (plan.allowed_providers) THEN
    allowed := false;
    reason := format('The %s plan doesn''t include %s models. Choose another model or change plan.', plan.name, p_provider);
  ELSE
    allowed := n < quota;
    reason := NULL;
  END IF;
  RETURN NEXT;
END
$$;
REVOKE EXECUTE ON FUNCTION consume_quota(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION consume_quota(uuid, text) TO app_tenant;

-- Retention: the workspace's setting, but never longer than its plan keeps data.
CREATE OR REPLACE FUNCTION apply_retention(p_now timestamptz, p_batch integer)
  RETURNS TABLE (run_id uuid)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  expired uuid[];
BEGIN
  SELECT array_agg(x.id) INTO expired FROM (
    SELECT r.id FROM runs r
      JOIN workspaces w ON w.id = r.workspace_id
      JOIN plans p ON p.id = w.plan_id
     WHERE r.status IN ('done', 'failed', 'stopped')
       AND r.purged_at IS NULL
       AND r.finished_at < p_now - make_interval(days => least(w.retention_days, p.retention_days))
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

-- Seats: accepting an invitation needs a free seat on the workspace's plan.
CREATE OR REPLACE FUNCTION accept_invitation(p_hash text, p_user uuid)
  RETURNS TABLE (workspace_id uuid, role workspace_role)
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
DECLARE
  inv invitations%ROWTYPE;
  member users%ROWTYPE;
  free_seats integer;
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
  -- Lock the workspace so two acceptances can't both take the last seat.
  SELECT p.seats - (SELECT count(*) FROM users u WHERE u.workspace_id = inv.workspace_id)
    INTO free_seats
    FROM workspaces w JOIN plans p ON p.id = w.plan_id
   WHERE w.id = inv.workspace_id FOR UPDATE OF w;
  IF free_seats <= 0 THEN
    RAISE EXCEPTION 'This workspace has no free seats on its plan. Ask an owner to change plan.'
      USING ERRCODE = 'P0001';
  END IF;
  PERFORM set_config('app.user_id', p_user::text, true);
  UPDATE users u SET workspace_id = inv.workspace_id, role = inv.role WHERE u.id = p_user;
  UPDATE invitations i SET accepted_at = now(), accepted_by_id = p_user WHERE i.id = inv.id;
  RETURN QUERY SELECT inv.workspace_id, inv.role;
END
$$;

-- Usage across every workspace, for the service's operators only (users.is_platform_admin).
CREATE OR REPLACE FUNCTION platform_usage(p_since timestamptz)
  RETURNS TABLE (workspace_id uuid, name text, slug text, plan_id text, members integer,
                 runs integer, explorer_cost_usd double precision, reviewer_cost_usd double precision,
                 input_tokens bigint, output_tokens bigint)
  LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
BEGIN
  IF NOT coalesce((SELECT u.is_platform_admin FROM users u WHERE u.id = app_current_user()), false) THEN
    RAISE EXCEPTION 'Only a platform admin can see usage across workspaces.' USING ERRCODE = 'P0001';
  END IF;
  RETURN QUERY
  SELECT w.id, w.name, w.slug, w.plan_id,
         (SELECT count(*)::integer FROM users u WHERE u.workspace_id = w.id),
         count(e.id)::integer,
         coalesce(sum(e.explorer_cost_usd), 0), coalesce(sum(e.reviewer_cost_usd), 0),
         coalesce(sum(e.explorer_input_tokens + e.reviewer_input_tokens), 0)::bigint,
         coalesce(sum(e.explorer_output_tokens + e.reviewer_output_tokens), 0)::bigint
    FROM workspaces w
    LEFT JOIN usage_events e ON e.workspace_id = w.id AND e.created_at >= p_since
   GROUP BY w.id
   ORDER BY count(e.id) DESC, w.name;
END
$$;
REVOKE EXECUTE ON FUNCTION platform_usage(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION platform_usage(timestamptz) TO ata_web;

DO $$
DECLARE
  obj text;
BEGIN
  IF current_user = 'ata_owner' THEN
    RETURN;
  END IF;
  ALTER TABLE plans OWNER TO ata_owner;
  ALTER TABLE usage_events OWNER TO ata_owner;
  FOREACH obj IN ARRAY ARRAY['record_run_usage()', 'consume_quota(uuid, text)', 'apply_retention(timestamptz, integer)',
                             'accept_invitation(text, uuid)', 'platform_usage(timestamptz)'] LOOP
    EXECUTE format('ALTER FUNCTION %s OWNER TO ata_owner', obj);
  END LOOP;
END
$$;

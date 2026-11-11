-- Run 4, J5: Postgres row-level security as a second line of defence behind the app's
-- "WHERE workspace_id = ..." checks (docs/DATABASE.md, "Row-level security").
--
-- The web app runs tenant queries as the role app_tenant, inside a transaction that first sets
-- app.workspace_id. The policies below then hide every other workspace's rows, even from a
-- query that forgot its WHERE clause. An unset workspace matches nothing (fail closed).
-- The owning role (migrations, the worker) is not app_tenant and is not affected.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_tenant') THEN
    CREATE ROLE app_tenant NOLOGIN NOBYPASSRLS;
  END IF;
END
$$;

-- The connecting role must be allowed to SET ROLE app_tenant (a superuser always is).
DO $$
BEGIN
  EXECUTE format('GRANT app_tenant TO %I', current_user);
EXCEPTION WHEN others THEN NULL; -- already a member, or a superuser
END
$$;

GRANT USAGE ON SCHEMA public TO app_tenant;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_tenant;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_tenant;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_tenant;

-- The current workspace of this transaction, or NULL when it wasn't set.
CREATE OR REPLACE FUNCTION app_current_workspace() RETURNS uuid
  LANGUAGE sql STABLE
  AS $$ SELECT NULLIF(current_setting('app.workspace_id', true), '')::uuid $$;

ALTER TABLE "workspaces" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "workspaces" TO app_tenant
  USING ("id" = app_current_workspace()) WITH CHECK ("id" = app_current_workspace());

ALTER TABLE "users" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "users" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "runs" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "runs" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "domains" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "domains" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "model_configs" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "model_configs" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "login_setups" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "login_setups" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "api_keys" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "api_keys" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "webhook_endpoints" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "webhook_endpoints" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "finding_triage" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "finding_triage" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "invitations" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "invitations" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

ALTER TABLE "audit_log" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "audit_log" TO app_tenant
  USING ("workspace_id" = app_current_workspace()) WITH CHECK ("workspace_id" = app_current_workspace());

-- steps belongs to a workspace through its parent row, which RLS already filters.
ALTER TABLE "steps" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "steps" TO app_tenant USING (EXISTS (SELECT 1 FROM runs r WHERE r.id = steps.run_id)) WITH CHECK (EXISTS (SELECT 1 FROM runs r WHERE r.id = steps.run_id));

-- bugs belongs to a workspace through its parent row, which RLS already filters.
ALTER TABLE "bugs" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "bugs" TO app_tenant USING (EXISTS (SELECT 1 FROM runs r WHERE r.id = bugs.run_id)) WITH CHECK (EXISTS (SELECT 1 FROM runs r WHERE r.id = bugs.run_id));

-- webhook_deliveries belongs to a workspace through its parent row, which RLS already filters.
ALTER TABLE "webhook_deliveries" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "webhook_deliveries" TO app_tenant USING (EXISTS (SELECT 1 FROM webhook_endpoints e WHERE e.id = webhook_deliveries.endpoint_id)) WITH CHECK (EXISTS (SELECT 1 FROM webhook_endpoints e WHERE e.id = webhook_deliveries.endpoint_id));

-- api_rate_windows belongs to a workspace through its parent row, which RLS already filters.
ALTER TABLE "api_rate_windows" ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "api_rate_windows" TO app_tenant USING (EXISTS (SELECT 1 FROM api_keys k WHERE k.id = api_rate_windows.api_key_id)) WITH CHECK (EXISTS (SELECT 1 FROM api_keys k WHERE k.id = api_rate_windows.api_key_id));

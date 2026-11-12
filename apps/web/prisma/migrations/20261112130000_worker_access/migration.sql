-- Run 5, K3: the worker's background jobs that look across workspaces, as narrow functions.
--
-- The worker (ata_worker) sees no tenant rows outside a run's workspace. Two jobs start from
-- "what is due anywhere": webhook deliveries and requested sign-in checks. These functions
-- return only ids and workspaces; each item is then locked and processed inside its own
-- workspace (worker/webhooks.py, worker/login_checks.py).

CREATE OR REPLACE FUNCTION due_webhook_deliveries(p_limit integer)
  RETURNS TABLE (id uuid, workspace_id uuid)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
  SELECT d.id, e.workspace_id
    FROM webhook_deliveries d JOIN webhook_endpoints e ON e.id = d.endpoint_id
   WHERE d.status = 'pending' AND d.next_attempt_at <= now()
   ORDER BY d.next_attempt_at
   LIMIT p_limit
$$;

CREATE OR REPLACE FUNCTION requested_login_checks(p_limit integer)
  RETURNS TABLE (id uuid, workspace_id uuid)
  LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public, pg_temp
  AS $$
  SELECT s.id, s.workspace_id FROM login_setups s
   WHERE s.check_requested_at IS NOT NULL
   ORDER BY s.check_requested_at
   LIMIT p_limit
$$;

REVOKE EXECUTE ON FUNCTION due_webhook_deliveries(integer), requested_login_checks(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION due_webhook_deliveries(integer), requested_login_checks(integer) TO ata_worker;

DO $$
BEGIN
  IF current_user <> 'ata_owner' THEN
    ALTER FUNCTION due_webhook_deliveries(integer) OWNER TO ata_owner;
    ALTER FUNCTION requested_login_checks(integer) OWNER TO ata_owner;
  END IF;
END
$$;

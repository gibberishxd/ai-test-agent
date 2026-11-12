"""The worker inside one workspace (run 5, K3).

The worker connects as ata_worker, which sees no tenant rows without a workspace (row-level
security, fail closed). Once a run is claimed, its session is tied to the run's workspace:
every transaction the session begins first does

    SELECT set_config('app.workspace_id', <id>, true)   -- for this transaction only
    SET LOCAL ROLE app_tenant                           -- the role the policies apply to

so run code reads and writes only that workspace's rows, whatever its queries say. The few
things that span workspaces (claiming, lease recovery, retention, finding due webhooks and
login checks) are database functions (docs/DATABASE.md).
"""

import uuid

from sqlalchemy import event, text
from sqlalchemy.orm import Session

TENANT_KEY = "workspace_id"


def enter_tenant(session: Session, workspace_id: uuid.UUID | str) -> None:
    """Tie `session` to one workspace, from its next transaction on (and the current one)."""
    session.info[TENANT_KEY] = str(workspace_id)
    if session.in_transaction():
        _apply(session)


def leave_tenant(session: Session) -> None:
    session.info.pop(TENANT_KEY, None)


def _apply(session: Session) -> None:
    session.execute(
        text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": session.info[TENANT_KEY]}
    )
    session.execute(text("SET LOCAL ROLE app_tenant"))


@event.listens_for(Session, "after_begin")
def _set_tenant(session: Session, transaction, connection) -> None:
    workspace_id = session.info.get(TENANT_KEY)
    if workspace_id is None:
        return
    connection.execute(
        text("SELECT set_config('app.workspace_id', :ws, true)"), {"ws": workspace_id}
    )
    connection.execute(text("SET LOCAL ROLE app_tenant"))

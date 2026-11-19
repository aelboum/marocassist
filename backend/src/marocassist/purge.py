"""What happens to MarocAssist data when SaaS-OS purges a tenant.

Contract (`saas_os.core.tenancy.TenantPurgeParticipant`): idempotent, and
reports failure by raising. Core purges its own rows (service accounts,
API keys, memberships, roles) itself; this participant removes the
product's rows. The registry is per process: `create_app()` registers it,
and the operator command does with
`--setup marocassist.purge:register_purge_participants`.
"""

from __future__ import annotations

import uuid

from saas_os.core.tenancy import register_purge_participant
from saas_os.infra.db import delete, session_scope

from marocassist.accounts.models import PersonalWorkspace
from marocassist.accounts.workspace_settings import delete_for_tenant


class AccountsPurgeParticipant:
    @property
    def name(self) -> str:
        return "marocassist.accounts"

    def purge_tenant_data(self, tenant_id: uuid.UUID) -> None:
        delete_for_tenant(tenant_id)
        # Global lookup row (no RLS, see accounts.models): keyed by tenant.
        with session_scope() as session:
            session.execute(
                delete(PersonalWorkspace).where(PersonalWorkspace.tenant_id == tenant_id)
            )


ACCOUNTS_PURGE_PARTICIPANT = AccountsPurgeParticipant()


def register_purge_participants() -> None:
    register_purge_participant(ACCOUNTS_PURGE_PARTICIPANT)

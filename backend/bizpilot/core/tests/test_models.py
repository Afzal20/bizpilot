from __future__ import annotations

import uuid

import pytest

from bizpilot.core.models import AuditLog
from bizpilot.users.models import User


@pytest.mark.django_db
def test_audit_log_creation():
    user = User.objects.create_user(
        email="auditor@example.com",
        password="test-password-123!",  # noqa: S106
    )
    org_id = uuid.uuid4()

    log = AuditLog.objects.create(
        organization_id=org_id,
        actor=user,
        actor_email=user.email,
        action="invoice.create",
        target_model="Invoice",
        target_id="inv-12345",
        changes_diff={"total": "100.00"},
        ip_address="127.0.0.1",
        user_agent="TestAgent/1.0",
    )

    assert log.id is not None
    assert log.actor == user
    assert log.actor_email == "auditor@example.com"
    assert log.organization_id == org_id
    assert log.action == "invoice.create"
    assert log.changes_diff == {"total": "100.00"}
    assert "invoice.create" in str(log)

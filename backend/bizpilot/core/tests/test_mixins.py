from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIRequestFactory

from bizpilot.core.mixins import log_audit_event
from bizpilot.core.models import AuditLog
from bizpilot.users.models import User


class DummyTarget:
    pk = 42
    id = 42
    organization_id = uuid.uuid4()


@pytest.mark.django_db
def test_log_audit_event():
    factory = APIRequestFactory()
    request = factory.post("/api/v1/items/")
    user = User.objects.create_user(
        email="actor@example.com",
        password="test-password-123!",  # noqa: S106
    )
    request.user = user

    target = DummyTarget()
    entry = log_audit_event(
        request=request,
        action="update",
        target=target,
        changes_diff={"title": "New Title"},
    )

    assert entry.action == "update"
    assert entry.actor == user
    assert entry.actor_email == "actor@example.com"
    assert entry.target_id == "42"
    assert entry.changes_diff == {"title": "New Title"}
    assert AuditLog.objects.count() == 1

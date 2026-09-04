from __future__ import annotations

from typing import Any
import uuid

from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import PermissionDenied

from bizpilot.orgs.models import Organization
from bizpilot.orgs.permissions import OrgPermission
from bizpilot.orgs.permissions import get_org_id_from_request_or_view


class OrgScopedViewSet(viewsets.ModelViewSet):
    """
    Base ViewSet for multi-tenant ERP and organizational resources.
    Enforces tenant isolation, auto-filtering querysets by organization_id,
    and granular RBAC v2 action permission checks.
    """

    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    permission_map: dict[str, str] = {}

    def get_organization_id(self) -> uuid.UUID:
        """Extract and validate the current organization UUID from request context."""
        raw_id = get_org_id_from_request_or_view(self.request, self)
        if not raw_id:
            raise NotFound("Organization context is required for this operation.")
        try:
            return uuid.UUID(str(raw_id))
        except ValueError:
            raise NotFound("Invalid organization identifier.")

    def get_organization(self) -> Organization:
        """Retrieve the Organization model instance for the active scope."""
        org_id = self.get_organization_id()
        return get_object_or_404(Organization, id=org_id, is_active=True)

    def get_queryset(self) -> Any:
        """Scope base queryset to the active organization."""
        org_id = self.get_organization_id()
        base_qs = super().get_queryset()
        if hasattr(base_qs.model, "organization_id"):
            return base_qs.filter(organization_id=org_id)
        if hasattr(base_qs.model, "organization"):
            return base_qs.filter(organization=org_id)
        return base_qs

    def perform_create(self, serializer: Any) -> None:
        """Inject active organization into created entity if applicable."""
        org_id = self.get_organization_id()
        model_class = getattr(serializer.Meta, "model", None)
        if model_class and hasattr(model_class, "organization_id"):
            serializer.save(organization_id=org_id)
        elif model_class and hasattr(model_class, "organization"):
            serializer.save(organization=self.get_organization())
        else:
            serializer.save()

from __future__ import annotations

import json
from typing import Any

import stripe
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from bizpilot.billing.api.serializers import CheckoutRequestSerializer
from bizpilot.billing.api.serializers import PlanSerializer
from bizpilot.billing.api.serializers import PortalRequestSerializer
from bizpilot.billing.api.serializers import SubscriptionSerializer
from bizpilot.billing.engine import get_or_create_free_subscription
from bizpilot.billing.engine import seed_default_plans
from bizpilot.billing.engine import usage_summary
from bizpilot.billing.models import Plan
from bizpilot.billing.services import create_checkout_session
from bizpilot.billing.services import create_customer_portal_session
from bizpilot.billing.services import process_stripe_event
from bizpilot.billing.services import sync_checkout_session
from bizpilot.orgs.models import Organization
from bizpilot.orgs.permissions import IsOrgMember


class PlanListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PlanSerializer

    def get_queryset(self) -> Any:
        if not Plan.objects.filter(is_active=True).exists():
            seed_default_plans()
        return (
            Plan.objects.filter(is_active=True)
            .prefetch_related("entitlements", "prices")
            .order_by("tier")
        )


class SubscriptionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        sub = get_or_create_free_subscription(org)
        serializer = SubscriptionSerializer(sub)
        usage = usage_summary(org)
        data = {**serializer.data, "usage": usage}
        return Response(data)


class CreateCheckoutSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_email = request.user.email if request.user else None
        try:
            res = create_checkout_session(
                organization=org,
                price_id=serializer.validated_data["price_id"],
                success_url=serializer.validated_data["success_url"],
                cancel_url=serializer.validated_data["cancel_url"],
                customer_email=user_email,
            )
            return Response(res, status=status.HTTP_200_OK)
        except stripe.error.StripeError as err:
            return Response(
                {"detail": str(getattr(err, "user_message", None) or err)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            return Response(
                {"detail": str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class SyncCheckoutSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        session_id = request.data.get("session_id", "").strip()
        if not session_id:
            return Response(
                {"detail": "session_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            sub = sync_checkout_session(session_id, organization=org)
            if not sub:
                return Response(
                    {"detail": "Subscription could not be synced."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"status": "synced", "plan": sub.plan.code},
                status=status.HTTP_200_OK,
            )
        except stripe.error.StripeError as err:
            return Response(
                {"detail": str(getattr(err, "user_message", None) or err)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as err:
            return Response(
                {"detail": str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class CreateCustomerPortalView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def post(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        serializer = PortalRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            res = create_customer_portal_session(
                organization=org,
                return_url=serializer.validated_data["return_url"],
            )
            return Response(res, status=status.HTTP_200_OK)
        except ValueError as err:
            return Response(
                {"detail": str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class StripeWebhookView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request: Any) -> Response:
        payload = request.body
        sig_header = request.headers.get("Stripe-Signature", "")
        webhook_secret = getattr(
            settings,
            "STRIPE_WEBHOOK_SECRET",
            "whsec_placeholder",
        )

        try:
            if sig_header and webhook_secret != "whsec_placeholder":  # noqa: S105
                event = stripe.Webhook.construct_event(
                    payload,
                    sig_header,
                    webhook_secret,
                )
            else:
                event = json.loads(payload.decode("utf-8"))
        except (
            ValueError,
            json.JSONDecodeError,
            stripe.SignatureVerificationError,
        ) as err:
            return Response(
                {"error": str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        process_stripe_event(event)
        return Response({"status": "received"}, status=status.HTTP_200_OK)

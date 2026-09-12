from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from bizpilot.ai.agent import run_agent
from bizpilot.ai.api.serializers import AgentSerializer
from bizpilot.ai.api.serializers import AILogSerializer
from bizpilot.ai.api.serializers import AskBizPilotSerializer
from bizpilot.ai.api.serializers import CategorizeExpenseSerializer
from bizpilot.ai.api.serializers import DraftPaymentReminderSerializer
from bizpilot.ai.api.serializers import GenerateInvoiceItemsSerializer
from bizpilot.ai.gateway import AiUnavailableError
from bizpilot.ai.models import AILog
from bizpilot.ai.services import ask_bizpilot
from bizpilot.ai.services import categorize_expense
from bizpilot.ai.services import draft_payment_reminder
from bizpilot.ai.services import generate_invoice_items
from bizpilot.ai.services import stream_bizpilot
from bizpilot.erp.models import Invoice
from bizpilot.orgs.models import Organization
from bizpilot.orgs.permissions import OrgPermission


class GenerateInvoiceItemsView(APIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    permission_map = {"post": "ai.generate"}

    def post(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        serializer = GenerateInvoiceItemsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            items = generate_invoice_items(
                organization=org,
                prompt=serializer.validated_data["prompt"],
                currency=serializer.validated_data.get("currency"),
                user=request.user,
            )
            return Response({"items": items}, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response(
                {"error": err.message if hasattr(err, "message") else str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AiUnavailableError as err:
            return Response(
                {"error": str(err)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class AskBizPilotView(APIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    permission_map = {"post": "ai.use_assistant"}

    def post(self, request: Any, org_id: str) -> Any:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        serializer = AskBizPilotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        is_stream = serializer.validated_data.get("stream", False)
        question = serializer.validated_data["question"]
        history = serializer.validated_data.get("history", [])

        try:
            if is_stream:
                generator = stream_bizpilot(
                    organization=org,
                    question=question,
                    user=request.user,
                    history=history,
                )
                response = StreamingHttpResponse(
                    generator,
                    content_type="text/event-stream",
                )
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Buffering"] = "no"
                return response

            answer = ask_bizpilot(
                organization=org,
                question=question,
                user=request.user,
                history=history,
            )
            return Response({"answer": answer}, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response(
                {"error": err.message if hasattr(err, "message") else str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class RunAgentView(APIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    permission_map = {"post": "ai.use_assistant"}

    def post(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        serializer = AgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            res = run_agent(
                organization=org,
                instruction=serializer.validated_data["instruction"],
                confirm=serializer.validated_data.get("confirm", False),
                history=serializer.validated_data.get("history", []),
                user=request.user,
            )
            return Response(res, status=status.HTTP_200_OK)
        except ValidationError as err:
            return Response(
                {"error": err.message if hasattr(err, "message") else str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except AiUnavailableError as err:
            return Response(
                {"error": str(err)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class CategorizeExpenseView(APIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    permission_map = {"post": "ai.generate"}

    def post(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        serializer = CategorizeExpenseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        res = categorize_expense(
            organization=org,
            title=serializer.validated_data["title"],
            description=serializer.validated_data.get("description", ""),
            user=request.user,
        )
        return Response(res, status=status.HTTP_200_OK)


class DraftPaymentReminderView(APIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    permission_map = {"post": "ai.generate"}

    def post(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        serializer = DraftPaymentReminderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        invoice = get_object_or_404(
            Invoice,
            id=serializer.validated_data["invoice_id"],
            organization=org,
        )

        res = draft_payment_reminder(
            organization=org,
            invoice=invoice,
            tone=serializer.validated_data.get("tone", "friendly"),
            user=request.user,
        )
        return Response(res, status=status.HTTP_200_OK)


class AILogListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    serializer_class = AILogSerializer
    permission_map = {"get": "ai.use_assistant"}

    def get_queryset(self) -> Any:
        org_id = self.kwargs.get("org_id")
        return AILog.objects.filter(organization_id=org_id).order_by(
            "-created_at",
        )

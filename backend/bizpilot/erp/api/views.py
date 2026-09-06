from __future__ import annotations

from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import filters
from rest_framework import permissions
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from bizpilot.billing.engine import allow
from bizpilot.billing.engine import enforce
from bizpilot.erp.api.serializers import AdjustStockSerializer
from bizpilot.erp.api.serializers import ClientSerializer
from bizpilot.erp.api.serializers import ClientWithStatsSerializer
from bizpilot.erp.api.serializers import ExpenseSerializer
from bizpilot.erp.api.serializers import InvoiceSerializer
from bizpilot.erp.api.serializers import PaymentCreateSerializer
from bizpilot.erp.api.serializers import ProductSerializer
from bizpilot.erp.models import Client
from bizpilot.erp.models import Expense
from bizpilot.erp.models import Invoice
from bizpilot.erp.models import Payment
from bizpilot.erp.models import Product
from bizpilot.erp.services import PaymentDetails
from bizpilot.erp.services import adjust_product_stock
from bizpilot.erp.services import cancel_invoice
from bizpilot.erp.services import get_client_stats
from bizpilot.erp.services import get_dashboard_stats
from bizpilot.erp.services import get_report_data
from bizpilot.erp.services import global_org_search
from bizpilot.erp.services import record_invoice_payment
from bizpilot.erp.services import send_invoice
from bizpilot.orgs.models import Organization
from bizpilot.orgs.permissions import IsOrgMember
from bizpilot.orgs.permissions import OrgPermission
from bizpilot.orgs.viewsets import OrgScopedViewSet


class ClientViewSet(OrgScopedViewSet):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "email", "company", "phone"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    permission_map = {
        "list": "clients.view",
        "retrieve": "clients.view",
        "create": "clients.create",
        "update": "clients.edit",
        "partial_update": "clients.edit",
        "destroy": "clients.delete",
        "stats": "clients.view",
    }

    def get_serializer_class(self) -> type[Any]:
        if self.request.query_params.get("with_stats") == "true" or (
            self.action == "list" and self.request.query_params.get("with_stats") != "false"
        ):
            return ClientWithStatsSerializer
        return ClientSerializer

    @action(detail=True, methods=["get"])
    def stats(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        client = self.get_object()
        stats_data = get_client_stats(client)
        return Response(stats_data)

    def perform_create(self, serializer: Any) -> None:
        org = self.get_organization()
        enforce(org, "max_clients")
        super().perform_create(serializer)


class ProductViewSet(OrgScopedViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "sku", "category", "description"]
    ordering_fields = ["name", "unit_price", "stock_quantity", "created_at"]
    ordering = ["name"]
    permission_map = {
        "list": "products.view",
        "retrieve": "products.view",
        "create": "products.create",
        "update": "products.edit",
        "partial_update": "products.edit",
        "destroy": "products.delete",
        "adjust_stock": "products.adjust_stock",
    }

    @action(detail=True, methods=["post"], url_path="adjust-stock")
    def adjust_stock(
        self,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        product = self.get_object()
        serializer = AdjustStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_product = adjust_product_stock(
            product,
            serializer.validated_data["quantity_delta"],
            reason=serializer.validated_data.get("reason", ""),
            actor=request.user,
        )
        return Response(ProductSerializer(updated_product).data)

    def perform_create(self, serializer: Any) -> None:
        org = self.get_organization()
        enforce(org, "max_products")
        super().perform_create(serializer)


class InvoiceViewSet(OrgScopedViewSet):
    queryset = Invoice.objects.prefetch_related("items", "payments").select_related(
        "client",
    )
    serializer_class = InvoiceSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["invoice_number", "client_name", "client_email"]
    ordering_fields = ["issue_date", "due_date", "total", "created_at"]
    ordering = ["-created_at"]
    permission_map = {
        "list": "invoices.view",
        "retrieve": "invoices.view",
        "create": "invoices.create",
        "update": "invoices.edit",
        "partial_update": "invoices.edit",
        "destroy": "invoices.delete",
        "send": "invoices.send",
        "cancel": "invoices.cancel",
        "add_payment": "invoices.record_payment",
        "record_payment": "invoices.record_payment",
    }

    def perform_create(self, serializer: Any) -> None:
        org = self.get_organization()
        enforce(org, "max_invoices_per_month")
        super().perform_create(serializer)

    def get_queryset(self) -> Any:
        qs = super().get_queryset()
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)
        client_param = self.request.query_params.get("client_id")
        if client_param:
            qs = qs.filter(client_id=client_param)
        return qs

    @action(detail=True, methods=["post"])
    def send(
        self,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        invoice = self.get_object()
        allow(invoice.organization, "email_invoice_delivery")
        updated = send_invoice(invoice, actor=request.user)
        try:
            from bizpilot.core.tasks import send_invoice_email_task  # noqa: PLC0415
            send_invoice_email_task.delay(str(updated.id))
        except Exception:
            pass
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(
        self,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        from django.http import HttpResponse  # noqa: PLC0415
        from bizpilot.erp.pdf import generate_invoice_pdf  # noqa: PLC0415

        invoice = self.get_object()
        pdf_bytes = generate_invoice_pdf(invoice)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{invoice.invoice_number}.pdf"'
        return response

    @action(detail=True, methods=["post"])
    def cancel(
        self,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        invoice = self.get_object()
        updated = cancel_invoice(invoice, actor=request.user)
        return Response(self.get_serializer(updated).data)

    @action(detail=True, methods=["post"], url_path="payments")
    def add_payment(
        self,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        invoice = self.get_object()
        serializer = PaymentCreateSerializer(
            data={**request.data, "invoice": invoice.id},
        )
        serializer.is_valid(raise_exception=True)

        user = request.user if request.user.is_authenticated else None
        details = PaymentDetails(
            payment_method=serializer.validated_data.get(
                "payment_method",
                Payment.PaymentMethod.BANK_TRANSFER,
            ),
            payment_date=serializer.validated_data.get("payment_date"),
            reference=serializer.validated_data.get("reference", ""),
            notes=serializer.validated_data.get("notes", ""),
            recorded_by=user,
        )
        payment = record_invoice_payment(
            invoice,
            serializer.validated_data["amount"],
            details=details,
        )
        try:
            from bizpilot.core.tasks import send_payment_receipt_email_task  # noqa: PLC0415
            send_payment_receipt_email_task.delay(str(payment.id))
        except Exception:
            pass
        return Response(
            PaymentCreateSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="record-payment")
    def record_payment(
        self,
        request: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        return self.add_payment(request, *args, **kwargs)


class PaymentViewSet(OrgScopedViewSet):
    queryset = Payment.objects.select_related("invoice")
    serializer_class = PaymentCreateSerializer
    permission_map = {
        "list": "payments.view",
        "retrieve": "payments.view",
        "create": "payments.create",
        "destroy": "payments.delete",
    }

    def perform_create(self, serializer: Any) -> None:
        invoice = serializer.validated_data["invoice"]
        user = self.request.user if self.request.user.is_authenticated else None
        details = PaymentDetails(
            payment_method=serializer.validated_data.get(
                "payment_method",
                Payment.PaymentMethod.BANK_TRANSFER,
            ),
            payment_date=serializer.validated_data.get("payment_date"),
            reference=serializer.validated_data.get("reference", ""),
            notes=serializer.validated_data.get("notes", ""),
            recorded_by=user,
        )
        payment = record_invoice_payment(
            invoice,
            serializer.validated_data["amount"],
            details=details,
        )
        serializer.instance = payment
        try:
            from bizpilot.core.tasks import send_payment_receipt_email_task  # noqa: PLC0415
            send_payment_receipt_email_task.delay(str(payment.id))
        except Exception:
            pass


class ExpenseViewSet(OrgScopedViewSet):
    queryset = Expense.objects.all()
    serializer_class = ExpenseSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["title", "vendor", "category"]
    ordering_fields = ["expense_date", "amount", "created_at"]
    ordering = ["-expense_date"]
    permission_map = {
        "list": "expenses.view",
        "retrieve": "expenses.view",
        "create": "expenses.create",
        "update": "expenses.edit",
        "partial_update": "expenses.edit",
        "destroy": "expenses.delete",
    }


class DashboardStatsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    required_permission = "reports.view"

    def get(
        self,
        request: Any,
        org_id: str,
    ) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        stats_data = get_dashboard_stats(org)
        return Response(stats_data)


class ReportsAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, OrgPermission]
    required_permission = "reports.view"

    def get(
        self,
        request: Any,
        org_id: str,
    ) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        report_data = get_report_data(org)
        return Response(report_data)


class GlobalSearchAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsOrgMember]

    def get(self, request: Any, org_id: str) -> Response:
        org = get_object_or_404(Organization, id=org_id, is_active=True)
        q = request.query_params.get("q", "")
        results = global_org_search(org, q)
        return Response(results)

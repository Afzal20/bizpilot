from __future__ import annotations

from typing import Any

from django.http import Http404, HttpResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from bizpilot.erp.api.serializers import InvoiceSerializer
from bizpilot.erp.models import Invoice
from bizpilot.erp.pdf import generate_invoice_pdf


class PublicInvoiceDetailAPIView(APIView):
    """Public read-only invoice endpoint accessible to clients without authentication."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request: Any, pk: str, *args: Any, **kwargs: Any) -> Response:
        try:
            invoice = (
                Invoice.objects.select_related("client", "organization")
                .prefetch_related("items", "payments")
                .get(id=pk)
            )
        except (Invoice.DoesNotExist, ValueError):
            raise Http404("Invoice not found")

        serializer = InvoiceSerializer(invoice)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PublicInvoicePdfAPIView(APIView):
    """Public PDF download/streaming endpoint for invoices."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request: Any, pk: str, *args: Any, **kwargs: Any) -> HttpResponse:
        try:
            invoice = (
                Invoice.objects.select_related("client", "organization")
                .prefetch_related("items")
                .get(id=pk)
            )
        except (Invoice.DoesNotExist, ValueError):
            raise Http404("Invoice not found")

        pdf_bytes = generate_invoice_pdf(invoice)
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{invoice.invoice_number}.pdf"'
        return response

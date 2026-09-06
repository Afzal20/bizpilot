from __future__ import annotations

from django.urls import include
from django.urls import path
from rest_framework.routers import SimpleRouter

from bizpilot.erp.api.public_views import PublicInvoiceDetailAPIView
from bizpilot.erp.api.public_views import PublicInvoicePdfAPIView
from bizpilot.erp.api.views import ClientViewSet
from bizpilot.erp.api.views import DashboardStatsAPIView
from bizpilot.erp.api.views import ExpenseViewSet
from bizpilot.erp.api.views import GlobalSearchAPIView
from bizpilot.erp.api.views import InvoiceViewSet
from bizpilot.erp.api.views import PaymentViewSet
from bizpilot.erp.api.views import ProductViewSet
from bizpilot.erp.api.views import ReportsAPIView

app_name = "erp"

clients_router = SimpleRouter()
clients_router.register("clients", ClientViewSet, basename="org-clients")

products_router = SimpleRouter()
products_router.register("products", ProductViewSet, basename="org-products")

invoices_router = SimpleRouter()
invoices_router.register("invoices", InvoiceViewSet, basename="org-invoices")

payments_router = SimpleRouter()
payments_router.register("payments", PaymentViewSet, basename="org-payments")

expenses_router = SimpleRouter()
expenses_router.register("expenses", ExpenseViewSet, basename="org-expenses")

urlpatterns = [
    path("orgs/<uuid:org_id>/", include(clients_router.urls)),
    path("orgs/<uuid:org_id>/", include(products_router.urls)),
    path("orgs/<uuid:org_id>/", include(invoices_router.urls)),
    path("orgs/<uuid:org_id>/", include(payments_router.urls)),
    path("orgs/<uuid:org_id>/", include(expenses_router.urls)),
    path(
        "orgs/<uuid:org_id>/dashboard/stats/",
        DashboardStatsAPIView.as_view(),
        name="dashboard-stats",
    ),
    path(
        "orgs/<uuid:org_id>/reports/",
        ReportsAPIView.as_view(),
        name="reports",
    ),
    path(
        "orgs/<uuid:org_id>/search/",
        GlobalSearchAPIView.as_view(),
        name="search",
    ),
    path(
        "public/invoices/<uuid:pk>/",
        PublicInvoiceDetailAPIView.as_view(),
        name="public-invoice-detail",
    ),
    path(
        "public/invoices/<uuid:pk>/pdf/",
        PublicInvoicePdfAPIView.as_view(),
        name="public-invoice-pdf",
    ),
]

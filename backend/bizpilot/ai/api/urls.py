from __future__ import annotations

from django.urls import path

from bizpilot.ai.api.views import AILogListView
from bizpilot.ai.api.views import AskBizPilotView
from bizpilot.ai.api.views import CategorizeExpenseView
from bizpilot.ai.api.views import DraftPaymentReminderView
from bizpilot.ai.api.views import GenerateInvoiceItemsView

app_name = "ai"

urlpatterns = [
    path(
        "orgs/<uuid:org_id>/ai/generate-items/",
        GenerateInvoiceItemsView.as_view(),
        name="generate-items",
    ),
    path(
        "orgs/<uuid:org_id>/ai/assistant/",
        AskBizPilotView.as_view(),
        name="assistant",
    ),
    path(
        "orgs/<uuid:org_id>/ai/categorize-expense/",
        CategorizeExpenseView.as_view(),
        name="categorize-expense",
    ),
    path(
        "orgs/<uuid:org_id>/ai/draft-reminder/",
        DraftPaymentReminderView.as_view(),
        name="draft-reminder",
    ),
    path(
        "orgs/<uuid:org_id>/ai/logs/",
        AILogListView.as_view(),
        name="ai-logs",
    ),
]

"""
URL routing for the transactions API.
"""

from django.urls import path

from . import views

app_name = "transactions"

urlpatterns = [
    # Chat UI
    path("chat/", views.chat_ui, name="chat"),
    path("chat/reconciliation/", views.chat_reconciliation_proxy, name="chat-reconciliation-proxy"),
    # Health
    path("health/", views.health_check, name="health"),
    # Auth
    path("login/", views.merchant_login, name="login"),
    # Fee profiles
    path("fee-profile/<str:phone_number>/", views.get_fee_profile, name="fee-profile"),
    path("fee-profiles/", views.list_fee_profiles, name="fee-profiles"),
    # Settlements
    path(
        "settlement/<str:settlement_id>/",
        views.get_settlement,
        name="settlement-detail",
    ),
    path("settlements/", views.list_settlements, name="settlement-list"),
    # Transactions
    path("", views.list_transactions, name="transaction-list"),
    # Reconciliation Issues
    path("issues/", views.reconciliation_issues, name="reconciliation-issues"),
    path(
        "issues/<str:issue_id>/",
        views.reconciliation_issue_detail,
        name="reconciliation-issue-detail",
    ),
]

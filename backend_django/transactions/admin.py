"""
Admin registration for transaction models.
"""

from django.contrib import admin

from .models import ReconciliationIssue, MerchantFeeProfile, Settlement, Transaction


@admin.register(MerchantFeeProfile)
class MerchantFeeProfileAdmin(admin.ModelAdmin):
    list_display = ["merchant_id", "merchant_name", "mdr_rate", "gst_rate", "is_active"]
    list_filter = ["is_active", "settlement_cycle"]
    search_fields = ["merchant_id", "merchant_name"]


@admin.register(Settlement)
class SettlementAdmin(admin.ModelAdmin):
    list_display = [
        "settlement_id",
        "merchant",
        "gross_amount",
        "net_payout",
        "status",
        "settlement_date",
    ]
    list_filter = ["status", "settlement_date"]
    search_fields = ["settlement_id"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "transaction_id",
        "merchant",
        "amount",
        "mode",
        "is_refund",
        "transaction_date",
    ]
    list_filter = ["mode", "is_refund"]
    search_fields = ["transaction_id", "customer_name"]


@admin.register(ReconciliationIssue)
class ReconciliationIssueAdmin(admin.ModelAdmin):
    list_display = [
        "issue_id",
        "title",
        "merchant",
        "severity",
        "status",
        "created_at",
    ]
    list_filter = ["severity", "status"]
    search_fields = ["issue_id", "title"]

"""
REST serializers for transaction models.
"""

from rest_framework import serializers

from .models import ReconciliationIssue, MerchantFeeProfile, Settlement, Transaction


class MerchantFeeProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = MerchantFeeProfile
        fields = [
            "phone_number",
            "merchant_id",
            "merchant_name",
            "mdr_rate",
            "gst_rate",
            "amc_fees",
            "settlement_cycle",
            "is_active",
            "created_at",
            "updated_at",
        ]


class TransactionSerializer(serializers.ModelSerializer):
    settlement_id = serializers.CharField(source="settlement.settlement_id", read_only=True)
    phone_number = serializers.CharField(source="merchant.phone_number", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "transaction_id",
            "settlement_id",
            "phone_number",
            "amount",
            "mode",
            "card_last_four",
            "customer_name",
            "transaction_date",
            "is_refund",
            "created_at",
        ]


class SettlementSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source="merchant.phone_number", read_only=True)
    transactions = TransactionSerializer(many=True, read_only=True)

    class Meta:
        model = Settlement
        fields = [
            "settlement_id",
            "phone_number",
            "gross_amount",
            "mdr_deducted",
            "gst_deducted",
            "tax_deducted",
            "net_payout",
            "transaction_count",
            "settlement_date",
            "status",
            "transactions",
            "created_at",
        ]


class SettlementListSerializer(serializers.ModelSerializer):
    """Lighter serializer without nested transactions for list views."""

    phone_number = serializers.CharField(source="merchant.phone_number", read_only=True)

    class Meta:
        model = Settlement
        fields = [
            "settlement_id",
            "phone_number",
            "gross_amount",
            "tax_deducted",
            "net_payout",
            "transaction_count",
            "settlement_date",
            "status",
        ]


class ReconciliationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationIssue
        fields = [
            "issue_id",
            "settlement",
            "merchant",
            "title",
            "description",
            "expected_amount",
            "actual_amount",
            "discrepancy",
            "severity",
            "status",
            "raised_by",
            "created_at",
            "updated_at",
        ]


class ReconciliationIssueCreateSerializer(serializers.Serializer):
    """Serializer for creating reconciliation issues via the MCP bridge."""

    settlement_id = serializers.CharField(required=False, allow_blank=True)
    phone_number = serializers.CharField()
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    expected_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False
    )
    actual_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False
    )
    discrepancy = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False
    )
    severity = serializers.ChoiceField(
        choices=ReconciliationIssue.Severity.choices, default="medium"
    )

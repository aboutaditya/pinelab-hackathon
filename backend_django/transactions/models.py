"""
Transaction models — Source of Truth for the reconciliation agent.

Models:
  - MerchantFeeProfile: Static MDR/GST rates per merchant
  - Transaction: Individual payment/swipe records
  - Settlement: Aggregate payout records
  - ReconciliationIssue: Discrepancies flagged by the AI agent
"""

import uuid

from django.db import models


class MerchantFeeProfile(models.Model):
    """
    Stores the static fee configuration for a merchant.
    Used by the reconciliation agent to calculate expected payouts.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant_id = models.CharField(max_length=50, unique=True, db_index=True)
    phone_number = models.CharField(max_length=15, unique=True, db_index=True, default="0000000000")
    password = models.CharField(max_length=128, default="pinelabs123")
    merchant_name = models.CharField(max_length=255)
    mdr_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        help_text="Merchant Discount Rate as a decimal (e.g., 0.0180 = 1.80%)",
    )
    gst_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        help_text="GST rate on MDR as a decimal (e.g., 0.18 = 18%)",
    )
    amc_fees = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Annual Maintenance Charge in INR",
    )
    settlement_cycle = models.CharField(
        max_length=10,
        choices=[("T+1", "T+1"), ("T+2", "T+2"), ("T+3", "T+3")],
        default="T+1",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "merchant_fee_profiles"
        verbose_name = "Merchant Fee Profile"
        verbose_name_plural = "Merchant Fee Profiles"

    def __str__(self):
        return f"{self.merchant_id} — {self.merchant_name} (MDR: {self.mdr_rate})"


class FeePlanChangeLog(models.Model):
    """
    Change log for merchant fee rates.
    Applies to transactions on or after the effective_date.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        MerchantFeeProfile,
        on_delete=models.CASCADE,
        related_name="fee_plan_logs",
        to_field="merchant_id",
    )
    mdr_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
    )
    gst_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
    )
    amc_fees = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    settlement_cycle = models.CharField(
        max_length=10,
        choices=[("T+1", "T+1"), ("T+2", "T+2"), ("T+3", "T+3")],
        default="T+1",
    )
    effective_date = models.DateField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fee_plan_change_logs"
        ordering = ["-effective_date", "-created_at"]
        verbose_name_plural = "Fee Plan Change Logs"

    def __str__(self):
        return f"{self.merchant.merchant_id} changed to MDR {self.mdr_rate} on {self.effective_date}"


class Settlement(models.Model):
    """
    Aggregate payout record for a merchant.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        DISPUTED = "disputed", "Disputed"
        SETTLED = "settled", "Settled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    settlement_id = models.CharField(max_length=50, unique=True, db_index=True)
    merchant = models.ForeignKey(
        MerchantFeeProfile,
        on_delete=models.CASCADE,
        related_name="settlements",
        to_field="merchant_id",
    )
    gross_amount = models.DecimalField(max_digits=14, decimal_places=2)
    mdr_deducted = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gst_deducted = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    tax_deducted = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total tax = MDR + GST",
    )
    net_payout = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_count = models.PositiveIntegerField(default=0)
    settlement_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "settlements"
        ordering = ["-settlement_date"]

    def __str__(self):
        return f"{self.settlement_id} — ₹{self.net_payout} ({self.status})"


class Transaction(models.Model):
    """Individual swipe / payment record."""

    class PaymentMode(models.TextChoices):
        CREDIT_CARD = "credit_card", "Credit Card"
        DEBIT_CARD = "debit_card", "Debit Card"
        UPI = "upi", "UPI"
        NET_BANKING = "net_banking", "Net Banking"
        WALLET = "wallet", "Wallet"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=50, unique=True, db_index=True)
    settlement = models.ForeignKey(
        Settlement,
        on_delete=models.CASCADE,
        related_name="transactions",
        to_field="settlement_id",
    )
    merchant = models.ForeignKey(
        MerchantFeeProfile,
        on_delete=models.CASCADE,
        related_name="transactions",
        to_field="merchant_id",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    mode = models.CharField(
        max_length=20,
        choices=PaymentMode.choices,
        default=PaymentMode.CREDIT_CARD,
    )
    card_last_four = models.CharField(max_length=4, blank=True, default="")
    customer_name = models.CharField(max_length=255, blank=True, default="")
    transaction_date = models.DateTimeField()
    is_refund = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "transactions"
        ordering = ["-transaction_date"]

    def __str__(self):
        prefix = "REFUND " if self.is_refund else ""
        return f"{prefix}{self.transaction_id} — ₹{self.amount} ({self.mode})"


class ReconciliationIssue(models.Model):
    """Discrepancies found by the AI reconciliation agent for human review."""

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        INVESTIGATING = "investigating", "Investigating"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    issue_id = models.CharField(max_length=50, unique=True, db_index=True)
    settlement = models.ForeignKey(
        Settlement,
        on_delete=models.CASCADE,
        related_name="reconciliation_issues",
        to_field="settlement_id",
        null=True,
        blank=True,
    )
    merchant = models.ForeignKey(
        MerchantFeeProfile,
        on_delete=models.CASCADE,
        related_name="reconciliation_issues",
        to_field="merchant_id",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    expected_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    actual_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    discrepancy = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    severity = models.CharField(
        max_length=20, choices=Severity.choices, default=Severity.MEDIUM
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    raised_by = models.CharField(
        max_length=100, default="reconciliation_agent"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "reconciliation_issues"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.issue_id} — {self.title} [{self.severity}]"

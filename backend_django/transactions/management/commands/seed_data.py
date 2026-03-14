"""
Management command to seed the database with realistic sample data.

Usage:
    python manage.py seed_data
    python manage.py seed_data --noinput  (skip confirmation)
"""

import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from transactions.models import (
    ReconciliationIssue,
    MerchantFeeProfile,
    FeePlanChangeLog,
    Settlement,
    Transaction,
)

# ── Seed data constants ──────────────────────────────────────────

MERCHANTS = [
    {
        "merchant_id": "M001",
        "phone_number": "9876543210",
        "merchant_name": "Reliance Digital Electronics",
        "password": "password123",
        "mdr_rate": Decimal("0.0180"),
        "gst_rate": Decimal("0.1800"),
        "amc_fees": Decimal("2500.00"),
        "settlement_cycle": "T+1",
    },
    {
        "merchant_id": "M002",
        "phone_number": "8765432109",
        "merchant_name": "Big Bazaar Supermarket",
        "password": "password123",
        "mdr_rate": Decimal("0.0150"),
        "gst_rate": Decimal("0.1800"),
        "amc_fees": Decimal("1800.00"),
        "settlement_cycle": "T+1",
    },
    {
        "merchant_id": "M003",
        "phone_number": "7654321098",
        "merchant_name": "Apollo Pharmacy Chain",
        "password": "password123",
        "mdr_rate": Decimal("0.0120"),
        "gst_rate": Decimal("0.1800"),
        "amc_fees": Decimal("1200.00"),
        "settlement_cycle": "T+2",
    },
    {
        "merchant_id": "M004",
        "phone_number": "6543210987",
        "merchant_name": "Café Coffee Day",
        "password": "password123",
        "mdr_rate": Decimal("0.0200"),
        "gst_rate": Decimal("0.1800"),
        "amc_fees": Decimal("800.00"),
        "settlement_cycle": "T+1",
    },
    {
        "merchant_id": "M005",
        "phone_number": "5432109876",
        "merchant_name": "Tanishq Jewellers",
        "password": "password123",
        "mdr_rate": Decimal("0.0100"),
        "gst_rate": Decimal("0.1800"),
        "amc_fees": Decimal("5000.00"),
        "settlement_cycle": "T+2",
    },
]

PAYMENT_MODES = ["credit_card", "debit_card", "upi", "net_banking", "wallet"]
CUSTOMER_NAMES = [
    "Rajesh Kumar", "Priya Sharma", "Amit Patel", "Sneha Reddy",
    "Vikram Singh", "Anjali Gupta", "Rohit Jain", "Kavita Nair",
    "Suresh Menon", "Deepa Iyer", "Arjun Desai", "Meera Bhat",
    "Sanjay Verma", "Pooja Rao", "Nikhil Das", "Divya Pillai",
]


class Command(BaseCommand):
    help = "Seed the database with realistic Pine Labs transaction data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        if not options["noinput"]:
            confirm = input(
                "This will clear existing data and reseed. Continue? [y/N]: "
            )
            if confirm.lower() != "y":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        self.stdout.write("🌱 Seeding database...")

        # Clear existing data
        # Using try-except to handle cases where tables haven't been created yet
        # (e.g. initial run with renamed tables)
        models_to_clear = [
            ReconciliationIssue,
            Transaction,
            Settlement,
            FeePlanChangeLog,
            MerchantFeeProfile
        ]
        
        for model in models_to_clear:
            try:
                model.objects.all().delete()
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Skipping clear for {model.__name__}: {e}"))

        # 1. Create Merchant Fee Profiles and Change Logs
        merchant_profiles = {}
        today = timezone.now().date()
        for m in MERCHANTS:
            profile, created = MerchantFeeProfile.objects.update_or_create(
                merchant_id=m["merchant_id"],
                defaults=m
            )
            merchant_profiles[m["merchant_id"]] = profile
            
            # Create a base plan from a month ago (e.g., slightly lower MDR)
            FeePlanChangeLog.objects.get_or_create(
                merchant=profile,
                effective_date=today - timedelta(days=30),
                defaults={
                    "mdr_rate": profile.mdr_rate - Decimal("0.0020"),
                    "gst_rate": profile.gst_rate,
                    "amc_fees": profile.amc_fees,
                    "settlement_cycle": profile.settlement_cycle,
                }
            )
            
            # Create a rate bump that came into effect 2 days ago!
            FeePlanChangeLog.objects.get_or_create(
                merchant=profile,
                effective_date=today - timedelta(days=2),
                defaults={
                    "mdr_rate": profile.mdr_rate,
                    "gst_rate": profile.gst_rate,
                    "amc_fees": profile.amc_fees,
                    "settlement_cycle": profile.settlement_cycle,
                }
            )
            
            self.stdout.write(f"  ✅ Merchant: {m['merchant_name']}")

        # 2. Create Settlements & Transactions
        settlement_count = 0
        txn_count = 0

        for merchant_id, profile in merchant_profiles.items():
            # Create 3 settlements per merchant (last 3 days)
            for day_offset in range(1, 4):
                settlement_date = (
                    timezone.now() - timedelta(days=day_offset)
                ).date()
                stl_id = f"STL-{merchant_id}-{settlement_date.strftime('%Y%m%d')}"

                # Generate 5-10 transactions per settlement
                num_txns = random.randint(5, 10)
                txn_amounts = []
                transactions_data = []

                for t in range(num_txns):
                    amount = Decimal(str(random.randint(100, 50000)))
                    is_refund = random.random() < 0.08  # 8% refund rate
                    mode = random.choice(PAYMENT_MODES)
                    card_last_four = (
                        str(random.randint(1000, 9999))
                        if mode in ("credit_card", "debit_card")
                        else ""
                    )

                    txn_amounts.append(-amount if is_refund else amount)
                    transactions_data.append(
                        {
                            "amount": amount,
                            "mode": mode,
                            "is_refund": is_refund,
                            "card_last_four": card_last_four,
                            "customer_name": random.choice(CUSTOMER_NAMES),
                        }
                    )

                # Calculate settlement amounts using the active FeePlanChangeLog for the settlement date
                applicable_log = profile.fee_plan_logs.filter(effective_date__lte=settlement_date).first()
                if not applicable_log:
                    # Fallback to current if log is missing
                    active_mdr = profile.mdr_rate
                    active_gst = profile.gst_rate
                else:
                    active_mdr = applicable_log.mdr_rate
                    active_gst = applicable_log.gst_rate

                gross = sum(a for a in txn_amounts if a > 0)
                refunds = abs(sum(a for a in txn_amounts if a < 0))
                net_gross = gross - refunds
                mdr = (net_gross * active_mdr).quantize(Decimal("0.01"))
                gst = (mdr * active_gst).quantize(Decimal("0.01"))
                tax = mdr + gst
                net_payout = net_gross - tax

                # Introduce a deliberate discrepancy in ~20% of settlements
                has_discrepancy = random.random() < 0.20
                if has_discrepancy:
                    # Slightly wrong payout (off by ₹10-500)
                    discrepancy_amount = Decimal(
                        str(random.randint(10, 500))
                    )
                    net_payout_stored = net_payout - discrepancy_amount
                    stl_status = "processed"
                else:
                    net_payout_stored = net_payout
                    discrepancy_amount = Decimal("0")
                    stl_status = "settled"

                settlement, created = Settlement.objects.update_or_create(
                    settlement_id=stl_id,
                    defaults={
                        "merchant": profile,
                        "gross_amount": net_gross,
                        "mdr_deducted": mdr,
                        "gst_deducted": gst,
                        "tax_deducted": tax,
                        "net_payout": net_payout_stored,
                        "transaction_count": num_txns,
                        "settlement_date": settlement_date,
                        "status": stl_status,
                    }
                )
                settlement_count += 1

                # Create transactions
                for idx, td in enumerate(transactions_data):
                    txn_time = timezone.make_aware(
                        datetime.combine(
                            settlement_date,
                            datetime.min.time(),
                        )
                        + timedelta(hours=random.randint(8, 22), minutes=random.randint(0, 59))
                    )

                    Transaction.objects.update_or_create(
                        transaction_id=f"TXN-{merchant_id}-{settlement_date.strftime('%Y%m%d')}-{idx + 1:03d}",
                        defaults={
                            "settlement": settlement,
                            "merchant": profile,
                            "amount": td["amount"],
                            "mode": td["mode"],
                            "card_last_four": td["card_last_four"],
                            "customer_name": td["customer_name"],
                            "transaction_date": txn_time,
                            "is_refund": td["is_refund"],
                        }
                    )
                    txn_count += 1

                # Create reconciliation issue if there's a discrepancy
                if has_discrepancy:
                    ReconciliationIssue.objects.update_or_create(
                        issue_id=f"ISS-SEED-{stl_id}",
                        defaults={
                            "settlement": settlement,
                            "merchant": profile,
                            "title": f"Payout discrepancy in {stl_id}",
                            "description": (
                                f"Expected net payout: ₹{net_payout}, "
                                f"actual: ₹{net_payout_stored}. "
                                f"Discrepancy: ₹{discrepancy_amount}."
                            ),
                            "expected_amount": net_payout,
                            "actual_amount": net_payout_stored,
                            "discrepancy": discrepancy_amount,
                            "severity": "high" if discrepancy_amount > 200 else "medium",
                            "status": "open",
                        }
                    )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"✨ Seeded: {len(MERCHANTS)} merchants, "
                f"{settlement_count} settlements, "
                f"{txn_count} transactions"
            )
        )

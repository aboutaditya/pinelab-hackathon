"""
REST API views for the transaction service.
"""

import json
import os
import uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from django.db import models
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import ReconciliationIssue, MerchantFeeProfile, Settlement, Transaction
from .serializers import (
    ReconciliationIssueCreateSerializer,
    ReconciliationIssueSerializer,
    MerchantFeeProfileSerializer,
    SettlementListSerializer,
    SettlementSerializer,
    TransactionSerializer,
)


# ── Health Check ──────────────────────────────────────────────────


@api_view(["GET"])
def health_check(request):
    """Health check endpoint for Docker / load balancers."""
    return Response(
        {"status": "healthy", "service": "pine-labs-backend"},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
def merchant_login(request):
    """
    POST /api/v1/transactions/login/
    Validates merchant credentials (identifier + password).
    Identifier can be merchant_id or phone_number.
    """
    identifier = request.data.get("identifier")
    password = request.data.get("password")

    if not identifier or not password:
        return Response(
            {"error": "Identifier and password required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        profile = MerchantFeeProfile.objects.get(
            (models.Q(merchant_id=identifier) | models.Q(phone_number=identifier)),
            password=password,
            is_active=True,
        )
        return Response(
            {
                "success": True,
                "merchant_id": profile.merchant_id,
                "merchant_name": profile.merchant_name,
                "phone_number": profile.phone_number,
            }
        )
    except MerchantFeeProfile.DoesNotExist:
        return Response(
            {"error": "Invalid credentials or inactive account"},
            status=status.HTTP_401_UNAUTHORIZED,
        )


# ── Chat UI ───────────────────────────────────────────────────────


def chat_ui(request):
    """Renders the standard UI for the Reconciliation Agent."""
    return render(request, "transactions/chat.html")


@api_view(["POST"])
def chat_reconciliation_proxy(request):
    """
    Proxy POST /api/v1/transactions/chat/reconciliation/ to the AI agent.
    Used in production when the agent is not publicly reachable (e.g. behind ALB).
    """
    agent_url = os.environ.get("AGENT_URL", "http://localhost:8000").rstrip("/")
    target = f"{agent_url}/chat/v1/reconciliation"
    try:
        body = json.dumps(request.data) if isinstance(request.data, dict) else request.body
        req = Request(
            target,
            data=body.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=120) as resp:
            return Response(json.loads(resp.read().decode()), status=resp.status)
    except HTTPError as e:
        body = e.read().decode() if e.fp else "{}"
        try:
            return Response(json.loads(body), status=e.code)
        except json.JSONDecodeError:
            return Response({"detail": body or str(e)}, status=e.code)
    except (URLError, OSError) as e:
        return Response(
            {"detail": "Agent service unavailable"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def serve_intro_video(request):
    """Serve the intro video file."""
    import os
    from django.http import FileResponse
    video_path = os.path.join(
        os.path.dirname(__file__),
        "templates", "transactions", "pinelabsintro.mp4"
    )
    return FileResponse(open(video_path, "rb"), content_type="video/mp4")


def serve_navbar_image(request):
    """Serve the navbar image."""
    import os
    from django.http import FileResponse, Http404
    img_path = os.path.join(
        os.path.dirname(__file__),
        "templates", "transactions", "navbar.png"
    )
    if not os.path.isfile(img_path):
        raise Http404("Navbar image not found")
    return FileResponse(open(img_path, "rb"), content_type="image/png")


# ── Fee Profiles ──────────────────────────────────────────────────


@api_view(["GET"])
def get_fee_profile(request, phone_number):
    """
    GET /api/v1/transactions/fee-profile/{phone_number}/
    Returns the MDR and GST rates for a specific merchant.
    """
    try:
        profile = MerchantFeeProfile.objects.prefetch_related("fee_plan_logs").get(
            phone_number=phone_number, is_active=True
        )
    except MerchantFeeProfile.DoesNotExist:
        return Response(
            {"error": f"No active fee profile found for phone number '{phone_number}'"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Optional historical override based on transaction date
    txn_date_str = request.query_params.get("date")
    if txn_date_str:
        from datetime import datetime
        try:
            target_date = datetime.strptime(txn_date_str, "%Y-%m-%d").date()
            # Since ordering is "-effective_date", `.first()` gives the latest log that is <= target_date
            applicable_log = profile.fee_plan_logs.filter(effective_date__lte=target_date).first()
            if applicable_log:
                profile.mdr_rate = applicable_log.mdr_rate
                profile.gst_rate = applicable_log.gst_rate
                profile.amc_fees = applicable_log.amc_fees
                profile.settlement_cycle = applicable_log.settlement_cycle
        except ValueError:
            pass # Ignore formatted dates

    serializer = MerchantFeeProfileSerializer(profile)
    return Response(serializer.data)


@api_view(["GET"])
def list_fee_profiles(request):
    """
    GET /api/v1/transactions/fee-profiles/
    Returns all active merchant fee profiles.
    """
    profiles = MerchantFeeProfile.objects.filter(is_active=True)
    serializer = MerchantFeeProfileSerializer(profiles, many=True)
    return Response(serializer.data)


# ── Settlements ───────────────────────────────────────────────────


@api_view(["GET"])
def get_settlement(request, settlement_id):
    """
    GET /api/v1/transactions/settlement/{settlement_id}/
    Returns settlement details with all associated transactions.
    """
    try:
        settlement = Settlement.objects.prefetch_related("transactions").get(
            settlement_id=settlement_id
        )
    except Settlement.DoesNotExist:
        return Response(
            {"error": f"No settlement found with ID '{settlement_id}'"},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = SettlementSerializer(settlement)
    return Response(serializer.data)


@api_view(["GET"])
def list_settlements(request):
    """
    GET /api/v1/transactions/settlements/
    Returns all settlements. Supports ?phone_number= filter.
    """
    queryset = Settlement.objects.all()
    phone_number = request.query_params.get("phone_number")
    if phone_number:
        queryset = queryset.filter(merchant__phone_number=phone_number)

    serializer = SettlementListSerializer(queryset, many=True)
    return Response(serializer.data)


# ── Transactions ──────────────────────────────────────────────────


@api_view(["GET"])
def list_transactions(request):
    """
    GET /api/v1/transactions/
    Returns transactions. Supports ?settlement_id= and ?phone_number= filters.
    """
    queryset = Transaction.objects.select_related("settlement", "merchant").all()

    settlement_id = request.query_params.get("settlement_id")
    phone_number = request.query_params.get("phone_number")

    if settlement_id:
        queryset = queryset.filter(settlement__settlement_id=settlement_id)
    if phone_number:
        queryset = queryset.filter(merchant__phone_number=phone_number)

    serializer = TransactionSerializer(queryset, many=True)
    return Response(serializer.data)


# ── Reconciliation Issues ─────────────────────────────────────────


@api_view(["GET", "POST"])
def reconciliation_issues(request):
    """
    GET  /api/v1/transactions/issues/ — List all reconciliation issues
    POST /api/v1/transactions/issues/ — Create a new reconciliation issue
    """
    if request.method == "GET":
        queryset = ReconciliationIssue.objects.all()

        # Optional filters
        phone_number = request.query_params.get("phone_number")
        issue_status = request.query_params.get("status")
        severity = request.query_params.get("severity")

        if phone_number:
            queryset = queryset.filter(merchant__phone_number=phone_number)
        if issue_status:
            queryset = queryset.filter(status=issue_status)
        if severity:
            queryset = queryset.filter(severity=severity)

        serializer = ReconciliationIssueSerializer(queryset, many=True)
        return Response(serializer.data)

    # POST — create a new reconciliation issue
    create_serializer = ReconciliationIssueCreateSerializer(data=request.data)
    create_serializer.is_valid(raise_exception=True)
    data = create_serializer.validated_data

    # Resolve FK references
    try:
        merchant = MerchantFeeProfile.objects.get(
            phone_number=data["phone_number"]
        )
    except MerchantFeeProfile.DoesNotExist:
        return Response(
            {"error": f"Merchant with phone number '{data['phone_number']}' not found"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    settlement = None
    settlement_id = data.get("settlement_id")
    if settlement_id:
        try:
            settlement = Settlement.objects.get(settlement_id=settlement_id)
        except Settlement.DoesNotExist:
            return Response(
                {"error": f"Settlement '{settlement_id}' not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    issue = ReconciliationIssue.objects.create(
        issue_id=f"ISS-{uuid.uuid4().hex[:8].upper()}",
        settlement=settlement,
        merchant=merchant,
        title=data["title"],
        description=data["description"],
        expected_amount=data.get("expected_amount"),
        actual_amount=data.get("actual_amount"),
        discrepancy=data.get("discrepancy"),
        severity=data.get("severity", "medium"),
        raised_by="reconciliation_agent",
    )

    serializer = ReconciliationIssueSerializer(issue)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(["GET", "PATCH"])
def reconciliation_issue_detail(request, issue_id):
    """
    GET   /api/v1/transactions/issues/{issue_id}/ — Get issue details
    PATCH /api/v1/transactions/issues/{issue_id}/ — Update issue status
    """
    try:
        issue = ReconciliationIssue.objects.get(issue_id=issue_id)
    except ReconciliationIssue.DoesNotExist:
        return Response(
            {"error": f"Reconciliation issue '{issue_id}' not found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        serializer = ReconciliationIssueSerializer(issue)
        return Response(serializer.data)

    # PATCH — update status / severity
    allowed_fields = {"status", "severity", "description"}
    for field, value in request.data.items():
        if field in allowed_fields:
            setattr(issue, field, value)
    issue.save()

    serializer = ReconciliationIssueSerializer(issue)
    return Response(serializer.data)

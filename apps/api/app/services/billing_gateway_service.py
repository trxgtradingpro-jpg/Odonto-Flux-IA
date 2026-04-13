from __future__ import annotations

import hmac
import math
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ApiError
from app.models import Job, Setting, Tenant, TenantPlan

BILLING_STATE_KEY = "billing.state"
BILLING_INVOICES_KEY = "billing.invoices"
BILLING_CHECKOUT_SESSIONS_KEY = "billing.checkout_sessions"
BILLING_BLOCKED_STATUSES = {"blocked", "suspended", "canceled"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return None


def _days_overdue(next_due_at: datetime | None, now: datetime) -> int:
    if not next_due_at or now <= next_due_at:
        return 0
    seconds = (now - next_due_at).total_seconds()
    return max(1, int(math.ceil(seconds / 86_400)))


def _get_setting(db: Session, tenant_id: UUID, key: str) -> Setting | None:
    return db.scalar(select(Setting).where(Setting.tenant_id == tenant_id, Setting.key == key))


def _set_setting(
    db: Session,
    tenant_id: UUID,
    *,
    key: str,
    value: dict[str, Any],
    is_secret: bool = False,
) -> Setting:
    item = _get_setting(db, tenant_id, key)
    if not item:
        item = Setting(
            tenant_id=tenant_id,
            key=key,
            value=value,
            is_secret=is_secret,
        )
    else:
        item.value = value
        item.is_secret = is_secret
    db.add(item)
    db.flush()
    return item


def _default_state() -> dict[str, Any]:
    return {
        "provider": settings.billing_provider,
        "customer_id": None,
        "last_paid_at": None,
        "last_failed_at": None,
        "next_due_at": None,
        "grace_days": settings.billing_overdue_grace_days,
        "updated_at": _now_iso(),
    }


def get_billing_state(db: Session, tenant_id: UUID) -> dict[str, Any]:
    item = _get_setting(db, tenant_id, BILLING_STATE_KEY)
    if not item or not isinstance(item.value, dict):
        return _default_state()

    state = _default_state()
    for key in state:
        if key in item.value:
            state[key] = item.value[key]
    return state


def save_billing_state(db: Session, tenant_id: UUID, state: dict[str, Any]) -> dict[str, Any]:
    merged = _default_state()
    merged.update(state)
    merged["updated_at"] = _now_iso()
    _set_setting(db, tenant_id, key=BILLING_STATE_KEY, value=merged)
    return merged


def list_invoice_events(db: Session, tenant_id: UUID, *, limit: int = 20) -> list[dict[str, Any]]:
    item = _get_setting(db, tenant_id, BILLING_INVOICES_KEY)
    events = item.value.get("data", []) if item and isinstance(item.value, dict) else []
    if not isinstance(events, list):
        return []
    return events[: max(1, min(limit, 100))]


def append_invoice_event(db: Session, tenant_id: UUID, payload: dict[str, Any]) -> None:
    item = _get_setting(db, tenant_id, BILLING_INVOICES_KEY)
    current = item.value if item and isinstance(item.value, dict) else {"data": []}
    data = current.get("data", [])
    if not isinstance(data, list):
        data = []
    event = {
        "id": payload.get("id") or str(uuid4()),
        "status": payload.get("status", "unknown"),
        "amount_cents": int(payload.get("amount_cents") or 0),
        "currency": payload.get("currency") or "BRL",
        "description": payload.get("description") or "Evento de faturamento",
        "occurred_at": payload.get("occurred_at") or _now_iso(),
        "provider": payload.get("provider") or settings.billing_provider,
        "provider_invoice_id": payload.get("provider_invoice_id"),
    }
    data.insert(0, event)
    _set_setting(db, tenant_id, key=BILLING_INVOICES_KEY, value={"data": data[:50]})


def list_checkout_sessions(db: Session, tenant_id: UUID, *, limit: int = 10) -> list[dict[str, Any]]:
    item = _get_setting(db, tenant_id, BILLING_CHECKOUT_SESSIONS_KEY)
    sessions = item.value.get("data", []) if item and isinstance(item.value, dict) else []
    if not isinstance(sessions, list):
        return []
    return sessions[: max(1, min(limit, 30))]


def append_checkout_session(db: Session, tenant_id: UUID, payload: dict[str, Any]) -> None:
    item = _get_setting(db, tenant_id, BILLING_CHECKOUT_SESSIONS_KEY)
    current = item.value if item and isinstance(item.value, dict) else {"data": []}
    data = current.get("data", [])
    if not isinstance(data, list):
        data = []
    data.insert(0, payload)
    _set_setting(db, tenant_id, key=BILLING_CHECKOUT_SESSIONS_KEY, value={"data": data[:30]})


def get_delinquency_snapshot(
    db: Session,
    tenant_id: UUID,
    *,
    tenant: Tenant | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    target_tenant = tenant or db.get(Tenant, tenant_id)
    if not target_tenant:
        raise ApiError(status_code=404, code="TENANT_NOT_FOUND", message="Tenant nao encontrado")

    state = get_billing_state(db, tenant_id)
    next_due_at = _parse_datetime(state.get("next_due_at"))
    overdue_days = _days_overdue(next_due_at, now)
    grace_days = int(state.get("grace_days") or settings.billing_overdue_grace_days)
    is_delinquent = overdue_days > 0 or target_tenant.subscription_status in {"past_due", "blocked"}
    should_block = overdue_days > grace_days

    recommended_action = "ok"
    if should_block:
        recommended_action = "block"
    elif overdue_days > 0:
        recommended_action = "notify"

    return {
        "is_delinquent": is_delinquent,
        "days_overdue": overdue_days,
        "grace_days": grace_days,
        "recommended_action": recommended_action,
        "next_due_at": next_due_at.isoformat() if next_due_at else None,
        "last_paid_at": state.get("last_paid_at"),
        "last_failed_at": state.get("last_failed_at"),
    }


def _stripe_checkout(
    *,
    tenant: Tenant,
    plan: TenantPlan,
    customer_email: str,
    customer_id: str | None,
) -> dict[str, str]:
    if not settings.stripe_secret_key:
        raise ApiError(
            status_code=503,
            code="BILLING_PROVIDER_MISCONFIGURED",
            message="Gateway Stripe sem chave configurada",
        )

    stripe_data: list[tuple[str, str]] = [
        ("mode", "subscription"),
        ("success_url", settings.billing_success_url),
        ("cancel_url", settings.billing_cancel_url),
        ("client_reference_id", str(tenant.id)),
        ("metadata[tenant_id]", str(tenant.id)),
        ("metadata[plan_code]", plan.code),
        ("subscription_data[metadata][tenant_id]", str(tenant.id)),
        ("subscription_data[metadata][plan_code]", plan.code),
        ("line_items[0][price_data][currency]", (plan.currency or "BRL").lower()),
        ("line_items[0][price_data][unit_amount]", str(plan.price_cents)),
        ("line_items[0][price_data][product_data][name]", f"OdontoFlux {plan.name}"),
        ("line_items[0][price_data][recurring][interval]", "month"),
        ("line_items[0][quantity]", "1"),
    ]

    if customer_id:
        stripe_data.append(("customer", customer_id))
    else:
        stripe_data.append(("customer_email", customer_email))

    try:
        response = httpx.post(
            "https://api.stripe.com/v1/checkout/sessions",
            data=stripe_data,
            headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        details: dict[str, Any] = {}
        try:
            details = exc.response.json()
        except Exception:
            details = {"body": exc.response.text}
        raise ApiError(
            status_code=502,
            code="BILLING_PROVIDER_ERROR",
            message="Falha ao criar checkout no provedor",
            details=details,
        ) from exc
    except httpx.HTTPError as exc:
        raise ApiError(
            status_code=502,
            code="BILLING_PROVIDER_UNAVAILABLE",
            message="Gateway de pagamento indisponivel",
        ) from exc

    payload = response.json()
    checkout_url = payload.get("url")
    session_id = payload.get("id")
    if not checkout_url or not session_id:
        raise ApiError(
            status_code=502,
            code="BILLING_PROVIDER_INVALID_RESPONSE",
            message="Resposta invalida do gateway de pagamento",
        )
    return {
        "provider": "stripe",
        "checkout_url": checkout_url,
        "session_id": session_id,
        "customer_id": payload.get("customer"),
    }


def _manual_checkout(*, tenant: Tenant, plan: TenantPlan) -> dict[str, str]:
    session_id = f"manual_{uuid4().hex}"
    checkout_url = (
        f"{settings.billing_manual_checkout_url}?tenant={tenant.slug}&plan={plan.code}&session={session_id}"
    )
    return {
        "provider": "manual",
        "checkout_url": checkout_url,
        "session_id": session_id,
        "customer_id": "",
    }


def create_checkout_session(
    db: Session,
    *,
    tenant: Tenant,
    plan: TenantPlan,
    customer_email: str,
) -> dict[str, Any]:
    state = get_billing_state(db, tenant.id)
    provider = settings.billing_provider.lower().strip()

    if plan.price_cents <= 0:
        tenant.plan_id = plan.id
        tenant.subscription_status = "active"
        tenant.is_active = True
        db.add(tenant)
        save_billing_state(
            db,
            tenant.id,
            {
                **state,
                "provider": provider,
                "last_paid_at": _now_iso(),
                "next_due_at": (datetime.now(UTC) + timedelta(days=settings.billing_cycle_days)).isoformat(),
                "last_failed_at": None,
            },
        )
        append_invoice_event(
            db,
            tenant.id,
            {
                "status": "paid",
                "amount_cents": 0,
                "description": f"Migracao para plano {plan.name}",
                "provider": provider,
            },
        )
        return {
            "requires_payment": False,
            "checkout_url": None,
            "provider_session_id": None,
            "provider": provider,
        }

    if provider == "stripe":
        checkout = _stripe_checkout(
            tenant=tenant,
            plan=plan,
            customer_email=customer_email,
            customer_id=state.get("customer_id"),
        )
    else:
        checkout = _manual_checkout(tenant=tenant, plan=plan)

    append_checkout_session(
        db,
        tenant.id,
        {
            "id": checkout["session_id"],
            "provider": checkout["provider"],
            "plan_code": plan.code,
            "checkout_url": checkout["checkout_url"],
            "status": "pending",
            "created_at": _now_iso(),
        },
    )
    save_billing_state(
        db,
        tenant.id,
        {
            **state,
            "provider": checkout["provider"],
            "customer_id": checkout["customer_id"] or state.get("customer_id"),
        },
    )
    return {
        "requires_payment": True,
        "checkout_url": checkout["checkout_url"],
        "provider_session_id": checkout["session_id"],
        "provider": checkout["provider"],
    }


def _apply_subscription_success(
    db: Session,
    *,
    tenant: Tenant,
    plan_code: str | None,
    provider: str,
    provider_invoice_id: str | None,
    amount_cents: int,
    currency: str | None,
    customer_id: str | None,
) -> dict[str, Any]:
    if plan_code:
        plan = db.scalar(select(TenantPlan).where(TenantPlan.code == plan_code, TenantPlan.is_active.is_(True)))
        if plan:
            tenant.plan_id = plan.id

    now = datetime.now(UTC)
    tenant.subscription_status = "active"
    tenant.is_active = True
    db.add(tenant)

    state = get_billing_state(db, tenant.id)
    save_billing_state(
        db,
        tenant.id,
        {
            **state,
            "provider": provider,
            "customer_id": customer_id or state.get("customer_id"),
            "last_paid_at": now.isoformat(),
            "last_failed_at": None,
            "next_due_at": (now + timedelta(days=settings.billing_cycle_days)).isoformat(),
        },
    )
    append_invoice_event(
        db,
        tenant.id,
        {
            "status": "paid",
            "amount_cents": amount_cents,
            "currency": currency or "BRL",
            "provider": provider,
            "provider_invoice_id": provider_invoice_id,
            "description": "Pagamento confirmado",
        },
    )
    return {
        "tenant_id": str(tenant.id),
        "subscription_status": tenant.subscription_status,
        "next_due_at": (now + timedelta(days=settings.billing_cycle_days)).isoformat(),
    }


def _apply_subscription_failure(
    db: Session,
    *,
    tenant: Tenant,
    provider: str,
    provider_invoice_id: str | None,
    amount_cents: int,
    currency: str | None,
    customer_id: str | None,
) -> dict[str, Any]:
    state = get_billing_state(db, tenant.id)
    now = datetime.now(UTC)

    due_at = _parse_datetime(state.get("next_due_at"))
    if not due_at:
        due_at = now
        state["next_due_at"] = due_at.isoformat()

    overdue_days = max(1, _days_overdue(due_at, now))
    grace_days = int(state.get("grace_days") or settings.billing_overdue_grace_days)
    next_status = tenant.subscription_status
    if tenant.subscription_status not in {"suspended", "canceled"}:
        if overdue_days > grace_days:
            next_status = "blocked"
        elif overdue_days > 0:
            next_status = "past_due"

    tenant.subscription_status = next_status
    tenant.is_active = next_status != "canceled"
    db.add(tenant)

    save_billing_state(
        db,
        tenant.id,
        {
            **state,
            "provider": provider,
            "customer_id": customer_id or state.get("customer_id"),
            "last_failed_at": now.isoformat(),
        },
    )
    append_invoice_event(
        db,
        tenant.id,
        {
            "status": "failed",
            "amount_cents": amount_cents,
            "currency": currency or "BRL",
            "provider": provider,
            "provider_invoice_id": provider_invoice_id,
            "description": "Falha no pagamento",
        },
    )
    return {
        "tenant_id": str(tenant.id),
        "subscription_status": tenant.subscription_status,
        "days_overdue": overdue_days,
        "grace_days": grace_days,
    }


def extract_stripe_context(event_payload: dict[str, Any]) -> dict[str, Any]:
    data = event_payload.get("data", {})
    obj = data.get("object", {}) if isinstance(data, dict) else {}

    metadata = obj.get("metadata") if isinstance(obj, dict) else {}
    if not isinstance(metadata, dict):
        metadata = {}

    line_items = obj.get("lines", {}).get("data", []) if isinstance(obj, dict) else []
    first_line = line_items[0] if line_items and isinstance(line_items[0], dict) else {}
    line_metadata = first_line.get("metadata") if isinstance(first_line, dict) else {}
    if not isinstance(line_metadata, dict):
        line_metadata = {}

    subscription_details = obj.get("subscription_details") if isinstance(obj, dict) else {}
    sub_metadata = (
        subscription_details.get("metadata")
        if isinstance(subscription_details, dict)
        else {}
    )
    if not isinstance(sub_metadata, dict):
        sub_metadata = {}

    tenant_ref = (
        metadata.get("tenant_id")
        or line_metadata.get("tenant_id")
        or sub_metadata.get("tenant_id")
        or obj.get("client_reference_id")
    )
    plan_code = (
        metadata.get("plan_code")
        or line_metadata.get("plan_code")
        or sub_metadata.get("plan_code")
    )

    amount_cents = obj.get("amount_paid")
    if amount_cents is None:
        amount_cents = obj.get("amount_due")
    if amount_cents is None:
        amount_cents = first_line.get("amount_total") if isinstance(first_line, dict) else 0

    return {
        "tenant_id": tenant_ref,
        "plan_code": plan_code,
        "provider_session_id": obj.get("id"),
        "provider_invoice_id": obj.get("invoice") or obj.get("id"),
        "customer_id": obj.get("customer"),
        "amount_cents": int(amount_cents or 0),
        "currency": (obj.get("currency") or "BRL").upper(),
    }


def handle_stripe_event(db: Session, event_payload: dict[str, Any]) -> dict[str, Any]:
    event_type = event_payload.get("type")
    context = extract_stripe_context(event_payload)

    tenant_id_raw = context.get("tenant_id")
    if not tenant_id_raw:
        raise ApiError(
            status_code=400,
            code="BILLING_EVENT_MISSING_TENANT",
            message="Evento sem tenant_id em metadata",
        )

    try:
        tenant_id = UUID(str(tenant_id_raw))
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="BILLING_EVENT_TENANT_INVALID",
            message="tenant_id invalido no evento",
        ) from exc

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise ApiError(status_code=404, code="TENANT_NOT_FOUND", message="Tenant nao encontrado")

    if event_type in {"checkout.session.completed", "invoice.paid"}:
        return _apply_subscription_success(
            db,
            tenant=tenant,
            plan_code=context.get("plan_code"),
            provider="stripe",
            provider_invoice_id=context.get("provider_invoice_id"),
            amount_cents=context.get("amount_cents", 0),
            currency=context.get("currency"),
            customer_id=context.get("customer_id"),
        )

    if event_type in {"invoice.payment_failed", "checkout.session.expired"}:
        return _apply_subscription_failure(
            db,
            tenant=tenant,
            provider="stripe",
            provider_invoice_id=context.get("provider_invoice_id"),
            amount_cents=context.get("amount_cents", 0),
            currency=context.get("currency"),
            customer_id=context.get("customer_id"),
        )

    if event_type == "customer.subscription.deleted":
        tenant.subscription_status = "canceled"
        tenant.is_active = False
        db.add(tenant)
        append_invoice_event(
            db,
            tenant.id,
            {
                "status": "canceled",
                "amount_cents": 0,
                "currency": "BRL",
                "provider": "stripe",
                "provider_invoice_id": context.get("provider_invoice_id"),
                "description": "Assinatura cancelada no gateway",
            },
        )
        return {
            "tenant_id": str(tenant.id),
            "subscription_status": tenant.subscription_status,
        }

    return {"ignored": True, "event_type": event_type}


def verify_stripe_signature(payload: bytes, signature_header: str | None) -> bool:
    if not settings.stripe_webhook_secret:
        return False
    if not signature_header:
        return False

    parts = [segment.strip() for segment in signature_header.split(",") if segment.strip()]
    parsed: dict[str, str] = {}
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        parsed[key] = value

    timestamp = parsed.get("t")
    provided = parsed.get("v1")
    if not timestamp or not provided:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        settings.stripe_webhook_secret.encode("utf-8"),
        signed_payload,
        sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, provided)


def create_customer_portal_link(db: Session, tenant_id: UUID) -> dict[str, Any]:
    state = get_billing_state(db, tenant_id)
    provider = (state.get("provider") or settings.billing_provider).lower()

    if provider != "stripe":
        return {
            "provider": provider,
            "url": settings.billing_manual_checkout_url,
            "available": True,
        }

    if not settings.stripe_secret_key:
        raise ApiError(
            status_code=503,
            code="BILLING_PROVIDER_MISCONFIGURED",
            message="Stripe nao configurado para portal de pagamento",
        )

    customer_id = state.get("customer_id")
    if not customer_id:
        raise ApiError(
            status_code=400,
            code="BILLING_CUSTOMER_NOT_FOUND",
            message="Cliente de faturamento nao encontrado para este tenant",
        )

    data = {
        "customer": customer_id,
        "return_url": settings.billing_success_url,
    }
    try:
        response = httpx.post(
            "https://api.stripe.com/v1/billing_portal/sessions",
            data=data,
            headers={"Authorization": f"Bearer {settings.stripe_secret_key}"},
            timeout=20.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        details: dict[str, Any] = {}
        try:
            details = exc.response.json()
        except Exception:
            details = {"body": exc.response.text}
        raise ApiError(
            status_code=502,
            code="BILLING_PORTAL_ERROR",
            message="Falha ao criar sessao no portal de pagamento",
            details=details,
        ) from exc
    except httpx.HTTPError as exc:
        raise ApiError(
            status_code=502,
            code="BILLING_PROVIDER_UNAVAILABLE",
            message="Portal de pagamento indisponivel",
        ) from exc

    payload = response.json()
    return {
        "provider": "stripe",
        "url": payload.get("url"),
        "available": bool(payload.get("url")),
    }


def run_delinquency_check(db: Session) -> dict[str, Any]:
    tenants = db.execute(select(Tenant)).scalars().all()
    now = datetime.now(UTC)
    changed = 0
    blocked = 0
    past_due = 0
    active = 0

    for tenant in tenants:
        if tenant.subscription_status in {"suspended", "canceled"}:
            continue
        state = get_billing_state(db, tenant.id)
        due_at = _parse_datetime(state.get("next_due_at"))
        if not due_at:
            continue

        overdue_days = _days_overdue(due_at, now)
        grace_days = int(state.get("grace_days") or settings.billing_overdue_grace_days)

        expected_status = tenant.subscription_status
        if overdue_days > grace_days:
            expected_status = "blocked"
        elif overdue_days > 0:
            expected_status = "past_due"
        elif tenant.subscription_status in {"past_due", "blocked"}:
            expected_status = "active"

        if expected_status != tenant.subscription_status:
            tenant.subscription_status = expected_status
            tenant.is_active = expected_status != "canceled"
            db.add(tenant)
            changed += 1

        if expected_status == "blocked":
            blocked += 1
            open_alert = db.scalar(
                select(Job).where(
                    Job.tenant_id == tenant.id,
                    Job.job_type == "billing_delinquency",
                    Job.status.in_(["pending", "running"]),
                )
            )
            if not open_alert:
                db.add(
                    Job(
                        tenant_id=tenant.id,
                        job_type="billing_delinquency",
                        status="pending",
                        payload={
                            "title": "Risco de bloqueio por inadimplencia",
                            "severity": "alta",
                            "description": (
                                f"Tenant {tenant.trade_name} com {overdue_days} dia(s) de atraso."
                            ),
                            "days_overdue": overdue_days,
                            "grace_days": grace_days,
                        },
                        result={},
                        scheduled_for=now,
                    )
                )
        elif expected_status == "past_due":
            past_due += 1
        elif expected_status == "active":
            active += 1

        save_billing_state(
            db,
            tenant.id,
            {
                **state,
                "last_failed_at": state.get("last_failed_at") if overdue_days > 0 else None,
            },
        )

    db.commit()
    return {
        "checked_tenants": len(tenants),
        "updated_tenants": changed,
        "status_counts": {
            "active": active,
            "past_due": past_due,
            "blocked": blocked,
        },
    }

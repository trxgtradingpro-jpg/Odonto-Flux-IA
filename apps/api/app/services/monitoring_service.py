from __future__ import annotations

from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Job, Tenant

APP_STARTED_AT = datetime.now(UTC)


def _check_database(db: Session) -> dict[str, Any]:
    started = perf_counter()
    try:
        db.execute(text("SELECT 1"))
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return {"status": "up", "latency_ms": latency_ms}
    except Exception:
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return {"status": "down", "latency_ms": latency_ms}


def _check_redis() -> dict[str, Any]:
    started = perf_counter()
    try:
        client = Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            socket_connect_timeout=1,
        )
        client.ping()
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return {"status": "up", "latency_ms": latency_ms}
    except Exception:
        latency_ms = round((perf_counter() - started) * 1000, 2)
        return {"status": "down", "latency_ms": latency_ms}


def _open_incidents(db: Session) -> list[Job]:
    return (
        db.execute(
            select(Job).where(
                Job.job_type == "support_incident",
                Job.status.in_(["pending", "running"]),
            )
        )
        .scalars()
        .all()
    )


def monitoring_snapshot(db: Session) -> dict[str, Any]:
    now = datetime.now(UTC)
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(hours=24)

    db_service = _check_database(db)
    redis_service = _check_redis()
    services_ok = db_service["status"] == "up" and redis_service["status"] == "up"

    failed_jobs_last_hour = db.scalar(
        select(func.count(Job.id)).where(
            Job.status == "failed",
            Job.finished_at.is_not(None),
            Job.finished_at >= one_hour_ago,
        )
    ) or 0
    failed_jobs_24h = db.scalar(
        select(func.count(Job.id)).where(
            Job.status == "failed",
            Job.finished_at.is_not(None),
            Job.finished_at >= one_day_ago,
        )
    ) or 0

    recent_failures = (
        db.execute(
            select(Job)
            .where(Job.status == "failed")
            .order_by(Job.finished_at.desc().nullslast(), Job.created_at.desc())
            .limit(15)
        )
        .scalars()
        .all()
    )
    failures_data = [
        {
            "id": str(item.id),
            "job_type": item.job_type,
            "error_message": item.error_message,
            "attempts": item.attempts,
            "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        }
        for item in recent_failures
    ]

    incidents = _open_incidents(db)
    critical_incidents = [
        incident for incident in incidents if (incident.payload or {}).get("severity") == "critica"
    ]

    tenants_past_due = db.scalar(
        select(func.count(Tenant.id)).where(Tenant.subscription_status.in_(["past_due", "blocked"]))
    ) or 0
    tenants_blocked = db.scalar(
        select(func.count(Tenant.id)).where(Tenant.subscription_status == "blocked")
    ) or 0

    alerts: list[dict[str, str]] = []
    if not services_ok:
        alerts.append(
            {
                "severity": "critical",
                "title": "Infraestrutura degradada",
                "description": "API, banco de dados ou Redis sem resposta.",
            }
        )
    if failed_jobs_last_hour >= settings.monitoring_failed_jobs_threshold:
        severity = "critical" if failed_jobs_last_hour >= settings.monitoring_failed_jobs_threshold * 2 else "warning"
        alerts.append(
            {
                "severity": severity,
                "title": "Falhas de processamento",
                "description": (
                    f"{failed_jobs_last_hour} job(s) falharam na ultima hora."
                ),
            }
        )
    if critical_incidents:
        alerts.append(
            {
                "severity": "critical",
                "title": "Incidentes criticos em aberto",
                "description": f"{len(critical_incidents)} incidente(s) critico(s) aguardando resposta.",
            }
        )
    if tenants_blocked > 0:
        alerts.append(
            {
                "severity": "warning",
                "title": "Clientes bloqueados por inadimplencia",
                "description": f"{tenants_blocked} tenant(s) com operacao bloqueada.",
            }
        )

    return {
        "generated_at": now.isoformat(),
        "uptime_seconds": int((now - APP_STARTED_AT).total_seconds()),
        "services": {
            "api": {"status": "up"},
            "database": db_service,
            "redis": redis_service,
            "workers": {
                "status": "up" if failed_jobs_last_hour < settings.monitoring_failed_jobs_threshold else "degraded",
                "failed_jobs_last_hour": failed_jobs_last_hour,
            },
        },
        "errors": {
            "failed_jobs_last_hour": failed_jobs_last_hour,
            "failed_jobs_24h": failed_jobs_24h,
            "recent_failures": failures_data,
        },
        "incidents": {
            "open": len(incidents),
            "critical_open": len(critical_incidents),
        },
        "billing": {
            "tenants_past_due": tenants_past_due,
            "tenants_blocked": tenants_blocked,
        },
        "alerts": alerts,
        "alert_channels": settings.monitoring_alert_channels,
    }

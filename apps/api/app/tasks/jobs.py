from datetime import UTC, datetime
from uuid import UUID

from celery import shared_task
from sqlalchemy import select

from app.core.logging import logger
from app.db.session import SessionLocal
from app.models import Job
from app.services.automation_service import execute_automation_run, run_time_triggers
from app.services.billing_gateway_service import run_delinquency_check
from app.services.monitoring_service import monitoring_snapshot
from app.services.whatsapp_service import process_outbox_batch


@shared_task(name='app.tasks.jobs.execute_automation_run_task', bind=True, max_retries=3)
def execute_automation_run_task(self, run_id: str):
    db = SessionLocal()
    try:
        execute_automation_run(db, UUID(run_id))
        return {'status': 'ok', 'run_id': run_id}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=2**self.request.retries)
    finally:
        db.close()


@shared_task(name='app.tasks.jobs.process_whatsapp_outbox_task')
def process_whatsapp_outbox_task():
    db = SessionLocal()
    try:
        return process_outbox_batch(db, batch_size=40)
    finally:
        db.close()


@shared_task(name='app.tasks.jobs.run_time_automations_task')
def run_time_automations_task():
    db = SessionLocal()
    try:
        created = run_time_triggers(db)
        return {'runs_created': created}
    finally:
        db.close()


@shared_task(name='app.tasks.jobs.process_scheduled_jobs_task')
def process_scheduled_jobs_task():
    db = SessionLocal()
    now = datetime.now(UTC)
    try:
        jobs = db.execute(
            select(Job).where(
                Job.status == 'pending',
                Job.scheduled_for.is_not(None),
                Job.scheduled_for <= now,
            )
        ).scalars().all()

        processed = 0
        for job in jobs:
            job.status = 'running'
            job.started_at = now
            db.add(job)
            db.flush()

            try:
                job.status = 'success'
                job.result = {'message': 'job executado com sucesso'}
                job.finished_at = datetime.now(UTC)
            except Exception as exc:
                job.attempts += 1
                job.error_message = str(exc)
                if job.attempts >= job.max_attempts:
                    job.status = 'failed'
                    job.finished_at = datetime.now(UTC)
                else:
                    job.status = 'pending'
            db.add(job)
            processed += 1

        db.commit()
        return {'processed_jobs': processed}
    finally:
        db.close()


@shared_task(name='app.tasks.jobs.run_billing_delinquency_task')
def run_billing_delinquency_task():
    db = SessionLocal()
    try:
        return run_delinquency_check(db)
    finally:
        db.close()


@shared_task(name='app.tasks.jobs.monitor_platform_health_task')
def monitor_platform_health_task():
    db = SessionLocal()
    try:
        snapshot = monitoring_snapshot(db)
        if snapshot['alerts']:
            logger.warning(
                'platform_monitoring_alerts',
                alerts=snapshot['alerts'],
                failed_jobs_last_hour=snapshot['errors']['failed_jobs_last_hour'],
                critical_incidents=snapshot['incidents']['critical_open'],
            )
        else:
            logger.info(
                'platform_monitoring_ok',
                uptime_seconds=snapshot['uptime_seconds'],
                failed_jobs_last_hour=snapshot['errors']['failed_jobs_last_hour'],
            )
        return {
            'alerts': snapshot['alerts'],
            'failed_jobs_last_hour': snapshot['errors']['failed_jobs_last_hour'],
            'critical_incidents': snapshot['incidents']['critical_open'],
        }
    finally:
        db.close()

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    'odontoflux',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    timezone=settings.app_timezone,
    enable_utc=True,
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        'process-whatsapp-outbox': {
            'task': 'app.tasks.jobs.process_whatsapp_outbox_task',
            'schedule': 30.0,
        },
        'execute-time-automations': {
            'task': 'app.tasks.jobs.run_time_automations_task',
            'schedule': 60.0,
        },
        'process-scheduled-jobs': {
            'task': 'app.tasks.jobs.process_scheduled_jobs_task',
            'schedule': 45.0,
        },
        'run-billing-delinquency': {
            'task': 'app.tasks.jobs.run_billing_delinquency_task',
            'schedule': 300.0,
        },
        'monitor-platform-health': {
            'task': 'app.tasks.jobs.monitor_platform_health_task',
            'schedule': 120.0,
        },
    },
    imports=('app.tasks.jobs',),
)

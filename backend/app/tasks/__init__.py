from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "travel_planner",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.booking_tasks", "app.tasks.monitor_tasks"],
)

celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.task_track_started = True
celery_app.conf.worker_prefetch_multiplier = 1  # one task at a time per worker

# Run trip monitoring once per hour, every day
celery_app.conf.beat_schedule = {
    "scan-confirmed-trips": {
        "task": "app.tasks.monitor_tasks.scan_confirmed_trips",
        "schedule": crontab(minute=0),  # top of every hour
    },
}

"""Celery application. Workers: `celery -A config worker -Q default`."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

app = Celery("commandr")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

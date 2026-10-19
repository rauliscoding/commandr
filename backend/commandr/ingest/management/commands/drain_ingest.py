"""Drain the ingest stream into Postgres. Runs as the `drainer` service.

Long-running and independent of Celery. Several can run side by side (one
consumer group, distinct consumer names); stops cleanly on SIGTERM after the
batch in hand is written and acknowledged.
"""

import signal
import socket
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from commandr.ingest import stream


class Command(BaseCommand):
    help = "Write batches from the ingest stream to the database."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--once", action="store_true", help="Drain what is there and exit.")

    def handle(self, *args: Any, **options: Any) -> None:
        running = True

        def stop(signum: int, frame: object) -> None:
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        client = stream.get_client()
        consumer = f"{socket.gethostname()}-{id(self):x}"
        self.stdout.write(f"Draining {settings.INGEST_STREAM_KEY} as {consumer}")
        while running:
            close_old_connections()
            done = stream.drain_once(client, consumer, block_ms=0 if options["once"] else 5000)
            if options["once"] and done == 0:
                break

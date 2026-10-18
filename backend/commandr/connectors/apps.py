from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    name = "commandr.connectors"
    label = "connectors"

    def ready(self) -> None:
        from . import declarations  # noqa: F401  registers every connector

from django.apps import AppConfig


class ConnectorsConfig(AppConfig):
    name = "commandr.connectors"
    label = "connectors"

    def ready(self) -> None:
        from commandr.integrations.setup import register

        from . import declarations  # noqa: F401  registers every connector
        from .heartbeat.setup import HeartbeatSetup
        from .push_api.setup import PushApiSetup
        from .status_endpoint.setup import StatusEndpointSetup
        from .uptime_probe.setup import UptimeProbeSetup

        for setup in (UptimeProbeSetup(), HeartbeatSetup(), StatusEndpointSetup(), PushApiSetup()):
            register(setup)

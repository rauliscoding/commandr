"""JSON Schemas for the ingestion contract, v1.

A copy of `components.schemas` in docs/architecture/openapi/ingest-v1.yaml:
the docs are not shipped in the image, so the server cannot read the YAML at
run time. `tests/test_ingest_contract.py` fails if the two ever differ — edit
both together.
"""

from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

SCHEMAS: dict[str, Any] = {
    "MetricName": {"type": "string", "pattern": "^[a-z0-9_]+(\\.[a-z0-9_]+)*$", "maxLength": 120},
    "Attributes": {
        "type": "object",
        "maxProperties": 8,
        "propertyNames": {"pattern": "^[a-z0-9_]{1,64}$"},
        "additionalProperties": {"type": "string", "maxLength": 128},
    },
    "Resource": {
        "type": "object",
        "additionalProperties": False,
        "required": ["service"],
        "properties": {
            "service": {"type": "string", "maxLength": 120},
            "version": {"type": "string", "maxLength": 64},
            "environment": {"type": "string", "maxLength": 32},
        },
    },
    "Metric": {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "type", "value"],
        "properties": {
            "name": {"$ref": "#/components/schemas/MetricName"},
            "type": {"type": "string", "enum": ["counter", "gauge"]},
            "value": {"type": "number"},
            "ts": {
                "type": "string",
                "format": "date-time",
                "description": "Defaults to receipt time",
            },
            "interval_s": {
                "type": "integer",
                "minimum": 1,
                "maximum": 86400,
                "description": "For counters, the window the delta covers.",
            },
            "unit": {"type": "string", "maxLength": 32},
            "attrs": {"$ref": "#/components/schemas/Attributes"},
        },
    },
    "Event": {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "ts"],
        "properties": {
            "id": {
                "type": "string",
                "maxLength": 64,
                "description": "Client-generated",
                "used for de-duplication": None,
            },
            "name": {"$ref": "#/components/schemas/MetricName"},
            "ts": {"type": "string", "format": "date-time"},
            "props": {
                "type": "object",
                "maxProperties": 16,
                "additionalProperties": {
                    "oneOf": [
                        {"type": "string", "maxLength": 256},
                        {"type": "number"},
                        {"type": "boolean"},
                    ]
                },
            },
        },
    },
    "ErrorEvent": {
        "type": "object",
        "additionalProperties": False,
        "required": ["ts", "level", "fingerprint", "message"],
        "properties": {
            "id": {"type": "string", "maxLength": 64},
            "ts": {"type": "string", "format": "date-time"},
            "level": {"type": "string", "enum": ["warning", "error", "critical"]},
            "fingerprint": {"type": "string", "maxLength": 128},
            "type": {"type": "string", "maxLength": 200},
            "message": {"type": "string", "maxLength": 2000},
            "culprit": {"type": "string", "maxLength": 500},
            "stack": {"type": "string", "maxLength": 65536},
            "attrs": {"$ref": "#/components/schemas/Attributes"},
        },
    },
    "IngestBatch": {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema"],
        "properties": {
            "schema": {"const": "commandr.ingest/v1"},
            "sent_at": {"type": "string", "format": "date-time"},
            "resource": {"$ref": "#/components/schemas/Resource"},
            "metrics": {
                "type": "array",
                "maxItems": 1000,
                "items": {"$ref": "#/components/schemas/Metric"},
            },
            "events": {
                "type": "array",
                "maxItems": 1000,
                "items": {"$ref": "#/components/schemas/Event"},
            },
            "errors": {
                "type": "array",
                "maxItems": 200,
                "items": {"$ref": "#/components/schemas/ErrorEvent"},
            },
        },
    },
    "IngestResult": {
        "type": "object",
        "required": ["accepted", "rejected"],
        "properties": {
            "accepted": {"type": "integer", "minimum": 0},
            "rejected": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["section", "index", "code", "message"],
                    "properties": {
                        "section": {"type": "string", "enum": ["metrics", "events", "errors"]},
                        "index": {"type": "integer", "minimum": 0},
                        "code": {
                            "type": "string",
                            "enum": [
                                "invalid",
                                "too_old",
                                "in_future",
                                "cardinality_limit",
                                "quota_exceeded",
                                "personal_data",
                                "duplicate",
                            ],
                        },
                        "message": {"type": "string"},
                    },
                },
            },
        },
    },
    "Check": {
        "type": "object",
        "required": ["key", "status"],
        "properties": {
            "key": {"type": "string", "maxLength": 200},
            "name": {"type": "string", "maxLength": 200},
            "status": {"type": "string", "enum": ["ok", "warn", "fail", "unknown"]},
            "summary": {"type": "string", "maxLength": 500},
            "value": {"type": "number"},
            "unit": {"type": "string", "maxLength": 32},
        },
    },
    "Gauge": {
        "type": "object",
        "required": ["name", "value"],
        "properties": {
            "name": {"$ref": "#/components/schemas/MetricName"},
            "value": {"type": "number"},
            "unit": {"type": "string", "maxLength": 32},
            "attrs": {"$ref": "#/components/schemas/Attributes"},
        },
    },
    "Kpi": {
        "type": "object",
        "required": ["name", "value"],
        "properties": {
            "name": {"$ref": "#/components/schemas/MetricName"},
            "label": {"type": "string", "maxLength": 120},
            "value": {
                "type": ["number", "null"],
                "description": "null means not available",
                "never 0": None,
            },
            "unit": {"type": "string", "maxLength": 32},
        },
    },
    "StatusDocument": {
        "type": "object",
        "required": ["schema", "service", "checks"],
        "properties": {
            "schema": {"const": "commandr.status/v1"},
            "service": {"type": "string", "maxLength": 120},
            "version": {"type": "string", "maxLength": 64},
            "environment": {"type": "string", "maxLength": 32},
            "generated_at": {"type": "string", "format": "date-time"},
            "checks": {
                "type": "array",
                "maxItems": 500,
                "items": {"$ref": "#/components/schemas/Check"},
            },
            "gauges": {
                "type": "array",
                "maxItems": 500,
                "items": {"$ref": "#/components/schemas/Gauge"},
            },
            "kpis": {
                "type": "array",
                "maxItems": 100,
                "items": {"$ref": "#/components/schemas/Kpi"},
            },
        },
    },
    "Problem": {
        "type": "object",
        "description": "RFC 9457 problem details",
        "properties": {
            "type": {"type": "string", "format": "uri"},
            "title": {"type": "string"},
            "status": {"type": "integer"},
            "detail": {"type": "string"},
            "code": {"type": "string"},
        },
    },
}

_ROOT = {"components": {"schemas": SCHEMAS}}


def validator(name: str, **overrides: Any) -> Draft202012Validator:
    """A validator for one named schema, `$ref`s resolved against the document.

    `overrides` replace top-level keywords of that schema (used to check the
    batch envelope without its items, so one bad item never rejects the rest).
    """
    schema = {**SCHEMAS[name], **overrides, **_ROOT}
    return Draft202012Validator(schema, format_checker=FormatChecker())

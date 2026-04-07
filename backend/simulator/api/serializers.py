"""
DRF serializers for the simulation API.

Validates incoming requests and structures outgoing responses.
No business logic lives here — only shape and type validation.
"""

from __future__ import annotations

from rest_framework import serializers


# ---------------------------------------------------------------------------
# Request serializers
# ---------------------------------------------------------------------------

class SimulationRequestSerializer(serializers.Serializer):
    """
    POST /api/simulate/

    Supports two usage modes:

    1. **Unified mode** — provide ``code`` and both engines receive the
       same source.  Parsing errors on one side are reported but don't
       block the other.

    2. **Split mode** — provide ``risc_code`` and/or ``cisc_code``
       separately so each architecture gets idiomatic assembly.

    At least one of ``code``, ``risc_code``, or ``cisc_code`` must be
    provided.
    """
    code = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Assembly code to send to BOTH engines (unified mode).",
    )
    risc_code = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="RISC-specific assembly code.",
    )
    cisc_code = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="CISC-specific assembly code.",
    )
    step = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Execute only the next instruction (step mode).",
    )
    pipeline = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Use RISC 5-stage pipeline simulation.",
    )
    transpile = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Interpret 'code' as common dialect and transpile to both architectures.",
    )
    risc_tcycle = serializers.FloatField(
        required=False,
        default=1.0,
        min_value=0.01,
        help_text="RISC clock period in nanoseconds.",
    )
    cisc_tcycle = serializers.FloatField(
        required=False,
        default=1.5,
        min_value=0.01,
        help_text="CISC clock period in nanoseconds.",
    )

    def validate(self, attrs):
        code = attrs.get("code", "").strip()
        risc_code = attrs.get("risc_code", "").strip()
        cisc_code = attrs.get("cisc_code", "").strip()

        if not code and not risc_code and not cisc_code:
            raise serializers.ValidationError(
                "At least one of 'code', 'risc_code', or 'cisc_code' must be provided."
            )
        return attrs


class SingleArchRequestSerializer(serializers.Serializer):
    """Serializer for single-architecture endpoints (/api/simulate/risc/ etc.)."""
    code = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="Assembly source code.",
    )
    step = serializers.BooleanField(required=False, default=False)
    pipeline = serializers.BooleanField(required=False, default=False)
    risc_tcycle = serializers.FloatField(required=False, default=1.0, min_value=0.01)
    cisc_tcycle = serializers.FloatField(required=False, default=1.5, min_value=0.01)


# ---------------------------------------------------------------------------
# Response serializers (contract documentation)
# ---------------------------------------------------------------------------

class EventSerializer(serializers.Serializer):
    component = serializers.CharField()
    action = serializers.CharField()
    inputs = serializers.ListField()
    output = serializers.JSONField()
    meta = serializers.DictField(required=False)


class CycleSerializer(serializers.Serializer):
    cycle = serializers.IntegerField()
    events = EventSerializer(many=True)


class MetricsSerializer(serializers.Serializer):
    instruction_count = serializers.IntegerField()
    total_cycles = serializers.IntegerField()
    cpi = serializers.FloatField()
    t_cycle_ns = serializers.FloatField()
    cpu_time_ns = serializers.FloatField()
    cpu_time_us = serializers.FloatField()


class ArchitectureResultSerializer(serializers.Serializer):
    timeline = CycleSerializer(many=True)
    metrics = MetricsSerializer()
    final_state = serializers.DictField()


class SimulationResponseSerializer(serializers.Serializer):
    risc = ArchitectureResultSerializer()
    cisc = ArchitectureResultSerializer()
    comparison = serializers.DictField()

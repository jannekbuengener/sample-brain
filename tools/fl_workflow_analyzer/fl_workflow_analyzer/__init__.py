"""Deterministic FL workflow reconstruction analyzer (#1322).

Consumes immutable raw events from the #1321 recorder sidecar.
Does not modify recorder capture, sessionization, or privacy contracts.
"""

from __future__ import annotations

__all__ = ["ANALYZER_VERSION", "RULE_VERSION", "DERIVED_SCHEMA_VERSION"]

ANALYZER_VERSION = "1.0.0"
RULE_VERSION = 7
DERIVED_SCHEMA_VERSION = 1

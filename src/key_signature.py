"""Compatibility alias for the external `sample_brain_analysis.key_signature` owner.

Implementation authority lives in `jannekbuengener/sample-brain-analysis`.
This module preserves the historical `src.*` import and monkeypatch surface only.
"""

from importlib import import_module as _import_module
import sys as _sys

_external_module = _import_module("sample_brain_analysis.key_signature")
_sys.modules[__name__] = _external_module

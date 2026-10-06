"""Reusable analyzer perturbation / metamorphic fixture mechanics (#957).

Owns transform mechanics + provenance only. Does not own AQ1–AQ7 musical
expectations, tolerances, or promotion gates. Does not couple to the
product Fit Variant cache path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import soundfile as sf

from .content_hash import compute_file_hash

CONTRACT_ID = "sample-brain.analyzer-perturbation.v1"
CONTRACT_VERSION = "1"

SUPPORTED_TRANSFORMS: frozenset[str] = frozenset(
    {
        "gain",
        "peak_normalize",
        "to_mono",
        "to_stereo",
        "resample",
        "pad_silence",
        "trim",
        "pitch_shift",
        "time_stretch",
    }
)

UNSUPPORTED_TRANSFORMS: frozenset[str] = frozenset(
    {
        "energy_trim_silence",
    }
)

_TRANSFORM_VERSION = "1"


class ValidationError(ValueError):
    """Invalid or non-finite transform specification."""


class UnsupportedTransformError(ValueError):
    """Requested transform is explicitly unsupported or unknown."""


@dataclass(frozen=True)
class _AudioBuffer:
    samples: np.ndarray  # shape (n,) mono or (n, ch) multi
    sample_rate: int

    @property
    def channels(self) -> int:
        if self.samples.ndim == 1:
            return 1
        return int(self.samples.shape[1])

    @property
    def n_samples(self) -> int:
        return int(self.samples.shape[0])


def describe_capabilities() -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "supported": sorted(SUPPORTED_TRANSFORMS),
        "unsupported": sorted(UNSUPPORTED_TRANSFORMS),
    }


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _require_finite_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValidationError(f"{name} must be finite")
    return number


def _require_non_negative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be a non-negative integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValidationError(f"{name} must be a non-negative integer")
    number = int(value)
    if number < 0:
        raise ValidationError(f"{name} must be a non-negative integer")
    return number


def _require_positive_int(name: str, value: Any) -> int:
    number = _require_non_negative_int(name, value)
    if number <= 0:
        raise ValidationError(f"{name} must be a positive integer")
    return number


def _validate_params(transform_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(params, Mapping):
        raise ValidationError("params must be an object")
    params = dict(params)

    if transform_id == "gain":
        allowed = {"factor"}
        if set(params) != allowed:
            raise ValidationError("gain params must be exactly {factor}")
        factor = _require_finite_number("factor", params["factor"])
        if factor <= 0.0:
            raise ValidationError("gain factor must be > 0")
        return {"factor": factor}

    if transform_id == "peak_normalize":
        allowed = {"target_peak"}
        if set(params) != allowed:
            raise ValidationError("peak_normalize params must be exactly {target_peak}")
        peak = _require_finite_number("target_peak", params["target_peak"])
        if peak <= 0.0 or peak > 1.0:
            raise ValidationError("target_peak must be in (0, 1]")
        return {"target_peak": peak}

    if transform_id == "to_mono":
        allowed = {"method"}
        if set(params) != allowed:
            raise ValidationError("to_mono params must be exactly {method}")
        method = params["method"]
        if method != "mean":
            raise ValidationError("to_mono method must be 'mean'")
        return {"method": method}

    if transform_id == "to_stereo":
        allowed = {"method"}
        if set(params) != allowed:
            raise ValidationError("to_stereo params must be exactly {method}")
        method = params["method"]
        if method != "duplicate":
            raise ValidationError("to_stereo method must be 'duplicate'")
        return {"method": method}

    if transform_id == "resample":
        allowed = {"target_sr"}
        if set(params) != allowed:
            raise ValidationError("resample params must be exactly {target_sr}")
        return {"target_sr": _require_positive_int("target_sr", params["target_sr"])}

    if transform_id == "pad_silence":
        allowed = {"leading_samples", "trailing_samples"}
        if set(params) != allowed:
            raise ValidationError(
                "pad_silence params must be exactly {leading_samples, trailing_samples}"
            )
        return {
            "leading_samples": _require_non_negative_int(
                "leading_samples", params["leading_samples"]
            ),
            "trailing_samples": _require_non_negative_int(
                "trailing_samples", params["trailing_samples"]
            ),
        }

    if transform_id == "trim":
        allowed = {"leading_samples", "trailing_samples"}
        if set(params) != allowed:
            raise ValidationError(
                "trim params must be exactly {leading_samples, trailing_samples}"
            )
        return {
            "leading_samples": _require_non_negative_int(
                "leading_samples", params["leading_samples"]
            ),
            "trailing_samples": _require_non_negative_int(
                "trailing_samples", params["trailing_samples"]
            ),
        }

    if transform_id == "pitch_shift":
        allowed = {"n_steps"}
        if set(params) != allowed:
            raise ValidationError("pitch_shift params must be exactly {n_steps}")
        return {"n_steps": _require_finite_number("n_steps", params["n_steps"])}

    if transform_id == "time_stretch":
        allowed = {"rate"}
        if set(params) != allowed:
            raise ValidationError("time_stretch params must be exactly {rate}")
        rate = _require_finite_number("rate", params["rate"])
        if rate <= 0.0:
            raise ValidationError("time_stretch rate must be > 0")
        return {"rate": rate}

    raise UnsupportedTransformError(f"unsupported transform id: {transform_id!r}")


def validate_transform_spec(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize a perturbation spec (fail closed)."""
    if not isinstance(spec, Mapping):
        raise ValidationError("spec must be an object")
    contract_id = spec.get("contract_id")
    contract_version = spec.get("contract_version")
    transforms = spec.get("transforms")
    if contract_id != CONTRACT_ID:
        raise ValidationError(f"contract_id must be {CONTRACT_ID!r}")
    if contract_version != CONTRACT_VERSION:
        raise ValidationError(f"contract_version must be {CONTRACT_VERSION!r}")
    if not isinstance(transforms, Sequence) or isinstance(transforms, (str, bytes)):
        raise ValidationError("transforms must be a list")

    canonical_steps: list[dict[str, Any]] = []
    for index, step in enumerate(transforms):
        if not isinstance(step, Mapping):
            raise ValidationError(f"transforms[{index}] must be an object")
        unknown = set(step) - {"id", "version", "params"}
        if unknown:
            raise ValidationError(
                f"transforms[{index}] has unknown keys: {sorted(unknown)}"
            )
        transform_id = step.get("id")
        version = step.get("version")
        params = step.get("params")
        if not isinstance(transform_id, str):
            raise ValidationError(f"transforms[{index}].id must be a string")
        if transform_id in UNSUPPORTED_TRANSFORMS:
            raise UnsupportedTransformError(
                f"transform {transform_id!r} is explicitly unsupported"
            )
        if transform_id not in SUPPORTED_TRANSFORMS:
            raise UnsupportedTransformError(
                f"unknown transform id: {transform_id!r}"
            )
        if version != _TRANSFORM_VERSION:
            raise ValidationError(
                f"transforms[{index}].version must be {_TRANSFORM_VERSION!r}"
            )
        canonical_steps.append(
            {
                "id": transform_id,
                "version": _TRANSFORM_VERSION,
                "params": _validate_params(transform_id, params or {}),
            }
        )

    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "transforms": canonical_steps,
    }


def compute_derived_identity(source_path: Path, spec: Mapping[str, Any]) -> str:
    """Path-independent semantic identity for source bytes + transform spec."""
    canonical = validate_transform_spec(spec)
    source_hash = compute_file_hash(Path(source_path))
    payload = {
        "contract_id": canonical["contract_id"],
        "contract_version": canonical["contract_version"],
        "source_content_hash": source_hash,
        "transforms": canonical["transforms"],
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return digest


def _librosa_version() -> str:
    try:
        return metadata.version("librosa")
    except metadata.PackageNotFoundError:
        return "unknown"


def _load_source(path: Path) -> _AudioBuffer:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    with sf.SoundFile(str(path)) as handle:
        samples = handle.read(dtype="float32", always_2d=False)
        sample_rate = int(handle.samplerate)
    samples = np.asarray(samples, dtype=np.float32)
    if samples.size == 0:
        raise ValidationError("source audio is empty")
    return _AudioBuffer(samples=samples, sample_rate=sample_rate)


def _as_channels_first(buffer: _AudioBuffer) -> np.ndarray:
    if buffer.samples.ndim == 1:
        return buffer.samples.reshape(1, -1)
    return buffer.samples.T


def _from_channels_first(channels_first: np.ndarray, sample_rate: int) -> _AudioBuffer:
    arr = np.asarray(channels_first, dtype=np.float32)
    if arr.ndim != 2:
        raise ValidationError("internal channel layout error")
    if arr.shape[0] == 1:
        return _AudioBuffer(samples=arr[0], sample_rate=sample_rate)
    return _AudioBuffer(samples=arr.T, sample_rate=sample_rate)


def _apply_gain(buffer: _AudioBuffer, factor: float) -> _AudioBuffer:
    return _AudioBuffer(
        samples=np.asarray(buffer.samples * factor, dtype=np.float32),
        sample_rate=buffer.sample_rate,
    )


def _apply_peak_normalize(buffer: _AudioBuffer, target_peak: float) -> _AudioBuffer:
    peak = float(np.max(np.abs(buffer.samples)))
    if not math.isfinite(peak) or peak <= 0.0:
        raise ValidationError("peak_normalize requires a positive finite peak")
    return _apply_gain(buffer, target_peak / peak)


def _apply_to_mono(buffer: _AudioBuffer) -> _AudioBuffer:
    if buffer.channels == 1:
        return buffer
    mono = np.mean(buffer.samples, axis=1).astype(np.float32)
    return _AudioBuffer(samples=mono, sample_rate=buffer.sample_rate)


def _apply_to_stereo(buffer: _AudioBuffer) -> _AudioBuffer:
    if buffer.channels == 1:
        mono = buffer.samples if buffer.samples.ndim == 1 else buffer.samples[:, 0]
        stereo = np.stack([mono, mono], axis=1).astype(np.float32)
        return _AudioBuffer(samples=stereo, sample_rate=buffer.sample_rate)
    if buffer.channels == 2:
        raise ValidationError("to_stereo refuses multi-channel sources with >1 channel")
    raise ValidationError("to_stereo requires mono input")


def _apply_resample(buffer: _AudioBuffer, target_sr: int) -> _AudioBuffer:
    if target_sr == buffer.sample_rate:
        return buffer
    import librosa

    channels_first = _as_channels_first(buffer)
    resampled = librosa.resample(
        channels_first,
        orig_sr=buffer.sample_rate,
        target_sr=target_sr,
    )
    return _from_channels_first(np.asarray(resampled, dtype=np.float32), target_sr)


def _apply_pad_silence(
    buffer: _AudioBuffer, leading_samples: int, trailing_samples: int
) -> _AudioBuffer:
    if leading_samples == 0 and trailing_samples == 0:
        return buffer
    if buffer.channels == 1:
        padded = np.pad(
            buffer.samples,
            (leading_samples, trailing_samples),
            mode="constant",
            constant_values=0.0,
        )
    else:
        padded = np.pad(
            buffer.samples,
            ((leading_samples, trailing_samples), (0, 0)),
            mode="constant",
            constant_values=0.0,
        )
    return _AudioBuffer(samples=padded.astype(np.float32), sample_rate=buffer.sample_rate)


def _apply_trim(
    buffer: _AudioBuffer, leading_samples: int, trailing_samples: int
) -> _AudioBuffer:
    end = buffer.n_samples - trailing_samples
    if leading_samples >= end:
        raise ValidationError("trim would remove all samples")
    trimmed = buffer.samples[leading_samples:end]
    if trimmed.shape[0] < 1:
        raise ValidationError("trim would remove all samples")
    return _AudioBuffer(
        samples=np.asarray(trimmed, dtype=np.float32),
        sample_rate=buffer.sample_rate,
    )


def _apply_pitch_shift(buffer: _AudioBuffer, n_steps: float) -> _AudioBuffer:
    if math.isclose(n_steps, 0.0, rel_tol=0.0, abs_tol=1e-12):
        return buffer
    import librosa

    channels_first = _as_channels_first(buffer)
    shifted = librosa.effects.pitch_shift(
        channels_first,
        sr=buffer.sample_rate,
        n_steps=n_steps,
    )
    return _from_channels_first(np.asarray(shifted, dtype=np.float32), buffer.sample_rate)


def _apply_time_stretch(buffer: _AudioBuffer, rate: float) -> _AudioBuffer:
    if math.isclose(rate, 1.0, rel_tol=0.0, abs_tol=1e-12):
        return buffer
    import librosa

    channels_first = _as_channels_first(buffer)
    stretched = librosa.effects.time_stretch(channels_first, rate=rate)
    return _from_channels_first(
        np.asarray(stretched, dtype=np.float32), buffer.sample_rate
    )


def _apply_step(buffer: _AudioBuffer, step: Mapping[str, Any]) -> _AudioBuffer:
    transform_id = step["id"]
    params = step["params"]
    if transform_id == "gain":
        return _apply_gain(buffer, params["factor"])
    if transform_id == "peak_normalize":
        return _apply_peak_normalize(buffer, params["target_peak"])
    if transform_id == "to_mono":
        return _apply_to_mono(buffer)
    if transform_id == "to_stereo":
        return _apply_to_stereo(buffer)
    if transform_id == "resample":
        return _apply_resample(buffer, params["target_sr"])
    if transform_id == "pad_silence":
        return _apply_pad_silence(
            buffer, params["leading_samples"], params["trailing_samples"]
        )
    if transform_id == "trim":
        return _apply_trim(
            buffer, params["leading_samples"], params["trailing_samples"]
        )
    if transform_id == "pitch_shift":
        return _apply_pitch_shift(buffer, params["n_steps"])
    if transform_id == "time_stretch":
        return _apply_time_stretch(buffer, params["rate"])
    raise UnsupportedTransformError(f"unsupported transform id: {transform_id!r}")


def apply_transforms(
    buffer: _AudioBuffer, transforms: Sequence[Mapping[str, Any]]
) -> _AudioBuffer:
    current = buffer
    for step in transforms:
        current = _apply_step(current, step)
    return current


def materialize_derived_fixture(
    source_path: Path,
    spec: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    """Apply validated transforms and write a derived WAV without mutating source.

    ``output_path`` is process-local convenience and is not part of semantic identity.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    if source_path.resolve() == output_path.resolve():
        raise ValidationError("source and destination must be different paths")

    canonical = validate_transform_spec(spec)
    derived_identity = compute_derived_identity(source_path, canonical)
    source_hash = compute_file_hash(source_path)

    buffer = _load_source(source_path)
    rendered = apply_transforms(buffer, canonical["transforms"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(
        str(output_path),
        rendered.samples,
        rendered.sample_rate,
        subtype="PCM_16",
        format="WAV",
    )

    uses_librosa = any(
        step["id"] in {"resample", "pitch_shift", "time_stretch"}
        for step in canonical["transforms"]
    )
    provenance: dict[str, Any] = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "source": {"content_hash": source_hash},
        "transforms": canonical["transforms"],
        "derived_identity": derived_identity,
        "backend": {
            "name": "librosa" if uses_librosa else "numpy_soundfile",
            "librosa_version": _librosa_version() if uses_librosa else None,
        },
        # Local-only convenience; callers must not treat this as semantic identity.
        "output_path": str(output_path),
    }
    return provenance


__all__ = [
    "CONTRACT_ID",
    "CONTRACT_VERSION",
    "SUPPORTED_TRANSFORMS",
    "UNSUPPORTED_TRANSFORMS",
    "ValidationError",
    "UnsupportedTransformError",
    "describe_capabilities",
    "validate_transform_spec",
    "compute_derived_identity",
    "materialize_derived_fixture",
]

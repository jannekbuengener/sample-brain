"""Frozen tests for AQ6 headless ranking-compare adapter (#1054 M4).

TEST FREEZE: these assertions define the thin AQ6 DomainAdapter contract.
Fix the adapter — not these expectations — when they turn red. Wrap only
``run_aq6_harmonic_ranking_candidate_compare``; do not rewrite ranking/
theory algorithms, blend planes into one fake score, mutate the shared
STATIC_ADAPTER_REGISTRY, or invent a preference signal.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import (
    DOCUMENT_TYPE,
    DomainAdapter,
    STATIC_ADAPTER_REGISTRY,
    build_request,
    result_semantic_fingerprint,
    serialize_result,
    validate_result,
)
from src.aq6_harmonic_ranking_candidate_compare import (
    DOCUMENT_TYPE as AQ6_COMPARE_DOCUMENT_TYPE,
    EXIT_REPRODUCIBLE,
    HARMONIC_RANKING_CANDIDATES,
    candidate_public,
)
from src.aq6_harmonic_ranking_relevance import (
    BENCHMARK_ID,
    FIXTURE_RELPATH as RANKING_FIXTURE_RELPATH,
    load_relevance_benchmark_fixture,
)
from src.aq_headless_adapters.aq6_harmonic_ranking_compare import (
    ADAPTER_CAPABILITIES,
    ADAPTER_ID,
    ADAPTER_VERSION,
    DOMAIN_TOKEN,
    Aq6HarmonicRankingCompareAdapter,
    candidate_config_fingerprint,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
RANKING_FIXTURE = REPO_ROOT / RANKING_FIXTURE_RELPATH


@pytest.fixture
def external_out_dir() -> Iterator[Path]:
    """Temp dir guaranteed outside the git tree (AQ6 runner hard requirement)."""
    root = Path(tempfile.gettempdir()).resolve()
    try:
        root.relative_to(REPO_ROOT.resolve())
    except ValueError:
        pass
    else:
        pytest.skip("system tempdir is inside the repository")
    path = Path(tempfile.mkdtemp(prefix="sb-aq6-headless-", dir=str(root)))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _dataset_fingerprint() -> str:
    return fingerprint(load_relevance_benchmark_fixture(RANKING_FIXTURE))


def _baseline_fp() -> str:
    return candidate_config_fingerprint("harmonic.baseline.v1")


def _current_fp() -> str:
    return candidate_config_fingerprint("harmonic.rank_filter.drop_uncertain")


def _compare_request(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "domain": DOMAIN_TOKEN,
        "adapter_id": ADAPTER_ID,
        "operation": "compare",
        "benchmark_id": BENCHMARK_ID,
        "dataset_id": "aq6-harmonic-ranking-relevance-v1",
        "dataset_content_fingerprint": _dataset_fingerprint(),
        "partition_id": "aq6-cal-ranking-compare",
        "partition_role": "calibration",
        "baseline_candidate_id": "harmonic.baseline.v1",
        "baseline_config_fingerprint": _baseline_fp(),
        "current_candidate_id": "harmonic.rank_filter.drop_uncertain",
        "current_config_fingerprint": _current_fp(),
        "evidence_intent": "domain_artifact",
    }
    kwargs.update(overrides)
    return build_request(**kwargs)


def _adapter(external_out_dir: Path) -> Aq6HarmonicRankingCompareAdapter:
    return Aq6HarmonicRankingCompareAdapter(
        output_path=external_out_dir / "aq6-ranking-candidate-compare.json",
        repo_root=REPO_ROOT,
    )


def test_adapter_identity_and_capabilities_are_frozen() -> None:
    assert ADAPTER_ID == "aq6.ranking.candidate_compare"
    assert ADAPTER_VERSION == "1.0.0"
    assert DOMAIN_TOKEN == "aq6.ranking"
    assert ADAPTER_CAPABILITIES == frozenset({"compare", "locked_evaluation"})
    adapter = Aq6HarmonicRankingCompareAdapter(
        output_path=Path("unused.json"),
        repo_root=REPO_ROOT,
    )
    assert adapter.adapter_id == ADAPTER_ID
    assert adapter.adapter_version == ADAPTER_VERSION
    assert adapter.capabilities == ADAPTER_CAPABILITIES
    assert isinstance(adapter, DomainAdapter)


def test_candidate_config_fingerprints_match_public_identity() -> None:
    for candidate in HARMONIC_RANKING_CANDIDATES:
        assert candidate_config_fingerprint(candidate.candidate_id) == fingerprint(
            candidate_public(candidate)
        )


def test_static_registry_remains_empty_after_import() -> None:
    assert dict(STATIC_ADAPTER_REGISTRY) == {}
    assert ADAPTER_ID not in STATIC_ADAPTER_REGISTRY


def test_headless_compare_completes_with_multi_plane_provenance(
    external_out_dir: Path,
) -> None:
    adapter = _adapter(external_out_dir)
    request = _compare_request()
    result = adapter.run(request)

    assert result["document_type"] == DOCUMENT_TYPE
    assert result["run_status"] == "completed"
    assert result["adapter_id"] == ADAPTER_ID
    assert result["adapter_version"] == ADAPTER_VERSION
    assert result["domain"] == DOMAIN_TOKEN
    assert result["operation"] == "compare"
    assert result["production_authorized"] is False
    assert "decision_token" not in result
    assert "next_action" not in result
    assert "metrics" not in result
    assert "metric_values" not in result
    assert "analysis_eval" not in result

    domain_artifact = result["domain_artifact"]
    assert domain_artifact["artifact_id"] == AQ6_COMPARE_DOCUMENT_TYPE
    assert len(domain_artifact["artifact_fingerprint"]) == 64

    planes = result["domain_planes"]
    # plane_id (not "token") — W0 assert_portable_value forbids key name "token".
    assert planes["ranking"]["plane_id"] == "aq6.ranking"
    assert planes["ranking"]["exit_status"] == EXIT_REPRODUCIBLE
    assert planes["ranking"]["mixed_into_aggregate_score"] is False
    assert planes["theory"]["plane_id"] == "aq6.theory"
    assert planes["theory"]["hard_gate"] is True
    assert planes["theory"]["mixed_into_ranking_metrics"] is False
    assert planes["theory"]["all_candidates_pass"] is True
    assert planes["preference"]["plane_id"] == "aq6.preference"
    assert planes["preference"]["status"] == "NOT_REQUIRED"
    assert planes["preference"]["signal"] is None

    # Ranking vs theory stay separate lists — never one blended score.
    assert "aggregate_score" not in result
    assert "blended_score" not in result
    assert "global_score" not in planes

    out = external_out_dir / "aq6-ranking-candidate-compare.json"
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["exit_status"] == EXIT_REPRODUCIBLE
    assert loaded["theory_plane"]["mixed_into_ranking_metrics"] is False
    assert fingerprint(loaded) == domain_artifact["artifact_fingerprint"]

    validated = validate_result(result)
    blob = serialize_result(validated)
    assert "D:/" not in blob
    assert "C:/" not in blob
    assert "decision_token" not in blob


def test_repeated_invocation_is_deterministic(external_out_dir: Path) -> None:
    request = _compare_request()
    first = _adapter(external_out_dir / "a").run(request)
    second = _adapter(external_out_dir / "b").run(request)
    assert result_semantic_fingerprint(first) == result_semantic_fingerprint(second)
    assert first["domain_artifact"]["artifact_fingerprint"] == (
        second["domain_artifact"]["artifact_fingerprint"]
    )


def test_locked_evaluation_on_test_partition_allowed(
    external_out_dir: Path,
) -> None:
    request = _compare_request(
        operation="locked_evaluation",
        partition_id="aq6-test-locked",
        partition_role="test",
        evidence_intent="locked_evaluation",
    )
    result = _adapter(external_out_dir).run(request)
    assert result["run_status"] == "completed"
    assert result["operation"] == "locked_evaluation"
    assert result["partition"]["role"] == "test"
    assert result["domain_planes"]["ranking"]["exit_status"] == EXIT_REPRODUCIBLE


def test_unsupported_operation_is_controlled_failure(
    external_out_dir: Path,
) -> None:
    # baseline op validates at the envelope layer but is not an adapter capability.
    request = build_request(
        domain=DOMAIN_TOKEN,
        adapter_id=ADAPTER_ID,
        operation="baseline",
        benchmark_id=BENCHMARK_ID,
        dataset_id="aq6-harmonic-ranking-relevance-v1",
        dataset_content_fingerprint=_dataset_fingerprint(),
        partition_id="aq6-cal-baseline",
        partition_role="calibration",
        baseline_candidate_id="harmonic.baseline.v1",
        baseline_config_fingerprint=_baseline_fp(),
        evidence_intent="domain_artifact",
    )
    result = _adapter(external_out_dir).run(request)
    assert result["run_status"] == "controlled_failure"
    assert result["error"]["code"] == "unsupported_operation"
    assert "domain_artifact" not in result


def test_adapter_id_mismatch_is_controlled_failure(
    external_out_dir: Path,
) -> None:
    request = _compare_request(adapter_id="aq1.tempo.candidate_compare")
    result = _adapter(external_out_dir).run(request)
    assert result["run_status"] == "controlled_failure"
    assert result["error"]["code"] == "adapter_mismatch"
    assert result["adapter_id"] == ADAPTER_ID


def test_output_inside_repo_is_controlled_failure() -> None:
    inside = REPO_ROOT / ".pytest_aq6_headless_should_not_exist.json"
    adapter = Aq6HarmonicRankingCompareAdapter(
        output_path=inside,
        repo_root=REPO_ROOT,
    )
    try:
        result = adapter.run(_compare_request())
        assert result["run_status"] == "controlled_failure"
        assert result["error"]["code"] == "output_path_rejected"
        assert not inside.exists()
    finally:
        if inside.exists():
            inside.unlink()


def test_unknown_candidate_identity_is_controlled_failure(
    external_out_dir: Path,
) -> None:
    request = _compare_request(
        current_candidate_id="harmonic.not.real",
        current_config_fingerprint=fingerprint({"candidate_id": "harmonic.not.real"}),
    )
    result = _adapter(external_out_dir).run(request)
    assert result["run_status"] == "controlled_failure"
    assert result["error"]["code"] == "unknown_candidate"

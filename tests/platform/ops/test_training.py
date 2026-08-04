from __future__ import annotations

import pytest

from vesper.platform.ops.training import (
    AdapterUnavailable,
    CandidateTrainingRequest,
    UnavailableQwenWorkPort,
    UnavailableTrainingPort,
    WorkItem,
)


def test_unavailable_qwen_port_never_claims_or_fails_queued_work() -> None:
    port = UnavailableQwenWorkPort()

    capability = port.available()
    assert capability.state.value == "disabled"
    assert capability.reason == "The qwen:64k runtime adapter is not configured."
    with pytest.raises(AdapterUnavailable, match="qwen:64k"):
        port.run_one(
            WorkItem(
                work_id="work-1",
                kind="normal",
                agent_id="v20-product",
                objective="Review V20 state.",
            )
        )


def test_unavailable_training_port_starts_nothing() -> None:
    port = UnavailableTrainingPort()
    request = CandidateTrainingRequest(
        request_id="candidate-1",
        model_family="approved-family",
        strategy="ml_model",
        feature_set_id="features-1",
        data_identity="massive-snapshot-1",
        evaluation_contract="evaluation-1",
        artifact_root="candidates/candidate-1",
    )

    capability = port.available()
    assert capability.state.value == "disabled"
    assert capability.reason == "No approved candidate training adapter is configured."
    with pytest.raises(AdapterUnavailable, match="training adapter"):
        port.train_and_evaluate(request)


def test_candidate_request_binds_every_approved_input() -> None:
    request = CandidateTrainingRequest(
        request_id="candidate-1",
        model_family="approved-family",
        strategy="ml_model",
        feature_set_id="features-1",
        data_identity="massive-snapshot-1",
        evaluation_contract="evaluation-1",
        artifact_root="candidates/candidate-1",
    )

    assert request.model_dump() == {
        "request_id": "candidate-1",
        "model_family": "approved-family",
        "strategy": "ml_model",
        "feature_set_id": "features-1",
        "data_identity": "massive-snapshot-1",
        "evaluation_contract": "evaluation-1",
        "artifact_root": "candidates/candidate-1",
    }


@pytest.mark.parametrize("artifact_root", ["C:\\outside", "/outside", "../outside"])
def test_candidate_artifact_root_is_relative_and_cannot_traverse(artifact_root) -> None:
    with pytest.raises(ValueError, match="artifact root"):
        CandidateTrainingRequest(
            request_id="candidate-1",
            model_family="approved-family",
            strategy="ml_model",
            feature_set_id="features-1",
            data_identity="massive-snapshot-1",
            evaluation_contract="evaluation-1",
            artifact_root=artifact_root,
        )


def test_work_items_reject_roles_outside_v20() -> None:
    with pytest.raises(ValueError, match="approved V20 role"):
        WorkItem(
            work_id="work-1",
            kind="normal",
            agent_id="outside-agent",
            objective="Do unrelated work.",
        )


def test_candidate_work_id_must_match_its_approved_request() -> None:
    request = CandidateTrainingRequest(
        request_id="candidate-1",
        model_family="approved-family",
        strategy="ml_model",
        feature_set_id="features-1",
        data_identity="massive-snapshot-1",
        evaluation_contract="evaluation-1",
        artifact_root="candidates/candidate-1",
    )
    with pytest.raises(ValueError, match="candidate request ID"):
        WorkItem(
            work_id="candidate-2",
            kind="candidate",
            agent_id="v20-model-researcher",
            objective="Evaluate candidate.",
            training_request=request,
        )


@pytest.mark.parametrize(
    "artifact_root",
    ["C:outside", "\\outside", "outside/candidate-1", "vesper/data/model_research"],
)
def test_candidate_artifact_root_stays_below_candidate_root(artifact_root) -> None:
    with pytest.raises(ValueError, match="artifact root"):
        CandidateTrainingRequest(
            request_id="candidate-1",
            model_family="approved-family",
            strategy="ml_model",
            feature_set_id="features-1",
            data_identity="massive-snapshot-1",
            evaluation_contract="evaluation-1",
            artifact_root=artifact_root,
        )

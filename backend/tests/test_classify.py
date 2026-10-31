"""Classifier endpoint tests — honest fallback (acceptance test 7).

The backend test environment has no PyTorch and no trained weights, so the
endpoint must return the documented `model_not_configured` status. The
classifier-status branches are additionally unit-tested without torch.
"""

import pytest

from tests.conftest import create_donation, make_jpeg_bytes


def test_classify_without_weights_returns_model_not_configured(client, donor_token):
    response = client.post(
        "/api/classify",
        files=[("image", ("primary.jpg", make_jpeg_bytes(), "image/jpeg"))],
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "model_not_configured"}


def test_classify_requires_donor_role(client, org_token, admin_token):
    for token in (org_token, admin_token):
        response = client.post(
            "/api/classify",
            files=[("image", ("p.jpg", make_jpeg_bytes(), "image/jpeg"))],
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


def test_classify_requires_authentication(client):
    response = client.post(
        "/api/classify",
        files=[("image", ("p.jpg", make_jpeg_bytes(), "image/jpeg"))],
    )
    assert response.status_code == 401


def test_classify_rejects_invalid_image_bytes(client, donor_token):
    response = client.post(
        "/api/classify",
        files=[("image", ("fake.jpg", b"not an image at all", "image/jpeg"))],
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.status_code == 422


def test_manual_category_selection_works_without_model(client, donor_token):
    """The full donation flow succeeds when the model is not configured —
    the donor simply confirms a category manually (acceptance test 7)."""
    response = client.post(
        "/api/classify",
        files=[("image", ("primary.jpg", make_jpeg_bytes(), "image/jpeg"))],
        headers={"Authorization": f"Bearer {donor_token}"},
    )
    assert response.json()["status"] == "model_not_configured"

    created = create_donation(client, donor_token, category_code="grains_rice")
    assert created.status_code == 201
    assert created.json()["category_code"] == "grains_rice"
    assert created.json()["ai_predicted_category"] is None


# --------------------------------------------------------- unit-level checks


def test_classifier_status_reports_missing_weights(tmp_path):
    from app.ml.classifier import classifier_status

    status = classifier_status(weights_file=tmp_path / "missing.pt")
    assert status.configured is False
    assert "not found" in (status.reason or "")


def test_classifier_status_reports_missing_torch(tmp_path):
    """Weights present but no torch in the environment -> honestly not runnable."""
    pytest.importorskip("PIL")  # environment sanity only
    from app.ml import classifier as classifier_module
    from app.ml.classifier import classifier_status

    dummy_weights = tmp_path / "image_classifier_v1.pt"
    dummy_weights.write_bytes(b"\x00" * 32)  # not real weights — just a file

    original = classifier_module._torch_available
    classifier_module._torch_available = lambda: False
    try:
        status = classifier_status(weights_file=dummy_weights)
    finally:
        classifier_module._torch_available = original
    assert status.configured is False
    assert "PyTorch" in (status.reason or "")


def test_wrapper_class_list_matches_canonical_ml_module():
    """Guard against drift between the backend constants and ml/src."""
    from app.core.constants import CLASSIFIER_CLASSES
    from app.ml.classifier import _canonical_classes

    assert _canonical_classes() == tuple(code for code, _ in CLASSIFIER_CLASSES)

"""Tests adicionales de cobertura para core.prometeo_approval (DT-12).

Cubren las líneas/ramas que tests/unit/test_prometeo_approval.py no ejercita:
el except del while en request_approval (JSON corrupto en completed), la rama
bool(response) en validation/confirmation (respuesta NO string), el tipo de
aprobación desconocido (return response), el else/sleep del polling, y las
ramas except de get_pending_approvals / complete_approval / cancel_approval.

Usa fixtures propios (cov_*) para no colisionar con los del test original.
"""


import pytest

import core.prometeo_approval as pa

FIXED_UUID = "12345678"
FIXED_ID = FIXED_UUID[:8]  # "12345678"


@pytest.fixture()
def cov_uuid(monkeypatch):
    """Determinista: uuid4 fijo + sleep noop para el polling."""
    monkeypatch.setattr(pa.uuid, "uuid4", lambda: FIXED_UUID)
    monkeypatch.setattr(pa.time, "sleep", lambda _: None)
    return FIXED_ID


@pytest.fixture()
def cov_dirs(monkeypatch, tmp_path):
    """Apunta los directorios module-globales a un tmp_path por test."""
    pending = tmp_path / "pending"
    completed = tmp_path / "completed"
    pending.mkdir(parents=True, exist_ok=True)
    completed.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pa, "PENDING_DIR", pending)
    monkeypatch.setattr(pa, "COMPLETED_DIR", completed)
    monkeypatch.setattr(pa, "APPROVAL_DIR", tmp_path)
    return tmp_path


def _save_completed(cov_dirs, approval_type, response, request_id, status="completed"):
    req = pa.ApprovalRequest(
        approval_type=approval_type, prompt="p", request_id=request_id
    )
    req.status = status
    req.response = response
    req.save_completed()
    return req


# ---------------------------------------------------------------------------
# request_approval: ramas del polling (líneas 181-190)
# ---------------------------------------------------------------------------


def test_request_approval_poll_sleeps_then_expires(cov_dirs, cov_uuid, monkeypatch):
    """Sin respuesta: el while hace sleep y luego expira -> TimeoutError (190, 185-188)."""
    calls = {"n": 0}

    def fake_is_expired(self):
        calls["n"] += 1
        return calls["n"] >= 2  # 1ª llamada falsa (sleep), 2ª verdadera (expira)

    monkeypatch.setattr(pa.ApprovalRequest, "is_expired", fake_is_expired)

    with pytest.raises(TimeoutError):
        pa.request_approval("validation", "p", timeout_seconds=5)


def test_request_approval_corrupt_completed_ignored_then_expires(
    cov_dirs, cov_uuid, monkeypatch
):
    """Completed con JSON corrupto -> except del while (181-182) y luego expira."""
    (pa.COMPLETED_DIR / f"{FIXED_ID}.json").write_text("{json roto")

    def fake_is_expired(self):
        return True

    monkeypatch.setattr(pa.ApprovalRequest, "is_expired", fake_is_expired)

    with pytest.raises(TimeoutError):
        pa.request_approval("validation", "p", timeout_seconds=5)


# ---------------------------------------------------------------------------
# request_approval: procesamiento de respuesta (204, 214, 219)
# ---------------------------------------------------------------------------


def test_request_approval_sudo_password_invalid(cov_dirs, cov_uuid):
    """sudo_password con respuesta vacía -> ValueError (línea 204)."""
    _save_completed(cov_dirs, "sudo_password", "", FIXED_ID)
    with pytest.raises(ValueError):
        pa.request_approval("sudo_password", "p", timeout_seconds=5)


def test_request_approval_validation_nonstring_bool(cov_dirs, cov_uuid):
    """validation con respuesta NO string -> bool(response) (línea 214)."""
    _save_completed(cov_dirs, "confirmation", True, FIXED_ID)
    assert pa.request_approval("confirmation", "p", timeout_seconds=5) is True


def test_request_approval_unknown_type_returns_response(cov_dirs, cov_uuid):
    """Tipo no conocido -> return response (línea 219)."""
    _save_completed(cov_dirs, "input", "xyz", FIXED_ID)
    assert pa.request_approval("weird", "p", timeout_seconds=5) == "xyz"


def test_request_approval_input_none_returns_empty(cov_dirs, cov_uuid):
    """input con response None -> \"\" (rama None de la línea 217)."""
    _save_completed(cov_dirs, "input", None, FIXED_ID)
    assert pa.request_approval("input", "p", timeout_seconds=5) == ""


# ---------------------------------------------------------------------------
# get_pending_approvals / complete_approval / cancel_approval: ramas except
# ---------------------------------------------------------------------------


def test_get_pending_approvals_skips_corrupt_json(cov_dirs):
    """Un JSON corrupto en pending se ignora (líneas 234-235)."""
    (pa.PENDING_DIR / "bad.json").write_text("{json roto")
    assert pa.get_pending_approvals() == []


def test_complete_approval_raises_on_corrupt_json(cov_dirs):
    """complete_approval con pending corrupto -> False (líneas 262-264)."""
    (pa.PENDING_DIR / "c.json").write_text("{json roto")
    assert pa.complete_approval("c", "x") is False


def test_cancel_approval_raises_on_corrupt_json(cov_dirs):
    """cancel_approval con pending corrupto -> False (líneas 279-280)."""
    (pa.PENDING_DIR / "c.json").write_text("{json roto")
    assert pa.cancel_approval("c") is False


def test_cancel_approval_missing_pending(cov_dirs):
    """cancel_approval de un id inexistente -> False (línea 271)."""
    assert pa.cancel_approval("noexiste") is False

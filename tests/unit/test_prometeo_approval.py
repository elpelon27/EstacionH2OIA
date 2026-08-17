"""Tests unitarios de core.prometeo_approval (DT-12 coverage).

Las rutas de approval (~/data/prometeo_approvals) son module-globales; se
reemplazan con tmp_path via monkeypatch para aislar cada test.
"""

import json

import pytest

import core.prometeo_approval as pa

# Fijar uuid4 para que str(uuid4())[:8] sea determinista y coincida en
# request_approval (que genera su propio id interno).
FIXED_UUID = "12345678"
FIXED_ID = FIXED_UUID[:8]  # "12345678"


@pytest.fixture()
def fixed_uuid(monkeypatch):
    monkeypatch.setattr(pa.uuid, "uuid4", lambda: FIXED_UUID)
    monkeypatch.setattr(pa.time, "sleep", lambda _: None)
    return FIXED_ID


@pytest.fixture()
def approval_dirs(monkeypatch, tmp_path):
    """Apuntar los directorios del módulo a un tmp_path por test."""
    pending = tmp_path / "pending"
    completed = tmp_path / "completed"
    pending.mkdir(parents=True, exist_ok=True)
    completed.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pa, "PENDING_DIR", pending)
    monkeypatch.setattr(pa, "COMPLETED_DIR", completed)
    monkeypatch.setattr(pa, "APPROVAL_DIR", tmp_path)
    return tmp_path


def test_approval_request_to_dict_roundtrip():
    req = pa.ApprovalRequest(
        approval_type="validation",
        prompt="¿Confirmas?",
        context={"commit": "abc123"},
        timeout_seconds=60,
        request_id="t1",
    )
    data = req.to_dict()
    assert data["id"] == "t1"
    assert data["type"] == "validation"
    assert data["status"] == "pending"

    restored = pa.ApprovalRequest.from_dict(data)
    assert restored.id == "t1"
    assert restored.prompt == "¿Confirmas?"
    assert restored.status == "pending"


def test_save_pending_and_completed(approval_dirs, tmp_path):
    req = pa.ApprovalRequest(
        approval_type="input",
        prompt="Ingresa texto",
        request_id="abc",
    )
    req.save_pending()
    assert (tmp_path / "pending" / "abc.json").exists()

    req.status = "completed"
    req.response = "hola"
    req.save_completed()
    assert (tmp_path / "completed" / "abc.json").exists()
    # El pending debe limpiarse tras completar
    assert not (tmp_path / "pending" / "abc.json").exists()


def test_is_expired(approval_dirs):
    req = pa.ApprovalRequest(
        approval_type="validation",
        prompt="test",
        timeout_seconds=0,
        request_id="exp",
    )
    # created_at es hora registrada al construir; forzamos vieja
    req.created_at = "2000-01-01T00:00:00+00:00"
    assert req.is_expired()


def test_is_expired_false_when_not_pending(approval_dirs):
    req = pa.ApprovalRequest(
        approval_type="validation", prompt="test", timeout_seconds=0, request_id="x"
    )
    req.created_at = "2000-01-01T00:00:00+00:00"
    req.status = "completed"
    assert not req.is_expired()


def test_complete_approval(approval_dirs, tmp_path):
    req = pa.ApprovalRequest(approval_type="validation", prompt="ok", request_id="c1")
    req.save_pending()

    assert pa.complete_approval("c1", "sí") is True
    assert (tmp_path / "completed" / "c1.json").exists()

    # Ya procesada → False
    assert pa.complete_approval("c1", "sí") is False
    # No existe → False
    assert pa.complete_approval("noexiste", "sí") is False


def test_cancel_approval(approval_dirs, tmp_path):
    req = pa.ApprovalRequest(approval_type="input", prompt="p", request_id="cl")
    req.save_pending()

    assert pa.cancel_approval("cl") is True
    data = json.loads((tmp_path / "completed" / "cl.json").read_text())
    assert data["status"] == "cancelled"

    assert pa.cancel_approval("cl") is False


def test_get_pending_approvals_filters_expired(approval_dirs, tmp_path):
    fresh = pa.ApprovalRequest(approval_type="input", prompt="fresh", request_id="f1")
    fresh.save_pending()

    stale = pa.ApprovalRequest(approval_type="input", prompt="stale", request_id="s1")
    stale.created_at = "2000-01-01T00:00:00+00:00"
    stale.save_pending()

    pending = pa.get_pending_approvals()
    ids = [r.id for r in pending]
    assert "f1" in ids
    # "s1" expiró → se movió a completed, no aparece en pending
    assert "s1" not in ids


def test_request_approval_returns_for_sudo_password(approval_dirs, fixed_uuid):
    # request_approval usa internamente str(uuid4())[:8]; pre-escribimos completed
    req = pa.ApprovalRequest(
        approval_type="sudo_password", prompt="dame pass", request_id=fixed_uuid
    )
    req.status = "completed"
    req.response = "s3cret"
    req.save_completed()

    result = pa.request_approval("sudo_password", "dame pass", timeout_seconds=5)
    assert result == "s3cret"


@pytest.mark.parametrize(
    "atype,response,expected",
    [
        ("validation", "sí", True),
        ("validation", "SI", True),
        ("validation", "apruebo", True),
        ("validation", "no", False),
        ("confirmation", "yes", True),
        ("input", "libre", "libre"),
        ("sudo_password", "pass123", "pass123"),
    ],
)
def test_request_approval_response_variants(
    approval_dirs, fixed_uuid, atype, response, expected
):
    req = pa.ApprovalRequest(approval_type=atype, prompt="p", request_id=fixed_uuid)
    req.status = "completed"
    req.response = response
    req.save_completed()

    assert pa.request_approval(atype, "p", timeout_seconds=5) == expected


def test_request_approval_raises_when_not_completed(approval_dirs, fixed_uuid):
    req = pa.ApprovalRequest(
        approval_type="validation", prompt="p", request_id=fixed_uuid
    )
    req.status = "cancelled"
    req.save_completed()

    with pytest.raises(ValueError):
        pa.request_approval("validation", "p", timeout_seconds=5)


def test_request_approval_expires(approval_dirs, fixed_uuid):
    # Sin respuesta y timeout 0 → el while no entra y va al else → TimeoutError
    with pytest.raises(TimeoutError):
        pa.request_approval("validation", "p", timeout_seconds=0)


def test_get_pending_approvals_excludes_completed(approval_dirs, tmp_path):
    req = pa.ApprovalRequest(approval_type="input", prompt="creada", request_id="zz9")
    req.save_pending()
    # Marcar una en pending como ya expiró moviéndola a completed
    done = pa.ApprovalRequest(approval_type="input", prompt="done", request_id="aa1")
    done.status = "completed"
    done.save_completed()

    pending = pa.get_pending_approvals()
    ids = [r.id for r in pending]
    assert "zz9" in ids
    assert "aa1" not in ids

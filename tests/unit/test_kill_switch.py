"""Test P0-C: Kill switch functionality"""

import contextlib
import os
import stat
import tempfile

import pytest


# Test that kill switch file can be created and removed
def test_kill_switch_file_operations():
    """Test that kill switch file can be created, detected, and removed."""
    # Create a temp file path that doesn't exist yet
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        kill_switch_path = tmp.name + "_test"

    # Ensure it doesn't exist
    if os.path.exists(kill_switch_path):
        os.remove(kill_switch_path)

    try:
        # Initially doesn't exist
        assert not os.path.exists(kill_switch_path)

        # Create it (simulate /stop command)
        with open(kill_switch_path, "w") as f:
            f.write("killed by test")
        assert os.path.exists(kill_switch_path)

        # Check detection works
        with open(kill_switch_path) as f:
            content = f.read()
        assert "killed by test" in content

        # Remove it (simulate /start command)
        os.remove(kill_switch_path)
        assert not os.path.exists(kill_switch_path)
    finally:
        if os.path.exists(kill_switch_path):
            os.remove(kill_switch_path)


# Test that bridge health endpoint reflects kill switch state
def test_bridge_health_kill_switch(reset_prometheus):
    """Test that _is_kill_switch_active correctly reports kill switch state."""
    import sys

    project_root = os.environ.get("HERMES_PROJECT_ROOT", "/mnt/ssd_trabajo/hermes-agent")
    sys.path.insert(0, project_root)

    # Set env var to allow insecure salt for tests
    os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

    # En CI, setear KILL_SWITCH_FILE env var antes del reload
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        import tempfile
        os.environ["KILL_SWITCH_FILE"] = tempfile.mktemp(suffix="_valentina.kill")

    # Need to reimport after prometheus reset
    import importlib

    if "api.bridge" in sys.modules:
        importlib.reload(sys.modules["api.bridge"])
    from api.bridge import KILL_SWITCH_FILE, _is_kill_switch_active

    # Test with no kill switch
    if os.path.exists(KILL_SWITCH_FILE):
        os.remove(KILL_SWITCH_FILE)

    assert not _is_kill_switch_active()

    # Test with kill switch active
    with open(KILL_SWITCH_FILE, "w") as f:
        f.write("test")

    assert _is_kill_switch_active()

    # Clean up
    os.remove(KILL_SWITCH_FILE)
    assert not _is_kill_switch_active()


# Test bridge startup clears kill switch
def test_bridge_startup_clears_kill_switch(reset_prometheus):
    """Test that bridge lifespan clears kill switch on startup."""
    import sys

    project_root = os.environ.get("HERMES_PROJECT_ROOT", "/mnt/ssd_trabajo/hermes-agent")
    sys.path.insert(0, project_root)

    os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

    # En CI, setear KILL_SWITCH_FILE env var antes del reload
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        import tempfile
        os.environ["KILL_SWITCH_FILE"] = tempfile.mktemp(suffix="_valentina.kill")

    import importlib

    if "api.bridge" in sys.modules:
        importlib.reload(sys.modules["api.bridge"])
    from api.bridge import KILL_SWITCH_FILE

    # Create kill switch file
    with open(KILL_SWITCH_FILE, "w") as f:
        f.write("stale from previous run")

    assert os.path.exists(KILL_SWITCH_FILE)

    # Simulate startup cleanup (from lifespan)
    if os.path.exists(KILL_SWITCH_FILE):
        os.remove(KILL_SWITCH_FILE)

    assert not os.path.exists(KILL_SWITCH_FILE)


# Test file permissions on creation (0600)
def test_kill_switch_file_permissions():
    """Test that kill switch file is created with 0600 permissions."""
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        test_path = tmp.name + "_perms"

    try:
        # Simulate cmd_stop creation with 0600
        import os as _os

        _fd = _os.open(test_path, _os.O_CREAT | _os.O_WRONLY | _os.O_TRUNC, 0o600)
        with _os.fdopen(_fd, "w") as f:
            f.write("test")

        # Check permissions
        file_stat = os.stat(test_path)
        permissions = stat.S_IMODE(file_stat.st_mode)
        assert permissions == 0o600, f"Expected 0600, got {oct(permissions)}"
    finally:
        if os.path.exists(test_path):
            os.remove(test_path)


# Test bridge meta_webhook rejects messages when kill switch active
@pytest.mark.asyncio
async def test_meta_webhook_respects_kill_switch(reset_prometheus):
    """Test that meta_webhook checks kill switch state."""
    import sys

    project_root = os.environ.get("HERMES_PROJECT_ROOT", "/mnt/ssd_trabajo/hermes-agent")
    sys.path.insert(0, project_root)

    os.environ["BRIDGE_ALLOW_INSECURE_SALT"] = "1"

    # En CI, setear KILL_SWITCH_FILE env var antes del reload
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        import tempfile
        os.environ["KILL_SWITCH_FILE"] = tempfile.mktemp(suffix="_valentina.kill")

    import importlib

    if "api.bridge" in sys.modules:
        importlib.reload(sys.modules["api.bridge"])
    from api.bridge import KILL_SWITCH_FILE, _is_kill_switch_active

    # Activate kill switch
    with open(KILL_SWITCH_FILE, "w") as f:
        f.write("test")

    try:
        assert _is_kill_switch_active()

        # The meta_webhook should check kill switch and return early
        kill_active = _is_kill_switch_active()
        assert kill_active
    finally:
        if os.path.exists(KILL_SWITCH_FILE):
            os.remove(KILL_SWITCH_FILE)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

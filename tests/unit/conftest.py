"""Unit test fixtures - overrides test file fixtures to prevent conflicts."""
import pytest


# =============================================================================
# OVERRIDE TEST_BOTTLE_TRACKER.PY FIXTURES
# =============================================================================

# The test_bottle_tracker.py has its own fixtures that conflict with root conftest.
# We override them here (tests/unit/conftest.py takes precedence over test file fixtures).

@pytest.fixture(autouse=True)
def reset_bottle_tracker_singleton():
    """Override test file's fixture - root conftest handles singleton reset."""
    pass


@pytest.fixture(autouse=True)
def test_db():
    """Override test file's fixture - root conftest provides test_db via _test_db_path."""
    pass


@pytest.fixture
def tracker():
    """Override test file's fixture - root conftest handles DB patching.
    
    This replaces the test file's tracker fixture which does its own DISPATCH_DB patching
    and restores the production DB at teardown (breaking isolation).
    """
    # Our root conftest's patch_dispatch_db fixture already patched DISPATCH_DB
    # to a temp DB. Just get the tracker instance.
    import skills.dispatch.bottle_tracker as bt_module
    from skills.dispatch.bottle_tracker import get_bottle_tracker
    tracker = get_bottle_tracker()
    yield tracker
    # Don't restore original DB - root conftest handles cleanup


# =============================================================================
# OVERRIDE TEST_DISPATCH_TELEGRAM_BOT.PY FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def patch_bot_db():
    """Override test file's fixture - root conftest handles DB patching."""
    pass


# =============================================================================
# OVERRIDE TEST_GPS_TRACKER.PY FIXTURES (if any)
# =============================================================================

# Add any other test file fixture overrides here as needed
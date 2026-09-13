import pytest

from app.core.config import get_settings


@pytest.fixture
def fresh_settings():
    """Reset the cached settings so env changes take effect for one test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

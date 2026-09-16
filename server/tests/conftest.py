import asyncio
import sys

import pytest

from app.core.config import get_settings

# psycopg's async adapter is incompatible with Windows' default
# ProactorEventLoop — force the selector loop for the test suite.
# (The server itself runs on Linux in Docker, where this is a no-op.)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture
def fresh_settings():
    """Reset the cached settings so env changes take effect for one test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def api_client():
    """Async HTTP client bound straight to the app (no server, no DB).

    Uses ASGITransport so app and test share the event loop — required
    when async sessions are involved.
    """
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

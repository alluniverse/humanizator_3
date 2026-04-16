"""Unit test conftest: override session-scoped DB fixture with no-op.

Unit tests run without a database or Redis — they test pure Python logic.
"""

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """No-op override: unit tests don't need a database."""
    yield

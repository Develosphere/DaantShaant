import inspect
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test to run with asyncio")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_collection_modifyitems(items):
    for item in items:
        if isinstance(item, pytest.Function) and inspect.iscoroutinefunction(item.obj):
            item.add_marker(pytest.mark.anyio)

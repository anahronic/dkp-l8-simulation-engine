import pytest

from tests.simulation.helpers import adapter_for


@pytest.fixture
def adapter():
    return adapter_for()

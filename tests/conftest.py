import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.rules import RuleStore
from server.service import RuleService


@pytest.fixture(scope="session")
def store():
    return RuleStore()


@pytest.fixture
def service(store):
    service = RuleService(store, port=0)
    yield service
    service.close()

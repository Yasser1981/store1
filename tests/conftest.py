import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from workorders.db import open_database  # noqa: E402
from workorders.models import WorkOrder  # noqa: E402
from workorders.repository import Repository  # noqa: E402

TODAY = date(2026, 11, 17)


@pytest.fixture
def repo(tmp_path):
    conn = open_database(tmp_path / "data" / "workorders.db")
    r = Repository(conn)
    yield r
    conn.close()


def make_order(**kw) -> WorkOrder:
    base = dict(order_no=1, order_year=2026, order_type="investment", project_name="مشروع تجريبي",
                work_type="civil")
    base.update(kw)
    return WorkOrder(**base)


@pytest.fixture
def factory():
    return make_order

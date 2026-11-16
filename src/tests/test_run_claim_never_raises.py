"""docs/contracts.md: `run_claim` must not raise. A store it cannot use ends as `failed`.

The only exception a shape lets through is InjectedCrash (the crash lab needs to see it).
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from lab8.db import init_store
from lab8.durability import InjectedCrash
from lab8.metrics import check_trace
from lab8.shapes import SHAPES
from tests.conftest import CLAIMS, WORLD

GROUP_SHAPES = ["workflow", "single", "orchestrator"]


def _assert_failed_cleanly(result, started_at):
    assert (result.status, result.proposal_amount) == ("failed", 0)
    assert (result.refund_effects, result.committed_audit_count) == ([], 0)
    assert result.error_reason and result.error_reason.startswith("internal:")
    assert check_trace(result.as_dict(), started_at=started_at) == (True, "ok")


@pytest.mark.parametrize("shape", GROUP_SHAPES)
def test_store_that_cannot_be_opened_is_a_failed_result(tmp_path, shape):
    started_at = time.time()
    result = SHAPES[shape]("C-001", seed=11, store_path=str(tmp_path / "no-such-folder" / "x.sqlite"))
    _assert_failed_cleanly(result, started_at)


@pytest.mark.parametrize("shape", GROUP_SHAPES)
def test_store_without_the_lab_schema_is_a_failed_result(tmp_path, shape):
    store = tmp_path / "empty.sqlite"
    sqlite3.connect(str(store)).close()  # a valid SQLite file with no tables
    started_at = time.time()
    result = SHAPES[shape]("C-001", seed=11, store_path=str(store))
    _assert_failed_cleanly(result, started_at)


@pytest.mark.parametrize("shape", GROUP_SHAPES)
def test_injected_crash_is_still_allowed_through(tmp_path, shape):
    store = tmp_path / "crash.sqlite"
    init_store(store, WORLD, CLAIMS).close()
    with pytest.raises(InjectedCrash):
        SHAPES[shape]("C-012", seed=11, store_path=str(store), crash_at="before_effect")

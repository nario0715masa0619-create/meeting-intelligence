"""Pytest safety gate for tests that call paid external APIs."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    mark_expression = config.getoption("markexpr")
    if "live" in mark_expression.split():
        return

    skip_live = pytest.mark.skip(reason="live tests require explicit selection with -m live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)

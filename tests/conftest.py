"""
Pytest configuration and shared fixtures.
"""
from __future__ import annotations

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that make real network requests.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring network"
    )

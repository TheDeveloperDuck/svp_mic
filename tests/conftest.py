import datetime
import logging
import os
import pathlib
import sys

import pytest

LOG_DIR = pathlib.Path(__file__).parent.parent / "test_logs"


def pytest_configure(config):
    LOG_DIR.mkdir(exist_ok=True)

    args = config.invocation_params.args
    suite_type = "all"
    suite_subtype = "all"

    for arg in args:
        if "functional/e2e" in arg:
            suite_type, suite_subtype = "functional", "e2e"
        elif "functional/integration" in arg:
            suite_type, suite_subtype = "functional", "integration"
        elif "functional/regression" in arg:
            suite_type, suite_subtype = "functional", "regression"
        elif "functional/unit" in arg:
            suite_type, suite_subtype = "functional", "unit"
        elif "functional" in arg:
            suite_type, suite_subtype = "functional", "all"
        elif "stress/concurrent" in arg:
            suite_type, suite_subtype = "stress", "concurrent"
        elif "stress/resilience" in arg:
            suite_type, suite_subtype = "stress", "resilience"
        elif "stress" in arg:
            suite_type, suite_subtype = "stress", "all"

    now = datetime.datetime.now().strftime("%H%M_%Y%m%d")
    log_filename = f"{suite_type}_{suite_subtype}_{now}.log"
    log_path = LOG_DIR / log_filename

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.DEBUG)

    config._log_file_path = log_path


def pytest_sessionfinish(session, exitstatus):
    log_path = getattr(session.config, "_log_file_path", None)
    if log_path:
        print(f"\n[log] test output written to {log_path}")

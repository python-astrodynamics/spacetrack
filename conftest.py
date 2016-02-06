# coding: utf-8
from __future__ import absolute_import, division, print_function

import sys

import pytest


class DummyCollector(pytest.collect.File):
    def collect(self):
        return []


def pytest_pycollect_makemodule(path, parent):
    # skip asyncio tests unless on Python 3.5+, because async/await
    # is a SyntaxError.
    if 'aio' in path.basename and sys.version_info < (3, 5):
        return DummyCollector(path, parent=parent)

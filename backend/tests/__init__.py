# SPDX-License-Identifier: AGPL-3.0-only
# (c) 2026 Vahini Technologies.
"""Backend tests, run in CI by `python -m unittest discover -s backend/tests
-t .` (#228). A package so discovery imports each file as
backend.tests.<name>, the name the files import each other by."""

import unittest


def function_tests(namespace, name="FunctionTests"):
    """A TestCase that runs each module-level test_* function in namespace.

    Some files are written as plain functions with bare asserts. unittest
    discovery collects only TestCase classes, so without this those files
    ran no test at all. Each file ends with
    `FunctionTests = function_tests(globals())`.
    """
    methods = {
        key: staticmethod(value)
        for key, value in namespace.items()
        if key.startswith("test_") and callable(value)
    }
    return type(name, (unittest.TestCase,), methods)

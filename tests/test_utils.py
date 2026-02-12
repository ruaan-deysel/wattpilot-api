"""Tests for shared JSON utilities."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from wattpilot_api.utils import JSONNamespaceEncoder, value_to_json


class TestJSONNamespaceEncoder:
    def test_namespace_encoding(self) -> None:
        ns = SimpleNamespace(a=1, b="two")
        result = json.dumps(ns, cls=JSONNamespaceEncoder)
        assert '"a": 1' in result
        assert '"b": "two"' in result

    def test_fallback(self) -> None:
        with pytest.raises(TypeError):
            json.dumps(object(), cls=JSONNamespaceEncoder)


class TestValueToJson:
    def test_simple_namespace(self) -> None:
        result = value_to_json(SimpleNamespace(x=42))
        assert '"x": 42' in result

    def test_primitive(self) -> None:
        assert value_to_json(42) == "42"
        assert value_to_json("hello") == '"hello"'

    def test_none(self) -> None:
        assert value_to_json(None) == "null"

    def test_list(self) -> None:
        result = value_to_json([1, 2, 3])
        assert result == "[1, 2, 3]"

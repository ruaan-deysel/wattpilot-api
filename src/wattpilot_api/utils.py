"""Shared utilities for JSON encoding."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any


class JSONNamespaceEncoder(json.JSONEncoder):
    """JSON encoder that handles :class:`~types.SimpleNamespace` objects."""

    def default(self, o: object) -> Any:
        if isinstance(o, SimpleNamespace):
            return o.__dict__
        return super().default(o)


def value_to_json(value: Any) -> str:
    """Serialize *value* to a JSON string, supporting :class:`~types.SimpleNamespace`."""
    return json.dumps(value, cls=JSONNamespaceEncoder)

"""Loader and accessor for the Wattpilot YAML API definition."""

from __future__ import annotations

import importlib.resources as import_resources
import logging
import pkgutil
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import yaml

from wattpilot_api.utils import value_to_json

_LOGGER = logging.getLogger(__name__)


@dataclass
class ApiDefinition:
    """Parsed representation of ``wattpilot.yaml``."""

    config: dict[str, Any] = field(default_factory=dict)
    messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    properties: dict[str, dict[str, Any]] = field(default_factory=dict)
    split_properties: list[str] = field(default_factory=list)


def validate_api_definition(config: Any) -> dict[str, Any]:
    """Validate top-level structure of the raw YAML config."""
    if not isinstance(config, dict):
        msg = "wattpilot.yaml must define a mapping at top level"
        raise ValueError(msg)
    if "messages" not in config or not isinstance(config["messages"], list):
        msg = "wattpilot.yaml must contain a list 'messages'"
        raise ValueError(msg)
    if "properties" not in config or not isinstance(config["properties"], list):
        msg = "wattpilot.yaml must contain a list 'properties'"
        raise ValueError(msg)

    for entry in config["messages"]:
        if not isinstance(entry, dict) or "key" not in entry:
            msg = "Each message entry must be a mapping with a 'key'"
            raise ValueError(msg)

    for prop in config["properties"]:
        if not isinstance(prop, dict) or "key" not in prop:
            msg = "Each property entry must be a mapping with a 'key'"
            raise ValueError(msg)
        child_props = prop.get("childProps", [])
        if not isinstance(child_props, list):
            msg = "'childProps' must be a list when present"
            raise ValueError(msg)

    return config


def _add_unique(d: dict[str, Any], k: str, v: Any) -> dict[str, Any]:
    if k in d:
        _LOGGER.warning("About to add duplicate key %s to dictionary - skipping!", k)
    else:
        d[k] = v
    return d


def load_api_definition(*, split_properties: bool = True) -> ApiDefinition:
    """Load and parse ``wattpilot.yaml`` from package resources.

    When *split_properties* is ``True`` (the default), array/object properties
    with ``childProps`` entries are expanded into individual virtual properties.
    """
    try:
        raw_text = (
            import_resources.files("wattpilot_api.resources")
            .joinpath("wattpilot.yaml")
            .read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        data = pkgutil.get_data("wattpilot_api", "resources/wattpilot.yaml")
        if data is None:
            msg = "Could not load wattpilot.yaml"
            raise FileNotFoundError(msg) from None
        try:
            raw_text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            msg = f"Failed to decode wattpilot.yaml as UTF-8: {exc.reason}"
            raise ValueError(msg) from exc

    api_def = ApiDefinition()

    try:
        api_def.config = validate_api_definition(yaml.safe_load(raw_text or "{}"))
        api_def.messages = {m["key"]: m for m in api_def.config["messages"]}

        for p in api_def.config["properties"]:
            api_def.properties = _add_unique(api_def.properties, p["key"], p)
            if "childProps" in p and split_properties:
                for cp in p["childProps"]:
                    cp = (
                        {
                            "description": (
                                f"This is a child property of '{p['key']}'. "
                                "See its description for more information."
                            ),
                            "category": p.get("category", ""),
                            "jsonType": p.get("itemType", ""),
                        }
                        | cp
                        | {
                            "parentProperty": p["key"],
                            "rw": "R",
                        }
                    )
                    api_def.properties = _add_unique(api_def.properties, cp["key"], cp)
                    api_def.split_properties.append(cp["key"])

    except yaml.YAMLError as exc:
        _LOGGER.fatal("Failed to parse wattpilot.yaml: %s", exc)
        raise

    return api_def


def get_child_property_value(
    api_def: ApiDefinition,
    all_props: dict[str, Any],
    child_key: str,
) -> Any:
    """Resolve the value of a split child property from its parent's value."""
    cpd = api_def.properties[child_key]
    if "parentProperty" not in cpd:
        _LOGGER.warning("Child property '%s' is not linked to a parent property", cpd["key"])
        return None

    ppd = api_def.properties[cpd["parentProperty"]]
    parent_value = all_props.get(ppd["key"])

    if ppd["jsonType"] == "array":
        if parent_value is None:
            return None
        idx = int(cpd["valueRef"])
        if idx < len(parent_value):
            return parent_value[idx]
        return None

    if ppd["jsonType"] == "object":
        if parent_value is None:
            return None
        ref = cpd["valueRef"]
        if isinstance(parent_value, SimpleNamespace) and ref in parent_value.__dict__:
            return parent_value.__dict__[ref]
        if isinstance(parent_value, dict) and ref in parent_value:
            return parent_value[ref]
        _LOGGER.warning(
            "Unable to map child property %s: type=%s, value=%s",
            cpd["key"],
            type(parent_value),
            value_to_json(parent_value),
        )
        return None

    _LOGGER.warning("Property %s cannot be split!", ppd["key"])
    return None


def get_all_properties(
    api_def: ApiDefinition,
    all_props: dict[str, Any],
    *,
    available_only: bool = True,
) -> dict[str, Any]:
    """Return a dict of all property values, optionally including child properties."""
    if available_only:
        props = dict(all_props)
        for cp_key in api_def.split_properties:
            props[cp_key] = get_child_property_value(api_def, all_props, cp_key)
    else:
        props = {k: all_props.get(k) for k in api_def.properties}
    return props

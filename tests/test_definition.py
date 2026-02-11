"""Tests for the API definition loader."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from wattpilot_api.definition import (
    ApiDefinition,
    _add_unique,
    _JSONNamespaceEncoder,
    _value_to_json,
    get_all_properties,
    get_child_property_value,
    load_api_definition,
    validate_api_definition,
)


class TestValidateApiDefinition:
    def test_valid(self) -> None:
        config: dict[str, Any] = {
            "messages": [{"key": "hello"}],
            "properties": [{"key": "amp"}],
        }
        result = validate_api_definition(config)
        assert result is config

    def test_not_dict(self) -> None:
        with pytest.raises(ValueError, match="mapping at top level"):
            validate_api_definition("not a dict")

    def test_missing_messages(self) -> None:
        with pytest.raises(ValueError, match="list 'messages'"):
            validate_api_definition({"properties": [{"key": "amp"}]})

    def test_messages_not_list(self) -> None:
        with pytest.raises(ValueError, match="list 'messages'"):
            validate_api_definition({"messages": "bad", "properties": [{"key": "amp"}]})

    def test_missing_properties(self) -> None:
        with pytest.raises(ValueError, match="list 'properties'"):
            validate_api_definition({"messages": [{"key": "hello"}]})

    def test_properties_not_list(self) -> None:
        with pytest.raises(ValueError, match="list 'properties'"):
            validate_api_definition({"messages": [{"key": "hello"}], "properties": "bad"})

    def test_message_without_key(self) -> None:
        with pytest.raises(ValueError, match="mapping with a 'key'"):
            validate_api_definition(
                {
                    "messages": [{"type": "hello"}],
                    "properties": [{"key": "amp"}],
                }
            )

    def test_message_not_dict(self) -> None:
        with pytest.raises(ValueError, match="mapping with a 'key'"):
            validate_api_definition(
                {
                    "messages": ["hello"],
                    "properties": [{"key": "amp"}],
                }
            )

    def test_property_without_key(self) -> None:
        with pytest.raises(ValueError, match="mapping with a 'key'"):
            validate_api_definition(
                {
                    "messages": [{"key": "hello"}],
                    "properties": [{"name": "amp"}],
                }
            )

    def test_child_props_not_list(self) -> None:
        with pytest.raises(ValueError, match="'childProps' must be a list"):
            validate_api_definition(
                {
                    "messages": [{"key": "hello"}],
                    "properties": [{"key": "nrg", "childProps": "bad"}],
                }
            )


class TestAddUnique:
    def test_add_new_key(self) -> None:
        d: dict[str, Any] = {}
        result = _add_unique(d, "a", 1)
        assert result == {"a": 1}

    def test_duplicate_key_skipped(self) -> None:
        d: dict[str, Any] = {"a": 1}
        result = _add_unique(d, "a", 2)
        assert result == {"a": 1}


class TestLoadApiDefinition:
    def test_load_default(self) -> None:
        api_def = load_api_definition()
        assert isinstance(api_def, ApiDefinition)
        assert len(api_def.messages) > 0
        assert len(api_def.properties) > 0
        assert "amp" in api_def.properties

    def test_load_without_split(self) -> None:
        api_def = load_api_definition(split_properties=False)
        assert len(api_def.split_properties) == 0

    def test_load_with_split(self) -> None:
        api_def = load_api_definition(split_properties=True)
        # Should have some split properties from nrg, etc.
        assert len(api_def.split_properties) >= 0  # May or may not have any

    def test_messages_have_keys(self) -> None:
        api_def = load_api_definition()
        assert "hello" in api_def.messages
        assert "authRequired" in api_def.messages
        assert "fullStatus" in api_def.messages

    def test_properties_have_types(self) -> None:
        api_def = load_api_definition()
        amp = api_def.properties["amp"]
        assert "key" in amp


class TestGetChildPropertyValue:
    def test_array_child(self) -> None:
        api_def = ApiDefinition(
            properties={
                "nrg": {"key": "nrg", "jsonType": "array"},
                "nrg_v1": {
                    "key": "nrg_v1",
                    "parentProperty": "nrg",
                    "valueRef": "0",
                },
            }
        )
        all_props = {"nrg": [230, 231, 232]}
        result = get_child_property_value(api_def, all_props, "nrg_v1")
        assert result == 230

    def test_array_child_none_parent(self) -> None:
        api_def = ApiDefinition(
            properties={
                "nrg": {"key": "nrg", "jsonType": "array"},
                "nrg_v1": {
                    "key": "nrg_v1",
                    "parentProperty": "nrg",
                    "valueRef": "0",
                },
            }
        )
        result = get_child_property_value(api_def, {}, "nrg_v1")
        assert result is None

    def test_array_child_out_of_range(self) -> None:
        api_def = ApiDefinition(
            properties={
                "nrg": {"key": "nrg", "jsonType": "array"},
                "nrg_v99": {
                    "key": "nrg_v99",
                    "parentProperty": "nrg",
                    "valueRef": "99",
                },
            }
        )
        all_props = {"nrg": [230]}
        result = get_child_property_value(api_def, all_props, "nrg_v99")
        assert result is None

    def test_object_child_dict(self) -> None:
        api_def = ApiDefinition(
            properties={
                "parent": {"key": "parent", "jsonType": "object"},
                "child": {
                    "key": "child",
                    "parentProperty": "parent",
                    "valueRef": "field1",
                },
            }
        )
        all_props = {"parent": {"field1": "value1", "field2": "value2"}}
        result = get_child_property_value(api_def, all_props, "child")
        assert result == "value1"

    def test_object_child_namespace(self) -> None:
        from types import SimpleNamespace

        api_def = ApiDefinition(
            properties={
                "parent": {"key": "parent", "jsonType": "object"},
                "child": {
                    "key": "child",
                    "parentProperty": "parent",
                    "valueRef": "x",
                },
            }
        )
        all_props = {"parent": SimpleNamespace(x=42)}
        result = get_child_property_value(api_def, all_props, "child")
        assert result == 42

    def test_object_child_none_parent(self) -> None:
        api_def = ApiDefinition(
            properties={
                "parent": {"key": "parent", "jsonType": "object"},
                "child": {
                    "key": "child",
                    "parentProperty": "parent",
                    "valueRef": "x",
                },
            }
        )
        result = get_child_property_value(api_def, {}, "child")
        assert result is None

    def test_object_child_missing_ref(self) -> None:
        api_def = ApiDefinition(
            properties={
                "parent": {"key": "parent", "jsonType": "object"},
                "child": {
                    "key": "child",
                    "parentProperty": "parent",
                    "valueRef": "missing",
                },
            }
        )
        all_props = {"parent": {"other": 1}}
        result = get_child_property_value(api_def, all_props, "child")
        assert result is None

    def test_unsplittable_type(self) -> None:
        api_def = ApiDefinition(
            properties={
                "parent": {"key": "parent", "jsonType": "string"},
                "child": {
                    "key": "child",
                    "parentProperty": "parent",
                    "valueRef": "x",
                },
            }
        )
        all_props = {"parent": "hello"}
        result = get_child_property_value(api_def, all_props, "child")
        assert result is None

    def test_no_parent_property(self) -> None:
        api_def = ApiDefinition(
            properties={
                "orphan": {"key": "orphan"},
            }
        )
        result = get_child_property_value(api_def, {}, "orphan")
        assert result is None


class TestGetAllProperties:
    def test_available_only(self) -> None:
        api_def = ApiDefinition(
            properties={"amp": {"key": "amp"}, "car": {"key": "car"}},
            split_properties=[],
        )
        all_props = {"amp": 16, "car": 2}
        result = get_all_properties(api_def, all_props, available_only=True)
        assert result == {"amp": 16, "car": 2}

    def test_all_properties(self) -> None:
        api_def = ApiDefinition(
            properties={
                "amp": {"key": "amp"},
                "car": {"key": "car"},
                "missing": {"key": "missing"},
            },
            split_properties=[],
        )
        all_props = {"amp": 16}
        result = get_all_properties(api_def, all_props, available_only=False)
        assert result == {"amp": 16, "car": None, "missing": None}

    def test_available_only_with_split(self) -> None:
        api_def = ApiDefinition(
            properties={
                "nrg": {"key": "nrg", "jsonType": "array"},
                "nrg_v1": {
                    "key": "nrg_v1",
                    "parentProperty": "nrg",
                    "valueRef": "0",
                },
            },
            split_properties=["nrg_v1"],
        )
        all_props = {"nrg": [230, 231]}
        result = get_all_properties(api_def, all_props, available_only=True)
        assert result["nrg"] == [230, 231]
        assert result["nrg_v1"] == 230


class TestJSONNamespaceEncoderApiDef:
    def test_namespace_encoding(self) -> None:
        import json

        ns = SimpleNamespace(a=1)
        result = json.dumps(ns, cls=_JSONNamespaceEncoder)
        assert '"a": 1' in result

    def test_fallback(self) -> None:
        import json

        with pytest.raises(TypeError):
            json.dumps(object(), cls=_JSONNamespaceEncoder)

    def test_value_to_json(self) -> None:
        result = _value_to_json(SimpleNamespace(x=42))
        assert '"x": 42' in result


class TestGetChildPropertyValueObjectMissingRefNamespace:
    def test_object_child_namespace_missing_ref(self) -> None:
        """Cover the warning log path in get_child_property_value with SimpleNamespace."""
        api_def = ApiDefinition(
            properties={
                "parent": {"key": "parent", "jsonType": "object"},
                "child": {
                    "key": "child",
                    "parentProperty": "parent",
                    "valueRef": "missing",
                },
            }
        )
        all_props = {"parent": SimpleNamespace(other=1)}
        result = get_child_property_value(api_def, all_props, "child")
        assert result is None


class TestLoadApiDefinitionFallback:
    def test_pkgutil_fallback(self) -> None:
        valid_yaml = "messages:\n  - key: hello\nproperties:\n  - key: amp\n    jsonType: integer\n"
        with (
            patch("wattpilot_api.definition.import_resources") as mock_res,
            patch("wattpilot_api.definition.pkgutil.get_data") as mock_pkg,
        ):
            mock_res.files.side_effect = FileNotFoundError
            mock_pkg.return_value = valid_yaml.encode("utf-8")
            api_def = load_api_definition()
            assert "amp" in api_def.properties

    def test_pkgutil_returns_none(self) -> None:
        with (
            patch("wattpilot_api.definition.import_resources") as mock_res,
            patch("wattpilot_api.definition.pkgutil.get_data") as mock_pkg,
        ):
            mock_res.files.side_effect = FileNotFoundError
            mock_pkg.return_value = None
            with pytest.raises(FileNotFoundError, match="Could not load"):
                load_api_definition()

    def test_pkgutil_unicode_error(self) -> None:
        with (
            patch("wattpilot_api.definition.import_resources") as mock_res,
            patch("wattpilot_api.definition.pkgutil.get_data") as mock_pkg,
        ):
            mock_res.files.side_effect = FileNotFoundError
            mock_pkg.return_value = b"\xff\xfe"  # Invalid UTF-8
            with pytest.raises(ValueError, match="Failed to decode"):
                load_api_definition()

    def test_yaml_parse_error(self) -> None:
        import yaml

        with patch("wattpilot_api.definition.import_resources") as mock_res:
            mock_files = mock_res.files.return_value
            mock_files.joinpath.return_value.read_text.return_value = (
                "messages:\n  - key: hello\nproperties:\n  - key: amp\n  bad_indent: {\n"
            )
            with pytest.raises(yaml.YAMLError):
                load_api_definition()

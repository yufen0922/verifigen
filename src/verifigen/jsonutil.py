"""Small JSON-only helpers. Paths use RFC 6901 JSON pointers, never eval()."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from types import MappingProxyType
from typing import Any


def parts(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError("A field pointer must start with '/'")
    result = []
    for part in pointer[1:].split("/"):
        # Reject malformed escapes instead of silently interpreting a different path.
        import re

        if re.search(r"~(?![01])", part):
            raise ValueError("Invalid JSON pointer escape")
        result.append(part.replace("~1", "/").replace("~0", "~"))
    return result


def get_path(value: Any, pointer: str) -> Any:
    for part in parts(pointer):
        if isinstance(value, Mapping):
            value = value[part]
        elif isinstance(value, (list, tuple)) and part.isdecimal():
            value = value[int(part)]
        else:
            raise KeyError(pointer)
    return value


def replace_path(value: dict[str, Any], pointer: str, replacement: Any) -> None:
    """Replace an existing dict field; array mutation is deliberately unsupported."""
    keys = parts(pointer)
    node = value
    for key in keys[:-1]:
        node = node[key]
        if not isinstance(node, dict):
            raise KeyError(pointer)
    if keys[-1] not in node:
        raise KeyError(pointer)
    node[keys[-1]] = deepcopy(replacement)


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


def json_copy(value: Any) -> Any:
    return json.loads(json.dumps(thaw(value), ensure_ascii=False, allow_nan=False))


def digest(value: Any) -> str:
    encoded = json.dumps(thaw(value), sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()

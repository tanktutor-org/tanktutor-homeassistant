"""Every translation has exactly the keys of strings.json, so no label is ever missing."""

import json
from pathlib import Path

BASE = Path(__file__).parent.parent / "custom_components" / "tanktutor"


def keys(node, prefix=""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from keys(value, f"{prefix}{key}.")
    else:
        yield prefix.rstrip(".")


def load(path):
    return set(keys(json.loads(path.read_text(encoding="utf-8"))))


def test_english_matches_strings_json():
    assert load(BASE / "translations" / "en.json") == load(BASE / "strings.json")


def test_italian_has_the_same_keys():
    assert load(BASE / "translations" / "it.json") == load(BASE / "strings.json")


def test_manifest_version_is_set():
    manifest = json.loads((BASE / "manifest.json").read_text())
    assert manifest["domain"] == "tanktutor"
    assert manifest["version"]

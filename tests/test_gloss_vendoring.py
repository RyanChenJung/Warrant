"""The vendored Gloss detectors are the public release's, with only the import path changed (#28).

The reference is the release's own files, committed byte for byte under
`fixtures/gloss_release/` with a `.txt` suffix so that nothing imports or collects them. Their git
blob ids are the ones in the release commit's tree, so the reference can be checked against the
public repository without trusting this repo.
"""

import ast
import hashlib
import json
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
REFERENCE = Path(__file__).parent / "fixtures" / "gloss_release"
MANIFEST = json.loads((REFERENCE / "MANIFEST.json").read_text())
NOTE = REPO / "warrant" / "battery" / "gloss" / "VENDORING.md"

RELEASE_PACKAGE = "gloss"
VENDORED_PACKAGE = "warrant.battery.gloss"


def vendored_path(release_path):
    """Where a file of the release lives in this repo."""
    if release_path.startswith("tests/"):
        return REPO / "tests" / "battery" / release_path.removeprefix("tests/")
    if release_path == "LICENSE":
        return REPO / "warrant" / "battery" / "gloss" / "LICENSE"
    return REPO / "warrant" / "battery" / release_path


def reference_path(release_path):
    return REFERENCE / f"{release_path}.txt"


def blob_id(data):
    """The id git gives a file with these bytes."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def comparable(source, package):
    """The code of a module with docstrings dropped and the import path `package` read as the
    release's. Comments are not in the syntax tree, and nothing else is normalised."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = node.body[1:]
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == package or node.module.startswith(package + "."):
                node.module = RELEASE_PACKAGE + node.module.removeprefix(package)
    return ast.dump(tree, indent=1)


MODULES = sorted(path for path in MANIFEST["files"] if path.endswith(".py"))


def test_the_reference_files_are_the_blobs_of_the_release_commit():
    for path, blob in MANIFEST["files"].items():
        assert blob_id(reference_path(path).read_bytes()) == blob, path


@pytest.mark.parametrize("path", MODULES)
def test_a_vendored_module_has_the_code_of_the_release(path):
    vendored = comparable(vendored_path(path).read_text(encoding="utf-8"), VENDORED_PACKAGE)
    released = comparable(reference_path(path).read_text(encoding="utf-8"), RELEASE_PACKAGE)
    assert vendored == released


def test_the_reference_comparison_notices_a_changed_statement():
    source = reference_path("gloss/detect/link.py").read_text(encoding="utf-8")
    changed = source.replace("_MIN_MATCH_RATE = 50.0", "_MIN_MATCH_RATE = 40.0")
    assert changed != source
    assert comparable(changed, RELEASE_PACKAGE) != comparable(source, RELEASE_PACKAGE)


def test_the_vendored_copy_holds_the_release_files_and_no_other_module():
    package = REPO / "warrant" / "battery" / "gloss"
    found = {f"gloss/{p.relative_to(package).as_posix()}" for p in package.rglob("*.py")}
    found |= {f"tests/{p.name}" for p in (REPO / "tests" / "battery").glob("*.py")}
    assert found == set(MODULES)


def test_the_vendored_copy_carries_the_release_licence():
    assert vendored_path("LICENSE").read_bytes() == reference_path("LICENSE").read_bytes()
    assert "MIT License" in vendored_path("LICENSE").read_text()


def test_the_vendoring_note_cites_the_release_and_lists_every_file():
    note = NOTE.read_text()
    assert MANIFEST["repository"] in note
    assert MANIFEST["commit"] in note
    assert MANIFEST["private_original_commit"] in note
    for path, blob in MANIFEST["files"].items():
        assert f"`{path}`" in note, path
        assert blob in note, path


def imports_of_gloss(source):
    """The top-level modules named `gloss` that a module imports, by line."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""]
        else:
            continue
        lines += [node.lineno for name in names if name.split(".")[0] == RELEASE_PACKAGE]
    return lines


def test_nothing_in_the_repo_imports_the_gloss_package():
    offenders = []
    for root in (REPO / "warrant", REPO / "tests"):
        for path in sorted(root.rglob("*.py")):
            offenders += [
                f"{path.relative_to(REPO)}:{line}" for line in imports_of_gloss(path.read_text(encoding="utf-8"))
            ]
    assert offenders == []


def test_the_import_search_sees_both_import_forms():
    assert imports_of_gloss("import gloss.model\nfrom gloss.detect import quote\n") == [1, 2]
    assert imports_of_gloss("from warrant.battery.gloss.model import Tier\nimport glossary\n") == []


def test_gloss_is_not_a_dependency_and_duckdb_is_pinned():
    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    names = [d.split("[")[0].split("=")[0].split(">")[0].split("<")[0].strip() for d in project["dependencies"]]
    assert RELEASE_PACKAGE not in names
    assert f"duckdb=={MANIFEST['duckdb']}" in project["dependencies"]
    lock = tomllib.loads((REPO / "uv.lock").read_text())
    assert [p["version"] for p in lock["package"] if p["name"] == "duckdb"] == [MANIFEST["duckdb"]]
    assert RELEASE_PACKAGE not in [p["name"] for p in lock["package"]]

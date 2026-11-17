"""The PoCs built on the structured-data modules pass only option names gaik accepts.

DocumentsToStructuredData and AudioToStructuredData check every name in their
option dicts (``transcriber_ctor``, ``extractor_ctor``, ``parser_ctor`` and the
call-time dicts) against the component it goes to, and refuse a stage config
(``config``, ``api_config``, ``openai_config``). These tests read the names the
generated ``run_poc.py`` puts in those dicts and run gaik's own check on them.
"""

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import scaffold_poc

options = pytest.importorskip("gaik.software_modules._options")
extractor = pytest.importorskip("gaik.software_components.extractor")

EXAMPLES = Path(__file__).parent.parent / "examples"

_OPTION_DICTS = (
    "transcriber_ctor",
    "transcribe_options",
    "parser_ctor",
    "parse_options",
    "extractor_ctor",
    "extract_options",
)


def _returned_keys(tree: ast.Module, function: str) -> set[str]:
    """Keys of every dict literal a module-level function returns."""
    keys: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function:
            for ret in ast.walk(node):
                if isinstance(ret, ast.Return) and isinstance(ret.value, ast.Dict):
                    keys |= {k.value for k in ret.value.keys if isinstance(k, ast.Constant)}
    return keys


def _dict_keys(value: ast.expr, scope: ast.AST, helpers: ast.Module) -> set[str]:
    """Keys a dict expression can hold: literal keys, ``**helper()`` keys and later
    ``name[key] = ...`` assignments when the expression is a variable."""
    if isinstance(value, ast.Dict):
        keys = set()
        for key, item in zip(value.keys, value.values, strict=True):
            if isinstance(key, ast.Constant):
                keys.add(key.value)
            elif key is None and isinstance(item, ast.Call) and isinstance(item.func, ast.Name):
                found = _returned_keys(helpers, item.func.id)
                assert found, f"no dict returned by {item.func.id}()"
                keys |= found
            else:
                raise AssertionError(f"unreadable dict entry: {ast.unparse(item)}")
        return keys
    if isinstance(value, ast.Name):
        keys = set()
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == value.id:
                        keys |= _dict_keys(node.value, scope, helpers)
                    if (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == value.id
                        and isinstance(target.slice, ast.Constant)
                    ):
                        keys.add(target.slice.value)
        return keys
    raise AssertionError(f"unreadable option dict: {ast.unparse(value)}")


def _run_options(poc_dir: Path) -> dict[str, set[str]]:
    tree = ast.parse((poc_dir / "run_poc.py").read_text())
    helpers = ast.parse((poc_dir / "provider_config.py").read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pipeline"
    ]
    assert len(calls) == 1, "expected one pipeline.run(...) call"
    return {
        kw.arg: _dict_keys(kw.value, tree, helpers)
        for kw in calls[0].keywords
        if kw.arg in _OPTION_DICTS
    }


def _check(found: dict[str, set[str]], targets: dict[str, tuple]) -> None:
    for name, keys in found.items():
        target, set_by_module = targets[name]
        options.checked_options(
            dict.fromkeys(keys, "x"), target, what=name, set_by_module=set_by_module
        )


_EXTRACT_SET = options.EXTRACT_SET_BY_MODULE


def test_audio_poc_options_pass_the_module_check(tmp_path):
    transcriber = pytest.importorskip("gaik.software_components.transcriber")
    poc = scaffold_poc(
        Blueprint.from_file(EXAMPLES / "incident_reporting_blueprint.json"), tmp_path
    )["poc_dir"]
    found = _run_options(poc)
    assert {"transcriber_ctor", "extractor_ctor"} <= set(found)
    assert "local_api_base" in found["transcriber_ctor"]  # the helper's keys were read
    _check(
        found,
        {
            "transcriber_ctor": (transcriber.Transcriber, ()),
            "transcribe_options": (transcriber.Transcriber.transcribe, ("file_path",)),
            "extractor_ctor": (extractor.DataExtractor, ()),
            "extract_options": (extractor.DataExtractor.extract, _EXTRACT_SET),
        },
    )


def test_document_poc_options_pass_the_module_check(tmp_path):
    parsers = pytest.importorskip("gaik.software_components.parsers")
    poc = scaffold_poc(
        Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json"), tmp_path
    )["poc_dir"]
    found = _run_options(poc)
    assert {"parser_ctor", "extractor_ctor"} <= set(found)
    # The template sets no parser options today; any it gains must suit every parser.
    checked = 0
    for parser in ("VisionParser", "PyMuPDFParser", "DocxParser"):
        parser_class = getattr(parsers, parser, None)
        if parser_class is None:
            continue
        _check({"parser_ctor": found["parser_ctor"]}, {"parser_ctor": (parser_class, ())})
        checked += 1
    assert checked, "no parser class was available to check against"
    _check(
        {k: v for k, v in found.items() if k not in ("parser_ctor", "parse_options")},
        {
            "extractor_ctor": (extractor.DataExtractor, ()),
            "extract_options": (extractor.DataExtractor.extract, _EXTRACT_SET),
        },
    )
    assert not found.get("parse_options"), "parse_options depends on the parser chosen"


def test_the_check_reads_a_refused_key(tmp_path):
    """The reader above sees a stage config the way the module would refuse it."""
    tree = ast.parse("extractor_ctor = {}\nextractor_ctor['config'] = cfg\n")
    keys = _dict_keys(ast.Name(id="extractor_ctor"), tree, ast.parse(""))
    with pytest.raises(ValueError, match="not accepted here"):
        options.checked_options(
            dict.fromkeys(keys, "x"), extractor.DataExtractor, what="extractor_ctor"
        )

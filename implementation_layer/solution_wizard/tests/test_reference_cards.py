"""Tests for component reference cards (Part 1a)."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.registry import get_reference_cards, get_registry


def test_cards_load_and_validate():
    cards = get_reference_cards()
    assert len(cards.names()) >= 10


def test_every_registry_component_has_a_card():
    """Every component/module the wizard can select must have a reference card."""
    cards = set(get_reference_cards().names())
    reg_names = {e["name"] for e in get_registry().all()}
    missing = reg_names - cards
    assert not missing, f"Registry components without a reference card: {missing}"


def test_card_required_keys_present():
    cards = get_reference_cards()
    for name in cards.names():
        card = cards.get(name)
        for key in ("import", "construct", "call", "returns"):
            assert key in card, f"Card '{name}' missing key '{key}'"


def test_card_imports_are_gaik_imports():
    cards = get_reference_cards()
    for name in cards.names():
        imp = cards.get(name)["import"]
        assert "gaik" in imp, f"Card '{name}' import does not reference gaik: {imp}"


def test_card_import_matches_a_known_module_path():
    """Each card's import path should look like a real gaik module path."""
    cards = get_reference_cards()
    for name in cards.names():
        imp = cards.get(name)["import"]
        m = re.search(r"from\s+(gaik[\w\.]*)\s+import", imp)
        assert m, f"Card '{name}' has no parseable 'from gaik... import': {imp}"
        modpath = m.group(1)
        assert modpath.startswith("gaik.software_")


def test_get_unknown_card_returns_none():
    assert get_reference_cards().get("NoSuchComponent") is None


# ---------------------------------------------------------------------------
# Structured options (V3 component-option awareness)
# ---------------------------------------------------------------------------

def test_five_previously_missing_cards_present():
    cards = set(get_reference_cards().names())
    for name in ("LLMJudgePanel", "ExtractionEvaluator", "RAGEvaluator",
                 "BatchEvaluationRunner", "FormUnderstander"):
        assert name in cards, f"card '{name}' missing"


def test_options_arrays_are_well_formed():
    cards = get_reference_cards()
    for name in cards.names():
        card = cards.get(name)
        opts = card.get("options")
        if opts is None:
            continue
        assert isinstance(opts, list), f"{name}.options must be a list"
        for opt in opts:
            for key in ("name", "type", "effect", "selection_relevant", "infer_from"):
                assert key in opt, f"{name} option {opt.get('name')} missing '{key}'"
            assert isinstance(opt["selection_relevant"], bool)


def test_transcriber_declares_enhanced_transcript_with_finnish_rule():
    card = get_reference_cards().get("Transcriber")
    opts = {o["name"]: o for o in card.get("options", [])}
    assert "enhanced_transcript" in opts
    assert "fi" in opts["enhanced_transcript"]["infer_from"].lower() \
        or "finnish" in opts["enhanced_transcript"]["infer_from"].lower()
    # Transcriber subsumes the standalone enhancer for audio
    assert "TranscriptEnhancer" in (card.get("subsumes") or [])


def test_modules_declare_subsumed_components():
    cards = get_reference_cards()
    for mod in ("AudioToStructuredData", "DocumentsToStructuredData", "RAGWorkflow"):
        card = cards.get(mod)
        assert card.get("subsumes"), f"{mod} should declare subsumed components"


# ---------------------------------------------------------------------------
# Structural correctness via inspect (requires gaik installed; skips otherwise)
# ---------------------------------------------------------------------------

def _try_import(import_line: str):
    """Execute a card's import line and return the imported name, or None on failure."""
    import importlib
    m = re.search(r"from\s+(gaik[\w\.]*)\s+import\s+([\w,\s]+)", import_line)
    if not m:
        return None
    modpath = m.group(1)
    names = [n.strip() for n in m.group(2).split(",")]
    try:
        mod = importlib.import_module(modpath)
        for name in names:
            obj = getattr(mod, name, None)
            if obj is not None:
                return obj
    except Exception:
        return None
    return None


def _extract_construct_param(construct_line: str) -> str | None:
    """Extract the first named param from a construct snippet like ClassName(param=...)."""
    m = re.search(r"\((\w+)=", construct_line)
    return m.group(1) if m else None


def _extract_method_name(call_line: str) -> str | None:
    """Extract the method name from a call snippet like 'result = obj.method(...)'."""
    m = re.search(r"\.\s*(\w+)\s*\(", call_line)
    return m.group(1) if m else None


def _gaik_available() -> bool:
    try:
        import gaik  # noqa: F401
        return True
    except ImportError:
        return False


import pytest

@pytest.mark.skipif(not _gaik_available(), reason="gaik not installed; skipping structural card tests")
def test_card_constructor_param_exists_on_class():
    """Constructor params mentioned in 'construct' must exist on the class __init__.

    Multi-line construct snippets (with helper-function calls like get_openai_config)
    are skipped -- they involve multiple classes and cannot be simply checked by
    inspecting the first imported name.
    """
    import inspect
    cards = get_reference_cards()
    failures = []
    for name in cards.names():
        card = cards.get(name)
        if "\n" in card["construct"]:
            # Multi-step construct; skip structural check
            continue
        cls = _try_import(card["import"])
        if cls is None or not callable(cls):
            continue
        param_name = _extract_construct_param(card["construct"])
        if param_name is None:
            continue
        try:
            sig = inspect.signature(cls.__init__)
            if param_name not in sig.parameters:
                failures.append(
                    f"Card '{name}': construct mentions param '{param_name}' "
                    f"but {cls.__name__}.__init__ has: {list(sig.parameters)}"
                )
        except (ValueError, TypeError):
            pass
    assert not failures, "\n".join(failures)


@pytest.mark.skipif(not _gaik_available(), reason="gaik not installed; skipping structural card tests")
def test_card_call_method_exists_on_class():
    """Method names mentioned in 'call' must exist as actual methods on the class."""
    cards = get_reference_cards()
    failures = []
    for name in cards.names():
        card = cards.get(name)
        cls = _try_import(card["import"])
        if cls is None or not callable(cls):
            continue
        method_name = _extract_method_name(card["call"])
        if method_name is None or method_name in ("load_schema", "save", "save_schema"):
            continue  # skip result-object helper methods
        if not hasattr(cls, method_name):
            failures.append(
                f"Card '{name}': call mentions method '{method_name}' "
                f"but {cls.__name__} does not have it"
            )
    assert not failures, "\n".join(failures)

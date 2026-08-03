"""Registry freshness scan — compares the Solution Wizard's component registry
and reference cards against the *installed* gaik package, by introspection.

This is the deterministic backbone of the `gaik-sync` skill. It does NOT edit
anything; it produces a structured list of findings the skill reasons over.

Usage:
    python audit_registry.py            # human-readable report (exit 0)
    python audit_registry.py --json     # machine-readable findings for the skill
    python audit_registry.py --strict   # exit 1 if any findings (for CI)

Findings categories:
    parity     — registry entry that has no reference card
    removed    — card whose gaik import no longer resolves (class gone/renamed)
    api_drift  — constructor kwarg or call method that no longer exists on gaik
    options    — card option name that is not a real constructor parameter
    new        — public gaik class in a tracked module not known to the wizard
    version    — installed gaik version vs the wizard's last-validated pin

Each finding is {category, component, detail, file_hint}. The skill maps each to
a concrete edit (registry JSON, reference cards JSON, or SKILL.md guidance).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import inspect
import json
import os
import pkgutil
import re
import sys
from pathlib import Path


@contextlib.contextmanager
def _quiet():
    """Suppress noisy stdout/stderr that some gaik submodules print on import."""
    with open(os.devnull, "w") as devnull:
        with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
            yield


# ---------------------------------------------------------------------------
# Locate the Solution Wizard package (co-located registries live next to it)
# ---------------------------------------------------------------------------


def _find_wizard_dir() -> Path:
    """Walk upward from this script until we find the solution_wizard package."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "implementation_layer" / "solution_wizard"
        if (candidate / "src" / "solution_wizard" / "registry.py").exists():
            return candidate
    raise SystemExit(
        "Could not locate implementation_layer/solution_wizard from "
        f"{here}. Run this script from inside the gaik-toolkit repo."
    )


WIZARD_DIR = _find_wizard_dir()
PIN_FILE = WIZARD_DIR / "gaik_validated_version.txt"
REGISTRY_FILE = "registries/gaik_component_registry.json"
CARDS_FILE = "registries/component_reference_cards.json"

sys.path.insert(0, str(WIZARD_DIR / "src"))

from solution_wizard.registry import get_reference_cards, get_registry  # noqa: E402

# gaik packages whose public classes we expect to be tracked by the wizard.
TRACKED_GAIK_PACKAGES = (
    "gaik.software_components",
    "gaik.software_modules",
)

# Methods that belong to result objects / helpers, not the component class.
_SKIP_METHODS = {"load_schema", "save", "save_schema", "get", "model_dump"}


# ---------------------------------------------------------------------------
# Introspection helpers
# ---------------------------------------------------------------------------


def _import_primary_class(import_line: str):
    """Import a card's `import` line and return the first callable class, or None."""
    m = re.search(r"from\s+(gaik[\w\.]*)\s+import\s+([\w,\s]+)", import_line)
    if not m:
        return None
    modpath = m.group(1)
    names = [n.strip() for n in m.group(2).split(",")]
    try:
        with _quiet():
            mod = importlib.import_module(modpath)
    except Exception:
        return None
    for name in names:
        obj = getattr(mod, name, None)
        if isinstance(obj, type):
            return obj
    return None


def _constructor_params(cls) -> set[str]:
    try:
        return set(inspect.signature(cls.__init__).parameters) - {"self"}
    except (ValueError, TypeError):
        return set()


def _class_name_in_construct(construct: str) -> str | None:
    """The class being constructed, e.g. 'Transcriber' from 'x = Transcriber(...)'."""
    m = re.search(r"=\s*([A-Z]\w+)\s*\(", construct) or re.search(r"\b([A-Z]\w+)\s*\(", construct)
    return m.group(1) if m else None


def _top_level_kwargs(construct: str, class_name: str) -> list[str]:
    """Extract only the OUTERMOST constructor's keyword args.

    Avoids false positives from nested helper calls such as
    ``Transcriber(api_config=get_openai_config(use_azure=use_azure), language=...)``
    where ``use_azure`` belongs to the helper, not the component.
    """
    start = construct.find(class_name + "(")
    if start < 0:
        return []
    i = start + len(class_name) + 1  # just past the '('
    depth = 0
    kwargs: list[str] = []
    token = ""
    args_region = ""
    # capture the balanced-paren argument region
    while i < len(construct):
        ch = construct[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            if depth == 0:
                break
            depth -= 1
        args_region += ch
        i += 1
    # now find key= at top level (depth 0) within args_region
    depth = 0
    j = 0
    while j < len(args_region):
        ch = args_region[j]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and ch == "=" and args_region[j : j + 2] != "==":
            # walk back to grab the identifier
            m = re.search(r"(\w+)\s*$", token)
            if m:
                kwargs.append(m.group(1))
            token = ""
            j += 1
            continue
        elif depth == 0 and ch == ",":
            token = ""
            j += 1
            continue
        token += ch
        j += 1
    return kwargs


def _call_method(call_line: str) -> str | None:
    m = re.search(r"\.\s*(\w+)\s*\(", call_line)
    return m.group(1) if m else None


def _installed_version() -> str:
    try:
        from importlib.metadata import version

        return version("gaik")
    except Exception:
        try:
            import gaik

            return getattr(gaik, "__version__", "unknown")
        except Exception:
            return "unknown"


def _pinned_version() -> str:
    return PIN_FILE.read_text(encoding="utf-8").strip() if PIN_FILE.exists() else ""


def _card_module_paths(cards) -> set[str]:
    """All gaik module paths referenced by reference-card import lines."""
    refs: set[str] = set()
    for name in cards.names():
        m = re.search(r"from\s+(gaik[\w\.]+)\s+import", cards.get(name)["import"])
        if m:
            refs.add(m.group(1))
    return refs


def _gaik_subpackages() -> dict[str, str]:
    """Map each immediate subpackage dotted-path -> its parent tracked package.

    We scan at *subpackage* granularity (e.g. gaik.software_components.transcriber)
    rather than per-class: a genuinely new component arrives as a new submodule
    package, whereas per-class scanning floods on Pydantic schema/result classes.
    """
    subs: dict[str, str] = {}
    for pkg_name in TRACKED_GAIK_PACKAGES:
        try:
            with _quiet():
                pkg = importlib.import_module(pkg_name)
        except Exception:
            continue
        if not hasattr(pkg, "__path__"):
            continue
        for info in pkgutil.iter_modules(pkg.__path__, pkg_name + "."):
            if info.ispkg:
                subs[info.name] = pkg_name
    return subs


# ---------------------------------------------------------------------------
# Audit checks (each returns a list of finding dicts)
# ---------------------------------------------------------------------------


def _finding(category: str, component: str, detail: str, file_hint: str) -> dict:
    return {"category": category, "component": component, "detail": detail, "file_hint": file_hint}


def check_parity(reg, cards) -> list[dict]:
    reg_names = {e["name"] for e in reg.all()}
    card_names = set(cards.names())
    out = [
        _finding("parity", n, "registry component has no reference card", CARDS_FILE)
        for n in sorted(reg_names - card_names)
    ]
    out += [
        _finding("parity", n, "reference card has no registry entry", REGISTRY_FILE)
        for n in sorted(card_names - reg_names)
    ]
    return out


def check_removed(cards) -> list[dict]:
    out = []
    for name in cards.names():
        card = cards.get(name)
        if _import_primary_class(card["import"]) is None:
            out.append(
                _finding(
                    "removed",
                    name,
                    f"import does not resolve: {card['import']}",
                    CARDS_FILE,
                )
            )
    return out


def check_api_drift(cards) -> list[dict]:
    out = []
    for name in cards.names():
        card = cards.get(name)
        cls = _import_primary_class(card["import"])
        if cls is None:
            continue  # reported by check_removed
        params = _constructor_params(cls)

        construct = card.get("construct", "")
        cls_name = _class_name_in_construct(construct)
        if cls_name and "\n" not in construct:
            for kw in _top_level_kwargs(construct, cls_name):
                if kw not in params:
                    out.append(
                        _finding(
                            "api_drift",
                            name,
                            f"construct kwarg '{kw}' not in {cls.__name__}.__init__ "
                            f"(actual: {sorted(params)})",
                            CARDS_FILE,
                        )
                    )

        method = _call_method(card.get("call", ""))
        if method and method not in _SKIP_METHODS and not hasattr(cls, method):
            out.append(
                _finding(
                    "api_drift",
                    name,
                    f"call method '{method}' not found on {cls.__name__}",
                    CARDS_FILE,
                )
            )
    return out


_CONFIG_NAME_RE = re.compile(r"\b([A-Z]\w*(?:Config|Options|Settings|Params))\s*\(")


def _import_named_class(import_line: str, target: str):
    """Import the module of a card's `import` line and return class `target`."""
    m = re.search(r"from\s+(gaik[\w\.]*)\s+import\s+", import_line)
    if not m:
        return None
    try:
        with _quiet():
            mod = importlib.import_module(m.group(1))
    except Exception:
        return None
    obj = getattr(mod, target, None)
    return obj if isinstance(obj, type) else None


def _method_params(cls, method_name: str | None) -> set[str]:
    fn = getattr(cls, method_name, None) if method_name else None
    if fn is None:
        return set()
    try:
        return set(inspect.signature(fn).parameters) - {"self"}
    except (ValueError, TypeError):
        return set()


def _config_fields(card) -> set[str]:
    """Constructor params / dataclass fields of any *Config(...) the card builds.

    Components like ParallelTranscriber take their behaviour flags via a nested
    config object (``config=TranscriptionConfig(response_format=...)``), so those
    flags are legitimate options even though they live on the config, not the
    component constructor.
    """
    out: set[str] = set()
    for m in _CONFIG_NAME_RE.finditer(card.get("construct", "")):
        cfg = _import_named_class(card.get("import", ""), m.group(1))
        if cfg is None:
            continue
        out |= _constructor_params(cfg)
        with contextlib.suppress(Exception):
            import dataclasses

            if dataclasses.is_dataclass(cfg):
                out |= {f.name for f in dataclasses.fields(cfg)}
    return out


_PASSTHROUGH_RE = re.compile(r"^(\w+?)_(?:ctor|options)$")


def _passthrough_params(cls, card, cards) -> set[str]:
    """Params of the components a module forwards keyword dicts to.

    Modules like AudioToStructuredData expose their sub-components' knobs as
    passthrough dicts on the primary method — ``run(transcriber_ctor={...},
    extract_options={...})`` — which land on ``Transcriber(**...)`` /
    ``DataExtractor.extract(**...)``. Those flags are legitimate options even
    though they appear nowhere in the module's own signature. Resolve each
    ``<prefix>_ctor`` / ``<prefix>_options`` parameter against the card's
    ``subsumes`` list and accept the subsumed component's parameters too.
    """
    if cards is None:
        return set()
    subsumed = card.get("subsumes") or []
    if not subsumed:
        return set()

    out: set[str] = set()
    for param in _method_params(cls, _call_method(card.get("call", ""))):
        m = _PASSTHROUGH_RE.match(param)
        if not m:
            continue
        prefix = m.group(1).replace("_", "").lower()
        for name in subsumed:
            if not name.lower().endswith(prefix):
                continue
            sub_card = cards.get(name) if name in cards.names() else None
            if not sub_card:
                continue
            sub_cls = _import_primary_class(sub_card.get("import", ""))
            if sub_cls is None:
                continue
            out |= _constructor_params(sub_cls)
            out |= _method_params(sub_cls, _call_method(sub_card.get("call", "")))
    return out


def _accepted_option_params(cls, card, cards=None) -> set[str]:
    """Where a behaviour-changing option may legitimately live: the constructor,
    the primary method (run/enhance_text/transcribe/...), a nested config the
    construct line builds, or a subsumed component the primary method forwards a
    keyword dict to. Options are inference hints for the wizard, not a
    constructor-only contract — an option that maps to a real method/config
    argument is correct, not drift.
    """
    return (
        _constructor_params(cls)
        | _method_params(cls, _call_method(card.get("call", "")))
        | _config_fields(card)
        | _passthrough_params(cls, card, cards)
    )


def check_options(cards) -> list[dict]:
    out = []
    for name in cards.names():
        card = cards.get(name)
        opts = card.get("options") or []
        if not opts:
            continue
        cls = _import_primary_class(card["import"])
        if cls is None:
            continue
        params = _accepted_option_params(cls, card, cards)
        for opt in opts:
            opt_name = opt.get("name", "")
            if opt_name and opt_name not in params:
                out.append(
                    _finding(
                        "options",
                        name,
                        f"option '{opt_name}' is not a constructor, primary-method, "
                        f"nested-config, or subsumed-passthrough parameter of "
                        f"{cls.__name__} (accepted: {sorted(params)})",
                        CARDS_FILE,
                    )
                )
    return out


def check_new(reg, cards) -> list[dict]:
    """Subpackages under the tracked gaik packages that no card import references.

    A subpackage no card points at is a candidate new component family worth a
    human decision: add a registry entry + reference card, or (if it is an
    internal helper like an llm-provider layer) deliberately ignore it.
    """
    referenced = _card_module_paths(cards)
    out = []
    for sub_path in sorted(_gaik_subpackages()):
        if any(ref == sub_path or ref.startswith(sub_path + ".") for ref in referenced):
            continue
        out.append(
            _finding(
                "new",
                sub_path.rsplit(".", 1)[-1],
                f"gaik subpackage '{sub_path}' is not referenced by any reference card "
                f"(new component family, or an internal helper to ignore)",
                REGISTRY_FILE,
            )
        )
    return out


def check_version() -> list[dict]:
    installed = _installed_version()
    pinned = _pinned_version()
    if not pinned:
        return [
            _finding(
                "version",
                "gaik",
                f"no validated-version pin found; installed gaik is {installed}. "
                f"Create {PIN_FILE.name} once the registry is verified.",
                PIN_FILE.name,
            )
        ]
    if installed != pinned:
        return [
            _finding(
                "version",
                "gaik",
                f"installed gaik {installed} != last-validated {pinned}",
                PIN_FILE.name,
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_audit() -> dict:
    reg = get_registry()
    cards = get_reference_cards()
    try:
        with _quiet():
            import gaik  # noqa: F401
        gaik_ok = True
    except ImportError:
        gaik_ok = False

    findings: list[dict] = []
    findings += check_version()
    findings += check_parity(reg, cards)
    if gaik_ok:
        findings += check_removed(cards)
        findings += check_api_drift(cards)
        findings += check_options(cards)
        findings += check_new(reg, cards)

    return {
        "gaik_installed": _installed_version(),
        "gaik_validated": _pinned_version() or "(unpinned)",
        "gaik_importable": gaik_ok,
        "registry_components": len(reg.all()),
        "reference_cards": len(cards.names()),
        "findings": findings,
    }


def _print_report(result: dict) -> None:
    print("=" * 64)
    print("GAIK Sync - Registry Freshness Scan")
    print("=" * 64)
    print(f"  gaik installed       : {result['gaik_installed']}")
    print(f"  wizard validated     : {result['gaik_validated']}")
    print(f"  registry components  : {result['registry_components']}")
    print(f"  reference cards      : {result['reference_cards']}")
    if not result["gaik_importable"]:
        print("  NOTE: gaik not importable — introspection checks skipped.")
    print()

    findings = result["findings"]
    if not findings:
        print("No findings — the wizard registry is in sync with gaik.")
        return

    order = ["version", "removed", "api_drift", "options", "parity", "new"]
    labels = {
        "version": "VERSION",
        "removed": "REMOVED (card import failed)",
        "api_drift": "API DRIFT (constructor/method changed)",
        "options": "OPTIONS (option not a real param)",
        "parity": "PARITY (registry entry and reference card out of step)",
        "new": "NEW (untracked gaik class)",
    }
    by_cat: dict[str, list[dict]] = {}
    for f in findings:
        by_cat.setdefault(f["category"], []).append(f)

    for cat in order:
        items = by_cat.get(cat, [])
        if not items:
            continue
        print(f"[{labels[cat]}]  ({len(items)})")
        for f in items:
            print(f"  - {f['component']}: {f['detail']}")
            print(f"      -> update: {f['file_hint']}")
        print()

    print("-" * 64)
    print(f"{len(findings)} finding(s). The gaik-sync skill maps each to an edit.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any findings")
    args = parser.parse_args()

    result = run_audit()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _print_report(result)

    # Version-only findings are informational; don't fail --strict on them alone.
    actionable = [f for f in result["findings"] if f["category"] != "version"]
    return 1 if (args.strict and actionable) else 0


if __name__ == "__main__":
    sys.exit(main())

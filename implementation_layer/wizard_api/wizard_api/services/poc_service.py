"""PoC package generation for wizard_api sessions (#93).

Wraps the V1 scaffolder (``solution_wizard.scaffolder.scaffold_poc``) so the UI
can turn an approved blueprint into the runnable ``poc/`` package that #151's
listing and zip endpoints already serve. Deterministic: no API calls, no LLM.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from wizard_api.services import artifact_sync, blueprint_service, scaffold_guard

try:
    from solution_wizard.blueprint import Blueprint
    from solution_wizard.scaffolder import scaffold_poc
    from solution_wizard.v2_adapter import v2_to_v1_dict

    _SOLUTION_WIZARD_AVAILABLE = True
except ImportError:  # pragma: no cover - optional in minimal installs
    _SOLUTION_WIZARD_AVAILABLE = False

logger = logging.getLogger(__name__)


class PlaceholderBlueprintError(RuntimeError):
    """Nothing has been designed yet: the blueprint is still the seed (#181)."""


class PocGenerationError(RuntimeError):
    pass


class UnscaffoldableBlueprintError(PocGenerationError):
    """A name in the blueprint would reach generated code unchecked (scaffold_guard)."""


class PackageFolderError(PocGenerationError):
    """``poc/`` is not a plain folder of the session, so nothing is written into it."""


#: Records what *we* scaffolded, so a later run can tell its own output apart
#: from files the agent wrote during the conversation. See ``_clear_previous``.
#: It lives beside ``poc/`` rather than inside it, so the package the user
#: downloads is exactly what the scaffolder produced — no wizard bookkeeping.
MANIFEST_NAME = ".wizard-scaffold.json"

#: Subtrees a regeneration must never touch: the user's sample inputs, the
#: results of an earlier run, and hand-curated eval ground truth.
#: Written as POSIX parts, the same form ``_normalise`` gives a manifest entry.
_PRESERVED_DIRS = ("sample_input", "output", "evals/ground_truth")

#: What makes ``poc/`` a package. The agent writes ``schemas/`` and ``prompts/``
#: already at the schema-design step, long before any package exists, so those
#: alone are work in progress for the scaffolder to build on — not a finished
#: PoC to keep.
_PACKAGE_ENTRYPOINT = "run_poc.py"


def solution_wizard_available() -> bool:
    return _SOLUTION_WIZARD_AVAILABLE


def regular_file(path: str | os.PathLike, root: str | os.PathLike) -> bool:
    """A real file inside ``root``: not a symlink, and not reached through one.

    Everything under the session directory may have been written by the agent,
    and only the session's own files are part of what the API hands out.
    """
    if os.path.islink(path) or not os.path.isfile(path):
        return False
    real_root = os.path.realpath(root)
    real = os.path.realpath(path)
    return real.startswith(real_root + os.sep)


def regular_files(root: str | os.PathLike) -> list[str]:
    """The real files under ``root``, relative to it; symlinked files and folders are skipped."""
    found = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(folder, d))]
        for name in names:
            path = os.path.join(folder, name)
            if regular_file(path, root):
                found.append(os.path.relpath(path, root))
    return sorted(found)


def _blueprint_fingerprint(v1: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(v1, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _agent_v1_draft(output_dir: str | None) -> dict[str, Any] | None:
    """The agent's own V1 blueprint (``<output_dir>/use_case.blueprint.json``),
    when it is present and valid.

    The agent writes this complete V1 blueprint at spec generation. It carries
    ``selected_modules`` and the real ``input_types``, so scaffolding from it
    wires the case's own pattern (``audio_to_structured`` /
    ``document_to_structured`` / ``rag``). ``v2_to_v1_dict`` is minimal — it
    leaves ``selected_modules`` empty, drops the module into
    ``selected_building_blocks`` and hard-codes ``input_types`` to ``["text"]``
    — so ``_determine_pattern`` never matches and the scaffolder falls back to
    ``_generic`` (``template_wired: False``, a TODO stub for ``run_poc.py``).
    See #167. Returns None when there is no readable, valid draft, so the caller
    falls back to the conversion.
    """
    if not output_dir:
        return None
    try:
        with open(Path(output_dir) / "use_case.blueprint.json", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        Blueprint.model_validate(data)
    except Exception:  # noqa: BLE001 - not a valid V1 blueprint; convert instead
        return None
    return data


def build_v1_blueprint(
    v2_blueprint: dict[str, Any],
    *,
    session_id: str,
    output_dir: str | None = None,
    target_output_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The V1 blueprint the scaffolder expects.

    Prefers the agent's own draft (``use_case.blueprint.json``) when it is
    present and valid: it carries the selected module and real input types, so
    the scaffolder wires the case's own pattern. Only when there is no valid
    draft does it fall back to ``v2_to_v1_dict``, whose minimal output always
    scaffolds ``_generic`` (#167).

    ``v2_to_v1_dict`` fills ``target_output_spec`` with a placeholder
    (``schema_name: "Output"``, one ``result`` field) because a V2 blueprint
    does not carry the output fields — those are agreed separately at the
    Specification step and live on the session. The session override below
    keeps the agreed schema whichever source produced the blueprint; without it
    a converted blueprint would ship a one-field dummy schema.
    """
    v1 = _agent_v1_draft(output_dir)
    if v1 is None:
        v1 = v2_to_v1_dict(v2_blueprint, session_id=session_id)
    if target_output_spec and target_output_spec.get("fields"):
        v1["target_output_spec"] = target_output_spec
    return v1


def _normalise(relative: Any) -> str | None:
    """A manifest entry as a plain relative POSIX path, or None if it is not one.

    Every check on an entry uses this one value, so ``./sample_input/a.pdf`` and
    ``sample_input/a.pdf`` are the same file to all of them. Absolute paths and
    any ``..`` part are refused; ``.`` parts are dropped.
    """
    if not isinstance(relative, str) or not relative or "\x00" in relative:
        return None
    path = PurePosixPath(relative.replace(os.sep, "/"))
    if path.is_absolute() or os.path.isabs(relative):
        return None
    parts = [part for part in path.parts if part != "."]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def _is_preserved(relative: str) -> bool:
    """Whether a normalised entry lies in a subtree regeneration must not touch."""
    return any(relative == keep or relative.startswith(keep + "/") for keep in _PRESERVED_DIRS)


def _valid_manifest(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    files = data.get("files", [])
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        return False
    hashes = data.get("hashes", {})
    if not isinstance(hashes, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in hashes.items()
    ):
        return False
    blueprint = data.get("blueprint")
    return blueprint is None or isinstance(blueprint, str)


def _read_manifest(root: Path) -> dict[str, Any] | None:
    """The previous run's manifest, or None when there is none we can use.

    The manifest lives in the session directory, which the agent can write. A
    manifest of the wrong shape counts as no manifest at all, so it can never
    make a generation fail.
    """
    path = root / MANIFEST_NAME
    if not os.path.lexists(path):
        return None
    try:
        if os.path.islink(path) or not path.is_file():
            raise ValueError("not a regular file")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not _valid_manifest(data):
            raise ValueError("unexpected shape")
    except (OSError, ValueError) as exc:
        logger.warning("ignoring the scaffold manifest of a session: %s", exc)
        return None
    return {
        "blueprint": data.get("blueprint"),
        "files": data.get("files", []),
        "hashes": data.get("hashes", {}),
    }


def _manifest_files(manifest: dict[str, Any]) -> set[str]:
    """The normalised package paths a manifest claims."""
    return {n for n in (_normalise(f) for f in manifest.get("files", [])) if n is not None}


def _linked_part(poc_dir: Path, relative: str) -> Path | None:
    """The first symlink on the way to ``relative`` inside ``poc_dir``, the entry included."""
    current = poc_dir
    for part in relative.split("/"):
        current = current / part
        if current.is_symlink():
            return current
    return None


def _manifest_file(poc_dir: Path, relative: Any) -> Path | None:
    """The package file a manifest entry names, if it is a real file inside ``poc/``."""
    normalised = _normalise(relative)
    if normalised is None or _linked_part(poc_dir, normalised) is not None:
        return None
    target = poc_dir / normalised
    return target if regular_file(target, poc_dir) else None


def _remove_links(poc_dir: Path) -> None:
    """Remove every symlink inside ``poc/``, without following any of them.

    The scaffolder writes its files with ``Path.write_text``, which follows a
    link, so a link left at a path it writes would send that file outside the
    package. A link is never part of a package (``regular_files`` skips them),
    so removing one loses nothing the user can download.
    """
    for folder, dirs, names in os.walk(poc_dir):
        for name in [*dirs, *names]:
            path = os.path.join(folder, name)
            if os.path.islink(path):
                try:
                    os.unlink(path)
                except OSError:  # pragma: no cover - the write-through check below still holds
                    logger.warning("could not remove a link inside a PoC package")
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(folder, d))]


def _clear_previous(poc_dir: Path, manifest: dict[str, Any]) -> None:
    """Delete the files our own previous run wrote.

    The scaffolder deliberately leaves an existing ``schemas/output_schema.py``
    alone, so that a schema the user reviewed during the conversation is not
    overwritten. That guard would also freeze *our* schema, making a
    regeneration after a blueprint change a silent no-op. Clearing only what
    this manifest claims keeps both properties: the agent's files survive, ours
    are refreshed.

    A symlink at (or on the way to) a manifest path is removed as a link and
    never followed, so its target stays as it is.
    """
    for relative in sorted(_manifest_files(manifest)):
        if _is_preserved(relative):
            continue
        link = _linked_part(poc_dir, relative)
        try:
            if link is not None:
                link.unlink()
            elif regular_file(poc_dir / relative, poc_dir):
                (poc_dir / relative).unlink()
        except OSError:  # pragma: no cover - best effort, scaffolder rewrites anyway
            pass


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _agent_edited(poc_dir: Path, manifest: dict[str, Any]) -> bool:
    """Whether the agent rewrote any file our last run wrote.

    The agent finishes a composed pipeline by wiring the ``run_poc.py`` we
    scaffolded (there is no template for it). A regeneration that cleared "our"
    files would silently put the TODO stub back over that work. Manifests
    written before hashes were recorded cannot tell, and count as unedited.
    """
    hashes = manifest.get("hashes")
    for relative, digest in (hashes if isinstance(hashes, dict) else {}).items():
        normalised = _normalise(relative)
        if normalised is None or _is_preserved(normalised):
            continue
        target = _manifest_file(poc_dir, normalised)
        try:
            if target is not None and _file_hash(target) != digest:
                return True
        except OSError:  # pragma: no cover - unreadable counts as not ours to judge
            continue
    return False


def _agent_package(poc_dir: Path) -> dict[str, Any]:
    return {
        "generated": True,
        "source": "agent",
        "scaffolded": False,
        "pattern": "",
        "template_wired": True,
        "files": _relative_files(poc_dir),
        "regenerated": False,
        "blueprint_changed": False,
    }


def _relative_files(poc_dir: Path) -> list[str]:
    return [f for f in regular_files(poc_dir) if "__pycache__" not in Path(f).parts]


def generate_poc(
    v2_blueprint: dict[str, Any],
    *,
    session_id: str,
    output_dir: str,
    target_output_spec: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Scaffold ``<output_dir>/poc`` from the session's active blueprint.

    Returns the pattern the scaffolder picked, the files now in the package,
    and whether this replaced an earlier scaffold of ours.

    A package the *agent* produced during the conversation is left alone unless
    ``force`` says otherwise: the agent wires the real GAIK component for the
    case's own pattern and can add synthetic test data and an eval rubric,
    which this deterministic scaffolder cannot reproduce. Overwriting it would
    trade a working, case-specific PoC for a generic template.
    """
    if not _SOLUTION_WIZARD_AVAILABLE:
        raise PocGenerationError("solution_wizard package is not installed")
    if not output_dir:
        raise PocGenerationError("session has no output_dir")

    root = Path(output_dir)
    poc_dir = root / "poc"
    if poc_dir.is_symlink() or (poc_dir.exists() and not poc_dir.is_dir()):
        logger.warning("refusing to generate a PoC: the package path is not a plain folder")
        raise PackageFolderError(
            "the PoC package location is not a plain folder, so it cannot be regenerated"
        )
    previous = _read_manifest(root)

    if not force:
        if previous is None and (poc_dir / _PACKAGE_ENTRYPOINT).is_file():
            # No manifest and an entrypoint of its own: the agent built the package.
            return _agent_package(poc_dir)
        if previous is not None and _agent_edited(poc_dir, previous):
            # We scaffolded it, then the agent wired it: the package is now theirs.
            return _agent_package(poc_dir)

    # The seed blueprint is editable scenery, not a design. Without the agent's
    # draft on disk there is nothing to scaffold from, and the skeleton this used
    # to write wired nothing and explained nothing (#181).
    if blueprint_service.is_placeholder(v2_blueprint) and not artifact_sync.has_draft_blueprint(
        output_dir
    ):
        raise PlaceholderBlueprintError(
            "the blueprint is still the placeholder: nothing has been designed yet, "
            "so there is nothing to scaffold. Work through the wizard to Gate 2 first."
        )

    try:
        v1 = build_v1_blueprint(
            v2_blueprint,
            session_id=session_id,
            output_dir=output_dir,
            target_output_spec=target_output_spec,
        )
    except Exception as exc:  # noqa: BLE001 - the adapter's own errors, named for the user
        raise PocGenerationError(
            f"blueprint could not be adapted for the scaffolder: {exc}"
        ) from exc
    try:
        # The scaffolder pastes these values into source it then executes; see
        # scaffold_guard. The fingerprint below stays on the blueprint as written.
        blueprint = Blueprint.model_validate(scaffold_guard.safe_for_scaffolding(v1))
    except scaffold_guard.UnsafeBlueprintError as exc:
        raise UnscaffoldableBlueprintError(f"blueprint is not scaffoldable: {exc}") from exc
    except Exception as exc:  # pydantic ValidationError and friends
        raise PocGenerationError(f"blueprint is not scaffoldable: {exc}") from exc

    # Files already here that our last run did not write are the agent's — the
    # schema and extraction prompt approved in the conversation. The scaffolder
    # builds on them, and leaving them out of the manifest keeps a later
    # regeneration from deleting them.
    ours_before = _manifest_files(previous) if previous else set()
    agent_files = set(_relative_files(poc_dir)) - ours_before if poc_dir.is_dir() else set()

    if previous:
        _clear_previous(poc_dir, previous)
    if poc_dir.is_dir():
        _remove_links(poc_dir)

    try:
        result = scaffold_poc(blueprint, root)
    except Exception as exc:
        raise PocGenerationError(f"scaffolding failed: {exc}") from exc

    files = _relative_files(poc_dir)
    fingerprint = _blueprint_fingerprint(v1)
    try:
        with open(root / MANIFEST_NAME, "w", encoding="utf-8") as fh:
            ours = [f for f in files if f not in agent_files]
            json.dump(
                {
                    "blueprint": fingerprint,
                    "files": ours,
                    "hashes": {f: _file_hash(poc_dir / f) for f in ours},
                },
                fh,
                indent=2,
            )
    except OSError as exc:  # pragma: no cover - the package itself is fine
        raise PocGenerationError(f"could not record the scaffold manifest: {exc}") from exc

    return {
        "generated": True,
        "source": "scaffolder",
        "scaffolded": True,
        "pattern": result.get("pattern", ""),
        "template_wired": bool(result.get("template_wired")),
        "files": files,
        "regenerated": previous is not None,
        "blueprint_changed": previous is None or previous.get("blueprint") != fingerprint,
    }


def discard_poc(output_dir: str) -> None:
    """Remove a generated package. Only used by tests and by callers that need
    a clean slate — never wired to a route, because losing a PoC should not be
    one request away."""
    if not output_dir:
        return
    shutil.rmtree(Path(output_dir) / "poc", ignore_errors=True)


#: What a package must have before it is offered as a download. The customer's
#: test report found the download button live as soon as *any* file existed, so
#: a package with no README, no requirements.txt and an unwired entrypoint could
#: be taken away and did nothing when run.
README_NAME = "README.md"
REQUIREMENTS_NAME = "requirements.txt"


def package_problems(poc_dir: str) -> list[str]:
    """What is missing or broken before this package can be handed to a user.

    Empty means ready. Nothing in the package is executed here: the entrypoint
    is parsed, not imported, because it is agent-written code and the api holds
    the model credentials. The checks cover what a first run would trip over at
    once: a missing file, an entrypoint that does not parse or wires no gaik
    component (a call that exists only in a comment does not count), an import
    that cannot be resolved, and a schema file gaik cannot load.
    """
    problems: list[str] = []

    entrypoint = os.path.join(poc_dir, _PACKAGE_ENTRYPOINT)
    if not regular_file(entrypoint, poc_dir):
        problems.append(f"{_PACKAGE_ENTRYPOINT} is missing")
    else:
        with open(entrypoint, encoding="utf-8", errors="replace") as fh:
            source = fh.read()
        problems.extend(_entrypoint_problems(source, poc_dir))

    requirements = os.path.join(poc_dir, REQUIREMENTS_NAME)
    if not regular_file(requirements, poc_dir):
        problems.append(f"{REQUIREMENTS_NAME} is missing")
    else:
        with open(requirements, encoding="utf-8", errors="replace") as fh:
            if "gaik" not in fh.read():
                problems.append(f"{REQUIREMENTS_NAME} does not require gaik")

    if not regular_file(os.path.join(poc_dir, README_NAME), poc_dir):
        problems.append(f"{README_NAME} is missing")

    problems.extend(_schema_problems(poc_dir))
    problems.extend(_transcription_problems(poc_dir))
    return problems


CONFIG_NAME = "config.yaml"
#: A config file larger than this is not one the scaffolder wrote; it is not parsed.
_MAX_CONFIG_BYTES = 256 * 1024
_TRANSCRIPTION_STAGE_CALL = re.compile(r"get_stage_config\([^()]*?[\"']transcription[\"']")
_TRANSCRIBING_NAME = re.compile(
    r"\b(" + "|".join(sorted(scaffold_guard.TRANSCRIBING_COMPONENTS)) + r")\b"
)


#: Stages that use gaik's structured extraction. It waits 30 seconds for a model
#: call unless the config says otherwise, and a long document takes more: every
#: try then times out and the run fails after about six minutes (UC05, R31).
_STRUCTURED_STAGES = ("extraction", "judge")
_DEFAULT_MODEL_TIMEOUT_SECONDS = 120


def model_timeout_seconds() -> int:
    raw = os.getenv("WIZARD_POC_MODEL_TIMEOUT_SECONDS", "").strip()
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MODEL_TIMEOUT_SECONDS
    return value if value > 0 else _DEFAULT_MODEL_TIMEOUT_SECONDS


def config_with_model_timeout(poc_dir: str) -> str | None:
    """The package's config.yaml with a model call limit on its structured stages.

    None when there is nothing to change: no readable config, or every such
    stage already names its own limit. A stage the config does not list is not
    added, because a listed stage no longer falls back to ``models:``.
    """
    path = os.path.join(poc_dir, CONFIG_NAME)
    if not regular_file(path, poc_dir) or os.path.getsize(path) > _MAX_CONFIG_BYTES:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return None
    stages = config.get("stages") if isinstance(config, dict) else None
    if not isinstance(stages, dict):
        return None
    changed = False
    for name in _STRUCTURED_STAGES:
        stage = stages.get(name)
        if isinstance(stage, dict) and "timeout" not in stage:
            stage["timeout"] = model_timeout_seconds()
            changed = True
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True) if changed else None


def _package_transcribes(poc_dir: str) -> bool:
    """Whether the package's code reads the transcription stage or builds a transcriber."""
    for relative in regular_files(poc_dir):
        parts = Path(relative).parts
        if not relative.endswith(".py") or parts[0] in _NOT_CODE_DIRS:
            continue
        try:
            with open(os.path.join(poc_dir, relative), encoding="utf-8", errors="replace") as fh:
                source = fh.read()
        except OSError:
            continue
        if _TRANSCRIPTION_STAGE_CALL.search(source) or _TRANSCRIBING_NAME.search(source):
            return True
    return False


def _transcription_problems(poc_dir: str) -> list[str]:
    """A transcription stage in config.yaml that would run on the chat model.

    The generated ``get_stage_config`` takes ``stages.transcription.model`` as
    the transcription model when ``transcription_model`` is not set. The
    scaffolder fills that ``model`` with the chat model when the blueprint
    names no transcription model, and the provider then refuses the first
    audio file. Only whether a transcription model is named is checked, not
    which one.
    """
    path = os.path.join(poc_dir, CONFIG_NAME)
    if not regular_file(path, poc_dir) or os.path.getsize(path) > _MAX_CONFIG_BYTES:
        return []
    try:
        import yaml

        with open(path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
    except Exception:  # noqa: BLE001 - an unreadable config is the run's own error to report
        return []
    if not isinstance(config, dict):
        return []
    stages = config.get("stages") if isinstance(config.get("stages"), dict) else {}
    stage = stages.get("transcription")
    if not isinstance(stage, dict) or not _package_transcribes(poc_dir):
        return []

    def text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    if text(stage.get("transcription_model")):
        return []
    models = config.get("models") if isinstance(config.get("models"), dict) else {}
    extraction = stages.get("extraction") if isinstance(stages.get("extraction"), dict) else {}
    chat = text(extraction.get("model")) or text(models.get("extraction"))
    stage_model = text(stage.get("model"))
    if stage_model and stage_model != chat:
        return []  # a model of its own, named for this stage
    if not stage_model and text(models.get("transcription")):
        return []  # the package's own transcription default applies
    return [
        f"{CONFIG_NAME} has no transcription model for the transcription stage, so audio "
        "would be sent to the chat model, which cannot transcribe. Set "
        "models.transcription_model in the blueprint and regenerate, or set "
        "stages.transcription.transcription_model in config.yaml"
    ]


def _imports(tree: ast.AST) -> list[tuple[str, int]]:
    """Every (module, line) the entrypoint imports, leaving out imports guarded by
    a ``try`` that catches ImportError: those are optional by the author's intent."""
    found: list[tuple[str, int]] = []

    def guarded(node: ast.Try) -> bool:
        for handler in node.handlers:
            names = ast.dump(handler.type) if handler.type is not None else "bare"
            if any(n in names for n in ("ImportError", "ModuleNotFoundError", "Exception", "bare")):
                return True
        return False

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Try) and guarded(node):
            for child in node.handlers + node.orelse + node.finalbody:
                visit(child)
            return
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module, node.lineno))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return found


_TODO_MARKER = re.compile(r"\b(TODO|FIXME)\b")


def _todo_markers(source: str) -> list[int]:
    """Line numbers of the TODO/FIXME markers in ``source`` (comments and strings)."""
    return [n for n, line in enumerate(source.splitlines(), start=1) if _TODO_MARKER.search(line)]


def _entrypoint_problems(source: str, poc_dir: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{_PACKAGE_ENTRYPOINT} does not parse (line {exc.lineno}: {exc.msg})"]

    imports = _imports(tree)
    # The scaffolder's _generic fallback is a TODO stub, and a skeleton whose
    # component calls are comments names gaik in those comments. Only an import
    # statement counts as wiring a component.
    if not any(module.split(".")[0] == "gaik" for module, _ in imports):
        return [f"{_PACKAGE_ENTRYPOINT} does not wire any gaik component"]

    # The agent writes the entrypoint in steps and leaves TODO markers where it
    # has not been yet. A package that already imports gaik was offered as
    # ready while nine such markers were still in it (#252): the markers say
    # the author is not done, so the package is not.
    markers = _todo_markers(source)
    if markers:
        first = markers[0]
        return [
            f"{_PACKAGE_ENTRYPOINT} still has {len(markers)} TODO marker(s), "
            f"first at line {first}: the package is not finished"
        ]

    # Without gaik in this environment we cannot tell what the runner has.
    if not _gaik_available():
        return []
    problems: list[str] = []
    seen: set[str] = set()
    for module, line in imports:
        top = module.split(".")[0]
        if top in seen or top in sys.stdlib_module_names or _is_local_module(poc_dir, top):
            continue
        seen.add(top)
        if not _resolvable(module):
            problems.append(
                f"{_PACKAGE_ENTRYPOINT} line {line} imports {module}, "
                "which the sandbox image does not have"
            )
    problems.extend(_run_time_dependency_problems(tree))
    return problems


def _gaik_available() -> bool:
    return importlib.util.find_spec("gaik") is not None


#: gaik parts that import a heavy package only when they first run, so the
#: import of the part itself succeeds: (module prefix, class names, the package
#: they need at run time, the gaik extra that installs it). The sandbox image
#: leaves docling out on purpose (it brings PyTorch and models), and a package
#: built on RAGWorkflow passed every check and then failed on its first
#: document (UC03, 5 Nov 2026). Since gaik 0.8.10 RAGWorkflow(parser="text")
#: reads the documents' own text layer and needs no docling, so that use is
#: left alone (see _rag_workflow_reads_text_only).
_RUN_TIME_DEPENDENCIES = (
    (
        "gaik.software_modules.RAG_workflow",
        ("RAGWorkflow",),
        "docling",
        "rag-parser-vision",
    ),
    (
        "gaik.software_components.RAG.rag_parser_vision",
        ("VisionRagParser",),
        "docling",
        "rag-parser-vision",
    ),
    (
        "gaik.software_components.RAG.rag_parser_docling",
        ("DoclingRagParser",),
        "docling",
        "rag-parser-docling",
    ),
)


def _rag_workflow_reads_text_only(tree: ast.AST) -> bool:
    """Every ``RAGWorkflow(...)`` call in the entrypoint passes ``parser="text"``.

    Only a literal counts: a value read from config can be "vision" at run time,
    and the default is "vision". With no call in sight (the class is aliased or
    built elsewhere) the answer is no, so the package is still held back.
    """
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "RAGWorkflow")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "RAGWorkflow")
        )
    ]
    return bool(calls) and all(
        any(
            keyword.arg == "parser"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "text"
            for keyword in call.keywords
        )
        for call in calls
    )


def _run_time_dependency_problems(tree: ast.AST) -> list[str]:
    """A gaik part the entrypoint uses whose run-time package the image lacks.

    Matched on the module imported (``from gaik.software_modules.RAG_workflow
    import ...``) or on the class name imported from a gaik package
    (``from gaik.software_modules import RAGWorkflow``).
    """
    problems: list[str] = []
    reported: set[str] = set()
    text_only_rag = _rag_workflow_reads_text_only(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            pairs = [(node.module, alias.name) for alias in node.names]
        elif isinstance(node, ast.Import):
            pairs = [(alias.name, "") for alias in node.names]
        else:
            continue
        for module, name in pairs:
            if not module.split(".")[0] == "gaik":
                continue
            for prefix, classes, needed, extra in _RUN_TIME_DEPENDENCIES:
                part = name if name in classes else prefix.rsplit(".", 1)[-1]
                uses = module == prefix or module.startswith(prefix + ".") or name in classes
                if not uses or part in reported or _resolvable(needed):
                    continue
                if part in ("RAGWorkflow", "RAG_workflow"):
                    if text_only_rag:
                        continue
                    way_out = (
                        'pass parser="text" to RAGWorkflow (it then reads the '
                        "documents' text layer), or build the pipeline from components "
                        "the image has (for example PyMuPDFParser with the RAG components)"
                    )
                else:
                    way_out = (
                        "build the pipeline from components the image "
                        "has (for example PyMuPDFParser with the RAG components)"
                    )
                reported.add(part)
                problems.append(
                    f"{_PACKAGE_ENTRYPOINT} line {node.lineno} uses {part}, which needs "
                    f"{needed} (gaik extra {extra}) when it runs, and the sandbox image "
                    f"does not have it: {way_out}"
                )
    return problems


#: Package folders that hold inputs and results, never the package's own code.
_NOT_CODE_DIRS = {"sample_input", "output", "__pycache__", ".venv", "venv"}


def _is_local_module(poc_dir: str, name: str) -> bool:
    """A module the package ships itself: at its root, or one folder down.

    One folder down covers the wizard's own layout: ``schemas/output_schema.py``
    is imported after ``sys.path.insert(0, .../schemas)``, and a package that did
    so was refused as importing a module the sandbox lacks (UC03, 6 Oct 2026).
    """

    def _here(folder: str) -> bool:
        return os.path.isfile(os.path.join(folder, name + ".py")) or os.path.isdir(
            os.path.join(folder, name)
        )

    if _here(poc_dir):
        return True
    try:
        entries = os.scandir(poc_dir)
    except OSError:
        return False
    with entries:
        return any(
            entry.is_dir() and entry.name not in _NOT_CODE_DIRS and _here(entry.path)
            for entry in entries
        )


def _resolvable(module: str) -> bool:
    """The api image installs the same gaik extras as the runner (a test keeps the
    two lists equal), so a module the api cannot find is one the runner lacks."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, AttributeError):
        return False


REQUIREMENTS_JSON = os.path.join("schemas", "output_schema_requirements.json")


def _null_non_string_defaults(node: Any) -> None:
    if isinstance(node, dict):
        if (
            "field_name" in node
            and node.get("default") is not None
            and not isinstance(node["default"], str)
        ):
            node["default"] = None
        for value in node.values():
            _null_non_string_defaults(value)
    elif isinstance(node, list):
        for value in node:
            _null_non_string_defaults(value)


def _schema_problems(poc_dir: str) -> list[str]:
    path = os.path.join(poc_dir, REQUIREMENTS_JSON)
    if not regular_file(path, poc_dir):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError:
        # The error text would name the file's place on the server.
        return [f"{REQUIREMENTS_JSON} could not be read"]
    except ValueError as exc:
        return [f"{REQUIREMENTS_JSON} is not valid JSON ({exc})"]
    try:
        from gaik.software_components.extractor import ExtractionRequirements
    except ImportError:
        return []
    # run_poc.py resets a non-string field default to null before loading, so a
    # default of that kind is not a reason to hold the package back.
    _null_non_string_defaults(data)
    # Composite files (parent_with_nested_list) have another body; only the
    # plain extraction layout is checked here.
    if isinstance(data, dict) and data.get("requirements_type", "extraction") != "extraction":
        return []
    body = data.get("requirements") if isinstance(data, dict) else None
    try:
        if not isinstance(body, dict):
            return [f'{REQUIREMENTS_JSON} has no "requirements" section']
        ExtractionRequirements(**body)
    except Exception as exc:  # pydantic.ValidationError, whatever the version
        first = str(exc).strip().splitlines()
        detail = " ".join(first[1:3]).strip() or (first[0] if first else "invalid")
        return [f"{REQUIREMENTS_JSON} cannot be loaded by gaik ({detail[:160]})"]
    return []


#: The files whose content decides whether a preflight is still current. The
#: agent rewrites ``run_poc.py`` after a package first reads as ready, so a check
#: is tied to what it looked at, not to the package merely existing.
_VERSION_FILES = (
    "run_poc.py",
    "config.yaml",
    "provider_config.py",
    "requirements.txt",
    os.path.join("schemas", "output_schema.py"),
    os.path.join("schemas", "output_schema_requirements.json"),
)


def package_version(poc_dir: str) -> str:
    """A short digest of the files a preflight reads; changes when any of them does."""
    digest = hashlib.sha256()
    for name in _VERSION_FILES:
        path = os.path.join(poc_dir, name)
        digest.update(name.encode())
        if regular_file(path, poc_dir):
            with open(path, "rb") as fh:
                digest.update(fh.read())
    return digest.hexdigest()[:16]


def package_is_ready(poc_dir: str) -> bool:
    return not package_problems(poc_dir)


# ---------------------------------------------------------------------------
# Sample input for a sandbox run (#95)
# ---------------------------------------------------------------------------

#: Where an uploaded input lands. It is inside the package on purpose: the zip
#: endpoint already serves the whole poc/ folder and the Job's init container
#: unpacks it, so an upload reaches the run with no change to the manifest. It
#: also survives regeneration — `_PRESERVED_DIRS` keeps it.
SAMPLE_INPUT_DIR = "sample_input"

#: One file, not a corpus. The run has ten minutes and a 1 GiB scratch volume.
MAX_INPUT_BYTES = 50 * 1024 * 1024


class InputTooLargeError(ValueError):
    """An upload over the limit: refused before the rest of it is read (#297)."""


async def read_upload(file: Any, limit: int | None = None) -> bytes:
    """The upload's bytes, read a piece at a time and stopped at the limit.

    ``await file.read()`` held the whole upload in memory before any size
    check, so a body the relay did not measure (chunked, no content-length)
    cost its full size (#297). This stops at the first byte over the limit.
    """
    limit = MAX_INPUT_BYTES if limit is None else limit
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data += chunk
        if len(data) > limit:
            raise InputTooLargeError(f"the file is larger than {limit // (1024 * 1024)} MB")
    return bytes(data)


class InputRejectedError(ValueError):
    """The upload is not something we will write into a package."""


def safe_input_name(filename: str) -> str:
    """The name we will store, or refuse.

    Uploads go into ``sample_input/`` and nowhere else. The package root holds
    ``run_poc.py`` — the file the sandbox Job executes — so a name that can
    climb out of the input directory is the difference between handing the run
    some data and handing it a different program.
    """
    raw = (filename or "").strip()
    if not raw:
        raise InputRejectedError("the file has no name")

    # A browser legitimately sends a path when the user picks a file from a
    # folder, so a directory prefix is stripped rather than refused. A ".."
    # segment is not that — it is an attempt to leave the input directory, and
    # quietly turning it into a plain name would hide what was asked for.
    parts = raw.replace("\\", "/").split("/")
    if any(part == ".." for part in parts):
        raise InputRejectedError(f"'{filename}' tries to leave the input directory")
    if raw.startswith("/") or raw.startswith("\\") or (len(raw) > 1 and raw[1] == ":"):
        raise InputRejectedError(f"'{filename}' is an absolute path")

    name = parts[-1]
    if name in {"", ".", ".."} or name.startswith("."):
        raise InputRejectedError(f"'{filename}' is not a usable file name")
    if os.sep in name or (os.altsep and os.altsep in name):
        raise InputRejectedError(f"'{filename}' is not a usable file name")
    if len(name) > 200:
        raise InputRejectedError("the file name is too long")
    return name


#: Beside the inputs: the names of the files the user added themselves, one a
#: line. The package's input helper (input_bundle.py) reads it and takes such a
#: file before the wizard's example of the same type; without it a run read
#: whichever name sorted first, and an uploaded file was often never read. It
#: lives in sample_input/, so it travels to the sandbox with the inputs and is
#: no part of the package's version.
UPLOADED_NAMES_FILE = ".uploaded"


def sample_input_dir(poc_dir: str) -> str:
    return os.path.join(poc_dir, SAMPLE_INPUT_DIR)


def uploaded_sample_inputs(poc_dir: str) -> list[str]:
    """The inputs the user added themselves and that are still there, oldest first."""
    folder = sample_input_dir(poc_dir)
    try:
        with open(os.path.join(folder, UPLOADED_NAMES_FILE), encoding="utf-8") as fh:
            names = [line.strip() for line in fh if line.strip()]
    except OSError:
        return []
    return [n for n in dict.fromkeys(names) if os.path.isfile(os.path.join(folder, n))]


def _record_uploaded(poc_dir: str, names: list[str]) -> None:
    path = os.path.join(sample_input_dir(poc_dir), UPLOADED_NAMES_FILE)
    # Never through a link: the list is written where the inputs are, or not at all.
    if os.path.islink(path) or not names:
        with contextlib.suppress(FileNotFoundError):
            os.remove(path)
    if not names:
        return
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(names) + "\n")


def save_sample_input(poc_dir: str, filename: str, data: bytes) -> str:
    """Write one input file into the package, and return its stored name."""
    if len(data) > MAX_INPUT_BYTES:
        raise InputRejectedError(f"the file is larger than {MAX_INPUT_BYTES // (1024 * 1024)} MB")
    if not data:
        raise InputRejectedError("the file is empty")

    name = safe_input_name(filename)
    target_dir = sample_input_dir(poc_dir)
    os.makedirs(target_dir, exist_ok=True)

    target = os.path.realpath(os.path.join(target_dir, name))
    root = os.path.realpath(target_dir)
    # Belt and braces: even with the name checked, the resolved path must still
    # be inside the input directory — a symlinked sample_input would otherwise
    # let a write land elsewhere.
    if target != root and not target.startswith(root + os.sep):
        raise InputRejectedError(f"'{filename}' resolves outside the input directory")

    with open(target, "wb") as fh:
        fh.write(data)
    _record_uploaded(poc_dir, [*(n for n in uploaded_sample_inputs(poc_dir) if n != name), name])
    return name


def list_sample_inputs(poc_dir: str) -> list[dict[str, object]]:
    """The files in ``sample_input/``, each with whether the user added it.

    The wizard writes example inputs there too. The PoC tab starts its test run
    by itself only on the user's own files: in a UC04 run it started on the
    wizard's examples before the user had added anything, and the report cited
    those examples beside the user's documents.
    """
    target_dir = sample_input_dir(poc_dir)
    if not os.path.isdir(target_dir):
        return []
    uploaded = set(uploaded_sample_inputs(poc_dir))
    entries = []
    for name in sorted(os.listdir(target_dir)):
        path = os.path.join(target_dir, name)
        if name != UPLOADED_NAMES_FILE and os.path.isfile(path):
            entries.append(
                {"name": name, "bytes": os.path.getsize(path), "uploaded": name in uploaded}
            )
    return entries


def delete_sample_input(poc_dir: str, filename: str) -> bool:
    name = safe_input_name(filename)
    path = os.path.join(sample_input_dir(poc_dir), name)
    if not regular_file(path, poc_dir):
        return False
    os.remove(path)
    _record_uploaded(poc_dir, [n for n in uploaded_sample_inputs(poc_dir) if n != name])
    return True


# ---------------------------------------------------------------------------
# The deployable package (#143)
# ---------------------------------------------------------------------------

#: What belongs to developing the PoC but not to handing it over. The sample
#: input is the developer's test document, `output/` is the previous run's
#: result, and __pycache__ was found in a package during review — none of it is
#: part of what someone else installs.
_NOT_DEPLOYABLE_DIRS = (SAMPLE_INPUT_DIR, "output")
_NOT_DEPLOYABLE_NAMES = (MANIFEST_NAME, ".env")
_NOT_DEPLOYABLE_SUFFIXES = (".pyc", ".pyo")


def is_deployable_path(relative_path: str) -> bool:
    """Whether one file inside poc/ belongs in the deployable package."""
    parts = relative_path.replace("\\", "/").split("/")
    if any(part == "__pycache__" for part in parts):
        return False
    if parts[0] in _NOT_DEPLOYABLE_DIRS:
        return False
    name = parts[-1]
    if name in _NOT_DEPLOYABLE_NAMES:
        return False
    return not name.endswith(_NOT_DEPLOYABLE_SUFFIXES)


def deployable_files(poc_dir: str) -> list[str]:
    """The package as someone else receives it, relative to poc/."""
    return [rel for rel in regular_files(poc_dir) if is_deployable_path(rel)]


#: The folder the wizard writes the solution's documentation into (step 12).
SOLUTION_DOCS_DIR = "docs"
#: The documents ``generate_docs.py`` writes there, in its order: solution_wizard's
#: ``docs_generator.DOC_NAMES``. Kept here because the api hands the documents
#: over without solution_wizard installed; a test holds the two lists together.
SOLUTION_DOC_NAMES = (
    "genai_product_canvas",
    "technical_specification",
    "user_guide",
    "developer_guide",
    "evaluation_plan",
)
#: The diagram's name in the deployable package. It is drawn from the session's
#: blueprint when the package is taken, not copied, see :func:`stored_bpmn`.
SOLUTION_BPMN_NAME = artifact_sync.WORKFLOW_BPMN_FILE
#: A solution file larger than this is left out of the package. The documents
#: and diagrams the wizard writes are a few kilobytes each.
MAX_SOLUTION_FILE_BYTES = 5 * 1024 * 1024


def _solution_file(root: str, relative: str) -> str | None:
    """The session's file at ``relative``, when it is a real file of a sane size."""
    path = os.path.join(root, relative)
    if not regular_file(path, root) or os.path.getsize(path) > MAX_SOLUTION_FILE_BYTES:
        return None
    return path


def solution_files(output_dir: str | None) -> list[tuple[str, str]]:
    """The files beside ``poc/`` that go into the deployable package as they are.

    Each entry is the name the file has in the package and where it is in the
    session: the blueprint the wizard wrote (the use case, the business and
    technical specification with the model provider and preferences, the
    components and the workflow), the workflow as a Mermaid diagram, and the
    documents ``generate_docs.py`` writes (:data:`SOLUTION_DOC_NAMES`). Only
    those: anything else in ``docs/`` (a ``.env``, ``__pycache__``, a copy of a
    test document) stays out. The BPMN diagram is not here; it is drawn when the
    package is taken (:data:`SOLUTION_BPMN_NAME`).

    Real files only, as in the package: a symlink the agent left is not
    followed, and neither is a linked ``docs/`` folder.
    """
    if not output_dir or not os.path.isdir(output_dir):
        return []
    root = os.path.realpath(output_dir)
    wanted = [artifact_sync.DRAFT_BLUEPRINT_FILE, artifact_sync.WORKFLOW_MMD_FILE]
    docs = os.path.join(root, SOLUTION_DOCS_DIR)
    if os.path.isdir(docs) and not os.path.islink(docs):
        wanted += [f"{SOLUTION_DOCS_DIR}/{name}.md" for name in SOLUTION_DOC_NAMES]
    found: list[tuple[str, str]] = []
    for name in wanted:
        path = _solution_file(root, name)
        if path is not None:
            found.append((name, path))
    return found


def solution_file_names(output_dir: str | None, *, can_draw: bool) -> list[str]:
    """The names the deployable package carries beside ``poc/``, in its order.

    The BPMN diagram is named where the package can draw it from the session's
    blueprint (``can_draw``: solution_wizard is installed) or falls back to the
    one the session kept (:func:`stored_bpmn`).
    """
    if not output_dir or not os.path.isdir(output_dir):
        return []
    names = [name for name, _ in solution_files(output_dir)]
    if can_draw or stored_bpmn(output_dir) is not None:
        position = 1 if names[:1] == [artifact_sync.DRAFT_BLUEPRINT_FILE] else 0
        names.insert(position, SOLUTION_BPMN_NAME)
    return names


def stored_bpmn(output_dir: str | None) -> tuple[str, str] | None:
    """The diagram already drawn in the session, for when it cannot be drawn again.

    The workspace's (``ui_view/workflow.bpmn``, written on the last chat turn),
    else the agent's own ``workflow.bpmn``; with where it came from
    (``"workspace_view"`` or ``"agent_draft"``). Either may be older than the
    blueprint: a save in the Blueprint form or the diagram rewrites neither.
    """
    if not output_dir or not os.path.isdir(output_dir):
        return None
    root = os.path.realpath(output_dir)
    for relative, source in (
        (artifact_sync.UI_VIEW_BPMN_FILE, "workspace_view"),
        (artifact_sync.WORKFLOW_BPMN_FILE, "agent_draft"),
    ):
        path = _solution_file(root, relative)
        if path is not None:
            return path, source
    return None

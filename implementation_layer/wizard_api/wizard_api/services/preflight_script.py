"""The script a preflight Job runs inside the runner image (#252).

A preflight is a sandbox run that does everything a first run would trip over
before it reaches the input: it parses ``run_poc.py``, imports what that file
imports (with the runner's own packages, not an approximation of them), builds
the model config of every stage in ``config.yaml`` through the package's
``provider_config.py``, and loads the approved schema the way gaik does. No model
is called, so it needs no input and costs nothing.

It lives here as text because the Job runs it with ``python -c``: the runner image
is built and rolled out separately, and a script baked into it would make this
check wait for an image rebuild.
"""

PREFLIGHT_SCRIPT = r"""
import ast
import importlib
import importlib.util
import json
import os
import sys

sys.path.insert(0, os.getcwd())
problems = []
# The package's own code runs here (imports, provider_config, the schema), and a
# sys.exit() in it ends this script before any PROBLEM line unless it is caught.


def problem(message):
    problems.append(message)
    print("PROBLEM: " + message, flush=True)


def guarded(node):
    for handler in node.handlers:
        names = ast.dump(handler.type) if handler.type is not None else "bare"
        if any(n in names for n in ("ImportError", "ModuleNotFoundError", "Exception", "bare")):
            return True
    return False


def imports(tree):
    found = []

    def visit(node):
        if isinstance(node, ast.Try) and guarded(node):
            for child in node.handlers + node.orelse + node.finalbody:
                visit(child)
            return
        if isinstance(node, ast.Import):
            found.extend((a.name, [], node.lineno) for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module, [a.name for a in node.names], node.lineno))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    return found


# Package folders that hold inputs and results, never the package's own code
# (the api's readiness check keeps the same list).
NOT_CODE_DIRS = {"sample_input", "output", "__pycache__", ".venv", "venv"}


def is_local(top):
    # A module the package ships itself: at its root, or one folder down. The
    # wizard's own layout imports schemas/output_schema.py after a
    # sys.path.insert(0, .../schemas) at module level, which this script does
    # not execute; the folder decides, not the path (UC03, 6 Oct 2026).
    def here(folder):
        return os.path.isfile(os.path.join(folder, top + ".py")) or os.path.isdir(os.path.join(folder, top))

    if here("."):
        return True
    try:
        entries = list(os.scandir("."))
    except OSError:
        return False
    return any(e.is_dir() and e.name not in NOT_CODE_DIRS and here(e.path) for e in entries)


source = ""
tree = None
try:
    with open("run_poc.py", encoding="utf-8") as fh:
        source = fh.read()
    tree = ast.parse(source)
except OSError as exc:
    problem("run_poc.py cannot be read (%s)" % exc)
except SyntaxError as exc:
    problem("run_poc.py does not parse (line %s: %s)" % (exc.lineno, exc.msg))

if tree is not None:
    seen = set()
    for module, names, line in imports(tree):
        top = module.split(".")[0]
        if top in sys.stdlib_module_names or is_local(top):
            continue
        try:
            mod = importlib.import_module(module)
        except (Exception, SystemExit) as exc:
            problem("run_poc.py line %d: import %s failed (%s: %s)" % (line, module, type(exc).__name__, exc))
            continue
        for name in names:
            if name == "*" or hasattr(mod, name) or (module, name) in seen:
                continue
            seen.add((module, name))
            try:
                importlib.import_module(module + "." + name)
            except (Exception, SystemExit):
                problem("run_poc.py line %d: %s has no name %s" % (line, module, name))

# The model config of every stage, built the way run_poc.py builds it.
if os.path.isfile("config.yaml") and os.path.isfile("provider_config.py"):
    try:
        import yaml
        import provider_config

        config = yaml.safe_load(open("config.yaml", encoding="utf-8")) or {}
        for stage in (config.get("stages") or {}):
            try:
                provider_config.get_stage_config(config, stage)
            except (Exception, SystemExit) as exc:
                problem("config.yaml stage %s: %s: %s" % (stage, type(exc).__name__, exc))
    except (Exception, SystemExit) as exc:
        problem("config.yaml / provider_config.py cannot be loaded (%s: %s)" % (type(exc).__name__, exc))

# The approved schema, loaded the way gaik's pipeline.load_schema does.
req_path = os.path.join("schemas", "output_schema_requirements.json")
schema_path = os.path.join("schemas", "output_schema.py")
if os.path.isfile(req_path):
    try:
        data = json.load(open(req_path, encoding="utf-8"))
        if data.get("requirements_type", "extraction") == "extraction":
            # A package whose run_poc.py resets non-string defaults loads the file
            # after that reset; one that does not, loads it as it is.
            if "_normalise_field_defaults" in source:
                def reset(node):
                    if isinstance(node, dict):
                        if "field_name" in node and node.get("default") is not None and not isinstance(node["default"], str):
                            node["default"] = None
                        for value in node.values():
                            reset(value)
                    elif isinstance(node, list):
                        for value in node:
                            reset(value)
                reset(data)
            from gaik.software_components.extractor import ExtractionRequirements
            ExtractionRequirements(**data["requirements"])
        if os.path.isfile(schema_path):
            spec = importlib.util.spec_from_file_location(data["model_name"], schema_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            getattr(module, data["model_name"])
    except (Exception, SystemExit) as exc:
        first = str(exc).strip().splitlines()
        problem("schema cannot be loaded (%s: %s)" % (type(exc).__name__, " ".join(first[:3])[:200]))

if problems:
    print("=== PREFLIGHT FAILED: %d problem(s) ===" % len(problems), flush=True)
    sys.exit(1)
print("=== PREFLIGHT OK ===", flush=True)
"""  # noqa: E501

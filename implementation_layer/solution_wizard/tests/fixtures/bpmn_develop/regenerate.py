"""Write the develop fixtures for test_bpmn_agent_report_steps.py.

For each shape in that test's ``DEVELOP_SHAPES``: ``<name>.json`` is the
blueprint, and ``<name>.bpmn`` is what the generator at the commit in
``DEVELOP_COMMIT`` draws from it. Run from implementation_layer/solution_wizard:

    python tests/fixtures/bpmn_develop/regenerate.py

with the repository's Python environment (the one the tests run in). The
generator is taken from that commit with ``git archive``, into a temporary
folder, and run in a separate process, so the drawing is develop's, not this
checkout's. Review the diagrams that change before committing them.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TESTS = HERE.parent.parent
SRC = "implementation_layer/solution_wizard/src"

DRAW = """
import json, sys
from pathlib import Path
from solution_wizard.blueprint import Blueprint
from solution_wizard.bpmn_generator import generate_bpmn
for path in sys.argv[1:]:
    bp = Blueprint.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    Path(path).with_suffix(".bpmn").write_text(generate_bpmn(bp), encoding="utf-8", newline="\\n")
"""


def main() -> None:
    commit = (HERE / "DEVELOP_COMMIT").read_text(encoding="utf-8").strip()
    sys.path.insert(0, str(TESTS))
    import test_bpmn_agent_report_steps as shapes

    paths = []
    for name, build in sorted(shapes.DEVELOP_SHAPES.items()):
        path = HERE / f"{name}.json"
        path.write_text(
            json.dumps(build(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
        )
        paths.append(str(path))

    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    ).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(
            ["git", "-C", root, "archive", "--format=tar", commit, SRC],
            capture_output=True,
            check=True,
        )
        subprocess.run(["tar", "-x", "-C", tmp], input=archive.stdout, check=True)
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-c",
                f"import sys; sys.path.insert(0, {str(Path(tmp) / SRC)!r})\n{DRAW}",
                *paths,
            ],
            check=True,
        )
    print(f"wrote {len(paths)} fixtures from {commit}")


if __name__ == "__main__":
    main()

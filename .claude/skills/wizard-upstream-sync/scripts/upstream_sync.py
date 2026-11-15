#!/usr/bin/env python3
"""Take upstream GAIK-project/gaik-toolkit changes into the Solution Wizard v2 fork
(NCF-public/gaik-toolkit-configuration-wizard-v2) as one checked pull request.

  plan       Read-only report (fetches first): the last sync, the upstream pull
             requests and commits since it, what each touches, gaik public-surface,
             extras and pin changes, a merge preview and a recommended target.
  prepare    A new worktree and branch from origin/develop; merges the target with a
             merge commit. Stops with the merge in progress when it conflicts.
  bump-pins  Sets ARG GAIK_VERSION in both images and the runner README; commits.
  checks     Runs uv sync, the gaik-sync audit, the tests and ruff in the worktree.
  pr-body    Renders the PR title, body and Slack note from the plan and the checks.

Python 3.11+, standard library only. The wizard clone is found from the current folder or
next to this checkout (--repo or WIZARD_REPO otherwise). Worktrees and reports go to
`.worktrees/<clone name>/` beside the clone, or to the folder set once per clone with
`git config upstream-sync.worktrees <dir>`; never into the repository. Examples:

  python upstream_sync.py plan
  python upstream_sync.py plan --base 24179260^1 --target v0.8.11   # replay a past sync
  python upstream_sync.py prepare --target v0.8.12
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

FORK_DIR = "gaik-toolkit-configuration-wizard-v2"
FORK_URL = re.compile(
    r"github\.com[:/]NCF-public/gaik-toolkit-configuration-wizard-v2(\.git)?/?$", re.I
)
WORKTREES_KEY = "upstream-sync.worktrees"
UPSTREAM_URL = "https://github.com/GAIK-project/gaik-toolkit.git"
UPSTREAM_SLUG = "GAIK-project/gaik-toolkit"
FORK_SLUG = "NCF-public/gaik-toolkit-configuration-wizard-v2"
FORK_OWNER = "NCF-public"
BASE_DEFAULT = "origin/develop"

PIN_FILE = "implementation_layer/solution_wizard/gaik_validated_version.txt"
DOCKERFILES = (
    "implementation_layer/wizard_api/Dockerfile",
    "implementation_layer/deploy/poc-runner/Dockerfile",
)
RUNNER_README = "implementation_layer/deploy/poc-runner/README.md"
REGISTRY = "implementation_layer/solution_wizard/registries/gaik_component_registry.json"
CARDS = "implementation_layer/solution_wizard/registries/component_reference_cards.json"
AUDIT = ".claude/skills/gaik-sync/scripts/audit_registry.py"
GAIK_SRC = "implementation_layer/src/gaik/"
UNIT_TESTS = "implementation_layer/unit_tests/"
# Tests the sync always runs: the agent plugin and no-code catalog quote gaik's API, and
# the fork's own VisionExtractor test covers its edit of a gaik file.
UNIT_TESTS_ALWAYS = (
    "test_agent_plugin.py",
    "test_no_code_catalog.py",
    "test_vision_strict_schema.py",
)
# The image tests in test_deploy_instances.py read the Dockerfiles only. The rest of that
# file and the other deploy-manifest tests run `bash deploy.sh`; on Windows Python finds
# WSL's bash in System32 first and they fail for that reason alone. CI's deploy-manifests
# job runs them on every sync PR, because the pin bump touches implementation_layer/deploy/.
IMAGE_TESTS = (f"{UNIT_TESTS}test_deploy_instances.py", "gaik or reportlab or pandas")

# Paths the fork owns. Upstream has none of them until wizard v2 is delivered there.
WIZARD_OWNED = (
    "implementation_layer/solution_wizard_v2/",
    "implementation_layer/wizard_api/",
    "implementation_layer/deploy/",
    "implementation_layer/WIZARD-DEV.md",
    "gaik-aiops/",
    "GITFLOW.md",
    ".github/workflows/solution-wizard-v2.yml",
    ".github/workflows/wizard-v2-",
    ".github/workflows/aiops.yml",
    ".github/security/",
    "implementation_layer/unit_tests/test_deploy_instances.py",
    "implementation_layer/unit_tests/test_sandbox_job_manifest.py",
    "implementation_layer/unit_tests/test_sandbox_network_policy.py",
    "implementation_layer/unit_tests/test_vision_strict_schema.py",
)

# (key, label, path prefixes, what it means for the wizard). First match wins.
CLASSES = (
    (
        "wizard-owned",
        "wizard v2 (fork-owned)",
        WIZARD_OWNED,
        "upstream changed a fork-owned path: read it, a conflict is likely",
    ),
    ("pin", "validated gaik pin", (PIN_FILE,), "the images must follow it (test_deploy_instances)"),
    (
        "wizard-assets",
        "wizard registry, cards, guidance",
        (
            "implementation_layer/solution_wizard/registries/",
            "implementation_layer/solution_wizard/SKILL.md",
            "implementation_layer/solution_wizard/CLAUDE.md",
            "implementation_layer/solution_wizard/schemas/",
        ),
        "the PoC generator reads these: audit after the merge",
    ),
    (
        "wizard-v1",
        "Solution Wizard code",
        ("implementation_layer/solution_wizard/",),
        "wizard_api imports it and the fork edits it too",
    ),
    (
        "gaik-src",
        "gaik library",
        (GAIK_SRC,),
        "reaches the images only through the PyPI version in GAIK_VERSION",
    ),
    (
        "packaging",
        "packaging and extras",
        ("pyproject.toml", "uv.lock", "MANIFEST.in"),
        "check the images' GAIK_EXTRAS",
    ),
    ("gaik-sync", "gaik-sync skill", (".claude/skills/gaik-sync/",), "the audit itself changed"),
    ("ci", "CI workflows", (".github/workflows/",), "the fork runs these workflows too"),
    (
        "repo-meta",
        "code owners, templates, security policy",
        (".github/", "SECURITY.md", "CODEOWNERS"),
        "the fork inherits it: keep it or drop it on purpose",
    ),
    (
        "agent-instructions",
        "agent instructions",
        ("AGENTS.md", "CLAUDE.md"),
        "the fork's agents read it too: check it still fits the fork",
    ),
    ("tests", "gaik tests", (UNIT_TESTS,), "rides along; the matching tests run"),
    (
        "agent-skills",
        "agent skills and no-code assets",
        ("implementation_layer/no-code-assets/", ".claude-plugin/", ".claude/"),
        "rides along",
    ),
    ("demo", "demo app", ("implementation_layer/toolkit_demo_app/",), "rides along"),
    ("other", "docs, evaluation, examples, other", ("",), "rides along"),
)
CLASS_LABEL = {key: label for key, label, _, _ in CLASSES}
CLASS_EFFECT = {key: effect for key, _, _, effect in CLASSES}
AFFECTS_WIZARD = (
    "wizard-owned",
    "pin",
    "wizard-assets",
    "wizard-v1",
    "gaik-src",
    "packaging",
    "gaik-sync",
    "ci",
    "repo-meta",
    "agent-instructions",
)
NEEDS_AUDIT = ("gaik-src", "packaging", "wizard-assets", "pin", "gaik-sync")

MERGE_PR = re.compile(r"^Merge pull request #(\d+) from ([\w.-]+)/(\S+)")
SQUASH_PR = re.compile(r"\(#(\d+)\)\s*$")
RELEASE_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
PUBLIC_DEF = re.compile(r"^[+-]\s*(async\s+)?def\s+(?!_)\w+\s*\(")
PUBLIC_CLASS = re.compile(r"^[+-]\s*class\s+(?!_)\w+")
EXPORT_LINE = re.compile(r"^[+-]\s*(__all__|from\s+\S+\s+import|import\s)")
PARAM_LINE = re.compile(r"^[+-]\s+(?!_)[a-z]\w*\s*:\s*[^=#]+?(\s*=\s*[^#]+)?,\s*$")
SECRET_ENV = re.compile(
    r"(_API_KEY|_KEY|_TOKEN|_SECRET|_PASSWORD|_CREDENTIALS)$"
    r"|^(AZURE|OPENAI|ANTHROPIC|GOOGLE|GEMINI|AITTA|TYPESAFE|LANGFUSE|SUPABASE)_",
    re.I,
)
LOCAL_PATH = re.compile(
    r"(?i)([a-z]:[\\/]+users[\\/]|/c/users/|/home/[a-z0-9_.-]+/|/users/[a-z0-9_.-]+/"
    r"|appdata[\\/]|onedrive|\.agents[\\/]|\.claude[\\/]projects)"
)


# --------------------------------------------------------------------------- helpers


def run(cmd, cwd=None, check=True, timeout=None, env=None):
    proc = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd) if cwd else None,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        env=env,
    )
    if check and proc.returncode != 0:
        raise SystemExit(
            f"command failed ({proc.returncode}): {' '.join(map(str, cmd))}\n"
            f"{(proc.stderr or proc.stdout).strip()}"
        )
    return proc


def git(repo, *args, check=True):
    return run(["git", "-C", repo, *args], check=check).stdout


def rev(repo, ref):
    out = git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", check=False).strip()
    return out or None


def is_ancestor(repo, a, b):
    return (
        run(["git", "-C", repo, "merge-base", "--is-ancestor", a, b], check=False).returncode == 0
    )


def describe(repo, sha):
    out = git(repo, "describe", "--tags", "--match", "v[0-9]*", sha, check=False).strip()
    return out or None


def short(sha):
    return sha[:8] if sha else "-"


def show(repo, rev_, path):
    proc = run(["git", "-C", repo, "show", f"{rev_}:{path}"], check=False)
    return proc.stdout if proc.returncode == 0 else None


def commit_info(repo, sha):
    out = git(repo, "log", "-1", "--date=short", "--format=%H%x1f%ad%x1f%s", sha).strip()
    full, date, subject = out.split("\x1f", 2)
    return {"sha": full, "date": date, "subject": subject}


def classify(path, fork_added=frozenset()):
    if path in fork_added:
        return "wizard-owned"
    for key, _, prefixes, _ in CLASSES:
        if any(path.startswith(p) for p in prefixes):
            return key
    return "other"


def version_of(target):
    m = RELEASE_TAG.match(target or "")
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else None


def pypi_has(version):
    """True / False when PyPI answers, None when it cannot be reached."""
    url = f"https://pypi.org/pypi/gaik/{version}/json"
    req = urllib.request.Request(url, headers={"User-Agent": "wizard-upstream-sync"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as exc:
        return False if exc.code == 404 else None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def local_paths(text):
    return [line for line in text.splitlines() if LOCAL_PATH.search(line)]


def main_checkout(path):
    """The main working tree of the repository at `path`, also from a linked worktree."""
    proc = run(
        ["git", "-C", path, "rev-parse", "--path-format=absolute", "--git-common-dir"], check=False
    )
    return Path(proc.stdout.strip()).parent if proc.returncode == 0 else None


def is_fork(path):
    proc = run(["git", "-C", path, "remote", "get-url", "origin"], check=False)
    return proc.returncode == 0 and bool(FORK_URL.search(proc.stdout.strip()))


def find_repo(explicit=None):
    """The wizard v2 clone: --repo, WIZARD_REPO, the current repository or this script's when it
    is the fork, or a folder named like the fork next to either of them."""
    if explicit or os.environ.get("WIZARD_REPO"):
        return Path(explicit or os.environ["WIZARD_REPO"]).resolve()
    for start in (Path.cwd(), Path(__file__).resolve().parent):
        base = main_checkout(start)
        if not base:
            continue
        if is_fork(base):
            return base
        sibling = base.parent / FORK_DIR
        if sibling.is_dir() and is_fork(sibling):
            return sibling
    sys.exit("Cannot find the wizard v2 clone: pass --repo <path> or set WIZARD_REPO.")


def worktrees_root(repo):
    """`git config upstream-sync.worktrees` of the clone, else `.worktrees/<clone>` beside it."""
    main = main_checkout(repo) or Path(repo)
    configured = git(main, "config", "--get", WORKTREES_KEY, check=False).strip()
    if configured:
        return Path(os.path.expanduser(configured))
    return main.parent / ".worktrees" / main.name


def notes_dir(args, repo):
    return Path(args.notes) if args.notes else worktrees_root(repo) / "upstream-sync-notes"


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------------------------- fetch


def upstream_remote(repo):
    for line in git(repo, "remote", "-v").splitlines():
        parts = line.split()
        if (
            len(parts) == 3
            and parts[2] == "(fetch)"
            and re.search(r"github\.com[:/]GAIK-project/gaik-toolkit(\.git)?/?$", parts[1], re.I)
        ):
            return parts[0]
    return None


def ensure_upstream(repo, fetch_now=True):
    """Find or add the upstream remote (GITFLOW.md: `git remote add upstream ...`).

    The remote tracks main and the v* release tags only; setuptools-scm in this repo
    reads those tags (`git describe --match v*.*.*`) to give the in-repo gaik a version.
    """
    notes = []
    name = upstream_remote(repo)
    if not name:
        if not fetch_now:
            raise SystemExit("No upstream remote yet: run once without --no-fetch.")
        git(repo, "remote", "add", "-t", "main", "upstream", UPSTREAM_URL)
        git(repo, "config", "--add", "remote.upstream.fetch", "refs/tags/v*:refs/tags/v*")
        git(repo, "config", "remote.upstream.tagOpt", "--no-tags")
        # Changes to upstream go through its own clone; no fork branch is pushed there by mistake.
        git(repo, "remote", "set-url", "--push", "upstream", "no-push")
        name = "upstream"
        notes.append(f"added remote `upstream` ({UPSTREAM_URL}, main and v* tags)")
    if fetch_now:
        git(repo, "fetch", "--prune", "--quiet", "origin")
        git(
            repo,
            "fetch",
            "--quiet",
            name,
            f"+refs/heads/main:refs/remotes/{name}/main",
            "refs/tags/v*:refs/tags/v*",
        )
        notes.append("fetched origin and upstream (main, v* tags)")
    return name, notes


# --------------------------------------------------------------------------- analysis


def last_sync(repo, base, point):
    """The merge on `base` that brought in `point`, and the PR that landed it."""
    info = {
        "point": commit_info(repo, point),
        "describe": describe(repo, point),
        "merge": None,
        "pr": None,
        "pr_title": None,
        "pr_merged": None,
    }
    out = git(
        repo,
        "log",
        "--merges",
        "--ancestry-path",
        "--date=short",
        "--format=%H%x1f%P%x1f%ad%x1f%s",
        f"{point}..{base}",
    )
    merge = None
    for line in out.splitlines():
        sha, parents, date, subject = line.split("\x1f", 3)
        if point in parents.split()[1:]:
            merge = {"sha": sha, "date": date, "subject": subject}  # keep the oldest
    if not merge:
        return info
    info["merge"] = merge
    # The oldest commit on base's first-parent line that contains the merge is the PR
    # merge that landed it (or the merge itself). Containment only grows along the line.
    chain = git(repo, "rev-list", "--first-parent", "--reverse", f"{point}..{base}").split()
    lo, hi, found = 0, len(chain) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if is_ancestor(repo, merge["sha"], chain[mid]):
            found, hi = mid, mid - 1
        else:
            lo = mid + 1
    landing = chain[found] if found is not None else merge["sha"]
    body = git(repo, "log", "-1", "--date=short", "--format=%s%x1f%ad%x1f%b", landing)
    subject, date, rest = body.split("\x1f", 2)
    m = MERGE_PR.match(subject) or SQUASH_PR.search(subject)
    if m:
        info["pr"] = int(m.group(1))
        lines = [ln.strip() for ln in rest.splitlines() if ln.strip()]
        info["pr_title"] = (
            lines[0] if MERGE_PR.match(subject) and lines else SQUASH_PR.sub("", subject).strip()
        )
        info["pr_merged"] = date
    return info


def entries_between(repo, start, end, fork_added, base):
    """First-parent entries of `end` after `start`, each with what it brought in."""
    fmt = "%x1e%H%x1f%an%x1f%ad%x1f%s%x1f%b%x1d"
    out = git(
        repo,
        "log",
        "--first-parent",
        "-m",
        "--name-only",
        "--date=short",
        f"--format={fmt}",
        f"{start}..{end}",
    )
    entries = []
    for chunk in out.split("\x1e")[1:]:
        head, _, files_part = chunk.partition("\x1d")
        sha, author, date, subject, body = head.split("\x1f", 4)
        files = sorted({f.strip() for f in files_part.splitlines() if f.strip()})
        classes = Counter(classify(f, fork_added) for f in files)
        m = MERGE_PR.match(subject)
        entry = {
            "sha": sha,
            "date": date,
            "author": author,
            "subject": subject,
            "title": subject,
            "pr": None,
            "from": None,
            "branch": None,
            "kind": "commit",
            "files": files,
            "classes": dict(classes),
        }
        if m:
            lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
            entry.update(
                pr=int(m.group(1)),
                title=lines[0] if lines else subject,
                kind="pr",
                **{"from": m.group(2)},
                branch=m.group(3),
            )
        elif SQUASH_PR.search(subject):
            entry.update(
                pr=int(SQUASH_PR.search(subject).group(1)),
                kind="pr",
                title=SQUASH_PR.sub("", subject).strip(),
            )
        elif subject.startswith("chore(release)"):
            entry["kind"] = "release"
        entry["affects_wizard"] = any(c in AFFECTS_WIZARD for c in classes)
        entry["commits"] = (
            int(git(repo, "rev-list", "--count", f"{sha}^1..{sha}").strip() or 1)
            if entry["kind"] == "pr"
            else 1
        )
        if entry["from"] == FORK_OWNER and entry["branch"]:
            fork_ref = f"refs/remotes/origin/{entry['branch']}"
            if rev(repo, fork_ref):
                entry["fork_branch_in_base"] = is_ancestor(repo, fork_ref, base)
        entries.append(entry)
    return entries


def surface(repo, start, end):
    """Heuristic: which gaik source changes may alter the public surface."""
    files = {}
    for line in git(repo, "diff", "--name-status", "-M", start, end, "--", GAIK_SRC).splitlines():
        parts = line.split("\t")
        status, path = parts[0], parts[-1]
        reasons = files.setdefault(path, set())
        if path.endswith(".md") or "/tests/" in path:
            continue
        if status.startswith("A"):
            reasons.add("new file")
        elif status.startswith("D"):
            reasons.add("removed file")
        elif status.startswith("R"):
            reasons.add(f"renamed from {parts[1]}")
    current = None
    for line in git(repo, "diff", "-U0", "--no-color", start, end, "--", GAIK_SRC).splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", line)
            current = m.group(2) if m else None
            continue
        if line.startswith(("+++", "---")) or not current or line[:1] not in "+-":
            continue
        reasons = files.setdefault(current, set())
        if current.endswith((".md", "/prompts.py")) or "/tests/" in current:
            continue  # docs, prompt text and tests do not change what callers see
        if PUBLIC_DEF.match(line):
            reasons.add("public def")
        elif PUBLIC_CLASS.match(line):
            reasons.add("public class")
        elif EXPORT_LINE.match(line) and current.endswith("__init__.py"):
            reasons.add("exports")
        elif PARAM_LINE.match(line):
            reasons.add("typed parameter or field lines")
    surface_files = [{"path": p, "reasons": sorted(r)} for p, r in sorted(files.items()) if r]
    internal = sorted(p for p, r in files.items() if not r)
    components = sorted(
        {
            m.group(2)
            for p in files
            if (
                m := re.match(
                    rf"{re.escape(GAIK_SRC)}(software_components|software_modules)/([^/]+)/", p
                )
            )
        }
    )
    return surface_files, internal, components


def extras(repo, rev_):
    text = show(repo, rev_, "pyproject.toml")
    if not text:
        return {}, []
    project = tomllib.loads(text).get("project", {})
    return project.get("optional-dependencies", {}), project.get("dependencies", [])


def registry_ids(repo, rev_):
    text = show(repo, rev_, REGISTRY)
    if not text:
        return {}
    data = json.loads(text)
    items = data if isinstance(data, list) else data.get("components", [])
    return {item.get("id") or item.get("name"): item for item in items}


def cards(repo, rev_):
    text = show(repo, rev_, CARDS)
    return json.loads(text) if text else {}


def arg_value(text, name):
    m = re.search(rf'(?m)^ARG {name}="?([^"\r\n]*?)"?[ \t]*\r?$', text or "")
    return m.group(1) if m else None


def pins(repo, base, target, target_version, offline):
    result = {
        "validated_base": (show(repo, base, PIN_FILE) or "").strip() or None,
        "validated_target": (show(repo, target, PIN_FILE) or "").strip() or None,
        "images": {},
        "readme_base": None,
        "extras_missing": [],
        "new_extras_not_in_images": [],
        "pypi": None,
    }
    image_extras = set()
    for rel in DOCKERFILES:
        text = show(repo, base, rel)
        result["images"][rel] = {
            "version": arg_value(text, "GAIK_VERSION"),
            "extras": arg_value(text, "GAIK_EXTRAS"),
        }
        image_extras |= set(filter(None, (arg_value(text, "GAIK_EXTRAS") or "").split(",")))
    m = re.search(r"currently (\d+\.\d+\.\d+) from", show(repo, base, RUNNER_README) or "")
    result["readme_base"] = m.group(1) if m else None
    target_extras, _ = extras(repo, target)
    result["extras_missing"] = sorted(
        e for e in image_extras if target_extras and e not in target_extras
    )
    version = target_version or result["validated_target"]
    result["version"] = version
    if version and not offline:
        result["pypi"] = pypi_has(version)
    return result, image_extras


def open_upstream_prs(fork_added):
    if not shutil.which("gh"):
        return None
    proc = run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            UPSTREAM_SLUG,
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,title,author,headRepositoryOwner,headRefName,files,isDraft",
        ],
        check=False,
        timeout=60,
    )
    if proc.returncode != 0:
        return None
    prs = []
    for pr in json.loads(proc.stdout or "[]"):
        files = [f["path"] for f in pr.get("files") or []]
        classes = Counter(classify(f, fork_added) for f in files)
        prs.append(
            {
                "pr": pr["number"],
                "title": pr["title"],
                "author": pr["author"]["login"],
                "from": (pr.get("headRepositoryOwner") or {}).get("login"),
                "branch": pr["headRefName"],
                "draft": pr["isDraft"],
                "classes": dict(classes),
                "affects_wizard": any(c in AFFECTS_WIZARD for c in classes),
            }
        )
    return prs


def build_plan(args):
    repo = find_repo(args.repo)
    remote, notes = ensure_upstream(repo, fetch_now=not args.no_fetch)
    base_sha = rev(repo, args.base) or sys.exit(f"cannot resolve base {args.base}")
    main_ref = f"refs/remotes/{remote}/main"
    main_sha = rev(repo, main_ref) or sys.exit(f"cannot resolve {main_ref}")
    tags = [
        t
        for t in git(repo, "tag", "--merged", main_sha, "-l", "v*", "--sort=-v:refname").split()
        if RELEASE_TAG.match(t)
    ]
    latest = tags[0] if tags else None
    if args.target in (None, "release"):
        target = latest
    elif args.target == "main":
        target = main_ref
    else:
        target = args.target
    target_sha = rev(repo, target) if target else None
    if target and not target_sha:
        sys.exit(f"cannot resolve target {target}")

    point = git(repo, "merge-base", base_sha, main_sha).strip()
    sync = last_sync(repo, base_sha, point)
    plan = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "repo": str(repo),
        "notes": notes,
        "remote": remote,
        "base": {"ref": args.base, **commit_info(repo, base_sha)},
        "upstream_main": {
            "ref": f"{remote}/main",
            **commit_info(repo, main_sha),
            "describe": describe(repo, main_sha),
        },
        "latest_release": latest,
        "last_sync": sync,
        "main_synced": is_ancestor(repo, main_sha, base_sha),
        "target": None,
        "entries": [],
        "unreleased": [],
        "open_prs": None,
    }
    fork_changed = set(git(repo, "diff", "--name-only", point, base_sha).split("\n")) - {""}
    fork_added = frozenset(
        git(repo, "diff", "--name-only", "--diff-filter=A", point, base_sha).split("\n")
    ) - {""}
    fork_edits = sorted(f for f in fork_changed - fork_added if classify(f) != "wizard-owned")
    plan["fork_edits"] = {
        "files": fork_edits,
        "gaik_src": [f for f in fork_edits if f.startswith(GAIK_SRC)],
    }

    if target_sha:
        version = version_of(target) or (show(repo, target_sha, PIN_FILE) or "").strip() or None
        synced = is_ancestor(repo, target_sha, base_sha)
        plan["target"] = {
            "ref": target,
            **commit_info(repo, target_sha),
            "version": version,
            "synced": synced,
            "describe": describe(repo, target_sha),
            "commit_count": 0
            if synced
            else int(git(repo, "rev-list", "--count", f"{base_sha}..{target_sha}").strip()),
        }
        if not synced:
            start = git(repo, "merge-base", base_sha, target_sha).strip()
            plan["entries"] = entries_between(repo, start, target_sha, fork_added, base_sha)
            up_changed = set(git(repo, "diff", "--name-only", start, target_sha).split("\n")) - {""}
            surface_files, internal, components = surface(repo, start, target_sha)
            ex_start, deps_start = extras(repo, start)
            ex_target, deps_target = extras(repo, target_sha)
            reg_start, reg_target = registry_ids(repo, start), registry_ids(repo, target_sha)
            cards_start, cards_target = cards(repo, start), cards(repo, target_sha)
            pin_info, image_extras = pins(repo, base_sha, target_sha, version, args.offline)
            new_components = sorted(set(reg_target) - set(reg_start))
            pin_info["new_extras_not_in_images"] = sorted(
                {
                    f"{cid}: {reg_target[cid].get('install_extra')}"
                    for cid in new_components
                    if reg_target[cid].get("install_extra")
                    and reg_target[cid]["install_extra"] not in image_extras
                }
            )
            conflicts = predict_conflicts(repo, base_sha, target_sha)
            classes = Counter(classify(f, fork_added) for f in up_changed)
            tests = sorted(
                f"{UNIT_TESTS}test_{name}.py"
                for name in components
                if show(repo, target_sha, f"{UNIT_TESTS}test_{name}.py") is not None
            )
            plan.update(
                {
                    "changed_files": len(up_changed),
                    "classes": dict(classes),
                    "surface": {
                        "files": surface_files,
                        "internal": internal,
                        "components": components,
                    },
                    "extras_change": {
                        "added": sorted(set(ex_target) - set(ex_start)),
                        "removed": sorted(set(ex_start) - set(ex_target)),
                        "changed": sorted(
                            k for k in set(ex_start) & set(ex_target) if ex_start[k] != ex_target[k]
                        ),
                        "dependencies_changed": deps_start != deps_target,
                    },
                    "registry_change": {
                        "added": new_components,
                        "removed": sorted(set(reg_start) - set(reg_target)),
                        "changed": sorted(
                            k
                            for k in set(reg_start) & set(reg_target)
                            if reg_start[k] != reg_target[k]
                        ),
                    },
                    "cards_change": {
                        "added": sorted(set(cards_target) - set(cards_start)),
                        "removed": sorted(set(cards_start) - set(cards_target)),
                        "changed": sorted(
                            k
                            for k in set(cards_start) & set(cards_target)
                            if cards_start[k] != cards_target[k]
                        ),
                    },
                    "pins": pin_info,
                    "conflicts": conflicts,
                    "both_changed": sorted(set(fork_edits) & up_changed),
                    "upstream_touched_fork_owned": sorted(
                        f for f in up_changed if classify(f, fork_added) == "wizard-owned"
                    ),
                    "tests_for_changed": tests,
                }
            )
            surface_paths = {f["path"] for f in surface_files}
            for e in plan["entries"]:
                e["surface"] = sorted(set(e["files"]) & surface_paths)
                e["pin_change"] = PIN_FILE in e["files"]
            reasons = [CLASS_LABEL[c] for c in NEEDS_AUDIT if classes.get(c)]
            plan["audit"] = {"needed": bool(reasons), "reasons": reasons}
    if not plan["main_synced"] and target_sha and not is_ancestor(repo, main_sha, target_sha):
        plan["unreleased"] = entries_between(repo, target_sha, main_sha, fork_added, base_sha)
    if not args.no_gh:
        plan["open_prs"] = open_upstream_prs(fork_added)
    plan["recommendation"] = recommend(plan)
    return plan


def predict_conflicts(repo, base, target):
    proc = run(
        [
            "git",
            "-C",
            repo,
            "merge-tree",
            "--write-tree",
            "--name-only",
            "--no-messages",
            base,
            target,
        ],
        check=False,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    if proc.returncode == 0:
        return {"clean": True, "files": []}
    if proc.returncode == 1:
        return {"clean": False, "files": lines[1:]}
    return {"clean": None, "files": [], "error": (proc.stderr or proc.stdout).strip()}


def recommend(plan):
    target = plan.get("target")
    rec = {"action": "none", "lines": []}
    if not target:
        rec["lines"].append("Upstream main has no release tag: nothing to recommend.")
        return rec
    if target["synced"]:
        if plan["main_synced"]:
            rec["lines"].append(
                f"Nothing to move: develop already has upstream main "
                f"({short(plan['upstream_main']['sha'])}, {plan['upstream_main']['describe']})."
            )
        else:
            waiting = plan["unreleased"]
            touching = [e for e in waiting if e["affects_wizard"]]
            rec["lines"].append(
                f"No release since {target['ref']}. Upstream main is {len(waiting)} entries ahead, "
                f"{len(touching)} of them touching what the wizard uses."
            )
            rec["lines"].append(
                "Wait for the next release; take main (--target main) only for changes that do not "
                "touch the gaik library, extras or wizard assets, since the images install a PyPI release."
            )
        return rec
    version = target["version"]
    rec["action"] = "sync"
    pin = plan["pins"]
    rec["lines"].append(
        f"Take {target['ref']} into develop on branch chore/gaik-{version}: "
        f"{len(plan['entries'])} upstream entries, {target['commit_count']} commits."
    )
    if pin["pypi"] is False:
        rec["action"] = "wait"
        rec["lines"].append(
            f"gaik {version} is not on PyPI yet: the images cannot install it. Wait."
        )
    elif pin["pypi"] is None:
        rec["lines"].append(
            f"PyPI not checked or unreachable: confirm gaik {version} is published."
        )
    if pin["validated_target"] and pin["validated_target"] != version:
        rec["lines"].append(
            f"The validated pin at the target is {pin['validated_target']}, not {version}: ask the user."
        )
    if plan["audit"]["needed"]:
        rec["lines"].append(
            "Run the gaik-sync audit after the merge: upstream changed "
            + ", ".join(plan["audit"]["reasons"])
            + "."
        )
    if plan["conflicts"]["clean"] is False:
        rec["lines"].append(
            f"Expect {len(plan['conflicts']['files'])} conflicted files; "
            "resolve them by the rules in references/conflicts.md."
        )
    if plan["upstream_touched_fork_owned"]:
        rec["lines"].append("Upstream changed fork-owned paths: read those diffs before merging.")
    inherits = [
        CLASS_LABEL[c] for c in ("repo-meta", "agent-instructions") if plan["classes"].get(c)
    ]
    if inherits:
        rec["lines"].append(
            "The fork inherits upstream's "
            + " and ".join(inherits)
            + ": keep or drop them on purpose."
        )
    if pin["extras_missing"] or pin["new_extras_not_in_images"]:
        rec["lines"].append("Check GAIK_EXTRAS in both Dockerfiles (see Pins).")
    if plan["unreleased"]:
        rec["lines"].append(
            f"{len(plan['unreleased'])} newer upstream entries stay for a later sync."
        )
    return rec


# --------------------------------------------------------------------------- report


def entry_ref(e):
    return f"{UPSTREAM_SLUG}#{e['pr']}" if e.get("pr") else short(e["sha"])


def entry_classes(e):
    order = [k for k, *_ in CLASSES]
    return ", ".join(CLASS_LABEL[c] for c in sorted(e["classes"], key=order.index))


def rider_summary(riders):
    """'66 entries: demo app 40, docs, evaluation, examples, other 20, ...'"""
    counts = Counter()
    for e in riders:
        main = max(e["classes"], key=e["classes"].get) if e["classes"] else "other"
        counts[main] += 1
    return (
        f"{len(riders)} entries ("
        + ", ".join(f"{CLASS_LABEL[k]} {n}" for k, n in counts.most_common())
        + ")"
    )


def entry_effect(e):
    parts = []
    if e.get("surface"):
        parts.append(f"**public surface?** ({len(e['surface'])} gaik files): audit")
    for c in AFFECTS_WIZARD:
        if c in e["classes"]:
            parts.append(f"**pin**: {CLASS_EFFECT[c]}" if c == "pin" else CLASS_EFFECT[c])
    return "; ".join(parts) or "rides along"


def render_plan(plan):
    out = []
    add = out.append
    base, main = plan["base"], plan["upstream_main"]
    add(f"# Upstream sync plan ({plan['generated'][:16].replace('T', ' ')})\n")
    for note in plan["notes"]:
        add(f"- {note}")
    add(f"- Fork: `{base['ref']}` {short(base['sha'])} ({base['date']}) {base['subject']}")
    add(
        f"- Upstream: `{main['ref']}` {short(main['sha'])} ({main['date']}, {main['describe']}); "
        f"latest release {plan['latest_release']}"
    )
    sync = plan["last_sync"]
    point = sync["point"]
    line = f"- Last sync point: {short(point['sha'])} ({sync['describe']}, {point['date']})"
    if sync["merge"]:
        line += f', merged by {short(sync["merge"]["sha"])} "{sync["merge"]["subject"]}"'
    if sync["pr"]:
        line += f' in {FORK_SLUG}#{sync["pr"]} "{sync["pr_title"]}" ({sync["pr_merged"]})'
    add(line + "\n")

    target = plan["target"]
    if target and not target["synced"]:
        add(
            f"## What would move: {sync['describe']} -> {target['ref']} "
            f"({len(plan['entries'])} entries, {target['commit_count']} commits, "
            f"{plan['changed_files']} files)\n"
        )
        add("| Upstream | Date | Title | Touches | For the wizard |")
        add("|---|---|---|---|---|")
        riders = []
        for e in plan["entries"]:
            title = e["title"].replace("|", "/")
            if e.get("from") == FORK_OWNER:
                title += (
                    " (NCF fork PR"
                    + (", already in develop" if e.get("fork_branch_in_base") else "")
                    + ")"
                )
            if e["affects_wizard"] or e["kind"] == "release":
                add(
                    f"| {entry_ref(e)} | {e['date']} | {title} | {entry_classes(e)} | {entry_effect(e)} |"
                )
            else:
                riders.append(e)
        if riders:
            add(
                f"\nRides along without effect on the wizard: {rider_summary(riders)}. "
                + "; ".join(f"{entry_ref(e)} {e['title']}" for e in riders[:6])
                + (f"; and {len(riders) - 6} more (plan JSON)" if len(riders) > 6 else "")
            )
        add("")
        s = plan["surface"]
        add("## gaik public surface\n")
        if s["files"]:
            add("May change the public surface (heuristic; the gaik-sync audit decides):")
            for f in s["files"]:
                add(f"- `{f['path']}`: {', '.join(f['reasons'])}")
        else:
            add("No gaik source change looks like a public-surface change.")
        if s["internal"]:
            add(f"Internal gaik changes: {', '.join('`' + p + '`' for p in s['internal'])}")
        ec, rc, cc = plan["extras_change"], plan["registry_change"], plan["cards_change"]
        for label, change in (("Extras", ec), ("Registry components", rc), ("Reference cards", cc)):
            parts = [f"{k}: {', '.join(v)}" for k, v in change.items() if isinstance(v, list) and v]
            if parts:
                add(f"- {label}: " + "; ".join(parts))
        if ec.get("dependencies_changed"):
            add("- gaik's base dependencies changed.")
        audit = plan["audit"]
        add(
            f"\nAudit: {'needed after the merge (' + ', '.join(audit['reasons']) + ')' if audit['needed'] else 'not required; run it anyway if unsure'}.\n"
        )

        p = plan["pins"]
        add("## Pins\n")
        add("| Pin | develop | target |")
        add("|---|---|---|")
        add(f"| `gaik_validated_version.txt` | {p['validated_base']} | {p['validated_target']} |")
        for rel, info in p["images"].items():
            add(f"| `{rel}` ARG GAIK_VERSION | {info['version']} | bump to {p['version']} |")
        add(f'| runner README "currently" | {p["readme_base"]} | {p["version"]} |')
        pypi = {True: "published", False: "NOT on PyPI", None: "not checked"}[p["pypi"]]
        add(f"\nPyPI gaik {p['version']}: {pypi}.")
        if p["extras_missing"]:
            add(
                f"GAIK_EXTRAS entries the target no longer defines: {', '.join(p['extras_missing'])}."
            )
        if p["new_extras_not_in_images"]:
            add(
                f"New components whose extra the images do not install: {', '.join(p['new_extras_not_in_images'])}."
            )
        add("")
        c = plan["conflicts"]
        add("## Merge preview\n")
        if c["clean"]:
            add("`git merge-tree`: merges cleanly.")
        elif c["clean"] is False:
            add("`git merge-tree`: conflicts in " + ", ".join(f"`{f}`" for f in c["files"]) + ".")
        else:
            add(f"`git merge-tree` failed: {c.get('error')}")
        if plan["both_changed"]:
            add("Changed on both sides: " + ", ".join(f"`{f}`" for f in plan["both_changed"]) + ".")
        if plan["upstream_touched_fork_owned"]:
            add(
                "Upstream touched fork-owned paths: "
                + ", ".join(f"`{f}`" for f in plan["upstream_touched_fork_owned"])
                + "."
            )
        if plan["tests_for_changed"]:
            add(
                "Tests for the changed components: "
                + ", ".join(f"`{t}`" for t in plan["tests_for_changed"])
                + "."
            )
        add("")
    elif target:
        add(
            f"## Nothing to move\n\ndevelop already contains {target['ref']} ({short(target['sha'])}).\n"
        )

    fe = plan["fork_edits"]
    add("## Fork edits to upstream files\n")
    add(
        f"{len(fe['files'])} upstream files differ on the fork's side since the last sync point; "
        "these are where conflicts come from."
    )
    if fe["gaik_src"]:
        add(
            "gaik library files the fork edits (the images install the PyPI release without these): "
            + ", ".join(f"`{f}`" for f in fe["gaik_src"])
            + "."
        )
    add("")
    if plan["unreleased"]:
        add(
            f"## Not in a release yet ({len(plan['unreleased'])} entries after {target['ref'] if target else '-'})\n"
        )
        for e in plan["unreleased"]:
            add(
                f"- {entry_ref(e)} {e['date']} {e['title']} [{entry_classes(e)}]"
                + (" (touches the wizard's inputs)" if e["affects_wizard"] else "")
            )
        add("")
    if plan["open_prs"] is not None:
        prs = plan["open_prs"]
        add(f"## Coming later: {len(prs)} open upstream PRs\n")
        for pr in prs:
            who = pr["from"] if pr["from"] != "GAIK-project" else "upstream"
            add(
                f"- {UPSTREAM_SLUG}#{pr['pr']} {pr['title']} ({who}{', draft' if pr['draft'] else ''}) "
                f"[{', '.join(CLASS_LABEL[c] for c in pr['classes'])}]"
            )
        add("")
    add("## Recommendation\n")
    for line in plan["recommendation"]["lines"]:
        add(f"- {line}")
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- commands


def cmd_plan(args):
    plan = build_plan(args)
    name = (plan["target"] or {}).get("version") or "none"
    if plan["target"] and plan["target"]["synced"]:
        name = f"{name}-synced"
    out_dir = notes_dir(args, Path(plan["repo"]))
    json_path = write(out_dir / f"plan-{name}.json", json.dumps(plan, indent=2, ensure_ascii=False))
    md = render_plan(plan)
    md_path = write(out_dir / f"plan-{name}.md", md)
    print(md)
    print(f"(plan saved: {md_path} and {json_path.name})")
    return 0


def cmd_prepare(args):
    repo = find_repo(args.repo)
    target = args.target
    if target == "main":
        target = f"refs/remotes/{upstream_remote(repo) or 'upstream'}/main"
    target_sha = rev(repo, target) or sys.exit(f"cannot resolve {args.target}: run plan first")
    version = version_of(args.target)
    if version:
        label, default_branch = args.target, f"chore/gaik-{version}"
    else:  # an unreleased upstream commit, as in "Merge upstream main (54218f5d) ..."
        label = f"main ({short(target_sha)})"
        default_branch = f"chore/upstream-sync-{datetime.now():%Y-%m-%d}"
    branch = args.branch or default_branch
    wt = Path(args.worktree) if args.worktree else worktrees_root(repo) / branch.split("/", 1)[-1]
    if wt.exists():
        sys.exit(f"{wt} exists already; continue there or pick --worktree")
    if rev(repo, f"refs/heads/{branch}") or rev(repo, f"refs/remotes/origin/{branch}"):
        sys.exit(f"branch {branch} exists already; pick --branch")
    git(repo, "worktree", "add", "--quiet", "-b", branch, wt, args.base)
    print(f"worktree {wt} on {branch} from {args.base}")
    message = f"Merge upstream gaik-toolkit {label} into develop"
    proc = run(["git", "-C", wt, "merge", "--no-ff", "-m", message, target_sha], check=False)
    if proc.returncode == 0:
        print(f"merged {args.target} cleanly: {git(wt, 'log', '-1', '--format=%h %s').strip()}")
        return 0
    conflicted = git(wt, "diff", "--name-only", "--diff-filter=U").split()
    print(f"merge of {args.target} stopped with {len(conflicted)} conflicted files:")
    for f in conflicted:
        print(f"  {f}  [{CLASS_LABEL[classify(f)]}]")
    print(
        "Resolve them by references/conflicts.md, then `git add` and `git commit` with a "
        "'Conflicts:' paragraph in the message."
    )
    return 2


def cmd_bump_pins(args):
    wt = Path(args.worktree)
    version = args.version or (wt / PIN_FILE).read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        sys.exit(f"not a release version: {version}")
    changed = []
    edits = [
        (rel, r"(?m)^(ARG GAIK_VERSION=)\S+?(?=[ \t]*\r?$)", rf"\g<1>{version}")
        for rel in DOCKERFILES
    ]
    edits.append((RUNNER_README, r"(currently )\d+\.\d+\.\d+( from)", rf"\g<1>{version}\g<2>"))
    for rel, pattern, repl in edits:
        path = wt / rel
        text = path.read_bytes().decode("utf-8")
        new, n = re.subn(pattern, repl, text)
        if n != 1:
            sys.exit(f"{rel}: expected one pin, found {n}; edit it by hand")
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            changed.append(rel)
    if not changed:
        print(f"images already pin gaik {version}")
        return 0
    print("updated: " + ", ".join(changed))
    if args.commit:
        git(wt, "add", "--", *changed)
        git(
            wt,
            "commit",
            "--quiet",
            "-m",
            f"chore(images): install gaik {version} in the api and runner images",
        )
        print(git(wt, "log", "-1", "--format=%h %s").strip())
    return 0


def pytest_summary(text):
    """The counts on pytest's last summary line, e.g. '329 passed, 2 skipped'."""
    lines = text.strip().splitlines()
    for line in reversed(lines):
        parts = re.findall(
            r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected)\b", line
        )
        if parts:
            return ", ".join(f"{n} {k}" for n, k in parts)
    return lines[-1] if lines else ""


def sync_merge(wt, base):
    out = git(wt, "log", "--merges", "--first-parent", "--format=%H%x1f%P%x1f%s", f"{base}..HEAD")
    for line in out.splitlines():
        sha, parents, subject = line.split("\x1f", 2)
        if subject.startswith("Merge upstream gaik-toolkit"):
            return sha, parents.split()[1]
    return None, None


# The check steps that run in the environment `uv sync` builds.
NEEDS_ENV = ("audit", "solution-wizard", "image-pins", "unit-tests", "wizard-api")


def cmd_checks(args):
    wt = Path(args.worktree).resolve()
    out_dir = notes_dir(args, wt)
    logs = out_dir / f"logs-{wt.name}"
    logs.mkdir(parents=True, exist_ok=True)
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if args.plan else {}
    unit = [f"{UNIT_TESTS}{t}" for t in UNIT_TESTS_ALWAYS] + plan.get("tests_for_changed", [])
    unit = sorted({t for t in unit if (wt / t).exists()})
    # Like CI: no provider keys or tokens, so no test can make a paid or live call.
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    env.update(PYTHONUTF8="1", WIZARD_SESSION_OUTPUT_ROOT=str(logs / "wizard-sessions"))
    api = "implementation_layer/wizard_api"
    base = plan.get("base", {}).get("ref", BASE_DEFAULT)
    # ruff on the Python files this PR changes: upstream's CI formatted its own files, and
    # the fork's older unformatted files are not this sync's business.
    changed_py = [
        f
        for f in git(
            wt, "diff", "--name-only", "--diff-filter=AMR", base, "HEAD", "--", "*.py"
        ).split()
        if f.startswith("implementation_layer/")
    ]
    skips = {}
    if os.name == "nt" and "import fcntl" in "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in (wt / api / "wizard_api").rglob("*.py")
    ):
        skips["wizard-api"] = (
            "not run locally on Windows (wizard_api imports fcntl); CI's wizard-api job runs it with Postgres",
            "with Docker Desktop running: bash scripts/docker-test.sh --step api in implementation_layer/wizard_api",
        )
    if not changed_py:
        skips["ruff-format"] = ("no Python files changed by this PR", "")
    steps = [
        # A fixed Python: left to uv, a machine's newest interpreter is used, and an extra
        # without a wheel for it yet is then built from source or fails.
        (
            "uv-sync",
            f"uv sync --all-extras (Python {args.python})",
            ["uv", "sync", "--all-extras", "--python", args.python],
            ".",
            2400,
        ),
        ("audit", "gaik-sync audit", ["uv", "run", "python", AUDIT, "--json"], ".", 900),
        # -m "not llm": tests marked llm make real, paid API calls (as in upstream's CI).
        (
            "solution-wizard",
            "solution_wizard tests",
            [
                "uv",
                "run",
                "python",
                "-m",
                "pytest",
                "implementation_layer/solution_wizard/tests",
                "-q",
                "-m",
                "not llm",
                "-p",
                "no:cacheprovider",
            ],
            ".",
            2400,
        ),
        (
            "image-pins",
            "image pin tests (test_deploy_instances, Dockerfile part)",
            [
                "uv",
                "run",
                "python",
                "-m",
                "pytest",
                IMAGE_TESTS[0],
                "-k",
                IMAGE_TESTS[1],
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            ".",
            600,
        ),
        (
            "unit-tests",
            "unit tests: " + ", ".join(Path(t).stem for t in unit),
            [
                "uv",
                "run",
                "python",
                "-m",
                "pytest",
                *unit,
                "-q",
                "-m",
                "not llm",
                "-p",
                "no:cacheprovider",
            ],
            ".",
            2400,
        ),
        (
            "wizard-api",
            "wizard_api tests",
            [
                "uv",
                "run",
                "--no-project",
                "--with-editable",
                ".",
                "--with-editable",
                "../solution_wizard",
                "--with",
                "pytest",
                "--with",
                "httpx",
                "python",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            api,
            2400,
        ),
        (
            "ruff-format",
            f"ruff format --check on the {len(changed_py)} Python files this PR changes",
            ["uvx", "ruff@0.14.10", "format", "--check", *changed_py],
            ".",
            600,
        ),
        (
            "ruff-check",
            "ruff check implementation_layer/wizard_api/",
            ["uvx", "ruff@0.14.10", "check", f"{api}/"],
            ".",
            600,
        ),
    ]
    only = set(args.only.split(",")) if args.only else None
    results = []
    for key, label, cmd, cwd, timeout in steps:
        if only and key not in only:
            continue
        if key in NEEDS_ENV and any(
            r["key"] == "uv-sync" and r["status"] != "pass" for r in results
        ):
            # Without the environment the audit reports components as removed and the
            # tests fail on a missing pytest: neither says anything about the sync.
            res = {
                "key": key,
                "label": label,
                "command": " ".join(cmd),
                "cwd": cwd,
                "status": "error",
                "summary": "not run: uv sync failed, so the environment is incomplete",
                "seconds": 0,
            }
            results.append(res)
            print(f"[{datetime.now():%H:%M:%S}] {label}: {res['summary']}", flush=True)
            continue
        if (args.skip_sync and key == "uv-sync") or (key == "unit-tests" and not unit):
            continue
        if key in skips:
            summary, hint = skips[key]
            results.append(
                {
                    "key": key,
                    "label": label,
                    "command": " ".join(cmd),
                    "cwd": cwd,
                    "status": "skip",
                    "summary": summary,
                    "hint": hint,
                    "seconds": 0,
                }
            )
            print(
                f"[{datetime.now():%H:%M:%S}] {label}: skipped, {summary}"
                + (f"; {hint}" if hint else ""),
                flush=True,
            )
            continue
        print(f"[{datetime.now():%H:%M:%S}] {label} ...", flush=True)
        started = time.time()
        try:
            proc = run(cmd, cwd=wt / cwd, check=False, timeout=timeout, env=env)
            code, output = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            code, output = -1, f"timed out after {timeout}s"
        log = write(logs / f"{key}.log", output)
        res = {
            "key": key,
            "label": label,
            "command": " ".join(cmd),
            "cwd": cwd,
            "code": code,
            "seconds": round(time.time() - started),
            "log": str(log),
        }
        if key == "audit":
            res.update(audit_result(output, code))
        elif key in ("solution-wizard", "image-pins", "unit-tests", "wizard-api"):
            res["summary"] = pytest_summary(output)
            res["status"] = "pass" if code == 0 else ("fail" if code in (1, 2) else "error")
            res["failed"] = re.findall(r"^FAILED (\S+)", output, re.M)[:20]
        else:
            res["status"] = "pass" if code == 0 else "fail"
            res["summary"] = output.strip().splitlines()[-1] if output.strip() else ""
        results.append(res)
        print(f"    {res['status']}: {res.get('summary', '')} ({res['seconds']} s)", flush=True)
    merge, target = sync_merge(wt, base)
    paths = []
    if merge:
        fork_commits = git(wt, "rev-list", "--no-merges", "HEAD", f"^{base}", f"^{target}").split()
        for sha in fork_commits + [merge]:
            diff = git(wt, "show", "--cc", "--format=", sha)
            paths += [
                f"{short(sha)}: {ln[:160]}"
                for ln in diff.splitlines()
                if ln.startswith("+") and not ln.startswith("+++") and LOCAL_PATH.search(ln)
            ]
    dirty = [
        ln for ln in git(wt, "status", "--porcelain", "--untracked-files=no").splitlines() if ln
    ]
    checks = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "worktree": str(wt),
        "branch": git(wt, "branch", "--show-current").strip(),
        "head": git(wt, "rev-parse", "HEAD").strip(),
        "merge": merge,
        "target": target,
        "steps": results,
        "local_paths": paths,
        "dirty_tracked": dirty,
    }
    path = write(
        out_dir / f"checks-{wt.name}.json", json.dumps(checks, indent=2, ensure_ascii=False)
    )
    print(
        f"local paths in the fork's commits: {len(paths)}; tracked files changed by the checks: {len(dirty)}"
    )
    print(f"(checks saved: {path})")
    return 0 if all(r["status"] in ("pass", "skip") for r in results) and not paths else 1


def audit_result(output, code):
    try:
        data = json.loads(output[output.index("{") : output.rindex("}") + 1])
    except ValueError:
        return {"status": "error", "summary": "audit printed no JSON"}
    cats = Counter(f["category"] for f in data.get("findings", []))
    actionable = {k: v for k, v in cats.items() if k != "version"}
    summary = (
        f"{data.get('registry_components')} components, {data.get('reference_cards')} cards; "
        + (", ".join(f"{v} {k}" for k, v in sorted(actionable.items())) or "no drift")
        + (
            f"; version note: installed {data.get('gaik_installed')}, validated {data.get('gaik_validated')}"
            if cats.get("version")
            else ""
        )
    )
    if not data.get("gaik_importable", True):
        summary += "; gaik NOT importable, introspection skipped"
    return {
        "status": "pass" if not actionable and data.get("gaik_importable", True) else "fail",
        "summary": summary,
        "findings": data.get("findings", []),
    }


def bullets(path):
    if not path:
        return []
    text = Path(path).read_text(encoding="utf-8")
    return [ln.rstrip() for ln in text.splitlines() if ln.strip()]


def risk_line(plan, version):
    """The PR template's risk level: High for CI, releases, gaik's public API or extras."""
    reasons = []
    if plan.get("surface", {}).get("files"):
        reasons.append("gaik's public API may change")
    ec = plan.get("extras_change", {})
    if any(ec.get(k) for k in ("added", "removed", "changed")) or ec.get("dependencies_changed"):
        reasons.append("gaik's extras or dependencies change")
    if plan.get("classes", {}).get("ci"):
        reasons.append("CI workflows change")
    if reasons:
        return f"High: {'; '.join(reasons)}; the api and runner images move to gaik {version}."
    return (
        f"Medium: the api and runner images move to gaik {version}; upstream changed no public API, "
        "extras or CI."
    )


def cmd_pr_body(args):
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    checks = json.loads(Path(args.checks).read_text(encoding="utf-8")) if args.checks else {}
    target, pins_ = plan["target"], plan.get("pins", {})
    if not target or target["synced"]:
        sys.exit("the plan has nothing to move")
    version, start = (
        target["version"],
        plan["last_sync"]["describe"] or short(plan["last_sync"]["point"]["sha"]),
    )
    old = pins_.get("validated_base") or start
    title = f"Bring gaik {version} into develop"
    affecting = [e for e in plan["entries"] if e["affects_wizard"] and e["kind"] != "release"]
    riders = [e for e in plan["entries"] if not e["affects_wizard"] and e["kind"] != "release"]
    out = ["## What", ""]
    out.append(
        f"- Merges upstream gaik-toolkit `{target['ref']}` into `develop` (gaik {old} to {version}: "
        f"{len(plan['entries'])} upstream changes, {target['commit_count']} commits)."
    )
    out.append(f"- Installs gaik {version} in the api and runner images (`ARG GAIK_VERSION`).")
    if pins_.get("validated_target") and pins_.get("validated_target") != pins_.get(
        "validated_base"
    ):
        out.append(
            f"- Upstream validated the Solution Wizard guidance for {pins_['validated_target']} "
            "(`gaik_validated_version.txt`)."
        )
    out += bullets(args.what)
    out.append("")
    if affecting:
        out += [
            "Upstream changes the wizard uses:",
            "",
            "| Upstream | What | Touches |",
            "|---|---|---|",
        ]
        for e in affecting:
            out.append(f"| {entry_ref(e)} | {e['title'].replace('|', '/')} | {entry_classes(e)} |")
        out.append("")
    if riders:
        many = len(riders) != 1
        out += [
            f"<details><summary>Also brings {len(riders)} upstream change{'s' if many else ''} "
            f"that do{'' if many else 'es'} not touch the wizard</summary>",
            "",
        ]
        out += [f"- {entry_ref(e)} {e['title']}" for e in riders]
        out += ["", "</details>", ""]
    why = bullets(args.why) or [
        "- [[fill: why these upstream changes matter to the wizard, 1-3 bullets]]"
    ]
    out += ["## Why", "", *why, ""]
    conflicts = bullets(args.conflicts)
    if not conflicts and checks.get("merge"):
        for where in (checks.get("worktree"), plan.get("repo")):
            if not where or not Path(where).is_dir():
                continue
            proc = run(
                ["git", "-C", where, "log", "-1", "--format=%b", checks["merge"]], check=False
            )
            if proc.returncode == 0:
                para = proc.stdout.split("Conflicts:", 1)
                if len(para) == 2:
                    conflicts = ["- " + " ".join(para[1].split())]
                break
    if not conflicts:
        conflicts = (
            ["- None."]
            if plan.get("conflicts", {}).get("clean")
            else ["- [[fill: one bullet per conflicted file, which side was kept and why]]"]
        )
    out += ["## Merge conflicts", "", *conflicts, "", "## Testing", ""]
    for step in checks.get("steps", []):
        mark = "x" if step["status"] == "pass" else " "
        extra = {"pass": "", "skip": " (skipped)"}.get(
            step["status"], f" ({step['status'].upper()})"
        )
        failed = f" Failed: {', '.join(step['failed'])}." if step.get("failed") else ""
        summary = step.get("summary", "").rstrip(".!")
        out.append(f"- [{mark}] {step['label']}: {summary}{extra}.{failed}")
    if not checks.get("steps"):
        out.append("- [ ] [[fill: checks not run yet]]")
    out.append(f"- [ ] Not yet run on s4: the runner image has to be rebuilt for gaik {version}.")
    out += bullets(args.notes_extra)
    env = bullets(args.env) or [
        "[[fill: environment variables the upstream changes add or change, from their PR bodies, or None]]"
    ]
    out += [
        "",
        "## Risk",
        "",
        args.risk or risk_line(plan, version),
        "",
        "## How to revert",
        "",
        f"Revert the merge of this pull request (`git revert -m 1 <merge commit>`): develop and both "
        f"images go back to gaik {old}; rebuild the api and runner images after it. A later sync has "
        "to revert that revert first, or git keeps these upstream commits out.",
        "",
        "## Environment variables",
        "",
        *env,
        "",
        "## Notes for merging",
        "",
        "- Merge with a merge commit, not a squash, so the shared history with upstream stays "
        "and the next sync is small.",
        "",
    ]
    body = "\n".join(out)
    statuses = {s["status"] for s in checks.get("steps", [])}
    if statuses and statuses <= {"pass"}:
        state = "Tests and the registry audit pass locally; not yet run on s4."
    elif statuses and statuses <= {"pass", "skip"}:
        state = "The registry audit and local tests pass, the rest run in CI; not yet run on s4."
    else:
        state = "[[fill: state of the checks]]"
    state = args.slack_state or state
    slack = [
        "Review: <PR link>",
        f"Brings gaik {version} from upstream into develop and installs it in the api and runner images. "
        + (
            args.slack_line
            or "[[fill: one line on the upstream fix that matters most to the wizard]]"
        ),
        state,
    ]
    slack_text = "\n".join(slack).replace("`", "")
    bad = local_paths(body) + local_paths(slack_text)
    out_dir = notes_dir(args, Path(plan["repo"]))
    body_path = write(out_dir / f"pr-{version}.md", body)
    write(out_dir / f"pr-{version}-title.txt", title + "\n")
    slack_path = write(out_dir / f"slack-{version}.txt", slack_text + "\n")
    print(f"TITLE: {title}\n\n{body}\n----- Slack -----\n{slack_text}\n")
    print(f"(saved: {body_path}, {slack_path.name})")
    placeholders = re.findall(r"\[\[fill:[^\]]*\]\]", body + slack_text)
    if bad:
        print("REFUSED: machine-local paths in the public text:\n  " + "\n  ".join(bad))
        return 3
    if placeholders:
        print("Fill before posting: " + "; ".join(placeholders))
        return 1
    print(
        f"gh pr create --draft --repo {FORK_SLUG} --base develop --head chore/gaik-{version} "
        f'--title "{title}" --body-file "{body_path}"'
    )
    return 0


# --------------------------------------------------------------------------- main


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo",
        help="the wizard v2 clone (default: WIZARD_REPO, the current repository or this script's "
        "when it is the fork, or a folder named like the fork beside either)",
    )
    parser.add_argument(
        "--notes",
        help="where reports go (default: upstream-sync-notes in the worktrees folder, see above)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="read-only report of what would move")
    p.add_argument("--base", default=BASE_DEFAULT)
    p.add_argument(
        "--target", help="release (default: latest v* tag on upstream main), main, or a ref"
    )
    p.add_argument("--no-fetch", action="store_true")
    p.add_argument("--offline", action="store_true", help="skip the PyPI check")
    p.add_argument("--no-gh", action="store_true", help="skip open upstream PRs")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("prepare", help="worktree + branch from develop, merge the target")
    p.add_argument("--target", required=True)
    p.add_argument("--base", default=BASE_DEFAULT)
    p.add_argument("--branch")
    p.add_argument("--worktree")
    p.set_defaults(func=cmd_prepare)

    p = sub.add_parser("bump-pins", help="set ARG GAIK_VERSION in both images")
    p.add_argument("--worktree", required=True)
    p.add_argument("--version", help="default: the merged gaik_validated_version.txt")
    p.add_argument("--commit", action="store_true")
    p.set_defaults(func=cmd_bump_pins)

    p = sub.add_parser("checks", help="run the audit, tests and ruff in the worktree")
    p.add_argument("--worktree", required=True)
    p.add_argument("--plan", help="plan JSON, for the tests of changed components")
    p.add_argument(
        "--only",
        help="comma list: uv-sync,audit,solution-wizard,image-pins,unit-tests,"
        "wizard-api,ruff-format,ruff-check",
    )
    p.add_argument("--skip-sync", action="store_true")
    p.add_argument(
        "--python",
        default="3.11",
        help="Python for the worktree's environment (default: 3.11, as in CI and the images)",
    )
    p.set_defaults(func=cmd_checks)

    p = sub.add_parser("pr-body", help="render the PR title, body and Slack note")
    p.add_argument("--plan", required=True)
    p.add_argument("--checks")
    p.add_argument("--why", help="file with the Why bullets")
    p.add_argument("--what", help="file with extra What bullets (fork-side fixes in this PR)")
    p.add_argument("--conflicts", help="file with one bullet per conflict resolution")
    p.add_argument("--notes-extra", help="file with extra check bullets")
    p.add_argument("--slack-line", help="one sentence for the Slack note")
    p.add_argument(
        "--slack-state", help="the Slack note's last line, when the checks were not all clean"
    )
    p.add_argument("--risk", help="the Risk line, when the computed one does not fit")
    p.add_argument(
        "--env", help="file with the Environment variables bullets (or a line saying None)"
    )
    p.set_defaults(func=cmd_pr_body)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

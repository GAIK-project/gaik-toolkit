#!/usr/bin/env python3
"""A user-level library of report templates: search, load and save.

  python template_library.py list
  python template_library.py search QUERY
  python template_library.py show ID
  python template_library.py load ID --out structure.json [--replace]
  python template_library.py save --spec SPEC --name NAME --description TEXT
                                  [--id ID] [--keywords a,b] [--replace] [--approved]

A template is the reusable part of a report spec: its title, language, report-wide
instructions and sections. Sources, models, settings, sample files and run results are never
saved. `load` writes the sections as a structure file that `run_report.py set-sections`
accepts, after the user has reviewed them in chat like any other structure.

The library is a folder of one JSON file per template, in a fixed per-user place that no
skill update replaces: `--library`, else the GAIK_REPORT_TEMPLATES environment variable, else
`report-templates` under the home folder. A write is refused inside a git working tree or the
skill's own folder, so a template cannot reach a public repository by accident. `save` writes
nothing unless `--approved` is given, which the agent passes only after the user has seen the
preview and agreed.

Every command takes --json to print one JSON result on stdout. Exit codes: 0 done, 2 invalid
input. Nothing here calls a model or the network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_INPUT = 0, 2
FORMAT = "report-template/1"
ENV_LIBRARY = "GAIK_REPORT_TEMPLATES"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SKILL_DIR = Path(__file__).resolve().parents[1]
SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}|api[_-]?key\s*[:=]\s*\S{8,}", re.IGNORECASE)
STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "report",
    "write",
    "make",
    "create",
    "need",
    "want",
    "please",
    "using",
    "use",
    "about",
    "have",
    "our",
    "your",
    "are",
    "who",
    "its",
    "their",
    "can",
    "all",
    "any",
    "new",
    "template",
    "based",
    "like",
    "also",
}
TRANSLITERATE = {"ß": "ss", "æ": "ae", "Æ": "ae", "ø": "o", "Ø": "o", "œ": "oe", "Œ": "oe"}
FIELD_WEIGHTS = {"name": 3, "keywords": 3, "description": 2, "titles": 1, "id": 2}
MAX_RESULTS = 5


class LibraryError(Exception):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


def slug(text: str) -> str:
    """An ASCII id: 'Condition assessment (house)' -> 'condition_assessment_house'."""
    text = "".join(TRANSLITERATE.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", text.lower())).strip("_")


def words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return [w for w in re.findall(r"[a-z0-9]{3,}", folded) if w not in STOPWORDS]


def library_dir(option: str | None) -> Path:
    chosen = option or os.environ.get(ENV_LIBRARY, "").strip()
    return Path(chosen).expanduser() if chosen else Path.home() / "report-templates"


def inside_git_tree(path: Path) -> Path | None:
    """The git working tree that contains `path`, if any (the path need not exist yet)."""
    for parent in [path.resolve(), *path.resolve().parents]:
        if (parent / ".git").exists():
            return parent
    return None


def check_writable_place(library: Path) -> None:
    resolved = library.resolve()
    if resolved == SKILL_DIR or SKILL_DIR in resolved.parents:
        raise LibraryError(
            "library-location",
            f"The library cannot be inside the skill's folder: a skill update would replace it. "
            f"Use a folder under your home folder, or set {ENV_LIBRARY}",
        )
    tree = inside_git_tree(resolved)
    if tree is not None:
        raise LibraryError(
            "library-location",
            f"The library cannot be inside a git working tree ({tree.name}): a template could "
            f"be committed and published by accident. Use a folder outside any repository, "
            f"or set {ENV_LIBRARY}",
        )


def read_template(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LibraryError("bad-template", f"{path.name} cannot be read: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise LibraryError("bad-template", f"{path.name} is not a {FORMAT} file")
    if not isinstance(data.get("structure"), list) or not data["structure"]:
        raise LibraryError("bad-template", f"{path.name} has no sections")
    return data


def all_templates(library: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The valid templates in the library, and a note for each file that was skipped."""
    found: list[dict[str, Any]] = []
    skipped: list[str] = []
    if library.is_dir():
        for path in sorted(library.glob("*.json")):
            try:
                found.append(read_template(path))
            except LibraryError as exc:
                skipped.append(str(exc))
    return found, skipped


def summary(template: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": template.get("id"),
        "name": template.get("name"),
        "description": template.get("description"),
        "keywords": template.get("keywords", []),
        "language": template.get("language"),
        "sections": [s.get("title") for s in template["structure"]],
        "saved": template.get("saved"),
    }


def score(template: dict[str, Any], query: list[str]) -> int:
    """Weighted count of query words found in the template's fields; a word also matches a
    field word that shares its first five letters, so 'inspections' finds 'inspection'."""
    fields = {
        "name": template.get("name", ""),
        "keywords": " ".join(template.get("keywords", [])),
        "description": template.get("description", ""),
        "titles": " ".join(s.get("title", "") for s in template["structure"]),
        "id": str(template.get("id", "")).replace("_", " ").replace("-", " "),
    }
    total = 0
    for field, text in fields.items():
        have = set(words(text))
        for word in query:
            if word in have or any(
                len(word) >= 5 and len(h) >= 5 and word[:5] == h[:5] for h in have
            ):
                total += FIELD_WEIGHTS[field]
    return total


def structure_from_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """The spec's sections in the structure-file format that set-sections reads."""
    sections = spec.get("sections")
    if not isinstance(sections, list) or not sections:
        raise LibraryError("bad-spec", "The spec has no sections to save")
    titles = {s.get("id"): s.get("title") for s in sections if isinstance(s, dict)}
    structure = []
    for section in sections:
        title = (section.get("title") or "").strip()
        prompt = (section.get("instructions") or "").strip()
        if not title or not prompt:
            raise LibraryError(
                "bad-spec", f"Section {title or section.get('id')!r} needs a title and a prompt"
            )
        entry: dict[str, Any] = {"title": title, "prompt": prompt}
        if section.get("required_items"):
            entry["required_items"] = list(section["required_items"])
        if section.get("depends_on"):
            entry["summary_of"] = [titles[i] for i in section["depends_on"] if i in titles]
        structure.append(entry)
    if len(structure) == 1 and structure[0]["title"] == "Draft":
        raise LibraryError("bad-spec", "The spec still has only the placeholder section")
    return structure


def build_template(args: argparse.Namespace) -> dict[str, Any]:
    try:
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LibraryError("bad-spec", f"The spec cannot be read: {exc}") from exc
    if not isinstance(spec, dict):
        raise LibraryError("bad-spec", "The spec is not a JSON object")
    name = (args.name or "").strip()
    description = (args.description or "").strip()
    if not name or not description:
        raise LibraryError("bad-input", "--name and --description are required: search uses them")
    template_id = (args.id or slug(name)).strip()
    if not ID_PATTERN.match(template_id):
        raise LibraryError(
            "bad-input",
            f"The id {template_id!r} must be lower-case letters, digits, '_' or '-', and start "
            "with a letter or digit",
        )
    keywords = [k.strip() for k in (args.keywords or "").split(",") if k.strip()]
    template = {
        "format": FORMAT,
        "id": template_id,
        "name": name,
        "description": description,
        "keywords": keywords,
        "language": spec.get("language") or "English",
        "title": spec.get("title") or name,
        "instructions": spec.get("instructions") or "",
        "structure": structure_from_spec(spec),
        "saved": datetime.now(UTC).date().isoformat(),
    }
    if SECRET.search(json.dumps(template)):
        raise LibraryError("secret", "The text looks like it contains an API key; nothing is saved")
    return template


def find(library: Path, template_id: str) -> dict[str, Any]:
    if not ID_PATTERN.match(template_id):
        raise LibraryError("bad-input", f"{template_id!r} is not a template id")
    path = library / f"{template_id}.json"
    if not path.is_file():
        raise LibraryError("not-found", f"No template {template_id!r} in {library}")
    return read_template(path)


def command_list(args: argparse.Namespace) -> dict[str, Any]:
    library = library_dir(args.library)
    templates, skipped = all_templates(library)
    return {
        "library": str(library),
        "exists": library.is_dir(),
        "templates": [summary(t) for t in templates],
        "skipped": skipped,
    }


def command_search(args: argparse.Namespace) -> dict[str, Any]:
    library = library_dir(args.library)
    query = words(args.query)
    templates, skipped = all_templates(library)
    ranked = sorted(
        ((score(t, query), t) for t in templates), key=lambda pair: (-pair[0], pair[1]["id"])
    )
    matches = [{**summary(t), "score": s} for s, t in ranked if s > 0][:MAX_RESULTS]
    return {
        "library": str(library),
        "query_words": query,
        "matches": matches,
        "templates_in_library": len(templates),
        "skipped": skipped,
    }


def command_show(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "library": str(library_dir(args.library)),
        "template": find(library_dir(args.library), args.id),
    }


def command_load(args: argparse.Namespace) -> dict[str, Any]:
    library = library_dir(args.library)
    template = find(library, args.id)
    out = Path(args.out)
    if out.exists() and not args.replace:
        raise LibraryError("would-replace", f"{out} exists; pass --replace to overwrite it")
    if library.resolve() in out.resolve().parents:
        raise LibraryError("bad-input", "Write the structure file outside the library")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(template["structure"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        "loaded": template["id"],
        "saved": template.get("saved"),
        "structure_file": str(out),
        "title": template.get("title"),
        "language": template.get("language"),
        "instructions": template.get("instructions"),
        "sections": [s["title"] for s in template["structure"]],
        "next": "Review the sections with the user, then run run_report.py set-sections",
    }


def command_save(args: argparse.Namespace) -> dict[str, Any]:
    library = library_dir(args.library)
    template = build_template(args)
    check_writable_place(library)
    path = library / f"{template['id']}.json"
    exists = path.exists()
    result = {
        "library": str(library),
        "file": str(path),
        "exists": exists,
        "written": False,
        "template": template,
    }
    if not args.approved:
        result["next"] = (
            "Show the user this template and ask whether to save it. Write it only after they "
            "agree, by running the same command again with --approved"
        )
        return result
    if exists and not args.replace:
        raise LibraryError(
            "would-replace", f"{path.name} exists; pass --replace once the user agrees to update it"
        )
    library.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(template, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)
    result["written"] = True
    return result


def render(command: str, result: dict[str, Any]) -> str:
    lines: list[str] = []
    if command in ("list", "search"):
        items = result["templates"] if command == "list" else result["matches"]
        where = f"{result['library']}" + (
            "" if result.get("exists", True) else " (does not exist yet)"
        )
        lines.append(f"Library: {where}")
        if not items:
            lines.append("No templates." if command == "list" else "No matching template.")
        for item in items:
            extra = f"  score {item['score']}" if "score" in item else ""
            lines.append(f"- {item['id']}: {item['name']}{extra}")
            lines.append(f"    {item['description']}")
            lines.append(f"    sections: {'; '.join(item['sections'])}")
        lines += [f"Skipped: {note}" for note in result.get("skipped", [])]
    elif command == "save":
        verb = "Saved" if result["written"] else "Preview, nothing written"
        lines.append(
            f"{verb}: {result['file']}"
            + (" (replaces an existing template)" if result["exists"] else "")
        )
        template = result["template"]
        lines.append(f"{template['name']}: {template['description']}")
        lines += [f"  {i}. {s['title']}" for i, s in enumerate(template["structure"], 1)]
        if "next" in result:
            lines.append(result["next"])
    elif command == "load":
        lines.append(f"Loaded {result['loaded']} to {result['structure_file']}")
        lines += [f"  {i}. {t}" for i, t in enumerate(result["sections"], 1)]
        lines.append(result["next"])
    else:
        lines.append(json.dumps(result, indent=2, ensure_ascii=False))
    return "\n".join(lines)


COMMANDS = {
    "list": command_list,
    "search": command_search,
    "show": command_show,
    "load": command_load,
    "save": command_save,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A user-level library of report templates.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        p = sub.add_parser(name)
        p.add_argument(
            "--library", help=f"library folder (default: {ENV_LIBRARY} or ~/report-templates)"
        )
        p.add_argument("--json", action="store_true", help="print one JSON result on stdout")
        if name == "search":
            p.add_argument("query", help="the user's request, in their words")
        if name in ("show", "load"):
            p.add_argument("id")
        if name == "load":
            p.add_argument("--out", required=True, help="the structure file to write")
            p.add_argument("--replace", action="store_true", help="overwrite --out")
        if name == "save":
            p.add_argument(
                "--spec", required=True, help="the report spec to take the sections from"
            )
            p.add_argument("--name", required=True)
            p.add_argument("--description", required=True)
            p.add_argument("--id", help="file name of the template (default: from --name)")
            p.add_argument("--keywords", help="comma-separated words the user may search with")
            p.add_argument("--replace", action="store_true", help="update an existing template")
            p.add_argument(
                "--approved",
                action="store_true",
                help="write the template; pass it only after the user agreed to the preview",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        result = COMMANDS[args.command](args)
    except LibraryError as exc:
        error = {
            "ok": False,
            "command": args.command,
            "error": {"category": exc.category, "message": str(exc)},
        }
        print(json.dumps(error, indent=2, ensure_ascii=False) if args.json else f"Error: {exc}")
        return EXIT_INPUT
    result = {"ok": True, "command": args.command, **result}
    print(
        json.dumps(result, indent=2, ensure_ascii=False)
        if args.json
        else render(args.command, result)
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())

"""Checks for the published agent plugin in agent-plugin/.

Clients install the plugin from .claude-plugin/marketplace.json, and its skills
quote gaik's API. Nothing else in CI reads either, so a malformed manifest or a
renamed gaik method would reach every installed agent unnoticed. These tests
read files and introspect signatures only -- no network, no database.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import json
import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "agent-plugin"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
SKILL_DIRS = sorted(p.parent for p in (PLUGIN_DIR / "skills").glob("*/SKILL.md"))
SKILL_FILES = sorted((PLUGIN_DIR / "skills").rglob("*.md"))

# Agent Plugins v1: the manifest schema is closed.
AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MANIFEST_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}
PLUGIN_NAME = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
# Codex refuses a version that is not strict semver.
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)

# Agent Skills specification.
SKILL_FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _manifest() -> dict:
    return json.loads(_read(PLUGIN_DIR / "plugin.json"))


def _frontmatter(skill_dir: Path) -> tuple[dict, str]:
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", _read(skill_dir / "SKILL.md"), re.DOTALL)
    assert match, f"{skill_dir.name}/SKILL.md has no frontmatter"
    return yaml.safe_load(match.group(1)), match.group(2)


# ── Manifest and marketplace ────────────────────────────────────────


def test_manifest_is_agent_plugins_v1():
    manifest = _manifest()

    assert manifest["$schema"] == AGENT_PLUGINS_SCHEMA
    assert len(manifest["name"]) <= 64 and PLUGIN_NAME.fullmatch(manifest["name"])
    unknown = set(manifest) - MANIFEST_FIELDS
    assert not unknown, f"not in the closed schema; client data goes under `extensions`: {unknown}"
    assert SEMVER.fullmatch(manifest["version"]), manifest["version"]
    assert manifest["description"].strip()


def test_claude_manifest_agrees_with_the_portable_one():
    # Claude Code reads .claude-plugin/plugin.json; Agent Plugins clients read the
    # root plugin.json. Each caches an install under the version it read, so the two
    # must name the same plugin at the same version.
    claude = json.loads(_read(PLUGIN_DIR / ".claude-plugin" / "plugin.json"))
    portable = _manifest()

    assert claude["name"] == portable["name"]
    assert claude.get("version") == portable["version"], "bump both manifests together"


def test_every_marketplace_entry_resolves_to_a_plugin():
    marketplace = json.loads(_read(MARKETPLACE))
    assert marketplace["owner"]["name"]

    for entry in marketplace["plugins"]:
        source = entry["source"]
        assert source.startswith("./"), f"{entry['name']}: relative sources must start with ./"
        plugin_dir = (REPO_ROOT / source).resolve()
        manifest = json.loads(_read(plugin_dir / "plugin.json"))
        assert manifest["name"] == entry["name"]
        # plugin.json holds the only version. Clients cache an install under the
        # version they read, so a second copy here would drift out of step.
        assert "version" not in entry


def test_marketplace_lists_this_plugin():
    names = {entry["name"] for entry in json.loads(_read(MARKETPLACE))["plugins"]}
    assert _manifest()["name"] in names


# ── Skills ──────────────────────────────────────────────────────────


def test_plugin_has_skills():
    assert SKILL_DIRS, "no skills/<name>/SKILL.md found"


@pytest.mark.parametrize("skill_dir", SKILL_DIRS, ids=lambda p: p.name)
def test_skill_frontmatter_follows_the_spec(skill_dir):
    meta, body = _frontmatter(skill_dir)
    name, description = meta["name"], meta["description"]

    assert name == skill_dir.name, "name must match the directory"
    assert len(name) <= 64 and SKILL_NAME.fullmatch(name)
    assert set(meta) <= SKILL_FIELDS, f"outside the spec: {set(meta) - SKILL_FIELDS}"
    assert 1 <= len(description) <= 1024, f"description is {len(description)} characters"
    # Claude products reject these words in a name, and XML tags in either field.
    assert "claude" not in name and "anthropic" not in name
    assert "<" not in description and ">" not in description
    assert len(body.splitlines()) <= 500, "keep SKILL.md under 500 lines; move detail out"


@pytest.mark.parametrize("path", SKILL_FILES, ids=lambda p: p.relative_to(PLUGIN_DIR).as_posix())
def test_referenced_files_exist(path):
    skill_dir = PLUGIN_DIR / "skills" / path.relative_to(PLUGIN_DIR / "skills").parts[0]
    text = _read(path)
    for ref in re.findall(r"(references/[\w./-]+\.md)", text):
        assert (skill_dir / ref).is_file(), f"{ref} does not exist"
    # A reference file names its siblings bare, e.g. `finnish.md`.
    if path.parent.name == "references":
        for sibling in re.findall(r"`([\w-]+\.md)`", text):
            assert (path.parent / sibling).is_file(), f"{sibling} does not exist"


# ── The gaik API the skills quote ───────────────────────────────────


def _resolve(module_name: str, dotted: str):
    try:
        obj = importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"{module_name} needs an optional dependency: {exc}")
    for part in dotted.split("."):
        assert hasattr(obj, part), (
            f"{module_name}.{dotted} is quoted by an agent-plugin skill but does not exist. "
            "If it was renamed, update agent-plugin/skills in the same change. If it should "
            "exist, its optional dependency is missing: run `uv sync --all-extras`."
        )
        obj = getattr(obj, part)
    return obj


def _imports_in_skills() -> list[tuple[str, str]]:
    pairs = set()
    # A parenthesised import may span lines; a bare one ends at the line break.
    pattern = re.compile(r"from (gaik[\w.]*) import (\([^)]*\)|[^\n]+)")
    for path in SKILL_FILES:
        for module_name, names in pattern.findall(_read(path)):
            for name in re.split(r"[\s,()]+", names.split("#")[0]):
                if re.fullmatch(r"[A-Za-z_]\w*", name):
                    pairs.add((module_name, name))
    return sorted(pairs)


@pytest.mark.parametrize(("module_name", "name"), _imports_in_skills(), ids=lambda v: v)
def test_every_import_in_the_skills_resolves(module_name, name):
    _resolve(module_name, name)


# (module, attribute, keyword arguments the skills pass by name)
QUOTED_CALLS = [
    # parsing-documents
    ("gaik.software_components.parsers", "PyMuPDFParser.parse_pdf", ()),
    ("gaik.software_components.parsers", "parse_pdf", ()),
    ("gaik.software_components.parsers", "DocxParser.parse_docx", ()),
    ("gaik.software_components.parsers", "DoclingParser.parse_document", ()),
    ("gaik.software_components.parsers", "VisionPlusParser", ("vision_config",)),
    ("gaik.software_components.parsers", "VisionPlusParser.parse_document", ()),
    ("gaik.software_components.parsers", "DoclingApiClientParser", ("api_base", "password")),
    (
        "gaik.software_components.parsers",
        "MultimodalParser",
        ("model_provider", "merge_table", "create_html", "use_azure", "vertex_ai"),
    ),
    ("gaik.software_components.parsers", "MultimodalParser.parse", ()),
    # extracting-structured-data
    (
        "gaik.software_components.vision_extractor",
        "VisionExtractor",
        ("model_provider", "use_azure", "vertex_ai", "include_verification"),
    ),
    (
        "gaik.software_components.vision_extractor",
        "VisionExtractor.extract",
        ("file_paths", "user_requirements", "extraction_model", "schema_dir"),
    ),
    ("gaik.software_components.extractor", "DataExtractor.extract", ("documents", "requirements")),
    ("gaik.software_components.schema_generator", "SchemaGenerator.generate_schema", ()),
    (
        "gaik.software_components.schema_generator",
        "SchemaGenerator.generate_schema_with_usage",
        (),
    ),
    ("gaik.software_components.evaluators", "ExtractionEvaluator.evaluate_dataset", ()),
    ("gaik.software_components.evaluators", "BatchEvaluationRunner", ("on_error",)),
    ("gaik.software_components.evaluators", "RAGEvaluator", ("judge",)),
    ("gaik.software_components.validators", "LLMJudge", ()),
    ("gaik.software_components.validators", "LLMJudgePanel", ()),
    ("gaik.software_components.validators", "compare_pairwise", ()),
    # searching-documents
    ("gaik.software_components.config", "get_openai_config", ("use_azure",)),
    ("gaik.software_components.RAG.embedder", "Embedder", ("model",)),
    ("gaik.software_components.RAG.embedder", "Embedder.embed", ()),
    ("gaik.software_components.RAG.embedder", "Embedder.embed_query", ()),
    (
        "gaik.software_components.RAG.pg_vector_store",
        "PgVectorStore",
        ("embedding_dim", "fts_language", "text_processor", "tsquery_mode", "hnsw_ef_search"),
    ),
    ("gaik.software_components.RAG.pg_vector_store", "PgVectorStore.setup", ("create_extensions",)),
    ("gaik.software_components.RAG.pg_vector_store", "PgVectorStore.add", ()),
    (
        "gaik.software_components.RAG.pg_vector_store",
        "PgVectorStore.search_semantic",
        ("top_k", "threshold"),
    ),
    ("gaik.software_components.RAG.pg_vector_store", "PgVectorStore.search_keyword", ("top_k",)),
    ("gaik.software_components.RAG.pg_vector_store", "PgVectorStore.search_hybrid", ()),
    ("gaik.software_components.RAG.ranker", "Ranker", ("rrf_k", "expose_ranks")),
    ("gaik.software_components.RAG.ranker", "Ranker.fuse", ("names", "weights", "top_k")),
    ("gaik.software_components.RAG.ranker", "Ranker.rerank", ("on_error",)),
    ("gaik.software_components.RAG.retriever", "Retriever", ("hybrid_search",)),
    (
        "gaik.software_components.RAG.finnish_text_processor",
        "FinnishTextProcessor",
        ("backend", "decompound"),
    ),
    ("gaik.software_components.RAG.finnish_text_processor", "FinnishTextProcessor.to_tsquery", ()),
    (
        "gaik.software_components.RAG.finnish_text_processor",
        "FinnishTextProcessor.to_tsvector_text",
        (),
    ),
    ("gaik.software_components.RAG.relevance_gate", "RelevanceGate", ("floor", "lower_is_better")),
    (
        "gaik.software_components.RAG.relevance_gate",
        "RelevanceGate.calibrate",
        ("lower_is_better",),
    ),
    ("gaik.software_components.RAG.relevance_gate", "RelevanceGate.is_answerable", ("key",)),
]


@pytest.mark.parametrize(
    ("module_name", "dotted", "kwargs"), QUOTED_CALLS, ids=[c[1] for c in QUOTED_CALLS]
)
def test_quoted_call_exists_with_its_keywords(module_name, dotted, kwargs):
    params = inspect.signature(_resolve(module_name, dotted)).parameters
    missing = [kw for kw in kwargs if kw not in params]
    assert not missing, f"{dotted} no longer accepts {missing}; update the skill that passes them"


# (module, dataclass, fields the skills read)
QUOTED_FIELDS = [
    (
        "gaik.software_components.parsers",
        "ParseResult",
        ("raw_markdown", "clean_markdown", "html", "usage"),
    ),
    (
        "gaik.software_components.vision_extractor",
        "VisionExtractionResult",
        ("data", "usage", "verification"),
    ),
    ("gaik.software_components.extractor", "SchemaGenerationResult", ("schema", "requirements")),
    (
        "gaik.software_components.evaluators",
        "ExtractionMetrics",
        ("precision", "recall", "f1", "hallucination_rate", "n_correct", "n_expected"),
    ),
    ("gaik.software_components.RAG.relevance_gate", "Calibration", ("floor", "separated")),
]


@pytest.mark.parametrize(
    ("module_name", "cls_name", "fields"), QUOTED_FIELDS, ids=[f[1] for f in QUOTED_FIELDS]
)
def test_quoted_result_fields_exist(module_name, cls_name, fields):
    cls = _resolve(module_name, cls_name)
    present = {f.name for f in dataclasses.fields(cls)}
    missing = [f for f in fields if f not in present]
    assert not missing, f"{cls_name} no longer has {missing}; update the skill that reads them"

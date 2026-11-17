"""External services: a need outside GAIK, checked in the blueprint and written into the PoC.

A service's package goes into requirements.txt, which a customer installs with
``pip install -r``, and its variable names into .env.example, so the blueprint
refuses anything but a plain requirement and names of the service's own.
"""

import ast
import contextlib
import copy
import io
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard import blueprint as bp_module  # noqa: E402
from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.docs_generator import generate_docs  # noqa: E402
from solution_wizard.scaffolder import scaffold_poc  # noqa: E402
from solution_wizard.validator import validate  # noqa: E402

WIZARD = Path(__file__).parent.parent
EXAMPLE = WIZARD / "examples" / "document_extraction_blueprint.json"
SCHEMA_FILE = WIZARD / "schemas" / "use_case_blueprint.schema.json"
TEMPLATES = WIZARD / "templates" / "poc"
#: gaik's source in this repository, read as text: the tests here run without gaik.
GAIK_SOURCE = WIZARD.parent / "src" / "gaik"

SEARCH = {
    "name": "Tavily web search",
    "purpose": "Finds recent public news about the supplier named in the invoice",
    "python_package": "tavily-python>=0.5",
    "env_vars": ["TAVILY_API_KEY"],
    "docs_url": "https://docs.tavily.com",
    "data_sent": "The supplier's company name, as a search query",
    "user_can_provide": True,
    "fallback": "The supplier news field is left empty",
}


def _data(*services: dict) -> dict:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data["technical_spec"]["external_services"] = [copy.deepcopy(s) for s in services]
    return data


def _blueprint(*services: dict) -> Blueprint:
    return Blueprint.model_validate(_data(*services))


def _refused(**changes) -> str:
    with pytest.raises(ValueError) as caught:
        _blueprint({**SEARCH, **changes})
    return str(caught.value)


# ---------------------------------------------------------------------------
# The blueprint model
# ---------------------------------------------------------------------------


def test_a_plain_service_is_accepted_as_written() -> None:
    services = _blueprint(SEARCH).technical_spec["external_services"]

    assert services == [SEARCH]


def test_a_blueprint_without_services_is_unchanged() -> None:
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    assert Blueprint.model_validate(data).technical_spec == data["technical_spec"]
    assert bp_module.external_services(Blueprint.model_validate(data)) == []


@pytest.mark.parametrize(
    "package",
    [
        "tavily-python",
        "tavily-python>=0.5,<1",
        "requests[socks]==2.32.3",
        "Foo.Bar_baz~=1.4",
        "pkg[a,b]!=2.0.*",
    ],
)
def test_plain_requirements_are_accepted(package) -> None:
    services = _blueprint({**SEARCH, "python_package": package}).technical_spec

    assert services["external_services"][0]["python_package"] == package


@pytest.mark.parametrize(
    "package",
    [
        "https://example.com/tavily-0.5.tar.gz",
        "tavily @ https://example.com/tavily.whl",
        "git+https://example.com/tavily.git",
        "-e .",
        "-e git+https://example.com/x.git#egg=x",
        "--index-url https://mirror.example/simple",
        "tavily --index-url https://mirror.example/simple",
        "tavily\n--extra-index-url https://mirror.example/simple",
        "tavily\n",
        "tavily\r",
        "tavily; python_version < '3.12'",
        "tavily>=0.5 ; sys_platform == 'win32'",
        "./vendor/tavily",
        "../tavily",
        "C:\\wheels\\tavily.whl",
        "tavily===0.5",
        'tavily"',
        "",
    ],
)
def test_a_requirement_that_is_not_plain_is_refused(package) -> None:
    message = _refused(python_package=package)

    assert "must be a plain PyPI requirement" in message
    assert "external_services[0].python_package" in message


@pytest.mark.parametrize(
    "package",
    [
        "gaik<0.5",
        "gaik[extractor]==0.1.0",
        "GAIK",
        "pyyaml==5.1",
        "PyYAML",
        "pydantic==1.0",
        "pydantic[email]>=2.6",
        "python_dotenv",
        "Python.Dotenv==0.1",
        "reportlab<4",
    ],
)
def test_a_project_the_poc_installs_for_itself_is_not_a_service_package(package) -> None:
    """pip would combine the service's line with the PoC's own (gaik<0.5 beside
    gaik>=0.11.0) and fail, or install a version the PoC cannot run on."""
    message = _refused(python_package=package)

    assert "which the PoC installs for itself" in message
    assert "external_services[0].python_package" in message


def test_a_package_that_only_starts_like_one_of_the_poc_s_own_is_accepted() -> None:
    for package in ("gaik-extras-for-x", "pydantic-settings>=2", "pyyaml-include"):
        services = _blueprint({**SEARCH, "python_package": package}).technical_spec
        assert services["external_services"][0]["python_package"] == package


def test_every_project_the_scaffolder_writes_is_one_a_service_cannot_name(tmp_path) -> None:
    """The scaffolder's requirements.txt, with the PDF report and every provider extra
    the example uses: a project added there must be added to POC_OWN_PROJECTS too."""
    data = _data()
    data["technical_spec"]["output_types"] = ["json", "pdf"]
    poc = scaffold_poc(Blueprint.model_validate(data), tmp_path)["poc_dir"]
    lines = [line for line in _requirements(poc) if line and not line.startswith("#")]

    assert any(line.startswith("reportlab") for line in lines)
    assert {bp_module.project_name(line) for line in lines} <= bp_module.POC_OWN_PROJECTS


def test_a_service_pinning_gaik_after_loading_writes_no_requirements(tmp_path) -> None:
    bp = _blueprint(SEARCH)
    bp.technical_spec["external_services"][0]["python_package"] = "gaik<0.5"

    errors, _ = _rule_15(validate(bp))
    assert errors and "which the PoC installs for itself" in errors[0]
    with pytest.raises(ValueError, match="which the PoC installs for itself"):
        scaffold_poc(bp, tmp_path)
    assert not (tmp_path / "poc" / "requirements.txt").exists()


@pytest.mark.parametrize(
    "name",
    [
        "tavily_api_key",
        "TAVILY-API-KEY",
        "1TAVILY",
        "TAVILY_API_KEY\n",
        "TAVILY API KEY",
        "",
        "A" * 65,
    ],
)
def test_a_variable_name_that_is_not_upper_case_is_refused(name) -> None:
    message = _refused(env_vars=[name])

    assert "must be an UPPER_CASE name" in message


@pytest.mark.parametrize(
    "name",
    [
        "AZURE_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "LITELLM_API_KEY",
        "WIZARD_API_TOKEN",
        "GAIK_ALLOWED_ENDPOINT_HOSTS",
        "LLM_PROVIDER",
        "TTS_ENDPOINT",
        "TYPESAFE_BASE_URL",
        "TYPESAFE_API_KEY",
        "API_BASE",
        "PYTHONPATH",
        "PATH",
    ],
)
def test_a_provider_or_sandbox_variable_is_not_a_services_own(name) -> None:
    """The sandbox holds the provider's key under these names: a service that read one
    would send it to a third party."""
    message = _refused(env_vars=[name])

    assert "belongs to gaik, the model providers, the sandbox, Python, the network" in message


@pytest.mark.parametrize(
    "name",
    [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CURL_CA_BUNDLE",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "UV_INDEX_URL",
        "CONDA_PREFIX",
        "LD_PRELOAD",
        "DYLD_INSERT_LIBRARIES",
    ],
)
def test_a_network_tls_or_installer_setting_is_not_a_services_own(name) -> None:
    """Set from the service's .env section, these would send every model call, with the
    provider's key, through a proxy or a certificate the service chose."""
    message = _refused(env_vars=[name])

    assert "the network or the installers" in message


@pytest.mark.parametrize("name", ["http_proxy", "https_proxy", "Https_Proxy", "no_proxy"])
def test_a_proxy_variable_in_any_case_is_refused(name) -> None:
    assert bp_module.env_name_problem(name)
    assert _refused(env_vars=[name])


def test_every_variable_the_env_template_names_is_reserved() -> None:
    """A provider added to .env.example without a reserved name fails here."""
    template = (TEMPLATES / "_common" / "env.example.tmpl").read_text(encoding="utf-8")
    names = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]*)=", template, re.MULTILINE))
    names |= set(re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b are also accepted", template))

    assert len(names) > 20
    for name in sorted(names):
        assert bp_module.env_name_problem(name), name


#: gaik's helpers that read a variable by the name passed to them.
_ENV_READERS = {
    "getenv",
    "_env",
    "_first_env",
    "require_env",
    "_int",
    "_float",
    "_str",
    "_text",
    "_number",
}
_ENV_NAME = re.compile(r"[A-Z][A-Z0-9_]+")


def _is_environ(node: ast.AST) -> bool:
    return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
        isinstance(node, ast.Name) and node.id == "environ"
    )


def _variables_gaik_reads() -> set[str]:
    """The variable names gaik's source reads, found without importing gaik: the names
    passed to os.getenv, os.environ and gaik's own env helpers, and the addresses
    endpoints.PROVIDER_ENDPOINT_ENVS trusts with a provider's key."""
    names: set[str] = set()
    for path in sorted(GAIK_SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants: dict[str, str] = {}
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if not isinstance(target, ast.Name):
                    continue
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    constants[target.id] = node.value.value
                if target.id == "PROVIDER_ENDPOINT_ENVS":
                    names |= {
                        c.value
                        for c in ast.walk(node.value)
                        if isinstance(c, ast.Constant) and isinstance(c.value, str)
                    }
        for node in ast.walk(tree):
            args: list[ast.AST] = []
            if isinstance(node, ast.Call):
                func = node.func
                called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if called in _ENV_READERS or (
                    called == "get" and isinstance(func, ast.Attribute) and _is_environ(func.value)
                ):
                    args = node.args
            elif isinstance(node, ast.Subscript) and _is_environ(node.value):
                args = [node.slice]
            for arg in args:
                if isinstance(arg, ast.Constant):
                    value = arg.value
                else:
                    value = constants.get(arg.id) if isinstance(arg, ast.Name) else None
                if isinstance(value, str):
                    names.add(value)
    return {name for name in names if _ENV_NAME.fullmatch(name)}


def test_every_variable_gaik_reads_is_reserved() -> None:
    """A service that named one would choose gaik's provider (LLM_PROVIDER), an address
    gaik sends a key to (TTS_ENDPOINT, TYPESAFE_BASE_URL) or a component's setting."""
    names = _variables_gaik_reads()

    assert {"LLM_PROVIDER", "TTS_ENDPOINT", "TYPESAFE_BASE_URL", "AZURE_API_KEY"} <= names
    assert len(names) > 60
    assert [name for name in sorted(names) if not bp_module.env_name_problem(name)] == []


@pytest.mark.parametrize(
    "url",
    [
        "http://docs.example.com",
        "https://user:secret@docs.example.com",
        "javascript:alert(1)",
        "https://docs.example.com/a b",
        "https://docs.example.com\n",
        "https://",
    ],
)
def test_the_docs_address_is_https_without_credentials(url) -> None:
    assert "must be an https address" in _refused(docs_url=url)


@pytest.mark.parametrize(
    "missing", ["name", "purpose", "data_sent", "user_can_provide", "fallback"]
)
def test_what_the_user_was_told_and_answered_is_required(missing) -> None:
    service = {k: v for k, v in SEARCH.items() if k != missing}
    with pytest.raises(ValueError, match=missing):
        _blueprint(service)


def test_a_name_on_two_lines_and_an_unknown_key_are_refused() -> None:
    assert "name must be one line" in _refused(name="Search\nimport os")
    assert "Extra inputs are not permitted" in _refused(api_key="tvly-not-a-real-key")
    assert "must not be empty" in _refused(fallback="   ")


def test_the_list_has_a_limit() -> None:
    services = [
        {**SEARCH, "name": f"Service {n}"} for n in range(bp_module.MAX_EXTERNAL_SERVICES + 1)
    ]
    with pytest.raises(ValueError, match="the limit is"):
        _blueprint(*services)
    with pytest.raises(ValueError, match="must be a list"):
        Blueprint.model_validate({**_data(), "technical_spec": {"external_services": "Tavily"}})


# ---------------------------------------------------------------------------
# The JSON Schema
# ---------------------------------------------------------------------------


def _service_schema(schema: dict) -> dict:
    return schema["properties"]["technical_spec"]["properties"]["external_services"]["items"]


def test_the_committed_json_schema_is_the_models() -> None:
    assert json.loads(SCHEMA_FILE.read_text(encoding="utf-8")) == Blueprint.model_json_schema()


def test_the_json_schema_patterns_refuse_what_the_model_refuses() -> None:
    props = _service_schema(json.loads(SCHEMA_FILE.read_text(encoding="utf-8")))["properties"]
    package = props["python_package"]["pattern"]
    env_name = props["env_vars"]["items"]["pattern"]

    assert re.fullmatch(package, "tavily-python>=0.5,<1")
    for bad in ("https://x/y.whl", "-e .", "tavily --index-url x", "tavily\n-e .", "x; os=='nt'"):
        assert not re.fullmatch(package, bad), bad
    assert re.fullmatch(env_name, "TAVILY_API_KEY")
    assert not re.fullmatch(env_name, "tavily_key")


def test_the_json_schema_validates_a_blueprint() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))

    jsonschema.validate(_data(SEARCH), schema)
    for change in (
        {"python_package": "-e ."},
        {"python_package": "tavily --index-url https://mirror.example/simple"},
        {"env_vars": ["tavily-key"]},
        {"docs_url": "http://docs.example.com"},
        {"user_can_provide": "yes"},
        {"api_key": "tvly-not-a-real-key"},
    ):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(_data({**SEARCH, **change}), schema)


# ---------------------------------------------------------------------------
# The validator (Rule 15)
# ---------------------------------------------------------------------------


def _rule_15(result) -> tuple[list[str], list[str]]:
    return (
        [e.message for e in result.errors if e.rule == 15],
        [w.message for w in result.warnings if w.rule == 15],
    )


def test_a_service_the_user_can_provide_passes() -> None:
    errors, warnings = _rule_15(validate(_blueprint(SEARCH)))

    assert errors == [] and warnings == []


def test_a_service_the_user_cannot_provide_is_an_open_item() -> None:
    errors, warnings = _rule_15(validate(_blueprint({**SEARCH, "user_can_provide": False})))

    assert errors == []
    assert len(warnings) == 1
    assert "the user cannot provide it yet" in warnings[0]
    assert "open item in assumptions" in warnings[0]


def test_local_processing_refuses_a_service_that_receives_data() -> None:
    bp = _blueprint(SEARCH, {**SEARCH, "name": "Local graph library", "data_sent": "None"})
    bp.governance.data_handling.local_processing_required = True

    errors, _ = _rule_15(validate(bp))

    assert len(errors) == 1
    assert "Tavily web search" in errors[0] and "local_processing_required" in errors[0]


@pytest.mark.parametrize(
    "said",
    ["none", "None", "  NONE  ", "none.", "Nothing", "nothing.", "No data", "no  data."],
)
def test_only_a_bare_none_nothing_or_no_data_counts_as_nothing_sent(said) -> None:
    bp = _blueprint({**SEARCH, "name": "Local graph library", "data_sent": said})
    bp.governance.data_handling.local_processing_required = True

    errors, _ = _rule_15(validate(bp))

    assert bp_module.sends_nothing(said)
    assert errors == []


@pytest.mark.parametrize(
    "said",
    [
        "None of the documents; the query text goes to Tavily",
        "No data beyond the company name",
        "Nothing but the supplier's name",
        "None except the business ID",
        "nothing other than the query",
        "none: it runs locally",
        "Nothing leaves the machine",
        "No data is sent",
        "none, none",
        "Nonessential metadata of the invoice",
        "The supplier's company name",
        "Some data, none of it personal",
    ],
)
def test_any_other_wording_counts_as_data_sent(said) -> None:
    """A wording that starts like "none" may still name what leaves, so only the bare
    words count as nothing: with local processing required the service is refused."""
    bp = _blueprint({**SEARCH, "data_sent": said})
    bp.governance.data_handling.local_processing_required = True

    errors, _ = _rule_15(validate(bp))

    assert not bp_module.sends_nothing(said)
    assert len(errors) == 1


def test_no_external_model_api_asks_for_the_data_owners_word() -> None:
    bp = _blueprint(SEARCH)
    bp.governance.data_handling.external_model_api_allowed = False

    errors, warnings = _rule_15(validate(bp))

    assert not any("Tavily" in e for e in errors)
    assert any("Confirm with the data owner" in w for w in warnings)


def test_a_service_changed_after_loading_is_checked_again(tmp_path) -> None:
    bp = _blueprint(SEARCH)
    bp.technical_spec["external_services"][0]["python_package"] = "-e git+https://x/y.git"

    errors, _ = _rule_15(validate(bp))
    assert errors and "plain PyPI requirement" in errors[0]
    with pytest.raises(ValueError, match="plain PyPI requirement"):
        scaffold_poc(bp, tmp_path)
    assert not (tmp_path / "poc" / "requirements.txt").exists()


# ---------------------------------------------------------------------------
# The PoC package
# ---------------------------------------------------------------------------


def _requirements(poc: Path) -> list[str]:
    return (poc / "requirements.txt").read_text(encoding="utf-8").splitlines()


def _added_requirements(tmp_path: Path, *services: dict) -> list[str]:
    """The lines the services add after what the package has without them."""
    lines = _requirements(scaffold_poc(_blueprint(*services), tmp_path)["poc_dir"])
    plain = _requirements(scaffold_poc(_blueprint(), tmp_path / "plain")["poc_dir"])
    # The gaik lines and the rest come first, as without services.
    assert lines[: len(plain)] == plain
    return lines[len(plain) :]


def test_packages_follow_the_gaik_lines_and_an_exact_duplicate_is_left_out(tmp_path) -> None:
    services = (
        SEARCH,
        {**SEARCH, "name": "Tavily again", "python_package": "Tavily_Python>=0.5"},
        {**SEARCH, "name": "Register lookup", "python_package": "requests[socks]>=2.31"},
        {**SEARCH, "name": "Register again", "python_package": "requests[SOCKS]"},
        {**SEARCH, "name": "No package", "python_package": None},
    )

    assert _added_requirements(tmp_path, *services) == [
        "# Packages of the external services (README, External services)",
        "tavily-python>=0.5",
        "requests[socks]>=2.31",
    ]


def test_a_package_with_extras_or_a_stricter_version_is_kept(tmp_path) -> None:
    """pip combines every line of one project, so the extra and the version count."""
    services = (
        SEARCH,
        {**SEARCH, "name": "Stricter", "python_package": "tavily-python>=0.6"},
        {**SEARCH, "name": "Register lookup", "python_package": "requests>=2.31"},
        {**SEARCH, "name": "Over a proxy", "python_package": "requests[socks]>=2.31"},
        {**SEARCH, "name": "Same again", "python_package": "requests[socks]>=2.31"},
    )

    assert _added_requirements(tmp_path, *services) == [
        "# Packages of the external services (README, External services)",
        "tavily-python>=0.5",
        "tavily-python>=0.6",
        "requests>=2.31",
        "requests[socks]>=2.31",
    ]


def test_no_services_no_extra_requirement_lines(tmp_path) -> None:
    poc = scaffold_poc(_blueprint(), tmp_path)["poc_dir"]

    assert not any("external services" in line for line in _requirements(poc))


def test_env_example_has_each_services_keys_empty_under_its_comment(tmp_path) -> None:
    other = {
        **SEARCH,
        "name": "Register lookup",
        "purpose": "Checks the supplier's business ID\nprint('injected')",
        "env_vars": ["REGISTER_API_KEY", "TAVILY_API_KEY", "REGISTER_BASE_URL"],
    }
    poc = scaffold_poc(_blueprint(SEARCH, other), tmp_path)["poc_dir"]
    env = (poc / ".env.example").read_text(encoding="utf-8")
    section = env[env.index("# --- External services") :]

    assert section.splitlines() == [
        "# --- External services (outside GAIK) ---",
        "# Without its key the PoC skips the step, says so in its log, and runs the rest.",
        f"# {SEARCH['name']}: {SEARCH['purpose']}",
        "TAVILY_API_KEY=",
        "",
        "# Register lookup: Checks the supplier's business ID print('injected')",
        "REGISTER_API_KEY=",
        "REGISTER_BASE_URL=",
    ]
    # Each name once, every other line a comment.
    assert env.count("TAVILY_API_KEY=") == 1
    for line in env.splitlines():
        assert not line or line.startswith("#") or re.fullmatch(r"[A-Z][A-Z0-9_]*=", line), line


def test_env_example_is_unchanged_without_services(tmp_path) -> None:
    poc = scaffold_poc(_blueprint(), tmp_path)["poc_dir"]
    env = (poc / ".env.example").read_text(encoding="utf-8")

    assert "External services" not in env
    assert env.endswith("# GAIK_ALLOWED_ENDPOINT_HOSTS=\n")


def test_the_readme_and_the_documents_list_the_services_and_keys(tmp_path) -> None:
    unavailable = {**SEARCH, "name": "Mail | sender", "user_can_provide": False}
    bp = _blueprint(SEARCH, unavailable)
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    readme = (poc / "README.md").read_text(encoding="utf-8")
    docs = {p.stem: p.read_text(encoding="utf-8") for p in generate_docs(bp, tmp_path)}

    assert "## External services" in readme
    for text in (readme, docs["technical_specification"]):
        assert "**Tavily web search**" in text
        assert "`tavily-python>=0.5`" in text and "`TAVILY_API_KEY`" in text
        assert "not yet, an open item; the PoC runs without it" in text
        assert "Mail \\| sender" in text  # text, not a table cell
    assert "set `TAVILY_API_KEY` (Tavily web search)" in docs["user_guide"]


def test_without_services_the_readme_has_no_section_and_the_guide_says_none(tmp_path) -> None:
    bp = _blueprint()
    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    docs = {p.stem: p.read_text(encoding="utf-8") for p in generate_docs(bp, tmp_path)}

    assert "External services" not in (poc / "README.md").read_text(encoding="utf-8")
    assert "- External services: none." in docs["user_guide"]
    assert "${" not in docs["technical_specification"] + docs["user_guide"]


def test_the_web_diagram_path_does_not_carry_services() -> None:
    """generate_bpmn_from_v2.py validates what v2_to_v1_dict builds. Its technical_spec
    has fixed keys, so a service entry the scaffolder would refuse cannot stop the
    Workflow tab's diagram."""
    from solution_wizard.bpmn_generator import generate_bpmn
    from solution_wizard.v2_adapter import v2_to_v1_dict

    v2 = {
        "name": "Invoice check",
        "steps": [
            {"id": "upload", "name": "Upload invoice", "type": "io"},
            {"id": "extract", "name": "Extract fields", "type": "ai", "component": "Extractor"},
        ],
        "technical_spec": {"external_services": [{**SEARCH, "python_package": "-e ."}]},
        "external_services": [{**SEARCH, "env_vars": ["HTTPS_PROXY"]}],
    }
    v1 = v2_to_v1_dict(v2, session_id="s1")

    assert "external_services" not in v1["technical_spec"]
    assert "<bpmn" in generate_bpmn(Blueprint.model_validate(v1))


@pytest.mark.parametrize(
    "example", ["document_extraction_blueprint.json", "rag_workflow_blueprint.json"]
)
def test_the_generated_code_still_parses_with_services(tmp_path, example) -> None:
    data = json.loads((WIZARD / "examples" / example).read_text(encoding="utf-8"))
    data["technical_spec"]["external_services"] = [SEARCH]
    poc = scaffold_poc(Blueprint.model_validate(data), tmp_path)["poc_dir"]

    for name in ("run_poc.py", "provider_config.py", "evals/run_basic_eval.py"):
        ast.parse((poc / name).read_text(encoding="utf-8"))
    assert "def external_service(" in (poc / "provider_config.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The helper a step gets its package from (provider_config.external_service)
# ---------------------------------------------------------------------------


def _external_service():
    """The helper from the template, without the gaik imports provider_config has."""
    source = (TEMPLATES / "_common" / "provider_config.py.tmpl").read_text(encoding="utf-8")
    tree = ast.parse(source)
    func = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "external_service"
    )
    namespace: dict = {"os": __import__("os")}
    exec(compile(ast.Module(body=[func], type_ignores=[]), "provider_config", "exec"), namespace)
    return namespace["external_service"]


def _call(*args, **kwargs):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = _external_service()(*args, **kwargs)
    return result, out.getvalue()


def test_without_the_package_or_the_key_the_step_is_skipped(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    package, said = _call("Tavily web search", "no_such_package_xyz", ("TAVILY_API_KEY",))

    assert package is None
    assert said.startswith("SKIPPED Tavily web search: ")
    assert "package 'no_such_package_xyz' is not installed" in said
    assert "TAVILY_API_KEY not set in .env" in said
    assert said.count("\n") == 1  # one line in the run's log


def test_an_empty_key_counts_as_missing(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "   ")

    package, said = _call("Tavily web search", "json", ("TAVILY_API_KEY",))

    assert package is None
    assert "TAVILY_API_KEY not set" in said and "not installed" not in said


def test_with_the_package_and_the_key_the_package_is_returned(monkeypatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-value-not-a-key")

    package, said = _call("Tavily web search", "json", ("TAVILY_API_KEY",))

    assert package is json
    assert said == ""


@pytest.mark.parametrize("module", ["no_such_package_xyz.client", "json.no_such_submodule"])
def test_a_missing_module_inside_a_package_is_not_installed(monkeypatch, module) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "test-value-not-a-key")

    package, said = _call("Tavily web search", module, ("TAVILY_API_KEY",))

    assert package is None
    assert f"package {module!r} is not installed" in said


def _broken_package(tmp_path: Path, monkeypatch, name: str, body: str) -> None:
    (tmp_path / name).mkdir()
    (tmp_path / name / "__init__.py").write_text(body, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "test-value-not-a-key")


def test_an_installed_package_without_its_own_dependency_is_an_error(tmp_path, monkeypatch):
    """Not "not installed": the package is there and its install is broken."""
    _broken_package(tmp_path, monkeypatch, "broken_sdk_xyz", "import missing_dependency_xyz\n")

    with pytest.raises(ModuleNotFoundError, match="missing_dependency_xyz"):
        _call("Tavily web search", "broken_sdk_xyz", ("TAVILY_API_KEY",))


def test_an_import_error_of_the_package_itself_is_raised(tmp_path, monkeypatch) -> None:
    _broken_package(
        tmp_path, monkeypatch, "failing_sdk_xyz", "raise ImportError('needs a newer OpenSSL')\n"
    )

    with pytest.raises(ImportError, match="needs a newer OpenSSL"):
        _call("Tavily web search", "failing_sdk_xyz", ("TAVILY_API_KEY",))


def test_the_helper_is_no_import_statement_the_package_check_would_refuse() -> None:
    """The api's package check refuses an entrypoint that imports a package the sandbox
    lacks; the helper imports by name, so the call does not count as one."""
    source = (TEMPLATES / "_common" / "provider_config.py.tmpl").read_text(encoding="utf-8")
    func = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "external_service"
    )
    imports = [
        alias.name
        for node in ast.walk(func)
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    ]
    assert imports == ["importlib"]

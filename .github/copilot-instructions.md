**IMPORTANT:** Keep this updated with architecture changes — this is the source of truth for AI agents.

## Project Snapshot
- Multi-provider AI toolkit for structured data extraction (OpenAI, Anthropic, Google, Azure)
- Ships PyPI distribution from `gaik-py/src/gaik` via GitHub Actions
- Built on LangChain with `.with_structured_output()` API

## Tech Stack
- Python 3.10+, LangChain, Pydantic
- GitHub Actions: tests → build → publish to Test PyPI
- `pyproject.toml` defines all dependencies

## Architecture
```
gaik/
├── providers/    # Shared LLM provider registry (OpenAI, Anthropic, etc.)
└── extract/      # Dynamic schema extraction module
```

## Key Conventions
- **Providers**: All in `gaik/providers/`, registry in `__init__.py`
- **Default models**: OpenAI=gpt-4.1, Anthropic=claude-sonnet-4-5, Google=gemini-2.5-flash
- **Dependencies**: All providers in core deps (no optional extras)
- **Version sync**: `pyproject.toml` version must match git tag (v0.2.1 = 0.2.1)

## Adding New Provider
1. Create `gaik/providers/yourprovider.py` with `LLMProvider` subclass
2. Add `langchain-yourprovider>=x.x.x` to `dependencies` in `pyproject.toml`
3. Register in `gaik/providers/__init__.py` PROVIDERS dict
4. Run `examples/test_gaik_installation.py` to verify

## Testing
- **No API calls**: `python examples/test_gaik_installation.py`
- **With API**: `python examples/test_real_extraction.py` (needs API key)
- **Build**: `cd gaik-py && python -m build && twine check dist/*`
- **CI**: Workflow tests provider registry and LangChain integration

## Release
1. Bump version in `pyproject.toml`
2. Commit changes
3. Tag: `git tag v0.2.2 && git push origin v0.2.2`
4. GitHub Actions auto-publishes to Test PyPI

## Rules
- Keep `gaik.extract` API backward compatible
- Update examples when adding features
- Never commit secrets/tokens
- Test before pushing packaging changes

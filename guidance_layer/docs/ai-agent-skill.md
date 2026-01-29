# AI Agent Skill for GAIK Toolkit

This repository includes a skill definition for AI coding assistants, specifically designed for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

## What is a Skill?

Skills are structured documentation files that help AI agents understand how to work with a codebase. They provide:

- Installation instructions
- API patterns and code examples
- Configuration guidance
- Links to documentation

## Location

The GAIK toolkit skill is located at:

```
.claude/skills/gaik-toolkit/
├── SKILL.md                    # Main skill file
├── scripts/
│   └── fetch_pypi_readme.py    # Fetches latest PyPI info
└── references/
    ├── building-blocks.md      # Detailed API documentation
    ├── software-components.md  # Pipeline patterns
    └── examples.md             # Complete working examples
```

## Usage with Claude Code

When using [Claude Code](https://code.claude.com/) in this repository, the skill is automatically loaded. Claude will understand:

- How to use software components (`SchemaGenerator`, `DataExtractor`, `VisionParser`, `Transcriber`, etc.)
- How to configure Azure OpenAI or standard OpenAI
- How to use software components (`AudioToStructuredData`, `DocumentsToStructuredData`)
- Installation options (`gaik[all]`, `gaik[all-cpu]`, etc.)

## Fetching Latest Package Info

The included script fetches the latest package information from PyPI:

```bash
python .claude/skills/gaik-toolkit/scripts/fetch_pypi_readme.py
python .claude/skills/gaik-toolkit/scripts/fetch_pypi_readme.py --version  # Version only
```

## For Other AI Agents

If you're using a different AI coding assistant, you can reference the skill files directly:

- **Main documentation**: [.claude/skills/gaik-toolkit/SKILL.md](../.claude/skills/gaik-toolkit/SKILL.md)
- **API reference**: [.claude/skills/gaik-toolkit/references/building-blocks.md](../.claude/skills/gaik-toolkit/references/building-blocks.md)
- **Examples**: [.claude/skills/gaik-toolkit/references/examples.md](../.claude/skills/gaik-toolkit/references/examples.md)

## Maintaining the Skill

Update the skill when:

- New software components or software modules are added
- Import paths change in `implementation_layer/src/gaik/`
- Major API changes occur

The skill version is tracked in the SKILL.md frontmatter.

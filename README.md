# GAIK - General AI Kit

A monorepo toolkit for sharing and reusing code across Python and TypeScript projects.

## Purpose

GAIK enables you to:

- **Share code** between multiple projects without copy-pasting
- **Reuse utilities** across different codebases by installing directly from GitHub
- **Maintain consistency** with centralized, versioned components
- **Iterate quickly** by updating shared code in one place
- **Publish later** to PyPI/npm when components are mature enough

## Components

- **gaik-py**: Python library with modular namespace structure
- **gaik-ts**: TypeScript/ESM library with subpath exports
- **gaik-demo**: Docker environment where all components are available for testing

Both libraries support modular imports - use only what you need.

## Installation

### Python (gaik-py)

Install directly from GitHub:

```bash
pip install "git+https://github.com/ORG/gaik-py.git@v0.1.0"
```

Install with optional dependencies:

```bash
pip install "git+https://github.com/ORG/gaik-py.git@v0.1.0#egg=gaik[pdf,html]"
```

Available extras:

- `pdf`: PDF parsing support (pypdf>=4)
- `html`: HTML parsing support (beautifulsoup4>=4.12, lxml>=5)
- `dev`: Development tools (pytest, ruff, mypy, build, twine)

**Requirements:** Python >=3.9

### TypeScript (gaik-ts)

Install directly from GitHub:

```bash
pnpm add github:ORG/gaik-ts#v0.1.0
```

Or with npm/yarn:

```bash
npm install github:ORG/gaik-ts#v0.1.0
yarn add github:ORG/gaik-ts#v0.1.0
```

**Requirements:** Node.js >=18

## Usage

### Python

```python
# Import from namespace packages
from gaik.parser import your_parser_function
from gaik.logger import your_logger_function
```

### TypeScript

```typescript
// Import from main entry or subpaths
import { parser } from "gaik-ts";
import { yourFunction } from "gaik-ts/parser";
```

## Demo Application

The Docker demo provides an environment where both libraries are pre-installed and ready to use:

```bash
cd gaik-demo
docker-compose up
```

Use this to test your shared code before deploying to other projects.

## Project Structure

```
gaik-toolkit/
├── gaik-py/           # Python library
│   └── src/gaik/
│       ├── parser/    # Parser modules
│       └── logger/    # Logger modules
├── gaik-ts/           # TypeScript library
│   ├── src/
│   │   ├── parser/    # Parser modules
│   │   └── logger/    # Logger modules
│   └── dist/          # Compiled output
└── gaik-demo/         # Docker demo application
```

## Workflow

1. **Develop**: Add reusable code to gaik-py or gaik-ts
2. **Test**: Use gaik-demo to verify functionality
3. **Share**: Install in other projects directly from GitHub
4. **Version**: Tag releases for stable snapshots
5. **Publish**: When ready, publish to PyPI/npm for wider distribution

## Benefits

- **No copy-paste**: Single source of truth for shared utilities
- **Version control**: Pin to specific versions or use latest
- **Modular**: Import only what you need with optional dependencies
- **Type-safe**: Full TypeScript and Python type support
- **Flexible**: Use from GitHub now, publish to registries later

## Development

### Python Development

```bash
cd gaik-py
pip install -e ".[dev]"
pytest
ruff check .
mypy src/
```

### TypeScript Development

```bash
cd gaik-ts
pnpm install
pnpm build
pnpm test
```

## Publishing (Future)

### PyPI

```bash
cd gaik-py
python -m build
twine upload dist/*
```

### npm

```bash
cd gaik-ts
pnpm publish
```

## License

MIT

## Documentation

For detailed specifications and user stories, see:

- [Requirements & User Stories](.kiro/specs/gaik-monorepo/requirements.md)
- [Design Document](.kiro/specs/gaik-monorepo/design.md)
- [Implementation Tasks](.kiro/specs/gaik-monorepo/tasks.md)

## Version

Current version: 0.1.0

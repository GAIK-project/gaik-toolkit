# Design Document

## Overview

GAIK (General AI Kit) is a monorepo containing two language-specific libraries and a demo application. The design focuses on providing minimal, working templates that serve as a foundation for future development.

### Key Design Principles

1. **Modularity**: Namespace/subpath exports for selective imports
2. **Minimal Dependencies**: Core packages have minimal required dependencies
3. **Type Safety**: Full type hints in Python and strict TypeScript
4. **GitHub-First**: Optimized for direct GitHub installation
5. **Template-Driven**: Stub implementations as starting points

## Architecture

### Monorepo Structure

```
gaik/
├── gaik-py/              # Python library
│   ├── src/gaik/
│   │   ├── __init__.py
│   │   ├── parser/
│   │   │   ├── __init__.py
│   │   │   ├── html.py
│   │   │   └── pdf.py
│   │   └── logger/
│   │       ├── __init__.py
│   │       └── base.py
│   ├── pyproject.toml
│   ├── README.md
│   └── LICENSE
│   # Note: tests/ directory can be added in the future if needed
│
├── gaik-ts/              # TypeScript library
│   ├── src/
│   │   ├── index.ts
│   │   ├── parser/
│   │   │   └── index.ts
│   │   └── logger/
│   │       └── index.ts
│   ├── package.json
│   ├── tsconfig.json
│   ├── README.md
│   └── LICENSE
│
└── gaik-demo/            # Demo application
    ├── Dockerfile
    ├── docker-compose.yml
    ├── app/
    │   ├── demo.py
    │   └── package.json
    └── README.md
```

## Components and Interfaces

### Python Library (gaik-py)

#### Package Configuration (pyproject.toml)

Uses Hatchling as build backend with optional dependencies:

```toml
[project]
name = "gaik"
version = "0.1.0"
dependencies = ["typing-extensions>=4.7; python_version<'3.11'"]

[project.optional-dependencies]
pdf = ["pypdf>=4"]
html = ["beautifulsoup4>=4.12", "lxml>=5"]
dev = ["ruff", "mypy", "build", "twine"]
```

#### Parser Module Templates

Simple stub implementations to be replaced with real logic:

```python
# src/gaik/parser/html.py
from dataclasses import dataclass
from typing import List

@dataclass
class HtmlChunk:
    text: str

def parse_html(html: str) -> List[HtmlChunk]:
    """Stub - replace with your implementation"""
    return [HtmlChunk(text=html.strip())]
```

```python
# src/gaik/parser/pdf.py
from dataclasses import dataclass
from typing import List

@dataclass
class PdfChunk:
    text: str
    page: int = 0

def parse_pdf(pdf_path: str) -> List[PdfChunk]:
    """Stub - replace with your implementation"""
    return [PdfChunk(text="TODO", page=1)]
```

#### Logger Module Template

```python
# src/gaik/logger/base.py
import logging

def get_logger(name: str = "gaik") -> logging.Logger:
    """Simple logger template"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

### TypeScript Library (gaik-ts)

#### Package Configuration (package.json)

ESM module with subpath exports:

```json
{
  "name": "gaik-ts",
  "version": "0.1.0",
  "type": "module",
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {
    ".": {
      "import": "./dist/index.js",
      "types": "./dist/index.d.ts"
    },
    "./parser": {
      "import": "./dist/parser/index.js",
      "types": "./dist/parser/index.d.ts"
    },
    "./logger": {
      "import": "./dist/logger/index.js",
      "types": "./dist/logger/index.d.ts"
    }
  },
  "scripts": {
    "build": "tsc -p tsconfig.json"
  }
}
```

#### TypeScript Configuration (tsconfig.json)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "bundler",
    "declaration": true,
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "skipLibCheck": true
  },
  "include": ["src"]
}
```

#### Parser Module Templates

```typescript
// src/parser/index.ts
export type HtmlChunk = {
  text: string;
};

export type PdfChunk = {
  text: string;
  page: number;
};

export function parseHtml(input: string): HtmlChunk[] {
  /** Stub - replace with your implementation */
  return [{ text: input.trim() }];
}

export function parsePdf(filePath: string): PdfChunk[] {
  /** Stub - replace with your implementation */
  return [{ text: "TODO", page: 1 }];
}
```

#### Logger Module Template

```typescript
// src/logger/index.ts
export type Logger = {
  info: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  debug: (...args: unknown[]) => void;
};

export function createLogger(name: string = "gaik"): Logger {
  /** Simple console logger template */
  return {
    info: (...args: unknown[]) => console.log("INFO", name, ...args),
    error: (...args: unknown[]) => console.error("ERROR", name, ...args),
    warn: (...args: unknown[]) => console.warn("WARN", name, ...args),
    debug: (...args: unknown[]) => console.debug("DEBUG", name, ...args),
  };
}
```

#### Main Entry Point

```typescript
// src/index.ts
export * as parser from "./parser/index.js";
export * as logger from "./logger/index.js";
```

### Demo Application (gaik-demo)

#### Docker Configuration

Multi-stage Dockerfile for efficient builds:

```dockerfile
# Stage 1: Build TypeScript
FROM node:18-alpine AS ts-builder
WORKDIR /build
COPY gaik-ts/package.json gaik-ts/tsconfig.json ./
COPY gaik-ts/src ./src
RUN npm install && npm run build

# Stage 2: Final image
FROM python:3.11-slim
WORKDIR /app

# Install Node.js
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

# Install gaik-py from local source
COPY gaik-py /tmp/gaik-py
RUN pip install /tmp/gaik-py && rm -rf /tmp/gaik-py

# Install gaik-ts
COPY --from=ts-builder /build/dist /usr/local/lib/gaik-ts/dist
COPY --from=ts-builder /build/package.json /usr/local/lib/gaik-ts/
RUN cd /usr/local/lib/gaik-ts && npm link

# Copy demo app
COPY gaik-demo/app ./app
WORKDIR /app

CMD ["python", "demo.py"]
```

#### docker-compose.yml

```yaml
version: "3.8"

services:
  demo:
    build:
      context: .
      dockerfile: gaik-demo/Dockerfile
    volumes:
      - ./gaik-demo/app:/app:ro
```

#### Demo Application

Simple Python script that demonstrates both libraries:

```python
# app/demo.py
import subprocess
from gaik.parser.html import parse_html
from gaik.logger.base import get_logger

def main():
    print("=== GAIK Demo ===\n")

    # Python examples
    logger = get_logger("demo")
    logger.info("Testing Python library")
    chunks = parse_html("<h1>Hello GAIK</h1>")
    logger.info(f"Parsed {len(chunks)} chunks")

    # TypeScript examples
    print("\nTesting TypeScript library...")
    subprocess.run(["node", "-e", """
        import('gaik-ts').then(gaik => {
            const log = gaik.logger.createLogger('demo');
            log.info('TypeScript library works!');
            const chunks = gaik.parser.parseHtml('<h1>Hello</h1>');
            log.info(`Parsed ${chunks.length} chunks`);
        });
    """])

if __name__ == "__main__":
    main()
```

## Data Models

### Python

```python
@dataclass
class HtmlChunk:
    text: str

@dataclass
class PdfChunk:
    text: str
    page: int = 0
```

### TypeScript

```typescript
type HtmlChunk = {
  text: string;
};

type PdfChunk = {
  text: string;
  page: number;
};

type Logger = {
  info: (...args: unknown[]) => void;
  error: (...args: unknown[]) => void;
  warn: (...args: unknown[]) => void;
  debug: (...args: unknown[]) => void;
};
```

## Error Handling

Error handling is minimal in templates. Add appropriate error handling as you implement real functionality:

- **Python**: Use standard exceptions (ImportError, FileNotFoundError, RuntimeError)
- **TypeScript**: Use Error class with descriptive messages

## Testing Strategy

No testing infrastructure is included initially to keep things simple. The demo application serves as a basic verification that the libraries work.

**Note**: Testing can be added in the future if needed (pytest for Python, vitest/jest for TypeScript).

## Installation and Usage

### Python

**Installation from GitHub**:

```bash
pip install "git+https://github.com/ORG/gaik-py.git@v0.1.0"
# With extras:
pip install "git+https://github.com/ORG/gaik-py.git@v0.1.0#egg=gaik[html,pdf]"
```

**Usage**:

```python
from gaik.parser.html import parse_html
from gaik.logger.base import get_logger

logger = get_logger()
chunks = parse_html("<h1>Hello</h1>")
logger.info(f"Parsed {len(chunks)} chunks")
```

### TypeScript

**Installation from GitHub**:

```bash
pnpm add github:ORG/gaik-ts#v0.1.0
# or npm/yarn
```

**Usage**:

```typescript
// Namespace import
import { parser, logger } from "gaik-ts";
const chunks = parser.parseHtml("<h1>Hello</h1>");

// Direct subpath import
import { parseHtml } from "gaik-ts/parser";
import { createLogger } from "gaik-ts/logger";

const log = createLogger();
const chunks = parseHtml("<h1>Hello</h1>");
log.info(`Parsed ${chunks.length} chunks`);
```

### Demo

```bash
docker-compose -f gaik-demo/docker-compose.yml up --build
```

## Future Extensibility

### Adding New Modules

**Python**:

1. Create directory under `src/gaik/` (e.g., `src/gaik/pipelines/`)
2. Add `__init__.py` with exports
3. Add optional dependencies to `pyproject.toml` if needed

**TypeScript**:

1. Create directory under `src/` (e.g., `src/pipelines/`)
2. Add `index.ts` with exports
3. Update `src/index.ts` to export new namespace
4. Add subpath to `package.json` exports map

### Publishing to Package Registries

**Python (PyPI)**:

```bash
python -m build
twine upload dist/*
```

**TypeScript (npm)**:

```bash
npm run build
npm publish
```

### Version Management

- Use semantic versioning
- Tag releases: `v0.1.0`, `v0.2.0`, etc.
- Keep Python and TypeScript versions independent
- Update version in `pyproject.toml` and `package.json` before tagging

## Design Decisions Summary

1. **Monorepo**: Easier demo development, shared documentation
2. **Minimal Dependencies**: Lightweight core, optional extras
3. **src-layout (Python)**: Prevents import issues
4. **ESM (TypeScript)**: Modern standard
5. **Stub Implementations**: Working templates for future development
6. **Dataclasses/Types**: Clean, type-safe data structures
7. **Simple Logging**: No external dependencies initially
8. **Multi-Stage Docker**: Smaller final image
9. **Subpath Exports**: Selective imports
10. **Template-First**: Foundation for growth, not full implementations

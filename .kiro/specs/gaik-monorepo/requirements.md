# Requirements Document

## Introduction

GAIK (General AI Kit) is a monorepo project that provides reusable components, pipelines, and utilities for both Python and TypeScript environments. The project consists of two separate libraries and a demo application:

- **gaik-py**: Python library with modular namespace structure
- **gaik-ts**: TypeScript/ESM library with subpath exports support
- **gaik-demo**: Docker-based demo application showcasing the toolkit

Both libraries are designed to be installed initially directly from GitHub and later published to PyPI and npm. The structure enables modular usage where users can import only the parts they need.

## Requirements

### Requirement 1: Python Library Basic Structure

**User Story:** As a Python developer, I want to install and use gaik-py from GitHub, so that I can access reusable parsers, loggers, and other utilities in my projects.

#### Acceptance Criteria

1. WHEN gaik-py repository is created THEN it SHALL use src-layout with namespace package structure under `src/gaik/`
2. WHEN project is configured THEN it SHALL use Hatchling as build backend with pyproject.toml
3. WHEN package is installed from GitHub THEN it SHALL be installable via `pip install "git+https://github.com/ORG/gaik-py.git@v0.1.0"`
4. WHEN importing modules THEN users SHALL be able to import using `from gaik.parser import parse_html` and `from gaik.logger import get_logger`
5. WHEN project structure is created THEN it SHALL include subdirectories: `src/gaik/parser/`, `src/gaik/logger/`, and `tests/`

### Requirement 2: Python Library Modularity and Dependencies

**User Story:** As a Python developer, I want to install only the dependencies I need, so that I don't bloat my environment with unnecessary packages.

#### Acceptance Criteria

1. WHEN pyproject.toml is configured THEN it SHALL define optional dependencies for `pdf`, `html`, and `dev` extras
2. WHEN user installs with extras THEN they SHALL be able to use `pip install gaik[pdf,html]` syntax
3. WHEN core package is installed THEN it SHALL have minimal required dependencies (only typing-extensions for Python <3.11)
4. WHEN optional dependencies are defined THEN pdf SHALL include pypdf>=4 and html SHALL include beautifulsoup4>=4.12 and lxml>=5
5. WHEN dev dependencies are defined THEN they SHALL include pytest, ruff, mypy, build, and twine

### Requirement 3: Python Library Parser Module (example template)

**User Story:** As a developer, I want example parser module templates, so that I have a foundation for building document parsers in the future.

#### Acceptance Criteria

1. WHEN gaik.parser.html module exists THEN it SHALL provide a stub `parse_html()` function that returns List[HtmlChunk] as an example
2. WHEN gaik.parser.pdf module exists THEN it SHALL provide a basic stub structure for future PDF parsing functionality
3. WHEN HtmlChunk is defined THEN it SHALL be a dataclass with at least a `text` field as a template
4. WHEN parser modules are imported THEN they SHALL have proper type hints for all public functions
5. WHEN parser module structure is created THEN it SHALL serve as a foundation for future full implementations

### Requirement 4: Python Library Logger Module (example template)

**User Story:** As a developer, I want an example logging interface template, so that I have a foundation for building logging utilities in the future.

#### Acceptance Criteria

1. WHEN gaik.logger.base module exists THEN it SHALL provide a basic `get_logger()` function as an example
2. WHEN get_logger is called THEN it SHALL return a configured Python logging.Logger instance with basic setup
3. WHEN logger is created THEN it SHALL have a StreamHandler with formatted output showing level, name, and message
4. WHEN logger is created THEN it SHALL default to INFO level
5. WHEN logger module structure is created THEN it SHALL serve as a foundation for future full implementations

### Requirement 5: TypeScript Library Basic Structure

**User Story:** As a TypeScript developer, I want to install and use gaik-ts from GitHub, so that I can access reusable utilities in my Node.js/TypeScript projects.

#### Acceptance Criteria

1. WHEN gaik-ts repository is created THEN it SHALL use ESM module format with `"type": "module"` in package.json
2. WHEN package.json is configured THEN it SHALL define exports map for main entry and subpaths (./parser, ./logger)
3. WHEN project is built THEN it SHALL compile TypeScript to dist/ directory with declaration files
4. WHEN package is installed from GitHub THEN it SHALL be installable via `pnpm add github:ORG/gaik-ts#v0.1.0`
5. WHEN importing modules THEN users SHALL be able to import using `import { parser } from "gaik-ts"` or `import { parseHtml } from "gaik-ts/parser"`

### Requirement 6: TypeScript Library Configuration

**User Story:** As a TypeScript developer, I want strict type checking and modern ES features, so that I can write safe and maintainable code.

#### Acceptance Criteria

1. WHEN tsconfig.json is configured THEN it SHALL target ES2022 with ES2022 modules
2. WHEN TypeScript is compiled THEN it SHALL generate declaration files alongside JavaScript
3. WHEN strict mode is enabled THEN it SHALL enforce all strict type checking options
4. WHEN module resolution is configured THEN it SHALL use "bundler" strategy
5. WHEN build script runs THEN it SHALL compile src/ to dist/ maintaining directory structure

### Requirement 7: TypeScript Library Parser Module (example template)

**User Story:** As a developer, I want example parser module templates in TypeScript, so that I have a foundation for building document parsers in the future.

#### Acceptance Criteria

1. WHEN gaik-ts/parser module exists THEN it SHALL export a stub `parseHtml()` function as an example
2. WHEN parseHtml is called THEN it SHALL return an array of HtmlChunk objects with basic implementation
3. WHEN HtmlChunk type is defined THEN it SHALL have at least a `text` property of type string as a template
4. WHEN parser module is imported THEN all exports SHALL have proper TypeScript type definitions
5. WHEN parser is accessed via main entry THEN it SHALL be available as `parser` namespace export

### Requirement 8: TypeScript Library Logger Module (example template)

**User Story:** As a developer, I want an example logging interface template in TypeScript, so that I have a foundation for building logging utilities in the future.

#### Acceptance Criteria

1. WHEN gaik-ts/logger module exists THEN it SHALL export a basic `createLogger()` function as an example
2. WHEN createLogger is called THEN it SHALL return an object with `info()` and `error()` methods with simple console output
3. WHEN logger methods are called THEN they SHALL output to console with level prefix and logger name
4. WHEN createLogger is called with no arguments THEN it SHALL default to "gaik" as logger name
5. WHEN logger is accessed via main entry THEN it SHALL be available as `logger` namespace export

### Requirement 9: Documentation and metadata

**User Story:** As a developer, I want clear documentation and proper licensing, so that I understand how to use the libraries and their terms.

#### Acceptance Criteria

1. WHEN each repository is created THEN it SHALL include a README.md with installation and usage examples
2. WHEN package metadata is defined THEN it SHALL include MIT license information
3. WHEN README is written THEN it SHALL document GitHub installation method and future PyPI/npm plans
4. WHEN README includes examples THEN it SHALL show import statements and basic usage for each module
5. WHEN project is configured THEN it SHALL specify minimum Python version (>=3.9) and Node version (>=18)

### Requirement 10: Version control and publishing readiness

**User Story:** As a maintainer, I want version tagging and build configuration ready, so that I can easily publish to PyPI and npm in the future.

#### Acceptance Criteria

1. WHEN initial version is set THEN it SHALL be 0.1.0 in both projects
2. WHEN Python project is configured THEN it SHALL include build and twine in dev dependencies for PyPI publishing
3. WHEN TypeScript project is configured THEN it SHALL include prepublishOnly script that runs build
4. WHEN package files are defined THEN Python SHALL include src/gaik in wheel and TypeScript SHALL include dist/ in npm package
5. WHEN .npmignore or files field is configured THEN it SHALL exclude source files and include only dist/, README, and LICENSE

### Requirement 11: Docker-based Demo Application

**User Story:** As a developer evaluating GAIK, I want a Docker-based demo application, so that I can quickly test and explore the toolkit's capabilities without setting up a development environment.

#### Acceptance Criteria

1. WHEN gaik-demo directory is created THEN it SHALL contain a Dockerfile and docker-compose.yml
2. WHEN demo application is built THEN it SHALL install both gaik-py and gaik-ts from local sources
3. WHEN demo container runs THEN it SHALL provide a simple web interface or CLI that demonstrates parser and logger functionality
4. WHEN demo is accessed THEN it SHALL show examples of using both Python and TypeScript modules
5. WHEN demo README is provided THEN it SHALL include instructions for building and running with `docker-compose up`
6. WHEN demo application is structured THEN it SHALL include example scripts showing real-world usage patterns
7. WHEN demo is containerized THEN it SHALL use multi-stage builds to keep the final image size reasonable

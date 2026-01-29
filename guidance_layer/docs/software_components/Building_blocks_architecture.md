# Software Component Architecture Guide

This document describes the architecture patterns used for creating software components in the GAIK Toolkit. Use this as a reference when creating new software components.

## Table of Contents

1. [Overview](#overview)
2. [Software Component Structure](#software-component-structure)
3. [Core Components](#core-components)
4. [Package Configuration Patterns](#package-configuration-patterns)
5. [Documentation Standards](#documentation-standards)
6. [Testing Patterns](#testing-patterns)
7. [Creating a New Software Component: Step-by-Step](#creating-a-new-software-component-step-by-step)

---

## Overview

Software components are **modular, standalone components** that can be installed independently or as part of the full GAIK toolkit. Each software component:

- Solves a specific problem domain (extraction, parsing, transcription, classification, etc.)
- Can be installed with minimal dependencies using optional extras: `pip install gaik[component_name]`
- Uses graceful import fallbacks to prevent hard failures when optional dependencies are missing
- Follows consistent API patterns (configuration, main classes, utilities)
- Includes comprehensive documentation and examples

---

## Software Component Structure

### Directory Layout

Each software component follows this structure:

```
implementation_layer/implementation_layer/src/gaik/software_components/<component_name>/
├── __init__.py                  # Public API with graceful imports
├── <main_module>.py             # Core implementation
├── <utility_module>.py          # Helper functions (optional)
├── README.md                    # Quick reference documentation
├── tests/                       # Unit tests (if needed)
│   └── .gitkeep                 # Placeholder if no tests yet
├── requirements/                # Dependency documentation (optional)
└── Architectures/               # Design diagrams (optional)
```

### Supporting Files

```
implementation_layer/examples/software_components/<component_name>/
├── example_1.py                 # Basic usage example
├── example_2.py                 # Advanced usage example
└── ...

guidance_layer/docs/software_components/
├── <component_name>.md     # Comprehensive documentation
└── <component_name>/       # Subdirectory if multiple docs needed
    ├── README.md
    └── ...
```

---

## Core Components

### 1. Package Initialization (`__init__.py`)

The `__init__.py` file is critical for:
- Defining the public API
- Implementing graceful import fallbacks for optional dependencies
- Providing comprehensive module documentation

#### Pattern A: Simple Imports (No Optional Dependencies)

Used by: `extractor`, `doc_classifier`

```python
"""
<Software Component Name>

Brief description of what this software component does.

Main Classes:
    - ClassName1: Description
    - ClassName2: Description

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration
    - create_openai_client: Create OpenAI client from config

Utilities:
    - utility_function1: Description
    - utility_function2: Description

Example:
    >>> from gaik.software_components.<name> import MainClass, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> instance = MainClass(config=config)
    >>> result = instance.method("input.txt")
"""

from gaik.software_components.config import create_openai_client, get_openai_config

from .main_module import MainClass, helper_function

__all__ = [
    # Main API
    "MainClass",
    # Configuration
    "get_openai_config",
    "create_openai_client",
    # Utilities
    "helper_function",
]

__version__ = "0.1.0"
```

#### Pattern B: Optional Imports (With Graceful Fallback)

Used by: `transcriber`, `parsers`

```python
"""
<Software Component Name>

Brief description and examples.
"""

__all__ = []

# Configuration (requires openai, python-dotenv)
try:
    from gaik.software_components.config import create_openai_client, get_openai_config

    __all__.extend(["get_openai_config", "create_openai_client"])
except ImportError:
    pass

# Main functionality (requires specific dependencies)
try:
    from .main_module import (
        MainClass,
        UtilityFunction,
        CONSTANT,
    )

    __all__.extend([
        "MainClass",
        "UtilityFunction",
        "CONSTANT",
    ])
except ImportError:
    pass
```

**Key Points:**
- Start with empty `__all__` list
- Use try-except blocks for each set of related imports
- Silently pass on ImportError (graceful degradation)
- Extend `__all__` in each successful import block
- Group imports by dependency requirements

### 2. Shared Configuration (`config.py`)

All software components use a shared configuration module:

**Location:** `implementation_layer/implementation_layer/src/gaik/software_components/config.py`

**API:**
```python
from gaik.software_components.config import get_openai_config, create_openai_client

# Get configuration dictionary
config = get_openai_config(use_azure=True)  # or False for standard OpenAI

# Create client instance
client = create_openai_client(config)
```

**Configuration Structure:**
```python
{
    "use_azure": bool,
    "api_key": str,
    "azure_endpoint": str,           # Azure only
    "azure_audio_endpoint": str,     # Azure only
    "api_version": str,              # Azure only
    "model": str,
    "transcription_model": str,      # For audio/video processing
}
```

### 3. Main Module Implementation

Each software component has one or more implementation modules with:

#### Class Design Patterns

```python
"""Module docstring describing the functionality."""

from typing import Any, Dict, List, Optional
from pathlib import Path
import json
from pydantic import BaseModel

# Import shared configuration
from gaik.software_components.config import create_openai_client, get_openai_config


class ResultModel(BaseModel):
    """Pydantic model for type-safe results."""
    field1: str
    field2: int

    def save(self, output_dir: str) -> None:
        """Save results to directory."""
        pass


class MainClass:
    """
    Main software component class.

    Args:
        config: Configuration from get_openai_config()
        model: Optional model override
        **kwargs: Additional configuration options

    Example:
        >>> config = get_openai_config(use_azure=True)
        >>> instance = MainClass(config=config)
        >>> result = instance.process("input.txt")
    """

    def __init__(
        self,
        config: dict,
        model: Optional[str] = None,
        **kwargs
    ):
        self.config = config
        self.model = model or config.get("model")
        self.client = create_openai_client(config)

    def process(self, input_data: Any, **options) -> ResultModel:
        """
        Main processing method.

        Args:
            input_data: Input to process
            **options: Additional processing options

        Returns:
            ResultModel with processing results
        """
        # Implementation
        pass

    def _with_retries(self, func, *args, **kwargs):
        """Internal retry wrapper with exponential backoff."""
        import time
        from openai import RateLimitError, APITimeoutError, APIError

        max_retries = 4
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except (RateLimitError, APITimeoutError, APIError) as e:
                if attempt == max_retries - 1:
                    raise
                wait_time = 2 ** attempt
                print(f"Retry {attempt + 1}/{max_retries} after {wait_time}s...")
                time.sleep(wait_time)


# Convenience functions
def convenience_function(input_path: str, **options) -> ResultModel:
    """
    Convenience wrapper for one-shot processing.

    Args:
        input_path: Path to input file
        **options: Options passed to MainClass

    Returns:
        Processing results
    """
    config = get_openai_config()
    instance = MainClass(config=config)
    return instance.process(input_path, **options)
```

#### Key Implementation Patterns

1. **Configuration Dependency Injection**
   - Accept `config` dict in constructor
   - Create client using `create_openai_client(config)`
   - Allow model overrides via parameters

2. **Retry Logic**
   - Use `_with_retries()` wrapper for API calls
   - Handle: RateLimitError, APITimeoutError, APIError
   - Exponential backoff: 2^attempt seconds
   - Default 4 retry attempts

3. **Pydantic Result Models**
   - Use Pydantic for type-safe results
   - Include helper methods (save, export, etc.)
   - Provide clear field documentation

4. **Convenience Functions**
   - Provide simple one-shot functions for common use cases
   - Create config internally with defaults
   - Wrap main class instantiation

---

## Package Configuration Patterns

### 1. Dependencies in `pyproject.toml`

```toml
[project]
name = "gaik"
dependencies = [
    # Core runtime requirements shared across all installs
    "pydantic>=2.12.4",
    "python-dotenv>=1.0.0",
    "openai>=1.58.0",
]

[project.optional-dependencies]
# Software component: <name>
<component_name> = [
    "dependency1>=1.0.0",
    "dependency2>=2.0.0",
]

# All features
all = [
    "gaik[<component_name>]",
    # ... other software components
]
```

**Dependency Guidelines:**
- **Core dependencies**: Only pydantic, python-dotenv, openai
- **Optional dependencies**: Specific to each software component
- Use version pins (`>=X.Y.Z`) for minimum compatibility
- Group related dependencies together

### 2. Registration in Main Package

**File:** `implementation_layer/implementation_layer/src/gaik/software_components/__init__.py`

```python
"""Software components namespace for gaik components."""

__all__ = [
    "config",
    "extractor",
    "transcriber",
    "parsers",
    "doc_classifier",
    "<new_component>",  # Add here
]
```

### 3. Import Test Registration

**File:** `implementation_layer/unit_tests/test_imports.py`

```python
def test_<new_component>_import():
    """Test that <new_component> module can be imported."""
    from gaik.software_components import <new_component>

    assert <new_component> is not None
```

---

## Documentation Standards

### 1. Module Documentation (`guidance_layer/docs/software_components/<name>.md`)

```markdown
# <Software Component Name>

Brief description of what this software component does.

## Installation

\`\`\`bash
pip install gaik[<component_name>]
\`\`\`

**Note:** List any special requirements or API access needed

---

## Quick Start

\`\`\`python
from gaik.software_components.<name> import MainClass, get_openai_config

# Configure
config = get_openai_config(use_azure=True)

# Use
instance = MainClass(config=config)
result = instance.process("input.txt")

print(result)
\`\`\`

---

## Features

- **Feature 1** - Description
- **Feature 2** - Description
- **Feature 3** - Description

---

## Basic API

### MainClass

\`\`\`python
from gaik.software_components.<name> import MainClass

instance = MainClass(
    config: dict,              # From get_openai_config()
    model: str | None = None   # Optional model override
)

# Process data
result = instance.process(
    input_data,
    option1=value1,
    option2=value2
)
\`\`\`

### Configuration

\`\`\`python
from gaik.software_components.<name> import get_openai_config

# Azure OpenAI (default)
config = get_openai_config(use_azure=True)

# Standard OpenAI
config = get_openai_config(use_azure=False)
\`\`\`

---

## Examples

### Example 1: Basic Usage

\`\`\`python
# Code example
\`\`\`

### Example 2: Advanced Usage

\`\`\`python
# Code example
\`\`\`

---

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| param1 | str | None | Description |
| param2 | bool | True | Description |

---

## Return Types

### ResultModel

\`\`\`python
class ResultModel:
    field1: str
    field2: int

    def save(self, output_dir: str) -> None:
        """Save results."""
\`\`\`

---

## Advanced Usage

### Custom Configuration

### Error Handling

### Performance Optimization

---

## Troubleshooting

### Common Issues

**Issue 1**: Description
- Solution

**Issue 2**: Description
- Solution

---

## API Reference

[Link to full API documentation if available]
```

### 2. Inline README (`implementation_layer/implementation_layer/src/gaik/software_components/<name>/README.md`)

Provide a quick reference version:

```markdown
# <Software Component Name>

Brief 1-2 sentence description.

## Installation

\`\`\`bash
pip install gaik[<name>]
\`\`\`

## Quick Example

\`\`\`python
from gaik.software_components.<name> import MainClass, get_openai_config

config = get_openai_config(use_azure=True)
instance = MainClass(config=config)
result = instance.process("input.txt")
\`\`\`

## Documentation

See [full documentation](../../../guidance_layer/docs/software_components/<name>.md) for detailed usage.
```

---

## Testing Patterns

### 1. Import Tests

**Location:** `implementation_layer/unit_tests/test_imports.py`

```python
def test_<component>_import():
    """Test that <component> module can be imported."""
    from gaik.software_components import <component>

    assert <component> is not None
```

### 2. Unit Tests (Optional)

**Location:** `implementation_layer/implementation_layer/src/gaik/software_components/<name>/tests/`

```python
"""Unit tests for <component_name>."""

import pytest
from gaik.software_components.<name> import MainClass, get_openai_config


def test_initialization():
    """Test MainClass initialization."""
    config = get_openai_config()
    instance = MainClass(config=config)
    assert instance is not None


def test_processing():
    """Test basic processing."""
    config = get_openai_config()
    instance = MainClass(config=config)
    result = instance.process("test input")
    assert result is not None
```

### 3. Integration Tests

**Location:** `implementation_layer/unit_tests/test_<component>_integration.py`

```python
"""Integration tests for <component_name>."""

import pytest
from gaik.software_components.<name> import MainClass


@pytest.mark.integration
def test_end_to_end_workflow():
    """Test complete workflow."""
    # Test implementation
    pass
```

---

## Creating a New Software Component: Step-by-Step

### Step 1: Create Directory Structure

```bash
mkdir -p implementation_layer/implementation_layer/src/gaik/software_components/<name>
mkdir -p implementation_layer/implementation_layer/src/gaik/software_components/<name>/tests
mkdir -p implementation_layer/examples/software_components/<name>
mkdir -p guidance_layer/docs/software_components
```

### Step 2: Create Core Files

1. **`implementation_layer/implementation_layer/src/gaik/software_components/<name>/__init__.py`**
   - Follow Pattern A or Pattern B from above
   - Define public API in `__all__`
   - Add comprehensive docstring

2. **`implementation_layer/implementation_layer/src/gaik/software_components/<name>/<main_module>.py`**
   - Implement main class(es)
   - Use `get_openai_config()` and `create_openai_client()`
   - Add retry logic with `_with_retries()`
   - Use Pydantic models for results

3. **`implementation_layer/implementation_layer/src/gaik/software_components/<name>/README.md`**
   - Quick reference documentation
   - Installation instructions
   - Basic example

### Step 3: Update Package Configuration

1. **`pyproject.toml`**
   ```toml
   [project.optional-dependencies]
   <name> = [
       "dependency1>=1.0.0",
       "dependency2>=2.0.0",
   ]
   ```

2. **`implementation_layer/implementation_layer/src/gaik/software_components/__init__.py`**
   ```python
   __all__ = [
       # ... existing
       "<name>",
   ]
   ```

3. **`implementation_layer/unit_tests/test_imports.py`**
   ```python
   def test_<name>_import():
       """Test that <name> module can be imported."""
       from gaik.software_components import <name>
       assert <name> is not None
   ```

### Step 4: Create Documentation

1. **`guidance_layer/docs/software_components/<name>.md`**
   - Follow documentation template above
   - Include installation, quick start, features, API reference
   - Add multiple examples
   - Document all configuration options

### Step 5: Create Examples

1. **`implementation_layer/examples/software_components/<name>/example_1.py`**
   ```python
   """
   Example 1: Basic usage of <name>.

   This script demonstrates how to:
   1. Configure the client
   2. Use the main class
   3. Process results
   """

   import sys
   from pathlib import Path
   from dotenv import load_dotenv

   load_dotenv(Path(__file__).parent.parent.parent / ".env")
   sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

   from gaik.software_components.<name> import MainClass, get_openai_config

   if __name__ == "__main__":
       print("=" * 80)
       print("<NAME> - EXAMPLE USAGE")
       print("=" * 80)

       config = get_openai_config(use_azure=True)
       instance = MainClass(config=config)
       result = instance.process("test input")

       print("\nResults:")
       print(result)
   ```

### Step 6: Test the Software Component

1. **Test import**
   ```bash
   pytest implementation_layer/unit_tests/test_imports.py::test_<name>_import
   ```

2. **Test installation**
   ```bash
   pip install -e ".[<name>]"
   python implementation_layer/examples/software_components/<name>/example_1.py
   ```

3. **Test in isolation**
   ```bash
   pip install gaik[<name>]
   python -c "from gaik.software_components.<name> import MainClass; print('OK')"
   ```

### Step 7: Update Main README (Optional)

Add to the main `README.md` if this is a major new feature:

```markdown
### <Software Component Name>

Brief description.

\`\`\`bash
pip install gaik[<name>]
\`\`\`

[Documentation](guidance_layer/docs/software_components/<name>.md) | [Examples](implementation_layer/examples/software_components/<name>/)
```

---

## Design Principles

### 1. Modularity
- Each software component is independently installable
- Minimal core dependencies
- Optional features via extras

### 2. Consistency
- Uniform API patterns (config, classes, utilities)
- Shared configuration system
- Common retry and error handling

### 3. Type Safety
- Full type hints throughout
- Pydantic models for validation
- PEP 561 compliance (py.typed marker)

### 4. Graceful Degradation
- Optional imports with try-except
- Helpful error messages when dependencies missing
- No hard failures on import

### 5. Developer Experience
- Comprehensive documentation
- Multiple examples (basic to advanced)
- Clear error messages
- Convenience functions for common use cases

### 6. Production Ready
- Retry logic with exponential backoff
- Timeout handling
- Structured logging (where applicable)
- Result serialization (JSON export)

---

## Common Patterns Reference

### Pattern: Retry Logic

```python
def _with_retries(self, func, *args, **kwargs):
    """Retry API calls with exponential backoff."""
    import time
    from openai import RateLimitError, APITimeoutError, APIError

    max_retries = 4
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (RateLimitError, APITimeoutError, APIError) as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt
            print(f"Retry {attempt + 1}/{max_retries} after {wait_time}s: {e}")
            time.sleep(wait_time)
```

### Pattern: Result Model

```python
from pydantic import BaseModel
from typing import Optional
import json
from pathlib import Path

class ProcessingResult(BaseModel):
    """Type-safe result container."""

    field1: str
    field2: int
    field3: Optional[float] = None

    def save(self, output_dir: str, filename: str = "result.json") -> None:
        """Save result to JSON file."""
        output_path = Path(output_dir) / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, default=str)
```

### Pattern: Convenience Function

```python
def process_file(
    file_path: str,
    use_azure: bool = True,
    **options
) -> ProcessingResult:
    """
    One-shot convenience function.

    Args:
        file_path: Path to input file
        use_azure: Use Azure OpenAI or standard OpenAI
        **options: Additional processing options

    Returns:
        Processing result
    """
    config = get_openai_config(use_azure=use_azure)
    processor = MainClass(config=config)
    return processor.process(file_path, **options)
```

---

## Checklist for New Software Component

- [ ] Directory structure created
- [ ] `__init__.py` with public API and docstring
- [ ] Main implementation module(s)
- [ ] Optional dependencies in `pyproject.toml`
- [ ] Registered in `implementation_layer/implementation_layer/src/gaik/software_components/__init__.py`
- [ ] Import test in `implementation_layer/unit_tests/test_imports.py`
- [ ] Full documentation in `guidance_layer/docs/software_components/<name>.md`
- [ ] Quick reference README in module directory
- [ ] At least 2 examples in `implementation_layer/examples/software_components/<name>/`
- [ ] Tests pass: `pytest implementation_layer/unit_tests/test_imports.py`
- [ ] Can be installed: `pip install gaik[<name>]`
- [ ] Examples run successfully
- [ ] Follows all design patterns and conventions
- [ ] Uses shared `config.py` for OpenAI/Azure setup
- [ ] Includes retry logic for API calls
- [ ] Uses Pydantic models for results
- [ ] Provides convenience functions

---

## Questions or Issues?

If you have questions about creating software components:
1. Review existing software components: `extractor`, `transcriber`, `parsers`, `doc_classifier`
2. Check the examples in `implementation_layer/examples/software_components/`
3. Refer to this architecture guide
4. Open an issue on GitHub: https://github.com/GAIK-project/gaik-toolkit/issues

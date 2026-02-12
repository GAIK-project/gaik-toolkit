# Extractor Examples

This folder contains multiple examples demonstrating how to use the Extractor component to extract structured data from text using plain-language field requirements.

## Files

- `extraction_example_1.py` - Basic extraction with simple field definitions
- `extraction_example_2.py` - Advanced extraction with constraints and validation rules
- `extraction_example_3.py` - Extraction with custom field types and options
- `extraction_example_4.py` - Complex extraction scenario with nested structures
- `input/` - Sample input documents for testing
- `saved_project_schema.py` - Example of reusing a generated schema across multiple extractions

## What These Examples Show

- How to define extraction fields in plain language without writing schemas
- How to specify field constraints, allowed values, and validation rules
- How to generate and reuse Pydantic schemas for consistent extraction
- How to handle various data types and complex field requirements

## Usage

```bash
# Run individual examples
python extraction_example_1.py
python extraction_example_2.py
python extraction_example_3.py
python extraction_example_4.py
```

## Related Documentation

- [Extractor Component](../../../src/gaik/software_components/extractor)
- [Software Components Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-components#extractor)

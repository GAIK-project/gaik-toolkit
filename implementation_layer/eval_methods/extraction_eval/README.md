# Extraction Evaluation

Evaluation methods for assessing structured data extraction quality.

## Purpose

Evaluate the accuracy and completeness of data extracted by `SchemaGenerator` and `DataExtractor` software components.

## Metrics

- **Field Accuracy**: Percentage of correctly extracted fields
- **Schema Quality**: Appropriateness of generated schemas
- **Type Correctness**: Accuracy of data type inference
- **Completeness**: Percentage of required fields successfully extracted
- **Precision & Recall**: For nested structures and lists

## Evaluation Approaches

- **Ground Truth Comparison**: Compare extracted data against manually labeled datasets
- **Cross-Document Consistency**: Evaluate consistency across similar documents
- **LLM-as-Judge**: Use language models to assess extraction quality
- **Schema Validation**: Pydantic model validation results

## Related Components

- `SchemaGenerator` software component
- `DataExtractor` software component
- `DocumentsToStructuredData` software module
- `AudioToStructuredData` software module

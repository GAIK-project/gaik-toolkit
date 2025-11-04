# GAIK Examples

Example scripts demonstrating GAIK library usage with multiple LLM providers.

## Available Examples

### 1. `test_gaik_installation.py`
**Quick test without API calls** - Perfect for:
- Verifying installation
- Understanding the API structure
- Testing provider registry and LangChain integration

```bash
python test_gaik_installation.py
```

### 2. `test_real_extraction.py`
**Real multi-provider extraction** - Demonstrates:
- Simple extraction with OpenAI, Anthropic, Google
- Batch processing with `dynamic_extraction_workflow`
- Provider switching

**Setup:**

Choose your provider(s) and set API key:

```bash
# OpenAI (default)
export OPENAI_API_KEY='sk-...'

# Anthropic Claude
export ANTHROPIC_API_KEY='sk-ant-...'

# Google Gemini
export GOOGLE_API_KEY='...'

# Azure OpenAI
export AZURE_OPENAI_API_KEY='...'
export AZURE_OPENAI_ENDPOINT='https://your-resource.openai.azure.com/'
```

**Run:**
```bash
python test_real_extraction.py
```

The script automatically detects available API keys and runs tests for those providers.

## More Information

- [Main Documentation](../gaik-py/README.md)
- [GitHub Repository](https://github.com/GAIK-project/toolkit-shared-components)

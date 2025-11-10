# Vision Examples

## Setup
```bash
pip install gaik[vision]
```

## Environment
```powershell
# OpenAI
$env:OPENAI_API_KEY='sk-...'

# Azure OpenAI
$env:AZURE_API_KEY='...'
$env:AZURE_ENDPOINT='https://...'
$env:AZURE_DEPLOYMENT='gpt-4o'
```

## Files
- `demo_vision_simple.py` - Basic PDF→Markdown conversion
- `demo_vision_parser.py` - CLI with advanced options
- `WEF-page-10.pdf` - Sample PDF for testing

## Usage
```bash
# Simple
python demo_vision_simple.py

# CLI
python demo_vision_parser.py invoice.pdf
python demo_vision_parser.py invoice.pdf --output result.md --dpi 300
python demo_vision_parser.py invoice.pdf --openai  # Use OpenAI instead of Azure
```

## Configuration
```python
# Azure (default)
config = get_openai_config(use_azure=True)

# OpenAI
config = get_openai_config(use_azure=False)
```

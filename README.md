# Web App Builder - Static Website Generator

A desktop application built with PySide6 that uses GPT4All to generate professional static websites (HTML, CSS, JS). Designed for non-technical users. Live preview powered by Qt WebEngine.

## Features
- Local LLM via GPT4All with model picker and auto-download
- Premium blue/black gradient UI with left chat history, center interaction, right live preview
- Impressive progress indicators and step-by-step generation
- GitHub Pages-ready output

## Requirements
- Python 3.9+
- Linux/macOS/Windows supported

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

## Run
### Option 1: Direct run (may show CUDA warnings)
```bash
python web_app_builder.py
```

### Option 2: CPU-only mode (recommended)
```bash
python run_with_cpu.py
```

## Troubleshooting

### CUDA Errors
If you see CUDA-related errors like "Failed to load llamamodel-mainline-cuda.dll", use the CPU-only wrapper:
```bash
python run_with_cpu.py
```

### No Models Found
1. Click "Refresh Models" to load available models
2. Or add a local `.gguf` model file:
   - Click "Add Local Model" 
   - Select your `.gguf` file
   - Click "Refresh Models"

### Model Download Issues
- Models are cached in the `models/` folder
- Click "Open Models Folder" to view downloaded models
- Large models may take time to download

## Output Structure
```
output_projects/
└── {project_name}/
    ├── index.html
    ├── styles.css
    ├── script.js
    └── assets/
```

## Notes
- First run of a new model will download it. This may take time depending on bandwidth.
- All websites are static and suitable for GitHub Pages.
- The app runs in CPU-only mode by default to avoid CUDA compatibility issues.
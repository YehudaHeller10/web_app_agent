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
```bash
python web_app_builder.py
```

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
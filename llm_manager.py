from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

import requests

try:
	from gpt4all import GPT4All
except Exception:  # pragma: no cover - allow app to run without immediate import failure
	GPT4All = None  # type: ignore


MODEL_SOURCES = [
	"https://gpt4all.io/models/models.json",
	"https://raw.githubusercontent.com/nomic-ai/gpt4all/main/models/models.json",
]

BASE_DIR = Path(__file__).parent.resolve()
DEFAULT_MODEL_DIR = BASE_DIR / "models"
DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ModelInfo:
	name: str
	filename: str
	filesize: int
	url: str
	description: str
	license: str


class LLMManager:
	def __init__(self, model_dir: Path = DEFAULT_MODEL_DIR) -> None:
		self.model_dir: Path = model_dir
		self._models_cache: List[ModelInfo] = []

	def _scan_local_models(self) -> List[ModelInfo]:
		models: List[ModelInfo] = []
		for path in sorted(self.model_dir.glob("*.gguf")):
			try:
				size = path.stat().st_size
				models.append(ModelInfo(
					name=path.stem,
					filename=path.name,
					filesize=size,
					url="",
					description="Local model",
					license="",
				))
			except Exception:
				continue
		return models

	def list_available_models(self, prioritize_code: bool = True) -> List[ModelInfo]:
		# Always include local models
		local = self._scan_local_models()
		if self._models_cache:
			# merge latest local with cached remotes
			cached = [m for m in self._models_cache if m.filename not in {lm.filename for lm in local}]
			return local + cached
		models: List[ModelInfo] = []
		for src in MODEL_SOURCES:
			try:
				resp = requests.get(src, timeout=15)
				resp.raise_for_status()
				data = resp.json()
				for item in data:
					filename = item.get("filename") or item.get("fname") or ""
					if not filename.endswith(".gguf"):
						continue
					name = item.get("name") or item.get("model") or filename
					desc = item.get("description") or item.get("info") or ""
					url = item.get("url") or item.get("download_url") or item.get("download") or ""
					filesize = int(item.get("filesize") or item.get("size") or 0)
					license_str = item.get("license", "")
					models.append(ModelInfo(name=name, filename=filename, filesize=filesize, url=url, description=desc, license=license_str))
			except Exception:
				continue
		# Prefer smaller code-capable models
		def score(m: ModelInfo) -> int:
			is_code = int(bool(re.search(r"code|coder|deepseek|starcoder|replit", m.name.lower()))) if prioritize_code else 0
			size_score = 0
			if m.filesize:
				if m.filesize < 1_500_000_000:
					size_score = 1
				elif m.filesize < 4_500_000_000:
					size_score = 3
				elif m.filesize < 8_000_000_000:
					size_score = 2
				else:
					size_score = 0
			return is_code * 10 + size_score
		models.sort(key=score, reverse=True)
		# Deduplicate by filename and merge local first
		seen = set()
		merged: List[ModelInfo] = []
		for m in local + models:
			if m.filename in seen:
				continue
			seen.add(m.filename)
			merged.append(m)
		self._models_cache = merged
		return merged

	def is_downloaded(self, model: ModelInfo) -> bool:
		return (self.model_dir / model.filename).exists()

	def download_model(self, model: ModelInfo, progress: Optional[Callable[[int, int], None]] = None) -> Path:
		dest = self.model_dir / model.filename
		if dest.exists():
			return dest
		if not model.url:
			raise RuntimeError("Model URL not available for download")
		self.model_dir.mkdir(parents=True, exist_ok=True)
		with requests.get(model.url, stream=True, timeout=30) as r:
			r.raise_for_status()
			total = int(r.headers.get("content-length", model.filesize or 0))
			downloaded = 0
			with open(dest, "wb") as f:
				for chunk in r.iter_content(chunk_size=1024 * 1024):
					if chunk:
						f.write(chunk)
						downloaded += len(chunk)
						if progress:
							progress(downloaded, total)
		return dest

	def generate_site(self, prompt: str, model: ModelInfo, step_callback: Optional[Callable[[str], None]] = None, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
		if GPT4All is None:
			raise RuntimeError("gpt4all package not installed")
		model_path = str(self.model_dir / model.filename)
		if not Path(model_path).exists():
			raise RuntimeError(f"Model file not found: {model_path}")
		
		if step_callback:
			step_callback("planning")
		if progress_callback:
			progress_callback("🎯 **Planning Phase**\n\nI'm analyzing your request: *" + prompt + "*\n\nLet me break this down and plan the website structure...")
		
		# Enhanced system prompt with step-by-step explanations and Tailwind usage
		system = (
			"You are a senior web developer creating a complete static website. "
			"Explain your process step by step as you work, then provide the final code. "
			"Use Tailwind CSS via CDN for professional styling, but also include a styles.css file for custom overrides. "
			"In the HTML <head>, include the Tailwind CDN script and also link to styles.css and script.js. "
			"Format your response like this:\n\n"
			"🎨 **Design Phase**\n[Explain your design decisions]\n\n"
			"⚙️ **Implementation Phase**\n[Explain what you're building]\n\n"
			"📝 **Final Code**\n```json\n{\"html\": \"...\", \"css\": \"...\", \"js\": \"...\"}\n```\n\n"
			"Use modern HTML5 semantic tags, responsive design, Tailwind utility classes, and clean ES6 JavaScript."
		)
		
		user = (
			f"Create a website for: {prompt}\n\n"
			"Requirements:\n"
			"- Single-page index.html\n"
			"- Include Tailwind CSS via CDN in <head>\n"
			"- Also include links to styles.css and script.js\n"
			"- Use Tailwind classes for a premium, professional design\n"
			"- Keep custom CSS minimal and scoped for overrides\n"
			"- Modern, responsive design and accessible JS\n\n"
			"Please explain your process as you work."
		)
		
		if step_callback:
			step_callback("design")
		if progress_callback:
			progress_callback("🎨 **Design Phase**\n\nNow I'm designing the visual layout and user experience...")
		
		try:
			llm = GPT4All(
				model_name=model_path, 
				allow_download=False, 
				device='cpu',
				use_mlock=False,
				use_mmap=True,
				threads=4
			)
			
			if step_callback:
				step_callback("html")
			if progress_callback:
				progress_callback("⚙️ **Implementation Phase**\n\nGenerating the HTML structure, CSS styles, and JavaScript functionality...")
			
			response = llm.generate(
				f"SYSTEM:\n{system}\nUSER:\n{user}\nASSISTANT:",
				temp=0.1,
				max_tokens=4096,
			)
			llm.close()
			
			if progress_callback:
				progress_callback("📝 **Final Code**\n\nExtracting and organizing the generated code...")
				
		except Exception as e:
			raise RuntimeError(f"Model generation failed: {str(e)}")
		
		# Try parse JSON
		try:
			data = self._extract_json(response)
			html = data.get("html", "")
			css = data.get("css", "")
			js = data.get("js", "")
		except Exception:
			# Fallback naive splits
			html, css, js = self._fallback_sections(response)
		
		if progress_callback:
			progress_callback("✅ **Website Ready!**\n\nYour website has been generated successfully! The files are being saved and the preview will update shortly.")
		
		return {"html": html, "css": css, "js": js}

	def _extract_json(self, text: str) -> Dict[str, str]:
		m = re.search(r"\{[\s\S]*\}", text)
		if not m:
			raise ValueError("No JSON found")
		return json.loads(m.group(0))

	def _fallback_sections(self, text: str) -> tuple[str, str, str]:
		# Heuristics to split content
		parts = re.split(r"(?im)^\s*(?:HTML|CSS|JS|JavaScript)\s*:?\s*$", text)
		if len(parts) >= 4:
			return parts[1].strip(), parts[2].strip(), parts[3].strip()
		# As a last resort, wrap everything in a simple template
		boiler_html = """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Generated Site</title><link rel=\"stylesheet\" href=\"styles.css\"></head><body><main><h1>Your Site</h1><p>Content could not be parsed cleanly.</p></main><script src=\"script.js\"></script></body></html>"""
		return boiler_html, "body{font-family:system-ui;}\n", "console.log('site ready');\n"
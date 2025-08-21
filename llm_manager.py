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

	def generate_site(self, prompt: str, model: ModelInfo, step_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
		if GPT4All is None:
			raise RuntimeError("gpt4all package not installed")
		model_path = str(self.model_dir / model.filename)
		if step_callback:
			step_callback("planning")
		# Instruct model to return strict JSON
		system = (
			"You are a senior web developer generating a complete static website. "
			"Return ONLY a compact JSON object with keys: html, css, js. "
			"Do not include markdown fences. Use modern HTML5 semantic tags, responsive CSS, and clean ES6 JS."
		)
		user = (
			f"User description: {prompt}\n"
			"Requirements: Single-page index.html with links to styles.css and script.js. "
			"Keep CSS modern and aesthetic (blue/black gradient). Make JS unobtrusive and accessible."
		)
		if step_callback:
			step_callback("design")
		with GPT4All(model_path=model_path, allow_download=False, device='cpu') as llm:
			if step_callback:
				step_callback("html")
			response = llm.generate(
				f"SYSTEM:\n{system}\nUSER:\n{user}\nASSISTANT:",
				temp=0.1,
				max_tokens=4096,
			)
		# Try parse JSON
		try:
			data = self._extract_json(response)
			html = data.get("html", "")
			css = data.get("css", "")
			js = data.get("js", "")
		except Exception:
			# Fallback naive splits
			html, css, js = self._fallback_sections(response)
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
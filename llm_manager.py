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

	def generate_site(self, prompt: str, model: ModelInfo, step_callback: Optional[Callable[[str], None]] = None, progress_callback: Optional[Callable[[str], None]] = None, raw_callback: Optional[Callable[[str], None]] = None) -> Dict[str, str]:
		if GPT4All is None:
			raise RuntimeError("gpt4all package not installed")
		model_path = str(self.model_dir / model.filename)
		if not Path(model_path).exists():
			raise RuntimeError(f"Model file not found: {model_path}")
		
		if step_callback:
			step_callback("planning")
		if progress_callback:
			progress_callback("🎯 **Planning Phase**\n\nI'm analyzing your request: *" + prompt + "*\n\nLet me break this down and plan the website structure...")
		
		# Prompt: narrative first, then strict JSON between delimiters
		system = (
			"You are a senior web developer. First, write a brief, friendly explanation of what you are about to build. "
			"Then, at the END of your response, output ONLY the final code as a single compact JSON object with keys html, css, js. "
			"Wrap the JSON strictly between the delimiters <JSON_START> and <JSON_END>. Do NOT use markdown fences around the JSON. "
			"Example: <JSON_START>{\"html\":\"...\",\"css\":\"...\",\"js\":\"...\"}<JSON_END>. "
			"The HTML must include Tailwind CSS via CDN in <head> AND link to styles.css and script.js. Use responsive, modern design."
		)
		
		user = (
			f"Create a website for: {prompt}\n\n"
			"Remember: End with <JSON_START>{\"html\":\"...\",\"css\":\"...\",\"js\":\"...\"}<JSON_END> and nothing else."
		)
		
		if step_callback:
			step_callback("design")
		if progress_callback:
			progress_callback("🎨 **Generating Website**\n\nCreating your website...")
		
		try:
			llm = GPT4All(model_name=model_path)
			
			if step_callback:
				step_callback("html")
			if progress_callback:
				progress_callback("⚙️ **Processing**\n\nGenerating code...")
			
			# Generate with streaming when supported; fallback to non-streaming
			prompt_text = f"SYSTEM:\n{system}\nUSER:\n{user}\nASSISTANT:"
			response = ""
			try:
				current_text = ""
				def on_token(token: str) -> None:
					nonlocal current_text
					current_text += token
					if raw_callback:
						raw_callback(current_text)
					if progress_callback and len(current_text) % 200 == 0:
						progress_callback("⚙️ Generating…")
				response = llm.generate(
					prompt_text,
					temp=0.1,
					max_tokens=4096,
					streaming=True,
					callback=on_token,
				)
				# response may be empty with streaming; ensure we have final text
				if not response:
					response = current_text
			except TypeError:
				# Older GPT4All versions without streaming support
				response = llm.generate(
					prompt_text,
					temp=0.1,
					max_tokens=4096,
				)
				if raw_callback:
					raw_callback(response)
			finally:
				llm.close()
			
			if progress_callback:
				progress_callback("📝 **Processing**\n\nExtracting code…")
				
		except Exception as e:
			raise RuntimeError(f"Model generation failed: {str(e)}")
		
		# Store the full response for raw output display FIRST
		print(f"About to call raw_callback, response length: {len(response)}")
		if raw_callback:
			print("✅ Raw callback exists, calling it...")
			raw_callback(response)
		else:
			print("❌ Raw callback is None!")
		
		# Debug: Print response length and preview
		print(f"Response length: {len(response)}")
		print(f"Response preview: {response[:200]}...")
		
		# Try parse JSON using delimiters first
		m = re.search(r"<JSON_START>([\s\S]*?)<JSON_END>", response)
		if m:
			try:
				data = json.loads(m.group(1).strip())
				html = data.get("html", "")
				css = data.get("css", "")
				js = data.get("js", "")
				print("✅ Delimited JSON parsing successful")
			except Exception as e:
				print(f"❌ Delimited JSON parsing failed: {e}")
		else:
			# Try classic JSON
			try:
				data = self._extract_json(response)
				html = data.get("html", "")
				css = data.get("css", "")
				js = data.get("js", "")
				print("✅ JSON parsing successful")
			except Exception as e:
				print(f"❌ JSON parsing failed: {e}")
				# Try extracting fenced code blocks (```html, ```css, ```js)
				fenced = self._extract_from_fences(response)
				if fenced is not None:
					html, css, js = fenced
					print("✅ Fenced code extraction successful")
				else:
					# Fallback naive splits
					html, css, js = self._fallback_sections(response)
					print("⚠️ Using fallback sections")
					print(f"Response preview: {response[:500]}...")
		
		if progress_callback:
			progress_callback("✅ **Website Ready!**\n\nYour website has been generated successfully! The files are being saved and the preview will update shortly.")
		
		return {"html": html, "css": css, "js": js}

	def _extract_json(self, text: str) -> Dict[str, str]:
		# Prefer fenced ```json blocks if present
		fenced = re.search(r"```json\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
		if fenced:
			candidate = fenced.group(1)
			return json.loads(candidate)
		# Fallback: first JSON-like object
		m = re.search(r"\{[\s\S]*\}", text)
		if not m:
			raise ValueError("No JSON found")
		return json.loads(m.group(0))

	def _extract_from_fences(self, text: str) -> Optional[tuple[str, str, str]]:
		def find(lang_pattern: str) -> str:
			m = re.search(r"```" + lang_pattern + r"\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
			return m.group(1).strip() if m else ""
		html = find("html")
		css = find("css")
		js = find("(?:js|javascript)")
		if html or css or js:
			return html, css, js
		return None

	def _fallback_sections(self, text: str) -> tuple[str, str, str]:
		# Heuristics to split content
		parts = re.split(r"(?im)^\s*(?:HTML|CSS|JS|JavaScript)\s*:?\s*$", text)
		if len(parts) >= 4:
			return parts[1].strip(), parts[2].strip(), parts[3].strip()
		# As a last resort, wrap everything in a simple template
		boiler_html = """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Generated Site</title><link rel=\"stylesheet\" href=\"styles.css\"></head><body><main><h1>Your Site</h1><p>Content could not be parsed cleanly.</p></main><script src=\"script.js\"></script></body></html>"""
		return boiler_html, "body{font-family:system-ui;}\n", "console.log('site ready');\n"
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_ROOT = BASE_DIR / "output_projects"
HISTORY_FILE = OUTPUT_ROOT / "_history.json"


@dataclass
class ProjectRecord:
	name: str
	description: str
	model: str
	path: str
	timestamp: str


class ProjectManager:
	def __init__(self, output_root: Path = OUTPUT_ROOT) -> None:
		self.output_root: Path = output_root
		self.output_root.mkdir(parents=True, exist_ok=True)
		if not HISTORY_FILE.exists():
			HISTORY_FILE.write_text("[]", encoding="utf-8")

	def sanitize_project_name(self, name: str) -> str:
		clean = "".join(c for c in name if c.isalnum() or c in ("-", "_", " ")).strip()
		clean = clean.replace(" ", "-")
		return clean or f"project-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

	def ensure_project_dir(self, project_name: str) -> Path:
		safe = self.sanitize_project_name(project_name)
		project_dir = self.output_root / safe
		(project_dir / "assets").mkdir(parents=True, exist_ok=True)
		return project_dir

	def save_site_files(self, project_dir: Path, html: str, css: str, js: str) -> None:
		(project_dir / "index.html").write_text(html, encoding="utf-8")
		(project_dir / "styles.css").write_text(css, encoding="utf-8")
		(project_dir / "script.js").write_text(js, encoding="utf-8")

	def add_history(self, name: str, description: str, model: str, project_dir: Path) -> None:
		record = ProjectRecord(
			name=name,
			description=description,
			model=model,
			path=str(project_dir.resolve()),
			timestamp=datetime.now().isoformat(timespec="seconds"),
		)
		items = self._read_history()
		items.insert(0, record.__dict__)
		HISTORY_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")

	def list_history(self) -> List[ProjectRecord]:
		items = self._read_history()
		return [ProjectRecord(**i) for i in items]

	def load_project(self, project_path: Path) -> Tuple[str, str, str]:
		index = (project_path / "index.html").read_text(encoding="utf-8") if (project_path / "index.html").exists() else ""
		css = (project_path / "styles.css").read_text(encoding="utf-8") if (project_path / "styles.css").exists() else ""
		js = (project_path / "script.js").read_text(encoding="utf-8") if (project_path / "script.js").exists() else ""
		return index, css, js

	def _read_history(self) -> List[Dict]:
		try:
			if HISTORY_FILE.exists():
				return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
			return []
		except Exception:
			return []
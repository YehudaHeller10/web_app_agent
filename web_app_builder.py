from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from project_manager import ProjectManager, OUTPUT_ROOT
from web_preview import WebPreview
from llm_manager import LLMManager, ModelInfo


class StepWidget(QtWidgets.QWidget):
	def __init__(self, icon: str, text: str, parent=None) -> None:
		super().__init__(parent)
		self.icon_label = QtWidgets.QLabel(icon)
		self.text_label = QtWidgets.QLabel(text)
		self.status_label = QtWidgets.QLabel("")
		self.progress = QtWidgets.QProgressBar()
		self.progress.setRange(0, 1)
		self.progress.setTextVisible(False)
		layout = QtWidgets.QHBoxLayout(self)
		layout.addWidget(self.icon_label)
		layout.addWidget(self.text_label, 1)
		layout.addWidget(self.status_label)
		layout.addWidget(self.progress)

	def set_active(self, active: bool) -> None:
		self.progress.setRange(0, 0 if active else 1)
		self.status_label.setText("In progress…" if active else "")

	def set_done(self) -> None:
		self.progress.setRange(1, 1)
		self.status_label.setText("✅ Done")


class GenerationWorker(QtCore.QObject):
	finished = QtCore.Signal(dict)
	error = QtCore.Signal(str)
	progress_step = QtCore.Signal(str)
	download_progress = QtCore.Signal(int, int)

	def __init__(self, prompt: str, model: ModelInfo, llm: LLMManager, pm: ProjectManager) -> None:
		super().__init__()
		self.prompt = prompt
		self.model = model
		self.llm = llm
		self.pm = pm

	@QtCore.Slot()
	def run(self) -> None:
		try:
			if not self.llm.is_downloaded(self.model):
				self.progress_step.emit("download")
				self.llm.download_model(self.model, progress=lambda d, t: self.download_progress.emit(d, t))
			self.progress_step.emit("planning")
			result = self.llm.generate_site(self.prompt, self.model, step_callback=lambda s: self.progress_step.emit(s))
			self.finished.emit(result)
		except Exception as e:
			self.error.emit(str(e))


class MainWindow(QtWidgets.QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.setWindowTitle("Web App Builder - Static Site Generator")
		self.resize(1400, 860)

		self.pm = ProjectManager()
		self.llm = LLMManager()

		self._setup_ui()
		self._apply_theme()
		self._load_models()
		self._load_history()

	def _setup_ui(self) -> None:
		# Left: History
		self.history_search = QtWidgets.QLineEdit()
		self.history_search.setPlaceholderText("Search projects…")
		self.history_list = QtWidgets.QListWidget()
		self.history_list.itemActivated.connect(self._open_history_item)
		left = QtWidgets.QWidget()
		lv = QtWidgets.QVBoxLayout(left)
		lv.addWidget(QtWidgets.QLabel("History"))
		lv.addWidget(self.history_search)
		lv.addWidget(self.history_list, 1)
		self.history_search.textChanged.connect(self._filter_history)

		# Collapsible history toggle
		self.toggle_history_btn = QtWidgets.QToolButton()
		self.toggle_history_btn.setText("Hide History")
		self.toggle_history_btn.setCheckable(True)
		self.toggle_history_btn.toggled.connect(lambda c: self._toggle_history(c, left))

		# Center: Interaction
		self.prompt_edit = QtWidgets.QTextEdit()
		self.prompt_edit.setPlaceholderText("Describe your website idea… e.g. 'A photographer portfolio with gallery and contact form'")
		self.model_combo = QtWidgets.QComboBox()
		self.refresh_models_btn = QtWidgets.QToolButton()
		self.refresh_models_btn.setText("Refresh Models")
		self.open_models_btn = QtWidgets.QToolButton()
		self.open_models_btn.setText("Open Models Folder")
		self.add_local_btn = QtWidgets.QToolButton()
		self.add_local_btn.setText("Add Local Model")
		self.generate_btn = QtWidgets.QPushButton("Generate Website")
		self.generate_btn.clicked.connect(self._on_generate)
		self.model_combo.activated.connect(self._on_model_selected)

		center_top = QtWidgets.QHBoxLayout()
		center_top.addWidget(QtWidgets.QLabel("Model:"))
		center_top.addWidget(self.model_combo, 1)
		center_top.addWidget(self.refresh_models_btn)
		center_top.addWidget(self.open_models_btn)
		center_top.addWidget(self.add_local_btn)
		center_top.addWidget(self.generate_btn)

		self.steps = [
			StepWidget("🎯", "Planning your website structure…"),
			StepWidget("🎨", "Designing the visual layout…"),
			StepWidget("⚙️", "Generating HTML structure…"),
			StepWidget("🎭", "Creating beautiful CSS styles…"),
			StepWidget("⚡", "Adding interactive JavaScript…"),
			StepWidget("✅", "Your website is ready!"),
		]
		self._set_all_steps_idle()

		steps_widget = QtWidgets.QWidget()
		steps_layout = QtWidgets.QVBoxLayout(steps_widget)
		for s in self.steps:
			steps_layout.addWidget(s)
		steps_layout.addStretch(1)

		suggestions = QtWidgets.QHBoxLayout()
		for text in [
			"Portfolio for a photographer",
			"Restaurant site with menu and contact form",
			"Event landing page with schedule and speakers",
			"Modern blog homepage",
		]:
			btn = QtWidgets.QPushButton(text)
			btn.clicked.connect(lambda _, t=text: self.prompt_edit.setPlainText(t))
			suggestions.addWidget(btn)

		center = QtWidgets.QWidget()
		cv = QtWidgets.QVBoxLayout(center)
		header_row = QtWidgets.QHBoxLayout()
		header_row.addWidget(QtWidgets.QLabel("Web App Builder"))
		header_row.addStretch(1)
		header_row.addWidget(self.toggle_history_btn)

		cv.addLayout(header_row)
		cv.addLayout(center_top)
		cv.addLayout(suggestions)
		cv.addWidget(self.prompt_edit, 1)
		cv.addWidget(QtWidgets.QLabel("Progress"))
		cv.addWidget(steps_widget)

		# Right: Preview
		self.preview = WebPreview()

		splitter = QtWidgets.QSplitter()
		splitter.addWidget(left)
		splitter.addWidget(center)
		splitter.addWidget(self.preview)
		splitter.setSizes([250, 600, 550])

		self.setCentralWidget(splitter)

		self.refresh_models_btn.clicked.connect(self._load_models)
		self.open_models_btn.clicked.connect(self._open_models_folder)
		self.add_local_btn.clicked.connect(self._add_local_model)

	def _apply_theme(self) -> None:
		# Blue/black gradient theme via QSS
		self.setStyleSheet(
			"""
			QMainWindow { background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1, stop:0 #0b1020, stop:1 #102a43); }
			QLabel, QLineEdit, QTextEdit, QListWidget, QComboBox, QPushButton { color: #e6eef8; font-size: 14px; }
			QToolBar, QLineEdit, QTextEdit, QListWidget, QComboBox { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; }
			QPushButton { background-color: #1f4b99; border: 1px solid #2b6cb0; padding: 10px 16px; border-radius: 10px; }
			QPushButton:hover { background-color: #275dad; }
			QComboBox, QLineEdit { min-height: 36px; }
			QTextEdit { padding: 8px; }
			QListWidget::item { padding: 10px; }
			#previewFrame { background: #0e1726; border-radius: 12px; }
			"""
		)

	def _load_models(self) -> None:
		self.model_combo.clear()
		models = self.llm.list_available_models(prioritize_code=True)[:30]
		for m in models:
			status = "(cached)" if self.llm.is_downloaded(m) else ""
			self.model_combo.addItem(f"{m.name} {status}", m)
			self.model_combo.setItemData(self.model_combo.count()-1, m, QtCore.Qt.ItemDataRole.UserRole)
		if self.model_combo.count() == 0:
			self.model_combo.addItem("NO MODELS FOUNDS", None)

	def _load_history(self) -> None:
		self.history_list.clear()
		for rec in self.pm.list_history():
			item = QtWidgets.QListWidgetItem(f"{rec.name}  •  {rec.description}  •  {rec.timestamp}")
			item.setData(QtCore.Qt.ItemDataRole.UserRole, rec)
			self.history_list.addItem(item)

	def _filter_history(self, text: str) -> None:
		for i in range(self.history_list.count()):
			item = self.history_list.item(i)
			rec = item.data(QtCore.Qt.ItemDataRole.UserRole)
			visible = text.lower() in (rec.name + " " + rec.description).lower()
			item.setHidden(not visible)

	def _open_history_item(self, item: QtWidgets.QListWidgetItem) -> None:
		rec = item.data(QtCore.Qt.ItemDataRole.UserRole)
		index_path = Path(rec.path) / "index.html"
		if index_path.exists():
			self.preview.load_index(index_path)

	def _project_name_from_prompt(self, prompt: str) -> str:
		return (prompt[:40] or "My Website").strip().rstrip(".")

	def _on_generate(self) -> None:
		prompt = self.prompt_edit.toPlainText().strip()
		if not prompt:
			QtWidgets.QMessageBox.warning(self, "Input needed", "Please describe your website idea.")
			return
		model: Optional[ModelInfo] = self.model_combo.currentData()
		if model is None:
			QtWidgets.QMessageBox.warning(self, "Model needed", "NO MODELS FOUNDS")
			return
		self._set_all_steps_idle()
		self.steps[0].set_active(True)
		self.generate_btn.setEnabled(False)

		self.thread = QtCore.QThread(self)
		self.worker = GenerationWorker(prompt, model, self.llm, self.pm)
		self.worker.moveToThread(self.thread)
		self.thread.started.connect(self.worker.run)
		self.worker.progress_step.connect(self._on_progress_step)
		self.worker.download_progress.connect(self._on_download_progress)
		self.worker.finished.connect(self._on_generation_finished)
		self.worker.error.connect(self._on_generation_error)
		self.worker.finished.connect(self.thread.quit)
		self.worker.error.connect(self.thread.quit)
		self.thread.finished.connect(self.worker.deleteLater)
		self.thread.start()

	def _on_model_selected(self) -> None:
		model: Optional[ModelInfo] = self.model_combo.currentData(QtCore.Qt.ItemDataRole.UserRole)
		if not model or self.llm.is_downloaded(model):
			return
		mb = QtWidgets.QMessageBox(self)
		mb.setIcon(QtWidgets.QMessageBox.Icon.Question)
		mb.setWindowTitle("Download Model")
		mb.setText("The selected model will be downloaded to the local 'models' folder for future use. Continue?")
		mb.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
		if mb.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
			return
		progress = QtWidgets.QProgressDialog("Downloading model…", "Cancel", 0, 100, self)
		progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
		progress.setAutoClose(True)
		progress.show()
		try:
			self.llm.download_model(model, progress=lambda d, t: progress.setValue(int(d * 100 / max(1, t))))
			self._load_models()
		except Exception as e:
			QtWidgets.QMessageBox.critical(self, "Download failed", str(e))

	def _on_progress_step(self, step: str) -> None:
		mapping = {
			"download": 0,
			"planning": 0,
			"design": 1,
			"html": 2,
			"css": 3,
			"js": 4,
		}
		if step in mapping:
			idx = mapping[step]
			for i, sw in enumerate(self.steps):
				if i < idx:
					sw.set_done()
				elif i == idx:
					sw.set_active(True)
				else:
					sw.set_active(False)

	def _on_download_progress(self, downloaded: int, total: int) -> None:
		self.steps[0].text_label.setText(f"Downloading model… {downloaded//(1024*1024)} / {total//(1024*1024)} MB")

	def _on_generation_finished(self, result: dict) -> None:
		self.steps[4].set_done()
		self.steps[5].set_done()
		self.generate_btn.setEnabled(True)
		prompt = self.prompt_edit.toPlainText().strip()
		name = self._project_name_from_prompt(prompt)
		project_dir = self.pm.ensure_project_dir(name)
		self.pm.save_site_files(project_dir, result.get("html", ""), result.get("css", ""), result.get("js", ""))
		self.pm.add_history(name=name, description=prompt, model=self.model_combo.currentText(), project_dir=project_dir)
		self._load_history()
		index_path = project_dir / "index.html"
		self.preview.load_index(index_path)

	def _on_generation_error(self, message: str) -> None:
		self.generate_btn.setEnabled(True)
		QtWidgets.QMessageBox.critical(self, "Generation failed", message)

	def _set_all_steps_idle(self) -> None:
		labels = [
			"Planning your website structure…",
			"Designing the visual layout…",
			"Generating HTML structure…",
			"Creating beautiful CSS styles…",
			"Adding interactive JavaScript…",
			"Your website is ready!",
		]
		for i, s in enumerate(self.steps):
			s.set_active(False)
			s.status_label.setText("")
			s.text_label.setText(labels[i])

	def _open_models_folder(self) -> None:
		from llm_manager import DEFAULT_MODEL_DIR
		DEFAULT_MODEL_DIR.mkdir(parents=True, exist_ok=True)
		QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(DEFAULT_MODEL_DIR)))

	def _add_local_model(self) -> None:
		path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Add Local Model", str(Path.cwd()), "GGUF Models (*.gguf)")
		if not path:
			return
		from llm_manager import DEFAULT_MODEL_DIR
		dest = DEFAULT_MODEL_DIR / Path(path).name
		try:
			if Path(path).resolve() != dest.resolve():
				dest.write_bytes(Path(path).read_bytes())
			self._load_models()
		except Exception as e:
			QtWidgets.QMessageBox.critical(self, "Add model failed", str(e))

	def _toggle_history(self, collapsed: bool, panel: QtWidgets.QWidget) -> None:
		panel.setVisible(not collapsed)
		self.toggle_history_btn.setText("Show History" if collapsed else "Hide History")


def main() -> None:
	app = QtWidgets.QApplication(sys.argv)
	w = MainWindow()
	w.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
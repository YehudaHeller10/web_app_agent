from __future__ import annotations

import sys
import math
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from project_manager import ProjectManager, OUTPUT_ROOT
from web_preview import WebPreview
from llm_manager import LLMManager, ModelInfo


class ChatMessage(QtWidgets.QWidget):
	def __init__(self, content: str, is_user: bool = False, parent=None) -> None:
		super().__init__(parent)
		self.is_user = is_user
		
		layout = QtWidgets.QHBoxLayout(self)
		layout.setContentsMargins(20, 10, 20, 10)
		
		# Avatar
		avatar = QtWidgets.QLabel("👤" if is_user else "🤖")
		avatar.setFixedSize(32, 32)
		avatar.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
		avatar.setStyleSheet("font-size: 20px;")
		
		# Message content
		self.content_label = QtWidgets.QLabel(content)
		self.content_label.setWordWrap(True)
		self.content_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
		self.content_label.setTextFormat(QtCore.Qt.TextFormat.MarkdownText)
		self.content_label.setStyleSheet("""
			QLabel {
				background-color: #ffffff;
				border-radius: 12px;
				padding: 12px 16px;
				color: #111111;
				font-size: 14px;
				line-height: 1.6;
			}
		""")
		
		if is_user:
			layout.addStretch()
			layout.addWidget(self.content_label)
			layout.addWidget(avatar)
		else:
			layout.addWidget(avatar)
			layout.addWidget(self.content_label)
			layout.addStretch()

	def update_content(self, content: str) -> None:
		self.content_label.setText(content)


class ProgressSpinner(QtWidgets.QWidget):
	def __init__(self, parent=None) -> None:
		super().__init__(parent)
		self.angle = 0
		self.timer = QtCore.QTimer()
		self.timer.timeout.connect(self.rotate)
		self.timer.start(50)
		
	def rotate(self) -> None:
		self.angle = (self.angle + 30) % 360
		self.update()
		
	def paintEvent(self, event) -> None:
		painter = QtGui.QPainter(self)
		painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
		
		# Draw spinning dots
		center = self.rect().center()
		radius = 8
		for i in range(8):
			angle = math.radians(self.angle + i * 45)
			x = center.x() + int(radius * 2 * math.cos(angle))
			y = center.y() + int(radius * 2 * math.sin(angle))
			alpha = 255 - (i * 30)
			painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, alpha), 3))
			painter.drawPoint(x, y)


class GenerationWorker(QtCore.QObject):
	finished = QtCore.Signal(dict)
	error = QtCore.Signal(str)
	progress_step = QtCore.Signal(str)
	progress_message = QtCore.Signal(str)
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
				self.progress_message.emit("📥 **Downloading Model**\n\nDownloading the AI model to your local machine...")
				self.llm.download_model(self.model, progress=lambda d, t: self.download_progress.emit(d, t))
			
			self.progress_message.emit("🎯 **Starting Generation**\n\nInitializing the AI model and preparing to create your website...")
			result = self.llm.generate_site(
				self.prompt, 
				self.model, 
				step_callback=lambda s: self.progress_step.emit(s),
				progress_callback=lambda msg: self.progress_message.emit(msg)
			)
			self.finished.emit(result)
		except Exception as e:
			self.error.emit(str(e))


class MainWindow(QtWidgets.QMainWindow):
	def __init__(self) -> None:
		super().__init__()
		self.setWindowTitle("Web App Builder - AI Website Generator")
		self.resize(1600, 1000)

		self.pm = ProjectManager()
		self.llm = LLMManager()

		self._setup_ui()
		self._apply_theme()
		self._load_models()
		self._load_history()

	def _setup_ui(self) -> None:
		# Create all widgets first
		self._create_widgets()
		self._setup_layouts()
		self._connect_signals()

	def _create_widgets(self) -> None:
		# Left sidebar - History
		self.history_search = QtWidgets.QLineEdit()
		self.history_search.setPlaceholderText("🔍 Search projects...")
		self.history_list = QtWidgets.QListWidget()
		self.history_list.itemActivated.connect(self._open_history_item)
		
		# Collapsible history toggle
		self.toggle_history_btn = QtWidgets.QToolButton()
		self.toggle_history_btn.setText("📋")
		self.toggle_history_btn.setToolTip("Toggle History")
		self.toggle_history_btn.setCheckable(True)

		# Top toolbar
		self.model_combo = QtWidgets.QComboBox()
		self.model_combo.setPlaceholderText("Select AI Model")
		self.refresh_models_btn = QtWidgets.QToolButton()
		self.refresh_models_btn.setText("🔄")
		self.refresh_models_btn.setToolTip("Refresh Models")
		self.open_models_btn = QtWidgets.QToolButton()
		self.open_models_btn.setText("📁")
		self.open_models_btn.setToolTip("Open Models Folder")
		self.add_local_btn = QtWidgets.QToolButton()
		self.add_local_btn.setText("➕")
		self.add_local_btn.setToolTip("Add Local Model")

		# Chat area
		self.chat_scroll = QtWidgets.QScrollArea()
		self.chat_widget = QtWidgets.QWidget()
		self.chat_layout = QtWidgets.QVBoxLayout(self.chat_widget)
		self.chat_layout.addStretch()
		self.chat_scroll.setWidget(self.chat_widget)
		self.chat_scroll.setWidgetResizable(True)
		self.chat_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

		# Input area
		self.input_container = QtWidgets.QWidget()
		self.input_layout = QtWidgets.QHBoxLayout(self.input_container)
		self.input_layout.setContentsMargins(20, 10, 20, 20)
		
		self.prompt_edit = QtWidgets.QTextEdit()
		self.prompt_edit.setPlaceholderText("Describe your website idea... (e.g., 'A photographer portfolio with gallery and contact form')")
		self.prompt_edit.setMaximumHeight(100)
		
		self.generate_btn = QtWidgets.QPushButton("🚀 Generate Website")
		self.generate_btn.setFixedSize(150, 40)

		# Right panel - Preview
		self.preview = WebPreview()

	def _setup_layouts(self) -> None:
		# Left panel
		left = QtWidgets.QWidget()
		left.setMaximumWidth(300)
		lv = QtWidgets.QVBoxLayout(left)
		lv.setContentsMargins(10, 10, 10, 10)
		lv.addWidget(QtWidgets.QLabel("📚 Project History"))
		lv.addWidget(self.history_search)
		lv.addWidget(self.history_list, 1)

		# Top toolbar
		toolbar = QtWidgets.QWidget()
		toolbar_layout = QtWidgets.QHBoxLayout(toolbar)
		toolbar_layout.setContentsMargins(20, 10, 20, 10)
		toolbar_layout.addWidget(QtWidgets.QLabel("🤖 Model:"))
		toolbar_layout.addWidget(self.model_combo, 1)
		toolbar_layout.addWidget(self.refresh_models_btn)
		toolbar_layout.addWidget(self.open_models_btn)
		toolbar_layout.addWidget(self.add_local_btn)
		toolbar_layout.addWidget(self.toggle_history_btn)

		# Center panel
		center = QtWidgets.QWidget()
		cv = QtWidgets.QVBoxLayout(center)
		cv.setContentsMargins(0, 0, 0, 0)
		cv.addWidget(toolbar)
		cv.addWidget(self.chat_scroll, 1)
		cv.addWidget(self.input_container)

		# Input area layout
		self.input_layout.addWidget(self.prompt_edit, 1)
		self.input_layout.addWidget(self.generate_btn)

		# Main splitter
		splitter = QtWidgets.QSplitter()
		splitter.addWidget(left)
		splitter.addWidget(center)
		splitter.addWidget(self.preview)
		splitter.setSizes([300, 800, 500])

		self.setCentralWidget(splitter)

	def _connect_signals(self) -> None:
		self.history_search.textChanged.connect(self._filter_history)
		self.generate_btn.clicked.connect(self._on_generate)
		self.model_combo.activated.connect(self._on_model_selected)
		self.refresh_models_btn.clicked.connect(self._load_models)
		self.open_models_btn.clicked.connect(self._open_models_folder)
		self.add_local_btn.clicked.connect(self._add_local_model)
		self.toggle_history_btn.toggled.connect(self._toggle_history)

	def _apply_theme(self) -> None:
		# ChatGPT-like theme
		self.setStyleSheet(
			"""
			QMainWindow { 
				background-color: #343541; 
				color: #ececf1;
			}
			QLabel, QLineEdit, QTextEdit, QListWidget, QComboBox, QPushButton { 
				color: #ececf1; 
				font-size: 14px; 
				font-family: 'Segoe UI', Arial, sans-serif;
			}
			QLineEdit, QTextEdit, QComboBox { 
				background-color: #40414f; 
				border: 1px solid #565869; 
				border-radius: 8px; 
				padding: 8px 12px;
			}
			QLineEdit:focus, QTextEdit:focus, QComboBox:focus { 
				border-color: #10a37f; 
			}
			QPushButton { 
				background-color: #10a37f; 
				border: none; 
				border-radius: 8px; 
				padding: 10px 16px; 
				font-weight: 500;
			}
			QPushButton:hover { 
				background-color: #0d8f6f; 
			}
			QPushButton:pressed { 
				background-color: #0b7a5f; 
			}
			QPushButton:disabled { 
				background-color: #565869; 
				color: #8e8ea0; 
			}
			QToolButton { 
				background-color: transparent; 
				border: 1px solid #565869; 
				border-radius: 6px; 
				padding: 6px; 
				font-size: 16px;
			}
			QToolButton:hover { 
				background-color: #40414f; 
				border-color: #10a37f; 
			}
			QListWidget { 
				background-color: #40414f; 
				border: 1px solid #565869; 
				border-radius: 8px; 
				padding: 4px;
			}
			QListWidget::item { 
				padding: 8px 12px; 
				border-radius: 6px; 
				margin: 2px;
			}
			QListWidget::item:hover { 
				background-color: #565869; 
			}
			QListWidget::item:selected { 
				background-color: #10a37f; 
			}
			QScrollArea { 
				background-color: #343541; 
				border: none; 
			}
			QScrollBar:vertical { 
				background-color: #40414f; 
				width: 12px; 
				border-radius: 6px; 
			}
			QScrollBar::handle:vertical { 
				background-color: #565869; 
				border-radius: 6px; 
				min-height: 20px; 
			}
			QScrollBar::handle:vertical:hover { 
				background-color: #10a37f; 
			}
			#previewFrame { 
				background-color: #1a1a1a; 
				border-radius: 12px; 
			}
			"""
		)

	def _add_chat_message(self, content: str, is_user: bool = False) -> ChatMessage:
		message = ChatMessage(content, is_user)
		self.chat_layout.insertWidget(self.chat_layout.count() - 1, message)
		return message

	def _add_progress_message(self, content: str) -> ChatMessage:
		message = ChatMessage(content, False)
		# Add spinner
		spinner = ProgressSpinner()
		spinner.setFixedSize(20, 20)
		message.layout().insertWidget(1, spinner)
		self.chat_layout.insertWidget(self.chat_layout.count() - 1, message)
		return message

	def _load_models(self) -> None:
		try:
			self.model_combo.clear()
			models = self.llm.list_available_models(prioritize_code=True)[:30]
			for m in models:
				status = " ✅" if self.llm.is_downloaded(m) else ""
				self.model_combo.addItem(f"{m.name}{status}", m)
				self.model_combo.setItemData(self.model_combo.count()-1, m, QtCore.Qt.ItemDataRole.UserRole)
			if self.model_combo.count() == 0:
				self.model_combo.addItem("❌ NO MODELS FOUNDS", None)
		except Exception as e:
			self.model_combo.clear()
			self.model_combo.addItem(f"❌ Error: {str(e)}", None)

	def _load_history(self) -> None:
		self.history_list.clear()
		for rec in self.pm.list_history():
			item = QtWidgets.QListWidgetItem(f"📄 {rec.name}\n💬 {rec.description[:50]}...\n🕒 {rec.timestamp}")
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
			# Add message to chat
			self._add_chat_message(f"📄 **Loaded Project**: {rec.name}\n\n{rec.description}", False)

	def _project_name_from_prompt(self, prompt: str) -> str:
		return (prompt[:40] or "My Website").strip().rstrip(".")

	def _on_generate(self) -> None:
		prompt = self.prompt_edit.toPlainText().strip()
		if not prompt:
			QtWidgets.QMessageBox.warning(self, "Input needed", "Please describe your website idea.")
			return
		model: Optional[ModelInfo] = self.model_combo.currentData()
		if model is None:
			QtWidgets.QMessageBox.warning(self, "Model needed", "❌ NO MODELS FOUNDS")
			return
		
		# Verify model file exists
		model_path = self.llm.model_dir / model.filename
		if not model_path.exists():
			QtWidgets.QMessageBox.critical(self, "Model Error", f"Model file not found: {model_path}\nPlease download the model first.")
			return
		
		# Add user message to chat
		self._add_chat_message(prompt, True)
		self._last_prompt = prompt
		
		# Add initial AI message
		self.current_ai_message = self._add_progress_message("🤖 **AI Assistant**\n\nInitializing...")
		
		self.generate_btn.setEnabled(False)
		self.prompt_edit.clear()

		self.thread = QtCore.QThread(self)
		self.worker = GenerationWorker(prompt, model, self.llm, self.pm)
		self.worker.moveToThread(self.thread)
		self.thread.started.connect(self.worker.run)
		self.worker.progress_message.connect(self._update_ai_message)
		self.worker.finished.connect(self._on_generation_finished)
		self.worker.error.connect(self._on_generation_error)
		self.worker.finished.connect(self.thread.quit)
		self.worker.error.connect(self.thread.quit)
		self.thread.finished.connect(self.worker.deleteLater)
		self.thread.start()

	def _update_ai_message(self, content: str) -> None:
		if hasattr(self, 'current_ai_message'):
			self.current_ai_message.update_content(content)

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

	def _on_generation_finished(self, result: dict) -> None:
		self.generate_btn.setEnabled(True)
		# Use last prompt to avoid empty project name after clearing input
		prompt = getattr(self, "_last_prompt", self.prompt_edit.toPlainText().strip())
		name = self._project_name_from_prompt(prompt)
		project_dir = self.pm.ensure_project_dir(name)
		self.pm.save_site_files(project_dir, result.get("html", ""), result.get("css", ""), result.get("js", ""))
		self.pm.add_history(name=name, description=prompt, model=self.model_combo.currentText(), project_dir=project_dir)
		self._load_history()
		index_path = project_dir / "index.html"
		self.preview.load_index(index_path)
		
		# Update final message
		if hasattr(self, 'current_ai_message'):
			self.current_ai_message.update_content("✅ **Website Generated Successfully!**\n\nYour website has been created and is ready for preview. The files have been saved to your project folder.")

	def _on_generation_error(self, message: str) -> None:
		self.generate_btn.setEnabled(True)
		# Show detailed error information with readable styling
		error_dialog = QtWidgets.QMessageBox(self)
		error_dialog.setIcon(QtWidgets.QMessageBox.Icon.Critical)
		error_dialog.setWindowTitle("Generation Failed")
		error_dialog.setText(f"❌ Error: {message}")
		error_dialog.setDetailedText(f"Model: {self.model_combo.currentText()}\nPrompt: {self.prompt_edit.toPlainText()[:100]}...")
		error_dialog.setStyleSheet("QLabel{color:#111;background:#fff;} QMessageBox{background:#fff;} QPushButton{background:#10a37f;color:#fff;border:none;border-radius:6px;padding:6px 10px;}")
		error_dialog.exec()

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

	def _toggle_history(self, collapsed: bool) -> None:
		# Find the left panel (first widget in splitter)
		left_panel = self.centralWidget().widget(0)
		left_panel.setVisible(not collapsed)
		self.toggle_history_btn.setText("📋" if collapsed else "📋")


def main() -> None:
	app = QtWidgets.QApplication(sys.argv)
	w = MainWindow()
	w.show()
	sys.exit(app.exec())


if __name__ == "__main__":
	main()
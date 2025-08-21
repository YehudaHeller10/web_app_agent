from __future__ import annotations

from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView


class WebPreview(QtWidgets.QWidget):
	device_modes = {
		"Desktop": 1280,
		"Tablet": 768,
		"Mobile": 375,
	}

	def __init__(self, parent=None) -> None:
		super().__init__(parent)
		self._index_path: Path | None = None

		self.toolbar = QtWidgets.QToolBar()
		self.mode_combo = QtWidgets.QComboBox()
		self.mode_combo.addItems(list(self.device_modes.keys()))
		self.zoom_combo = QtWidgets.QComboBox()
		self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%"])
		self.zoom_combo.setCurrentText("100%")
		self.reload_btn = QtWidgets.QToolButton()
		self.reload_btn.setText("Refresh")

		self.toolbar.addWidget(QtWidgets.QLabel("View:"))
		self.toolbar.addWidget(self.mode_combo)
		self.toolbar.addSeparator()
		self.toolbar.addWidget(QtWidgets.QLabel("Zoom:"))
		self.toolbar.addWidget(self.zoom_combo)
		self.toolbar.addSeparator()
		self.toolbar.addWidget(self.reload_btn)

		self.view_container = QtWidgets.QScrollArea()
		self.view_container.setWidgetResizable(True)
		self.view_frame = QtWidgets.QFrame()
		self.view_frame.setObjectName("previewFrame")
		self.view_layout = QtWidgets.QVBoxLayout(self.view_frame)
		self.view_layout.setContentsMargins(20, 20, 20, 20)
		self.view_layout.setSpacing(0)

		self.view = QWebEngineView()
		self.view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.NoContextMenu)
		self.view_layout.addWidget(self.view)
		self.view_container.setWidget(self.view_frame)

		layout = QtWidgets.QVBoxLayout(self)
		layout.addWidget(self.toolbar)
		layout.addWidget(self.view_container)

		self.mode_combo.currentTextChanged.connect(self._apply_device_mode)
		self.zoom_combo.currentTextChanged.connect(self._apply_zoom)
		self.reload_btn.clicked.connect(self.reload)

		self._apply_device_mode(self.mode_combo.currentText())
		self._apply_zoom(self.zoom_combo.currentText())

	def load_index(self, index_path: Path) -> None:
		self._index_path = index_path
		self.view.setUrl(QUrl.fromLocalFile(str(index_path)))

	def reload(self) -> None:
		if self._index_path:
			self.view.reload()

	def _apply_device_mode(self, mode: str) -> None:
		width = self.device_modes.get(mode, 1280)
		self.view.setFixedWidth(width)

	def _apply_zoom(self, text: str) -> None:
		value = text.replace("%", "")
		try:
			zoom_factor = max(0.25, min(3.0, float(value) / 100.0))
			self.view.setZoomFactor(zoom_factor)
		except Exception:
			self.view.setZoomFactor(1.0)
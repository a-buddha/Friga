""" APK patcher panel """

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.patcher import Patcher


class ApkPatcherPanel(QWidget):
    def __init__(self, patcher: Patcher, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patcher = patcher
        self._serial: str | None = None
        self._apk: str | None = None

        self._apk_label = QLabel("No APK selected")
        self._apk_label.setStyleSheet("color: #9b9b9b;")
        self._browse_btn = QPushButton("Choose APK…")
        self._browse_btn.clicked.connect(self._on_browse)

        pick_row = QHBoxLayout()
        pick_row.addWidget(self._browse_btn)
        pick_row.addWidget(self._apk_label, 1)

        self._patch_btn = QPushButton("Patch && Install")
        self._patch_btn.clicked.connect(self._on_patch)

        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setRange(0, 7)
        self._progress.setValue(0)
        self._progress.setFormat("Idle")

        box = QGroupBox("APK Patching (frida-gadget)")
        box_layout = QVBoxLayout(box)
        box_layout.addLayout(pick_row)
        box_layout.addWidget(self._patch_btn)
        box_layout.addWidget(self._progress)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(box)
        layout.addStretch()

        self._patcher.progress.connect(self._on_progress)
        self._patcher.busy_changed.connect(self._on_busy_changed)
        self._patcher.finished.connect(self._on_finished)
        self._patcher.error.connect(self._on_error)

        self._update_enabled()

    def set_device(self, serial: str | None) -> None:
        self._serial = serial
        self._update_enabled()

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select APK", "", "APK files (*.apk)")
        if path:
            self._apk = path
            self._apk_label.setText(Path(path).name)
            self._apk_label.setStyleSheet("color: #d4d4d4;")
            self._update_enabled()

    def _on_patch(self) -> None:
        if self._apk and self._serial:
            self._patcher.patch(self._apk, self._serial)

    def _on_progress(self, step: int, total: int, label: str) -> None:
        self._progress.setRange(0, total)
        self._progress.setValue(step)
        self._progress.setFormat(f"{step}/{total}  {label}")

    def _on_busy_changed(self, busy: bool) -> None:
        self._update_enabled(busy)

    def _on_finished(self, _package: str) -> None:
        self._progress.setValue(self._progress.maximum())
        self._progress.setFormat("Done ✓")

    def _on_error(self, _message: str) -> None:
        self._progress.setFormat("Failed ✗")

    def _update_enabled(self, busy: bool | None = None) -> None:
        if busy is None:
            busy = self._patcher.is_busy
        self._browse_btn.setEnabled(not busy)
        self._patch_btn.setEnabled(bool(self._apk) and bool(self._serial) and not busy)

""" IPA patcher panel — design preview only.
Mirrors the APK patcher's layout so the iOS workflow has parity, but nothing runs:
patching an IPA needs macOS and a jailbroken device, which is out of scope. The
patch button is disabled and everything here is just a mock-up of what it would be """

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

_DISABLED_REASON = (
    "IPA patching needs macOS and a jailbroken iOS device, which is out of scope "
    "for this project. This panel is a design preview of the iOS workflow."
)


class IpaPatcherPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ipa: str | None = None

        note = QLabel("Coming soon! iOS support is a design preview only")
        note.setStyleSheet("color: #dcdcaa;")
        note.setWordWrap(True)

        self._ipa_label = QLabel("No IPA selected")
        self._ipa_label.setStyleSheet("color: #9b9b9b;")
        self._browse_btn = QPushButton("Choose IPA…")
        self._browse_btn.clicked.connect(self._on_browse)

        pick_row = QHBoxLayout()
        pick_row.addWidget(self._browse_btn)
        pick_row.addWidget(self._ipa_label, 1)

        self._patch_btn = QPushButton("Patch && Install")
        self._patch_btn.setEnabled(False)
        self._patch_btn.setToolTip(_DISABLED_REASON)

        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setEnabled(False)
        self._progress.setRange(0, 7)
        self._progress.setValue(0)
        self._progress.setFormat("Not available")

        box = QGroupBox("IPA Patching (frida-gadget)")
        box_layout = QVBoxLayout(box)
        box_layout.addWidget(note)
        box_layout.addLayout(pick_row)
        box_layout.addWidget(self._patch_btn)
        box_layout.addWidget(self._progress)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(box)
        layout.addStretch()

    def _on_browse(self) -> None:
        # Lets you see the picker; patching still can't run.
        path, _ = QFileDialog.getOpenFileName(self, "Select IPA", "", "IPA files (*.ipa)")
        if path:
            self._ipa = path
            self._ipa_label.setText(Path(path).name)
            self._ipa_label.setStyleSheet("color: #d4d4d4;")

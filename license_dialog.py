# license_dialog.py
# Licensing activation interface using non-blocking background QThread.

import time
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from security import verify_license_online, save_local_license, LicenseVerificationResult
from device_identity import get_hwid, get_legacy_hwid_candidates

class LicenseVerificationWorker(QThread):
    finished = pyqtSignal(object)  # Emits LicenseVerificationResult

    def __init__(self, key: str, hwid: str):
        super().__init__()
        self.key = key
        self.hwid = hwid

    def run(self):
        # Generate legacy candidates in case the server needs them for matching
        candidates = get_legacy_hwid_candidates()
        result = verify_license_online(self.key, self.hwid, candidates=candidates)
        self.finished.emit(result)

class LicenseDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Cutter License")
        application = QApplication.instance()
        if application is not None and not application.windowIcon().isNull():
            self.setWindowIcon(application.windowIcon())
        self.resize(450, 200)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setModal(True)
        
        # Load HWID
        try:
            self.hwid = get_hwid()
            self.hwid_available = True
        except Exception:
            self.hwid = ""
            self.hwid_available = False
            
        self.worker = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        self.lbl_title = QLabel("VIDEO CUTTER PREMIUM")
        self.lbl_title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #3b82f6;"
        )
        layout.addWidget(self.lbl_title)

        self.lbl_desc = QLabel(
            "Vui lòng nhập License Key để kích hoạt phần mềm:"
        )
        layout.addWidget(self.lbl_desc)

        self.txt_key = QLineEdit()
        self.txt_key.setPlaceholderText("VIDEO-XXXX-XXXX-XXXX-XXXX")
        self.txt_key.setStyleSheet(
            "padding: 8px; font-size: 14px; "
            "border: 1px solid #ccc; border-radius: 4px;"
        )
        layout.addWidget(self.txt_key)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        btn_layout = QHBoxLayout()
        self.btn_exit = QPushButton("Thoát")
        self.btn_exit.clicked.connect(self.reject)

        self.btn_activate = QPushButton("Kích hoạt ngay")
        self.btn_activate.setStyleSheet(
            "background-color: #10b981; color: white; "
            "font-weight: bold; padding: 6px 16px; border-radius: 4px;"
        )
        self.btn_activate.clicked.connect(self.activate_license)

        btn_layout.addWidget(self.btn_exit)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_activate)
        layout.addLayout(btn_layout)
        
        # If hardware id is not available, block activation upfront
        if not self.hwid_available:
            self.lbl_status.setText("Lỗi: Không thể lấy HWID phần cứng của thiết bị này.")
            self.txt_key.setEnabled(False)
            self.btn_activate.setEnabled(False)

    def activate_license(self):
        key = self.txt_key.text().strip()
        if not key:
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_status.setText("Vui lòng nhập Key.")
            return

        self.set_controls_enabled(False)
        self.lbl_status.setStyleSheet("color: #666;")
        self.lbl_status.setText("Đang kết nối đến máy chủ bản quyền và kiểm tra...")

        # Run online check in background thread
        self.worker = LicenseVerificationWorker(key, self.hwid)
        self.worker.finished.connect(self.on_verification_finished)
        self.worker.start()

    def on_verification_finished(self, result: LicenseVerificationResult):
        if result.valid:
            # Save key locally
            key = self.txt_key.text().strip()
            save_local_license(
                key=key,
                status=result.status,
                last_verified_at=datetime.utcnow().isoformat() + "Z",
                cached_expires_at=getattr(result, "expired_at", None)
            )
            self.lbl_status.setStyleSheet("color: #10b981; font-weight: bold;")
            self.lbl_status.setText("Kích hoạt bản quyền thành công!")
            
            # Wait a moment before accepting
            QApplication.processEvents()
            time.sleep(1)
            self.accept()
        else:
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_status.setText(result.message)
            self.set_controls_enabled(True)

    def set_controls_enabled(self, enabled: bool):
        self.txt_key.setEnabled(enabled)
        self.btn_activate.setEnabled(enabled)
        self.btn_exit.setEnabled(enabled)

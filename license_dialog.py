"""
license_dialog.py — License activation dialog for Video Cutter.
===============================================================
Runs license verification on a background QThread to avoid blocking the GUI.
No time.sleep() or QApplication.processEvents() used.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from security import (
    verify_license_online, save_local_license,
    LicenseVerificationResult, LicenseStatus,
)
from device_identity import get_hwid, DeviceIdentityError


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND WORKER
# ═══════════════════════════════════════════════════════════════════════════════

class LicenseActivateWorker(QThread):
    """
    Worker thread that calls verify_license_online() off the GUI thread.
    Emits result via signal when done.
    """
    finished = pyqtSignal(object)  # LicenseVerificationResult
    
    def __init__(self, key: str, hwid: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._hwid = hwid
    
    def run(self):
        result = verify_license_online(self._key, self._hwid)
        self.finished.emit(result)


# ═══════════════════════════════════════════════════════════════════════════════
#  LICENSE DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class LicenseDialog(QDialog):
    """
    Modal dialog for license key activation.
    
    - Runs API calls on QThread (no GUI blocking).
    - Disables button during verification (no double-click).
    - Shows structured status messages.
    - Accepts on successful activation, rejects on close/exit.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Video Cutter License")
        self.resize(450, 200)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setModal(True)
        
        self._worker = None
        self._hwid = None
        self._key = None
        
        # Try to get HWID
        try:
            self._hwid = get_hwid()
        except DeviceIdentityError as e:
            self._hwid_error = str(e)
        else:
            self._hwid_error = None
        
        self._init_ui()
    
    def _init_ui(self):
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
        self.txt_key.returnPressed.connect(self._activate_license)
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
        self.btn_activate.clicked.connect(self._activate_license)
        
        btn_layout.addWidget(self.btn_exit)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_activate)
        layout.addLayout(btn_layout)
        
        # Show HWID error if applicable
        if self._hwid_error:
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_status.setText(
                "Không thể xác định mã máy. Vui lòng chạy với quyền Administrator."
            )
            self.btn_activate.setEnabled(False)
    
    def _activate_license(self):
        """Start license activation on worker thread."""
        # Guard: prevent double-click
        if self._worker is not None and self._worker.isRunning():
            return
        
        key = self.txt_key.text().strip()
        if not key:
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_status.setText("Vui lòng nhập Key.")
            return
        
        if not self._hwid:
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_status.setText(
                "Không thể xác định mã máy. Vui lòng chạy với quyền Administrator."
            )
            return
        
        # Save key for later use in result handler
        self._key = key
        
        # Disable controls during verification
        self.btn_activate.setEnabled(False)
        self.btn_exit.setEnabled(False)
        self.txt_key.setEnabled(False)
        self.lbl_status.setStyleSheet("color: #666;")
        self.lbl_status.setText("Đang kiểm tra kết nối và bản quyền...")
        
        # Start worker
        self._worker = LicenseActivateWorker(key, self._hwid, parent=self)
        self._worker.finished.connect(self._on_activation_result)
        self._worker.start()
    
    def _on_activation_result(self, result: LicenseVerificationResult):
        """Handle activation result from worker thread."""
        # Re-enable exit button always
        self.btn_exit.setEnabled(True)
        
        if result.valid is True:
            # Save license locally
            save_local_license(self._key, result)
            
            self.lbl_status.setStyleSheet("color: #10b981; font-weight: bold;")
            self.lbl_status.setText(result.message)
            
            # Auto-close after brief delay (non-blocking)
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(800, self.accept)
        else:
            self.lbl_status.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_status.setText(result.message)
            self.btn_activate.setEnabled(True)
            self.txt_key.setEnabled(True)
    
    def closeEvent(self, event):
        """Handle window close — wait for worker if running."""
        if self._worker is not None and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(3000)
        super().closeEvent(event)

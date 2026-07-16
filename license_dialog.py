from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QApplication,
)
from PyQt6.QtCore import Qt
from security import verify_license_online, save_local_license, get_hwid
import time


class LicenseDialog(QDialog):
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
        self.hwid = get_hwid()
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

    def activate_license(self):
        key = self.txt_key.text().strip()
        if not key:
            self.lbl_status.setText("Vui lòng nhập Key.")
            return

        self.btn_activate.setEnabled(False)
        self.lbl_status.setStyleSheet("color: #666;")
        self.lbl_status.setText("Đang kiểm tra kết nối và bản quyền...")
        QApplication.processEvents()

        is_valid, msg = verify_license_online(key, self.hwid)

        if is_valid:
            save_local_license(key)
            self.lbl_status.setStyleSheet("color: #10b981;")
            self.lbl_status.setText("Kích hoạt bản quyền thành công!")
            QApplication.processEvents()
            time.sleep(1)
            self.accept()
        else:
            self.lbl_status.setStyleSheet("color: red;")
            self.lbl_status.setText(msg)
            self.btn_activate.setEnabled(True)

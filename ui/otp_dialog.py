# ui/otp_dialog.py
"""OTP Dialog for locking/unlocking settings."""

import hashlib
import secrets

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, 
    QPushButton, QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt

from ui.styles import DARK_THEME


class OTPDialog(QDialog):
    """Dialog for OTP creation and verification."""
    
    def __init__(self, mode: str = "set", stored_hash: str = None, parent=None):
        """
        Args:
            mode: "set" (create new OTP) or "verify" (check existing OTP)
            stored_hash: SHA256 hash to verify against (only for verify mode)
        """
        super().__init__(parent)
        self.mode = mode
        self.stored_hash = stored_hash
        self.generated_otp = None
        
        self.setWindowTitle("🔒 BambiLock" + (" - Create Code" if mode == "set" else " - Verify Code"))
        self.setFixedSize(420, 300 if mode == "set" else 240)
        self.setModal(True)
        self.setStyleSheet(DARK_THEME)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Title
        if self.mode == "set":
            title = QLabel("🔐 Create Your BambiCode")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff6bd6;")
        else:
            title = QLabel("🔓 Enter Your BambiCode")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff6bd6;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Description
        if self.mode == "set":
            desc = QLabel(
                "Your settings will be locked with this code.\n"
                "Write it down - there is NO recovery!"
            )
            desc.setStyleSheet("font-size: 12px; color: #ffcc9b;")
        else:
            desc = QLabel("Enter your BambiCode to unlock settings:")
            desc.setStyleSheet("font-size: 12px; color: #88ddff;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # OTP Display (set mode only)
        if self.mode == "set":
            self.generated_otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
            
            code_label = QLabel("Your new BambiCode:")
            code_label.setStyleSheet("font-size: 11px; color: #888;")
            code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(code_label)
            
            otp_display = QLabel(self.generated_otp)
            otp_display.setStyleSheet("""
                font-size: 36px;
                font-weight: bold;
                color: #34c759;
                background: #151521;
                padding: 15px;
                border-radius: 10px;
                font-family: monospace;
                letter-spacing: 10px;
            """)
            otp_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(otp_display)
            
            warning = QLabel("⚠️ WRITE THIS DOWN - NO RECOVERY POSSIBLE!")
            warning.setStyleSheet("font-size: 11px; color: #ff6b6b; font-weight: bold;")
            warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(warning)
        
        # OTP Input (verify mode only)
        if self.mode == "verify":
            self.otp_input = QLineEdit()
            self.otp_input.setPlaceholderText("Enter 6-digit code...")
            self.otp_input.setMaxLength(6)
            self.otp_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.otp_input.setStyleSheet("""
                font-size: 24px;
                padding: 12px;
                font-family: monospace;
                letter-spacing: 5px;
            """)
            self.otp_input.returnPressed.connect(self._verify)
            layout.addWidget(self.otp_input)
        
        # Buttons
        buttons = QDialogButtonBox()
        
        if self.mode == "set":
            confirm_btn = QPushButton("✓ I've Saved This Code - Lock Settings")
            confirm_btn.setStyleSheet("""
                QPushButton {
                    background: #34c759;
                    color: #0b0b12;
                    font-weight: bold;
                    padding: 12px 20px;
                    border-radius: 8px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: #28a745;
                }
            """)
            confirm_btn.clicked.connect(self.accept)
            buttons.addButton(confirm_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        else:
            verify_btn = QPushButton("✓ Verify & Unlock")
            verify_btn.setStyleSheet("""
                QPushButton {
                    background: #ff6bd6;
                    color: #0b0b12;
                    font-weight: bold;
                    padding: 12px 20px;
                    border-radius: 8px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background: #ff8be0;
                }
            """)
            verify_btn.clicked.connect(self._verify)
            buttons.addButton(verify_btn, QDialogButtonBox.ButtonRole.AcceptRole)
        
        cancel_btn = QPushButton("✕ Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #26263a;
                color: #888;
                padding: 12px 20px;
                border-radius: 8px;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #333350;
                color: #ccc;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        buttons.addButton(cancel_btn, QDialogButtonBox.ButtonRole.RejectRole)
        
        layout.addWidget(buttons)
        self.setLayout(layout)
        
        if self.mode == "verify":
            self.otp_input.setFocus()
    
    def _verify(self):
        """Verify entered OTP against stored hash."""
        if self.mode != "verify":
            self.accept()
            return
        
        entered = self.otp_input.text().strip()
        if len(entered) != 6 or not entered.isdigit():
            QMessageBox.warning(self, "Invalid Code", "Please enter a 6-digit code.")
            return
        
        entered_hash = hashlib.sha256(entered.encode()).hexdigest()
        if entered_hash == self.stored_hash:
            self.accept()
        else:
            QMessageBox.warning(self, "Wrong Code", "Invalid BambiCode. Try again.")
            self.otp_input.clear()
            self.otp_input.setFocus()
    
    def get_otp(self) -> str:
        """Get the OTP (entered or generated)."""
        if self.mode == "set":
            return self.generated_otp
        else:
            return self.otp_input.text().strip()
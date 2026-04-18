"""Update dialog UI for BambiBrowser."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont

from core.auto_updater import AutoUpdater
from ui.styles import DARK_THEME


class UpdateDialog(QDialog):
    """Dialog for showing update notifications and progress."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.updater = None
        self.current_version = "0.0.0"
        self.release_url = ""
        self.new_version = ""
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle("💾 BambiBrowser Update")
        self.setFixedSize(480, 320)
        self.setModal(True)
        self.setStyleSheet(DARK_THEME + """
            QDialog {
                background: #0b0b12;
            }
            QLabel {
                color: #f5f5ff;
            }
            QPushButton {
                background: #ff6bd6;
                color: #1a0b1f;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 13px;
                border: none;
            }
            QPushButton:hover {
                background: #ff8be0;
            }
            QPushButton:disabled {
                background: #3a3a4a;
                color: #888;
            }
            QProgressBar {
                border: 2px solid #333;
                border-radius: 6px;
                background: #151521;
                color: #ff6bd6;
                text-align: center;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ff6bd6, stop:1 #ff8be0);
                border-radius: 4px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(25, 25, 25, 25)
        
        # Title
        title = QLabel("🎉 Update Available")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #7dff9a;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Message
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("color: #ccc; font-size: 12px;")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.message_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)
        
        # Progress message
        self.progress_message = QLabel()
        self.progress_message.setVisible(False)
        self.progress_message.setStyleSheet("color: #888; font-size: 11px;")
        self.progress_message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.progress_message)
        
        layout.addStretch()
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        self.download_btn = QPushButton("⬇️ Download & Install")
        self.download_btn.clicked.connect(self._on_download_clicked)
        button_layout.addWidget(self.download_btn)
        
        self.later_btn = QPushButton("⏱️ Later")
        self.later_btn.setStyleSheet("""
            QPushButton {
                background: #26263a;
                color: #ff6bd6;
                font-weight: bold;
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 13px;
                border: 1px solid #ff6bd6;
            }
            QPushButton:hover {
                background: #333350;
            }
        """)
        self.later_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.later_btn)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def set_updater(self, updater: AutoUpdater, current_version: str):
        """Set the updater and connect signals."""
        self.updater = updater
        self.current_version = current_version
        
        # Disconnect any existing connections
        try:
            self.updater.update_progress.disconnect()
            self.updater.update_ready_to_install.disconnect()
            self.updater.error_occurred.disconnect()
        except:
            pass
        
        # Connect updater signals
        self.updater.update_progress.connect(self._on_download_progress)
        self.updater.update_ready_to_install.connect(self._on_update_ready)
        self.updater.error_occurred.connect(self._on_update_error)
    
    def show_update_available(self, new_version: str, release_url: str):
        """Show update available notification."""
        self.release_url = release_url
        self.new_version = new_version
        
        self.message_label.setText(
            f"<p>A new version of BambiBrowser is available!</p>"
            f"<p>Current version: <b>v{self.current_version}</b><br>"
            f"Latest version: <b style='color: #7dff9a;'>v{new_version}</b></p>"
            f"<p>Would you like to download and install the update?<br>"
            f"<span style='color: #888; font-size: 11px;'>The application will restart after installation.</span></p>"
        )
        self.show()
        self.raise_()
        self.activateWindow()
    
    def _on_download_clicked(self):
        """Handle download button click."""
        self.download_btn.setEnabled(False)
        self.later_btn.setEnabled(False)
        
        self.progress_bar.setVisible(True)
        self.progress_message.setVisible(True)
        self.progress_bar.setValue(0)
        
        self.message_label.setText("<b>Preparing download...</b>")
        self.message_label.setStyleSheet("color: #ff6bd6; font-size: 13px;")
        
        if self.updater:
            self.updater.download_update(self.release_url)
        else:
            self._on_update_error("Updater not initialized")
    
    def _on_download_progress(self, percentage: int, message: str):
        """Handle download progress."""
        self.progress_bar.setValue(percentage)
        self.progress_message.setText(message)
        
        if percentage < 20:
            self.message_label.setText("<b>Starting download...</b>")
        elif percentage < 80:
            self.message_label.setText(f"<b>Downloading update... {percentage}%</b>")
        else:
            self.message_label.setText("<b>Finalizing download...</b>")
    
    def _on_update_ready(self, update_file: str):
        """Handle update ready for installation."""
        self.progress_bar.setValue(100)
        self.progress_message.setText("Download complete!")
        self.message_label.setText("<b>✨ Update downloaded successfully!</b>")
        self.message_label.setStyleSheet("color: #7dff9a; font-size: 13px;")
        
        reply = QMessageBox.question(
            self,
            "Install Update?",
            f"BambiBrowser v{self.new_version} has been downloaded!\n\n"
            f"The application will restart to complete the installation.\n"
            f"Please ensure no videos are currently playing.\n\n"
            f"Install now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.updater:
                # Define restart callback
                def restart_app():
                    import sys
                    import subprocess
                    from pathlib import Path
                    
                    # Get the main script path
                    base_dir = Path(update_file).parent.parent
                    main_script = base_dir / "bambi_browser.py"
                    
                    if not main_script.exists():
                        # Try to find the executable
                        exe_path = base_dir / "BambiBrowser.exe"
                        if exe_path.exists():
                            subprocess.Popen([str(exe_path)])
                        else:
                            # Fallback to python
                            python_exe = sys.executable
                            subprocess.Popen([python_exe, str(main_script)])
                    else:
                        python_exe = sys.executable
                        subprocess.Popen([python_exe, str(main_script)])
                    
                    sys.exit(0)
                
                # Install the update
                self.updater.install_update(update_file, restart_app)
                self.accept()
        else:
            self.reject()
    
    def _on_update_error(self, error: str):
        """Handle update error."""
        self.download_btn.setEnabled(True)
        self.later_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_message.setVisible(False)
        
        self.message_label.setText(f"<b>❌ Update Failed</b><br><br>{error}")
        self.message_label.setStyleSheet("color: #ff6b6b; font-size: 12px;")
        
        QMessageBox.warning(
            self,
            "Update Failed",
            f"Failed to download or install update:\n\n{error}\n\n"
            f"You can try again later or download manually from:\n"
            f"https://github.com/sissy3city/BambiBrowser/releases"
        )
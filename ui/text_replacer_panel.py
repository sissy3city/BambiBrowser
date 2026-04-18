"""Text Replacer settings panel - Powered by AutoHotkey with settings lock."""

import logging
import json
from typing import Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QLineEdit, QCheckBox,
    QTextEdit, QRadioButton, QComboBox, QFileDialog,
    QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QSettings

logger = logging.getLogger("BambiBrowser.UI.TextReplacer")


class TextReplacerPanel(QWidget):
    """Panel for managing OS-level text replacements with settings lock."""
    
    rules_changed = pyqtSignal(dict)
    toggle_requested = pyqtSignal(bool)
    
    def __init__(self, text_replacer, parent=None):
        super().__init__(parent)
        self.text_replacer = text_replacer
        self.settings = QSettings("BambiBrowser", "Settings")
        self._locked = False
        
        self._setup_ui()
        self._connect_signals()
        self._load_settings()
        self._update_ahk_status()
        self._update_lock_state()
    
    def _connect_signals(self):
        """Connect signals after UI is set up."""
        if self.text_replacer:
            self.text_replacer.replacements_updated.connect(self._on_rules_updated)
            self.text_replacer.status_changed.connect(self._on_status_changed)
        
        self.table.itemChanged.connect(self._on_table_item_changed)
    
    def _setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # ========== Header with Toggle ==========
        header_layout = QHBoxLayout()
        
        title = QLabel("🔄 OS Text Replacer")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ff6bd6;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # AHK Status indicator
        self.ahk_status_label = QLabel()
        self.ahk_status_label.setStyleSheet("font-size: 11px; padding: 4px 8px; border-radius: 12px;")
        header_layout.addWidget(self.ahk_status_label)
        
        # Toggle button
        self.toggle_btn = QPushButton("▶ Start")
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background: #34c759;
                color: white;
                font-weight: bold;
                padding: 10px 24px;
                border-radius: 20px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #28a745;
            }
            QPushButton:disabled {
                background: #3a3a4a;
                color: #888;
            }
        """)
        self.toggle_btn.clicked.connect(self._on_toggle_clicked)
        header_layout.addWidget(self.toggle_btn)
        
        main_layout.addLayout(header_layout)
        
        # ========== Lock Status ==========
        self.lock_status_label = QLabel()
        self.lock_status_label.setStyleSheet("""
            font-size: 12px;
            padding: 8px;
            background: #151521;
            border-radius: 8px;
        """)
        self.lock_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.lock_status_label)
        
        # ========== Status Bar ==========
        self.status_label = QLabel("⏸ Stopped")
        self.status_label.setStyleSheet("""
            font-size: 13px;
            color: #888;
            padding: 10px;
            background: #151521;
            border-radius: 8px;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # ========== Replacement Rules ==========
        rules_group = QGroupBox("📝 Replacement Rules")
        rules_group.setStyleSheet("""
            QGroupBox {
                font-size: 14px;
                font-weight: bold;
                color: #ff6bd6;
                border: 2px solid #333;
                border-radius: 10px;
                margin-top: 12px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 8px;
                background: #0b0b12;
            }
        """)
        
        rules_layout = QVBoxLayout()
        rules_layout.setSpacing(10)
        rules_layout.setContentsMargins(16, 16, 16, 16)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Trigger Word", "Replacement", ""])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 60)
        self.table.setMinimumHeight(250)
        self.table.setStyleSheet("""
            QTableWidget {
                background: #151521;
                border: 1px solid #333;
                border-radius: 8px;
                gridline-color: #2a2a3a;
            }
            QTableWidget::item {
                padding: 8px;
                color: #f5f5ff;
            }
            QTableWidget::item:selected {
                background: #3a3a5a;
            }
            QHeaderView::section {
                background: #1a1a2a;
                color: #ff6bd6;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
            QTableWidget:disabled {
                opacity: 0.5;
            }
        """)
        rules_layout.addWidget(self.table)
        
        # Add new rule
        add_layout = QHBoxLayout()
        add_layout.setSpacing(8)
        
        self.original_input = QLineEdit()
        self.original_input.setPlaceholderText("Trigger (e.g., i)")
        self.original_input.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 2px solid #444;
                border-radius: 8px;
                background: #151521;
                color: #f5f5ff;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #ff6bd6;
            }
            QLineEdit:disabled {
                opacity: 0.5;
            }
        """)
        add_layout.addWidget(self.original_input)
        
        arrow_label = QLabel("→")
        arrow_label.setStyleSheet("font-size: 16px; color: #ff6bd6; font-weight: bold;")
        add_layout.addWidget(arrow_label)
        
        self.replacement_input = QLineEdit()
        self.replacement_input.setPlaceholderText("Replacement (e.g., Bambi)")
        self.replacement_input.setStyleSheet("""
            QLineEdit {
                padding: 10px;
                border: 2px solid #444;
                border-radius: 8px;
                background: #151521;
                color: #f5f5ff;
                font-size: 13px;
            }
            QLineEdit:focus {
                border-color: #ff6bd6;
            }
            QLineEdit:disabled {
                opacity: 0.5;
            }
        """)
        add_layout.addWidget(self.replacement_input)
        
        self.add_btn = QPushButton("➕ Add")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: #3a3a5a;
                color: white;
                padding: 10px 20px;
                border-radius: 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #4a4a6a;
            }
            QPushButton:disabled {
                background: #2a2a3a;
                color: #666;
            }
        """)
        self.add_btn.clicked.connect(self._add_rule)
        add_layout.addWidget(self.add_btn)
        
        rules_layout.addLayout(add_layout)
        
        # Preset buttons
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(8)
        
        preset_label = QLabel("Presets:")
        preset_label.setStyleSheet("color: #888; font-size: 12px;")
        preset_layout.addWidget(preset_label)
        
        for name, display in [("bambi_basic", "Bambi L1"), ("bambi_advanced", "Bambi L2"), 
                              ("bambi_max", "Bambi L3 (Max)")]:
            btn = QPushButton(display)
            btn.setStyleSheet("""
                QPushButton {
                    background: #2a2a3a;
                    color: #ccc;
                    padding: 6px 12px;
                    border-radius: 4px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background: #3a3a4a;
                    color: #ff6bd6;
                }
                QPushButton:disabled {
                    opacity: 0.5;
                }
            """)
            btn.clicked.connect(lambda checked, n=name: self._add_preset(n))
            preset_layout.addWidget(btn)
        
        preset_layout.addStretch()
        rules_layout.addLayout(preset_layout)
        
        # Action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        
        self.reset_default_btn = QPushButton("🔄 Reset to Default")
        self.reset_default_btn.setStyleSheet("""
            QPushButton {
                background: #26263a;
                color: #f5f5ff;
                padding: 10px 16px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #333350;
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)
        self.reset_default_btn.clicked.connect(self._reset_to_default)
        action_layout.addWidget(self.reset_default_btn)
        
        self.clear_all_btn = QPushButton("🗑 Clear All")
        self.clear_all_btn.setStyleSheet("""
            QPushButton {
                background: #3a1a1a;
                color: #ff6b6b;
                padding: 10px 16px;
                border-radius: 8px;
            }
            QPushButton:hover {
                background: #5a2a2a;
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)
        self.clear_all_btn.clicked.connect(self._clear_all)
        action_layout.addWidget(self.clear_all_btn)
        
        action_layout.addStretch()
        
        self.stats_label = QLabel("0 rules")
        self.stats_label.setStyleSheet("font-size: 12px; color: #666;")
        action_layout.addWidget(self.stats_label)
        
        rules_layout.addLayout(action_layout)
        
        # Import/Export buttons
        io_layout = QHBoxLayout()
        io_layout.setSpacing(8)
        
        self.export_btn = QPushButton("📤 Export")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                padding: 6px 12px;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #7dff9a;
                border-color: #7dff9a;
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)
        self.export_btn.clicked.connect(self._export_rules)
        io_layout.addWidget(self.export_btn)
        
        self.import_btn = QPushButton("📥 Import")
        self.import_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                padding: 6px 12px;
                border: 1px solid #444;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #7dff9a;
                border-color: #7dff9a;
            }
            QPushButton:disabled {
                opacity: 0.5;
            }
        """)
        self.import_btn.clicked.connect(self._import_rules)
        io_layout.addWidget(self.import_btn)
        
        io_layout.addStretch()
        rules_layout.addLayout(io_layout)
        
        rules_group.setLayout(rules_layout)
        main_layout.addWidget(rules_group)
        
        # ========== Script Preview ==========
        self.preview_btn = QPushButton("📄 Show AHK Script Preview")
        self.preview_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #888;
                padding: 8px;
                border: 1px dashed #444;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #ff6bd6;
                border-color: #ff6bd6;
            }
        """)
        self.preview_btn.clicked.connect(self._toggle_preview)
        main_layout.addWidget(self.preview_btn)
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setVisible(False)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background: #0a0a14;
                color: #7dff9a;
                border: 1px solid #333;
                border-radius: 6px;
                padding: 8px;
                font-size: 11px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        main_layout.addWidget(self.preview_text)
        
        # ========== AHK Download Help ==========
        if self.text_replacer and not self.text_replacer.ahk_available:
            ahk_help = QLabel(
                "⚠️ <b>AutoHotkey Not Found</b><br>"
                "Download from: <a href='https://www.autohotkey.com/' style='color: #ff6bd6;'>https://www.autohotkey.com/</a><br>"
                "Or place AutoHotkey.exe in the 'ahk' folder next to this application."
            )
            ahk_help.setStyleSheet("""
                font-size: 12px;
                color: #ff6b6b;
                padding: 12px;
                background: #2a1a1a;
                border-radius: 8px;
                border: 1px solid #ff6b6b;
            """)
            ahk_help.setWordWrap(True)
            ahk_help.setOpenExternalLinks(True)
            main_layout.addWidget(ahk_help)
        
        self.setLayout(main_layout)
    
    def _update_ahk_status(self):
        """Update AHK availability indicator."""
        if self.text_replacer and self.text_replacer.ahk_available:
            self.ahk_status_label.setText("✅ AHK Ready")
            self.ahk_status_label.setStyleSheet("""
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 12px;
                background: #1a3a1a;
                color: #7dff9a;
            """)
        else:
            self.ahk_status_label.setText("❌ AHK Missing")
            self.ahk_status_label.setStyleSheet("""
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 12px;
                background: #3a1a1a;
                color: #ff6b6b;
            """)
    

    def _load_settings(self):
        """Load settings from QSettings."""
        # Text replacer has its own lock state (separate from playback settings)
        saved_tr_lock_hash = self.settings.value("text_replacer/otp_hash", "")
        self._locked = bool(saved_tr_lock_hash and saved_tr_lock_hash.strip() != "")
        
        if self.text_replacer:
            self.text_replacer._locked = self._locked
        
        # Load saved text replacer settings - always use auto mode
        saved_rules = self.settings.value("text_replacer/rules", {})
        
        if isinstance(saved_rules, str):
            try:
                saved_rules = json.loads(saved_rules)
            except:
                saved_rules = {}
        
        # Apply to text_replacer
        if self.text_replacer:
            self.text_replacer._use_prefix = False
            if saved_rules:
                self.text_replacer._replacement_rules = saved_rules
        
        self._load_rules()
        self._update_lock_state()
    
    def _save_settings(self):
        """Save settings to QSettings."""
        rules = {}
        for row in range(self.table.rowCount()):
            original = self.table.item(row, 0)
            replacement = self.table.item(row, 1)
            if original and replacement:
                rules[original.text()] = replacement.text()
        
        # Always use auto mode (prefix mode removed)
        self.settings.setValue("text_replacer/rules", json.dumps(rules))
        
        if self.text_replacer:
            self.text_replacer._use_prefix = False
    
    def _update_lock_state(self):
        """Update UI based on lock state."""
        enabled = not self._locked
        
        # Update text replacer lock state
        if self.text_replacer:
            self.text_replacer._locked = self._locked
        
        # Disable all controls when locked
        self.table.setEnabled(enabled)
        self.original_input.setEnabled(enabled)
        self.replacement_input.setEnabled(enabled)
        self.add_btn.setEnabled(enabled)
        self.reset_default_btn.setEnabled(enabled)
        self.clear_all_btn.setEnabled(enabled)
        self.export_btn.setEnabled(True)  # Export always allowed
        self.import_btn.setEnabled(enabled)
        
        # Update lock status label
        if self._locked:
            self.lock_status_label.setText("🔒 TEXT REPLACER SETTINGS LOCKED")
            self.lock_status_label.setStyleSheet("""
                font-size: 12px;
                color: #ff6b6b;
                padding: 8px;
                background: #2a1a1a;
                border-radius: 8px;
                font-weight: bold;
            """)
        else:
            self.lock_status_label.setText("🔓 Settings Unlocked - Save to lock")
            self.lock_status_label.setStyleSheet("""
                font-size: 12px;
                color: #7dff9a;
                padding: 8px;
                background: #151521;
                border-radius: 8px;
            """)
    
    def set_locked(self, locked: bool):
        """Set the locked state (called from main window when settings saved/unlocked)."""
        self._locked = locked
        if self.text_replacer:
            self.text_replacer._locked = locked
        self._update_lock_state()
        self._save_settings()
    
    def _load_rules(self):
        """Load current rules into table."""
        if not self.text_replacer:
            return
        
        try:
            self.table.itemChanged.disconnect(self._on_table_item_changed)
        except TypeError:
            pass
        
        self.table.setRowCount(0)
        
        rules = self.text_replacer.rules
        
        for original, replacement in rules.items():
            self._add_rule_to_table(original, replacement)
        
        self._update_stats()
        self._update_toggle_button()
        
        self.table.itemChanged.connect(self._on_table_item_changed)
    
    def _add_rule_to_table(self, original: str, replacement: str):
        """Add a rule to the table."""
        row = self.table.rowCount()
        self.table.insertRow(row)
        
        original_item = QTableWidgetItem(original)
        original_item.setFlags(original_item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, original_item)
        
        replacement_item = QTableWidgetItem(replacement)
        replacement_item.setFlags(replacement_item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 1, replacement_item)
        
        delete_btn = QPushButton("❌")
        delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                padding: 4px;
            }
            QPushButton:hover {
                background: #3a1a1a;
                border-radius: 4px;
            }
        """)
        delete_btn.clicked.connect(lambda checked, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 2, delete_btn)
    
    def _delete_row(self, row: int):
        """Delete a row from the table."""
        if self._locked:
            return
        
        original_item = self.table.item(row, 0)
        if original_item and self.text_replacer:
            self.text_replacer.remove_rule(original_item.text())
        
        self.table.removeRow(row)
        self._update_stats()
        self._emit_rules()
        self._save_settings()
    
    def _on_table_item_changed(self, item: QTableWidgetItem):
        """Handle manual edits to table cells."""
        if self._locked:
            return
        self._emit_rules()
        self._save_settings()
    
    def _add_rule(self):
        """Add a new rule from input fields."""
        if self._locked:
            QMessageBox.warning(self, "Settings Locked", "Cannot add rules while settings are locked.")
            return
        
        original = self.original_input.text().strip()
        replacement = self.replacement_input.text().strip()
        
        if not original or not replacement:
            QMessageBox.warning(self, "Invalid Input", "Both fields are required.")
            return
        
        if self.text_replacer:
            self.text_replacer.add_rule(original, replacement)
            self._add_rule_to_table(original.lower(), replacement)
        
        self.original_input.clear()
        self.replacement_input.clear()
        self.original_input.setFocus()
        
        self._update_stats()
        self._emit_rules()
        self._save_settings()
    
    def _add_preset(self, preset_name: str):
        """Add a preset of rules."""
        if self._locked:
            QMessageBox.warning(self, "Settings Locked", "Cannot add presets while settings are locked.")
            return
        
        presets = {
            "bambi_basic": {
                "i": "Bambi", "me": "Bambi", "my": "Bambi's",
                "mine": "Bambi's", "myself": "Bambi",
            },
            "bambi_advanced": {
                "i": "Bambi", "me": "Bambi", "my": "Bambi's",
                "mine": "Bambi's", "myself": "Bambi", "im": "Bambi is",
                "ive": "Bambi has", "id": "Bambi would", "ill": "Bambi will",
                "we": "Bambi and friends", "our": "Bambi's", "ours": "Bambi's",
            },
            "bambi_max": {
                "i": "your dumb bimbo Bambi", "me": "dumb bimbo Bambi", "my": "dumb bimbo Bambi's",
                "mine": "dumb bimbo Bambi's", "myself": "dumb bimbo Bambi",
                "im": "your stupid horny bimbo is", "ive": "your dumb whore has",
                "id": "dumb bimbo would", "ill": "your stupid slut will",
                "we": "stupid bitches", "our": "dumb sluts'", "ours": "dumb sluts'",
                "think": "mindlessly drool about", "understand": "comprehend with my empty skull",
                "feel": "feel in my needy pussy", "want": "desperately crave",
                "need": "desperately need to fuck", "love": "live to serve and please",
                "brain": "empty dumb bimbo brain", "smart": "cock-drunk", "intelligent": "ditzy",
                "book": "dick", "study": "suck", "learn": "become more of a bimbo",
            },
        }
        
        if preset_name in presets:
            reply = QMessageBox.question(
                self, "Add Preset",
                f"Add '{preset_name}' preset? This will merge with existing rules.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                for original, replacement in presets[preset_name].items():
                    exists = False
                    for row in range(self.table.rowCount()):
                        if self.table.item(row, 0).text().lower() == original.lower():
                            exists = True
                            break
                    
                    if not exists:
                        self.text_replacer.add_rule(original, replacement)
                        self._add_rule_to_table(original, replacement)
                
                self._update_stats()
                self._emit_rules()
                self._save_settings()
                
                QMessageBox.information(self, "Preset Added", f"Added {preset_name} preset!")
    
    def _reset_to_default(self):
        """Reset to default Bambi rules."""
        if self._locked:
            QMessageBox.warning(self, "Settings Locked", "Cannot reset while settings are locked.")
            return
        
        reply = QMessageBox.question(
            self, "Reset to Default",
            "Replace all rules with default Bambi replacements?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.text_replacer:
                self.text_replacer.reset_to_default()
                self._load_rules()
                self._emit_rules()
                self._save_settings()
    
    def _clear_all(self):
        """Clear all rules."""
        if self._locked:
            QMessageBox.warning(self, "Settings Locked", "Cannot clear while settings are locked.")
            return
        
        reply = QMessageBox.question(
            self, "Clear All",
            "Remove ALL replacement rules?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            if self.text_replacer:
                self.text_replacer.clear_rules()
            self.table.setRowCount(0)
            self._update_stats()
            self._emit_rules()
            self._save_settings()
    
    def _export_rules(self):
        """Export rules to a JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Replacement Rules",
            "bambi_replacements.json", "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                rules = {}
                for row in range(self.table.rowCount()):
                    original = self.table.item(row, 0)
                    replacement = self.table.item(row, 1)
                    if original and replacement:
                        rules[original.text()] = replacement.text()
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(rules, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(self, "Export Successful", 
                                       f"Exported {len(rules)} rules to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", str(e))
    
    def _import_rules(self):
        """Import rules from a JSON file."""
        if self._locked:
            QMessageBox.warning(self, "Settings Locked", "Cannot import while settings are locked.")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Replacement Rules",
            "", "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    rules = json.load(f)
                
                if not isinstance(rules, dict):
                    raise ValueError("Invalid format - expected dictionary")
                
                reply = QMessageBox.question(
                    self, "Import Rules",
                    f"Found {len(rules)} rules. Replace existing or merge?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | 
                    QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Yes
                )
                
                if reply == QMessageBox.StandardButton.Cancel:
                    return
                
                if reply == QMessageBox.StandardButton.Yes:
                    self.table.setRowCount(0)
                    if self.text_replacer:
                        self.text_replacer.clear_rules()
                
                for original, replacement in rules.items():
                    if original and replacement:
                        exists = False
                        for row in range(self.table.rowCount()):
                            if self.table.item(row, 0).text() == original:
                                if reply == QMessageBox.StandardButton.No:
                                    self.table.item(row, 1).setText(replacement)
                                exists = True
                                break
                        
                        if not exists:
                            if self.text_replacer:
                                self.text_replacer.add_rule(original, replacement)
                            self._add_rule_to_table(original, replacement)
                
                self._update_stats()
                self._emit_rules()
                self._save_settings()
                
                QMessageBox.information(self, "Import Successful", f"Imported {len(rules)} rules")
                
            except Exception as e:
                QMessageBox.critical(self, "Import Failed", f"Error: {e}")
    
    def _emit_rules(self):
        """Emit the current rules."""
        rules = {}
        for row in range(self.table.rowCount()):
            original = self.table.item(row, 0)
            replacement = self.table.item(row, 1)
            if original and replacement:
                rules[original.text()] = replacement.text()
        
        if self.text_replacer:
            self.text_replacer.set_rules(rules)
        
        self.rules_changed.emit(rules)
    
    def _update_stats(self):
        """Update stats label."""
        count = self.table.rowCount()
        self.stats_label.setText(f"{count} rule{'s' if count != 1 else ''}")
    
    def _on_toggle_clicked(self):
        """Handle toggle button click."""
        if self.text_replacer:
            if self.text_replacer.is_enabled:
                self.text_replacer.stop()
            else:
                self.text_replacer.start()
    
    def _on_status_changed(self, enabled: bool):
        """Update UI when status changes."""
        self._update_toggle_button()
        
        if enabled:
            self.status_label.setText("🟢 ACTIVE - Auto-replace mode")
            self.status_label.setStyleSheet("""
                font-size: 13px;
                color: #7dff9a;
                padding: 10px;
                background: #1a2a1a;
                border-radius: 8px;
                font-weight: bold;
            """)
        else:
            self.status_label.setText("⏸ Stopped - Click Start to enable")
            self.status_label.setStyleSheet("""
                font-size: 13px;
                color: #888;
                padding: 10px;
                background: #151521;
                border-radius: 8px;
            """)
    
    def _update_toggle_button(self):
        """Update toggle button appearance."""
        if self.text_replacer and self.text_replacer.is_enabled:
            self.toggle_btn.setText("⏹ Stop")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #ff3b30;
                    color: white;
                    font-weight: bold;
                    padding: 10px 24px;
                    border-radius: 20px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #d63030;
                }
            """)
        else:
            self.toggle_btn.setText("▶ Start")
            self.toggle_btn.setStyleSheet("""
                QPushButton {
                    background: #34c759;
                    color: white;
                    font-weight: bold;
                    padding: 10px 24px;
                    border-radius: 20px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #28a745;
                }
            """)
    
    def _on_rules_updated(self, rules: dict):
        """Handle rules updated from text_replacer."""
        try:
            self.table.itemChanged.disconnect(self._on_table_item_changed)
        except TypeError:
            pass
        
        self.table.setRowCount(0)
        for original, replacement in rules.items():
            self._add_rule_to_table(original, replacement)
        self._update_stats()
        
        self.table.itemChanged.connect(self._on_table_item_changed)
    
    def _toggle_preview(self):
        """Toggle script preview visibility."""
        if self.preview_text.isVisible():
            self.preview_text.setVisible(False)
            self.preview_btn.setText("📄 Show AHK Script Preview")
        else:
            if self.text_replacer:
                self.preview_text.setText(self.text_replacer.get_script_preview())
            self.preview_text.setVisible(True)
            self.preview_btn.setText("📄 Hide AHK Script Preview")
    
    def get_settings(self) -> dict:
        """Get current settings for persistence."""
        rules = {}
        for row in range(self.table.rowCount()):
            original = self.table.item(row, 0)
            replacement = self.table.item(row, 1)
            if original and replacement:
                rules[original.text()] = replacement.text()
        
        return {
            "enabled": self.text_replacer.is_enabled if self.text_replacer else False,
            "rules": rules,
        }
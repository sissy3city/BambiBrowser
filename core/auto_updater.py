"""Auto-updater for BambiBrowser - checks and installs updates from GitHub."""

import json
import logging
import os
import shutil
import subprocess
import threading
import tempfile
import zipfile
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

import requests
from PyQt6.QtCore import QObject, pyqtSignal, QThread

logger = logging.getLogger("BambiBrowser.AutoUpdater")

GITHUB_REPO = "sissy3city/BambiBrowser"
UPDATE_CHECK_INTERVAL = 3600  # Check every hour


class Version:
    """Semantic version parser."""
    
    def __init__(self, version_string: str):
        """Parse version string (e.g., '1.2.3')."""
        try:
            parts = version_string.strip().split('.')
            self.major = int(parts[0]) if len(parts) > 0 else 0
            self.minor = int(parts[1]) if len(parts) > 1 else 0
            self.patch = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, IndexError):
            logger.warning(f"Invalid version string: {version_string}")
            self.major = self.minor = self.patch = 0
    
    def __lt__(self, other: "Version") -> bool:
        """Check if this version is older than other."""
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __le__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)
    
    def __gt__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) > (other.major, other.minor, other.patch)
    
    def __ge__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) >= (other.major, other.minor, other.patch)
    
    def __eq__(self, other: "Version") -> bool:
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


class GitHubUpdateChecker(QThread):
    """Background thread for checking GitHub releases."""
    
    update_available = pyqtSignal(str, str)  # new_version, release_url
    check_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, current_version: str):
        super().__init__()
        self.current_version = Version(current_version)
        self._running = True
    
    def run(self):
        """Check for updates from GitHub."""
        try:
            logger.info("Checking for updates...")
            
            api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            
            release_data = response.json()
            
            # Get version from tag (e.g., "v1.2.3" -> "1.2.3")
            tag_name = release_data.get("tag_name", "").lstrip('v')
            latest_version = Version(tag_name)
            
            logger.info(f"Current: {self.current_version}, Latest: {latest_version}")
            
            # Check if update is available
            if latest_version > self.current_version:
                release_url = release_data.get("html_url", "")
                logger.info(f"Update available: {latest_version}")
                self.update_available.emit(str(latest_version), release_url)
            else:
                logger.info("Already running latest version")
            
            self.check_complete.emit()
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to check for updates: {e}")
            self.error_occurred.emit(f"Update check failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error checking for updates: {e}")
            self.error_occurred.emit(f"Unexpected error: {e}")
    
    def stop(self):
        """Stop the checker thread."""
        self._running = False


class GitHubUpdateDownloader(QThread):
    """Background thread for downloading and installing updates."""
    
    progress = pyqtSignal(int, str)  # percentage, message
    download_complete = pyqtSignal(str)  # path to downloaded file
    error_occurred = pyqtSignal(str)
    
    def __init__(self, release_url: str, download_dir: Path):
        super().__init__()
        self.release_url = release_url
        self.download_dir = download_dir
        self._running = True
    
    def run(self):
        """Download the latest release."""
        try:
            logger.info(f"Downloading update from {self.release_url}...")
            
            # Get release info from GitHub API
            api_url = self.release_url.replace("https://github.com", "https://api.github.com/repos")
            api_url = api_url.replace("/releases/tag/", "/releases/tags/")
            
            response = requests.get(api_url, timeout=10)
            response.raise_for_status()
            release_data = response.json()
            
            # Find the Windows ZIP asset
            download_url = None
            for asset in release_data.get("assets", []):
                if "windows" in asset["name"].lower() or asset["name"].endswith(".zip"):
                    download_url = asset["browser_download_url"]
                    break
            
            if not download_url:
                raise ValueError("No Windows release found for this version")
            
            self.progress.emit(10, "Found release, starting download...")
            
            # Download the file
            response = requests.get(download_url, timeout=30, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get("content-length", 0))
            download_path = self.download_dir / "BambiBrowser_update.zip"
            
            downloaded = 0
            with open(download_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if not self._running:
                        download_path.unlink(missing_ok=True)
                        return
                    
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    progress_pct = int((downloaded / total_size * 90) + 10) if total_size > 0 else 50
                    self.progress.emit(progress_pct, f"Downloading... {downloaded // 1024 // 1024}MB")
            
            self.progress.emit(95, "Download complete, verifying...")
            logger.info(f"Update downloaded to {download_path}")
            
            self.download_complete.emit(str(download_path))
            
        except Exception as e:
            logger.error(f"Failed to download update: {e}")
            self.error_occurred.emit(f"Download failed: {e}")
    
    def stop(self):
        """Stop the download."""
        self._running = False


class AutoUpdater(QObject):
    """Main auto-updater class."""
    
    update_available = pyqtSignal(str, str)  # new_version, release_url
    update_ready_to_install = pyqtSignal(str)  # path to update file
    update_progress = pyqtSignal(int, str)  # percentage, message
    error_occurred = pyqtSignal(str)
    
    def __init__(self, app_dir: Path):
        super().__init__()
        self.app_dir = app_dir
        self.version_file = app_dir / "VERSION"
        self.download_dir = Path(tempfile.gettempdir()) / "BambiBrowser_Updates"
        self.download_dir.mkdir(exist_ok=True)
        
        self.current_version = self._load_version()
        self._checker_thread: Optional[GitHubUpdateChecker] = None
        self._downloader_thread: Optional[GitHubUpdateDownloader] = None
        
        logger.info(f"AutoUpdater initialized - Current version: {self.current_version}")
    
    def _load_version(self) -> str:
        """Load version from VERSION file."""
        try:
            if self.version_file.exists():
                with open(self.version_file, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            logger.warning(f"Failed to read VERSION file: {e}")
        
        return "0.0.0"
    
    def check_for_updates(self):
        """Start background check for updates."""
        if self._checker_thread and self._checker_thread.isRunning():
            logger.warning("Update check already in progress")
            return
        
        self._checker_thread = GitHubUpdateChecker(self.current_version)
        self._checker_thread.update_available.connect(self._on_update_available)
        self._checker_thread.error_occurred.connect(self._on_check_error)
        self._checker_thread.start()
    
    def _on_update_available(self, new_version: str, release_url: str):
        """Handle update available signal."""
        logger.info(f"Update available: {new_version}")
        self.update_available.emit(new_version, release_url)
    
    def _on_check_error(self, error: str):
        """Handle check error."""
        logger.warning(f"Update check error: {error}")
        self.error_occurred.emit(error)
    
    def download_update(self, release_url: str):
        """Start downloading the update."""
        if self._downloader_thread and self._downloader_thread.isRunning():
            logger.warning("Download already in progress")
            return
        
        self._downloader_thread = GitHubUpdateDownloader(release_url, self.download_dir)
        self._downloader_thread.progress.connect(self._on_download_progress)
        self._downloader_thread.download_complete.connect(self._on_download_complete)
        self._downloader_thread.error_occurred.connect(self._on_download_error)
        self._downloader_thread.start()
    
    def _on_download_progress(self, percentage: int, message: str):
        """Handle download progress."""
        self.update_progress.emit(percentage, message)
    
    def _on_download_complete(self, file_path: str):
        """Handle download complete."""
        logger.info(f"Update downloaded: {file_path}")
        self.update_ready_to_install.emit(file_path)
    
    def _on_download_error(self, error: str):
        """Handle download error."""
        logger.error(f"Download error: {error}")
        self.error_occurred.emit(error)
    
    def install_update(self, update_file: str, restart_callback: Callable[[], None]):
        """
        Install the update and restart the application.
        
        Args:
            update_file: Path to the downloaded update ZIP file
            restart_callback: Callback to restart the application
        """
        try:
            logger.info(f"Installing update from {update_file}...")
            
            update_path = Path(update_file)
            if not update_path.exists():
                raise FileNotFoundError(f"Update file not found: {update_file}")
            
            # Extract update to temporary directory
            extract_dir = self.download_dir / "extracted_update"
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True)
            
            with zipfile.ZipFile(update_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            logger.info(f"Update extracted to {extract_dir}")
            
            # Find the main BambiBrowser directory in the ZIP
            bambi_dir = None
            for item in extract_dir.iterdir():
                if item.name == "BambiBrowser" and item.is_dir():
                    bambi_dir = item
                    break
            
            if not bambi_dir:
                # Maybe the ZIP contains files directly
                bambi_dir = extract_dir
            
            logger.info(f"Backup current installation to {self.app_dir}.backup...")
            
            # Backup current installation
            backup_dir = self.app_dir.parent / f"{self.app_dir.name}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if self.app_dir.exists():
                shutil.copytree(self.app_dir, backup_dir)
                logger.info(f"Backup created: {backup_dir}")
            
            # Replace files (excluding user settings and caches)
            exclude_dirs = {'.venv', '__pycache__', '.git', 'vlc/locale'}
            
            # Note: extensions/ folder IS included in updates
            # Both Chromium (at extension/chromium/) and Firefox (at extension/firefox/) will be updated
            
            for src_file in bambi_dir.rglob('*'):
                if src_file.is_dir():
                    continue
                
                # Skip excluded directories
                if any(excluded in src_file.parts for excluded in exclude_dirs):
                    continue
                
                rel_path = src_file.relative_to(bambi_dir)
                dst_file = self.app_dir / rel_path
                
                # Create dest directories
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file
                shutil.copy2(src_file, dst_file)
            
            # Update VERSION file
            with open(self.version_file, 'w') as f:
                # Extract version from release
                import re
                version_match = re.search(r'(\d+\.\d+\.\d+)', update_path.name)
                version = version_match.group(1) if version_match else self.current_version
                f.write(version)
            
            logger.info("Update installed successfully!")
            
            # Cleanup
            update_path.unlink(missing_ok=True)
            shutil.rmtree(extract_dir, ignore_errors=True)
            
            # Restart application
            logger.info("Restarting application...")
            if restart_callback:
                restart_callback()
            
        except Exception as e:
            logger.error(f"Failed to install update: {e}")
            self.error_occurred.emit(f"Installation failed: {e}")
    
    def cleanup(self):
        """Clean up threads."""
        if self._checker_thread:
            self._checker_thread.stop()
            self._checker_thread.wait()
        
        if self._downloader_thread:
            self._downloader_thread.stop()
            self._downloader_thread.wait()

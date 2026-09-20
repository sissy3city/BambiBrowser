"""FFmpeg portable downloader for accurate duration detection."""

import os
import zipfile
import urllib.request
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger("BambiBrowser.FFmpegDownloader")

# Direct download URL for ffmpeg essentials (Windows 64-bit)
# This is the official gyan.dev build - stable and widely used
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# Fallback URL in case the main one fails
FFMPEG_FALLBACK_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip"


def download_with_progress(url: str, dest_path: Path, description: str = "Downloading") -> bool:
    """Download a file with progress reporting."""
    try:
        logger.info(f"{description} from {url}")
        
        def report_progress(block_num: int, block_size: int, total_size: int):
            downloaded = block_num * block_size
            if total_size > 0:
                percent = min(100, int(downloaded * 100 / total_size))
                if percent % 25 == 0:  # Log every 25%
                    mb_downloaded = downloaded / (1024 * 1024)
                    mb_total = total_size / (1024 * 1024)
                    logger.info(f"Download progress: {percent}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)")
        
        urllib.request.urlretrieve(url, str(dest_path), reporthook=report_progress)
        return True
        
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return False


def extract_ffprobe(zip_path: Path, bin_dir: Path) -> bool:
    """Extract only ffprobe.exe from the zip file."""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Get list of all files
            file_list = zip_ref.namelist()
            
            # Look for ffprobe.exe
            ffprobe_files = [f for f in file_list if f.endswith('ffprobe.exe')]
            
            if not ffprobe_files:
                logger.error("ffprobe.exe not found in the downloaded package")
                return False
            
            # Use the first match
            ffprobe_in_zip = ffprobe_files[0]
            logger.info(f"Found ffprobe in zip: {ffprobe_in_zip}")
            
            # Extract to bin directory
            target_path = bin_dir / "ffprobe.exe"
            
            with zip_ref.open(ffprobe_in_zip) as source:
                with open(target_path, 'wb') as target:
                    target.write(source.read())
            
            logger.info(f"Extracted ffprobe.exe to {target_path}")
            
            # Also try to extract ffmpeg.exe (useful for other features)
            ffmpeg_files = [f for f in file_list if f.endswith('ffmpeg.exe')]
            if ffmpeg_files:
                target_path = bin_dir / "ffmpeg.exe"
                with zip_ref.open(ffmpeg_files[0]) as source:
                    with open(target_path, 'wb') as target:
                        target.write(source.read())
                logger.info(f"Extracted ffmpeg.exe to {target_path}")
            
            return True
            
    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return False


def download_ffprobe(target_dir: Path) -> bool:
    """
    Download ffprobe.exe from ffmpeg essentials package.
    Only extracts ffprobe.exe and ffmpeg.exe to save space.
    
    Args:
        target_dir: Directory to store ffmpeg files (will create 'bin' subdirectory)
    
    Returns:
        True if successful, False otherwise
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    bin_dir = target_dir / "bin"
    bin_dir.mkdir(exist_ok=True)
    
    ffprobe_path = bin_dir / "ffprobe.exe"
    
    # Check if already exists
    if ffprobe_path.exists():
        # Verify it works
        try:
            import subprocess
            result = subprocess.run(
                [str(ffprobe_path), "-version"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                logger.info(f"ffprobe already exists and works: {ffprobe_path}")
                return True
            else:
                logger.warning("Existing ffprobe appears broken, re-downloading...")
                ffprobe_path.unlink(missing_ok=True)
        except:
            logger.warning("Could not verify existing ffprobe, re-downloading...")
            ffprobe_path.unlink(missing_ok=True)
    
    # Create temp directory for download
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        zip_path = temp_path / "ffmpeg.zip"
        
        # Try primary URL
        success = download_with_progress(
            FFMPEG_DOWNLOAD_URL,
            zip_path,
            "Downloading FFmpeg essentials (~30 MB)"
        )
        
        # Try fallback URL if primary fails
        if not success:
            logger.info("Primary URL failed, trying fallback...")
            success = download_with_progress(
                FFMPEG_FALLBACK_URL,
                zip_path,
                "Downloading FFmpeg from fallback (~80 MB)"
            )
        
        if not success:
            logger.error("All download attempts failed")
            return False
        
        # Extract ffprobe
        if not extract_ffprobe(zip_path, bin_dir):
            return False
        
        # Clean up
        zip_path.unlink(missing_ok=True)
    
    # Verify the extracted file works
    ffprobe_path = bin_dir / "ffprobe.exe"
    if ffprobe_path.exists():
        try:
            import subprocess
            result = subprocess.run(
                [str(ffprobe_path), "-version"],
                capture_output=True,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                version_line = result.stdout.decode('utf-8', errors='ignore').split('\n')[0]
                logger.info(f"✅ ffprobe ready: {version_line[:50]}...")
                return True
        except Exception as e:
            logger.error(f"ffprobe verification failed: {e}")
    
    logger.error("ffprobe installation failed")
    return False


def ensure_ffprobe(base_dir: Path) -> Optional[str]:
    """
    Ensure ffprobe is available, downloading if necessary.
    
    Args:
        base_dir: Base directory of the application
    
    Returns:
        Path to ffprobe.exe if available, None otherwise
    """
    from core.duration_helper import get_ffprobe_path
    
    # Check if already available in system or bundled
    ffprobe_path = get_ffprobe_path()
    if ffprobe_path:
        logger.info(f"ffprobe found at: {ffprobe_path}")
        return ffprobe_path
    
    # Not found - needed for accurate video duration detection
    logger.info("ffprobe not found - needed for accurate video duration detection")

    import sys
    if sys.platform != "win32":
        # No Linux build is bundled/downloaded here - it's a system package.
        logger.warning(
            "ffprobe not found. Install it with: sudo dnf install ffmpeg ffmpeg-libs "
            "(requires RPM Fusion on stock Fedora). Duration detection will use estimates until then."
        )
        return None

    # In GUI mode, we can ask the user
    try:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        
        app = QApplication.instance()
        if app:
            reply = QMessageBox.question(
                None,
                "Download Duration Detector?",
                "BambiBrowser can download a small tool (~30 MB) to accurately detect video durations.\n\n"
                "This helps enforce safety limits (max video length).\n\n"
                "Without it, durations will be estimated and may be less accurate.\n\n"
                "Download now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.No:
                logger.info("User declined ffprobe download")
                return None
    except:
        # No GUI or error - auto-download
        logger.info("Auto-downloading ffprobe...")
    
    # Download ffprobe
    ffmpeg_dir = base_dir / "ffmpeg"
    
    logger.info("Downloading ffprobe - this may take a moment...")
    
    if download_ffprobe(ffmpeg_dir):
        ffprobe_path = ffmpeg_dir / "bin" / "ffprobe.exe"
        if ffprobe_path.exists():
            logger.info(f"ffprobe successfully installed: {ffprobe_path}")
            return str(ffprobe_path)
    
    logger.warning("Could not obtain ffprobe - duration detection will use estimates only")
    return None


def get_ffprobe_status(base_dir: Path) -> dict:
    """
    Get status of ffprobe availability.
    
    Returns:
        Dictionary with status information
    """
    from core.duration_helper import get_ffprobe_path
    
    ffprobe_path = get_ffprobe_path()
    
    status = {
        "available": ffprobe_path is not None,
        "path": ffprobe_path,
        "bundled": False,
    }
    
    if ffprobe_path:
        ffmpeg_dir = base_dir / "ffmpeg" / "bin" / "ffprobe.exe"
        status["bundled"] = Path(ffprobe_path) == ffmpeg_dir
        
        # Get version if possible
        try:
            import subprocess
            result = subprocess.run(
                [ffprobe_path, "-version"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                status["version"] = version_line.replace("ffprobe version", "").strip()
        except:
            status["version"] = "unknown"
    
    return status
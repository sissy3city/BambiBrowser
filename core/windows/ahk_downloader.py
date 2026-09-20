"""AutoHotkey portable downloader."""

import os
import zipfile
import urllib.request
from pathlib import Path
import logging

logger = logging.getLogger("BambiBrowser.AHKDownloader")

AHK_DOWNLOAD_URL = "https://www.autohotkey.com/download/ahk.zip"


def download_autohotkey(target_dir: Path) -> bool:
    """Download AutoHotkey portable to the specified directory."""
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / "ahk.zip"
    
    try:
        logger.info(f"Downloading AutoHotkey from {AHK_DOWNLOAD_URL}...")
        urllib.request.urlretrieve(AHK_DOWNLOAD_URL, zip_path)
        
        logger.info("Extracting...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
        
        zip_path.unlink()  # Delete zip
        
        # Find the actual exe
        for exe in target_dir.rglob("AutoHotkey*.exe"):
            logger.info(f"AutoHotkey ready: {exe}")
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Failed to download AutoHotkey: {e}")
        return False
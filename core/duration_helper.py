"""Helper functions for video duration handling."""

import subprocess
import logging
import json
import re
import urllib.request
import urllib.error
import tempfile
import os
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("BambiBrowser.DurationHelper")


def get_vlc_path() -> Optional[str]:
    """Get VLC executable path."""
    base_dir = Path(__file__).parent.parent
    
    # Check bundled VLC first
    vlc_path = base_dir / "vlc" / "vlc.exe"
    if vlc_path.exists():
        return str(vlc_path)
    
    # Check common installation paths
    candidates = [
        r"C:\Program Files\VideoLAN\VLC\vlc.exe",
        r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
    ]
    
    for path in candidates:
        if Path(path).exists():
            return path
    
    return None


def get_ffprobe_path() -> Optional[str]:
    """Get ffprobe executable path - checks bundled version first."""
    base_dir = Path(__file__).parent.parent
    
    # Check bundled ffmpeg FIRST (highest priority)
    ffprobe_paths = [
        base_dir / "ffmpeg" / "bin" / "ffprobe.exe",
        base_dir / "ffprobe.exe",
    ]
    
    for path in ffprobe_paths:
        if path.exists():
            logger.debug(f"Found bundled ffprobe: {path}")
            return str(path)
    
    # Check PATH as fallback
    import shutil
    ffprobe_in_path = shutil.which("ffprobe")
    if ffprobe_in_path:
        logger.debug(f"Found ffprobe in PATH: {ffprobe_in_path}")
        return ffprobe_in_path
    
    return None


def get_video_duration_vlc_media_info(url: str, timeout: int = 8) -> Optional[int]:
    """
    Get video duration using VLC's media info (without playing).
    This uses --run-time=0 to just probe the media.
    """
    vlc_path = get_vlc_path()
    if not vlc_path:
        logger.debug("VLC not found")
        return None
    
    try:
        # Use VLC to get media info without actually playing
        # --run-time=0 means exit immediately after probing
        cmd = [
            vlc_path,
            "--intf", "dummy",           # No interface
            "--play-and-exit",           # Exit when done
            "--no-video",                # Don't display video
            "--no-audio",                # Don't play audio
            "--run-time", "0",           # Exit immediately after probing
            "--verbose", "1",            # Get info output
            url,
            "vlc://quit"
        ]
        
        logger.debug(f"Probing with VLC...")
        
        # Set environment to use bundled plugins
        env = os.environ.copy()
        vlc_dir = Path(vlc_path).parent
        plugin_path = vlc_dir / "plugins"
        if plugin_path.exists():
            env["VLC_PLUGIN_PATH"] = str(plugin_path)
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 5,
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        # Parse stderr for duration info (VLC outputs media info there)
        output = result.stderr + result.stdout
        
        # Look for duration in VLC's verbose output
        # VLC outputs: "duration: 13" or "length: 13" 
        patterns = [
            r'duration[:\s]+(\d+)',
            r'length[:\s]+(\d+)',
            r'Duration:\s*(\d+):(\d+):(\d+)',
            r'(\d+):(\d+):(\d+)\.\d+\s+duration',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                if len(match.groups()) == 3:
                    h, m, s = map(int, match.groups())
                    duration = h * 3600 + m * 60 + s
                else:
                    duration = int(match.group(1))
                
                # Sanity check
                if 1 <= duration <= 86400:
                    logger.info(f"Duration detected via VLC probe: {duration}s ({duration//60}m {duration%60}s)")
                    return duration
        
        # Alternative: look for "stream 0" duration
        stream_match = re.search(r'Stream \d+.*?duration[:\s]+(\d+)', output, re.IGNORECASE)
        if stream_match:
            duration = int(stream_match.group(1))
            if 1 <= duration <= 86400:
                logger.info(f"Duration from stream info: {duration}s")
                return duration
        
        logger.debug(f"VLC probe could not find duration")
        
    except subprocess.TimeoutExpired:
        logger.debug(f"VLC probe timeout")
    except Exception as e:
        logger.debug(f"VLC probe error: {e}")
    
    return None


def get_video_duration_ffprobe(url: str, timeout: int = 8) -> Optional[int]:
    """
    Get video duration using ffprobe.
    """
    ffprobe_path = get_ffprobe_path()
    if not ffprobe_path:
        return None
    
    try:
        cmd = [
            ffprobe_path,
            "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "-timeout", str(timeout * 1000000),
            url
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout + 3,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode == 0 and result.stdout.strip():
            try:
                duration = int(float(result.stdout.strip()))
                if 1 <= duration <= 86400:
                    logger.info(f"Duration via ffprobe: {duration}s ({duration//60}m {duration%60}s)")
                    return duration
            except ValueError:
                pass
        
    except Exception as e:
        logger.debug(f"ffprobe error: {e}")
    
    return None


def get_video_duration_from_headers(url: str, timeout: int = 5) -> Optional[int]:
    """
    Try to get video duration from HTTP headers.
    """
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        req.add_header("Referer", "https://hypnotube.com/")
        req.add_header("Origin", "https://hypnotube.com")
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            headers = response.headers
            
            # Check Content-Length and estimate
            if "Content-Length" in headers:
                size_bytes = int(headers["Content-Length"])
                size_mb = size_bytes / (1024 * 1024)
                
                # Estimate based on typical bitrates:
                # - Very small (< 5MB): likely short clip (estimate 5-30 seconds)
                # - Small (5-20MB): short video (30s - 2min)
                # - Medium (20-100MB): standard video (2-10min)
                # - Large (> 100MB): long video (10min+)
                
                if size_mb < 1:
                    estimated = max(3, int(size_mb * 20))  # ~3-20 seconds
                elif size_mb < 5:
                    estimated = int(size_mb * 8)  # ~8-40 seconds
                elif size_mb < 20:
                    estimated = int(size_mb * 5)  # ~25-100 seconds
                elif size_mb < 100:
                    estimated = int(size_mb * 4)  # ~1.5-6.5 minutes
                else:
                    estimated = int(size_mb * 3)  # ~5+ minutes
                
                if 1 <= estimated <= 7200:
                    logger.info(f"Estimated from Content-Length ({size_mb:.1f}MB): ~{estimated}s ({estimated//60}m {estimated%60}s)")
                    return estimated
            
            # Check duration headers
            for header in ["Content-Duration", "X-Content-Duration", "X-Amz-Meta-Duration"]:
                if header in headers:
                    duration = parse_duration_string(headers[header])
                    if duration:
                        logger.info(f"Duration from header '{header}': {duration}s")
                        return duration
                    
    except urllib.error.HTTPError as e:
        # HEAD not allowed, try GET with Range
        if e.code == 405 or e.code == 403:
            return get_duration_from_range_request(url, timeout)
    except Exception as e:
        logger.debug(f"HEAD request error: {e}")
    
    return None


def get_duration_from_range_request(url: str, timeout: int = 5) -> Optional[int]:
    """
    Fallback: Use Range request to get a small chunk and estimate from Content-Range.
    """
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        req.add_header("Referer", "https://hypnotube.com/")
        req.add_header("Range", "bytes=0-0")  # Only request first byte
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            content_range = response.headers.get("Content-Range", "")
            
            # Content-Range: bytes 0-0/12345678
            match = re.search(r'/(\d+)$', content_range)
            if match:
                total_bytes = int(match.group(1))
                size_mb = total_bytes / (1024 * 1024)
                
                # Estimate duration
                if size_mb < 1:
                    estimated = max(3, int(size_mb * 20))
                elif size_mb < 5:
                    estimated = int(size_mb * 8)
                elif size_mb < 20:
                    estimated = int(size_mb * 5)
                else:
                    estimated = int(size_mb * 4)
                
                if 1 <= estimated <= 7200:
                    logger.info(f"Estimated from Content-Range ({size_mb:.1f}MB): ~{estimated}s")
                    return estimated
                    
    except Exception as e:
        logger.debug(f"Range request error: {e}")
    
    return None


def parse_duration_string(duration_str: str) -> Optional[int]:
    """Parse duration string in various formats to seconds."""
    if not duration_str:
        return None
    
    duration_str = str(duration_str).strip()
    
    try:
        seconds = float(duration_str)
        if 1 <= seconds <= 86400:
            return int(seconds)
    except ValueError:
        pass
    
    # Try HH:MM:SS format
    match = re.match(r'(\d+):(\d+):(\d+)', duration_str)
    if match:
        h, m, s = map(int, match.groups())
        return h * 3600 + m * 60 + s
    
    match = re.match(r'(\d+):(\d+)', duration_str)
    if match:
        m, s = map(int, match.groups())
        return m * 60 + s
    
    return None


def estimate_video_duration(url: str) -> Tuple[Optional[int], str]:
    """
    Get video duration with multiple fallback methods.
    
    Returns:
        Tuple of (duration_seconds, source)
        source can be: "detected", "estimated", "unknown"
    """
    logger.debug(f"Getting duration for: {url[:80]}...")
    
    # Method 1: VLC probe (most reliable for token URLs)
    duration = get_video_duration_vlc_media_info(url, timeout=8)
    if duration:
        return duration, "detected"
    
    # Method 2: ffprobe
    duration = get_video_duration_ffprobe(url, timeout=8)
    if duration:
        return duration, "detected"
    
    # Method 3: HTTP headers (Content-Length estimation)
    duration = get_video_duration_from_headers(url, timeout=5)
    if duration:
        return duration, "estimated"
    
    # Method 4: URL pattern matching
    url_lower = url.lower()
    
    # Look for explicit duration in URL
    patterns = [
        (r'[_-](\d+)sec', 1),
        (r'[_-](\d+)s[^a-z]', 1),
        (r'[_-](\d+)min', 60),
        (r'[_-](\d+)m[^a-z]', 60),
        (r'duration[=:](\d+)', 1),
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, url_lower)
        if match:
            value = int(match.group(1))
            estimated = value * multiplier
            if 1 <= estimated <= 7200:
                logger.info(f"Duration from URL pattern: {estimated}s")
                return estimated, "estimated"
    
    # Method 5: Platform-specific defaults (conservative)
    if 'hypnotube.com' in url_lower:
        # Hypnotube videos vary - use a shorter default for safety
        logger.info("Using default Hypnotube estimate: 5m")
        return 300, "estimated"
    elif any(x in url_lower for x in ['redgifs', 'gfycat', 'imgur', 'tenor']):
        logger.info("Short clip platform: 1m")
        return 60, "estimated"
    
    return None, "unknown"


def format_duration(seconds: Optional[int]) -> str:
    """Format duration for display."""
    if seconds is None:
        return "Unknown"
    
    if seconds < 60:
        return f"{seconds}s"
    
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    
    if remaining_seconds == 0:
        return f"{minutes}m"
    
    return f"{minutes}m {remaining_seconds}s"


# For backwards compatibility
def get_video_duration(url: str, timeout: int = 10) -> Optional[int]:
    """Legacy function."""
    duration, _ = estimate_video_duration(url)
    return duration
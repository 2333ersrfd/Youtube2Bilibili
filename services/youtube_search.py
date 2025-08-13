import os
import json
import subprocess
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

"""
Simple YouTube search using yt-dlp (no official API). 
It searches by keyword and returns basic metadata.
Requirements: yt-dlp installed and accessible in PATH.
"""

@dataclass
class YouTubeVideo:
    id: str
    title: str
    url: str
    duration: Optional[int]
    uploader: Optional[str]
    upload_date: Optional[str]
    description: Optional[str]


def search_videos(keyword: str, max_results: int = 5, region: str = "US") -> List[YouTubeVideo]:
    # yt-dlp supports ytsearchN:keyword pattern
    query = f"ytsearch{max_results}:{keyword}"
    if os.path.exists("cookies.txt"):
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--skip-download",
            "--no-warnings",
            "--default-search", "ytsearch",
            "--cookies", "cookies.txt",
            query,
        ]
    else:
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--skip-download",
            "--no-warnings",
            "--default-search", "ytsearch",
            query,
        ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    videos: List[YouTubeVideo] = []
    if proc.returncode != 0:
        return videos
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except Exception:
            continue
        if data.get("_type") == "playlist":
            # When yt-dlp returns a playlist wrapper
            for entry in data.get("entries", []) or []:
                if not entry:
                    continue
                videos.append(_to_model(entry))
        else:
            videos.append(_to_model(data))
    return videos


def _to_model(d: Dict[str, Any]) -> YouTubeVideo:
    return YouTubeVideo(
        id=d.get("id") or "",
        title=d.get("title") or "",
        url=d.get("webpage_url") or (f"https://www.youtube.com/watch?v={d.get('id')}") if d.get("id") else "",
        duration=d.get("duration"),
        uploader=d.get("uploader"),
        upload_date=d.get("upload_date"),
        description=d.get("description"),
    )

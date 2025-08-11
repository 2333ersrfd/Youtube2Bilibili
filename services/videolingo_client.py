import time
import requests
from typing import Optional, Dict, Any

class VideoLingoClient:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip('/')

    def process_url(self, url: str, target_language: str = "简体中文", source_language: Optional[str] = None,
                    enable_dubbing: bool = False, burn_subtitles: bool = True, resolution: str = "1080") -> str:
        payload = {
            "url": url,
            "target_language": target_language,
            "source_language": source_language,
            "enable_dubbing": enable_dubbing,
            "burn_subtitles": burn_subtitles,
            "resolution": resolution,
        }
        r = requests.post(f"{self.base}/api/v1/process-url", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["task_id"]

    def get_status(self, task_id: str) -> Dict[str, Any]:
        r = requests.get(f"{self.base}/api/v1/tasks/{task_id}", timeout=30)
        r.raise_for_status()
        return r.json()

    def wait_until_done(self, task_id: str, poll_sec: int = 10, timeout_sec: int = 36000) -> Dict[str, Any]:
        start = time.time()
        while True:
            s = self.get_status(task_id)
            st = s.get("status")
            if st in ("completed", "failed"):
                return s
            if time.time() - start > timeout_sec:
                raise TimeoutError("Video processing timeout")
            time.sleep(poll_sec)

    def download_file(self, task_id: str, file_type: str, out_path: str) -> str:
        # file_type: video_sub | video_dub | src_srt | trans_srt | dub_audio
        url = f"{self.base}/api/v1/download/{task_id}/{file_type}"
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            f.write(r.content)
        return out_path

    def delete_task(self, task_id: str) -> bool:
        try:
            r = requests.delete(f"{self.base}/api/v1/tasks/{task_id}", timeout=30)
            return r.status_code // 100 == 2
        except Exception:
            return False

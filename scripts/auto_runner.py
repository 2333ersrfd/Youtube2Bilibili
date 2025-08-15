import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import List
from datetime import datetime, timedelta
import time
import requests

# Ensure project root is on sys.path for `services` imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.youtube_search import search_videos
from services.videolingo_client import VideoLingoClient
from services.openai_title_tags import AITitleTagger
from services.bilibili_check import check_duplicate
from services.history_store import load_history_ids, append_history
from services.ai_client import AIClient

CONFIG_PATH = Path("config/settings.json")
title_template = "[中字翻译] {title}"
desc_template = """{title_zh}
-----------------------
本视频由VideoLingo提供字幕。
原视频标题: {title_en}
原视频链接: {video_url}
描述: {desc}
"""

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dirs(cfg):
    for k, p in cfg.get("paths", {}).items():
        Path(p).mkdir(parents=True, exist_ok=True)


def check_tool_available(cmd: str) -> bool:
    try:
        res = subprocess.run([cmd, "--version"], capture_output=True, text=True)
        return res.returncode == 0
    except Exception:
        return False


def wait_task_with_progress(api: VideoLingoClient, task_id: str, poll_sec: int = 3, timeout_sec: int = 36000):
    """轮询任务状态：不显示进度条，仅在 step 变化时打印一行状态。"""
    start = time.time()
    last_step = None
    while True:
        try:
            s = api.get_status(task_id)
        except Exception:
            # 静默网络抖动；稍后重试
            time.sleep(min(10, poll_sec))
            continue

        status = s.get("status")
        prog = s.get("progress")
        step = s.get("current_step") or ""
        msg = s.get("message") or ""
        try:
            if isinstance(prog, (int, float)):
                pct = max(0, min(100, int(prog)))
            else:
                pct = 0
        except Exception:
            pct = 0

        if step != last_step:
            print(f"  [{pct}%] {step} - {msg}")
            last_step = step

        if status in ("completed", "failed"):
            return s

        if time.time() - start > timeout_sec:
            return {"status": "failed", "message": "超时", "progress": pct}

        time.sleep(poll_sec)


def download_cover(youtube_url: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cover.jpg"
    if os.path.exists("cookies.txt"):
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "--cookies", "cookies.txt",
            "-o", str(out_dir / "%(id)s.%(ext)s"),
            youtube_url,
        ]
    else:
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "-o", str(out_dir / "%(.id)s.%(ext)s"),
            youtube_url,
        ]
    subprocess.run(cmd, check=False)
    # pick first jpg
    for f in out_dir.glob("*.jpg"):
        return f
    return out_path  # may not exist


def run_biliup(cover: Path, source: str, title: str, desc: str, tags: List[str], video_path: str):
    # keep tags 2-4 Chinese chars as requested
    filt = []
    for t in tags:
        t = t.strip()
        if 2 <= len(t) <= 4:
            filt.append(t)
    if not filt and tags:
        filt = tags[:6]
    tag_str = ",".join(filt[:12])
    cmd = ["biliup", "upload"]
    if cover and Path(cover).exists():
        cmd += ["--cover", str(cover)]
    cmd += [
        "--source", source,
        "--title", title,
        "--desc", desc,
        "--tag", tag_str,
        video_path,
    ]
    # Note: for Windows PowerShell, pass list to subprocess to avoid quoting 
    print(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def upload_with_retry(cover: Path, source: str, title: str, desc: str, tags: List[str], video_path: str,
                      attempts: int = 3, backoff_sec: int = 20):
    """
    Try uploading with retries. Returns (success: bool, code: int, out: str, err: str).
    """
    wait = max(1, int(backoff_sec))
    for i in range(1, max(1, int(attempts)) + 1):
        code, out, err = run_biliup(cover, source, title, desc, tags, video_path)
        if code == 0:
            return True, code, out, err
        print(f"  Upload attempt {i} failed (code={code}).")
        if i < attempts:
            print(f"  Retrying in {wait}s...")
            time.sleep(wait)
            # exponential-ish backoff with cap
            wait = min(wait * 2, 300)
    return False, code, out, err


def main():
    cfg = load_config()
    ensure_dirs(cfg)

    api = VideoLingoClient(cfg["api_base"])
    ai = AIClient(
        base_url=cfg["openai"]["base_url"],
        api_key=cfg["openai"]["api_key"],
        model=cfg["openai"].get("model", "gpt-4o-mini"),
    )
    tagger = AITitleTagger(base_url=cfg["openai"]["base_url"], api_key=cfg["openai"]["api_key"], model=cfg["openai"].get("model", "gpt-4o-mini"))

    # Tools check
    if not check_tool_available("yt-dlp"):
        print("未检测到 yt-dlp，请先安装：pip install -U yt-dlp")
        return

    # Quick health check for API availability (fallback to /)
    base = cfg["api_base"].rstrip('/')
    ok = False
    try:
        r = requests.get(base + "/health", timeout=5)
        r.raise_for_status()
        ok = True
    except Exception:
        try:
            r2 = requests.get(base + "/", timeout=5)
            if r2.ok and ("VideoLingo" in r2.text or "docs" in r2.text):
                ok = True
        except Exception:
            ok = False
    if not ok:
        print(f"无法连接到 VideoLingo API: {base}，请确认已启动或修改 config/settings.json 的 api_base。")
        return

    keywords = cfg.get("keywords", [])
    if not keywords:
        print("No keywords in config. Add 'keywords' array.")
        return

    max_n = cfg["youtube"].get("max_results_per_keyword", 5)
    min_dur = cfg["youtube"].get("min_duration_sec", 0)
    max_dur = cfg["youtube"].get("max_duration_sec", 1000000)
    blacklist = set([c.lower() for c in cfg["youtube"].get("blacklist_channels", [])])
    days = cfg["youtube"].get("published_after_days", 365)
    cutoff = datetime.utcnow() - timedelta(days=days)
    history_file = cfg.get("history_file", str(Path(cfg["paths"]["workspace"]) / "history.jsonl"))
    processed = load_history_ids(history_file)
    cleanup_remote = cfg.get("cleanup_remote", True)
    upload_attempts = int(cfg.get("upload_retry_attempts", 3))
    upload_backoff = int(cfg.get("upload_retry_backoff_sec", 20))

    for kw in keywords:
        print(f"Searching: {kw}")
        videos = search_videos(kw, max_results=max_n, region=cfg["youtube"].get("search_region", "US"))
        for v in videos:
            print(f"- Candidate: {v.title}")
            # skip processed
            if v.id and v.id in processed:
                print("  Skip (already processed)")
                continue
            # filters
            if v.duration is not None and (v.duration < min_dur or v.duration > max_dur):
                print("  Skip (duration out of range)")
                # record skip into history
                if v.id:
                    append_history(history_file, {
                        "yt_id": v.id,
                        "yt_url": v.url,
                        "status": "skipped",
                        "reason": "duration_out_of_range",
                        "duration": v.duration,
                        "uploaded_at": datetime.utcnow().isoformat(),
                    })
                    processed.add(v.id)
                continue
            if v.uploader and v.uploader.lower() in blacklist:
                print("  Skip (blacklisted channel)")
                if v.id:
                    append_history(history_file, {
                        "yt_id": v.id,
                        "yt_url": v.url,
                        "status": "skipped",
                        "reason": "blacklisted_channel",
                        "channel": v.uploader,
                        "uploaded_at": datetime.utcnow().isoformat(),
                    })
                    processed.add(v.id)
                continue
            if v.upload_date and len(v.upload_date) == 8:
                try:
                    dt = datetime.strptime(v.upload_date, "%Y%m%d")
                    if dt < cutoff:
                        print("  Skip (too old)")
                        if v.id:
                            append_history(history_file, {
                                "yt_id": v.id,
                                "yt_url": v.url,
                                "status": "skipped",
                                "reason": "too_old",
                                "upload_date": v.upload_date,
                                "uploaded_at": datetime.utcnow().isoformat(),
                            })
                            processed.add(v.id)
                        continue
                except Exception:
                    pass
            verdict = check_duplicate(v.title, translator=ai)
            if verdict.get("duplicate"):
                matched = verdict.get("matched") or []
                if matched:
                    print(f"  Skip (duplicate found): {matched[0].get('title','')} -> {matched[0].get('url','')}")
                else:
                    print("  Skip (duplicate found by AI verdict)")
                # record duplicate verdict
                if v.id:
                    rec = {
                        "yt_id": v.id,
                        "yt_url": v.url,
                        "status": "skipped",
                        "reason": "duplicate",
                        "verdict": verdict,
                        "uploaded_at": datetime.utcnow().isoformat(),
                    }
                    append_history(history_file, rec)
                    processed.add(v.id)
                continue

            # call API to process URL
            task_id = api.process_url(
                v.url,
                target_language=cfg.get("target_language", "简体中文"),
                source_language=None,
                enable_dubbing=cfg.get("enable_dubbing", False),
                burn_subtitles=cfg.get("burn_subtitles", True),
                resolution=cfg.get("resolution", "1080"),
            )
            print(f"  Submitted, task={task_id}, waiting...")
            res = wait_task_with_progress(api, task_id)
            if res.get("status") != "completed":
                print("  Task failed, skip.")
                # 清理远端任务
                if cleanup_remote:
                    api.delete_task(task_id)
                continue

            # download chinese subs for naming
            work = Path(cfg["paths"]["uploads_cache"]) / task_id
            work.mkdir(parents=True, exist_ok=True)

            trans_srt = work / "trans.srt"
            api.download_file(task_id, "trans_srt", str(trans_srt))

            # choose dubbed or subtitled video to upload
            out_video = work / ("output_dub.mp4" if cfg.get("enable_dubbing", False) else "output_sub.mp4")
            api.download_file(task_id, "video_dub" if cfg.get("enable_dubbing", False) else "video_sub", str(out_video))

            # read subs small chunk for AI
            cn_sub_text = trans_srt.read_text(encoding="utf-8", errors="ignore")

            # AI title + tags + desc
            pack = tagger.generate(v.title, cn_sub_text)
            title = title_template.format(title=pack.get("title", v.title)[:80])
            tags = pack.get("tags", [])
            desc = desc_template.format(title_zh=title, title_en=v.title, video_url=v.url, desc=pack.get("desc", "")[:2000])

            # cover
            cover_dir = Path(cfg["paths"]["covers"]) / task_id
            cover = download_cover(v.url, cover_dir)
            if not cover.exists():
                print("  Cover not found; proceeding without it may fail.")

            # upload via biliup
            ok, code, out, err = upload_with_retry(cover, v.url, title, desc, tags, str(out_video),
                                                   attempts=upload_attempts, backoff_sec=upload_backoff)
            if ok:
                print("  Uploaded successfully.")
                # record history
                append_history(history_file, {
                    "yt_id": v.id,
                    "yt_url": v.url,
                    "title": title,
                    "tags": tags,
                    "desc": desc,
                    "uploaded_at": datetime.utcnow().isoformat(),
                    "task_id": task_id,
                })
                processed.add(v.id)
            else:
                print("  Upload failed after retries:")
                print(err or out)
                # record failure but do not mark processed so it can be retried in future runs
                if v.id:
                    append_history(history_file, {
                        "yt_id": v.id,
                        "yt_url": v.url,
                        "status": "upload_failed",
                        "reason": err or out,
                        "attempts": upload_attempts,
                        "uploaded_at": datetime.utcnow().isoformat(),
                        "task_id": task_id,
                    })
            # 清理远端任务
            if cleanup_remote:
                api.delete_task(task_id)


if __name__ == "__main__":
    main()

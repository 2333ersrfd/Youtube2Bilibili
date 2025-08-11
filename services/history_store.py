import json
from pathlib import Path
from typing import Set, Dict, Any


def load_history_ids(file_path: str) -> Set[str]:
    p = Path(file_path)
    if not p.exists():
        return set()
    ids: Set[str] = set()
    with p.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                vid = obj.get("yt_id") or obj.get("id")
                if vid:
                    ids.add(str(vid))
            except Exception:
                continue
    return ids


def append_history(file_path: str, record: Dict[str, Any]) -> None:
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

import re
import time
import urllib.parse
import requests
from html import unescape
from lxml import html as lxml_html
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

from .ai_client import AIClient

"""
Simple duplicate check against Bilibili by searching the title on B 站的搜索页。
不依赖官方 API，仅做粗略相似度判断，命中则认为重复。
"""

@dataclass
class BiliSearchResult:
    url: str
    title: str
    uploader: Optional[str]


def similar(a: str, b: str) -> float:
    """Jaccard similarity over token sets.
    - English/number tokens: \\w+
    - Chinese characters treated as single-char tokens
    """
    def tok(s: str):
        # extract ascii words
        words = re.findall(r"[A-Za-z0-9_]+", s)
        # extract CJK chars
        cjk = re.findall(r"[\u4e00-\u9fff]", s)
        return {t.lower() for t in words} | set(cjk)
    A, B = tok(a or ""), tok(b or "")
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def check_duplicate(title: str, translator: Optional[AIClient] = None) -> Dict[str, Any]:
    """
    AI 判重流程：
    1) 先将原标题翻译为中文（若 translator 提供）。
    2) 用 lxml 抓取 B 站搜索页，收集候选 [{title,url}]。
    3) 让 AI 判断是否为重复搬运，返回 JSON：
       {"duplicate": bool, "reason": str, "matched": [{"title":..., "url":...}],
        "zh_title": str, "candidates": [...]}。
    """
    zh_title: Optional[str] = None
    if translator:
        try:
            zh_title = translator.translate_title_to_zh(title)
        except Exception:
            zh_title = None
    query_title = zh_title or title

    candidates: List[Dict[str, str]] = []
    try:
        q = urllib.parse.quote_plus(query_title)
        url = f"https://search.bilibili.com/all?keyword={q}"
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        doc = lxml_html.fromstring(r.text)

        # 找所有标题 h3
        nodes = doc.xpath('//h3[contains(@class, "bili-video-card__info--tit")]')
        for h3 in nodes:
            cand_title = (h3.get('title') or h3.text_content() or '').strip()
            if not cand_title:
                continue
            # 在所在卡片范围内找视频链接
            href = None
            card_a = h3.xpath('ancestor::div[contains(@class, "bili-video-card")][1]//a[starts-with(@href, "//www.bilibili.com/video/")][1]/@href')
            if card_a:
                href = card_a[0]
            else:
                anc_a = h3.xpath('ancestor::a[starts-with(@href, "//www.bilibili.com/video/")][1]/@href')
                if anc_a:
                    href = anc_a[0]
                else:
                    foll_a = h3.xpath('following::a[starts-with(@href, "//www.bilibili.com/video/")][1]/@href')
                    if foll_a:
                        href = foll_a[0]
            full_url = f"https:{href}" if href and href.startswith('//') else (href or '')
            candidates.append({"title": unescape(cand_title), "url": full_url})
    except Exception:
        candidates = []

    result: Dict[str, Any] = {"duplicate": False, "reason": "", "matched": [], "zh_title": query_title, "candidates": candidates}
    if translator:
        try:
            verdict = translator.judge_duplicate(original_title=title, zh_title=query_title, candidates=candidates)
            # 合并 verdict
            result.update({k: v for k, v in verdict.items() if k in ("duplicate", "reason", "matched")})
        except Exception as e:
            result["reason"] = f"AI 判重失败: {e}"
    return result

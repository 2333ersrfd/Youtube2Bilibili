from typing import List, Dict, Optional, cast, Any
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

TITLE_TAGS_PROMPT = """
你是资深的新媒体编辑。根据提供的视频原标题与中文字幕，生成：
1) 一个吸引人的中文标题（限制 20 字内，避免夸张词）。
2) 8-12 个中文标签（每个 2-4 字）。
3) 一段简洁描述（80-150 字），自然口语、避免重复。

返回 JSON：{{"title":"...","tags":[".."],"desc":"..."}}
原标题：{orig}
字幕：\n{subs}
"""


class AIClient:
    def __init__(self, base_url: str, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=cast(List[ChatCompletionMessageParam], messages),
            temperature=temperature,
        )
        content = resp.choices[0].message.content or ""
        return content.strip()

    def chat_json(self, messages: List[Dict[str, str]], temperature: float = 0.5, retries: int = 3) -> Dict[str, Any]:
        """Ask model to return pure JSON and parse it with retry.
        We enforce: only JSON, no markdown fences, no extra text.
        """
        sys_prefix = {
            "role": "system",
            "content": (
                "你必须只输出 JSON，不要任何额外文字、注释或代码块围栏。"
                "若无法满足，请返回一个 JSON 对象包含 {\"error\": \"原因\"}。"
            ),
        }
        msgs: List[Dict[str, str]] = [sys_prefix] + messages
        last_err: Optional[Exception] = None
        for i in range(retries):
            try:
                txt = self.chat(msgs, temperature=temperature)
                data = self._extract_json(txt)
                if isinstance(data, dict):
                    return data
                # 如果解析出的是数组，包一层
                if isinstance(data, list):
                    return {"list": data}
            except Exception as e:
                last_err = e
                # 追加提醒并重试
                msgs.append({
                    "role": "system",
                    "content": "请仅输出 JSON 对象，不要附加说明或 Markdown。",
                })
        if last_err:
            raise last_err
        return {}

    @staticmethod
    def _extract_json(text: str) -> Any:
        import json, re
        # 尝试直接解析
        try:
            return json.loads(text)
        except Exception:
            pass
        # 提取第一个花括号 JSON
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        # 提取数组
        m2 = re.search(r"\[[\s\S]*\]", text)
        if m2:
            return json.loads(m2.group(0))
        raise ValueError("无法从模型输出中解析 JSON")

    def translate_title_to_zh(self, title: str) -> str:
        if not title:
            return title
        data = self.chat_json([
            {"role": "system", "content": "你是专业的中英翻译，擅长视频标题翻译。"},
            {"role": "user", "content": "把以下标题翻译成简体中文，保持专有名词原样或常见译名，简洁自然。\n输出 JSON：{\"zh\": \"中文标题\"}.\n"+title},
        ], temperature=0.3)
        return cast(str, data.get("zh", ""))

    def generate_title_tags(self, original_title: str, cn_subs: str) -> Dict:
        prompt = TITLE_TAGS_PROMPT.format(orig=original_title, subs=cn_subs[:6000])
        data = self.chat_json([
            {"role": "system", "content": "你是精通 B 站风格的中文新媒体编辑。"},
            {"role": "user", "content": prompt + "\n仅输出 JSON 对象，字段为 title/tags/desc。"},
        ], temperature=0.7)
        return data

    def judge_duplicate(self, original_title: str, zh_title: str, candidates: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Ask AI to determine if candidates contain reuploads of the video by title.
        Return JSON: {"duplicate": bool, "reason": str, "matched": [{"title":..., "url":...}]}
        """
        import json
        msg = (
            "请根据原标题(可能为英文)与其中文译文，判断候选列表中是否存在相同或高度相似/同源的搬运。"
            "考虑缩写、序号、机翻差异、标点与空格、B站常见风格化等。"
            "输出 JSON：{\"duplicate\":true|false,\"reason\":\"...\",\"matched\":[{\"title\":\"...\",\"url\":\"...\"}]}"
        )
        data = self.chat_json([
            {"role": "system", "content": "你是内容审核与文本比对专家。"},
            {"role": "user", "content": msg + f"\n原标题: {original_title}\n中文译: {zh_title}\n候选列表(JSON 数组)：\n" + json.dumps(candidates, ensure_ascii=False)},
        ], temperature=0.2)
        # 兜底字段
        if "duplicate" not in data:
            data["duplicate"] = False
        if "matched" not in data:
            data["matched"] = []
        if "reason" not in data:
            data["reason"] = ""
        return data

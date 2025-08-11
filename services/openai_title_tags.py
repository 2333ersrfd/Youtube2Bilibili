from typing import Dict
from .ai_client import AIClient


class AITitleTagger:
    def __init__(self, base_url: str, api_key: str, model: str = "gpt-4o-mini"):
        self.client = AIClient(base_url=base_url, api_key=api_key, model=model)

    def generate(self, original_title: str, cn_subs: str) -> Dict:
        return self.client.generate_title_tags(original_title, cn_subs)

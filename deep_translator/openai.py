__copyright__ = [
    "Copyright (C) 2020 Nidhal Baccouri",
    "Copyright (C) 2026 Alan Lee",
]

import logging
from openai import OpenAI
from pathlib import Path
from typing import List, Optional

from deep_translator.base import BaseTranslator, Language
from deep_translator.google import GoogleTranslator
from deep_translator.constants import BASE_URLS, GOOGLE_LANGUAGES_TO_CODES
from deep_translator.exceptions import (
    RequestError,
    TooManyRequests,
    TranslationNotFound,
)
from deep_translator.validate import is_empty, is_input_valid, request_failed

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
"""You are a professional translator specializing in {engine_name} games.
Translate to {target_lang}. Respond only with the translated text. 
Preserve any formatting, special characters, and placeholders in the original text."""
)
TRANSLATION_PROMPT_TEMPLATE = """
Source Text: {text}
Translated Text:
"""
OPENAI_URL = "https://api.openai.com/v1"
OPENROUTER_URL = "https://openrouter.ai/api/v1"

class OpenAITranslator(BaseTranslator):
    """
    class that wraps functions, which use OpenAI's API under the hood to translate text(s)
    """
    
    def __init__(
        self,
        model: str = "openrouter/free",
        base_url: str = OPENROUTER_URL,
        source: str = "auto",
        target: str = "en",
        api_key: Optional[str] = None,
        **kwargs
    ):
        """
        @param source: source language to translate from
        @param target: target language to translate to
        """
        super().__init__(
            base_url=BASE_URLS.get("OPENAI_TRANSLATE"),
            source=source,
            target=target,
            element_tag="div",
            element_query={"class": "t0"},
            payload_key="q",  # key of text in the url
            **kwargs
        )
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        
    def _fetch_supported_languages(self) -> dict[str, Language]:
        # Use GoogleTranslator's method for supported languages
        return GoogleTranslator._fetch_supported_languages()
    
    def translate(self, text:str, **kwargs)-> Optional[str]:
        target_lang = self._languages.get(self._target, self._target)
        system_prompt = SYSTEM_PROMPT.format(engine_name=self.model, target_lang=target_lang)
        main_prompt = TRANSLATION_PROMPT_TEMPLATE.format(text=text)
        model = self.model
        if "model" in kwargs:
            logger.warning("Overriding the model specified in the translator initialization is not recommended as it may lead to unexpected behavior. Proceed with caution.")
            model = kwargs.pop("model")
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": main_prompt}
            ],
            **kwargs
        )
        if (content := response.choices[0].message.content) is not None:
            return content.strip()
        
        
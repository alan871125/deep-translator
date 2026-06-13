"""
google translator API
"""

__copyright__ = [
    "Copyright (C) 2020 Nidhal Baccouri",
    "Copyright (C) 2026 Alan Lee",
]

import re
import json
import logging
import requests
from pathlib import Path
from typing import List, Optional
from bs4 import BeautifulSoup

from deep_translator.base import BaseTranslator, Language, SupportedLanguages
from deep_translator.constants import BASE_URLS, GOOGLE_LANGUAGES_TO_CODES
from deep_translator.exceptions import (
    RequestError,
    TooManyRequests,
    TranslationNotFound,
)
from deep_translator.validate import is_empty, is_input_valid, request_failed

logger = logging.getLogger(__name__)

class GoogleTranslator(BaseTranslator):
    """
    class that wraps functions, which use Google Translate under the hood to translate text(s)
    """
    save_cache = True  # whether to save the fetched supported languages in a local cache file to avoid making repeated requests to Google for the same data, improving performance and reducing network load.
    def __init__(
        self,
        source: str = "auto",
        target: str = "en",
        proxies: Optional[dict] = None,
        **kwargs
    ):
        """
        @param source: source language to translate from
        @param target: target language to translate to
        """
        self.proxies = proxies
        super().__init__(
            base_url=BASE_URLS.get("GOOGLE_TRANSLATE"),
            source=source,
            target=target,
            element_tag="div",
            element_query={"class": "t0"},
            payload_key="q",  # key of text in the url
            **kwargs
        )

        self._alt_element_query = {"class": "result-container"}
    
    @classmethod
    def _fetch_supported_languages(cls, lang: str='en') -> SupportedLanguages:
        """
        Fetch supported languages from the translator's API
        
        @param lang: language to get the names of the supported languages in
        @return: dict mapping language names to their codes
        """
        if hasattr(cls, "languages_cache") and cls.languages_cache is not None:
            return cls.languages_cache
        url = f"https://translate.google.com/?hl={lang}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(url, headers=headers)
        html = response.text
        # save cache to a read/write safe location in the user's home directory
        cache_file = Path.home() / ".cache" / "deep_translator" / f"google_{lang}.json"

        # Search for the AF_initDataCallback containing the language list (ds:3)
        # The pattern looks for the key 'ds:3' and grabs the data array following it
        pattern = r"AF_initDataCallback\({key: 'ds:3'.*?data:(.*?), sideChannel: {}}\);"
        if (match := re.search(pattern, html, re.DOTALL)) is not None:
            data_str = match.group(1)
            try:
                data = json.loads(data_str) 
                code2lang = {d[0]: d[1] for d in data[0]} # d[0],d[1]: code, name
                if cls.save_cache:
                    logger.debug(f"Caching supported languages to {cache_file}")
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_file, "w", encoding="utf-8") as f:
                        json.dump({c: l for c, l in code2lang.items()}, f, ensure_ascii=False, indent=4)
            except Exception as e:
                raise RequestError(f"Failed to parse supported languages: {e}")
        # try loading from local cache file
        elif cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                code2lang = json.load(f)
        else:
            logger.warning("Failed to fetch supported languages from API nor caching from local. Falling back to default language list.")
            code2lang = GOOGLE_LANGUAGES_TO_CODES.copy()
        cls.languages_cache = SupportedLanguages.from_code2lang(code2lang)
        return cls.languages_cache

    def translate(self, text: str, **kwargs) -> Optional[str]:
        """
        function to translate a text
        @param text: desired text to translate
        @return: str: translated text
        """
        if is_input_valid(text, max_chars=5000):
            text = text.strip()
            if self._same_source_target() or is_empty(text):
                return text
            self._url_params["tl"] = self._target
            self._url_params["sl"] = self._source

            if self.payload_key:
                self._url_params[self.payload_key] = text

            response = requests.get(
                self.base_url, params=self._url_params, proxies=self.proxies
            )
            if response.status_code == 429:
                raise TooManyRequests()

            if request_failed(status_code=response.status_code):
                raise RequestError()

            soup = BeautifulSoup(response.text, "html.parser")

            element = soup.find(self._element_tag, self._element_query)
            response.close()

            if not element:
                element = soup.find(self._element_tag, self._alt_element_query)
                if not element:
                    raise TranslationNotFound(text)
            if element.get_text(strip=True) == text.strip():
                to_translate_alpha = "".join(
                    ch for ch in text.strip() if ch.isalnum()
                )
                translated_alpha = "".join(
                    ch for ch in element.get_text(strip=True) if ch.isalnum()
                )
                if (
                    to_translate_alpha
                    and translated_alpha
                    and to_translate_alpha == translated_alpha
                ):
                    self._url_params["tl"] = self._target
                    if "hl" not in self._url_params:
                        return text.strip()
                    del self._url_params["hl"]
                    return self.translate(text)

            else:
                return element.get_text(strip=True)

    def translate_file(self, path: str, **kwargs) -> str:
        """
        translate directly from file
        @param path: path to the target file
        @type path: str
        @param kwargs: additional args
        @return: str
        """
        return self._translate_file(path, **kwargs)

    def translate_batch(self, batch: List[str], **kwargs) -> List[str]:
        """
        translate a list of texts
        @param batch: list of texts you want to translate
        @return: list of translations
        """
        return self._translate_batch(batch, **kwargs)

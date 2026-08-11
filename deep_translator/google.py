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
import time
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

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

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


    def translate(
        self, text: str, max_retries: int = 2, **kwargs
    ) -> Optional[str]:
        """Translates text using web extraction with retry safety against bot detection."""
        if not is_input_valid(text, max_chars=5000):
            return None

        cleaned_text = text.strip()
        if self._same_source_target() or is_empty(cleaned_text):
            return cleaned_text

        # Build local params copy to prevent mutating class state across calls
        params = dict(self._url_params)
        params["tl"] = self._target
        params["sl"] = self._source
        if self.payload_key:
            params[self.payload_key] = cleaned_text

        # Merge headers to avoid sending default 'python-requests' User-Agent
        headers = getattr(self, "headers", DEFAULT_HEADERS)

        for attempt in range(max_retries + 1):
            try:
                with requests.get(
                    self.base_url,
                    params=params,
                    headers=headers,
                    proxies=self.proxies,
                    timeout=10,  # Always set timeouts to avoid hanging requests
                ) as response:

                    if response.status_code == 429:
                        raise TooManyRequests("Rate limited by host.")

                    if request_failed(status_code=response.status_code):
                        raise RequestError(f"HTTP Error: {response.status_code}")

                    soup = BeautifulSoup(response.text, "html.parser")

                    # Target search
                    element = soup.find(
                        self._element_tag, self._element_query
                    ) or soup.find(self._element_tag, self._alt_element_query)

                    if not element:
                        raise TranslationNotFound(cleaned_text)

                    result_text = element.get_text(strip=True)

                    # Check if output strictly matches input (untranslated)
                    if result_text == cleaned_text:
                        to_translate_alpha = "".join(
                            ch for ch in cleaned_text if ch.isalnum()
                        )
                        translated_alpha = "".join(
                            ch for ch in result_text if ch.isalnum()
                        )

                        if (
                            to_translate_alpha
                            and to_translate_alpha == translated_alpha
                        ):
                            # Retry strategy without recursion or state pollution
                            if "hl" in params:
                                del params["hl"]
                                time.sleep(1)  # Brief backoff before retry
                                continue

                    return result_text

            except (requests.RequestException, RequestError):
                if attempt == max_retries:
                    raise
                time.sleep(2**attempt)  # Exponential backoff

        return None

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

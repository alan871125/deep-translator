__copyright__ = [
    "Copyright (C) 2020 Nidhal Baccouri",
    "Copyright (C) 2026 Alan Lee",
]

import json
import os
import requests
import logging
from typing import List, Optional
from pathlib import Path

from deep_translator.base import BaseTranslator, Language, SupportedLanguages
from deep_translator.constants import (
    BASE_URLS,
    DEEPL_ENV_VAR,
    DEEPL_LANGUAGE_TO_CODE,
)
from deep_translator.exceptions import (
    ApiKeyException,
    AuthorizationException,
    ServerException,
    TranslationNotFound,
)
from deep_translator.validate import is_empty, is_input_valid, request_failed

logger = logging.getLogger(__name__)

class DeeplTranslator(BaseTranslator):
    """
    class that wraps functions, which use the DeeplTranslator translator
    under the hood to translate word(s)
    """
    save_cache = True  # whether to save the fetched supported languages in a local cache file to avoid making repeated requests to DeepL for the same data, improving performance and reducing network load.
    def __init__(
        self,
        source: str = "de",
        target: str = "en",
        api_key: Optional[str] = os.getenv(DEEPL_ENV_VAR, None),
        **kwargs
    ):
        """
        @param api_key: your DeeplTranslator api key.
        Get one here: https://www.deepl.com/docs-api/accessing-the-api/
        @param source: source language
        @param target: target language
        """
        if not api_key:
            raise ApiKeyException(env_var=DEEPL_ENV_VAR)

        self.version = "v3"
        self.api_key = api_key
        url = (
            BASE_URLS.get("DEEPL_FREE", "").format(version=self.version)
            if self.is_free_api(self.api_key)
            else BASE_URLS.get("DEEPL", "").format(version=self.version)
        )
        super().__init__(
            base_url=url,
            source=source,
            target=target,
            # languages=DEEPL_LANGUAGE_TO_CODE,
            **kwargs
        )
    
    def _fetch_supported_languages(self) -> SupportedLanguages:
        """ Fetch supported languages directly from the DeepL API.
        @return: dict mapping language names to their codes
        """
        # TODO: Suppose that this method should be changed to a class method, load API_KEY from env
        def object_hook(obj):
            """Custom object hook for JSON deserialization to convert language dicts into Language objects."""
            if "lang" in obj and "name" in obj:
                return obj["lang"], Language(code=obj["lang"], name=obj["name"], is_source=obj.get('usable_as_source', True), is_target=obj.get('usable_as_target', True))
            return obj
        if hasattr(self, "languages_cache") and self.languages_cache is not None:
            return self.languages_cache
        cache_file = cache_file = Path.home() / ".cache" / "deep_translator" / f"deepl.json"
        headers = {"Authorization": f"DeepL-Auth-Key {self.api_key}"}
        params = {"resource": "translate_text"}
        response = requests.get(
            f"{self._base_url}/languages", headers=headers, params=params
        )
        if request_failed(response.status_code):
            # If the request failed, try to load from cache if enabled, otherwise fallback to default language list.
            if cache_file.exists():
                with open(cache_file, "r") as f:
                    code2lang = dict(json.load(f, object_hook=object_hook))
            else:
                logger.warning("Failed to fetch supported languages from API nor caching from local. Falling back to default language list.")
                return super()._fetch_supported_languages() 
        elif self.save_cache:
            logger.debug(f"Caching supported languages to {cache_file}")
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(response.json(), f, ensure_ascii=False, indent=4)
                code2lang = dict(json.loads(response.text, object_hook=object_hook))
        else:
            logger.warning("Failed to fetch supported languages from API nor caching from local. Falling back to default language list.")
            code2lang = {code: Language(code, name) for name, code in DEEPL_LANGUAGE_TO_CODE.items()}
        code2lang.update({'auto': Language('auto', 'Auto', is_source=True, is_target=False)}) # force add 'auto' to the supported languages list since DeepL auto detects source language if not specified.
        self.__class__.languages_cache = SupportedLanguages.from_code2lang(code2lang)
        return self.__class__.languages_cache

    def is_free_api(self, api_key):
        return api_key.endswith(":fx")

    def translate(self, text: str, **kwargs) -> Optional[str]:
        """
        @param text: text to translate
        @return: translated text
        """
        if is_input_valid(text):
            if self._same_source_target() or is_empty(text):
                return text

            # Create the request parameters.
            translate_endpoint = "translate"
            headers = {
                "Authorization": f"DeepL-Auth-Key {self.api_key}",
            }
            data = {
                "target_lang": self._target,
                "text": text,
            }
            if self._source != "auto": # DeepL auto detects source language if not specified.
                data["source_lang"] = self._source
            # Do the request and check the connection.
            try:
                response = requests.post(
                    (self._base_url or "") + translate_endpoint, headers=headers, data=data
                )
            except ConnectionError:
                raise ServerException(503)
            # If the answer is not success, raise server exception.
            if response.status_code == 403:
                raise AuthorizationException(self.api_key)
            if request_failed(status_code=response.status_code):
                raise ServerException(response.status_code)
            # Get the response and check is not empty.
            res = response.json()
            if not res:
                raise TranslationNotFound(text)
            # Process and return the response.
            return res["translations"][0]["text"]

    def translate_file(self, path: str, **kwargs) -> str:
        return self._translate_file(path, **kwargs)

    def translate_batch(self, batch: List[str], **kwargs) -> List[str]:
        """
        @param batch: list of texts to translate
        @return: list of translations
        """
        return self._translate_batch(batch, **kwargs)


if __name__ == "__main__":
    d = DeeplTranslator(target="en", api_key="some-key")
    t = d.translate("Ich habe keine ahnung")
    print("text: ", t)

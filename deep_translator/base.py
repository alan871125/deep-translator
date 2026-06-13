"""base translator class"""

__copyright__ = "Copyright (C) 2020 Nidhal Baccouri"

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generator, List, Optional, Union

from deep_translator.constants import GOOGLE_LANGUAGES_TO_CODES
from deep_translator.exceptions import (
    InvalidSourceOrTargetLanguage,
    LanguageNotSupportedException,
)

class Language(str):
    """A helper class to represent a language with both its name and code,
    allowing for more user-friendly display of language names while still keeping track of the underlying language code.
    Backwards compatible with str, so it can be used wherever a string is expected.
    """
    code: str
    is_source: bool = True
    is_target: bool = True
    def __new__(cls, code:str, name:str, is_source: Optional[bool] = None, is_target: Optional[bool] = None):
        """Create a new instance of Language with the given code and name.
        
        @param code: the language code (abbreviation)
        @param name: the full name of the language
        @param is_source: whether the language is supported as a source language
        @param is_target: whether the language is supported as a target language
        """
        if name.lower() == "auto" or code.lower() == "auto":
            is_source, is_target = True, False
        instance = super().__new__(cls, name)
        instance.code = code
        instance.is_source = is_source if is_source is not None else cls.is_source
        instance.is_target = is_target if is_target is not None else cls.is_target
        return instance
    
class SupportedLanguages:
    lang2code: dict[str, str]
    code2lang: dict[str, Language]
    def __init__(self):
        self.lang2code = {}
        self.code2lang = {}
    @classmethod
    def from_lang2code(cls, lang2code: dict[str|Language, str]):
        """Create a LanguageSupportMenu instance from a mapping of language names to codes.
        
        @param lang2code: a dictionary mapping language names to their corresponding codes
        """
        instance = cls()
        for name, code in lang2code.items():
            if isinstance(name, Language):
                lang = name
            else:
                lang = Language(code, name)
            instance.lang2code[name] = code
            instance.code2lang[code] = lang
        return instance
    
    @classmethod
    def from_code2lang(cls, code2lang: dict[str, str|Language]):
        """Create a LanguageSupportMenu instance from a mapping of language codes to names.
        
        @param code2lang: a dictionary mapping language codes to their corresponding names
        """
        instance = cls()
        for code, name in code2lang.items():
            if isinstance(name, Language):
                lang = name
            else:
                lang = Language(code, name)
            instance.lang2code[name] = code
            instance.code2lang[code] = lang
        return instance
    
    def map_language_to_code(self, *languages: str|Language)-> Generator[str]:
        """Map a language name to its corresponding code.
        
        @param language: the name of the language to map
        @return: the corresponding language code
        """
        for lang in languages:
            if lang in self.lang2code:   # O(1) 
                yield self.lang2code[lang]
            elif lang in self.code2lang: # O(1) 
                yield lang
            else:
                raise LanguageNotSupportedException(
                    lang,
                    message=f"No support for the provided language.\n"
                    f"Please select one of the supported languages:\n"
                    f"{self.lang2code}",
                )
    @property
    def target_supported_languages(self) -> set[Language]:
        """Return a list of supported target languages."""
        return {lang for lang in self.code2lang.values() if lang.is_target}
    @property
    def source_supported_languages(self) -> set[Language]:
        """Return a list of supported source languages."""
        return {lang for lang in self.code2lang.values() if lang.is_source}
    @property
    def supported_languages(self) -> set[Language]:
        """Return a list of all supported languages."""
        return set(self.code2lang.values())

class BaseTranslator(ABC):
    """
    Abstract class that serve as a base translator for other different translators
    """
    languages_cache: SupportedLanguages  # class-level cache for supported languages of each translator subclass
    def __init__(
        self,
        base_url: Optional[str] = None,
        languages: Optional[dict] = None,
        source: str = "auto",
        target: str = "en",
        payload_key: Optional[str] = None,
        element_tag: Optional[str] = None,
        element_query: Optional[dict] = None,
        **url_params,
    ):
        """
        @param source: source language to translate from
        @param target: target language to translate to
        """
        self._base_url = base_url
        if languages is not None:
            self._supported_languages = SupportedLanguages.from_lang2code(languages)
        else:
            self._supported_languages = self._fetch_supported_languages()
        if not source:
            raise InvalidSourceOrTargetLanguage(source)
        if not target:
            raise InvalidSourceOrTargetLanguage(target)

        self._source, self._target = self._map_language_to_code(source, target)
        self._url_params = url_params
        self._element_tag = element_tag
        self._element_query = element_query
        self.payload_key = payload_key
        super().__init__()

    @property
    def source(self):
        return self._source

    @source.setter
    def source(self, lang):
        self._source = lang

    @property
    def target(self):
        return self._target

    @target.setter
    def target(self, lang):
        self._target = lang
        
    @property
    def base_url(self)-> str:
        assert self._base_url is not None, "Base URL is not set."
        return self._base_url

    @base_url.setter
    def base_url(self, url: str):
        self._base_url = url
        
    def _type(self):
        return self.__class__.__name__
    @property
    def _lang2code(self):
        return self._supported_languages.lang2code
    @property
    def _code2lang(self):
        return self._supported_languages.code2lang
    @property
    def target_supported_languages(self) -> set[Language]:
        """Return a list of supported target languages."""
        return self._supported_languages.target_supported_languages
    @property
    def source_supported_languages(self) -> set[Language]:
        """Return a list of supported source languages."""
        return self._supported_languages.source_supported_languages
    @property
    def supported_languages(self) -> set[Language]:
        """Return a list of all supported languages."""
        return self._supported_languages.supported_languages
    def _map_language_to_code(self, *languages):
        """
        map language to its corresponding code (abbreviation) if the language was passed
        by its full name by the user
        @param languages: list of languages
        @return: mapped value of the language or raise an exception if the language is
        not supported
        """
        return self._supported_languages.map_language_to_code(*languages)

    def _same_source_target(self) -> bool:
        return self._source == self._target

    def get_supported_languages(
        self, as_dict: bool = False, **kwargs
    ) -> Union[list, dict]:
        """
        return the supported languages by the Google translator
        @param as_dict: if True, the languages will be returned as a dictionary
        mapping languages to their abbreviations
        @return: list or dict
        """
        return self._lang2code if as_dict else list(self._lang2code.keys())

    def is_language_supported(self, language: str, **kwargs) -> bool:
        """
        check if the language is supported by the translator
        @param language: a string for 1 language
        @return: bool or raise an Exception
        """
        if (
            language == "auto"
            or language in self._lang2code.keys()
            or language in self._lang2code.values()
        ):
            return True
        else:
            return False
    @classmethod
    def _fetch_supported_languages(cls, *args, **kwargs) -> SupportedLanguages:
        """ Fetch supported languages from the translator's API, 
        Use Google's supported languages as a fallback if the translator does not provide an API for fetching supported languages.
        @return: dict mapping language names to their codes
        """
        if hasattr(cls, "languages_cache") and cls.languages_cache is not None:
            return cls.languages_cache
        cls._languages_cache = SupportedLanguages.from_lang2code(GOOGLE_LANGUAGES_TO_CODES)
        return cls._languages_cache

    @abstractmethod
    def translate(self, text: str, **kwargs) -> str:
        """
        translate a text using a translator under the hood and return
        the translated text
        @param text: text to translate
        @param kwargs: additional arguments
        @return: str
        """
        return NotImplemented("You need to implement the translate method!")

    def _read_docx(self, f: str):
        import docx2txt

        return docx2txt.process(f)

    def _read_pdf(self, f: str):
        import pypdf

        reader = pypdf.PdfReader(f)
        page = reader.pages[0]
        return page.extract_text()

    def _translate_file(self, path: str|Path, **kwargs) -> str:
        """
        translate directly from file
        @param path: path to the target file
        @type path: str or Path
        @param kwargs: additional args
        @return: str
        """
        path = Path(path)

        if not path.exists():
            print("Path to the file is wrong!")
            exit(1)

        ext = path.suffix

        if ext == ".docx":
            text = self._read_docx(f=str(path))

        elif ext == ".pdf":
            text = self._read_pdf(f=str(path))
        else:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read().strip()

        return self.translate(text)

    def _translate_batch(self, batch: List[str], **kwargs) -> List[str]:
        """
        translate a list of texts
        @param batch: list of texts you want to translate
        @return: list of translations
        """
        if not batch:
            raise Exception("Enter your text list that you want to translate")
        arr = []
        for i, text in enumerate(batch):
            translated = self.translate(text, **kwargs)
            arr.append(translated)
        return arr

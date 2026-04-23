"""
Динамическая система локализации EduAI.
Языковые файлы хранятся в locale/*.json (по одному на язык).
Поддерживает горячую перезагрузку — изменения файлов подхватываются без перезапуска.
"""
import json
import logging
import os
import threading

from django.conf import settings

logger = logging.getLogger('core')

_LOCALE_DIR = os.path.join(settings.BASE_DIR, 'locale')
_cache = {}          # lang -> {key: value}
_mtimes = {}         # lang -> last mtime
_lock = threading.Lock()


def _locale_path(lang):
    return os.path.join(_LOCALE_DIR, f'{lang}.json')


def _load_lang(lang):
    """Load or reload a language file if changed on disk."""
    path = _locale_path(lang)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return _cache.get(lang, {})
    if lang in _cache and _mtimes.get(lang) == mtime:
        return _cache[lang]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with _lock:
            _cache[lang] = data
            _mtimes[lang] = mtime
        logger.debug('Locale loaded: %s (%d keys)', lang, len(data))
        return data
    except Exception as e:
        logger.error('Failed to load locale %s: %s', lang, e)
        return _cache.get(lang, {})


def get_translations(lang='ru'):
    """Return flat dict of translations for the given language.
    Falls back to Russian for missing keys."""
    if lang not in available_languages():
        lang = 'ru'
    data = _load_lang(lang)
    if lang != 'ru':
        ru = _load_lang('ru')
        merged = dict(ru)
        merged.update(data)
        return merged
    return dict(data)


def available_languages():
    """Return list of available language codes based on locale/*.json files."""
    try:
        return sorted(
            f[:-5] for f in os.listdir(_LOCALE_DIR)
            if f.endswith('.json') and not f.startswith('.')
        )
    except OSError:
        return ['ru']


def get_language_name(lang):
    """Return human-readable name for a language code."""
    names = {'ru': 'Русский', 'kk': 'Қазақша', 'en': 'English',
             'de': 'Deutsch', 'fr': 'Français', 'es': 'Español',
             'tr': 'Türkçe', 'zh': '中文', 'ja': '日本語', 'ko': '한국어'}
    return names.get(lang, lang.upper())


def get_all_translations(lang):
    """Return all translations for a language (for admin editor)."""
    return _load_lang(lang)


def save_translations(lang, data):
    """Save translations dict to locale file."""
    path = _locale_path(lang)
    os.makedirs(_LOCALE_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with _lock:
        _cache.pop(lang, None)
        _mtimes.pop(lang, None)
    logger.info('Locale saved: %s (%d keys)', lang, len(data))


def update_translation(lang, key, value):
    """Update a single translation key."""
    data = dict(_load_lang(lang))
    data[key] = value
    save_translations(lang, data)

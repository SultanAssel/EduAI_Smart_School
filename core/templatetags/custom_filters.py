from django import template
import builtins

register = template.Library()


@register.filter
def to_chr(value):
    """Converts a number to an ASCII character (65 = A, 66 = B, etc.)"""
    try:
        return builtins.chr(int(value))
    except (ValueError, TypeError):
        return value


@register.filter
def get_item(dictionary, key):
    """Get a value from dict by key."""
    if dictionary is None:
        return None
    return dictionary.get(key)


@register.filter
def get_lang(obj, lang):
    """Get value by language key (ru/en) from dict."""
    if isinstance(obj, dict):
        return obj.get(lang, obj.get('en', obj.get('ru', '')))
    return obj


@register.filter
def localized_name(obj, lang):
    """Return localized name (works for Subject, FaqCategory, etc.)."""
    if obj is None:
        return ''
    if hasattr(obj, 'get_name'):
        return obj.get_name(lang)
    return getattr(obj, 'name', str(obj))


@register.filter
def localized_question(obj, lang):
    """Return localized FAQ question."""
    if obj is None:
        return ''
    if hasattr(obj, 'get_question'):
        return obj.get_question(lang)
    return getattr(obj, 'question', str(obj))


@register.filter
def localized_answer(obj, lang):
    """Return localized FAQ answer."""
    if obj is None:
        return ''
    if hasattr(obj, 'get_answer'):
        return obj.get_answer(lang)
    return getattr(obj, 'answer', str(obj))

"""
Контекстные процессоры EduAI.
Внедряют переводы (t) и настройки доступности (acc) во все шаблоны.
"""
from .translations import get_translations
from .models import EduUser, AccessibilityProfile


def eduai_context(request):
    """Глобальный context processor: переводы + доступность.

    Accessibility data is cached in session to avoid a DB query on every request.
    The cache is refreshed when the user updates their profile (session key: _acc_cache).
    """
    lang = request.session.get('language', 'ru')
    ctx = {
        't': get_translations(lang),
        'current_lang': lang,
    }

    uid = request.session.get('user_id')
    if uid:
        # Try session-cached accessibility first
        acc_cache = request.session.get('_acc_cache')
        if acc_cache is not None:
            ctx.update(acc_cache)
        else:
            # First request or cache cleared — load from DB and cache
            try:
                user = EduUser.objects.get(id=uid, is_active=True)
                try:
                    acc = user.accessibility
                except AccessibilityProfile.DoesNotExist:
                    acc = None
                acc_data = {}
                if acc:
                    acc_data = {
                        'acc_font_size': acc.font_size,
                        'acc_font_family': acc.font_family,
                        'acc_high_contrast': acc.high_contrast,
                        'acc_easy_read': acc.easy_read,
                        'acc_visual_aids': acc.visual_aids,
                        'acc_tts': acc.text_to_speech,
                        'acc_need': acc.primary_need,
                        'acc_zen': acc.zen_mode,
                        'acc_voice_input': acc.voice_input,
                    }
                request.session['_acc_cache'] = acc_data
                ctx.update(acc_data)
            except EduUser.DoesNotExist:
                request.session['_acc_cache'] = {}

    return ctx

"""
Представления (views) EduAI — страницы, авторизация, API.
"""
import io
import hashlib
import json
import logging
import os
import re
import secrets
import uuid as _uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Avg
from django.utils import timezone
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import ai
from .translations import get_translations
from .models import (
    EduUser, AccessibilityProfile, Subject, Lesson,
    Test, TestQuestion, TestAttempt, StudentAnswer,
    Essay, ClassReport, LearningProfile,
    ChatMessage, ContactMessage, FaqCategory,
    Assignment, AssignmentSubmission, SubmissionFile,
    Organization, OrganizationKey,
)

logger = logging.getLogger('core')

# Allowed file extensions for uploads (documents, images)
ALLOWED_UPLOAD_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.odt', '.ods', '.odp', '.txt', '.rtf', '.csv',
    '.png', '.jpg', '.jpeg', '.gif', '.webp',
    '.zip', '.rar', '.7z',
}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB

_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

# Expected MIME prefixes per extension (used with python-magic)
_EXT_MIME_MAP = {
    '.pdf':  ['application/pdf'],
    '.doc':  ['application/msword', 'application/x-ole-storage', 'application/CDFV2'],
    '.docx': ['application/zip', 'application/vnd.openxmlformats', 'application/octet-stream'],
    '.xls':  ['application/vnd.ms-excel', 'application/x-ole-storage', 'application/CDFV2'],
    '.xlsx': ['application/zip', 'application/vnd.openxmlformats', 'application/octet-stream'],
    '.ppt':  ['application/vnd.ms-powerpoint', 'application/x-ole-storage', 'application/CDFV2'],
    '.pptx': ['application/zip', 'application/vnd.openxmlformats', 'application/octet-stream'],
    '.odt':  ['application/zip', 'application/vnd.oasis'],
    '.ods':  ['application/zip', 'application/vnd.oasis'],
    '.odp':  ['application/zip', 'application/vnd.oasis'],
    '.txt':  ['text/'],
    '.csv':  ['text/'],
    '.rtf':  ['text/rtf', 'application/rtf'],
    '.png':  ['image/png'],
    '.jpg':  ['image/jpeg'],
    '.jpeg': ['image/jpeg'],
    '.gif':  ['image/gif'],
    '.webp': ['image/webp'],
    '.zip':  ['application/zip'],
    '.rar':  ['application/x-rar'],
    '.7z':   ['application/x-7z'],
}


def _validate_upload(uploaded_file):
    """Validate file: size, extension, MIME type (via python-magic), and image integrity (via Pillow)."""
    if not uploaded_file:
        return None
    if uploaded_file.size > MAX_UPLOAD_SIZE:
        return 'File too large (max 20MB)'
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return f'File type not allowed: {ext}'

    # Read header for MIME detection
    pos = uploaded_file.tell()
    header = uploaded_file.read(8192)
    uploaded_file.seek(pos)

    # MIME-based validation with python-magic
    try:
        import magic
        detected_mime = magic.from_buffer(header, mime=True)
        allowed_mimes = _EXT_MIME_MAP.get(ext, [])
        if allowed_mimes and not any(detected_mime.startswith(m) for m in allowed_mimes):
            logger.warning('Upload rejected: %s has MIME %s (expected %s)', uploaded_file.name, detected_mime, allowed_mimes)
            return 'File content does not match its extension'
    except ImportError:
        # Fallback: reject executables by signature
        _EXECUTABLE_SIGS = [b'MZ', b'\x7fELF', b'\xca\xfe', b'\xfe\xed']
        if any(header.startswith(s) for s in _EXECUTABLE_SIGS):
            return 'File content does not match its extension'

    # For images: verify with Pillow (destroys steganographic payloads)
    if ext in _IMAGE_EXTENSIONS:
        try:
            from PIL import Image
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            img.verify()
            uploaded_file.seek(0)
        except Exception:
            return 'Invalid or corrupted image file'

    return None


def serve_media(request, path):
    """Serve media files with Content-Disposition: attachment to prevent inline execution."""
    import mimetypes
    from urllib.parse import quote
    full_path = os.path.join(settings.MEDIA_ROOT, path)
    media_root_real = os.path.realpath(str(settings.MEDIA_ROOT))
    full_path_real = os.path.realpath(full_path)
    if not (full_path_real == media_root_real or full_path_real.startswith(media_root_real + os.sep)):
        return HttpResponse(status=403)
    if not os.path.isfile(full_path_real):
        return HttpResponse(status=404)
    content_type, _ = mimetypes.guess_type(full_path)
    content_type = content_type or 'application/octet-stream'
    # Force download for non-image/non-PDF files or any potentially executable content
    _INLINE_SAFE = {'image/png', 'image/jpeg', 'image/gif', 'image/webp', 'application/pdf'}
    filename = os.path.basename(path)
    resp = FileResponse(open(full_path, 'rb'), content_type=content_type)
    if content_type in _INLINE_SAFE:
        resp['Content-Disposition'] = f'inline; filename*=UTF-8\'\'{quote(filename)}'
    else:
        resp['Content-Disposition'] = f'attachment; filename*=UTF-8\'\'{quote(filename)}'
    resp['X-Content-Type-Options'] = 'nosniff'
    return resp


# ── Helpers ───────────────────────────────────────────────

def _get_ip(request):
    return request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')


def _rate_check(request, prefix, limit=5, period=300):
    """Atomic rate-limit check.  Returns (is_blocked, attempts)."""
    ip = _get_ip(request)
    key = f'{prefix}_{ip}'
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=period)
        count = 1
    return count > limit, count


# Daily AI request limit per user (resets midnight)
AI_DAILY_LIMIT = int(os.getenv('AI_DAILY_LIMIT', '100'))


def _ai_limit_check(user):
    """Check and increment daily AI request counter.  Returns True if blocked."""
    from datetime import date
    today = date.today()
    if user.ai_requests_date != today:
        user.ai_requests_today = 0
        user.ai_requests_date = today
    if user.ai_requests_today >= AI_DAILY_LIMIT:
        return True
    user.ai_requests_today += 1
    user.save(update_fields=['ai_requests_today', 'ai_requests_date'])
    return False

def _avatar_url(user):
    if not user.avatar:
        return ''
    try:
        return user.avatar.url
    except Exception:
        return ''


def _lang(request):
    return request.session.get('language', getattr(settings, 'DEFAULT_LANGUAGE', 'ru'))


def _ctx(request):
    lang = _lang(request)
    return {'lang': lang, 't': get_translations(lang)}


def _paginate(request, queryset, per_page=20):
    """Paginate a queryset; returns Page object."""
    paginator = Paginator(queryset, per_page)
    page_num = request.GET.get('page', 1)
    try:
        page_num = int(page_num)
    except (ValueError, TypeError):
        page_num = 1
    page_num = max(1, min(page_num, paginator.num_pages or 1))
    return paginator.get_page(page_num)


def _user_or_none(request):
    uid = request.session.get('user_id')
    if not uid:
        return None
    try:
        return EduUser.objects.get(id=uid, is_active=True)
    except EduUser.DoesNotExist:
        request.session.flush()
        return None


def _login_session(request, user):
    """Set up session for authenticated user.

    Calls cycle_key() to rotate the session ID, preventing session fixation attacks.
    """
    request.session.cycle_key()  # ← prevents session fixation
    request.session['user_id'] = user.id
    request.session['username'] = user.username
    request.session['user_email'] = user.email
    request.session['user_role'] = user.role
    request.session['user_avatar'] = _avatar_url(user)
    request.session['user_tz'] = user.tz or 'Asia/Almaty'


def _require_login(view_func):
    """Decorator: redirect to login if user is not authenticated."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.session.get('user_id'):
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _require_teacher(view_func):
    """Decorator: require authenticated teacher."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = _user_or_none(request)
        if not user:
            return redirect('login')
        if not user.is_teacher and not user.is_admin:
            return redirect('dashboard')
        request._edu_user = user
        return view_func(request, *args, **kwargs)
    return _wrapped


# ── Pages ────────────────────────────────────────────────

def index(request):
    ctx = _ctx(request)
    ctx['subjects_count'] = Subject.objects.count()
    ctx['teachers_count'] = EduUser.objects.filter(role='teacher').count()
    ctx['students_count'] = EduUser.objects.filter(role='student').count()
    ctx['tests_count'] = Test.objects.count()
    return render(request, 'core/index.html', ctx)


def dashboard(request):
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')

    ctx['user'] = user
    ctx['ai_available'] = ai.is_available()

    if user.is_student:
        # Данные студента
        ctx['recent_attempts'] = TestAttempt.objects.filter(student=user).select_related('test')[:5]
        ctx['essays'] = Essay.objects.filter(student=user).select_related('subject')[:5]
        ctx['subjects'] = Subject.objects.all()
        try:
            ctx['learning_profile'] = user.learning_profile
        except LearningProfile.DoesNotExist:
            ctx['learning_profile'] = LearningProfile.objects.create(student=user)
        try:
            ctx['accessibility'] = user.accessibility
        except AccessibilityProfile.DoesNotExist:
            ctx['accessibility'] = None

    elif user.is_teacher:
        # Данные учителя
        ctx['my_tests'] = Test.objects.filter(teacher=user).select_related('subject')[:10]
        ctx['my_lessons'] = Lesson.objects.filter(teacher=user).select_related('subject')[:10]
        ctx['subjects'] = Subject.objects.all()
        ctx['recent_attempts'] = TestAttempt.objects.filter(
            test__teacher=user
        ).select_related('test', 'student')[:10]
        ctx['class_reports'] = ClassReport.objects.filter(teacher=user).select_related('subject')[:5]

        # Actionable insights
        now = timezone.now()
        ctx['upcoming_deadlines'] = Assignment.objects.filter(
            teacher=user, due_date__gt=now, due_date__lte=now + timezone.timedelta(days=7),
            is_published=True,
        ).select_related('subject').order_by('due_date')[:5]
        ctx['struggling_students'] = TestAttempt.objects.filter(
            test__teacher=user, percentage__lt=50,
        ).select_related('test', 'student').order_by('-started_at')[:5]
        ctx['ungraded_submissions'] = AssignmentSubmission.objects.filter(
            assignment__teacher=user, status='submitted',
        ).select_related('assignment', 'student').order_by('-submitted_at')[:5]

    return render(request, 'core/dashboard.html', ctx)


def admin_panel(request):
    """Админ-панель: управление платформой (admin + school_admin)."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or user.role not in ('admin', 'school_admin'):
        return redirect('dashboard')

    ctx['user'] = user

    if user.is_admin:
        # Platform admin — full stats
        ctx['total_users'] = EduUser.objects.count()
        ctx['total_students'] = EduUser.objects.filter(role='student').count()
        ctx['total_teachers'] = EduUser.objects.filter(role='teacher').count()
        ctx['total_tests'] = Test.objects.count()
        ctx['total_attempts'] = TestAttempt.objects.count()
        ctx['total_essays'] = Essay.objects.count()
        ctx['total_lessons'] = Lesson.objects.count()
        ctx['total_subjects'] = Subject.objects.count()
        ctx['total_messages'] = ContactMessage.objects.count()
        ctx['unread_messages'] = ContactMessage.objects.filter(is_read=False).count()
        ctx['recent_users'] = EduUser.objects.all()[:15]
        ctx['recent_messages'] = ContactMessage.objects.filter(is_read=False)[:10]
        ctx['subjects'] = Subject.objects.all()
        ctx['recent_attempts'] = TestAttempt.objects.select_related('student', 'test')[:10]
        ctx['organizations'] = Organization.objects.all()
    elif user.is_school_admin and user.organization:
        # School admin — org-scoped
        org = user.organization
        ctx['organization'] = org
        members = EduUser.objects.filter(organization=org)
        ctx['total_users'] = members.count()
        ctx['total_students'] = members.filter(role='student').count()
        ctx['total_teachers'] = members.filter(role='teacher').count()
        ctx['teachers'] = members.filter(role='teacher').select_related('organization')
        ctx['recent_users'] = members[:15]
        ctx['subjects'] = Subject.objects.all()
        ctx['teacher_keys'] = OrganizationKey.objects.filter(
            organization=org, key_type='teacher'
        ).select_related('used_by', 'subject')[:20]
        ctx['student_keys'] = OrganizationKey.objects.filter(
            organization=org, key_type='student'
        ).select_related('used_by')[:20]
        ctx['total_tests'] = Test.objects.filter(teacher__organization=org).count()
        ctx['total_attempts'] = TestAttempt.objects.filter(student__organization=org).count()
        ctx['total_essays'] = Essay.objects.filter(student__organization=org).count()
        ctx['total_lessons'] = Lesson.objects.filter(teacher__organization=org).count()
        ctx['total_subjects'] = Subject.objects.count()
        ctx['total_messages'] = 0
        ctx['unread_messages'] = 0

    return render(request, 'core/admin.html', ctx)


def accessibility_module(request):
    """Модуль 1: Доступная среда."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    ctx['lessons'] = Lesson.objects.select_related('subject')[:20]
    try:
        ctx['accessibility'] = user.accessibility
    except AccessibilityProfile.DoesNotExist:
        ctx['accessibility'] = AccessibilityProfile.objects.create(user=user)
    return render(request, 'core/accessibility.html', ctx)


def teacher_assistant(request):
    """Модуль 2: Ассистент преподавателя."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()
    ctx['my_tests'] = Test.objects.filter(teacher=user).select_related('subject')[:20]
    ctx['ai_available'] = ai.is_available()
    return render(request, 'core/teacher_assistant.html', ctx)


def personalization(request):
    """Модуль 3: Персонализация."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()
    try:
        ctx['learning_profile'] = user.learning_profile
    except LearningProfile.DoesNotExist:
        ctx['learning_profile'] = LearningProfile.objects.create(student=user)
    ctx['ai_available'] = ai.is_available()
    return render(request, 'core/personalization.html', ctx)


def feedback_module(request):
    """Модуль 4: Проверка и Feedback Loop."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()
    ctx['ai_available'] = ai.is_available()

    if user.is_student:
        ctx['my_essays'] = Essay.objects.filter(student=user).select_related('subject')[:10]
    elif user.is_teacher or user.is_school_admin:
        ctx['my_reports'] = ClassReport.objects.filter(teacher=user).select_related('subject')[:10]
        # Scope essays: school_admin sees only their org's students
        essay_qs = Essay.objects.select_related('student', 'subject')
        if user.is_school_admin and user.organization:
            essay_qs = essay_qs.filter(student__organization=user.organization)
        ctx['recent_essays'] = essay_qs[:20]
    return render(request, 'core/feedback.html', ctx)


def faq(request):
    ctx = _ctx(request)
    ctx['faq_categories'] = FaqCategory.objects.prefetch_related('questions').all()
    return render(request, 'core/faq.html', ctx)


def copilot(request):
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    ctx['ai_available'] = ai.is_available()
    return render(request, 'core/copilot.html', ctx)


# ── Auth ─────────────────────────────────────────────────

def login(request):
    ctx = _ctx(request)
    if request.session.get('user_id'):
        return redirect('dashboard')

    if request.method == 'POST':
        # Rate limit: max 5 login attempts per IP per 5 min
        blocked, _ = _rate_check(request, 'login_rate', limit=5, period=300)
        if blocked:
            ctx['error'] = ctx['t'].get('err_too_many_logins', 'Слишком много попыток. Подождите 5 минут.')
            return render(request, 'core/login.html', ctx)

        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        user = EduUser.authenticate(email=email, password=password)
        if user:
            cache.delete(f'login_rate_{_get_ip(request)}')  # reset on success
            _login_session(request, user)
            return redirect('dashboard')
        ctx['error'] = ctx['t'].get('err_wrong_credentials', 'Неверный email или пароль')
        ctx['email'] = email

    return render(request, 'core/login.html', ctx)


def password_reset_request(request):
    """Step 1: user enters email, we generate token and send reset link."""
    ctx = _ctx(request)
    if request.session.get('user_id'):
        return redirect('dashboard')

    if request.method == 'POST':
        # Rate limit: max 3 reset attempts per IP per hour
        blocked, _ = _rate_check(request, 'pwreset_rate', limit=3, period=3600)
        if blocked:
            ctx['reset_sent'] = True  # don't reveal rate limit
            return render(request, 'core/password_reset.html', ctx)

        email = request.POST.get('email', '').strip()
        # Always show same message to avoid email enumeration
        ctx['reset_sent'] = True
        try:
            user = EduUser.objects.get(email=email)
            # Per-email rate limit: max 1 email per 5 min
            email_key = f'pwreset_email_{user.id}'
            if not cache.get(email_key):
                cache.set(email_key, 1, timeout=300)
                token = secrets.token_urlsafe(32)
                cache.set(f'password_reset_{token}', user.id, timeout=3600)
                reset_url = request.build_absolute_uri(f'/password-reset/{token}/')
                from django.core.mail import send_mail
                send_mail(
                    subject=ctx['t'].get('auth_reset_password', 'Reset password'),
                    message=f'{reset_url}',
                    from_email=None,  # uses DEFAULT_FROM_EMAIL
                    recipient_list=[user.email],
                    fail_silently=True,
                )
        except EduUser.DoesNotExist:
            pass  # don't reveal whether email exists

    return render(request, 'core/password_reset.html', ctx)


def password_reset_confirm(request, token):
    """Step 2: user clicks link with token, sets new password."""
    ctx = _ctx(request)
    user_id = cache.get(f'password_reset_{token}')
    if not user_id:
        ctx['invalid'] = True
        return render(request, 'core/password_reset_confirm.html', ctx)

    if request.method == 'POST':
        password = request.POST.get('password', '')
        password2 = request.POST.get('password_confirm', '')
        errors = []
        if len(password) < 6:
            errors.append(ctx['t'].get('err_password_min_6', 'Минимум 6 символов'))
        if password != password2:
            errors.append(ctx['t'].get('err_passwords_mismatch', 'Пароли не совпадают'))
        if errors:
            ctx['errors'] = errors
        else:
            try:
                user = EduUser.objects.get(id=user_id)
                cache.delete(f'password_reset_{token}')  # delete token before save to prevent reuse
                user.set_password(password)
                user.save()
                ctx['success'] = True
            except EduUser.DoesNotExist:
                ctx['invalid'] = True

    return render(request, 'core/password_reset_confirm.html', ctx)


def signup(request):
    ctx = _ctx(request)
    if request.session.get('user_id'):
        return redirect('dashboard')

    if request.method == 'POST':
        # Rate limit: max 5 signup attempts per IP per 10 min
        blocked, _ = _rate_check(request, 'signup_rate', limit=5, period=600)
        if blocked:
            ctx['errors'] = [ctx['t'].get('err_too_many_signups', 'Слишком много попыток регистрации. Подождите 10 минут.')]
            return render(request, 'core/signup.html', ctx)

        # Honeypot anti-bot field: bots fill invisible fields
        if request.POST.get('website', ''):
            # Silently reject — looks like success to the bot
            return redirect('dashboard')

        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password_confirm', '')
        school_key = request.POST.get('school_key', '').strip()
        # Teachers can only be created by admins — public signup is always 'student'
        role = 'student'
        errors = []

        t = ctx['t']

        # Validate school key
        key_obj = None
        if not school_key:
            errors.append(t.get('err_school_key_required', 'Введите ключ школы'))
        else:
            try:
                key_obj = OrganizationKey.objects.select_related('organization').get(
                    key=school_key, key_type='student', is_used=False
                )
            except OrganizationKey.DoesNotExist:
                errors.append(t.get('err_invalid_key', 'Недействительный или использованный ключ'))

        if len(username) < 3:
            errors.append(t.get('err_name_min_3', 'Имя минимум 3 символа'))
        if not email or '@' not in email:
            errors.append(t.get('err_invalid_email', 'Некорректный email'))
        if len(password) < 6:
            errors.append(t.get('err_password_min_6', 'Пароль минимум 6 символов'))
        if password != password2:
            errors.append(t.get('err_passwords_mismatch', 'Пароли не совпадают'))
        if EduUser.objects.filter(username=username).exists():
            errors.append(t.get('err_name_taken', 'Имя занято'))
        if EduUser.objects.filter(email=email).exists():
            errors.append(t.get('err_email_taken', 'Email уже зарегистрирован'))

        if errors:
            ctx['errors'] = errors
            ctx['username'] = username
            ctx['email'] = email
            ctx['first_name'] = first_name
            ctx['last_name'] = last_name
            ctx['school_key'] = school_key
            ctx['active_tab'] = 'student'
        else:
            user = EduUser.create_user(username=username, email=email, password=password,
                                       role=role, first_name=first_name, last_name=last_name,
                                       organization=key_obj.organization)
            # Создать профиль доступности и обучения
            AccessibilityProfile.objects.create(user=user)
            if role == 'student':
                LearningProfile.objects.create(student=user)
            key_obj.is_used = True
            key_obj.used_by = user
            key_obj.used_at = timezone.now()
            key_obj.save()
            _login_session(request, user)
            return redirect('dashboard')

    # Support ?tab= parameter for direct tab links
    if request.method == 'GET':
        tab = request.GET.get('tab', 'student')
        if tab in ('student', 'teacher', 'school'):
            ctx['active_tab'] = tab

    return render(request, 'core/signup.html', ctx)


def logout(request):
    request.session.flush()
    return redirect('home')


def profile(request):
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')

    if request.method == 'POST':
        action = request.POST.get('action', 'update_profile')
        if action == 'update_profile':
            user.first_name = request.POST.get('first_name', '').strip()
            user.last_name = request.POST.get('last_name', '').strip()
            user.patronymic = request.POST.get('patronymic', '').strip()
            username = request.POST.get('username', '').strip()
            if username and username != user.username:
                if EduUser.objects.filter(username=username).exclude(id=user.id).exists():
                    ctx['errors'] = [ctx['t'].get('err_name_taken', 'Имя занято')]
                else:
                    user.username = username
                    request.session['username'] = username

            grade_val = request.POST.get('grade', '')
            if grade_val:
                try:
                    user.grade = int(grade_val)
                except (ValueError, TypeError):
                    pass

            avatar_file = request.FILES.get('avatar')
            if avatar_file:
                _AVATAR_EXT = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
                aext = os.path.splitext(avatar_file.name)[1].lower()
                if avatar_file.size > 5 * 1024 * 1024:
                    ctx['errors'] = [ctx['t'].get('profile_max_size_err', 'Макс 5MB')]
                elif aext not in _AVATAR_EXT:
                    ctx['errors'] = [ctx['t'].get('err_invalid_image', 'Only image files allowed')]
                else:
                    v_err = _validate_upload(avatar_file)
                    if v_err:
                        ctx['errors'] = [v_err]
                    elif user.avatar and user.avatar.name:
                        try:
                            user.avatar.storage.delete(user.avatar.name)
                        except Exception:
                            logger.warning('Failed to delete old avatar: %s', user.avatar.name)
                    user.avatar = avatar_file

            user.save()
            request.session['user_avatar'] = _avatar_url(user)
            if 'errors' not in ctx:
                ctx['success'] = ctx['t'].get('msg_saved', 'Сохранено!')

        elif action == 'update_appearance':
            theme = request.POST.get('theme', 'light')
            lang = request.POST.get('language', 'ru')
            user_tz = request.POST.get('timezone', '').strip()
            if theme in ('light', 'dark'):
                user.theme = theme
                request.session['theme'] = theme
            if lang in ('ru', 'en', 'kk'):
                user.language = lang
                request.session['language'] = lang
            # Validate timezone
            import zoneinfo
            if user_tz:
                try:
                    zoneinfo.ZoneInfo(user_tz)
                    user.tz = user_tz
                    request.session['user_tz'] = user_tz
                except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                    pass
            user.save(update_fields=['theme', 'language', 'tz'])
            ctx['success'] = ctx['t'].get('msg_appearance_saved', 'Настройки внешнего вида сохранены!')

        elif action == 'change_password':
            cur = request.POST.get('current_password', '')
            new = request.POST.get('new_password', '')
            confirm = request.POST.get('confirm_password', '')
            errors = []
            if not user.check_password(cur):
                errors.append(ctx['t'].get('err_wrong_password', 'Неверный пароль'))
            if len(new) < 6:
                errors.append(ctx['t'].get('err_password_min_6', 'Минимум 6 символов'))
            if new != confirm:
                errors.append(ctx['t'].get('err_passwords_mismatch', 'Пароли не совпадают'))
            if errors:
                ctx['password_errors'] = errors
            else:
                user.set_password(new)
                user.save()
                ctx['password_success'] = ctx['t'].get('msg_password_changed', 'Пароль изменён!')

        elif action == 'update_accessibility':
            try:
                acc = user.accessibility
            except AccessibilityProfile.DoesNotExist:
                acc = AccessibilityProfile.objects.create(user=user)
            acc.primary_need = request.POST.get('primary_need', 'none')
            font_val = request.POST.get('font_size', '16')
            try:
                fs = int(font_val)
                acc.font_size = fs if 14 <= fs <= 32 else 16
            except (ValueError, TypeError):
                acc.font_size = 16
            font_family = request.POST.get('font_family', 'default')
            VALID_FONTS_PROFILE = {'default', 'opendyslexic', 'comfortaa', 'ptsans', 'pangolin',
                                   'verdana', 'georgia', 'arial', 'times', 'courier'}
            if font_family in VALID_FONTS_PROFILE:
                acc.font_family = font_family
            acc.high_contrast = request.POST.get('high_contrast') == 'on'
            acc.text_to_speech = request.POST.get('text_to_speech') == 'on'
            acc.easy_read = request.POST.get('easy_read') == 'on'
            acc.visual_aids = request.POST.get('visual_aids') == 'on'
            acc.zen_mode = request.POST.get('zen_mode') == 'on'
            acc.voice_input = request.POST.get('voice_input') == 'on'
            acc.save()
            request.session.pop('_acc_cache', None)  # Invalidate context processor cache
            ctx['acc_success'] = ctx['t'].get('msg_accessibility_saved', 'Настройки доступности сохранены!')

        elif action == 'update_tts':
            voice = request.POST.get('tts_voice', '').strip()
            speed_val = request.POST.get('tts_speed', '0')
            vol_val = request.POST.get('tts_volume', '100')
            try:
                user.tts_speed = max(-50, min(100, int(speed_val)))
            except (ValueError, TypeError):
                user.tts_speed = 0
            try:
                user.tts_volume = max(0, min(100, int(vol_val)))
            except (ValueError, TypeError):
                user.tts_volume = 100
            if re.match(r'^[a-zA-Z0-9\-]*$', voice):
                user.tts_voice = voice
            user.save(update_fields=['tts_voice', 'tts_speed', 'tts_volume'])
            ctx['success'] = ctx['t'].get('msg_tts_saved', 'TTS settings saved!')

    ctx['user'] = user
    ctx['profile_user'] = user
    try:
        ctx['accessibility'] = user.accessibility
    except AccessibilityProfile.DoesNotExist:
        ctx['accessibility'] = AccessibilityProfile.objects.create(user=user)
    return render(request, 'core/profile.html', ctx)


@require_POST
def delete_account(request):
    """Soft-delete user account after password confirmation.

    Educational data (test attempts, submissions) is preserved
    for school reporting. PII is scrubbed: chat history deleted,
    essays orphaned, profile anonymized.
    """
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    password = request.POST.get('password', '')
    if not user.check_password(password):
        return redirect('profile')
    # Delete PII-bearing records
    ChatMessage.objects.filter(user=user).delete()
    Essay.objects.filter(student=user).update(student=None)
    # Soft-delete: deactivate and anonymize PII so username/email can be reused
    anon_suffix = _uuid.uuid4().hex[:8]
    user.is_active = False
    user.username = f'deleted_{user.id}_{anon_suffix}'
    user.email = f'deleted_{user.id}_{anon_suffix}@deactivated.local'
    user.first_name = ''
    user.last_name = ''
    user.patronymic = ''
    if user.avatar and user.avatar.name:
        try:
            user.avatar.storage.delete(user.avatar.name)
        except Exception:
            logger.warning('Failed to delete avatar on account deactivation: %s', user.avatar.name)
    user.avatar = None
    user.save()
    request.session.flush()
    return redirect('home')


# ── API ──────────────────────────────────────────────────

@require_POST
def api_set_language(request):
    from .translations import available_languages
    try:
        data = json.loads(request.body)
        lang = data.get('language', 'ru')
        if lang in available_languages():
            request.session['language'] = lang
            user = _user_or_none(request)
            if user:
                user.language = lang
                user.save(update_fields=['language'])
            return JsonResponse({'success': True, 'language': lang})
    except Exception:
        logger.warning('api_set_language: invalid request')
    return JsonResponse({'error': 'Invalid'}, status=400)


@require_POST
def api_set_theme(request):
    try:
        data = json.loads(request.body)
        theme = data.get('theme', 'light')
        if theme in ('light', 'dark'):
            request.session['theme'] = theme
            user = _user_or_none(request)
            if user:
                user.theme = theme
                user.save(update_fields=['theme'])
            return JsonResponse({'success': True, 'theme': theme})
    except Exception:
        logger.warning('api_set_theme: invalid request')
    return JsonResponse({'error': 'Invalid'}, status=400)


@require_POST
def api_set_timezone(request):
    import zoneinfo
    try:
        data = json.loads(request.body)
        tz_name = data.get('timezone', '').strip()
        if tz_name:
            zoneinfo.ZoneInfo(tz_name)  # validate
            request.session['user_tz'] = tz_name
            user = _user_or_none(request)
            if user:
                user.tz = tz_name
                user.save(update_fields=['tz'])
            return JsonResponse({'success': True, 'timezone': tz_name})
    except (KeyError, zoneinfo.ZoneInfoNotFoundError):
        pass
    except Exception:
        logger.warning('api_set_timezone: invalid request')
    return JsonResponse({'error': 'Invalid timezone'}, status=400)


@require_POST
def api_accessibility(request):
    """API: Update accessibility settings from floating toolbar."""
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': 'auth'}, status=401)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid'}, status=400)

    try:
        acc = user.accessibility
    except AccessibilityProfile.DoesNotExist:
        acc = AccessibilityProfile.objects.create(user=user)

    VALID_FONTS = {'default', 'opendyslexic', 'comfortaa', 'ptsans', 'pangolin',
                   'verdana', 'georgia', 'arial', 'times', 'courier'}
    fields_changed = False

    if 'font_family' in data and data['font_family'] in VALID_FONTS:
        acc.font_family = data['font_family']
        fields_changed = True
    if 'font_size' in data:
        try:
            v = int(data['font_size'])
            if 14 <= v <= 32:
                acc.font_size = v
                fields_changed = True
        except (ValueError, TypeError):
            pass
    for field in ('high_contrast', 'easy_read', 'zen_mode', 'text_to_speech', 'voice_input', 'visual_aids'):
        if field in data and isinstance(data[field], bool):
            setattr(acc, field, data[field])
            fields_changed = True

    if fields_changed:
        acc.save()
        request.session.pop('_acc_cache', None)

    return JsonResponse({'success': True})


@require_POST
def api_speech_to_text(request):
    """API: Convert uploaded audio to text using SpeechRecognition + Google free API."""
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': 'auth'}, status=401)

    audio_file = request.FILES.get('audio')
    if not audio_file:
        return JsonResponse({'error': 'no_audio', 'text': ''}, status=400)

    # Limit file size (10MB)
    if audio_file.size > 10 * 1024 * 1024:
        return JsonResponse({'error': 'too_large', 'text': ''}, status=400)

    language = request.POST.get('language', 'ru')
    lang_map = {'ru': 'ru-RU', 'kk': 'kk-KZ', 'en': 'en-US'}
    lang = lang_map.get(language, 'ru-RU')

    import tempfile
    import subprocess
    tmp_path = wav_path = None
    try:
        import speech_recognition as sr

        # Save uploaded audio to temp file
        suffix = '.webm'
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in audio_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        # Convert to WAV using ffmpeg
        wav_path = tmp_path.replace(suffix, '.wav')
        result = subprocess.run(
            ['ffmpeg', '-i', tmp_path, '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path, '-y'],
            capture_output=True, timeout=15
        )
        if result.returncode != 0:
            logger.warning('ffmpeg conversion failed: %s', result.stderr[:200])
            return JsonResponse({'error': 'conversion_failed', 'text': ''}, status=500)

        # Recognize speech
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)

        text = recognizer.recognize_google(audio, language=lang)
        return JsonResponse({'text': text})

    except ImportError:
        return JsonResponse({'error': 'speech_recognition not installed', 'text': ''}, status=500)
    except Exception as e:
        err_name = type(e).__name__
        if err_name == 'UnknownValueError':
            return JsonResponse({'text': '', 'error': 'no_speech'})
        logger.warning('api_speech_to_text error: %s: %s', err_name, str(e)[:100])
        return JsonResponse({'text': '', 'error': 'recognition_failed'}, status=500)
    finally:
        for path in [tmp_path, wav_path]:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass


@require_POST
def api_ai_chat(request):
    lang = _lang(request)
    t = get_translations(lang)
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': t.get('err_auth_required', 'Авторизуйтесь')}, status=401)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)
    try:
        data = json.loads(request.body)
        user_msg = data.get('message', '').strip()
        if not user_msg:
            return JsonResponse({'error': 'Empty'}, status=400)
        if len(user_msg) > 4000:
            return JsonResponse({'error': t.get('err_message_too_long', 'Слишком длинное сообщение')}, status=400)

        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key

        ChatMessage.objects.create(user=user, session_key=session_key, role='user', content=user_msg)

        history = ChatMessage.objects.filter(user=user, session_key=session_key).order_by('-created_at')[:20]
        msgs = [{'role': m.role, 'content': m.content} for m in reversed(history)]

        answer = ai.chat(msgs, lang=lang)
        ChatMessage.objects.create(user=user, session_key=session_key, role='assistant', content=answer)
        return JsonResponse({'response': answer})

    except Exception as e:
        logger.error('AI chat error: %s', e)
        return JsonResponse({'error': t.get('err_ai_error', 'Ошибка ИИ')}, status=500)


@require_POST
def api_ai_stream(request):
    lang = _lang(request)
    t = get_translations(lang)
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': t.get('err_auth_required', 'Авторизуйтесь')}, status=401)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)
    try:
        data = json.loads(request.body)
        user_msg = data.get('message', '').strip()
    except Exception:
        return JsonResponse({'error': 'Invalid'}, status=400)

    if not user_msg:
        return JsonResponse({'error': 'Empty'}, status=400)
    if len(user_msg) > 4000:
        return JsonResponse({'error': t.get('err_message_too_long', 'Слишком длинное сообщение')}, status=400)

    # Use chat-level session_key from frontend, fallback to Django session
    session_key = data.get('session_key', '').strip()
    if not session_key:
        if not request.session.session_key:
            request.session.save()
        session_key = request.session.session_key
    ChatMessage.objects.create(user=user, session_key=session_key, role='user', content=user_msg)

    history = ChatMessage.objects.filter(user=user, session_key=session_key).order_by('-created_at')[:20]
    msgs = [{'role': m.role, 'content': m.content} for m in reversed(history)]

    def event_stream():
        collected = []
        saved = False
        try:
            for chunk in ai.stream(msgs, lang=lang):
                collected.append(chunk)
                yield f'data: {json.dumps({"token": chunk}, ensure_ascii=False)}\n\n'
        except GeneratorExit:
            # Client disconnected — save partial response, then return (do NOT yield)
            if not saved:
                saved = True
                full = ''.join(collected)
                if full.strip():
                    try:
                        ChatMessage.objects.create(user=user, session_key=session_key,
                                                   role='assistant', content=full)
                    except Exception:
                        logger.error('Failed to save partial streamed response to DB')
            return
        except Exception as exc:
            logger.error('Stream error: %s', exc)
            yield f'data: {json.dumps({"error": t.get("err_ai_error", "Error")})}\n\n'
        finally:
            # Save collected AI response (partial on error, full on success)
            if not saved:
                saved = True
                full = ''.join(collected)
                if full.strip():
                    try:
                        ChatMessage.objects.create(user=user, session_key=session_key,
                                                   role='assistant', content=full)
                    except Exception:
                        logger.error('Failed to save streamed response to DB')
        yield 'data: [DONE]\n\n'

    resp = StreamingHttpResponse(event_stream(), content_type='text/event-stream; charset=utf-8')
    resp['Cache-Control'] = 'no-cache'
    resp['X-Accel-Buffering'] = 'no'
    return resp


@require_POST
def api_generate_test(request):
    """API: Генерация теста из текста."""
    t = get_translations(_lang(request))
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': t.get('err_access_denied', 'Доступ запрещён')}, status=403)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    source_text = data.get('source_text', '').strip()
    subject_id = data.get('subject_id')
    grade = data.get('grade', 5)
    variant = data.get('variant', 'А')

    if not source_text:
        return JsonResponse({'error': t.get('err_no_text', 'Нет текста')}, status=400)

    subject = None
    if subject_id:
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            pass

    result = ai.generate_test(source_text, subject.name if subject else '', grade, variant)
    if not result:
        return JsonResponse({'error': t.get('err_ai_generate_test', 'ИИ не смог сгенерировать тест')}, status=500)

    questions = result.get('questions')
    if not isinstance(questions, list) or not questions:
        return JsonResponse({'error': t.get('err_ai_bad_format', 'ИИ вернул некорректный формат теста')}, status=500)

    if not subject:
        subject = Subject.objects.first()
    if not subject:
        return JsonResponse({'error': t.get('err_no_subjects', 'Нет доступных предметов')}, status=400)

    test = Test.objects.create(
        subject=subject,
        teacher=user,
        title=result.get('title', t.get('default_test_title', 'Test')),
        variant=variant,
        grade_level=grade,
        criteria=result.get('criteria', ''),
        source_text=source_text[:2000],
    )

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        TestQuestion.objects.create(
            test=test,
            question_text=q.get('text', ''),
            question_type=q.get('type', 'choice'),
            options=q.get('options'),
            correct_answer=q.get('correct', ''),
            points=q.get('points', 1),
            explanation=q.get('explanation', ''),
            order=i + 1,
        )

    return JsonResponse({
        'success': True,
        'test_id': test.id,
        'title': test.title,
        'questions_count': test.questions.count(),
        'criteria': test.criteria,
        'questions': questions,
    })


@require_POST
def api_check_essay(request):
    """API: Проверка эссе ИИ."""
    t = get_translations(_lang(request))
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': t.get('err_auth_required', 'Авторизуйтесь')}, status=401)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    essay_text = data.get('content', '').strip()
    title = data.get('title', t.get('default_essay_title', 'Essay')).strip()
    subject_id = data.get('subject_id')

    if not essay_text:
        return JsonResponse({'error': t.get('err_no_text', 'Нет текста')}, status=400)

    subject = None
    if subject_id:
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            pass
    if not subject:
        subject = Subject.objects.first()

    result = ai.check_essay(essay_text, title, subject.name if subject else '')
    if not result:
        return JsonResponse({'error': t.get('err_ai_check_essay', 'ИИ не смог проверить эссе')}, status=500)

    def _to_str(v):
        if isinstance(v, list):
            return '\n'.join(str(x) for x in v)
        return str(v) if v else ''

    result['strengths'] = _to_str(result.get('strengths', ''))
    result['weaknesses'] = _to_str(result.get('weaknesses', ''))
    result['recommendations'] = _to_str(result.get('recommendations', ''))

    essay = Essay.objects.create(
        student=user,
        subject=subject if subject else Subject.objects.first(),
        title=title,
        content=essay_text,
        is_checked=True,
        score=result.get('score', 0),
        logic_score=result.get('logic_score', 0),
        structure_score=result.get('structure_score', 0),
        argumentation_score=result.get('argumentation_score', 0),
        strengths=result.get('strengths', ''),
        weaknesses=result.get('weaknesses', ''),
        recommendations=result.get('recommendations', ''),
        materials_to_review=result.get('materials_to_review'),
        checked_at=timezone.now(),
    )

    return JsonResponse({
        'success': True,
        'essay_id': essay.id,
        'score': result.get('score', 0),
        'logic': result.get('logic_score', 0),
        'structure': result.get('structure_score', 0),
        'argumentation': result.get('argumentation_score', 0),
        'strengths': result.get('strengths', ''),
        'weaknesses': result.get('weaknesses', ''),
        'recommendations': result.get('recommendations', ''),
    })


@require_POST
def api_simplify_text(request):
    """API: Упрощение текста для easy-to-read."""
    t = get_translations(_lang(request))
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': t.get('err_auth_required', 'Авторизуйтесь')}, status=401)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid'}, status=400)

    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'error': t.get('err_no_text', 'Нет текста')}, status=400)

    result = ai.simplify_text(text)
    if not result:
        return JsonResponse({'error': t.get('err_ai_unavailable', 'ИИ недоступен')}, status=500)
    return JsonResponse({'success': True, 'simplified': result})


@require_POST
def api_generate_mindmap(request):
    """API: Генерация mind map."""
    t = get_translations(_lang(request))
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': t.get('err_auth_required', 'Авторизуйтесь')}, status=401)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid'}, status=400)

    text = data.get('text', '').strip()
    if not text:
        return JsonResponse({'error': t.get('err_no_text', 'Нет текста')}, status=400)

    result = ai.generate_mindmap(text)
    if not result:
        return JsonResponse({'error': t.get('err_ai_unavailable', 'ИИ недоступен')}, status=500)
    return JsonResponse({'success': True, 'mindmap': result})


@require_POST
def api_personalize(request):
    """API: Персонализированное объяснение."""
    t = get_translations(_lang(request))
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': t.get('err_auth_required', 'Авторизуйтесь')}, status=401)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid'}, status=400)

    topic = data.get('topic', '').strip()
    subject_name = data.get('subject', '').strip()
    difficulty = data.get('difficulty', 'medium')
    style = data.get('style', 'simple')
    interests_input = data.get('interests', [])
    if not topic:
        return JsonResponse({'error': t.get('err_specify_topic', 'Укажите тему')}, status=400)

    # Use submitted interests or fall back to profile
    interests = interests_input
    if not interests:
        try:
            interests = user.learning_profile.interests or []
        except LearningProfile.DoesNotExist:
            interests = []

    result = ai.personalize_explanation(
        topic, subject_name,
        interests, user.grade or 5,
        difficulty=difficulty, style=style,
    )
    if not result:
        return JsonResponse({'error': t.get('err_ai_unavailable', 'ИИ недоступен')}, status=500)
    return JsonResponse({'success': True, 'explanation': result})


@require_POST
def api_generate_report(request):
    """API: Сводный отчёт по классу."""
    t = get_translations(_lang(request))
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': t.get('err_access_denied', 'Доступ запрещён')}, status=403)
    if _ai_limit_check(user):
        return JsonResponse({'error': t.get('err_ai_limit', 'Дневной лимит ИИ-запросов исчерпан')}, status=429)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid'}, status=400)

    subject_id = data.get('subject_id')
    grade = data.get('grade', 5)

    subject = None
    if subject_id:
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            pass
    if not subject:
        subject = Subject.objects.first()
    if not subject:
        return JsonResponse({'error': t.get('err_no_subjects', 'Нет доступных предметов')}, status=400)

    # Собрать результаты тестов
    attempts = TestAttempt.objects.filter(
        test__subject=subject, test__grade_level=grade
    ).values('student__username', 'percentage', 'test__title')[:100]

    test_results = list(attempts)
    result = ai.generate_class_report(test_results, subject.name if subject else '', grade)
    if not result:
        return JsonResponse({'error': t.get('err_ai_unavailable', 'ИИ недоступен')}, status=500)

    report = ClassReport.objects.create(
        teacher=user,
        subject=subject,
        grade_level=grade,
        report_text=result.get('report_text', ''),
        problem_topics=result.get('problem_topics'),
        recommendations=result.get('recommendations', ''),
        avg_score=result.get('avg_score', 0),
        student_count=len(test_results),
    )

    return JsonResponse({
        'success': True,
        'report_id': report.id,
        'avg_score': result.get('avg_score', 0),
        'report': result.get('report_text', ''),
        'problem_topics': result.get('problem_topics', []),
        'recommendations': result.get('recommendations', ''),
    })


def contact(request):
    ctx = _ctx(request)
    user = _user_or_none(request)
    if user and request.method == 'GET':
        ctx['form_name'] = user.full_name
        ctx['form_email'] = user.email

    if request.method == 'POST':
        # Rate limit: max 5 contact messages per IP per 10 min
        blocked, _ = _rate_check(request, 'contact_rate', limit=5, period=600)
        if blocked:
            ctx['error_message'] = ctx['t'].get('err_too_many_messages', 'Слишком много сообщений. Подождите 10 минут.')
            return render(request, 'core/contact.html', ctx)

        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        errors = []
        t = ctx['t']
        if not name: errors.append(t.get('err_enter_name', 'Введите имя'))
        if not email: errors.append(t.get('err_enter_email', 'Введите email'))
        if not subject: errors.append(t.get('err_enter_subject', 'Введите тему'))
        if not message: errors.append(t.get('err_enter_message', 'Введите сообщение'))

        if errors:
            ctx['error_message'] = errors[0]
        else:
            ContactMessage.objects.create(
                name=name, email=email, subject=subject, message=message)
            ctx['success_message'] = t.get('msg_message_sent', 'Сообщение отправлено!')

    return render(request, 'core/contact.html', ctx)


def subscription(request):
    ctx = _ctx(request)
    return render(request, 'core/subscription.html', ctx)


def payment(request):
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    raw_plan = request.GET.get('plan', request.POST.get('plan', 'pro'))
    ctx['plan'] = raw_plan if raw_plan in ('free', 'pro', 'enterprise') else 'pro'
    return render(request, 'core/payment.html', ctx)


def about(request):
    """Страница «О платформе»."""
    ctx = _ctx(request)
    ctx['subjects_count'] = Subject.objects.count()
    ctx['teachers_count'] = EduUser.objects.filter(role='teacher').count()
    ctx['students_count'] = EduUser.objects.filter(role='student').count()
    ctx['tests_count'] = Test.objects.count()
    return render(request, 'core/about.html', ctx)


def lessons_catalog(request):
    """Каталог предметов и уроков."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    subjects = Subject.objects.all()
    selected_subject = request.GET.get('subject')
    ctx['subjects'] = subjects

    # Non-teachers only see published lessons
    base_qs = Lesson.objects.all() if user.is_teacher else Lesson.objects.filter(is_published=True)

    if selected_subject:
        try:
            subj = Subject.objects.get(id=selected_subject)
            ctx['selected_subject'] = subj
            qs = base_qs.filter(subject=subj).select_related('teacher')
        except Subject.DoesNotExist:
            qs = Lesson.objects.none()
    else:
        qs = base_qs.select_related('subject', 'teacher')

    ctx['page_obj'] = _paginate(request, qs, per_page=20)
    ctx['lessons'] = ctx['page_obj']

    return render(request, 'core/lessons.html', ctx)


# ── Teacher Lesson CRUD ─────────────────────────────────

def lesson_create(request):
    """Create a new lesson (teacher only)."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()
    ctx['ai_available'] = ai.is_available()

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        subject_id = request.POST.get('subject_id')
        grade = request.POST.get('grade_level', '5')
        errors = []
        if not title:
            errors.append('Title is required')
        if not content:
            errors.append('Content is required')
        if errors:
            ctx['errors'] = errors
            ctx['form'] = request.POST
        else:
            subject = None
            if subject_id:
                try:
                    subject = Subject.objects.get(id=subject_id)
                except Subject.DoesNotExist:
                    pass
            if not subject:
                subject = Subject.objects.first()
            if not subject:
                ctx['errors'] = ['No subjects available']
                return render(request, 'core/lesson_edit.html', ctx)
            try:
                grade_val = int(grade)
            except (ValueError, TypeError):
                grade_val = 5
            lesson = Lesson.objects.create(
                subject=subject, teacher=user, title=title,
                content=content, grade_level=grade_val,
                is_published=request.POST.get('is_published') == 'on',
            )
            attachment = request.FILES.get('attachment')
            if attachment:
                err = _validate_upload(attachment)
                if err:
                    ctx['errors'] = [err]
                    return render(request, 'core/lesson_edit.html', ctx)
                lesson.attachment = attachment
                lesson.attachment_name = attachment.name
                lesson.save(update_fields=['attachment', 'attachment_name'])
            return redirect('lesson_detail', lesson_id=lesson.id)
    return render(request, 'core/lesson_edit.html', ctx)


def lesson_edit(request, lesson_id):
    """Edit an existing lesson."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return redirect('login')
    try:
        lesson = Lesson.objects.get(id=lesson_id, teacher=user)
    except Lesson.DoesNotExist:
        return redirect('lessons')
    ctx['user'] = user
    ctx['lesson'] = lesson
    ctx['subjects'] = Subject.objects.all()
    ctx['ai_available'] = ai.is_available()
    ctx['editing'] = True

    if request.method == 'POST':
        lesson.title = request.POST.get('title', '').strip()
        lesson.content = request.POST.get('content', '').strip()
        subject_id = request.POST.get('subject_id')
        if subject_id:
            try:
                lesson.subject = Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist:
                pass
        try:
            lesson.grade_level = int(request.POST.get('grade_level', '5'))
        except (ValueError, TypeError):
            pass
        lesson.is_published = request.POST.get('is_published') == 'on'
        attachment = request.FILES.get('attachment')
        if attachment:
            err = _validate_upload(attachment)
            if err:
                ctx['errors'] = [err]
                return render(request, 'core/lesson_edit.html', ctx)
            if lesson.attachment and lesson.attachment.name:
                try:
                    lesson.attachment.storage.delete(lesson.attachment.name)
                except Exception:
                    logger.warning('Failed to delete old lesson attachment: %s', lesson.attachment.name)
            lesson.attachment = attachment
            lesson.attachment_name = attachment.name
        if request.POST.get('remove_attachment') == '1' and lesson.attachment:
            try:
                lesson.attachment.storage.delete(lesson.attachment.name)
            except Exception:
                logger.warning('Failed to delete attachment on remove: %s', lesson.attachment.name)
            lesson.attachment = None
            lesson.attachment_name = ''
        lesson.save()
        ctx['success'] = 'Lesson saved!'
        ctx['lesson'] = lesson
    return render(request, 'core/lesson_edit.html', ctx)


def lesson_detail(request, lesson_id):
    """View a single lesson."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    try:
        lesson = Lesson.objects.select_related('subject', 'teacher').get(id=lesson_id)
    except Lesson.DoesNotExist:
        return redirect('lessons')
    # Access control: owner or published only
    if not lesson.is_published and lesson.teacher != user:
        return redirect('lessons')
    ctx['user'] = user
    ctx['lesson'] = lesson
    ctx['ai_available'] = ai.is_available()
    ctx['is_owner'] = user == lesson.teacher
    return render(request, 'core/lesson_detail.html', ctx)


@require_POST
def lesson_delete(request, lesson_id):
    """Delete a lesson (owner only)."""
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': 'auth'}, status=401)
    try:
        lesson = Lesson.objects.get(id=lesson_id, teacher=user)
    except Lesson.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    if lesson.attachment and lesson.attachment.name:
        try:
            lesson.attachment.storage.delete(lesson.attachment.name)
        except Exception:
            logger.warning('Failed to delete attachment on lesson delete: %s', lesson.attachment.name)
    lesson.delete()
    return JsonResponse({'success': True})


@require_POST
def api_ai_lesson_content(request):
    """AI-assisted lesson content generation for teachers."""
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)
    topic = data.get('topic', '').strip()
    subject_name = data.get('subject', '').strip()
    grade = data.get('grade', 5)
    prompt = data.get('prompt', '').strip()
    if not topic:
        return JsonResponse({'error': 'topic required'}, status=400)
    result = ai.generate_lesson_content(topic, subject_name, grade, prompt)
    if not result:
        return JsonResponse({'error': 'AI unavailable'}, status=500)
    return JsonResponse({'success': True, 'content': result})


# ── Admin API ────────────────────────────────────────────

@require_POST
def api_admin_toggle_user(request):
    """Toggle user active status."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        target = EduUser.objects.get(id=data['user_id'])
        if target.id == user.id:
            return JsonResponse({'error': 'cannot deactivate self'}, status=400)
        target.is_active = not target.is_active
        target.save(update_fields=['is_active'])
        return JsonResponse({'success': True, 'is_active': target.is_active})
    except (EduUser.DoesNotExist, KeyError):
        return JsonResponse({'error': 'not found'}, status=404)


@require_POST
def api_admin_change_role(request):
    """Change user role."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        target = EduUser.objects.get(id=data['user_id'])
        role = data.get('role', 'student')
        if role not in ('student', 'teacher', 'school_admin', 'admin'):
            return JsonResponse({'error': 'invalid role'}, status=400)
        target.role = role
        target.save(update_fields=['role'])
        return JsonResponse({'success': True, 'role': role})
    except (EduUser.DoesNotExist, KeyError):
        return JsonResponse({'error': 'not found'}, status=404)


@require_POST
def api_admin_mark_read(request):
    """Mark message as read."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        msg = ContactMessage.objects.get(id=data['message_id'])
        msg.is_read = True
        msg.save(update_fields=['is_read'])
        return JsonResponse({'success': True})
    except (ContactMessage.DoesNotExist, KeyError):
        return JsonResponse({'error': 'not found'}, status=404)


@require_POST
def api_admin_reply(request):
    """Reply to a contact message."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
        msg = ContactMessage.objects.get(id=data['message_id'])
        reply_text = data.get('reply', '').strip()
        if not reply_text:
            return JsonResponse({'error': 'empty reply'}, status=400)
        msg.admin_reply = reply_text
        msg.replied_at = timezone.now()
        msg.is_read = True
        msg.is_resolved = True
        msg.save(update_fields=['admin_reply', 'replied_at', 'is_read', 'is_resolved'])
        return JsonResponse({'success': True})
    except (ContactMessage.DoesNotExist, KeyError):
        return JsonResponse({'error': 'not found'}, status=404)


def api_admin_i18n(request):
    """Admin i18n editor API. GET = load, POST = save."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    from .translations import get_all_translations, save_translations, available_languages
    if request.method == 'GET':
        lang = request.GET.get('lang', 'ru')
        data = get_all_translations(lang)
        return JsonResponse({'lang': lang, 'keys': data, 'languages': available_languages()})
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            lang = data.get('lang', 'ru')
            keys = data.get('keys', {})
            if not isinstance(keys, dict):
                return JsonResponse({'error': 'invalid'}, status=400)
            save_translations(lang, keys)
            return JsonResponse({'success': True, 'count': len(keys)})
        except Exception:
            logger.warning('api_admin_i18n: save failed')
            return JsonResponse({'error': 'Save failed'}, status=400)
    return JsonResponse({'error': 'method'}, status=405)


# ── Error handlers ───────────────────────────────────────

def error_404(request, exception):
    return render(request, 'core/404.html', _ctx(request), status=404)

def error_500(request):
    try:
        ctx = _ctx(request)
    except Exception:
        ctx = {'lang': 'ru'}
    return render(request, 'core/500.html', ctx, status=500)

def error_403(request, exception):
    return render(request, 'core/403.html', _ctx(request), status=403)


# ── TTS API (edge-tts — Microsoft Neural voices) ────

def _tts_split_sentences(text, max_chunk=2500):
    """Split text into chunks at sentence boundaries, each ≤ max_chunk chars.

    Priority: split at . ! ? ; then at , then at whitespace.
    Never splits mid-word. Tries to keep chunks close to max_chunk for efficiency.
    """
    if len(text) <= max_chunk:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chunk:
            chunks.append(remaining)
            break

        # Find the best split point within max_chunk
        window = remaining[:max_chunk]

        # Try sentence-ending punctuation first
        best = -1
        for sep in ['. ', '! ', '? ', '.\n', '!\n', '?\n', '; ', ';\n']:
            pos = window.rfind(sep)
            if pos > best:
                best = pos + len(sep) - 1  # include the punctuation, not the space

        if best > max_chunk * 0.3:
            # Good split point found
            split_at = best + 1
        else:
            # Try comma
            pos = window.rfind(', ')
            if pos > max_chunk * 0.3:
                split_at = pos + 1
            else:
                # Last resort: split at whitespace
                pos = window.rfind(' ')
                if pos > max_chunk * 0.2:
                    split_at = pos + 1
                else:
                    split_at = max_chunk

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return [c for c in chunks if c]


@require_POST
def api_tts(request):
    """Server-side TTS using edge-tts — returns MP3 audio with voice selection.

    Audio is cached by content hash so identical requests are served instantly.
    """
    if not request.session.get('user_id'):
        return JsonResponse({'error': 'auth'}, status=401)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)
    text = (data.get('text') or '').strip()
    if not text:
        return JsonResponse({'error': 'empty text'}, status=400)
    truncated = len(text) > 3000
    if truncated:
        text = text[:3000]
    # Strip markdown artifacts for cleaner speech
    text = re.sub(r'```[\s\S]*?```', '', text)  # code blocks
    text = re.sub(r'`[^`]+`', '', text)          # inline code
    text = re.sub(r'[#*_~>{}\[\]|]', '', text)   # markdown chars
    text = re.sub(r'https?://\S+', '', text)      # URLs
    text = re.sub(r'\n{3,}', '\n\n', text)        # excess newlines
    text = text.strip()
    if not text:
        return JsonResponse({'error': 'empty text'}, status=400)

    voice = (data.get('voice') or '').strip()
    rate = data.get('rate', '+0%')
    # Validate voice name (only letters, digits, hyphens)
    if not voice or not re.match(r'^[a-zA-Z0-9\-]+$', voice):
        voice = 'en-US-AvaMultilingualNeural'
    # Validate rate format
    if not isinstance(rate, str) or not re.match(r'^[+-]?\d{1,3}%$', rate):
        rate = '+0%'

    # ── Cache lookup by content hash ──
    cache_key = 'tts:' + hashlib.sha256(f'{text}|{voice}|{rate}'.encode()).hexdigest()[:32]
    cached = cache.get(cache_key)
    if cached:
        response = HttpResponse(cached, content_type='audio/mpeg')
        response['Content-Disposition'] = 'inline; filename="tts.mp3"'
        return response

    try:
        import edge_tts
        from asgiref.sync import async_to_sync

        async def _generate():
            comm = edge_tts.Communicate(text, voice, rate=rate)
            buf = io.BytesIO()
            async for chunk in comm.stream():
                if chunk['type'] == 'audio':
                    buf.write(chunk['data'])
            return buf.getvalue()

        audio_data = async_to_sync(_generate)()
        if not audio_data:
            raise RuntimeError('empty audio')
    except Exception as e:
        logger.warning('edge-tts failed (%s), trying gTTS fallback', e)
        # ── Fallback: gTTS (run in thread with timeout to avoid blocking) ──
        try:
            from gtts import gTTS
            lang_code = 'ru'
            if voice.startswith('kk-'):
                lang_code = 'tr'  # gTTS has no Kazakh; Turkish is closest
            elif voice.startswith('en-'):
                lang_code = 'en'
            elif voice.startswith('de-'):
                lang_code = 'de'
            elif voice.startswith('fr-'):
                lang_code = 'fr'
            elif voice.startswith('es-'):
                lang_code = 'es'
            def _gtts_generate():
                tts_obj = gTTS(text=text, lang=lang_code)
                buf = io.BytesIO()
                tts_obj.write_to_fp(buf)
                return buf.getvalue()
            with ThreadPoolExecutor(max_workers=1) as executor:
                audio_data = executor.submit(_gtts_generate).result(timeout=15)
        except FuturesTimeoutError:
            logger.error('gTTS fallback timed out (15s)')
            return JsonResponse({'error': 'TTS service timeout'}, status=504)
        except Exception as e2:
            logger.error('gTTS fallback also failed: %s', e2)
            return JsonResponse({'error': 'TTS service error'}, status=500)

    if not audio_data:
        return JsonResponse({'error': 'TTS failed'}, status=500)

    # Cache for 1 hour (max 2 MB to avoid bloating the cache)
    if len(audio_data) <= 2 * 1024 * 1024:
        cache.set(cache_key, audio_data, timeout=3600)

    response = HttpResponse(audio_data, content_type='audio/mpeg')
    response['Content-Disposition'] = 'inline; filename="tts.mp3"'
    if truncated:
        response['X-TTS-Truncated'] = '1'
    return response


@require_POST
def api_tts_chunked(request):
    """Chunked TTS: split text at sentence boundaries, return chunk info or audio.

    POST with action="prepare":
      body: {text, voice, rate}
      returns: {chunks: [{index, text_preview, char_count}], total_chunks, session_id}

    POST with action="chunk":
      body: {session_id, chunk_index, voice, rate}
      returns: audio/mpeg for that chunk
    """
    if not request.session.get('user_id'):
        return JsonResponse({'error': 'auth'}, status=401)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    action = data.get('action', 'prepare')

    if action == 'prepare':
        text = (data.get('text') or '').strip()
        if not text:
            return JsonResponse({'error': 'empty text'}, status=400)
        # Clean markdown
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`[^`]+`', '', text)
        text = re.sub(r'[#*_~>{}\[\]|]', '', text)
        text = re.sub(r'https?://\S+', '', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        if not text:
            return JsonResponse({'error': 'empty text'}, status=400)

        chunks = _tts_split_sentences(text, max_chunk=2500)
        session_id = hashlib.sha256(text.encode()).hexdigest()[:16]
        # Store chunks in cache for retrieval
        cache.set(f'tts_chunks:{session_id}', chunks, timeout=600)

        return JsonResponse({
            'session_id': session_id,
            'total_chunks': len(chunks),
            'chunks': [
                {
                    'index': i,
                    'text_preview': c[:60] + ('…' if len(c) > 60 else ''),
                    'char_count': len(c),
                }
                for i, c in enumerate(chunks)
            ],
        })

    elif action == 'chunk':
        session_id = data.get('session_id', '')
        chunk_index = data.get('chunk_index', 0)
        if not session_id or not re.match(r'^[a-f0-9]{16}$', session_id):
            return JsonResponse({'error': 'invalid session'}, status=400)

        chunks = cache.get(f'tts_chunks:{session_id}')
        if not chunks:
            return JsonResponse({'error': 'session expired, re-prepare'}, status=410)
        if not (0 <= chunk_index < len(chunks)):
            return JsonResponse({'error': 'invalid chunk index'}, status=400)

        chunk_text = chunks[chunk_index]
        voice = (data.get('voice') or '').strip()
        rate = data.get('rate', '+0%')
        if not voice or not re.match(r'^[a-zA-Z0-9\-]+$', voice):
            voice = 'en-US-AvaMultilingualNeural'
        if not isinstance(rate, str) or not re.match(r'^[+-]?\d{1,3}%$', rate):
            rate = '+0%'

        # Cache per-chunk audio
        cache_key = 'tts:' + hashlib.sha256(f'{chunk_text}|{voice}|{rate}'.encode()).hexdigest()[:32]
        cached = cache.get(cache_key)
        if cached:
            resp = HttpResponse(cached, content_type='audio/mpeg')
            resp['X-Chunk-Index'] = str(chunk_index)
            resp['X-Total-Chunks'] = str(len(chunks))
            return resp

        try:
            import edge_tts
            from asgiref.sync import async_to_sync

            async def _generate():
                comm = edge_tts.Communicate(chunk_text, voice, rate=rate)
                buf = io.BytesIO()
                async for ch in comm.stream():
                    if ch['type'] == 'audio':
                        buf.write(ch['data'])
                return buf.getvalue()

            audio_data = async_to_sync(_generate)()
            if not audio_data:
                raise RuntimeError('empty audio')
        except Exception as e:
            logger.warning('edge-tts chunk failed (%s), gTTS fallback', e)
            # gTTS fallback with timeout to avoid blocking worker
            try:
                from gtts import gTTS
                lang_code = 'ru'
                if voice.startswith('kk-'):
                    lang_code = 'tr'
                elif voice.startswith('en-'):
                    lang_code = 'en'
                def _gtts_chunk():
                    tts_obj = gTTS(text=chunk_text, lang=lang_code)
                    buf = io.BytesIO()
                    tts_obj.write_to_fp(buf)
                    return buf.getvalue()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    audio_data = executor.submit(_gtts_chunk).result(timeout=15)
            except FuturesTimeoutError:
                logger.error('gTTS chunk fallback timed out (15s)')
                return JsonResponse({'error': 'TTS timeout'}, status=504)
            except Exception as e2:
                logger.error('gTTS chunk fallback failed: %s', e2)
                return JsonResponse({'error': 'TTS error'}, status=500)

        if audio_data and len(audio_data) <= 2 * 1024 * 1024:
            cache.set(cache_key, audio_data, timeout=3600)

        resp = HttpResponse(audio_data, content_type='audio/mpeg')
        resp['X-Chunk-Index'] = str(chunk_index)
        resp['X-Total-Chunks'] = str(len(chunks))
        return resp

    return JsonResponse({'error': 'invalid action'}, status=400)


def api_tts_voices(request):
    """Return available edge-tts voices (cached). Includes fallback list."""
    cached = cache.get('edgettsvoices')
    if cached:
        return JsonResponse({'voices': cached})

    # Hardcoded fallback so the UI always has voices even if edge-tts hangs
    _FALLBACK_VOICES = [
        {'id': 'en-US-AvaMultilingualNeural', 'name': 'Ava 🌐', 'lang': 'multi', 'gender': 'Female'},
        {'id': 'en-US-AndrewMultilingualNeural', 'name': 'Andrew 🌐', 'lang': 'multi', 'gender': 'Male'},
        {'id': 'en-US-EmmaMultilingualNeural', 'name': 'Emma 🌐', 'lang': 'multi', 'gender': 'Female'},
        {'id': 'en-US-BrianMultilingualNeural', 'name': 'Brian 🌐', 'lang': 'multi', 'gender': 'Male'},
        {'id': 'ru-RU-SvetlanaNeural', 'name': 'Svetlana', 'lang': 'ru-RU', 'gender': 'Female'},
        {'id': 'ru-RU-DmitryNeural', 'name': 'Dmitry', 'lang': 'ru-RU', 'gender': 'Male'},
        {'id': 'kk-KZ-AigulNeural', 'name': 'Aigul', 'lang': 'kk-KZ', 'gender': 'Female'},
        {'id': 'kk-KZ-DauletNeural', 'name': 'Daulet', 'lang': 'kk-KZ', 'gender': 'Male'},
        {'id': 'en-US-JennyNeural', 'name': 'Jenny', 'lang': 'en-US', 'gender': 'Female'},
        {'id': 'en-US-GuyNeural', 'name': 'Guy', 'lang': 'en-US', 'gender': 'Male'},
        {'id': 'en-GB-SoniaNeural', 'name': 'Sonia', 'lang': 'en-GB', 'gender': 'Female'},
    ]

    try:
        import asyncio
        import edge_tts

        async def _list_with_timeout():
            return await asyncio.wait_for(edge_tts.list_voices(), timeout=8)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                from asgiref.sync import async_to_sync
                voices_raw = async_to_sync(_list_with_timeout)()
            else:
                voices_raw = loop.run_until_complete(_list_with_timeout())
        except RuntimeError:
            voices_raw = asyncio.run(_list_with_timeout())

        multilingual = []
        regular = []
        for v in voices_raw:
            locale = v.get('Locale', '')
            short = v['ShortName']
            is_multi = 'Multilingual' in short
            entry = {
                'id': short,
                'name': short.split('-', 2)[-1].replace('Neural', '').replace('Multilingual', ' 🌐'),
                'lang': 'multi' if is_multi else locale,
                'gender': v.get('Gender', ''),
            }
            if is_multi:
                multilingual.append(entry)
            elif locale.startswith(('ru-', 'en-', 'kk-', 'tr-', 'de-', 'fr-', 'es-', 'ja-', 'zh-', 'ko-')):
                regular.append(entry)
        voices = multilingual + regular
        if voices:
            cache.set('edgettsvoices', voices, 3600)
            return JsonResponse({'voices': voices})
        # edge-tts returned empty — use fallback
        cache.set('edgettsvoices', _FALLBACK_VOICES, 600)
        return JsonResponse({'voices': _FALLBACK_VOICES})
    except Exception as e:
        logger.warning('TTS voices error: %s — using fallback list', e)
        cache.set('edgettsvoices', _FALLBACK_VOICES, 300)
        return JsonResponse({'voices': _FALLBACK_VOICES})


# ── Manual Test Creation ─────────────────────────────────

def test_create(request):
    """Manual test builder for teachers."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()
    return render(request, 'core/test_create.html', ctx)


@require_POST
def api_test_save(request):
    """Save manually created test with questions."""
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)

    title = data.get('title', '').strip()
    subject_id = data.get('subject_id')
    grade = data.get('grade', 5)
    time_limit = data.get('time_limit', 45)
    questions = data.get('questions', [])

    if not title:
        return JsonResponse({'error': 'title required'}, status=400)
    if not questions:
        return JsonResponse({'error': 'questions required'}, status=400)

    subject = None
    if subject_id:
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            pass
    if not subject:
        subject = Subject.objects.first()
    if not subject:
        return JsonResponse({'error': 'no subjects'}, status=400)

    try:
        grade_val = int(grade)
    except (ValueError, TypeError):
        grade_val = 5
    try:
        time_val = max(5, min(180, int(time_limit)))
    except (ValueError, TypeError):
        time_val = 45

    test = Test.objects.create(
        subject=subject, teacher=user, title=title,
        grade_level=grade_val, time_limit=time_val,
        is_published=data.get('is_published', True),
    )

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            continue
        text = q.get('text', '').strip()
        if not text:
            continue
        TestQuestion.objects.create(
            test=test,
            question_text=text,
            question_type=q.get('type', 'choice'),
            options=q.get('options') if isinstance(q.get('options'), list) else None,
            correct_answer=q.get('correct', ''),
            points=max(1, int(q.get('points', 1) or 1)),
            explanation=q.get('explanation', ''),
            order=i + 1,
        )

    return JsonResponse({
        'success': True,
        'test_id': test.id,
        'title': test.title,
        'questions_count': test.questions.count(),
    })


def test_manage(request):
    """Teacher's test list with management."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return redirect('login')
    ctx['user'] = user
    qs = Test.objects.filter(teacher=user).select_related('subject')
    ctx['page_obj'] = _paginate(request, qs, per_page=20)
    ctx['tests'] = ctx['page_obj']
    return render(request, 'core/test_manage.html', ctx)


@require_POST
def api_test_publish(request, test_id):
    """Toggle test published status."""
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        test = Test.objects.get(id=test_id, teacher=user)
    except Test.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    test.is_published = not test.is_published
    test.save(update_fields=['is_published'])
    return JsonResponse({'success': True, 'is_published': test.is_published})


@require_POST
def api_test_delete(request, test_id):
    """Delete a test."""
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        test = Test.objects.get(id=test_id, teacher=user)
    except Test.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    test.delete()
    return JsonResponse({'success': True})


# ── Student Test Taking ──────────────────────────────────

def test_list(request):
    """Browse available published tests."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()
    subject_filter = request.GET.get('subject')
    qs = Test.objects.filter(is_published=True).select_related('subject', 'teacher')
    if subject_filter:
        qs = qs.filter(subject_id=subject_filter)
        try:
            ctx['selected_subject'] = Subject.objects.get(id=subject_filter)
        except Subject.DoesNotExist:
            pass
    ctx['page_obj'] = _paginate(request, qs, per_page=20)
    ctx['tests'] = ctx['page_obj']
    # Student's past attempts
    if user.is_student:
        ctx['my_attempts'] = TestAttempt.objects.filter(student=user).select_related('test__subject')[:20]
    return render(request, 'core/test_list.html', ctx)


def test_take(request, test_id):
    """Take a test — display questions."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    try:
        test = Test.objects.prefetch_related('questions').get(id=test_id, is_published=True)
    except Test.DoesNotExist:
        return redirect('test_list')
    # Check if already attempted
    existing = TestAttempt.objects.filter(test=test, student=user, finished_at__isnull=False).first()
    if existing:
        return redirect('test_result', attempt_id=existing.id)
    ctx['user'] = user
    ctx['test'] = test
    ctx['questions'] = test.questions.all()
    return render(request, 'core/test_take.html', ctx)


@require_POST
def api_test_submit(request, test_id):
    """Submit test answers and get score."""
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': 'auth'}, status=401)
    try:
        test = Test.objects.prefetch_related('questions').get(id=test_id, is_published=True)
    except Test.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    # Prevent duplicate submissions (atomic check)
    if TestAttempt.objects.filter(test=test, student=user, finished_at__isnull=False).exists():
        existing = TestAttempt.objects.filter(test=test, student=user, finished_at__isnull=False).first()
        return JsonResponse({'error': 'already submitted', 'attempt_id': existing.id}, status=400)

    # Enforce time limit: reject if started_at + time_limit < now (with 2 min grace)
    if test.time_limit and test.time_limit > 0:
        in_progress = TestAttempt.objects.filter(
            test=test, student=user, finished_at__isnull=True
        ).first()
        if in_progress:
            from datetime import timedelta
            deadline = in_progress.started_at + timedelta(minutes=test.time_limit + 2)
            if timezone.now() > deadline:
                in_progress.finished_at = deadline
                in_progress.score = 0
                in_progress.max_score = sum(q.points for q in test.questions.all())  # uses prefetch cache
                in_progress.percentage = 0
                in_progress.save()
                return JsonResponse({'error': 'time_expired', 'attempt_id': in_progress.id}, status=400)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)

    def _normalize(s):
        """Normalize text answer for comparison: lowercase, strip punctuation/spaces."""
        s = s.lower().strip()
        s = re.sub(r'[.,;:!?\-—–\'"«»""\'\'()\[\]{}]', '', s)  # remove punctuation
        s = re.sub(r'\s+', ' ', s).strip()  # collapse whitespace
        return s

    def _text_match(student_ans, correct_ans):
        """Check if text answers match with flexible comparison.

        Strategy:
        1. Exact match after normalization
        2. Word-set equivalence (any order)
        3. All correct-answer words present in student answer
        4. Student content words cover ≥50% of correct content words
        """
        s_norm = _normalize(student_ans)
        c_norm = _normalize(correct_ans)
        if not s_norm:
            return False
        # 1. Exact match after normalization
        if s_norm == c_norm:
            return True
        c_words = set(c_norm.split())
        s_words = set(s_norm.split())
        if not c_words:
            return False
        # 2. Word-set equivalence (any order): "Пушкин АС" == "АС Пушкин"
        if c_words == s_words:
            return True
        # 3. Student words are a superset of correct words (student wrote more but includes all key words)
        if c_words.issubset(s_words):
            return True
        # 4. Partial match: student content words must cover ≥50% of correct content words
        _filler = {'и', 'в', 'на', 'это', 'the', 'a', 'an', 'is', 'of', 'in', 'to', 'бұл', 'мен', 'да', 'не', 'по'}
        c_content = c_words - _filler
        s_content = s_words - _filler
        if s_content and c_content:
            overlap = s_content & c_content
            coverage = len(overlap) / len(c_content)
            if coverage >= 0.5 and len(overlap) >= 2:
                return True
        return False

    answers = data.get('answers', {})

    # Wrap in transaction to prevent race condition on double-click
    try:
        with transaction.atomic():
            # Lock this student's attempts to prevent double-submit
            existing = (TestAttempt.objects.select_for_update()
                        .filter(test=test, student=user, finished_at__isnull=False).first())
            if existing:
                return JsonResponse({'error': 'already submitted', 'attempt_id': existing.id}, status=400)

            attempt = TestAttempt.objects.create(test=test, student=user)
            total_score = 0
            max_score = 0
            questions = test.questions.all()

            for q in questions:
                max_score += q.points
                student_answer = str(answers.get(str(q.id), '')).strip()
                correct = q.correct_answer.strip()

                if q.question_type == 'choice' and q.options and len(correct) <= 2:
                    # correct_answer stores letter (A,B,C...), student submits option text
                    try:
                        idx = q.options.index(student_answer)
                        student_letter = chr(65 + idx)
                        is_correct = student_letter == correct.upper()
                    except (ValueError, IndexError):
                        is_correct = student_answer.lower() == correct.lower()
                else:
                    is_correct = _text_match(student_answer, correct)

                points = q.points if is_correct else 0
                total_score += points
                StudentAnswer.objects.create(
                    attempt=attempt, question=q,
                    answer_text=student_answer,
                    is_correct=is_correct,
                    points_earned=points,
                )

            percentage = (total_score / max_score * 100) if max_score > 0 else 0
            attempt.score = total_score
            attempt.max_score = max_score
            attempt.percentage = percentage
            attempt.finished_at = timezone.now()
            attempt.save()

            # ── Update LearningProfile ───────────────────────
            if user.is_student:
                profile, _ = LearningProfile.objects.get_or_create(student=user)
                all_attempts = TestAttempt.objects.filter(student=user, finished_at__isnull=False)
                profile.total_tests_taken = all_attempts.count()
                scores = list(all_attempts.values_list('percentage', flat=True))
                profile.avg_score = sum(scores) / len(scores) if scores else 0

                # Streak: count consecutive days with activity
                today = timezone.now().date()
                if profile.last_activity:
                    last_date = profile.last_activity.date()
                    if today == last_date:
                        pass  # same day, keep streak
                    elif (today - last_date).days == 1:
                        profile.streak_days += 1
                    else:
                        profile.streak_days = 1
                else:
                    profile.streak_days = 1
                profile.last_activity = timezone.now()

                # Weak & strong topics based on subject performance
                subject_scores = (
                    TestAttempt.objects.filter(student=user, finished_at__isnull=False)
                    .values('test__subject__name')
                    .annotate(avg_pct=Avg('percentage'))
                )
                strong = []
                weak = []
                for s in subject_scores:
                    name = s['test__subject__name']
                    avg = s['avg_pct'] or 0
                    if avg >= 75:
                        strong.append(name)
                    elif avg < 50:
                        weak.append(name)
                profile.strong_topics = strong or None
                profile.weak_topics = weak or None

                profile.save()
    except IntegrityError:
        existing = TestAttempt.objects.filter(test=test, student=user, finished_at__isnull=False).first()
        return JsonResponse({'error': 'already submitted', 'attempt_id': getattr(existing, 'id', None)}, status=400)

    return JsonResponse({
        'success': True,
        'attempt_id': attempt.id,
        'score': total_score,
        'max_score': max_score,
        'percentage': round(percentage, 1),
    })


def test_result(request, attempt_id):
    """View test result with answers."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    try:
        attempt = TestAttempt.objects.select_related('test__subject', 'student').get(id=attempt_id)
    except TestAttempt.DoesNotExist:
        return redirect('test_list')
    # Only the student or the test's teacher can view
    if attempt.student != user and attempt.test.teacher != user and not user.is_admin:
        return redirect('test_list')
    ctx['user'] = user
    ctx['attempt'] = attempt
    answers = list(attempt.answers.select_related('question').all())
    # Resolve letter-based correct answers to actual option text
    for a in answers:
        q = a.question
        if q.question_type == 'choice' and q.options and len(q.correct_answer.strip()) <= 2:
            try:
                idx = ord(q.correct_answer.strip().upper()) - 65
                if 0 <= idx < len(q.options):
                    a.correct_answer_text = q.options[idx]
                else:
                    a.correct_answer_text = q.correct_answer
            except (TypeError, ValueError):
                a.correct_answer_text = q.correct_answer
        else:
            a.correct_answer_text = q.correct_answer
    ctx['answers'] = answers
    return render(request, 'core/test_result.html', ctx)


# ── Assignment System ────────────────────────────────────

def assignment_list(request):
    """Browse assignments."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()
    if user.is_teacher:
        qs_t = Assignment.objects.filter(teacher=user).select_related('subject')
        ctx['page_obj'] = _paginate(request, qs_t, per_page=20)
        ctx['assignments'] = ctx['page_obj']
    else:
        qs = Assignment.objects.filter(is_published=True).select_related('subject', 'teacher')
        subject_filter = request.GET.get('subject')
        if subject_filter:
            qs = qs.filter(subject_id=subject_filter)
        ctx['page_obj'] = _paginate(request, qs, per_page=20)
        ctx['assignments'] = ctx['page_obj']
        # Student submissions
        ctx['my_submissions'] = {
            s.assignment_id: s
            for s in AssignmentSubmission.objects.filter(student=user)
        }
    return render(request, 'core/assignment_list.html', ctx)


def assignment_create(request):
    """Create an assignment (teacher)."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return redirect('login')
    ctx['user'] = user
    ctx['subjects'] = Subject.objects.all()

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        subject_id = request.POST.get('subject_id')
        grade = request.POST.get('grade_level', '5')
        max_score = request.POST.get('max_score', '100')
        due_date_str = request.POST.get('due_date', '').strip()

        if not title or not description:
            ctx['errors'] = ['Title and description required']
            ctx['form'] = request.POST
            return render(request, 'core/assignment_edit.html', ctx)

        subject = None
        if subject_id:
            try:
                subject = Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist:
                pass
        if not subject:
            subject = Subject.objects.first()
        if not subject:
            ctx['errors'] = ['No subjects']
            return render(request, 'core/assignment_edit.html', ctx)

        due_date = None
        if due_date_str:
            try:
                due_date = timezone.make_aware(datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M'))
            except (ValueError, TypeError):
                pass

        assignment = Assignment.objects.create(
            subject=subject, teacher=user, title=title,
            description=description,
            grade_level=int(grade) if grade.isdigit() else 5,
            max_score=int(max_score) if max_score.isdigit() else 100,
            due_date=due_date,
            is_published=request.POST.get('is_published') == 'on',
        )
        attachment = request.FILES.get('attachment')
        if attachment:
            err = _validate_upload(attachment)
            if err:
                ctx['errors'] = [err]
                return render(request, 'core/assignment_edit.html', ctx)
            assignment.attachment = attachment
            assignment.attachment_name = attachment.name
            assignment.save(update_fields=['attachment', 'attachment_name'])
        return redirect('assignment_detail', assignment_id=assignment.id)

    return render(request, 'core/assignment_edit.html', ctx)


def assignment_edit(request, assignment_id):
    """Edit assignment (teacher)."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return redirect('login')
    try:
        assignment = Assignment.objects.get(id=assignment_id, teacher=user)
    except Assignment.DoesNotExist:
        return redirect('assignment_list')
    ctx['user'] = user
    ctx['assignment'] = assignment
    ctx['subjects'] = Subject.objects.all()
    ctx['editing'] = True

    if request.method == 'POST':
        assignment.title = request.POST.get('title', '').strip()
        assignment.description = request.POST.get('description', '').strip()
        subject_id = request.POST.get('subject_id')
        if subject_id:
            try:
                assignment.subject = Subject.objects.get(id=subject_id)
            except Subject.DoesNotExist:
                pass
        try:
            assignment.grade_level = int(request.POST.get('grade_level', '5'))
        except (ValueError, TypeError):
            pass
        try:
            assignment.max_score = int(request.POST.get('max_score', '100'))
        except (ValueError, TypeError):
            pass
        due_date_str = request.POST.get('due_date', '').strip()
        if due_date_str:
            try:
                assignment.due_date = timezone.make_aware(datetime.strptime(due_date_str, '%Y-%m-%dT%H:%M'))
            except (ValueError, TypeError):
                pass
        assignment.is_published = request.POST.get('is_published') == 'on'
        attachment = request.FILES.get('attachment')
        if attachment:
            err = _validate_upload(attachment)
            if err:
                ctx['errors'] = [err]
                return render(request, 'core/assignment_edit.html', ctx)
            assignment.attachment = attachment
            assignment.attachment_name = attachment.name
        assignment.save()
        ctx['success'] = 'Saved!'
        ctx['assignment'] = assignment
    return render(request, 'core/assignment_edit.html', ctx)


def assignment_detail(request, assignment_id):
    """View assignment detail + submit (student) or view submissions (teacher)."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    try:
        assignment = Assignment.objects.select_related('subject', 'teacher').get(id=assignment_id)
    except Assignment.DoesNotExist:
        return redirect('assignment_list')
    # Access control: teacher (owner) or students (if published)
    if user == assignment.teacher:
        pass  # owner can always access
    elif not assignment.is_published:
        return redirect('assignment_list')
    ctx['user'] = user
    ctx['assignment'] = assignment
    ctx['is_owner'] = user == assignment.teacher

    if user.is_teacher and user == assignment.teacher:
        ctx['submissions'] = assignment.submissions.select_related('student').all()
    elif user.is_student:
        try:
            ctx['my_submission'] = AssignmentSubmission.objects.get(
                assignment=assignment, student=user
            )
        except AssignmentSubmission.DoesNotExist:
            ctx['my_submission'] = None

    # Student submit (use get_or_create to prevent race condition on double-click)
    if request.method == 'POST' and user.is_student:
        text = request.POST.get('text', '').strip()
        sub_files = request.FILES.getlist('files')
        if not text and not sub_files:
            ctx['error'] = 'Submit text or file'
        else:
            try:
                sub, created = AssignmentSubmission.objects.get_or_create(
                    assignment=assignment, student=user,
                    defaults={'text': text}
                )
                if not created:
                    ctx['error'] = 'Already submitted'
                else:
                    for f in sub_files:
                        err = _validate_upload(f)
                        if err:
                            ctx['error'] = err
                            break
                        SubmissionFile.objects.create(
                            submission=sub, file=f, file_name=f.name
                        )
                    ctx['my_submission'] = sub
                    if not ctx.get('error'):
                        ctx['success'] = 'Submitted!'
            except IntegrityError:
                ctx['error'] = 'Already submitted'

    return render(request, 'core/assignment_detail.html', ctx)


@require_POST
def api_assignment_grade(request, submission_id):
    """Grade a student submission (teacher only)."""
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        sub = AssignmentSubmission.objects.select_related('assignment').get(id=submission_id)
    except AssignmentSubmission.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    if sub.assignment.teacher != user:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'invalid'}, status=400)
    score = data.get('score')
    comment = data.get('comment', '').strip()
    if score is not None:
        try:
            sub.score = max(0, min(sub.assignment.max_score, float(score)))
        except (ValueError, TypeError):
            return JsonResponse({'error': 'invalid score'}, status=400)
    sub.teacher_comment = comment
    sub.status = 'graded'
    sub.graded_at = timezone.now()
    sub.save()
    return JsonResponse({'success': True, 'score': sub.score, 'status': sub.status})


@require_POST
def api_assignment_delete(request, assignment_id):
    """Delete assignment (teacher)."""
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        assignment = Assignment.objects.get(id=assignment_id, teacher=user)
    except Assignment.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    assignment.delete()
    return JsonResponse({'success': True})


# ── Chat History API (per-user, DB-backed) ───────────────

def api_chat_history(request):
    """Get user's chat sessions from DB."""
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': 'auth'}, status=401)
    messages = ChatMessage.objects.filter(user=user).order_by('created_at')[:200]
    # Group into sessions by session_key
    sessions = {}
    for m in messages:
        key = m.session_key or 'default'
        if key not in sessions:
            sessions[key] = {'id': key, 'title': '', 'messages': []}
        sessions[key]['messages'].append({'role': m.role, 'text': m.content})
        if not sessions[key]['title'] and m.role == 'user':
            sessions[key]['title'] = m.content[:40]
    return JsonResponse({'sessions': list(sessions.values())})


@require_POST
def api_chat_clear(request):
    """Clear user's chat history."""
    user = _user_or_none(request)
    if not user:
        return JsonResponse({'error': 'auth'}, status=401)
    session_key = None
    try:
        data = json.loads(request.body)
        session_key = data.get('session_key')
    except Exception:
        logger.debug('api_clear_history: could not parse body')
    if session_key:
        ChatMessage.objects.filter(user=user, session_key=session_key).delete()
    else:
        ChatMessage.objects.filter(user=user).delete()
    return JsonResponse({'success': True})


# ── Student Results Page ─────────────────────────────────

def my_results(request):
    """Student's or teacher's results overview."""
    ctx = _ctx(request)
    user = _user_or_none(request)
    if not user:
        return redirect('login')
    ctx['user'] = user
    if user.is_student:
        ctx['attempts'] = TestAttempt.objects.filter(
            student=user
        ).select_related('test__subject')
        ctx['attempts'] = _paginate(request, ctx['attempts'], per_page=20)
        ctx['submissions'] = AssignmentSubmission.objects.filter(
            student=user
        ).select_related('assignment__subject')[:30]
        ctx['essays'] = Essay.objects.filter(student=user).select_related('subject')[:20]
    elif user.is_teacher:
        ctx['test_attempts'] = TestAttempt.objects.filter(
            test__teacher=user
        ).select_related('test__subject', 'student')
        ctx['test_attempts'] = _paginate(request, ctx['test_attempts'], per_page=30)
        ctx['submissions'] = AssignmentSubmission.objects.filter(
            assignment__teacher=user
        ).select_related('assignment__subject', 'student')[:50]
    return render(request, 'core/results.html', ctx)


# ── Organization Setup (Master Key) ─────────────────────

def org_setup(request):
    """School admin activation via master key."""
    ctx = _ctx(request)
    if request.session.get('user_id'):
        return redirect('dashboard')

    if request.method == 'POST':
        t = ctx['t']
        # Rate limit: max 5 attempts per IP per hour
        blocked, _ = _rate_check(request, 'org_setup_rate', limit=5, period=3600)
        if blocked:
            ctx['errors'] = [t.get('err_too_many_attempts', 'Слишком много попыток. Подождите.')]
            return render(request, 'core/org_setup.html', ctx)

        master_key = request.POST.get('master_key', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password_confirm', '')

        errors = []

        # Validate key
        try:
            key_obj = OrganizationKey.objects.select_related('organization').get(
                key=master_key, key_type='master', is_used=False
            )
        except OrganizationKey.DoesNotExist:
            errors.append(t.get('err_invalid_key', 'Недействительный или использованный ключ'))
            key_obj = None

        if len(username) < 3:
            errors.append(t.get('err_name_min_3', 'Имя минимум 3 символа'))
        if not email or '@' not in email:
            errors.append(t.get('err_invalid_email', 'Некорректный email'))
        if len(password) < 6:
            errors.append(t.get('err_password_min_6', 'Пароль минимум 6 символов'))
        if password != password2:
            errors.append(t.get('err_passwords_mismatch', 'Пароли не совпадают'))
        if EduUser.objects.filter(username=username).exists():
            errors.append(t.get('err_name_taken', 'Имя занято'))
        if EduUser.objects.filter(email=email).exists():
            errors.append(t.get('err_email_taken', 'Email уже зарегистрирован'))

        if errors:
            ctx['errors'] = errors
            ctx['master_key'] = master_key
            ctx['username'] = username
            ctx['email'] = email
            ctx['first_name'] = first_name
            ctx['last_name'] = last_name
            ctx['active_tab'] = 'school'
        else:
            user = EduUser.create_user(
                username=username, email=email, password=password,
                role='school_admin', first_name=first_name, last_name=last_name,
                organization=key_obj.organization,
            )
            AccessibilityProfile.objects.create(user=user)
            key_obj.is_used = True
            key_obj.used_by = user
            key_obj.used_at = timezone.now()
            key_obj.save()
            _login_session(request, user)
            return redirect('admin_panel')

    return render(request, 'core/signup.html', ctx)


def teacher_signup(request):
    """Teacher registration via invitation key from school admin."""
    ctx = _ctx(request)
    if request.session.get('user_id'):
        return redirect('dashboard')

    if request.method == 'POST':
        t = ctx['t']
        # Rate limit: max 5 attempts per IP per hour
        blocked, _ = _rate_check(request, 'teacher_signup_rate', limit=5, period=3600)
        if blocked:
            ctx['errors'] = [t.get('err_too_many_attempts', 'Слишком много попыток. Подождите.')]
            return render(request, 'core/teacher_signup.html', ctx)

        teacher_key = request.POST.get('teacher_key', '').strip()
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        patronymic = request.POST.get('patronymic', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password_confirm', '')

        errors = []

        try:
            key_obj = OrganizationKey.objects.select_related('organization', 'subject').get(
                key=teacher_key, key_type='teacher', is_used=False
            )
        except OrganizationKey.DoesNotExist:
            errors.append(t.get('err_invalid_key', 'Недействительный или использованный ключ'))
            key_obj = None

        if len(username) < 3:
            errors.append(t.get('err_name_min_3', 'Имя минимум 3 символа'))
        if not email or '@' not in email:
            errors.append(t.get('err_invalid_email', 'Некорректный email'))
        if len(password) < 6:
            errors.append(t.get('err_password_min_6', 'Пароль минимум 6 символов'))
        if password != password2:
            errors.append(t.get('err_passwords_mismatch', 'Пароли не совпадают'))
        if EduUser.objects.filter(username=username).exists():
            errors.append(t.get('err_name_taken', 'Имя занято'))
        if EduUser.objects.filter(email=email).exists():
            errors.append(t.get('err_email_taken', 'Email уже зарегистрирован'))

        if errors:
            ctx['errors'] = errors
            ctx['teacher_key'] = teacher_key
            ctx['username'] = username
            ctx['email'] = email
            ctx['first_name'] = first_name
            ctx['last_name'] = last_name
            ctx['patronymic'] = patronymic
            ctx['active_tab'] = 'teacher'
        else:
            user = EduUser.create_user(
                username=username, email=email, password=password,
                role='teacher', first_name=first_name, last_name=last_name,
                patronymic=patronymic, organization=key_obj.organization,
            )
            AccessibilityProfile.objects.create(user=user)
            key_obj.is_used = True
            key_obj.used_by = user
            key_obj.used_at = timezone.now()
            key_obj.save()
            _login_session(request, user)
            return redirect('dashboard')

    return render(request, 'core/signup.html', ctx)


# ── School Admin API ─────────────────────────────────────

@require_POST
def api_school_generate_key(request):
    """School admin generates a teacher or student invitation key."""
    user = _user_or_none(request)
    if not user or not user.is_school_admin or not user.organization:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    key_type = data.get('key_type', 'teacher')
    if key_type not in ('teacher', 'student'):
        return JsonResponse({'error': 'invalid key_type'}, status=400)

    subject_id = data.get('subject_id')
    grades = (data.get('grades') or '').strip()

    subject = None
    if subject_id and key_type == 'teacher':
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            pass

    key_qs = OrganizationKey.objects.filter(
        organization=user.organization, key_type=key_type, is_used=False
    )
    if key_qs.count() >= 50:
        t = get_translations(_lang(request))
        return JsonResponse({'error': t.get('err_too_many_keys', 'Too many unused keys')}, status=400)

    key_obj = OrganizationKey.objects.create(
        organization=user.organization,
        key_type=key_type,
        subject=subject,
        grades=grades if key_type == 'teacher' else '',
    )
    return JsonResponse({
        'success': True,
        'key': key_obj.key,
        'key_type': key_type,
        'subject': subject.name if subject else '',
        'grades': grades if key_type == 'teacher' else '',
    })


@require_POST
def api_school_revoke_key(request):
    """School admin revokes an unused teacher key."""
    user = _user_or_none(request)
    if not user or not user.is_school_admin or not user.organization:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    key_id = data.get('key_id')
    try:
        key_obj = OrganizationKey.objects.get(
            id=key_id, organization=user.organization, is_used=False
        )
        key_obj.delete()
        return JsonResponse({'success': True})
    except OrganizationKey.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)


@require_POST
def api_admin_create_org(request):
    """Platform admin creates a new organization + master key."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    name = (data.get('name') or '').strip()
    address = (data.get('address') or '').strip()
    contact_email = (data.get('contact_email') or '').strip()

    if not name:
        t = get_translations(_lang(request))
        return JsonResponse({'error': t.get('err_enter_org_name', 'Enter organization name')}, status=400)

    org = Organization.objects.create(name=name, address=address, contact_email=contact_email)
    master_key = OrganizationKey.objects.create(organization=org, key_type='master')

    return JsonResponse({
        'success': True,
        'org_id': org.id,
        'org_name': org.name,
        'master_key': master_key.key,
    })


@require_POST
def api_admin_edit_org(request):
    """Platform admin edits an organization."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    org_id = data.get('org_id')
    try:
        org = Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)

    name = (data.get('name') or '').strip()
    if not name:
        t = get_translations(_lang(request))
        return JsonResponse({'error': t.get('err_enter_name', 'Enter name')}, status=400)
    org.name = name
    org.address = (data.get('address') or '').strip()
    org.contact_email = (data.get('contact_email') or '').strip()
    org.is_active = bool(data.get('is_active', True))
    org.save()
    return JsonResponse({'success': True})


@require_POST
def api_admin_delete_org(request):
    """Platform admin deletes an organization (cascade)."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    org_id = data.get('org_id')
    try:
        org = Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)

    # Unbind members before deleting
    org.members.update(organization=None)
    org.delete()
    return JsonResponse({'success': True})


@require_POST
def api_admin_regen_master_key(request):
    """Platform admin regenerates master key for an organization."""
    user = _user_or_none(request)
    if not user or not user.is_admin:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    org_id = data.get('org_id')
    try:
        org = Organization.objects.get(id=org_id)
    except Organization.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)

    # Revoke all unused master keys
    OrganizationKey.objects.filter(organization=org, key_type='master', is_used=False).delete()
    new_key = OrganizationKey.objects.create(organization=org, key_type='master')
    return JsonResponse({'success': True, 'key': new_key.key})


# ── Teacher Manual Essay Review ──────────────────────────

@require_POST
def api_essay_teacher_review(request):
    """Teacher manually reviews/overrides an essay score."""
    user = _user_or_none(request)
    if not user or not user.is_teacher:
        return JsonResponse({'error': 'forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    essay_id = data.get('essay_id')
    try:
        essay = Essay.objects.select_related('student').get(id=essay_id)
    except Essay.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    # Authorization: teacher can only review essays from students in their org
    if user.organization and essay.student and essay.student.organization_id != user.organization_id:
        return JsonResponse({'error': 'forbidden'}, status=403)

    score = data.get('score')
    comment = (data.get('comment') or '').strip()

    if score is not None:
        try:
            essay.score = max(0, min(100, float(score)))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'invalid score'}, status=400)

    if comment:
        essay.recommendations = comment
    essay.is_checked = True
    essay.checked_at = timezone.now()
    essay.save()

    return JsonResponse({'success': True, 'score': essay.score})

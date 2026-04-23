"""Модель пользователя EduAI."""
import uuid
from pathlib import PurePosixPath

from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone


def _avatar_path(instance, filename):
    ext = PurePosixPath(filename).suffix.lower() or '.jpg'
    short_uuid = uuid.uuid4().hex[:8]
    user_id = instance.pk or 'new'
    return f'avatars/{user_id}_{short_uuid}{ext}'


class EduUser(models.Model):
    ROLE_CHOICES = [
        ('student', 'Ученик'),
        ('teacher', 'Преподаватель'),
        ('school_admin', 'Администратор школы'),
        ('admin', 'Администратор платформы'),
    ]
    username = models.CharField(max_length=50, unique=True)
    email = models.EmailField(unique=True)
    password_hash = models.CharField(max_length=128)
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)
    patronymic = models.CharField('Отчество', max_length=50, blank=True)
    avatar = models.ImageField(upload_to=_avatar_path, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    role = models.CharField(max_length=20, default='student', choices=ROLE_CHOICES)
    organization = models.ForeignKey(
        'Organization', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='members',
    )
    grade = models.PositiveSmallIntegerField('Класс', null=True, blank=True)
    language = models.CharField(max_length=5, default='ru', choices=[('ru', 'RU'), ('en', 'EN'), ('kk', 'KZ')])
    theme = models.CharField(max_length=10, default='light', choices=[('dark', 'Тёмная'), ('light', 'Светлая')])
    # TTS preferences (set once in profile, used everywhere)
    tts_voice = models.CharField('TTS голос', max_length=80, blank=True, default='')
    tts_speed = models.SmallIntegerField('TTS скорость (%)', default=0)
    tts_volume = models.PositiveSmallIntegerField('TTS громкость', default=100)
    tz = models.CharField('Часовой пояс', max_length=40, default='Asia/Almaty')
    ai_requests_today = models.PositiveSmallIntegerField('Запросы ИИ сегодня', default=0)
    ai_requests_date = models.DateField('Дата счётчика ИИ', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = 'eduai_users'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.get_role_display()})'

    def set_password(self, raw):
        self.password_hash = make_password(raw)

    def check_password(self, raw):
        return check_password(raw, self.password_hash)

    def _upgrade_hash_if_needed(self, raw_password):
        """Re-hash password if the current hash uses an outdated algorithm."""
        from django.contrib.auth.hashers import identify_hasher
        try:
            hasher = identify_hasher(self.password_hash)
            if hasher.must_update(self.password_hash):
                self.set_password(raw_password)
                self.save(update_fields=['password_hash'])
        except ValueError:
            pass

    def update_last_login(self):
        self.last_login = timezone.now()
        self.save(update_fields=['last_login'])

    @property
    def full_name(self):
        parts = [self.first_name, self.last_name]
        name = ' '.join(p for p in parts if p)
        return name or self.username

    @property
    def is_student(self):
        return self.role == 'student'

    @property
    def is_teacher(self):
        return self.role == 'teacher'

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_school_admin(self):
        return self.role == 'school_admin'

    @classmethod
    def create_user(cls, username, email, password, **extra):
        user = cls(username=username, email=email, **extra)
        user.set_password(password)
        user.save()
        return user

    @classmethod
    def authenticate(cls, email=None, username=None, password=None):
        try:
            user = cls.objects.get(email=email) if email else cls.objects.get(username=username)
            if user.check_password(password) and user.is_active:
                user._upgrade_hash_if_needed(password)
                user.update_last_login()
                return user
        except cls.DoesNotExist:
            pass
        return None


class AccessibilityProfile(models.Model):
    """Профиль доступности для инклюзивного обучения."""
    NEED_CHOICES = [
        ('none', 'Без особенностей'),
        ('vision', 'Слабое зрение'),
        ('cognitive', 'Когнитивные особенности'),
        ('dyslexia', 'Дислексия'),
        ('hearing', 'Слабый слух'),
    ]
    FONT_CHOICES = [
        ('default', 'Inter (стандартный)'),
        ('opendyslexic', 'OpenDyslexic'),
        ('comfortaa', 'Comfortaa'),
        ('ptsans', 'PT Sans'),
        ('pangolin', 'Pangolin'),
        ('arial', 'Arial'),
        ('verdana', 'Verdana'),
        ('georgia', 'Georgia'),
        ('times', 'Times New Roman'),
        ('courier', 'Courier New'),
    ]
    user = models.OneToOneField(EduUser, on_delete=models.CASCADE, related_name='accessibility')
    primary_need = models.CharField('Основная потребность', max_length=20,
                                     choices=NEED_CHOICES, default='none')
    font_size = models.PositiveSmallIntegerField('Размер шрифта', default=16)
    font_family = models.CharField('Шрифт', max_length=20, choices=FONT_CHOICES, default='default')
    high_contrast = models.BooleanField('Высокий контраст', default=False)
    text_to_speech = models.BooleanField('Озвучка текста', default=False)
    easy_read = models.BooleanField('Упрощённый текст', default=False)
    visual_aids = models.BooleanField('Визуальные опоры', default=False)
    zen_mode = models.BooleanField('Дзен-режим (СДВГ)', default=False)
    voice_input = models.BooleanField('Голосовой ввод', default=False)

    class Meta:
        db_table = 'eduai_accessibility'

    def __str__(self):
        return f'{self.user.username} — {self.get_primary_need_display()}'

"""Организации (школы) и ключи приглашений."""
import secrets

from django.db import models
from django.utils import timezone


def _generate_key():
    return secrets.token_urlsafe(24)


class Organization(models.Model):
    """Школа / лицей / учебное учреждение."""
    name = models.CharField('Название', max_length=200)
    address = models.CharField('Адрес', max_length=300, blank=True)
    contact_email = models.EmailField('Email', blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'eduai_organizations'
        ordering = ['name']

    def __str__(self):
        return self.name


class OrganizationKey(models.Model):
    """Мастер-ключ для активации организации (выдаётся суперадмином)."""
    KEY_TYPES = [
        ('master', 'Мастер-ключ (для школьного админа)'),
        ('teacher', 'Ключ учителя'),
        ('student', 'Ключ ученика'),
    ]
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE,
                                      related_name='keys')
    key = models.CharField('Ключ', max_length=64, unique=True, default=_generate_key)
    key_type = models.CharField('Тип', max_length=10, choices=KEY_TYPES, default='teacher')
    subject = models.ForeignKey('Subject', on_delete=models.SET_NULL, null=True, blank=True,
                                 help_text='Предмет учителя (только для teacher-ключей)')
    grades = models.CharField('Классы', max_length=50, blank=True,
                               help_text='Список классов через запятую, напр. 5,6,7')
    used_by = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='used_keys')
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'eduai_org_keys'
        ordering = ['-created_at']

    def __str__(self):
        status = '✓' if self.is_used else '—'
        return f'{self.get_key_type_display()} [{self.key[:8]}…] {status}'

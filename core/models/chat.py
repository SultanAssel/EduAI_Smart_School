from django.db import models
from django.utils import timezone

from .user import EduUser


class ChatMessage(models.Model):
    """История чата ИИ-ассистента."""
    user = models.ForeignKey(EduUser, on_delete=models.CASCADE, related_name='messages', null=True, blank=True)
    session_key = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=10, choices=[('user', 'User'), ('assistant', 'Assistant')])
    content = models.TextField()
    context = models.CharField('Контекст', max_length=30, blank=True, default='general',
                                help_text='general, lesson, test, essay')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'eduai_chat_messages'
        ordering = ['created_at']

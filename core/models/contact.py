from django.db import models
from django.utils import timezone


class ContactMessage(models.Model):
    """Сообщение из контактной формы на сайте."""

    CATEGORY_CHOICES = [
        ('general', 'Общий вопрос / General'),
        ('support', 'Техподдержка / Support'),
        ('bug', 'Ошибка / Bug Report'),
        ('feature', 'Предложение / Feature Request'),
        ('partnership', 'Сотрудничество / Partnership'),
        ('sales', 'Продажи / Sales'),
    ]

    name = models.CharField(max_length=100)
    email = models.EmailField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='general')
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False, verbose_name='Решено')
    admin_reply = models.TextField(blank=True, default='', verbose_name='Ответ администратора')
    replied_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата ответа')

    class Meta:
        db_table = 'eduai_contact_messages'
        ordering = ['-created_at']

    def __str__(self):
        return f'[{self.category}] {self.subject} — {self.name}'

"""Персонализация — профиль обучения и траектории."""
from django.db import models
from django.utils import timezone


class LearningProfile(models.Model):
    """Профиль обучения ученика — отслеживание прогресса и персонализация."""
    student = models.OneToOneField('EduUser', on_delete=models.CASCADE, related_name='learning_profile')
    interests = models.JSONField('Интересы', blank=True, null=True,
                                  help_text='["Minecraft","физика","робототехника"]')
    strong_topics = models.JSONField('Сильные темы', blank=True, null=True)
    weak_topics = models.JSONField('Слабые темы', blank=True, null=True)
    learning_style = models.CharField('Стиль обучения', max_length=20, default='balanced',
                                       choices=[
                                           ('visual', 'Визуалист'),
                                           ('auditory', 'Аудиалист'),
                                           ('kinesthetic', 'Кинестетик'),
                                           ('balanced', 'Смешанный'),
                                       ])
    difficulty_level = models.CharField('Уровень сложности', max_length=15, default='medium',
                                         choices=[
                                             ('easy', 'Лёгкий'),
                                             ('medium', 'Средний'),
                                             ('hard', 'Сложный'),
                                             ('adaptive', 'Адаптивный'),
                                         ])
    total_tests_taken = models.PositiveIntegerField('Тестов пройдено', default=0)
    avg_score = models.FloatField('Средний балл', default=0)
    streak_days = models.PositiveSmallIntegerField('Дней подряд', default=0)
    last_activity = models.DateTimeField('Последняя активность', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'eduai_learning_profiles'

    def __str__(self):
        return f'Профиль: {self.student.username}'

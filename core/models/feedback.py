"""Эссе и проверка открытых ответов (Feedback Loop)."""
from django.db import models
from django.utils import timezone


class Essay(models.Model):
    """Эссе / развернутый ответ ученика."""
    student = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True,
                                 related_name='essays')
    subject = models.ForeignKey('Subject', on_delete=models.PROTECT, related_name='essays')
    title = models.CharField('Тема', max_length=200)
    content = models.TextField('Текст эссе')
    # Результаты ИИ-анализа
    is_checked = models.BooleanField('Проверено', default=False)
    score = models.FloatField('Оценка (0-100)', null=True, blank=True)
    logic_score = models.FloatField('Логика', null=True, blank=True)
    structure_score = models.FloatField('Структура', null=True, blank=True)
    argumentation_score = models.FloatField('Аргументация', null=True, blank=True)
    strengths = models.TextField('Сильные стороны', blank=True)
    weaknesses = models.TextField('Слабые стороны', blank=True)
    recommendations = models.TextField('Рекомендации', blank=True)
    materials_to_review = models.JSONField('Материалы для повторения', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'eduai_essays'
        ordering = ['-created_at']

    def __str__(self):
        name = self.student.username if self.student else '—'
        return f'{name}: {self.title}'


class ClassReport(models.Model):
    """Сводный отчет по классу (для преподавателя)."""
    teacher = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True,
                                  related_name='class_reports')
    subject = models.ForeignKey('Subject', on_delete=models.PROTECT, related_name='class_reports')
    grade_level = models.PositiveSmallIntegerField('Класс')
    report_text = models.TextField('Текст отчёта')
    problem_topics = models.JSONField('Проблемные темы', blank=True, null=True)
    recommendations = models.TextField('Рекомендации', blank=True)
    student_count = models.PositiveSmallIntegerField('Кол-во учеников', default=0)
    avg_score = models.FloatField('Средний балл', default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'eduai_class_reports'
        ordering = ['-created_at']

    def __str__(self):
        return f'Отчёт: {self.subject.name} {self.grade_level} класс'

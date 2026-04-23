"""Тесты и задания — генерация и прохождение."""
from django.db import models
from django.utils import timezone


class Test(models.Model):
    """Сгенерированный тест / контрольная."""
    lesson = models.ForeignKey('Lesson', on_delete=models.SET_NULL, related_name='tests',
                                null=True, blank=True)
    subject = models.ForeignKey('Subject', on_delete=models.PROTECT, related_name='tests')
    teacher = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True,
                                 related_name='created_tests')
    title = models.CharField('Название', max_length=200)
    variant = models.CharField('Вариант', max_length=5, default='А')
    grade_level = models.PositiveSmallIntegerField('Класс', default=5)
    criteria = models.TextField('Критерии оценивания', blank=True)
    source_text = models.TextField('Исходный текст для генерации', blank=True)
    time_limit = models.PositiveSmallIntegerField('Время (мин)', default=45)
    is_published = models.BooleanField('Опубликован', default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'eduai_tests'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} (вар. {self.variant})'

    @property
    def question_count(self):
        return self.questions.count()


class TestQuestion(models.Model):
    """Вопрос теста."""
    TYPE_CHOICES = [
        ('choice', 'С вариантами ответа'),
        ('text', 'Открытый ответ'),
        ('truefalse', 'Верно/Неверно'),
    ]
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField('Текст вопроса')
    question_type = models.CharField('Тип', max_length=15, choices=TYPE_CHOICES, default='choice')
    options = models.JSONField('Варианты ответа', blank=True, null=True,
                                help_text='["вариант1","вариант2","вариант3","вариант4"]')
    correct_answer = models.TextField('Правильный ответ')
    points = models.PositiveSmallIntegerField('Баллы', default=1)
    explanation = models.TextField('Пояснение к ответу', blank=True)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        db_table = 'eduai_test_questions'
        ordering = ['order']

    def __str__(self):
        return f'Q{self.order}: {self.question_text[:50]}'


class TestAttempt(models.Model):
    """Попытка прохождения теста учеником."""
    test = models.ForeignKey(Test, on_delete=models.CASCADE, related_name='attempts')
    student = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True,
                                 related_name='test_attempts')
    score = models.FloatField('Баллы', default=0)
    max_score = models.FloatField('Макс. баллов', default=0)
    percentage = models.FloatField('Процент', default=0)
    feedback = models.TextField('Обратная связь ИИ', blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'eduai_test_attempts'
        ordering = ['-started_at']

    def __str__(self):
        name = self.student.username if self.student else '—'
        return f'{name} — {self.test.title}: {self.percentage:.0f}%'


class StudentAnswer(models.Model):
    """Ответ ученика на вопрос теста."""
    attempt = models.ForeignKey(TestAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField('Ответ ученика')
    is_correct = models.BooleanField('Правильно', default=False)
    points_earned = models.FloatField('Баллы', default=0)
    ai_feedback = models.TextField('Комментарий ИИ', blank=True)

    class Meta:
        db_table = 'eduai_student_answers'

    def __str__(self):
        return f'{"✓" if self.is_correct else "✗"} {self.answer_text[:40]}'

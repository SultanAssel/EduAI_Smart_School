"""Учебные материалы и предметы."""
import uuid
from pathlib import PurePosixPath

from django.db import models
from django.utils import timezone


class Subject(models.Model):
    """Учебный предмет."""
    name = models.CharField('Название (рус)', max_length=100)
    name_en = models.CharField('Название (англ)', max_length=100, blank=True)
    name_kk = models.CharField('Название (каз)', max_length=100, blank=True)
    icon = models.CharField('Иконка (emoji)', max_length=10, default='📚')
    color = models.CharField('Цвет', max_length=20, default='#6366f1')
    description = models.TextField('Описание', blank=True)
    order = models.PositiveSmallIntegerField('Порядок', default=0)

    class Meta:
        db_table = 'eduai_subjects'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name

    def get_name(self, lang='ru'):
        """Возвращает название предмета на указанном языке."""
        if lang == 'en' and self.name_en:
            return self.name_en
        if lang == 'kk' and self.name_kk:
            return self.name_kk
        return self.name


def _lesson_file_path(instance, filename):
    ext = PurePosixPath(filename).suffix.lower()
    short_uuid = uuid.uuid4().hex[:8]
    return f'lessons/{instance.pk or "new"}_{short_uuid}{ext}'


def _assignment_file_path(instance, filename):
    ext = PurePosixPath(filename).suffix.lower()
    short_uuid = uuid.uuid4().hex[:8]
    return f'assignments/{instance.pk or "new"}_{short_uuid}{ext}'


def _submission_file_path(instance, filename):
    ext = PurePosixPath(filename).suffix.lower()
    short_uuid = uuid.uuid4().hex[:8]
    return f'submissions/{instance.assignment_id}_{instance.student_id}_{short_uuid}{ext}'


class Lesson(models.Model):
    """Урок / учебный материал."""
    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='lessons')
    teacher = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True,
                                 related_name='created_lessons')
    title = models.CharField('Тема', max_length=200)
    content = models.TextField('Текст урока')
    grade_level = models.PositiveSmallIntegerField('Класс', default=5)
    is_published = models.BooleanField('Опубликован', default=True)
    # File attachment (PDF, DOCX, etc.)
    attachment = models.FileField('Файл', upload_to=_lesson_file_path, blank=True, null=True)
    attachment_name = models.CharField('Имя файла', max_length=200, blank=True)
    # ИИ-адаптации
    easy_read_content = models.TextField('Упрощённый текст', blank=True,
                                          help_text='Автоматически сгенерированная версия easy-to-read')
    audio_url = models.URLField('Ссылка на аудио', blank=True)
    mindmap_data = models.JSONField('Данные майнд-мапа', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'eduai_lessons'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.subject.name}: {self.title}'


class Assignment(models.Model):
    """Задание от учителя для учеников."""
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='assignments')
    teacher = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True,
                                 related_name='created_assignments')
    title = models.CharField('Название', max_length=200)
    description = models.TextField('Описание задания')
    grade_level = models.PositiveSmallIntegerField('Класс', default=5)
    max_score = models.PositiveSmallIntegerField('Макс. баллов', default=100)
    due_date = models.DateTimeField('Крайний срок', null=True, blank=True)
    attachment = models.FileField('Файл', upload_to=_assignment_file_path, blank=True, null=True)
    attachment_name = models.CharField('Имя файла', max_length=200, blank=True)
    is_published = models.BooleanField('Опубликовано', default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'eduai_assignments'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def submission_count(self):
        return self.submissions.count()


class AssignmentSubmission(models.Model):
    """Сдача задания учеником."""
    STATUS_CHOICES = [
        ('submitted', 'Сдано'),
        ('graded', 'Оценено'),
        ('returned', 'Возвращено'),
    ]
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey('EduUser', on_delete=models.SET_NULL, null=True,
                                 related_name='submissions')
    text = models.TextField('Текст ответа', blank=True)
    file = models.FileField('Файл', upload_to=_submission_file_path, blank=True, null=True)
    file_name = models.CharField('Имя файла', max_length=200, blank=True)
    status = models.CharField('Статус', max_length=15, choices=STATUS_CHOICES, default='submitted')
    score = models.FloatField('Баллы', null=True, blank=True)
    teacher_comment = models.TextField('Комментарий учителя', blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'eduai_submissions'
        ordering = ['-submitted_at']
        unique_together = ['assignment', 'student']

    def __str__(self):
        name = self.student.username if self.student else '—'
        return f'{name} → {self.assignment.title}'


def _submission_extra_file_path(instance, filename):
    ext = PurePosixPath(filename).suffix.lower()
    short_uuid = uuid.uuid4().hex[:8]
    return f'submissions/{instance.submission.assignment_id}_{instance.submission.student_id}_{short_uuid}{ext}'


class SubmissionFile(models.Model):
    """Individual file attached to a submission (supports multi-file upload)."""
    submission = models.ForeignKey(AssignmentSubmission, on_delete=models.CASCADE,
                                   related_name='files')
    file = models.FileField(upload_to=_submission_extra_file_path)
    file_name = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'eduai_submission_files'
        ordering = ['uploaded_at']

    def __str__(self):
        return self.file_name

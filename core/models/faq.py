from django.db import models
from django.utils import timezone


class FaqCategory(models.Model):
    """Категория FAQ."""
    name = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True)
    name_kk = models.CharField(max_length=100, blank=True)
    icon = models.CharField(max_length=50, default='❓')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'eduai_faq_categories'
        ordering = ['order']

    def __str__(self):
        return self.name

    def get_name(self, lang='ru'):
        if lang == 'en' and self.name_en:
            return self.name_en
        if lang == 'kk' and self.name_kk:
            return self.name_kk
        return self.name


class FaqQuestion(models.Model):
    """Вопрос-ответ."""
    category = models.ForeignKey(FaqCategory, on_delete=models.CASCADE, related_name='questions')
    question = models.TextField()
    question_en = models.TextField(blank=True)
    question_kk = models.TextField(blank=True)
    answer = models.TextField()
    answer_en = models.TextField(blank=True)
    answer_kk = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'eduai_faq_questions'
        ordering = ['order']

    def __str__(self):
        return self.question[:60]

    def get_question(self, lang='ru'):
        if lang == 'en' and self.question_en:
            return self.question_en
        if lang == 'kk' and self.question_kk:
            return self.question_kk
        return self.question

    def get_answer(self, lang='ru'):
        if lang == 'en' and self.answer_en:
            return self.answer_en
        if lang == 'kk' and self.answer_kk:
            return self.answer_kk
        return self.answer

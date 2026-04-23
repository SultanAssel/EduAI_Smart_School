"""Админ-панель EduAI."""
import csv
from django.contrib import admin
from django.http import HttpResponse
from django.utils import timezone
from .models import (
    EduUser, AccessibilityProfile, Subject, Lesson,
    Test, TestQuestion, TestAttempt, StudentAnswer,
    Essay, ClassReport, LearningProfile,
    FaqCategory, FaqQuestion, ChatMessage, ContactMessage,
    Organization, OrganizationKey,
)

admin.site.site_header = 'EduAI — Панель управления'
admin.site.site_title = 'EduAI Admin'
admin.site.index_title = 'Управление платформой'


# ── Inlines ──────────────────────────────────────────────

class AccessibilityInline(admin.StackedInline):
    model = AccessibilityProfile
    extra = 0

class LearningProfileInline(admin.StackedInline):
    model = LearningProfile
    extra = 0
    readonly_fields = ['total_tests_taken', 'avg_score', 'streak_days', 'last_activity', 'updated_at']

class TestQuestionInline(admin.TabularInline):
    model = TestQuestion
    extra = 1
    fields = ['order', 'question_text', 'question_type', 'options', 'correct_answer', 'points']
    ordering = ['order']

class StudentAnswerInline(admin.TabularInline):
    model = StudentAnswer
    extra = 0
    readonly_fields = ['question', 'answer_text', 'is_correct', 'points_earned', 'ai_feedback']

    def has_add_permission(self, request, obj=None):
        return False

class FaqQuestionInline(admin.StackedInline):
    model = FaqQuestion
    extra = 1
    fields = ['order', 'question', 'question_en', 'question_kk', 'answer', 'answer_en', 'answer_kk']


# ── Helpers ──────────────────────────────────────────────

def export_csv(modeladmin, request, queryset):
    """Экспорт выбранных записей в CSV."""
    meta = modeladmin.model._meta
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename={meta.db_table}.csv'
    writer = csv.writer(response)
    fields = [f.name for f in meta.fields]
    writer.writerow(fields)
    for obj in queryset.iterator():
        writer.writerow([getattr(obj, f) for f in fields])
    return response

export_csv.short_description = '📥 Экспорт в CSV'


# ── EduUser ──────────────────────────────────────────────

@admin.register(EduUser)
class EduUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'full_name_display', 'role', 'grade', 'language', 'theme', 'is_active', 'last_login', 'created_at']
    list_filter = ['role', 'is_active', 'grade', 'language', 'theme']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'patronymic']
    list_per_page = 25
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    inlines = [AccessibilityInline, LearningProfileInline]
    actions = [export_csv, 'activate_users', 'deactivate_users']
    readonly_fields = ['created_at', 'last_login', 'password_hash']

    fieldsets = (
        ('Аккаунт', {'fields': ('username', 'email', 'password_hash', 'is_active', 'role')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'patronymic', 'avatar', 'grade')}),
        ('Настройки', {'fields': ('language', 'theme')}),
        ('Даты', {'fields': ('created_at', 'last_login'), 'classes': ('collapse',)}),
    )

    @admin.display(description='Полное имя')
    def full_name_display(self, obj):
        return obj.full_name

    @admin.action(description='✅ Активировать')
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f'Активировано: {updated}')

    @admin.action(description='🚫 Деактивировать')
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'Деактивировано: {updated}')


# ── Subject ──────────────────────────────────────────────

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'name_en', 'name_kk', 'icon', 'color', 'order', 'lesson_count', 'test_count']
    list_editable = ['order', 'icon', 'color', 'name_en', 'name_kk']
    search_fields = ['name', 'name_en', 'name_kk']
    ordering = ['order', 'name']

    @admin.display(description='Уроки')
    def lesson_count(self, obj):
        return obj.lessons.count()

    @admin.display(description='Тесты')
    def test_count(self, obj):
        return obj.tests.count()


# ── Lesson ───────────────────────────────────────────────

@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'teacher', 'grade_level', 'has_audio', 'created_at', 'updated_at']
    list_filter = ['subject', 'grade_level']
    search_fields = ['title', 'content']
    date_hierarchy = 'created_at'
    list_per_page = 25
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    actions = [export_csv]

    fieldsets = (
        (None, {'fields': ('title', 'subject', 'teacher', 'grade_level')}),
        ('Контент', {'fields': ('content', 'easy_read_content', 'audio_url', 'mindmap_data')}),
        ('Даты', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    @admin.display(boolean=True, description='Аудио')
    def has_audio(self, obj):
        return bool(obj.audio_url)


# ── Test ─────────────────────────────────────────────────

@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'variant', 'grade_level', 'teacher', 'question_count_display', 'time_limit', 'is_published', 'created_at']
    list_filter = ['subject', 'grade_level', 'is_published', 'variant']
    search_fields = ['title', 'source_text']
    date_hierarchy = 'created_at'
    list_per_page = 25
    ordering = ['-created_at']
    readonly_fields = ['created_at']
    inlines = [TestQuestionInline]
    actions = [export_csv, 'publish_tests', 'unpublish_tests']

    fieldsets = (
        (None, {'fields': ('title', 'subject', 'lesson', 'teacher')}),
        ('Параметры', {'fields': ('variant', 'grade_level', 'time_limit', 'is_published')}),
        ('Содержание', {'fields': ('source_text', 'criteria'), 'classes': ('collapse',)}),
        ('Мета', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )

    @admin.display(description='Вопросов')
    def question_count_display(self, obj):
        return obj.question_count

    @admin.action(description='📢 Опубликовать')
    def publish_tests(self, request, queryset):
        updated = queryset.update(is_published=True)
        self.message_user(request, f'Опубликовано: {updated}')

    @admin.action(description='🔒 Снять с публикации')
    def unpublish_tests(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f'Снято: {updated}')


# ── TestAttempt ──────────────────────────────────────────

@admin.register(TestAttempt)
class TestAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'test', 'score', 'max_score', 'percentage', 'started_at', 'finished_at']
    list_filter = ['test__subject', 'test__grade_level']
    search_fields = ['student__username', 'student__email', 'test__title']
    date_hierarchy = 'started_at'
    list_per_page = 30
    ordering = ['-started_at']
    readonly_fields = ['student', 'test', 'score', 'max_score', 'percentage', 'feedback', 'started_at', 'finished_at']
    inlines = [StudentAnswerInline]
    actions = [export_csv]

    def has_add_permission(self, request):
        return False


# ── Essay ────────────────────────────────────────────────

@admin.register(Essay)
class EssayAdmin(admin.ModelAdmin):
    list_display = ['student', 'subject', 'title', 'score', 'logic_score', 'structure_score', 'argumentation_score', 'is_checked', 'created_at']
    list_filter = ['is_checked', 'subject']
    search_fields = ['student__username', 'title', 'content']
    date_hierarchy = 'created_at'
    list_per_page = 25
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'checked_at', 'score', 'logic_score', 'structure_score', 'argumentation_score', 'strengths', 'weaknesses', 'recommendations', 'materials_to_review']
    actions = [export_csv]

    fieldsets = (
        (None, {'fields': ('student', 'subject', 'title')}),
        ('Текст', {'fields': ('content',)}),
        ('Оценки ИИ', {
            'fields': ('is_checked', 'score', 'logic_score', 'structure_score', 'argumentation_score'),
            'classes': ('collapse',) if False else (),
        }),
        ('Обратная связь', {
            'fields': ('strengths', 'weaknesses', 'recommendations', 'materials_to_review'),
            'classes': ('collapse',),
        }),
        ('Даты', {'fields': ('created_at', 'checked_at'), 'classes': ('collapse',)}),
    )


# ── ClassReport ──────────────────────────────────────────

@admin.register(ClassReport)
class ClassReportAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'subject', 'grade_level', 'student_count', 'avg_score', 'created_at']
    list_filter = ['subject', 'grade_level']
    search_fields = ['teacher__username', 'report_text']
    date_hierarchy = 'created_at'
    list_per_page = 25
    ordering = ['-created_at']
    readonly_fields = ['created_at']
    actions = [export_csv]


# ── LearningProfile ─────────────────────────────────────

@admin.register(LearningProfile)
class LearningProfileAdmin(admin.ModelAdmin):
    list_display = ['student', 'learning_style', 'difficulty_level', 'total_tests_taken', 'avg_score', 'streak_days', 'last_activity']
    list_filter = ['learning_style', 'difficulty_level']
    search_fields = ['student__username', 'student__email']
    list_per_page = 25
    ordering = ['-avg_score']
    readonly_fields = ['total_tests_taken', 'avg_score', 'streak_days', 'last_activity', 'updated_at']
    actions = [export_csv]

    fieldsets = (
        (None, {'fields': ('student', 'learning_style', 'difficulty_level')}),
        ('Темы', {'fields': ('interests', 'strong_topics', 'weak_topics')}),
        ('Статистика', {
            'fields': ('total_tests_taken', 'avg_score', 'streak_days', 'last_activity', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


# ── FAQ ──────────────────────────────────────────────────

@admin.register(FaqCategory)
class FaqCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'name_en', 'name_kk', 'icon', 'order', 'question_count']
    list_editable = ['order', 'name_en', 'name_kk']
    inlines = [FaqQuestionInline]

    @admin.display(description='Вопросов')
    def question_count(self, obj):
        return obj.questions.count()


# ── ChatMessage ──────────────────────────────────────────

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'context', 'short_content', 'created_at']
    list_filter = ['role', 'context']
    search_fields = ['user__username', 'content', 'session_key']
    date_hierarchy = 'created_at'
    list_per_page = 50
    ordering = ['-created_at']
    readonly_fields = ['user', 'session_key', 'role', 'content', 'context', 'created_at']

    def has_add_permission(self, request):
        return False

    @admin.display(description='Сообщение')
    def short_content(self, obj):
        return obj.content[:80] + '…' if len(obj.content) > 80 else obj.content


# ── ContactMessage ───────────────────────────────────────

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'category', 'subject', 'is_read', 'is_resolved', 'created_at']
    list_filter = ['is_read', 'is_resolved', 'category']
    search_fields = ['name', 'email', 'subject', 'message']
    date_hierarchy = 'created_at'
    list_per_page = 25
    ordering = ['-created_at']
    readonly_fields = ['name', 'email', 'category', 'subject', 'message', 'created_at']
    actions = [export_csv, 'mark_read', 'mark_resolved']

    fieldsets = (
        ('Обращение', {'fields': ('name', 'email', 'category', 'subject', 'message')}),
        ('Статус', {'fields': ('is_read', 'is_resolved')}),
        ('Ответ', {'fields': ('admin_reply', 'replied_at')}),
        ('Мета', {'fields': ('created_at',), 'classes': ('collapse',)}),
    )

    @admin.action(description='👁 Отметить как прочитанные')
    def mark_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f'Прочитано: {updated}')

    @admin.action(description='✅ Отметить как решённые')
    def mark_resolved(self, request, queryset):
        updated = queryset.update(is_read=True, is_resolved=True, replied_at=timezone.now())
        self.message_user(request, f'Решено: {updated}')


# ── Organization ─────────────────────────────────────────

class OrganizationKeyInline(admin.TabularInline):
    model = OrganizationKey
    extra = 0
    fields = ['key', 'key_type', 'subject', 'grades', 'is_used', 'used_by', 'created_at']
    readonly_fields = ['key', 'is_used', 'used_by', 'created_at']


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'address', 'contact_email', 'is_active', 'member_count', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'address', 'contact_email']
    ordering = ['name']
    inlines = [OrganizationKeyInline]
    actions = [export_csv]

    @admin.display(description='Участников')
    def member_count(self, obj):
        return obj.members.count()


@admin.register(OrganizationKey)
class OrganizationKeyAdmin(admin.ModelAdmin):
    list_display = ['key_short', 'organization', 'key_type', 'subject', 'is_used', 'used_by', 'created_at']
    list_filter = ['key_type', 'is_used']
    search_fields = ['key', 'organization__name']
    ordering = ['-created_at']
    readonly_fields = ['key', 'created_at', 'used_at']
    actions = [export_csv]

    @admin.display(description='Ключ')
    def key_short(self, obj):
        return f'{obj.key[:12]}…'

"""
EduAI — Seed command
Creates initial data: subjects, FAQ categories/questions, demo users
Usage: python manage.py seed
"""
from django.core.management.base import BaseCommand
from core.models import (
    EduUser, AccessibilityProfile, Subject, LearningProfile,
    FaqCategory, FaqQuestion,
)


class Command(BaseCommand):
    help = 'Seed the database with initial EduAI data'

    def handle(self, *args, **options):
        self.stdout.write('🌱 Seeding EduAI database...\n')

        # --- Subjects ---
        subjects_data = [
            {'name': 'Математика', 'icon': '📐', 'color': '#6366f1'},
            {'name': 'Русский язык', 'icon': '📝', 'color': '#ec4899'},
            {'name': 'Литература', 'icon': '📚', 'color': '#f59e0b'},
            {'name': 'Физика', 'icon': '⚡', 'color': '#3b82f6'},
            {'name': 'Химия', 'icon': '🧪', 'color': '#10b981'},
            {'name': 'Биология', 'icon': '🌱', 'color': '#22c55e'},
            {'name': 'История', 'icon': '🏛️', 'color': '#8b5cf6'},
            {'name': 'География', 'icon': '🌍', 'color': '#14b8a6'},
            {'name': 'Информатика', 'icon': '💻', 'color': '#06b6d4'},
            {'name': 'Английский язык', 'icon': '🇬🇧', 'color': '#f43f5e'},
        ]
        for sd in subjects_data:
            Subject.objects.get_or_create(name=sd['name'], defaults=sd)
        self.stdout.write(f'  ✅ Subjects: {Subject.objects.count()}')

        # --- FAQ ---
        faq_data = [
            {
                'name': 'Общие вопросы', 'icon': '❓', 'order': 1,
                'questions': [
                    ('Что такое EduAI?', 'EduAI — это интеллектуальная образовательная платформа на основе генеративного ИИ. Она помогает ученикам учиться эффективнее, а учителям — автоматизировать рутинные задачи.'),
                    ('Для кого предназначена платформа?', 'Платформа создана для учеников 1–11 классов (включая детей с особыми образовательными потребностями) и учителей.'),
                    ('Платформа бесплатная?', 'Да, EduAI полностью бесплатна для учебных заведений.'),
                ]
            },
            {
                'name': 'Ассистент преподавателя', 'icon': '👨‍🏫', 'order': 2,
                'questions': [
                    ('Как генерировать тесты?', 'Перейдите в раздел «Ассистент преподавателя», вставьте текст из учебника или методички, выберите предмет и класс, затем нажмите «Сгенерировать тест». ИИ создаст уникальные вопросы с вариантами ответов.'),
                    ('Можно ли редактировать сгенерированные тесты?', 'Да, после генерации вы можете скопировать и доработать тест в любом текстовом редакторе. Функция редактирования прямо на платформе будет доступна в ближайших обновлениях.'),
                ]
            },
            {
                'name': 'Инклюзивность', 'icon': '♿', 'order': 3,
                'questions': [
                    ('Что значит «Доступная среда»?', 'Модуль доступной среды включает функции для учеников с особыми потребностями: озвучивание текста, режим лёгкого чтения, генерация ментальных карт, настройка размера шрифта и контрастности.'),
                    ('Поддерживается ли синтез речи?', 'Да, EduAI использует Web Speech API для озвучивания текста. Поддерживается русский и казахский языки.'),
                ]
            },
            {
                'name': 'ИИ и безопасность', 'icon': '🤖', 'order': 4,
                'questions': [
                    ('Какой ИИ используется?', 'EduAI поддерживает различные модели: Google Gemini, OpenAI GPT, локальные модели через Ollama. По умолчанию используется Gemini 2.5 Flash.'),
                    ('Безопасны ли данные учеников?', 'Да, все данные хранятся на сервере учебного заведения. ИИ-запросы не содержат персональных данных учеников. Пароли хранятся в зашифрованном виде.'),
                ]
            },
        ]
        for cat_data in faq_data:
            cat, _ = FaqCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={'icon': cat_data['icon'], 'order': cat_data['order']}
            )
            for i, (q, a) in enumerate(cat_data['questions']):
                FaqQuestion.objects.get_or_create(
                    category=cat, question=q,
                    defaults={'answer': a, 'order': i + 1}
                )
        self.stdout.write(f'  ✅ FAQ: {FaqCategory.objects.count()} categories, {FaqQuestion.objects.count()} questions')

        # --- Demo Users ---
        if not EduUser.objects.filter(username='student_demo').exists():
            student = EduUser(username='student_demo', email='student@demo.com', role='student', grade=9)
            student.set_password('demo123')
            student.save()
            AccessibilityProfile.objects.get_or_create(user=student)
            LearningProfile.objects.get_or_create(student=student)
            self.stdout.write('  ✅ Demo student: student_demo / demo123')

        if not EduUser.objects.filter(username='teacher_demo').exists():
            teacher = EduUser(username='teacher_demo', email='teacher@demo.com', role='teacher')
            teacher.set_password('demo123')
            teacher.save()
            self.stdout.write('  ✅ Demo teacher: teacher_demo / demo123')

        if not EduUser.objects.filter(username='admin').exists():
            admin = EduUser(username='admin', email='admin@eduai.kz', role='admin')
            admin.set_password('admin123')
            admin.save()
            self.stdout.write('  ✅ Admin: admin / admin123')

        self.stdout.write(self.style.SUCCESS('\n🎉 Seeding complete!'))

from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('accessibility/', views.accessibility_module, name='accessibility'),
    path('teacher/', views.teacher_assistant, name='teacher_assistant'),
    path('personalization/', views.personalization, name='personalization'),
    path('feedback/', views.feedback_module, name='feedback'),
    path('copilot/', views.copilot, name='copilot'),
    path('faq/', views.faq, name='faq'),
    path('contact/', views.contact, name='contact'),
    path('subscription/', views.subscription, name='subscription'),
    path('payment/', views.payment, name='payment'),
    path('about/', views.about, name='about'),
    path('lessons/', views.lessons_catalog, name='lessons'),
    # Teacher lesson CRUD
    path('lessons/create/', views.lesson_create, name='lesson_create'),
    path('lessons/<int:lesson_id>/', views.lesson_detail, name='lesson_detail'),
    path('lessons/<int:lesson_id>/edit/', views.lesson_edit, name='lesson_edit'),
    path('lessons/<int:lesson_id>/delete/', views.lesson_delete, name='lesson_delete'),
    # Tests
    path('tests/', views.test_list, name='test_list'),
    path('tests/create/', views.test_create, name='test_create'),
    path('tests/manage/', views.test_manage, name='test_manage'),
    path('tests/<int:test_id>/', views.test_take, name='test_take'),
    path('tests/result/<int:attempt_id>/', views.test_result, name='test_result'),
    # Assignments
    path('assignments/', views.assignment_list, name='assignment_list'),
    path('assignments/create/', views.assignment_create, name='assignment_create'),
    path('assignments/<int:assignment_id>/', views.assignment_detail, name='assignment_detail'),
    path('assignments/<int:assignment_id>/edit/', views.assignment_edit, name='assignment_edit'),
    # Results
    path('results/', views.my_results, name='my_results'),
    # Auth
    path('signup/', views.signup, name='signup'),
    path('signup/teacher/', views.teacher_signup, name='teacher_signup'),
    path('org-setup/', views.org_setup, name='org_setup'),
    path('login/', views.login, name='login'),
    path('password-reset/', views.password_reset_request, name='password_reset'),
    path('password-reset/<str:token>/', views.password_reset_confirm, name='password_reset_confirm'),
    path('logout/', views.logout, name='logout'),
    path('profile/', views.profile, name='profile'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    # API
    path('api/language/', views.api_set_language, name='api_set_language'),
    path('api/theme/', views.api_set_theme, name='api_set_theme'),
    path('api/timezone/', views.api_set_timezone, name='api_set_timezone'),
    path('api/accessibility/', views.api_accessibility, name='api_accessibility'),
    path('api/speech-to-text/', views.api_speech_to_text, name='api_speech_to_text'),
    path('api/ai-chat/', views.api_ai_chat, name='api_ai_chat'),
    path('api/ai-stream/', views.api_ai_stream, name='api_ai_stream'),
    path('api/generate-test/', views.api_generate_test, name='api_generate_test'),
    path('api/check-essay/', views.api_check_essay, name='api_check_essay'),
    path('api/simplify/', views.api_simplify_text, name='api_simplify_text'),
    path('api/mindmap/', views.api_generate_mindmap, name='api_generate_mindmap'),
    path('api/personalize/', views.api_personalize, name='api_personalize'),
    path('api/class-report/', views.api_generate_report, name='api_generate_report'),
    path('api/tts/', views.api_tts, name='api_tts'),
    path('api/tts/chunked/', views.api_tts_chunked, name='api_tts_chunked'),
    path('api/tts/voices/', views.api_tts_voices, name='api_tts_voices'),
    path('api/ai-lesson/', views.api_ai_lesson_content, name='api_ai_lesson_content'),
    # Admin API
    path('api/admin/toggle-user/', views.api_admin_toggle_user, name='api_admin_toggle_user'),
    path('api/admin/change-role/', views.api_admin_change_role, name='api_admin_change_role'),
    path('api/admin/mark-read/', views.api_admin_mark_read, name='api_admin_mark_read'),
    path('api/admin/reply/', views.api_admin_reply, name='api_admin_reply'),
    path('api/admin/i18n/', views.api_admin_i18n, name='api_admin_i18n'),
    # Test API
    path('api/test/save/', views.api_test_save, name='api_test_save'),
    path('api/test/<int:test_id>/publish/', views.api_test_publish, name='api_test_publish'),
    path('api/test/<int:test_id>/delete/', views.api_test_delete, name='api_test_delete'),
    path('api/test/<int:test_id>/submit/', views.api_test_submit, name='api_test_submit'),
    # Assignment API
    path('api/assignment/grade/<int:submission_id>/', views.api_assignment_grade, name='api_assignment_grade'),
    path('api/assignment/<int:assignment_id>/delete/', views.api_assignment_delete, name='api_assignment_delete'),
    # Chat API
    path('api/chat/history/', views.api_chat_history, name='api_chat_history'),
    path('api/chat/clear/', views.api_chat_clear, name='api_chat_clear'),

    # Organization & Key Management
    path('api/school/generate-key/', views.api_school_generate_key, name='api_school_generate_key'),
    path('api/school/revoke-key/', views.api_school_revoke_key, name='api_school_revoke_key'),
    path('api/admin/create-org/', views.api_admin_create_org, name='api_admin_create_org'),
    path('api/admin/edit-org/', views.api_admin_edit_org, name='api_admin_edit_org'),
    path('api/admin/delete-org/', views.api_admin_delete_org, name='api_admin_delete_org'),
    path('api/admin/regen-master-key/', views.api_admin_regen_master_key, name='api_admin_regen_master_key'),
    # Teacher manual essay review
    path('api/essay/teacher-review/', views.api_essay_teacher_review, name='api_essay_teacher_review'),
]

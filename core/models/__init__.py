"""
Модели EduAI — интеллектуальная образовательная платформа.
"""

from .user import EduUser, AccessibilityProfile, _avatar_path
from .organization import Organization, OrganizationKey
from .education import Subject, Lesson, Assignment, AssignmentSubmission, SubmissionFile
from .testing import Test, TestQuestion, TestAttempt, StudentAnswer
from .feedback import Essay, ClassReport
from .learning import LearningProfile
from .faq import FaqCategory, FaqQuestion
from .chat import ChatMessage
from .contact import ContactMessage

__all__ = [
    '_avatar_path',
    'EduUser', 'AccessibilityProfile',
    'Organization', 'OrganizationKey',
    'Subject', 'Lesson', 'Assignment', 'AssignmentSubmission',
    'Test', 'TestQuestion', 'TestAttempt', 'StudentAnswer',
    'Essay', 'ClassReport',
    'LearningProfile',
    'FaqCategory', 'FaqQuestion',
    'ChatMessage',
    'ContactMessage',
]

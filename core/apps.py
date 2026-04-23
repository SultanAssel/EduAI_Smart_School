"""Конфигурация приложения EduAI."""
import logging

from django.apps import AppConfig

logger = logging.getLogger('core')


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'EduAI'

    def ready(self):
        """Инициализация приложения."""
        logger.info('EduAI ready ✓')

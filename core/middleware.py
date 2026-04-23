"""Custom middleware for EduAI."""
import logging
import zoneinfo

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger('core')


class UserTimezoneMiddleware:
    """Activate the per-user timezone stored in EduUser.tz."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        tz_name = request.session.get('user_tz')
        if tz_name:
            try:
                timezone.activate(zoneinfo.ZoneInfo(tz_name))
            except (KeyError, zoneinfo.ZoneInfoNotFoundError):
                logger.warning('Invalid timezone in session: %s', tz_name)
                timezone.activate(zoneinfo.ZoneInfo(settings.TIME_ZONE))
        else:
            timezone.deactivate()
        response = self.get_response(request)
        timezone.deactivate()
        return response

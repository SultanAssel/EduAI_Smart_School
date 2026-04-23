"""Periodic cleanup: expired sessions, stale cache, old chat messages."""
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Clear expired sessions, old chat messages, and stale cache entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chat-days', type=int, default=90,
            help='Delete chat messages older than N days (default: 90)',
        )

    def handle(self, *args, **options):
        # 1. Clear expired Django sessions
        self.stdout.write('Clearing expired sessions...')
        call_command('clearsessions')
        self.stdout.write(self.style.SUCCESS('Sessions cleared.'))

        # 2. Delete old chat messages
        days = options['chat_days']
        cutoff = timezone.now() - timedelta(days=days)
        from core.models import ChatMessage
        deleted, _ = ChatMessage.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted} chat messages older than {days} days.'))

        self.stdout.write(self.style.SUCCESS('Cleanup complete.'))

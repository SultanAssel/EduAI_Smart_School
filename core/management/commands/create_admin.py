"""
EduAI — Create platform admin
Usage: python manage.py create_admin
Creates a user with role='admin' who can create organizations and master keys.
"""
import getpass
from django.core.management.base import BaseCommand, CommandError
from core.models import EduUser, AccessibilityProfile


class Command(BaseCommand):
    help = 'Create a platform administrator (role=admin)'

    def add_arguments(self, parser):
        parser.add_argument('--username', help='Admin username')
        parser.add_argument('--email', help='Admin email')
        parser.add_argument('--password', help='Admin password (unsafe, prefer interactive)')
        parser.add_argument('--noinput', action='store_true', help='Use defaults without prompting')

    def handle(self, *args, **options):
        username = options['username']
        email = options['email']
        password = options['password']

        if not options['noinput']:
            if not username:
                username = input('Username: ').strip()
            if not email:
                email = input('Email: ').strip()
            if not password:
                password = getpass.getpass('Password: ')
                password2 = getpass.getpass('Password (again): ')
                if password != password2:
                    raise CommandError('Passwords do not match.')

        if not username or len(username) < 3:
            raise CommandError('Username must be at least 3 characters.')
        if not email or '@' not in email:
            raise CommandError('Invalid email address.')
        if not password or len(password) < 6:
            raise CommandError('Password must be at least 6 characters.')

        if EduUser.objects.filter(username=username).exists():
            raise CommandError(f'Username "{username}" is already taken.')
        if EduUser.objects.filter(email=email).exists():
            raise CommandError(f'Email "{email}" is already registered.')

        user = EduUser.create_user(
            username=username, email=email, password=password, role='admin',
        )
        AccessibilityProfile.objects.get_or_create(user=user)

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Platform admin created!\n'
            f'   Username: {username}\n'
            f'   Email:    {email}\n'
            f'   Role:     admin\n'
        ))

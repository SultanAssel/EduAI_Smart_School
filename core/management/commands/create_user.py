"""
EduAI — Create user with any role
Usage:
    python manage.py create_user --role student --username ivan --email ivan@test.com --password secret123
    python manage.py create_user  (interactive mode)
"""
import getpass
from django.core.management.base import BaseCommand, CommandError
from core.models import EduUser, AccessibilityProfile, LearningProfile, Organization

VALID_ROLES = ('student', 'teacher', 'school_admin', 'admin')


class Command(BaseCommand):
    help = 'Create a user with any role'

    def add_arguments(self, parser):
        parser.add_argument('--username', help='Username')
        parser.add_argument('--email', help='Email')
        parser.add_argument('--password', help='Password (unsafe, prefer interactive)')
        parser.add_argument('--role', choices=VALID_ROLES, help='User role')
        parser.add_argument('--first-name', default='', help='First name')
        parser.add_argument('--last-name', default='', help='Last name')
        parser.add_argument('--org', default='', help='Organization name (for teacher/school_admin)')
        parser.add_argument('--noinput', action='store_true', help='Non-interactive mode')

    def handle(self, *args, **options):
        role = options['role']
        username = options['username']
        email = options['email']
        password = options['password']
        first_name = options['first_name']
        last_name = options['last_name']
        org_name = options['org']

        if not options['noinput']:
            if not role:
                self.stdout.write(f'Available roles: {", ".join(VALID_ROLES)}')
                role = input('Role: ').strip()
            if not username:
                username = input('Username: ').strip()
            if not email:
                email = input('Email: ').strip()
            if not first_name:
                first_name = input('First name (optional): ').strip()
            if not last_name:
                last_name = input('Last name (optional): ').strip()
            if role in ('teacher', 'school_admin') and not org_name:
                org_name = input('Organization name (optional): ').strip()
            if not password:
                password = getpass.getpass('Password: ')
                password2 = getpass.getpass('Password (again): ')
                if password != password2:
                    raise CommandError('Passwords do not match.')

        if role not in VALID_ROLES:
            raise CommandError(f'Invalid role. Choose from: {", ".join(VALID_ROLES)}')
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

        extra = {}
        if first_name:
            extra['first_name'] = first_name
        if last_name:
            extra['last_name'] = last_name

        if org_name and role in ('teacher', 'school_admin'):
            try:
                extra['organization'] = Organization.objects.get(name=org_name)
            except Organization.DoesNotExist:
                raise CommandError(f'Organization "{org_name}" not found. Create it first with: python manage.py create_org "{org_name}"')

        user = EduUser.create_user(
            username=username, email=email, password=password, role=role, **extra,
        )
        AccessibilityProfile.objects.get_or_create(user=user)
        if role == 'student':
            LearningProfile.objects.get_or_create(student=user)

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ User created!\n'
            f'   Username: {username}\n'
            f'   Email:    {email}\n'
            f'   Role:     {role}\n'
        ))

"""
EduAI — Create organization + master key
Usage: python manage.py create_org "School Name"
Creates an Organization and generates a one-time master key for school_admin registration.
"""
from django.core.management.base import BaseCommand, CommandError
from core.models import Organization, OrganizationKey


class Command(BaseCommand):
    help = 'Create an organization and generate a master key'

    def add_arguments(self, parser):
        parser.add_argument('name', help='Organization name (e.g. "Школа №42")')
        parser.add_argument('--address', default='', help='Optional address')
        parser.add_argument('--email', default='', help='Optional contact email')

    def handle(self, *args, **options):
        name = options['name'].strip()
        if not name:
            raise CommandError('Organization name cannot be empty.')

        org, created = Organization.objects.get_or_create(
            name=name,
            defaults={
                'address': options['address'],
                'contact_email': options['email'],
            },
        )

        if not created:
            self.stdout.write(self.style.WARNING(f'Organization "{name}" already exists.'))

        key_obj = OrganizationKey.objects.create(
            organization=org, key_type='master',
        )

        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Organization {"created" if created else "found"}!\n'
            f'   Name:       {org.name}\n'
            f'   ID:         {org.id}\n'
            f'   Master Key: {key_obj.key}\n'
            f'\n   Give this key to the school administrator.\n'
            f'   They enter it at /org-setup/ to register.\n'
            f'   The key is single-use.\n'
        ))

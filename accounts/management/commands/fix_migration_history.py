from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Repair inconsistent PostgreSQL migration history."

    def handle(self, *args, **options):

        if connection.vendor != "postgresql":
            raise CommandError(
                "This command must be executed against PostgreSQL."
            )

        with connection.cursor() as cursor:

            self.stdout.write(
                self.style.WARNING(
                    "Checking current migration history..."
                )
            )

            cursor.execute(
                """
                SELECT app, name
                FROM django_migrations
                WHERE app IN ('accounts', 'admin')
                ORDER BY app, name;
                """
            )

            migrations = cursor.fetchall()

            for app, name in migrations:
                self.stdout.write(
                    f"  {app}.{name}"
                )

            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM django_migrations
                    WHERE app = 'accounts'
                    AND name = '0001_initial'
                );
                """
            )

            accounts_exists = cursor.fetchone()[0]

            if accounts_exists:
                self.stdout.write(
                    self.style.SUCCESS(
                        "accounts.0001_initial is already recorded."
                    )
                )
                return

            self.stdout.write(
                self.style.WARNING(
                    "accounts.0001_initial is missing."
                )
            )

            cursor.execute(
                """
                DELETE FROM django_migrations
                WHERE app = 'admin'
                AND name IN (
                    '0001_initial',
                    '0002_logentry_remove_auto_add',
                    '0003_logentry_add_action_flag_choices'
                );
                """
            )

            deleted_count = cursor.rowcount

            self.stdout.write(
                self.style.WARNING(
                    f"Removed {deleted_count} admin migration records."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Migration history repair completed."
            )
        )
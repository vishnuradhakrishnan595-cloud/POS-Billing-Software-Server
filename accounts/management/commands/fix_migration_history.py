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
                    "Checking PostgreSQL migration history..."
                )
            )

            # Check whether accounts migration is already recorded.
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

            # The admin tables already exist in PostgreSQL.
            # Therefore record the admin migrations as applied
            # instead of trying to recreate their tables.
            admin_migrations = [
                (
                    "admin",
                    "0001_initial",
                ),
                (
                    "admin",
                    "0002_logentry_remove_auto_add",
                ),
                (
                    "admin",
                    "0003_logentry_add_action_flag_choices",
                ),
            ]

            for app, name in admin_migrations:

                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM django_migrations
                        WHERE app = %s
                        AND name = %s
                    );
                    """,
                    [app, name],
                )

                exists = cursor.fetchone()[0]

                if not exists:

                    cursor.execute(
                        """
                        INSERT INTO django_migrations
                            (app, name, applied)
                        VALUES
                            (%s, %s, NOW());
                        """,
                        [app, name],
                    )

                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Recorded {app}.{name} as applied."
                        )
                    )

                else:

                    self.stdout.write(
                        f"{app}.{name} is already recorded."
                    )

            self.stdout.write(
                self.style.WARNING(
                    "Admin migration history has been repaired."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Migration history repair completed successfully."
            )
        )
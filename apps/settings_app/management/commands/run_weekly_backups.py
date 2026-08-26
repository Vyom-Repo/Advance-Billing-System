"""
apps/settings_app/management/commands/run_weekly_backups.py

Management command to trigger automated weekly data backups for all organizations
that have weekly backups enabled.

Usage:
    python manage.py run_weekly_backups [--force] [--org-id=ID]
"""

from django.core.management.base import BaseCommand
from apps.organization.models import Organization
from apps.settings_app.models import OrganizationBackupSetting
from apps.settings_app.services.backup_service import OrganizationBackupService


class Command(BaseCommand):
    help = "Generates and emails weekly structured business data backups to organization owners."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Bypass the 6-day idempotency check and send backups immediately.",
        )
        parser.add_argument(
            "--org-id",
            type=int,
            help="Run backup for a specific organization ID only.",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        org_id = options.get("org_id")

        if org_id:
            try:
                orgs = [Organization.objects.get(id=org_id)]
            except Organization.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"Organization ID {org_id} not found."))
                return
        else:
            # Select organizations with weekly backup enabled
            enabled_settings = OrganizationBackupSetting.objects.filter(weekly_backup_enabled=True)
            org_ids = enabled_settings.values_list("organization_id", flat=True)
            orgs = Organization.objects.filter(id__in=org_ids)

        if not orgs:
            self.stdout.write(self.style.SUCCESS("No organizations found with weekly backups enabled."))
            return

        self.stdout.write(f"Processing weekly data backups for {len(orgs)} organization(s)...")

        success_count = 0
        failure_count = 0

        for org in orgs:
            self.stdout.write(f" - Processing {org.business_name} (ID: {org.id})...")
            success, msg = OrganizationBackupService.send_weekly_backup_email(org, force=force)
            if success:
                success_count += 1
                self.stdout.write(self.style.SUCCESS(f"   [SUCCESS] {msg}"))
            else:
                failure_count += 1
                self.stderr.write(self.style.ERROR(f"   [FAILED] {msg}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nWeekly backup run complete. Successful: {success_count}, Failed: {failure_count}."
            )
        )

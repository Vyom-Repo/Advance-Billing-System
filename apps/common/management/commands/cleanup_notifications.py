from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.common.services.notification_service import NotificationService

User = get_user_model()

class Command(BaseCommand):
    help = 'Cleans up expired notifications and enforces per-user limits.'

    def handle(self, *args, **options):
        self.stdout.write("Starting notification cleanup...")
        
        users = User.objects.all()
        processed_users = 0
        
        for user in users:
            NotificationService.cleanup_for_user(user)
            processed_users += 1
            
        self.stdout.write(self.style.SUCCESS(f"Successfully processed cleanup for {processed_users} users."))

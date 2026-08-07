from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.contrib import messages
from apps.common.models import Notification, NotificationPriority, NotificationCategory

class NotificationService:
    RETENTION_POLICY_DAYS = {
        # Critical security handled by priority 1 (never delete)
        NotificationCategory.ORGANIZATION: 365,
        NotificationCategory.BILLING: 365,
        NotificationCategory.CUSTOMERS: 180,
        NotificationCategory.SYSTEM: 180,
        NotificationCategory.SETTINGS: 60,
    }
    
    MAX_NOTIFICATIONS = 300

    @classmethod
    def create(cls, user, category, event_type, title, message, priority=None, 
               organization=None, entity_type=None, entity_id=None, request=None):
        
        # Intercept Theme Changed events
        if event_type == "theme_changed":
            if request:
                messages.success(request, message)
            return None # Option B: skip persistent DB storage
            
        # Assign Priority if not provided
        if priority is None:
            priority = cls._determine_priority(category, event_type)
            
        with transaction.atomic():
            notification = Notification.objects.create(
                user=user,
                organization=organization,
                category=category,
                event_type=event_type,
                title=title,
                message=message,
                entity_type=entity_type,
                entity_id=entity_id,
                priority=priority
            )
        
        # Inline cleanup to enforce limit
        cls._trigger_cleanup(user)
        
        return notification

    @classmethod
    def _determine_priority(cls, category, event_type):
        critical_events = ["password_changed", "email_changed", "account_recovery", "organization_deleted"]
        high_events = ["invoice_marked_paid", "invoice_cancelled", "organization_updated", "gst_validation_failed"]
        medium_events = ["invoice_created", "invoice_updated", "customer_added", "customer_updated", "gst_verified"]
        low_events = ["profile_updated", "theme_changed"]
        
        if event_type in critical_events:
            return NotificationPriority.CRITICAL
        elif event_type in high_events:
            return NotificationPriority.HIGH
        elif event_type in low_events:
            return NotificationPriority.LOW
        else:
            return NotificationPriority.MEDIUM

    @classmethod
    def _trigger_cleanup(cls, user):
        """
        Enforce the 300 notification limit and delete expired notifications.
        """
        cls.cleanup_for_user(user)

    @classmethod
    def cleanup_for_user(cls, user):
        """
        1. Delete expired based on retention.
        2. Delete P5, P4, P3 progressively if count > MAX
        """
        now = timezone.now()
        
        # 1. Delete Expired
        for cat_choice in NotificationCategory.choices:
            cat = cat_choice[0]
            days = cls.RETENTION_POLICY_DAYS.get(cat, 60)
            cutoff_date = now - timedelta(days=days)
            # Delete expired, but protect P1 and P2
            Notification.objects.filter(
                user=user, 
                category=cat, 
                created_at__lt=cutoff_date,
                priority__gte=NotificationPriority.MEDIUM
            ).delete()
            
        cls._enforce_limit(user)

    @classmethod
    def _enforce_limit(cls, user):
        count = Notification.objects.filter(user=user).count()
        if count <= cls.MAX_NOTIFICATIONS:
            return
            
        excess = count - cls.MAX_NOTIFICATIONS
        
        # 2. Delete P5
        if excess > 0:
            excess = cls._delete_lowest_priority(user, NotificationPriority.TEMPORARY, excess)
            
        # 3. Delete P4
        if excess > 0:
            excess = cls._delete_lowest_priority(user, NotificationPriority.LOW, excess)
            
        # 4. Delete P3
        if excess > 0:
            excess = cls._delete_lowest_priority(user, NotificationPriority.MEDIUM, excess)
            
        # Priority 1 and 2 are never touched to enforce limit

    @classmethod
    def _delete_lowest_priority(cls, user, priority, excess):
        """
        Delete up to 'excess' notifications of the given priority, starting from oldest.
        Returns the remaining excess.
        """
        # Find oldest notifications of this priority
        oldest_ids = Notification.objects.filter(
            user=user, 
            priority=priority
        ).order_by('created_at').values_list('id', flat=True)[:excess]
        
        if oldest_ids:
            deleted_count, _ = Notification.objects.filter(id__in=list(oldest_ids)).delete()
            return excess - deleted_count
        return excess

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MaxLengthValidator
from mappings.models import Mapping


class Workflow(models.Model):
    """Scheduled workflow that automatically runs validations."""

    SCHEDULE_TYPES = [
        ('manual', 'On Demand'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, validators=[MaxLengthValidator(1000)])
    mapping = models.ForeignKey(Mapping, on_delete=models.CASCADE, related_name='workflows')

    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPES, default='manual')
    schedule_time = models.TimeField(null=True, blank=True, help_text='Time of day to run (for daily/weekly/monthly)')
    schedule_day = models.IntegerField(
        null=True, blank=True,
        help_text='Day of week (0=Mon, 6=Sun) for weekly; Day of month for monthly'
    )
    cron_expression = models.CharField(max_length=100, blank=True, help_text='Custom cron expression (5 fields)')



    is_active = models.BooleanField(default=True)
    celery_task_name = models.CharField(max_length=200, blank=True)
    selected_columns = models.TextField(blank=True, help_text='Comma-separated columns to validate. Leave empty for all.')
    recipient_email = models.CharField(max_length=255, blank=True, null=True, help_text='Email address to receive validation reports')

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='workflows')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.is_active:
            from .scheduler import calculate_next_run
            self.next_run = calculate_next_run(self)
        else:
            self.next_run = None
            
        update_fields = kwargs.get('update_fields')
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.add('next_run')
            kwargs['update_fields'] = list(update_fields)
            
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Workflow'

    def __str__(self):
        return f"{self.name} ({self.get_schedule_type_display()})"




class EmailNotification(models.Model):
    """Logs of sent email notifications for validation runs."""
    workflow = models.ForeignKey(Workflow, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_notifications')
    run = models.ForeignKey('validations.ETLRun', on_delete=models.SET_NULL, null=True, blank=True, related_name='email_notifications')
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    email_body = models.TextField()
    attachment_path = models.CharField(max_length=500, blank=True, null=True)
    sent_status = models.CharField(max_length=20, default='pending')  # 'success', 'failed', 'pending'
    sent_time = models.DateTimeField(null=True, blank=True)
    retry_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Email Notification'

    def __str__(self):
        return f"Notification {self.id} to {self.recipient_email} ({self.sent_status})"


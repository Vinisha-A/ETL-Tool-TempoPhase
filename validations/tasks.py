"""
Celery tasks for validation execution.
"""
import logging
from celery import shared_task
from .models import ETLRun
from .engine import ETLEngine

logger = logging.getLogger('validations')


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def run_etl_task(self, run_id):
    """Execute a validation run asynchronously."""
    try:
        run = ETLRun.objects.get(id=run_id)
        engine = ETLEngine(run)
        engine.execute()

        try:
            from logs.models import AuditLog
            AuditLog.objects.create(
                user=run.triggered_by,
                action=f'Validation Completed: {run.mapping.name}',
                entity_type='ETLRun',
                entity_id=run.id,
                details={
                    'total': run.total_checks,
                    'passed': run.passed_checks,
                    'failed': run.failed_checks,
                    'trigger_type': run.trigger_type,
                },
                level='info' if run.failed_checks == 0 else 'warning',
            )
            if run.triggered_by:
                from dashboard.models import Notification
                status_text = "Passed" if run.failed_checks == 0 else "Failed"
                Notification.objects.create(
                    user=run.triggered_by,
                    title=f"Validation Run {run.id} Completed",
                    message=f"Pipeline: {run.mapping.name}\nStatus: {status_text} ({run.passed_checks}/{run.total_checks} checks passed)",
                    level='success' if run.failed_checks == 0 else 'warning'
                )
        except Exception:
            pass

    except ETLRun.DoesNotExist:
        logger.error(f"ETLRun {run_id} not found")
    except Exception as exc:
        logger.error(f"Validation task failed: {exc}")
        try:
            run = ETLRun.objects.get(id=run_id)
            run.status = 'failed'
            run.error_message = str(exc)
            run.save()
            if run.triggered_by:
                from dashboard.models import Notification
                Notification.objects.create(
                    user=run.triggered_by,
                    title=f"Validation Run {run.id} Failed",
                    message=f"Pipeline: {run.mapping.name}\nError: {exc}",
                    level='error'
                )
        except Exception:
            pass
        raise self.retry(exc=exc)

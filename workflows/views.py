import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Workflow
from mappings.models import Mapping
from accounts.decorators import contributor_or_admin_required

logger = logging.getLogger(__name__)


@login_required
def workflow_list_view(request):
    """List all workflows."""
    workflows = Workflow.objects.select_related('mapping', 'created_by').all()
    return render(request, 'workflows/list.html', {'workflows': workflows})


@login_required
@contributor_or_admin_required
def workflow_create_view(request):
    """Create a new workflow."""
    mappings = Mapping.objects.filter(is_active=True)

    if request.method == 'POST':
        try:
            schedule_type = request.POST.get('schedule_type', 'manual')
            selected_cols = request.POST.getlist('selected_columns')
            selected_columns_str = ",".join(selected_cols)

            workflow = Workflow.objects.create(
                name=request.POST.get('name', ''),
                description=request.POST.get('description', ''),
                mapping_id=request.POST.get('mapping'),
                schedule_type=schedule_type,
                schedule_time=request.POST.get('schedule_time') or None,
                schedule_day=request.POST.get('schedule_day') or None,
                cron_expression=request.POST.get('cron_expression', ''),
                selected_columns=selected_columns_str,
                recipient_email=request.POST.get('recipient_email', '').strip() or None,
                created_by=request.user,
            )

            # Register with scheduler
            if schedule_type not in ('manual',):
                _register_celery_schedule(workflow)

            try:
                from logs.models import AuditLog
                AuditLog.objects.create(
                    user=request.user,
                    action=f'Created Workflow: {workflow.name}',
                    entity_type='Workflow',
                    entity_id=workflow.id,
                    details={
                        'schedule': workflow.schedule_type,
                    },
                    ip_address=request.META.get('REMOTE_ADDR'),
                    level='info',
                )
            except Exception:
                pass

            messages.success(request, f'Workflow "{workflow.name}" created successfully.')
            return redirect('workflows:list')

        except Exception as e:
            messages.error(request, f'Error: {str(e)}')

    return render(request, 'workflows/create.html', {'mappings': mappings})


@login_required
def workflow_detail_view(request, workflow_id):
    """View workflow details."""
    workflow = get_object_or_404(
        Workflow.objects.select_related('mapping', 'created_by'), id=workflow_id
    )
    return render(request, 'workflows/detail.html', {'workflow': workflow})


@login_required
@contributor_or_admin_required
def workflow_edit_view(request, workflow_id):
    """Edit an existing workflow."""
    workflow = get_object_or_404(Workflow, id=workflow_id)
    mappings = Mapping.objects.filter(is_active=True)

    if request.method == 'POST':
        try:
            schedule_type = request.POST.get('schedule_type', 'manual')
            selected_cols = request.POST.getlist('selected_columns')
            selected_columns_str = ",".join(selected_cols)

            workflow.name = request.POST.get('name', '').strip()
            workflow.description = request.POST.get('description', '')
            workflow.mapping_id = request.POST.get('mapping')
            workflow.schedule_type = schedule_type
            workflow.schedule_time = request.POST.get('schedule_time') or None
            workflow.schedule_day = request.POST.get('schedule_day') or None
            workflow.cron_expression = request.POST.get('cron_expression', '')
            workflow.selected_columns = selected_columns_str
            workflow.recipient_email = request.POST.get('recipient_email', '').strip() or None
            workflow.save()

            # Re-register or update Celery schedule
            if schedule_type not in ('manual',):
                _register_celery_schedule(workflow)
            else:
                # If changed to manual, deregister existing celery task
                try:
                    from django_celery_beat.models import PeriodicTask
                    if workflow.celery_task_name:
                        PeriodicTask.objects.filter(name=workflow.celery_task_name).delete()
                        workflow.celery_task_name = ''
                        workflow.save(update_fields=['celery_task_name'])
                except Exception:
                    pass

            try:
                from logs.models import AuditLog
                AuditLog.objects.create(
                    user=request.user,
                    action=f'Edited Workflow: {workflow.name}',
                    entity_type='Workflow',
                    entity_id=workflow.id,
                    details={'schedule': workflow.schedule_type},
                    ip_address=request.META.get('REMOTE_ADDR'),
                    level='info',
                )
            except Exception:
                pass

            messages.success(request, f'Workflow "{workflow.name}" updated successfully.')
            return redirect('workflows:detail', workflow_id=workflow.id)

        except Exception as e:
            messages.error(request, f'Error updating workflow: {str(e)}')

    return render(request, 'workflows/edit.html', {
        'workflow': workflow,
        'mappings': mappings,
        'is_edit': True,
    })


def _register_celery_schedule(workflow):
    """Register a workflow with Celery Beat for periodic execution."""
    try:
        from django_celery_beat.models import PeriodicTask, CrontabSchedule
        import json

        if workflow.schedule_type == 'daily':
            hour = workflow.schedule_time.hour if workflow.schedule_time else 0
            minute = workflow.schedule_time.minute if workflow.schedule_time else 0
            crontab, _ = CrontabSchedule.objects.get_or_create(
                minute=str(minute), hour=str(hour),
                day_of_week='*', day_of_month='*', month_of_year='*',
            )
            task_fn = 'workflows.tasks.execute_workflow_task'
            task_args = json.dumps([workflow.id])

        elif workflow.schedule_type == 'weekly':
            hour = workflow.schedule_time.hour if workflow.schedule_time else 0
            minute = workflow.schedule_time.minute if workflow.schedule_time else 0
            day = workflow.schedule_day if workflow.schedule_day is not None else 0
            crontab, _ = CrontabSchedule.objects.get_or_create(
                minute=str(minute), hour=str(hour),
                day_of_week=str(day), day_of_month='*', month_of_year='*',
            )
            task_fn = 'workflows.tasks.execute_workflow_task'
            task_args = json.dumps([workflow.id])

        elif workflow.schedule_type == 'monthly':
            hour = workflow.schedule_time.hour if workflow.schedule_time else 0
            minute = workflow.schedule_time.minute if workflow.schedule_time else 0
            day = workflow.schedule_day if workflow.schedule_day else 1
            crontab, _ = CrontabSchedule.objects.get_or_create(
                minute=str(minute), hour=str(hour),
                day_of_week='*', day_of_month=str(day), month_of_year='*',
            )
            task_fn = 'workflows.tasks.execute_workflow_task'
            task_args = json.dumps([workflow.id])



        elif workflow.schedule_type == 'custom_cron' and workflow.cron_expression:
            parts = workflow.cron_expression.split()
            if len(parts) == 5:
                crontab, _ = CrontabSchedule.objects.get_or_create(
                    minute=parts[0], hour=parts[1],
                    day_of_week=parts[4], day_of_month=parts[2], month_of_year=parts[3],
                )
            else:
                return
            task_fn = 'workflows.tasks.execute_workflow_task'
            task_args = json.dumps([workflow.id])
        else:
            return

        task_name = f'workflow_{workflow.id}_{workflow.name}'
        PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                'task': task_fn,
                'crontab': crontab,
                'args': task_args,
                'enabled': workflow.is_active,
            }
        )
        workflow.celery_task_name = task_name
        workflow.save(update_fields=['celery_task_name'])

    except ImportError:
        logger.warning("django-celery-beat not available, skipping schedule registration")
    except Exception as e:
        logger.error(f"Failed to register Celery schedule: {e}")


# ─── API Endpoints ─────────────────────────────────────────────────────────────

@login_required
@contributor_or_admin_required
@require_POST
def api_trigger_workflow(request, workflow_id):
    """Manually trigger a workflow."""
    if hasattr(request.user, 'profile') and request.user.profile.role == 'auditor':
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
    workflow = get_object_or_404(Workflow, id=workflow_id)

    try:
        from .tasks import execute_workflow_task
        execute_workflow_task.delay(workflow.id, 'manual')
    except Exception:
        from validations.models import ETLRun
        from validations.engine import ETLEngine
        run = ETLRun.objects.create(
            mapping=workflow.mapping,
            workflow=workflow,
            trigger_type='manual',
            status='pending',
            selected_columns=workflow.selected_columns,
        )
        engine = ETLEngine(run)
        try:
            engine.execute()
            if workflow.created_by:
                from dashboard.models import Notification
                status_text = "Passed" if run.failed_checks == 0 else "Failed"
                Notification.objects.create(
                    user=workflow.created_by,
                    title=f"Workflow '{workflow.name}' Completed",
                    message=f"Validation Run {run.id} finished.\nStatus: {status_text} ({run.passed_checks}/{run.total_checks} checks passed)",
                    level='success' if run.failed_checks == 0 else 'warning'
                )
        except Exception as e:
            if workflow.created_by:
                from dashboard.models import Notification
                Notification.objects.create(
                    user=workflow.created_by,
                    title=f"Workflow '{workflow.name}' Failed",
                    message=f"Execution failed due to error: {e}",
                    level='error'
                )

    return JsonResponse({'success': True})


@login_required
@contributor_or_admin_required
@require_POST
def api_toggle_workflow(request, workflow_id):
    """Toggle workflow active state."""
    if hasattr(request.user, 'profile') and request.user.profile.role == 'auditor':
        return JsonResponse({'success': False, 'error': 'Permission denied.'}, status=403)
    workflow = get_object_or_404(Workflow, id=workflow_id)
    data = json.loads(request.body) if request.body else {}
    workflow.is_active = data.get('is_active', not workflow.is_active)
    workflow.save(update_fields=['is_active'])

    try:
        from django_celery_beat.models import PeriodicTask
        if workflow.celery_task_name:
            PeriodicTask.objects.filter(name=workflow.celery_task_name).update(enabled=workflow.is_active)
    except Exception:
        pass

    return JsonResponse({'success': True, 'is_active': workflow.is_active})





@login_required
@contributor_or_admin_required
@require_POST
def workflow_delete_view(request, workflow_id):
    """Delete a workflow."""
    if hasattr(request.user, 'profile') and request.user.profile.role == 'auditor':
        messages.error(request, 'Permission denied.')
        return redirect('workflows:list')
    
    workflow = get_object_or_404(Workflow, id=workflow_id)
    name = workflow.name
    
    # Deregister Celery Beat task if registered
    try:
        from django_celery_beat.models import PeriodicTask
        if workflow.celery_task_name:
            PeriodicTask.objects.filter(name=workflow.celery_task_name).delete()
    except Exception:
        pass
        
    workflow.delete()
    
    try:
        from logs.models import AuditLog
        AuditLog.objects.create(
            user=request.user,
            action=f'Deleted Workflow: {name}',
            entity_type='Workflow',
            entity_id=workflow_id,
            ip_address=request.META.get('REMOTE_ADDR'),
            level='warning',
        )
    except Exception:
        pass
        
    messages.success(request, f'Workflow "{name}" deleted successfully.')
    return redirect('workflows:list')


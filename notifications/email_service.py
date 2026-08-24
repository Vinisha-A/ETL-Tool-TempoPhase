import os
import logging
from django.core.mail import EmailMessage
from django.utils import timezone
from django.conf import settings
from workflows.models import EmailNotification
from .report_generator import generate_excel_report

logger = logging.getLogger('validations')

def send_validation_email(run, workflow=None, recipient_email=None):
    """
    Constructs, logs, and sends an automated email notification after a validation run execution.
    """
    if not workflow:
        workflow = run.workflow
        
    if not recipient_email:
        if workflow and workflow.recipient_email:
            recipient_email = workflow.recipient_email
        elif run.triggered_by and run.triggered_by.email:
            recipient_email = run.triggered_by.email

    if not recipient_email:
        logger.warning(f"No recipient email resolved for ETLRun {run.id}. Skipping email notification.")
        return None

    # Step 1: Generate Excel Report
    filepath = None
    try:
        filepath = generate_excel_report(run)
    except Exception as e:
        logger.error(f"Failed to generate report for run {run.id}: {e}")

    # Step 2: Formulate Subject and Body
    workflow_name = workflow.name if workflow else run.mapping.name
    description = workflow.description if (workflow and workflow.description) else (run.mapping.description or "No description provided")
    pipeline_name = run.mapping.name
    execution_type = "Scheduled" if run.trigger_type == 'scheduled' else "On Demand"
    
    # Status formatting: Success / Failed / Partially Successful
    if run.status == 'failed':
        status_val = 'Failed'
    elif run.failed_checks == 0:
        status_val = 'Success'
    elif run.passed_checks > 0:
        status_val = 'Partially Successful'
    else:
        status_val = 'Failed'

    started_at_str = run.started_at.strftime('%Y-%m-%d %I:%M %p') if run.started_at else 'N/A'
    completed_at_str = run.completed_at.strftime('%Y-%m-%d %I:%M %p') if run.completed_at else 'N/A'

    subject = f"[ETL Job] Workflow Execution Status - {workflow_name}"
    
    triggered_by_name = (run.triggered_by.get_full_name() or run.triggered_by.username) if run.triggered_by else "System"

    body = (
        f"Dear User,\n\n"
        f"The workflow execution has completed.\n\n"
        f"Workflow Name: {workflow_name}\n"
        f"Description: {description}\n"
        f"Pipeline Name: {pipeline_name}\n"
        f"Execution Type: {execution_type}\n"
        f"Status: {status_val}\n"
        f"Started At: {started_at_str}\n"
        f"Completed At: {completed_at_str}\n\n"
        f"Total Steps: {run.total_checks}\n"
        f"Extracted: {run.records_extracted}\n"
        f"Loaded: {run.records_loaded}\n\n"
        f"Triggered By User Name: {triggered_by_name}\n"
        f"Recipient Email ID: {recipient_email}\n\n"
        f"Please find the attached ETL execution report.\n\n"
        f"Regards,\n"
        f"Team DataBridge"
    )

    # Step 3: Store Email Log (pending status first)
    notification = EmailNotification.objects.create(
        workflow=workflow,
        run=run,
        recipient_email=recipient_email,
        subject=subject,
        email_body=body,
        attachment_path=filepath,
        sent_status='pending',
    )

    # Step 4: Send Email
    try:
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@hdfc.com')
        
        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[recipient_email],
        )
        
        if filepath and os.path.exists(filepath):
            email.attach_file(filepath)
            
        email.send()
        
        notification.sent_status = 'success'
        notification.sent_time = timezone.now()
        notification.save()
        logger.info(f"Email notification successfully sent to {recipient_email} for ETLRun {run.id}")
        
    except Exception as e:
        notification.sent_status = 'failed'
        err_msg = str(e).strip()
        is_none_err = (
            not err_msg or 
            err_msg.lower() in ('none', '', '(none, none)', 'none, none', '(none,)', 'none,', '("none", "none")') or
            ('none' in err_msg.lower() and ('(' in err_msg or ',' in err_msg))
        )
        if is_none_err:
            err_msg = f"SMTP/Connection Error ({type(e).__name__}): Connection to the mail server failed. Please check your SMTP settings in settings.py / .env and VDI network permissions."
        notification.error_message = err_msg
        notification.save()
        logger.error(f"Failed sending validation email to {recipient_email} for ETLRun {run.id}: {e}")

    return notification

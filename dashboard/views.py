from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q

from connections.models import DataConnection
from mappings.models import Mapping, ETLStep
from validations.models import ETLRun, ETLResult
from workflows.models import Workflow
from logs.models import AuditLog
from django.shortcuts import get_object_or_404
from django.http import JsonResponse


@login_required
def dashboard_view(request):
    """Main dashboard with summary statistics and recent activity."""

    # Stats
    total_connections = DataConnection.objects.filter(is_active=True).count()
    total_mappings = Mapping.objects.filter(is_active=True).count()
    active_workflows = Workflow.objects.filter(is_active=True).count()

    # Recent validation runs
    recent_runs = ETLRun.objects.select_related('mapping', 'triggered_by').all()[:10]

    # Overall completed vs failed workflow/validation runs
    workflows_completed = ETLRun.objects.filter(status='completed').count()
    workflows_failed = ETLRun.objects.filter(status='failed').count()

    # Recent logs
    recent_logs = AuditLog.objects.select_related('user').all()[:10]

    # Connections list for quick access and dropdowns
    connections = DataConnection.objects.filter(is_active=True)
    operations = ETLStep.OPERATION_CHOICES

    context = {
        'total_connections': total_connections,
        'total_mappings': total_mappings,
        'active_workflows': active_workflows,
        'workflows_completed': workflows_completed,
        'workflows_failed': workflows_failed,
        'recent_runs': recent_runs,
        'recent_logs': recent_logs,
        'connections': connections,
        'operations': operations,
    }
    return render(request, 'dashboard/index.html', context)


import json
from django.http import JsonResponse
from .models import FormDraft

@login_required
def api_save_draft(request):
    """Save (create or update) form progress draft."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        page_key = data.get('page_key')
        form_data = data.get('data')
        
        if not page_key or form_data is None:
            return JsonResponse({'success': False, 'error': 'Missing page_key or data'}, status=400)
            
        draft, created = FormDraft.objects.get_or_create(
            user=request.user,
            page_key=page_key,
            status='draft',
            defaults={'data': form_data}
        )
        if not created:
            draft.data = form_data
            draft.save()
            
        return JsonResponse({'success': True, 'message': 'Draft saved successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def api_get_draft(request):
    """Retrieve active form progress draft."""
    page_key = request.GET.get('page_key')
    if not page_key:
        return JsonResponse({'success': False, 'error': 'Missing page_key'}, status=400)
        
    draft = FormDraft.objects.filter(user=request.user, page_key=page_key, status='draft').first()
    if draft:
        return JsonResponse({'success': True, 'data': draft.data})
    return JsonResponse({'success': True, 'data': None})


@login_required
def api_cancel_draft(request):
    """Cancel (discard) form progress draft."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        page_key = data.get('page_key')
        if not page_key:
            return JsonResponse({'success': False, 'error': 'Missing page_key'}, status=400)
            
        FormDraft.objects.filter(user=request.user, page_key=page_key, status='draft').update(status='cancelled')
        return JsonResponse({'success': True, 'message': 'Draft cancelled successfully'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def api_get_notifications(request):
    """Retrieve the latest 10 notifications for the current user."""
    notifications = request.user.notifications.all()[:10]
    unread_count = request.user.notifications.filter(is_read=False).count()
    
    data = []
    for notif in notifications:
        data.append({
            'id': notif.id,
            'title': notif.title,
            'message': notif.message,
            'level': notif.level,
            'is_read': notif.is_read,
            'created_at': notif.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        })
        
    return JsonResponse({
        'success': True,
        'notifications': data,
        'unread_count': unread_count
    })


@login_required
def api_clear_notifications(request):
    """Clear all notifications for the current user."""
    if request.method != 'POST':
         return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    request.user.notifications.all().delete()
    return JsonResponse({'success': True, 'message': 'All notifications cleared'})


# Help Center Operations Data Dictionary
HELP_DATA = {
    'string': {
        'title': 'String Operations Documentation',
        'ops': [
            {
                'alias': 'Null Check',
                'name': 'null_check',
                'logic': 'Counts the number of missing (null) values in the string column.',
                'match': 'The count of missing values matches exactly between source and target.',
                'mismatch': 'The count of missing values differs.'
            },
            {
                'alias': 'Length Check',
                'name': 'length_sum_check',
                'logic': 'Calculates the sum of the lengths of all string values in the column and compares them.',
                'match': 'The total sum of character counts matches exactly between source and target.',
                'mismatch': 'The total sum of character counts differs, suggesting formatting or content differences.'
            },
            {
                'alias': 'Sum Length',
                'name': 'sum_length',
                'logic': 'Similar to length check, aggregates the character lengths of all rows.',
                'match': 'Sum of character lengths matches.',
                'mismatch': 'Sum of character lengths differs.'
            },
            {
                'alias': 'Duplicate Check',
                'name': 'duplicate_check',
                'logic': 'Calculates the count of duplicate string entries in the column.',
                'match': 'The count of duplicate values matches between source and target (both should be 0).',
                'mismatch': 'There is a mismatch of duplicate values.'
            },

            {
                'alias': 'Pattern Match',
                'name': 'pattern_match',
                'logic': 'Verifies string values against a regular expression pattern (wildcards/likes).',
                'match': 'The count of values matching the pattern matches in both tables.',
                'mismatch': 'The count of values matching the pattern differs.'
            },
            {
                'alias': 'Regex Check',
                'name': 'regex_check',
                'logic': 'Verifies string values against a regular expression pattern.',
                'match': 'The count of matching regex patterns matches in both tables.',
                'mismatch': 'The count of matching regex patterns differs.'
            },
            {
                'alias': 'Count',
                'name': 'count',
                'logic': 'Counts the number of non-null string values in the column.',
                'match': 'The count of non-null values matches between source and target.',
                'mismatch': 'The count of non-null values differs.'
            },
            {
                'alias': 'Row Count Match',
                'name': 'row_count',
                'logic': 'Compares the total number of records (including nulls) in the source and target tables.',
                'match': 'The total row count of both tables is identical.',
                'mismatch': 'The total row count of the tables differs.'
            },
            {
                'alias': 'Unique Check',
                'name': 'unique_check',
                'logic': 'Verifies that all values in the column are unique (no duplicates).',
                'match': 'Both source and target columns are unique with zero duplicates.',
                'mismatch': 'One or both columns contain duplicates.'
            },
            {
                'alias': 'Distinct Count',
                'name': 'distinct_count',
                'logic': 'Calculates the number of unique non-null values in the column.',
                'match': 'The count of distinct values matches exactly between source and target.',
                'mismatch': 'The count of distinct values differs.'
            },
            {
                'alias': 'Data Type Check',
                'name': 'data_type_check',
                'logic': 'Verifies that the column data types are compatible character string types (e.g. VARCHAR vs TEXT).',
                'match': 'Datatypes of source and target are compatible character types.',
                'mismatch': 'Data types are incompatible (e.g. integer vs varchar).'
            },

        ]
    },
    'integer': {
        'title': 'Integer Operations Documentation',
        'ops': [
            {
                'alias': 'Null Check',
                'name': 'null_check',
                'logic': 'Counts null integer entries in the column.',
                'match': 'Missing integer count matches exactly between source and target.',
                'mismatch': 'Missing integer count differs.'
            },
            {
                'alias': 'Min Value Check',
                'name': 'min',
                'logic': 'Finds the minimum value in the integer column.',
                'match': 'The minimum value matches exactly between source and target.',
                'mismatch': 'The minimum value differs.'
            },
            {
                'alias': 'Max Value Check',
                'name': 'max',
                'logic': 'Finds the maximum value in the integer column.',
                'match': 'The maximum value matches exactly between source and target.',
                'mismatch': 'The maximum value differs.'
            },
            {
                'alias': 'Sum Check',
                'name': 'sum',
                'logic': 'Sums all integer values in the column.',
                'match': 'Sum of integer values matches exactly between source and target.',
                'mismatch': 'Sum of integer values differs.'
            },
            {
                'alias': 'Average Check',
                'name': 'avg',
                'logic': 'Computes the arithmetic mean of all non-null integers.',
                'match': 'The average value matches exactly between source and target.',
                'mismatch': 'The average value differs.'
            },
            {
                'alias': 'Range Check',
                'name': 'range_check',
                'logic': 'Checks if integer values fall within a specific range.',
                'match': 'The count of integers within the range matches.',
                'mismatch': 'The count of integers within the range differs.'
            },
            {
                'alias': 'Duplicate Check',
                'name': 'duplicate_check',
                'logic': 'Counts duplicate integer values in the column.',
                'match': 'Duplicate integer count matches.',
                'mismatch': 'Duplicate integer count differs.'
            },
            {
                'alias': 'Count',
                'name': 'count',
                'logic': 'Counts non-null integer values in the column.',
                'match': 'Non-null integer count matches exactly.',
                'mismatch': 'Non-null integer count differs.'
            },
            {
                'alias': 'Row Count Match',
                'name': 'row_count',
                'logic': 'Compares total rows in source and target.',
                'match': 'Total row count matches exactly.',
                'mismatch': 'Total row count differs.'
            },
            {
                'alias': 'Unique Check',
                'name': 'unique_check',
                'logic': 'Verifies all integers in the column are unique.',
                'match': 'All integers are unique with no duplicates.',
                'mismatch': 'Non-unique integers are found.'
            },
            {
                'alias': 'Distinct Count',
                'name': 'distinct_count',
                'logic': 'Counts distinct integer values.',
                'match': 'Distinct integer count matches exactly.',
                'mismatch': 'Distinct integer count differs.'
            },
            {
                'alias': 'Data Type Check',
                'name': 'data_type_check',
                'logic': 'Verifies integer data type compatibility (e.g. INT vs BIGINT).',
                'match': 'Integer data types are compatible.',
                'mismatch': 'Integer data types differ.'
            },
            {
                'alias': 'Standard Deviation',
                'name': 'std_dev',
                'logic': 'Computes the standard deviation of all non-null numeric values in the column.',
                'match': 'The standard deviation matches exactly between source and target.',
                'mismatch': 'The standard deviation differs.'
            },
            {
                'alias': 'Variance',
                'name': 'variance',
                'logic': 'Computes the variance of all non-null numeric values in the column.',
                'match': 'The variance matches exactly between source and target.',
                'mismatch': 'The variance differs.'
            },
            {
                'alias': 'Median',
                'name': 'median',
                'logic': 'Computes the median (middle value) of all non-null numeric values in the column.',
                'match': 'The median matches exactly between source and target.',
                'mismatch': 'The median differs.'
            },
            {
                'alias': 'Mode',
                'name': 'mode',
                'logic': 'Finds the most frequent value (mode) in the numeric column.',
                'match': 'The mode matches exactly between source and target.',
                'mismatch': 'The mode differs.'
            }
        ]
    },
    'float': {
        'title': 'Float Operations Documentation',
        'ops': [
            {
                'alias': 'Min Value Check',
                'name': 'min',
                'logic': 'Finds the minimum value in the float column.',
                'match': 'The minimum float value matches exactly between source and target.',
                'mismatch': 'The minimum float value differs.'
            },
            {
                'alias': 'Max Value Check',
                'name': 'max',
                'logic': 'Finds the maximum value in the float column.',
                'match': 'The maximum float value matches exactly between source and target.',
                'mismatch': 'The maximum float value differs.'
            },
            {
                'alias': 'Average Check',
                'name': 'avg',
                'logic': 'Computes the arithmetic mean of all non-null values in the column.',
                'match': 'The average float value matches within float precision (e.g. 1e-6).',
                'mismatch': 'The average float values differ.'
            },
            {
                'alias': 'Sum Check',
                'name': 'sum',
                'logic': 'Sums all floating point values in the column.',
                'match': 'The aggregated sums match within acceptable float tolerance.',
                'mismatch': 'The float sums differ.'
            },
            {
                'alias': 'Precision Check',
                'name': 'precision_check',
                'logic': 'Determine the maximum precision (total number of digits) of the float values in the column.',
                'match': 'The maximum precision matches between source and target.',
                'mismatch': 'The maximum precision differs.'
            },
            {
                'alias': 'Scale Check',
                'name': 'scale_check',
                'logic': 'Determine the maximum scale (number of digits to the right of the decimal point) of the float.',
                'match': 'The maximum scale of decimal/float values matches.',
                'mismatch': 'The maximum scale differs.'
            },
            {
                'alias': 'Duplicate Check',
                'name': 'duplicate_check',
                'logic': 'Identifies duplicate float values in the column.',
                'match': 'The count of duplicate values matches between source and target.',
                'mismatch': 'The duplicate float counts differ.'
            },
            {
                'alias': 'Null Count',
                'name': 'null_check',
                'logic': 'Counts the number of missing (null) values in the float column.',
                'match': 'The count of missing float values is identical.',
                'mismatch': 'The count of missing float values differs.'
            },
            {
                'alias': 'Count',
                'name': 'count',
                'logic': 'Counts the number of non-null values in the float column.',
                'match': 'The count of non-null float values matches.',
                'mismatch': 'The count of non-null float values differs.'
            },
            {
                'alias': 'Row Count Match',
                'name': 'row_count',
                'logic': 'Compares the total number of records (including nulls) in the source and target tables.',
                'match': 'The total row count of both tables is identical.',
                'mismatch': 'The total row count differs.'
            },
            {
                'alias': 'Unique Check',
                'name': 'unique_check',
                'logic': 'Verifies that all values in the float column are unique.',
                'match': 'All values are unique with zero duplicates.',
                'mismatch': 'Duplicate float values are detected.'
            },
            {
                'alias': 'Distinct Count',
                'name': 'distinct_count',
                'logic': 'Calculates the number of unique non-null values in the column.',
                'match': 'The count of distinct float values matches.',
                'mismatch': 'The count of distinct float values differs.'
            },
            {
                'alias': 'Data Type Check',
                'name': 'data_type_check',
                'logic': 'Verifies that the column data types are compatible floating point types (e.g. FLOAT vs DOUBLE).',
                'match': 'Float types are compatible.',
                'mismatch': 'Float types differ.'
            },
            {
                'alias': 'Standard Deviation',
                'name': 'std_dev',
                'logic': 'Computes the standard deviation of all non-null numeric values in the column.',
                'match': 'The standard deviation matches exactly between source and target.',
                'mismatch': 'The standard deviation differs.'
            },
            {
                'alias': 'Variance',
                'name': 'variance',
                'logic': 'Computes the variance of all non-null numeric values in the column.',
                'match': 'The variance matches exactly between source and target.',
                'mismatch': 'The variance differs.'
            },
            {
                'alias': 'Median',
                'name': 'median',
                'logic': 'Computes the median (middle value) of all non-null numeric values in the column.',
                'match': 'The median matches exactly between source and target.',
                'mismatch': 'The median differs.'
            },
            {
                'alias': 'Mode',
                'name': 'mode',
                'logic': 'Finds the most frequent value (mode) in the numeric column.',
                'match': 'The mode matches exactly between source and target.',
                'mismatch': 'The mode differs.'
            }
        ]
    },
    'date': {
        'title': 'Date Operations Documentation',
        'ops': [
            {
                'alias': 'Min Date',
                'name': 'min_date',
                'logic': 'Finds the oldest (minimum) date in the column.',
                'match': 'Minimum date matches exactly between source and target.',
                'mismatch': 'Minimum date differs.'
            },
            {
                'alias': 'Max Date',
                'name': 'max_date',
                'logic': 'Finds the newest (maximum) date in the column.',
                'match': 'Maximum date matches exactly between source and target.',
                'mismatch': 'Maximum date differs.'
            },
            {
                'alias': 'Null Check',
                'name': 'null_check',
                'logic': 'Counts missing date values in the column.',
                'match': 'Missing date count matches exactly between source and target.',
                'mismatch': 'Missing date count differs.'
            },
            {
                'alias': 'Duplicate Check',
                'name': 'duplicate_check',
                'logic': 'Counts duplicate dates.',
                'match': 'Duplicate date counts are identical between source and target.',
                'mismatch': 'Duplicate date counts differ.'
            },
            {
                'alias': 'Count',
                'name': 'count',
                'logic': 'Counts non-null date values.',
                'match': 'Non-null date count matches between source and target.',
                'mismatch': 'Non-null date count differs.'
            },
            {
                'alias': 'Row Count Match',
                'name': 'row_count',
                'logic': 'Compares total row counts.',
                'match': 'Total row count matches exactly.',
                'mismatch': 'Total row count differs.'
            },
            {
                'alias': 'Unique Check',
                'name': 'unique_check',
                'logic': 'Verifies all dates in the column are unique.',
                'match': 'All date values are unique with zero duplicates.',
                'mismatch': 'Duplicate dates are present.'
            },
            {
                'alias': 'Distinct Count',
                'name': 'distinct_count',
                'logic': 'Counts distinct date values.',
                'match': 'Distinct date count matches between source and target.',
                'mismatch': 'Distinct date count differs.'
            },

        ]
    }
}

@login_required
def help_documentation_view(request, category='string'):
    category = category.lower()
    if category not in HELP_DATA:
        category = 'string'
        
    query = request.GET.get('query', '').strip()
    
    selected_category_data = HELP_DATA[category]
    ops_list = selected_category_data['ops']
    
    if query:
        filtered_ops = []
        for op in ops_list:
            if (query.lower() in op['alias'].lower() or
                query.lower() in op['name'].lower() or
                query.lower() in op['logic'].lower() or
                query.lower() in op['match'].lower() or
                query.lower() in op['mismatch'].lower()):
                filtered_ops.append(op)
    else:
        filtered_ops = ops_list

    context = {
        'category': category,
        'title': selected_category_data['title'],
        'operations': filtered_ops,
        'query': query
    }
    return render(request, 'dashboard/help.html', context)


from django.db import models
from django.contrib.auth.models import User
from mappings.models import Mapping, ColumnMapping


class ETLRun(models.Model):
    """A single execution of validation against a mapping."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    TRIGGER_CHOICES = [
        ('manual', 'Manual'),
        ('scheduled', 'Scheduled'),
    ]

    mapping = models.ForeignKey(Mapping, on_delete=models.CASCADE, related_name='etl_runs')
    workflow = models.ForeignKey('workflows.Workflow', on_delete=models.SET_NULL, null=True, blank=True, related_name='etl_runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    triggered_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    trigger_type = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='manual')
    progress = models.IntegerField(default=0)  # 0-100

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Date filter values used for this run
    date_filter_start = models.CharField(max_length=50, null=True, blank=True)
    date_filter_end = models.CharField(max_length=50, null=True, blank=True)

    # Separate Date filter values
    source_date_filter_start = models.CharField(max_length=50, null=True, blank=True)
    source_date_filter_end = models.CharField(max_length=50, null=True, blank=True)
    target_date_filter_start = models.CharField(max_length=50, null=True, blank=True)
    target_date_filter_end = models.CharField(max_length=50, null=True, blank=True)
    selected_columns = models.TextField(blank=True, help_text='Comma-separated columns validated in this run.')

    total_checks = models.IntegerField(default=0)
    passed_checks = models.IntegerField(default=0)
    failed_checks = models.IntegerField(default=0)

    records_extracted = models.IntegerField(default=0)
    records_loaded = models.IntegerField(default=0)

    error_message = models.TextField(blank=True)
    parameters = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            # Resolve source dates
            if self.mapping.source_date_filter_type == 'specific':
                if not self.source_date_filter_start:
                    self.source_date_filter_start = self.mapping.source_date_filter_start
                if not self.source_date_filter_end:
                    self.source_date_filter_end = self.mapping.source_date_filter_start
            elif self.mapping.source_date_filter_type == 'range':
                if not self.source_date_filter_start:
                    self.source_date_filter_start = self.mapping.source_date_filter_start
                if not self.source_date_filter_end:
                    self.source_date_filter_end = self.mapping.source_date_filter_end

            # Resolve target dates
            if self.mapping.target_date_filter_type == 'specific':
                if not self.target_date_filter_start:
                    self.target_date_filter_start = self.mapping.target_date_filter_start
                if not self.target_date_filter_end:
                    self.target_date_filter_end = self.mapping.target_date_filter_start
            elif self.mapping.target_date_filter_type == 'range':
                if not self.target_date_filter_start:
                    self.target_date_filter_start = self.mapping.target_date_filter_start
                if not self.target_date_filter_end:
                    self.target_date_filter_end = self.mapping.target_date_filter_end

            # Resolve common date filters
            if self.mapping.date_filter_type == 'specific':
                if not self.date_filter_start:
                    self.date_filter_start = self.mapping.date_filter_start
                if not self.date_filter_end:
                    self.date_filter_end = self.mapping.date_filter_start
            elif self.mapping.date_filter_type == 'range':
                if not self.date_filter_start:
                    self.date_filter_start = self.mapping.date_filter_start
                if not self.date_filter_end:
                    self.date_filter_end = self.mapping.date_filter_end
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'ETL Run'

    def __str__(self):
        return f"ETL Run {self.id} - {self.mapping.name} ({self.status})"

    @property
    def pass_rate(self):
        if self.total_checks == 0:
            return 0
        return round((self.passed_checks / self.total_checks) * 100, 1)

    @property
    def monitor_run_number(self):
        """Dynamic monitor run sequence number matching Monitor list view."""
        if hasattr(self, 'rev_index') and self.rev_index is not None:
            return self.rev_index
        total_count = ETLRun.objects.count()
        runs_after = ETLRun.objects.filter(id__gt=self.id).count()
        return total_count - runs_after


class ETLResult(models.Model):
    """Individual result for each column-operation check in a validation run."""

    run = models.ForeignKey(ETLRun, on_delete=models.CASCADE, related_name='results')
    column_mapping = models.ForeignKey(ColumnMapping, on_delete=models.SET_NULL, null=True, blank=True)
    source_column = models.CharField(max_length=255, blank=True, null=True)
    target_column = models.CharField(max_length=255, blank=True, null=True)
    operation = models.CharField(max_length=50)
    source_value = models.TextField(blank=True, null=True)
    target_value = models.TextField(blank=True, null=True)
    is_match = models.BooleanField(default=False)
    difference = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        status = "✓" if self.is_match else "✕"
        col = self.source_column or (self.column_mapping.source_column if self.column_mapping else 'Unknown')
        return f"{status} {col}.{self.operation}"

    @property
    def source_op_display(self):
        op = self.operation
        if op == 'extraction':
            return f"Extracted: {self.source_value} rows"
        elif op == 'target_preparation':
            return f"Load Mode: {self.source_value}"
        elif op == 'loading':
            return f"Loaded: {self.source_value} rows"

        op_map = {
            'count': 'Count',
            'row_count': 'Row Count Match',
            'distinct_count': 'Distinct Count',
            'null_check': 'Null Check',
            'data_type_check': 'Data Type Check',
            'duplicate_check': 'Duplicate Check',
            'min': 'Minimum',
            'max': 'Maximum',
            'sum': 'Sum',
            'avg': 'Average',
            'length_sum_check': 'Length Sum Check',
            'sum_length': 'Sum Length',
            'regex_check': 'Regex Check',
            'unique_check': 'Unique Check',
            'range_check': 'Range Check',
            'min_date': 'Min Date',
            'max_date': 'Max Date',
        }
        op_name = op_map.get(op, op.replace('_', ' ').title())
        val = self.source_value if self.source_value is not None else '0'
        return f"{op_name}_src = {val}"

    @property
    def target_op_display(self):
        op = self.operation
        if op in ('extraction', 'target_preparation', 'loading'):
            return f"Status: {self.target_value}"

        op_map = {
            'count': 'Count',
            'row_count': 'Row Count Match',
            'distinct_count': 'Distinct Count',
            'null_check': 'Null Check',
            'data_type_check': 'Data Type Check',
            'duplicate_check': 'Duplicate Check',
            'min': 'Minimum',
            'max': 'Maximum',
            'sum': 'Sum',
            'avg': 'Average',
            'length_sum_check': 'Length Sum Check',
            'sum_length': 'Sum Length',
            'regex_check': 'Regex Check',
            'unique_check': 'Unique Check',
            'range_check': 'Range Check',
            'min_date': 'Min Date',
            'max_date': 'Max Date',
        }
        op_name = op_map.get(op, op.replace('_', ' ').title())
        val = self.target_value if self.target_value is not None else '0'
        return f"{op_name}_target = {val}"

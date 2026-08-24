from django.urls import path
from . import views

app_name = 'validations'

urlpatterns = [
    path('', views.etl_list_view, name='list'),
    path('report/<int:run_id>/', views.etl_report_view, name='report'),
    path('progress/<int:run_id>/', views.etl_progress_view, name='progress'),
    path('export/<int:run_id>/', views.export_report, name='export'),
    path('quick/', views.quick_etl_view, name='quick'),
    path('delete/<int:run_id>/', views.etl_delete_view, name='delete'),
    path('pipeline/<int:mapping_id>/', views.pipeline_monitor_history_view, name='pipeline_history'),
    # API
    path('api/progress/<int:run_id>/', views.api_etl_progress, name='api_progress'),
    path('api/trigger/<int:mapping_id>/', views.api_trigger_etl, name='api_trigger'),
    path('api/validate/<int:mapping_id>/', views.api_validate_pipeline, name='api_validate'),
    path('api/mapping/<int:mapping_id>/rules-metadata/', views.api_mapping_rules_metadata, name='api_mapping_rules_metadata'),
    path('api/send-email/<int:run_id>/', views.api_send_report_email, name='api_send_email'),
]

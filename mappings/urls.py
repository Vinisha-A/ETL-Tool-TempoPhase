from django.urls import path
from . import views

app_name = 'mappings'

urlpatterns = [
    path('', views.mapping_list_view, name='list'),
    path('create/', views.mapping_create_view, name='create'),
    path('<int:mapping_id>/', views.mapping_detail_view, name='detail'),
    path('<int:mapping_id>/edit/', views.mapping_edit_view, name='edit'),
    path('<int:mapping_id>/delete/', views.mapping_delete_view, name='delete'),
    path('api/columns/<int:mapping_id>/', views.api_mapping_columns, name='api_columns'),
    path('groups/create/', views.create_pipeline_group, name='create_group'),
    path('groups/<int:group_id>/rename/', views.rename_pipeline_group, name='rename_group'),
    path('groups/<int:group_id>/assign/', views.assign_group_pipelines, name='assign_group_pipelines'),
    path('groups/<int:group_id>/delete/', views.delete_pipeline_group, name='delete_group'),
    path('folders/create/', views.create_pipeline_group, name='create_folder'),
    path('folders/<int:group_id>/rename/', views.rename_pipeline_group, name='rename_folder'),
    path('folders/<int:group_id>/move/', views.move_pipeline_group, name='move_folder'),
    path('folders/<int:group_id>/assign/', views.assign_group_pipelines, name='assign_folder_pipelines'),
    path('folders/<int:group_id>/delete/', views.delete_pipeline_group, name='delete_folder'),
    path('move/', views.move_mappings_view, name='move_jobs'),
    path('<int:mapping_id>/rename/', views.rename_mapping_view, name='rename_job'),
]

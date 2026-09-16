from django.db import OperationalError, ProgrammingError
from django.db.models import Q
from mappings.models import Mapping, PipelineGroup, PipelineGroupAssignment


def pipeline_groups_context(request):
    """Context processor exposing hierarchical pipeline folders and counts globally for navigation."""
    if not request.user.is_authenticated:
        return {}

    try:
        # 1. Fetch all pipeline folders ordered by parent and name
        folders = list(PipelineGroup.objects.all().order_by('name'))

        # 2. Fetch all assignments
        assignments = PipelineGroupAssignment.objects.all().select_related('group')
        mapping_to_folder = {a.mapping_id: a.group_id for a in assignments}

        # 3. Retrieve all active mappings
        mappings = Mapping.objects.filter(is_active=True)

        # Apply creator filter if present
        selected_creator_name = request.GET.get('created_by_name', '').strip()
        if selected_creator_name:
            mappings = mappings.filter(
                Q(created_by__username__icontains=selected_creator_name) |
                Q(created_by__first_name__icontains=selected_creator_name) |
                Q(created_by__last_name__icontains=selected_creator_name)
            )

        total_pipelines_count = mappings.count()

        # Count mappings per folder
        folder_direct_counts = {}
        unassigned_count = 0
        for m in mappings:
            f_id = mapping_to_folder.get(m.id)
            if f_id:
                folder_direct_counts[f_id] = folder_direct_counts.get(f_id, 0) + 1
            else:
                unassigned_count += 1

    except (OperationalError, ProgrammingError):
        # Database tables do not exist yet
        return {
            'sidebar_folder_tree': [],
            'sidebar_folders': [],
            'sidebar_groups': [{'key': 'all', 'name': 'All Pipelines', 'count': 0, 'is_custom': False}],
            'sidebar_total_count': 0,
            'sidebar_unassigned_count': 0,
            'sidebar_selected_folder': 'all',
            'sidebar_selected_group': 'all',
        }

    # Determine selected folder from request params (?folder=<id> or ?group=custom_<id>)
    selected_param = request.GET.get('folder', '').strip()
    if not selected_param:
        group_param = request.GET.get('group', '').strip()
        if group_param.startswith('custom_'):
            selected_param = group_param.replace('custom_', '')
        elif group_param in ('all', 'other', 'unassigned'):
            selected_param = group_param if group_param != 'other' else 'unassigned'

    if not selected_param:
        selected_param = 'all'

    # Build hierarchical tree
    folder_nodes = {}
    for f in folders:
        folder_nodes[f.id] = {
            'id': f.id,
            'name': f.name,
            'key': f"custom_{f.id}",
            'parent_id': f.parent_id,
            'direct_count': folder_direct_counts.get(f.id, 0),
            'total_count': folder_direct_counts.get(f.id, 0),
            'subfolders': [],
            'level': 0,
            'is_selected': selected_param == str(f.id),
            'has_active_child': False,
        }

    root_folders = []
    for f in folders:
        node = folder_nodes[f.id]
        if f.parent_id and f.parent_id in folder_nodes:
            parent_node = folder_nodes[f.parent_id]
            node['level'] = parent_node['level'] + 1
            parent_node['subfolders'].append(node)
        else:
            root_folders.append(node)

    # Calculate recursive total_count and active child flags
    def compute_totals(node):
        has_active = False
        for child in node['subfolders']:
            child_has_active = compute_totals(child)
            node['total_count'] += child['total_count']
            if child_has_active or child['is_selected']:
                has_active = True
        node['has_active_child'] = has_active
        return has_active or node['is_selected']

    for root in root_folders:
        compute_totals(root)

    # Flatten depth-first for easy linear sidebar rendering with indentation
    flat_folders = []
    def flatten(nodes):
        for n in nodes:
            flat_folders.append({
                'id': n['id'],
                'name': n['name'],
                'key': n['key'],
                'parent_id': n['parent_id'],
                'level': n['level'],
                'direct_count': n['direct_count'],
                'total_count': n['total_count'],
                'has_children': len(n['subfolders']) > 0,
                'is_selected': n['is_selected'],
                'has_active_child': n['has_active_child'],
            })
            if n['subfolders']:
                flatten(n['subfolders'])

    flatten(root_folders)

    # Backward-compatible sidebar_groups list
    sidebar_groups = [
        {'key': 'all', 'name': 'All Pipelines', 'count': total_pipelines_count, 'is_custom': False}
    ]
    for ff in flat_folders:
        sidebar_groups.append({
            'key': ff['key'],
            'id': ff['id'],
            'name': ff['name'],
            'count': ff['total_count'],
            'is_custom': True,
        })
    if unassigned_count > 0:
        sidebar_groups.append({
            'key': 'unassigned',
            'name': 'Unorganized Pipelines',
            'count': unassigned_count,
            'is_custom': False
        })

    return {
        'sidebar_folder_tree': root_folders,
        'sidebar_folders': flat_folders,
        'sidebar_groups': sidebar_groups,
        'sidebar_total_count': total_pipelines_count,
        'sidebar_unassigned_count': unassigned_count,
        'sidebar_selected_folder': selected_param,
        'sidebar_selected_group': request.GET.get('group', 'all').strip(),
        'sidebar_selected_creator_name': selected_creator_name,
    }

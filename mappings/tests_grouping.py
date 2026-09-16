import json
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from mappings.models import Mapping, PipelineGroup, PipelineGroupAssignment, PipelineFolder, PipelineFolderAssignment
from connections.models import DataConnection

class PipelineHierarchyTestCase(TestCase):
    def setUp(self):
        # Create a test user and log in
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.login(username='testuser', password='password123')

        # Create dummy connections
        self.conn_db = DataConnection.objects.create(
            name='Postgres Source',
            connection_type='postgresql',
            host='localhost',
            database_name='src_db',
            created_by=self.user
        )
        self.conn_file = DataConnection.objects.create(
            name='CSV File Source',
            connection_type='csv',
            created_by=self.user
        )
        self.conn_tgt = DataConnection.objects.create(
            name='Postgres Target',
            connection_type='postgresql',
            host='localhost',
            database_name='tgt_db',
            created_by=self.user
        )

        try:
            from accounts.models import UserProfile
            self.profile, _ = UserProfile.objects.get_or_create(user=self.user, defaults={'role': 'admin'})
            self.profile.role = 'admin'
            self.profile.save()
        except ImportError:
            pass

    def test_folder_hierarchy_model_methods(self):
        """Test parent-child folder paths and descendant ID collection."""
        root = PipelineFolder.objects.create(name='Marketing')
        sub1 = PipelineFolder.objects.create(name='Campaigns', parent=root)
        sub2 = PipelineFolder.objects.create(name='2026', parent=sub1)

        self.assertEqual(root.get_full_path_name(), 'Marketing')
        self.assertEqual(sub1.get_full_path_name(), 'Marketing / Campaigns')
        self.assertEqual(sub2.get_full_path_name(), 'Marketing / Campaigns / 2026')

        path_nodes = [f.name for f in sub2.get_path()]
        self.assertEqual(path_nodes, ['Marketing', 'Campaigns', '2026'])

        descendants = root.get_all_descendant_ids()
        self.assertIn(root.id, descendants)
        self.assertIn(sub1.id, descendants)
        self.assertIn(sub2.id, descendants)

    def test_create_and_rename_folder_api(self):
        """Test API endpoints for creating root folders, subfolders, and renaming."""
        create_url = reverse('mappings:create_folder')

        # Create root folder
        resp = self.client.post(create_url, {'name': 'Operations'})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data['success'])
        root_id = data['folder']['id']

        # Create subfolder under Operations
        resp_sub = self.client.post(create_url, {'name': 'Daily Jobs', 'parent_id': root_id})
        self.assertEqual(resp_sub.status_code, 200)
        sub_data = json.loads(resp_sub.content)
        self.assertTrue(sub_data['success'])
        self.assertEqual(sub_data['folder']['parent_id'], root_id)
        sub_id = sub_data['folder']['id']

        # Sibling duplicate name should be rejected
        resp_dup = self.client.post(create_url, {'name': 'Daily Jobs', 'parent_id': root_id})
        self.assertEqual(resp_dup.status_code, 400)

        # Same name under DIFFERENT parent is allowed!
        resp_other = self.client.post(create_url, {'name': 'Daily Jobs'})
        self.assertEqual(resp_other.status_code, 200)

        # Rename subfolder
        rename_url = reverse('mappings:rename_folder', args=[sub_id])
        resp_rename = self.client.post(rename_url, {'name': 'Automated Daily Jobs'})
        self.assertEqual(resp_rename.status_code, 200)
        r_data = json.loads(resp_rename.content)
        self.assertEqual(r_data['name'], 'Automated Daily Jobs')

    def test_folder_filtering_and_breadcrumbs(self):
        """Verify navigation across folders, subfolders, and breadcrumbs in list view."""
        folder_sales = PipelineFolder.objects.create(name='Sales')
        folder_q1 = PipelineFolder.objects.create(name='Q1', parent=folder_sales)

        m1 = Mapping.objects.create(name='Sales Direct Pipe', source_connection=self.conn_db, target_connection=self.conn_tgt, created_by=self.user)
        m2 = Mapping.objects.create(name='Sales Q1 Pipe', source_connection=self.conn_db, target_connection=self.conn_tgt, created_by=self.user)
        m3 = Mapping.objects.create(name='Unorganized Pipe', source_connection=self.conn_db, target_connection=self.conn_tgt, created_by=self.user)

        PipelineFolderAssignment.objects.create(group=folder_sales, mapping=m1)
        PipelineFolderAssignment.objects.create(group=folder_q1, mapping=m2)

        # 1. All Pipelines
        resp = self.client.get(reverse('mappings:list') + '?folder=all')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context['mappings']), 3)
        # Root subfolders should include 'Sales'
        sf_names = [f.name for f in resp.context['subfolders']]
        self.assertIn('Sales', sf_names)

        # 2. View Sales folder
        resp_sales = self.client.get(reverse('mappings:list') + f'?folder={folder_sales.id}')
        self.assertEqual(resp_sales.status_code, 200)
        self.assertEqual(len(resp_sales.context['mappings']), 1)
        self.assertEqual(resp_sales.context['mappings'][0], m1)
        # Subfolders in Sales should include Q1
        sf_sales = [f.name for f in resp_sales.context['subfolders']]
        self.assertIn('Q1', sf_sales)
        # Breadcrumbs check
        bc_names = [b['name'] for b in resp_sales.context['breadcrumbs']]
        self.assertEqual(bc_names, ['All Pipelines', 'Sales'])

        # 3. View Unorganized Pipelines
        resp_unorg = self.client.get(reverse('mappings:list') + '?folder=unassigned')
        self.assertEqual(resp_unorg.status_code, 200)
        self.assertEqual(len(resp_unorg.context['mappings']), 1)
        self.assertEqual(resp_unorg.context['mappings'][0], m3)

    def test_assign_and_delete_folder(self):
        """Test assigning mappings and deleting folder."""
        folder = PipelineFolder.objects.create(name='Finance')
        m1 = Mapping.objects.create(name='Payroll', source_connection=self.conn_db, target_connection=self.conn_tgt, created_by=self.user)
        m2 = Mapping.objects.create(name='Invoices', source_connection=self.conn_db, target_connection=self.conn_tgt, created_by=self.user)

        # Assign both to Finance
        assign_url = reverse('mappings:assign_folder_pipelines', args=[folder.id])
        resp = self.client.post(assign_url, json.dumps({'mapping_ids': [m1.id, m2.id]}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        self.assertEqual(m1.folder, folder)
        self.assertEqual(m2.folder, folder)

        # Delete folder
        del_url = reverse('mappings:delete_folder', args=[folder.id])
        resp_del = self.client.post(del_url)
        self.assertEqual(resp_del.status_code, 200)
        self.assertFalse(PipelineFolder.objects.filter(id=folder.id).exists())
        # Mappings are now unorganized
        m1.refresh_from_db()
        self.assertIsNone(m1.folder)

    from unittest.mock import patch

    @patch('connections.connector.ConnectorEngine.test_connection', return_value=(True, 'OK'))
    def test_file_connection_custom_sql_validation(self, mock_test_conn):
        """Verify that flat file connections with custom queries produce a clear validation error."""
        mapping_file_sql = Mapping.objects.create(
            name='Invalid File SQL Pipe',
            source_connection=self.conn_file,
            target_connection=self.conn_tgt,
            query_type='custom_query',
            custom_query='SELECT * FROM my_csv',
            created_by=self.user
        )

        resp = self.client.get(reverse('validations:api_validate', args=[mapping_file_sql.id]))
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertFalse(data['success'])
        # Check that error explicitly mentions flat file connections
        sql_check = next((v for v in data['validations'] if v['name'] == 'Source SQL Query Syntax'), None)
        self.assertIsNotNone(sql_check)
        self.assertEqual(sql_check['status'], 'error')
        self.assertIn('flat file connections', sql_check['message'].lower())

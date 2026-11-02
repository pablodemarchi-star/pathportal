import json
import os
import unittest
from datetime import date
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from app import create_app, db
from app.models import ExamSession, ExamSessionYear, MarketingMaterialInfo, MarketingMaterialShare


class MarketingMaterialTest(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.context = self.app.app_context()
        self.context.push()
        db.drop_all()
        db.create_all()
        db.session.add_all([ExamSessionYear(year=2026), ExamSessionYear(year=2025)])
        self.first = self.record('Patagonian RW', 2026, 'Onsite')
        self.second = self.record('Patagonian LS', 2026, 'Online')
        self.old = self.record('Old session', 2025, 'Onsite')
        self.first.concat_session_ids = json.dumps([self.second.id])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state.update(user='admin', csrf_token='test')
        self.info_url = f'/marketing-material/sessions/{self.first.id}/info'

    def record(self, name, year, format):
        record = ExamSession(exam_session_name=name, category='Path School', status='Pending',
            session_date=date(year, 11, 10), shifts='Morning', modules='Speaking', format=format,
            city='Bariloche', province='Rio Negro', session_pictures_folder_url='https://example.com/photos')
        db.session.add(record)
        db.session.flush()
        return record

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def share(self):
        response = self.client.post('/marketing-material/share', data={'csrf_token':'test', 'action':'enable'})
        self.assertEqual(response.status_code, 302)
        return '/marketing-material/shared/' + db.session.get(MarketingMaterialShare, 1).token

    def test_group_latest_year_all_formats_and_unique_values(self):
        page = self.client.get('/marketing-material').get_data(as_text=True)
        self.assertIn('Patagonian RW', page)
        self.assertIn('Patagonian LS', page)
        self.assertNotIn('Old session', page)
        self.assertEqual(page.count('data-marketing-row='), 1)
        self.assertEqual(page.count('https://example.com/photos'), 1)
        self.assertEqual(page.count('Bariloche, Rio Negro'), 1)
        self.assertIn('>Onsite</span>', page)
        self.assertIn('>Online</span>', page)
        self.assertIn('data-instructions-url=', page)

    def test_save_sanitize_synchronize_and_public_read_only(self):
        response = self.client.post(self.info_url, data={'csrf_token':'test', 'title':'A special day',
            'instructions':'<p><b>Welcome</b><img src=x onerror=bad()></p>'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MarketingMaterialInfo.query.count(), 2)
        for note in MarketingMaterialInfo.query.all():
            self.assertEqual(note.title, 'A special day')
            self.assertNotIn('<img', note.content)
        public_url = self.share()
        anonymous = self.app.test_client()
        page = anonymous.get(public_url).get_data(as_text=True)
        self.assertIn('<b>Welcome</b>', page)
        self.assertIn('A special day', page)
        self.assertIn('data-marketing-copy=', page)
        self.assertIn('data-marketing-open=', page)
        for private in ('data-instructions-editor', 'csrf_token', 'data-instructions-url', '/exam-session-planner', 'Create shared link'):
            self.assertNotIn(private, page)
        self.client.post(self.info_url, data={'csrf_token':'test','instructions':'<p>Updated</p>'})
        self.assertIn('<p>Updated</p>', anonymous.get(public_url).get_data(as_text=True))
        self.assertEqual(anonymous.post(self.info_url, data={'instructions':'Changed'}).status_code, 302)

    def test_link_disable_regenerate_and_unknown_token(self):
        url = self.share()
        self.assertEqual(self.app.test_client().get(url).status_code, 200)
        self.client.post('/marketing-material/share', data={'csrf_token':'test','action':'disable'})
        self.assertEqual(self.app.test_client().get(url).status_code, 410)
        self.client.post('/marketing-material/share', data={'csrf_token':'test','action':'regenerate'})
        self.assertEqual(self.app.test_client().get(url).status_code, 404)
        self.assertEqual(self.app.test_client().get('/marketing-material/shared/unknown').status_code, 404)

    def test_folder_conflict_only_blocks_affected_group(self):
        self.second.session_pictures_folder_url = 'https://example.com/other'
        self.record('Independent', 2026, 'Online at exam centre')
        db.session.commit()
        page = self.client.get('/marketing-material').get_data(as_text=True)
        self.assertIn('Conflicting Session pictures folders', page)
        self.assertEqual(page.count('>Access ↗</a>'), 1)
        public = self.client.get(self.share()).get_data(as_text=True)
        self.assertNotIn('Conflicting Session pictures folders', public)
        self.assertEqual(public.count('>Access ↗</a>'), 1)

    def test_permissions_csrf_and_validation(self):
        self.assertEqual(self.app.test_client().get('/marketing-material').status_code, 302)
        self.assertEqual(self.client.post(self.info_url, data={'instructions':'text'}).status_code, 400)
        self.assertEqual(self.client.post('/marketing-material/share', data={'action':'enable'}).status_code, 400)
        with patch('app.routes.user_can_edit', return_value=False):
            self.assertEqual(self.client.post(self.info_url, data={'csrf_token':'test'}).status_code, 403)
            self.assertEqual(self.client.post('/marketing-material/share', data={'csrf_token':'test','action':'enable'}).status_code, 403)
            page = self.client.get('/marketing-material').get_data(as_text=True)
            self.assertNotIn('data-instructions-editor', page)
        for data in ({'title':'x'*201}, {'instructions':'x'*50001}):
            self.assertEqual(self.client.post(self.info_url, data={'csrf_token':'test', **data}).status_code, 400)
        self.assertEqual(MarketingMaterialInfo.query.count(), 0)

    def test_cross_year_group_kept_whole(self):
        self.second.session_date = date(2025, 12, 31)
        db.session.commit()
        page = self.client.get('/marketing-material').get_data(as_text=True)
        self.assertIn('Patagonian LS', page)
        self.assertIn('31/12/2025', page)
        self.assertEqual(page.count('data-marketing-row='), 1)

    def test_invalid_folder_and_session_deletion(self):
        self.first.session_pictures_folder_url = 'javascript:alert(1)'
        self.second.session_pictures_folder_url = ''
        db.session.commit()
        page = self.client.get('/marketing-material').get_data(as_text=True)
        self.assertIn('Invalid Session pictures folder URL.', page)
        self.assertNotIn('href="javascript:', page)
        self.client.post(self.info_url, data={'csrf_token':'test', 'instructions':'<p>Note</p>'})
        db.session.delete(self.first)
        db.session.commit()
        self.assertEqual(MarketingMaterialInfo.query.count(), 1)

    def test_sort_first_four_columns_in_portal_and_public_view(self):
        other = self.record('Alpha session', 2026, 'Online at exam centre')
        other.city = 'Azul'
        other.session_date = date(2026, 1, 1)
        db.session.commit()
        public_url = self.share()
        for base in ('/marketing-material', public_url):
            for column in ('exam_session', 'date', 'format', 'city'):
                ascending = self.client.get(f'{base}?sort={column}&dir=asc').get_data(as_text=True)
                descending = self.client.get(f'{base}?sort={column}&dir=desc').get_data(as_text=True)
                first_marker = f'data-marketing-row="{self.first.id}"'
                other_marker = f'data-marketing-row="{other.id}"'
                self.assertLess(ascending.index(other_marker), ascending.index(first_marker))
                self.assertLess(descending.index(first_marker), descending.index(other_marker))
                self.assertEqual(ascending.count('class="table-sort'), 4)
                self.assertIn('aria-sort="ascending"', ascending)
                self.assertIn(f'{base}?sort={column}&amp;dir=desc', ascending)
                self.assertEqual(ascending.count('data-marketing-row='), 2)
        self.assertEqual(self.client.get('/marketing-material?sort=invalid&dir=invalid').status_code, 200)

    def test_search_and_format_filters_preserve_groups_and_sorting(self):
        other = self.record('Independent session', 2026, 'Online at exam centre')
        db.session.commit()
        public_url = self.share()
        for base in ('/marketing-material', public_url):
            page = self.client.get(base + '?q=PATAGONIAN+LS&format=Online').get_data(as_text=True)
            self.assertIn('Patagonian RW', page)
            self.assertIn('Patagonian LS', page)
            self.assertNotIn('Independent session', page)
            self.assertEqual(page.count('data-marketing-row='), 1)
            self.assertIn('q=PATAGONIAN+LS&amp;format=Online', page)
            self.assertIn('value="Online" selected', page)
            self.assertIn('name="q"', page)
            page = self.client.get(base + '?format=Online+at+exam+centre&sort=city&dir=desc').get_data(as_text=True)
            self.assertIn(f'data-marketing-row="{other.id}"', page)
            self.assertNotIn('Patagonian RW', page)
            page = self.client.get(base + '?q=unknown').get_data(as_text=True)
            self.assertIn('No exam sessions match your filters.', page)
            self.assertNotIn('data-marketing-row=', page)
            page = self.client.get(base + '?q=Independent&format=Onsite').get_data(as_text=True)
            self.assertIn('No exam sessions match your filters.', page)

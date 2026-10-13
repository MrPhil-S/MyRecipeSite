import os
import re
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from recipe_app_v2.database import ReadOnlySession, get_session
from recipe_app_v2.main import app
from recipe_app_v2.models import Base, Query_History, Recipe


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add_all([Recipe(name='Chicken soup'), Recipe(name='Chicken soup with noodles')])
            session.commit()

        def sessions():
            with ReadOnlySession(self.engine, autoflush=False) as session:
                yield session
        app.dependency_overrides[get_session] = sessions
        self.environment = patch.dict(os.environ, {'RECIPE_DEV_WRITES': '1'})
        self.environment.start()
        self.writer = patch('recipe_app_v2.search_history.get_write_engine', return_value=self.engine)
        self.writer.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.writer.stop()
        self.environment.stop()
        self.engine.dispose()

    def token(self):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.client.get('/').text)[1]

    def histories(self):
        with Session(self.engine) as session:
            return list(session.scalars(select(Query_History.query_text).order_by(Query_History.query_history_id)))

    def test_live_queries_suggestions_sort_and_pagination_never_save(self):
        token = self.token()
        for q in ('c', 'ch', 'chicken'):
            self.assertEqual(self.client.get('/', params={'q': q}, headers={'HX-Request': 'true'}).status_code, 200)
            self.assertEqual(self.client.get('/search/history', params={'q': q}).status_code, 200)
        self.client.get('/?page=2&sort=name&q=chicken')
        response = self.client.post('/search', data={'q': 'chicken', 'sort': 'name',
            'intent': 'sort', 'csrf_token': token}, headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.histories(), [])

    def test_navbar_search_works_when_first_page_is_tags_or_aliases(self):
        for path in ('/tags/collections', '/image-aliases'):
            self.client.cookies.clear()
            body = self.client.get(path).text
            self.assertEqual(body.count('id="navbar-query"'), 1)
            token = re.search(r'name="csrf_token" value="([^"]+)"', body)[1]
            response = self.client.post('/search', data={'q': 'chicken', 'csrf_token': token}, follow_redirects=False)
            self.assertEqual(response.status_code, 303)
        self.assertEqual(self.histories(), ['chicken', 'chicken'])

    def test_explicit_search_saves_complete_query_and_canonical_url(self):
        token = self.token()
        data = {'q': '  chicken soup  ', 'sort': 'name', 'intent': 'search', 'csrf_token': token}
        response = self.client.post('/search', data=data, headers={'HX-Request': 'true'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['HX-Push-Url'], '/?page=1&sort=name&q=chicken+soup')
        self.assertNotIn('csrf', response.headers['HX-Push-Url'])
        self.assertEqual(self.histories(), ['chicken soup'])
        response = self.client.post('/search', data=data, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/?page=1&sort=name&q=chicken+soup')
        self.assertEqual(self.histories(), ['chicken soup', 'chicken soup'])
        body = self.client.get('/search/history').text
        self.assertEqual(body.count('data-history-query="chicken soup"'), 1)

    def test_only_searches_with_more_than_one_result_are_saved(self):
        token = self.token()
        for query in ('missing recipe', 'chicken soup with noodles'):
            response = self.client.post('/search', data={'q': query, 'csrf_token': token}, headers={'HX-Request': 'true'})
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.histories(), [])
        self.client.post('/search', data={'q': 'chicken', 'csrf_token': token})
        self.assertEqual(self.histories(), ['chicken'])

    def test_recent_deduplication_filtering_literal_wildcards_and_escaping(self):
        now = datetime.now()
        with Session(self.engine) as session:
            session.add_all([
                Query_History(query_text='CHICKEN', query_dt=now - timedelta(days=1)),
                Query_History(query_text='chicken', query_dt=now),
                Query_History(query_text='100%_special', query_dt=now),
                Query_History(query_text='<script>unsafe</script>', query_dt=now),
            ])
            session.commit()
        body = self.client.get('/search/history').text
        self.assertEqual(body.count('data-history-query="chicken"'), 1)
        self.assertNotIn('data-history-query="CHICKEN"', body)
        self.assertIn('&lt;script&gt;', body)
        self.assertNotIn('<script>unsafe', body)
        body = self.client.get('/search/history?q=%25_').text
        self.assertIn('100%_special', body)
        self.assertNotIn('chicken', body)

    def test_empty_long_disabled_and_invalid_submissions_do_not_save(self):
        token = self.token()
        for q in ('   ', 'x' * 101):
            response = self.client.post('/search', data={'q': q, 'csrf_token': token}, headers={'HX-Request': 'true'})
            self.assertEqual(response.status_code, 200)
        self.assertIn('too long', response.text)
        with patch.dict(os.environ, {'RECIPE_DEV_WRITES': '0'}):
            response = self.client.post('/search', data={'q': 'chicken', 'csrf_token': token}, headers={'HX-Request': 'true'})
            self.assertIn('saving is disabled', response.text)
        self.assertEqual(self.client.post('/search', data={'q': 'chicken', 'csrf_token': 'forged'}).status_code, 403)
        self.assertEqual(self.client.post('/search', data={'q': 'x' * 201, 'csrf_token': token}).status_code, 422)
        self.assertEqual(self.histories(), [])

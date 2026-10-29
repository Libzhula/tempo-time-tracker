from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from app import Problem, Tracker, make_handler, ThreadingHTTPServer


def ts(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'test.sqlite3'
        self.now = ts('2026-10-29T10:00:00')
        self.tracker = Tracker(self.path, lambda: self.now)
        self.alex = self.tracker.add_employee('Alex Example')['id']

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_flow_and_persistence(self):
        self.tracker.start(self.alex, 'Build a demo')
        self.now += 3661
        self.tracker.stop(self.alex)
        reopened = Tracker(self.path, lambda: self.now)
        report = reopened.report('2026-10-29', '2026-10-29')
        self.assertEqual(report['total_seconds'], 3661)
        self.assertEqual(report['entries'][0]['description'], 'Build a demo')
        self.assertIsNone(reopened.employees()[0]['timer_id'])

    def test_running_timer_survives_restart(self):
        self.tracker.start(self.alex, 'Research')
        self.now += 120
        reopened = Tracker(self.path, lambda: self.now)
        self.assertIsNotNone(reopened.employees()[0]['timer_id'])
        self.assertEqual(reopened.report('2026-10-29', '2026-10-29')['total_seconds'], 120)

    def test_repeated_start_and_stop(self):
        self.tracker.start(self.alex, 'First')
        with self.assertRaises(Problem) as exc:
            self.tracker.start(self.alex, 'Second')
        self.assertEqual(exc.exception.status, 409)
        self.now += 20
        self.tracker.stop(self.alex)
        self.now += 80
        with self.assertRaises(Problem):
            self.tracker.stop(self.alex)
        self.assertEqual(self.tracker.report('2026-10-29', '2026-10-29')['total_seconds'], 20)

    def test_concurrent_start_creates_exactly_one_timer(self):
        barrier = threading.Barrier(6)
        def start(_):
            barrier.wait()
            try:
                self.tracker.start(self.alex, 'Parallel request')
                return 201
            except Problem as error:
                return error.status
        with ThreadPoolExecutor(max_workers=6) as pool:
            statuses = list(pool.map(start, range(6)))
        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(409), 5)

    def test_empty_report_includes_zero_total_employees(self):
        report = self.tracker.report('2026-10-29', '2026-10-29')
        self.assertEqual(report['entries'], [])
        self.assertEqual(report['total_seconds'], 0)
        self.assertEqual(report['employees'][0]['seconds'], 0)

    def test_cross_midnight_clips_both_boundaries(self):
        self.now = ts('2026-10-28T23:30:00')
        self.tracker.start(self.alex, 'Overnight')
        self.now = ts('2026-10-30T00:30:00')
        self.tracker.stop(self.alex)
        report = self.tracker.report('2026-10-29', '2026-10-29')
        self.assertEqual(report['total_seconds'], 86400)
        self.assertEqual(self.tracker.report('2026-10-28', '2026-10-28')['total_seconds'], 1800)
        self.assertEqual(self.tracker.report('2026-10-30', '2026-10-30')['total_seconds'], 1800)

    def test_independent_employee_timers(self):
        other = self.tracker.add_employee('Sam Example')['id']
        self.tracker.start(self.alex, 'A')
        self.tracker.start(other, 'B')
        self.now += 60
        self.tracker.stop(self.alex)
        self.now += 60
        self.tracker.stop(other)
        self.assertEqual(self.tracker.report('2026-10-29', '2026-10-29')['total_seconds'], 180)

    def test_invalid_input_and_missing_employee(self):
        for value in ['', '  ', 123, None, 'x'*101]:
            with self.subTest(value=value), self.assertRaises(Problem):
                self.tracker.add_employee(value)
        with self.assertRaises(Problem):
            self.tracker.add_employee(' alex example ')
        for value in [True, '1', 0, -1]:
            with self.subTest(value=value), self.assertRaises(Problem):
                self.tracker.start(value, 'Task')
        with self.assertRaises(Problem) as exc:
            self.tracker.start(9999, 'Missing')
        self.assertEqual(exc.exception.status, 404)
        with self.assertRaises(Problem):
            self.tracker.start(self.alex, ' ')

    def test_invalid_periods(self):
        for first, last in [('2026-10-30','2026-10-29'),('wrong','2026-10-29'),('2026-02-30','2026-10-29')]:
            with self.subTest(first=first), self.assertRaises(Problem):
                self.tracker.report(first,last)

    def test_running_entry_is_clipped_to_period_end(self):
        self.now = ts('2026-10-28T23:30:00')
        self.tracker.start(self.alex, 'Still running')
        self.now = ts('2026-10-30T12:00:00')
        self.assertEqual(self.tracker.report('2026-10-29', '2026-10-29')['total_seconds'], 86400)

    def test_entry_touching_period_boundary_has_no_overlap(self):
        self.now = ts('2026-10-28T23:00:00')
        self.tracker.start(self.alex, 'Boundary')
        self.now = ts('2026-10-29T00:00:00')
        self.tracker.stop(self.alex)
        report = self.tracker.report('2026-10-29', '2026-10-29')
        self.assertEqual(report['total_seconds'], 0)
        self.assertEqual(report['entries'], [])


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(Tracker(Path(cls.tmp.name)/'http.sqlite3')))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        connection.request(method,path,body=body,headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read(), response.getheader('Content-Type')
        connection.close()
        return result

    def test_assets(self):
        for path, mime in [('/', 'text/html'),('/employee?id=1', 'text/html'),
                           ('/employee.js', 'text/javascript'),
                           ('/app.js','text/javascript'),('/style.css','text/css')]:
            status, body, content_type = self.request('GET',path)
            self.assertEqual(status,200)
            self.assertTrue(body)
            self.assertIn(mime,content_type)

    def test_state_includes_server_clock(self):
        status, body, _ = self.request('GET', '/api/state')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertIsInstance(data['employees'], list)
        self.assertIsInstance(data['server_time'], (int, float))

    def test_personal_tracker_and_overview_share_records(self):
        # Both screens use these same routes, never independent browser storage.
        headers = {'Content-Type': 'application/json'}
        status, body, _ = self.request('POST', '/api/employees',
                                       json.dumps({'name': 'Shared Example'}), headers)
        self.assertEqual(status, 201)
        employee_id = json.loads(body)['id']
        payload = json.dumps({'employee_id': employee_id, 'description': 'Personal tracker task'})
        self.assertEqual(self.request('POST', '/api/start', payload, headers)[0], 201)
        state = json.loads(self.request('GET', '/api/state')[1])
        person = next(p for p in state['employees'] if p['id'] == employee_id)
        self.assertIsNotNone(person['timer_id'])
        report = json.loads(self.request('GET', '/api/report?from=2020-01-01&to=2030-01-01')[1])
        entry = next(e for e in report['entries'] if e['employee_id'] == employee_id)
        self.assertEqual(entry['description'], 'Personal tracker task')
        self.assertIsNone(entry['ended_at'])
        self.assertEqual(self.request('POST', '/api/stop', payload, headers)[0], 200)
        state = json.loads(self.request('GET', '/api/state')[1])
        self.assertIsNone(next(p for p in state['employees'] if p['id'] == employee_id)['timer_id'])
        report = json.loads(self.request('GET', '/api/report?from=2020-01-01&to=2030-01-01')[1])
        self.assertIsNotNone(next(e for e in report['entries'] if e['id'] == entry['id'])['ended_at'])

    def test_http_flow(self):
        headers = {'Content-Type':'application/json'}
        status, body, _ = self.request('POST','/api/employees',json.dumps({'name':'HTTP Example'}),headers)
        self.assertEqual(status,201)
        person = json.loads(body)
        data = json.dumps({'employee_id':person['id'],'description':'API test'})
        self.assertEqual(self.request('POST','/api/start',data,headers)[0],201)
        self.assertEqual(self.request('POST','/api/start',data,headers)[0],409)
        self.assertEqual(self.request('POST','/api/stop',data,headers)[0],200)
        status, body, _ = self.request('GET','/api/report?from=2020-01-01&to=2030-01-01')
        self.assertEqual(status,200)
        self.assertTrue(json.loads(body)['entries'])

    def test_bad_requests(self):
        self.assertEqual(self.request('POST','/api/employees','{}')[0],415)
        headers = {'Content-Type':'application/json'}
        for body in ['[]','null','{oops']:
            self.assertEqual(self.request('POST','/api/employees',body,headers)[0],400)
        headers['Origin']='https://another-site.invalid'
        self.assertEqual(self.request('POST','/api/employees','{}',headers)[0],403)
        self.assertEqual(self.request('GET','/api/report?from=oops')[0],400)
        self.assertEqual(self.request('GET','/missing')[0],404)


if __name__ == '__main__':
    unittest.main()

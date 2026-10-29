"""Local time tracker. Python 3.11+, no third-party dependencies."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import time as clock
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Tracker:
    def __init__(self, path, now=clock.time):
        self.path, self.now = str(path), now
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE
                );
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY,
                    employee_id INTEGER NOT NULL REFERENCES employees(id),
                    description TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    ended_at REAL CHECK (ended_at IS NULL OR ended_at >= started_at)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_running_timer
                ON entries(employee_id) WHERE ended_at IS NULL;
                CREATE INDEX IF NOT EXISTS entries_period ON entries(started_at);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def text(value, label, limit):
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise Problem(f'{label}: требуется от 1 до {limit} символов.')
        return value.strip()

    @staticmethod
    def employee_id(value):
        if type(value) is not int or value < 1:
            raise Problem('Некорректный ID сотрудника.')
        return value

    def add_employee(self, name):
        name = self.text(name, 'Имя', 100)
        try:
            with self.db() as db:
                row = db.execute('INSERT INTO employees(name) VALUES (?) RETURNING id,name', (name,)).fetchone()
                return dict(row)
        except sqlite3.IntegrityError:
            raise Problem('Сотрудник с таким именем уже существует.', 409)

    def employees(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('''SELECT e.id,e.name,t.id AS timer_id,
                t.description,t.started_at FROM employees e LEFT JOIN entries t
                ON t.employee_id=e.id AND t.ended_at IS NULL ORDER BY e.name''')]

    def start(self, employee_id, description):
        employee_id = self.employee_id(employee_id)
        description = self.text(description, 'Описание', 500)
        try:
            with self.db() as db:
                if not db.execute('SELECT id FROM employees WHERE id=?', (employee_id,)).fetchone():
                    raise Problem('Сотрудник не найден.', 404)
                row = db.execute('''INSERT INTO entries(employee_id,description,started_at)
                    VALUES (?,?,?) RETURNING *''', (employee_id, description, self.now())).fetchone()
                return dict(row)
        except sqlite3.IntegrityError:
            raise Problem('У сотрудника уже запущен таймер.', 409)

    def stop(self, employee_id):
        employee_id = self.employee_id(employee_id)
        with self.db() as db:
            # One atomic update: a repeated stop cannot overwrite the original end time.
            row = db.execute('''UPDATE entries SET ended_at=MAX(started_at,?)
                WHERE employee_id=? AND ended_at IS NULL RETURNING *''',
                (self.now(), employee_id)).fetchone()
            if row is None:
                raise Problem('Активный таймер не найден.', 409)
            return dict(row)

    def report(self, start, end):
        try:
            first, last = date.fromisoformat(start), date.fromisoformat(end)
            if first > last:
                raise ValueError
            low = datetime.combine(first, time(), timezone.utc).timestamp()
            high = datetime.combine(last + timedelta(days=1), time(), timezone.utc).timestamp()
        except (ValueError, TypeError, OverflowError):
            raise Problem('Нужен корректный период: YYYY-MM-DD, начало ≤ конец.')
        now = self.now()
        with self.db() as db:
            # Both reads must see one snapshot even if another request adds an employee.
            db.execute('BEGIN')
            people = [dict(r) | {'seconds': 0.0} for r in db.execute('SELECT * FROM employees ORDER BY name')]
            by_id = {p['id']: p for p in people}
            rows = db.execute('''SELECT t.*,e.name FROM entries t JOIN employees e ON e.id=t.employee_id
                WHERE t.started_at < ? AND COALESCE(t.ended_at,?) > ?
                ORDER BY t.started_at DESC,t.id DESC''', (high, now, low)).fetchall()
        entries = []
        for row in rows:
            item = dict(row)
            effective_end = now if item['ended_at'] is None else item['ended_at']
            item['seconds'] = max(0.0, min(effective_end, high) - max(item['started_at'], low))
            by_id[item['employee_id']]['seconds'] += item['seconds']
            entries.append(item)
        return {'employees': people, 'entries': entries,
                'total_seconds': sum(p['seconds'] for p in people), 'as_of': now, 'timezone': 'UTC'}


def make_handler(tracker):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, payload, content_type='application/json; charset=utf-8'):
            body = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            try:
                assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                          '/employee': ('employee.html', 'text/html; charset=utf-8'),
                          '/employee.js': ('employee.js', 'text/javascript; charset=utf-8'),
                          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                          '/style.css': ('style.css', 'text/css; charset=utf-8')}
                if url.path in assets:
                    filename, mime = assets[url.path]
                    return self.reply(200, (ROOT / 'static' / filename).read_bytes(), mime)
                if url.path == '/api/employees':
                    return self.reply(200, tracker.employees())
                if url.path == '/api/state':
                    return self.reply(200, {'employees': tracker.employees(), 'server_time': tracker.now()})
                if url.path == '/api/report':
                    q = parse_qs(url.query)
                    return self.reply(200, tracker.report(q.get('from', [''])[0], q.get('to', [''])[0]))
                self.reply(404, {'error': 'Не найдено.'})
            except Problem as exc:
                self.reply(exc.status, {'error': str(exc)})

        def do_POST(self):
            try:
                # Keep writes same-origin; no cross-origin API access or credentials.
                origin = self.headers.get('Origin')
                if origin and origin != 'http://' + self.headers.get('Host', ''):
                    raise Problem('Запрос с другого сайта запрещён.', 403)
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise Problem('Ожидается application/json.', 415)
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length < 1 or length > 8192:
                        raise ValueError
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError
                except (ValueError, UnicodeDecodeError):
                    raise Problem('Некорректный JSON или размер запроса.')
                path = urlsplit(self.path).path
                if path == '/api/employees':
                    return self.reply(201, tracker.add_employee(data.get('name')))
                if path == '/api/start':
                    return self.reply(201, tracker.start(data.get('employee_id'), data.get('description')))
                if path == '/api/stop':
                    return self.reply(200, tracker.stop(data.get('employee_id')))
                self.reply(404, {'error': 'Не найдено.'})
            except Problem as exc:
                self.reply(exc.status, {'error': str(exc)})

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=str(ROOT / 'tracker.sqlite3'))
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(Tracker(args.db)))
    print(f'Open http://127.0.0.1:{args.port} — Ctrl+C to stop', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

"""Create fictional demo records in a separate database; never overwrite existing data."""
import argparse
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import time as clock

from app import Tracker


def seed(path):
    tracker = Tracker(path)
    now = clock.time()
    day = datetime.now(timezone.utc).date()
    midnight = datetime.combine(day, time(), timezone.utc)
    with tracker.db() as db:
        # Prevent two seed processes from both checking an empty database.
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT COUNT(*) FROM employees').fetchone()[0]:
            raise SystemExit('Database already contains employees; nothing was changed.')
        people = ['Алексей Примеров', 'София Тестова', 'Марк Демов']
        ids = [db.execute('INSERT INTO employees(name) VALUES (?) RETURNING id', (name,)).fetchone()[0]
               for name in people]
        tasks = ['Интеграция API и обработка событий', 'Макеты личного кабинета', 'Проверка отчётов и сценариев']
        for days_ago in (2, 1):
            start = (midnight - timedelta(days=days_ago) + timedelta(hours=9)).timestamp()
            for index, employee_id in enumerate(ids):
                duration = 3600 * (index + 1) + 1200 * days_ago
                db.execute('INSERT INTO entries(employee_id,description,started_at,ended_at) VALUES (?,?,?,?)',
                           (employee_id, tasks[index], start, start + duration))
        for index in (0, 1):
            db.execute('INSERT INTO entries(employee_id,description,started_at) VALUES (?,?,?)',
                       (ids[index], tasks[index], now - (index + 1) * 1250))
    print(f'Fictional demo data created: {path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', default=str(Path(__file__).resolve().parent / 'demo.sqlite3'))
    seed(parser.parse_args().db)

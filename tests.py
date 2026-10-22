"""Small deterministic fixtures exercising business boundaries in the actual SQL."""
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parent
AS_OF = '2026-10-21'


def fixture(folder):
    connection = sqlite3.connect(':memory:')
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript((ROOT / 'schema.sql').read_text())
    blocks = (ROOT / 'analysis.sql').read_text().split('-- name: ')[1:]
    sql = dict(block.split('\n', 1) for block in blocks)
    return connection, {k.strip(): v for k, v in sql.items()}


class BusinessBoundaries(unittest.TestCase):
    def test_weighted_margin_zero_revenue_and_month_window(self):
            c, q = fixture('04-commercial-performance')
            self.addCleanup(c.close)
            c.execute("INSERT INTO customers VALUES(1,'North')")
            c.executemany('INSERT INTO products VALUES(?,?)', [('A','Mixed'),('B','Zero')])
            c.executemany('INSERT INTO transactions VALUES(?,?,?,?,?,?,?)',
                          [(1,1,'A','2026-09-01',1,100000,90000),
                           (2,1,'A','2026-10-01',1,10000,1000),
                           (3,1,'B','2026-10-01',1,0,1000)])
            r = {x['category']: dict(x) for x in c.execute(q['category_margin'], {'as_of': AS_OF})}
            self.assertAlmostEqual(r['Mixed']['gross_margin_pct'], 19000/110000*100)
            self.assertIsNone(r['Zero']['gross_margin_pct'])
            months = [dict(x) for x in c.execute(q['monthly_revenue'], {'as_of': AS_OF})]
            self.assertIsNone(months[0]['prior_revenue_inr'])
            self.assertEqual(months[1]['cumulative_revenue_inr'], 1100)
            self.assertEqual(months[1]['change_pct'], -90)

if __name__ == "__main__":
    unittest.main(verbosity=2)

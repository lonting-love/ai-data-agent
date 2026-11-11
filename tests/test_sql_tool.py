import sqlite3
import tempfile
import unittest
from pathlib import Path

import execute_sql_tool as sql_module
from execute_sql_tool import _has_multiple_statements, _strip_comments, execute_sql_tool


class SqlGuardTests(unittest.TestCase):
    def test_strip_line_comment(self):
        self.assertEqual(_strip_comments("select 1 -- note").strip(), "select 1")

    def test_strip_block_comment(self):
        cleaned = " ".join(_strip_comments("select /* x */ 1").split())
        self.assertEqual(cleaned, "select 1")

    def test_comment_marker_inside_string_kept(self):
        self.assertIn("--not-comment", _strip_comments("select '--not-comment'"))

    def test_trailing_semicolon_is_single_statement(self):
        self.assertFalse(_has_multiple_statements("select 1;  "))

    def test_two_statements_detected(self):
        self.assertTrue(_has_multiple_statements("select 1; drop table t"))

    def test_semicolon_inside_string_ignored(self):
        self.assertFalse(_has_multiple_statements("select 'a;b'"))


class ExecuteSqlToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.tmp.name) / "test.db"
        conn = sqlite3.connect(cls.db_path)
        conn.execute("create table items (id integer, name text, amount real)")
        conn.executemany(
            "insert into items values (?, ?, ?)",
            [(i, f"item-{i}", i * 1.5) for i in range(1, 251)],
        )
        conn.commit()
        conn.close()
        cls.original_path = sql_module.DB_PATH
        cls.original_timeout = sql_module.SQL_TIMEOUT_SECONDS
        sql_module.DB_PATH = cls.db_path

    @classmethod
    def tearDownClass(cls):
        sql_module.DB_PATH = cls.original_path
        sql_module.SQL_TIMEOUT_SECONDS = cls.original_timeout
        cls.tmp.cleanup()

    def invoke(self, sql: str) -> str:
        return execute_sql_tool.invoke({"sql_query": sql})

    def test_select_returns_rows(self):
        result = self.invoke("select name, amount from items where id = 2")
        self.assertIn("name | amount", result)
        self.assertIn("item-2", result)

    def test_write_statement_rejected(self):
        self.assertIn("只允许执行 SELECT", self.invoke("delete from items"))

    def test_multi_statement_rejected(self):
        self.assertIn("一次只能执行一条 SQL", self.invoke("select 1; select 2"))

    def test_leading_comment_allowed(self):
        result = self.invoke("-- hi\nselect count(*) as total from items")
        self.assertIn("250", result)

    def test_row_limit_truncates(self):
        result = self.invoke("select * from items")
        self.assertIn("仅显示前 200 行", result)

    def test_empty_result_message(self):
        self.assertIn("结果为空", self.invoke("select * from items where id < 0"))

    def test_attach_database_denied(self):
        result = self.invoke("select * from other.items")
        self.assertIn("SQL执行失败", result)

    def test_timeout_interrupts_long_query(self):
        sql_module.SQL_TIMEOUT_SECONDS = 0.05
        try:
            result = self.invoke(
                "with recursive c(x) as (select 1 union all select x + 1 from c where x < 50000000) "
                "select sum(x) from c"
            )
        finally:
            sql_module.SQL_TIMEOUT_SECONDS = self.original_timeout
        self.assertIn("中断", result)


if __name__ == "__main__":
    unittest.main()

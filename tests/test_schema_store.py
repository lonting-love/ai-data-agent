import unittest
from unittest import mock

from schema_store import SCHEMAS, SchemaIndex, _expand, _lexical_search, _tokenize


class TokenizerTests(unittest.TestCase):
    def test_chinese_bigrams(self):
        self.assertEqual(_tokenize("订单"), ["订单"])

    def test_english_words(self):
        self.assertIn("customers", _tokenize("查询 customers 表"))

    def test_synonym_expansion(self):
        self.assertIn("customers", _expand("有多少客户"))
        self.assertIn("product_sales", _expand("各产品销售额"))


class LexicalSearchTests(unittest.TestCase):
    def test_order_question_hits_orders_table(self):
        docs = _lexical_search("最近一个月的订单金额是多少", k=3)
        self.assertEqual(docs[0].table, "orders")

    def test_synonym_question_hits_sales_table(self):
        docs = _lexical_search("每个月的营收趋势", k=3)
        self.assertIn("product_sales", [doc.table for doc in docs])

    def test_unknown_question_falls_back_to_all_schemas(self):
        docs = _lexical_search("zzz", k=3)
        self.assertEqual(len(docs), len(SCHEMAS))

    def test_results_respect_k(self):
        docs = _lexical_search("订单 客户 商品 支付", k=2)
        self.assertLessEqual(len(docs), 2)

    def test_index_falls_back_without_vector_deps(self):
        with mock.patch.object(SchemaIndex, "_try_load_chroma", return_value=None):
            index = SchemaIndex()
        self.assertEqual(index.backend_name, "lexical")
        docs = index.similarity_search("库存", k=4)
        self.assertTrue(docs)
        self.assertTrue(all(doc.text for doc in docs))


if __name__ == "__main__":
    unittest.main()

"""表结构检索：优先向量检索，缺少可选依赖时自动降级为词法检索。

对外保持 get_vectorstore() 接口不变，backend 只需调用 similarity_search(question, k)。
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

# 国内直连 HuggingFace 经常超时，默认走镜像
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
COLLECTION_NAME = "db_schemas"
PERSIST_DIR = Path(__file__).resolve().parent / "chroma_db"

SCHEMAS = [
    "表名: customers, 字段: name (姓名), city (城市), email (邮箱), phone (电话), signup_date (注册日期), vip_level (VIP等级)",
    "表名: products, 字段: product_name (产品名称), category (类别), price (价格), stock (库存), created_date (创建日期)",
    "表名: orders, 字段: customer_id (客户ID→customers), order_date (下单日期), amount (金额), status (状态)",
    "表名: order_items, 字段: order_id (订单ID→orders), product_id (产品ID→products), quantity (数量), unit_price (单价)",
    "表名: payments, 字段: order_id (订单ID→orders), pay_date (支付日期), amount (金额), payment_method (支付方式), status (状态)",
    "表名: shipments, 字段: order_id (订单ID→orders), ship_date (发货日期), carrier (承运商), tracking_no (运单号), status (状态)",
    "表名: reviews, 字段: product_id (产品ID→products), customer_id (客户ID→customers), rating (评分), comment (评论), review_date (评论日期)",
    "表名: inventory, 字段: product_id (产品ID→products), warehouse (仓库), quantity (数量), last_check_date (盘点日期)",
    "表名: suppliers, 字段: supplier_name (供应商名称), city (城市), contact_phone (联系电话), rating (评分)",
    "表名: employees, 字段: name (姓名), department (部门), salary (工资), hire_date (入职日期)",
    "表名: departments, 字段: dept_name (部门名称), manager_name (经理姓名), budget (预算)",
    "表名: courses, 字段: course_name (课程名称), teacher (教师), price (价格), hours (课时)",
    "表名: students, 字段: name (姓名), age (年龄), city (城市), enroll_date (入学日期)",
    "表名: enrollments, 字段: student_id (学生ID→students), course_id (课程ID→courses), enroll_date (选课日期), score (成绩)",
    "表名: books, 字段: title (书名), author (作者), category (类别), price (价格), publish_date (出版日期)",
    "表名: loans, 字段: book_id (图书ID→books), student_id (学生ID→students), loan_date (借出日期), return_date (归还日期), status (状态)",
    "表名: weather, 字段: city (城市), record_date (记录日期), temperature (温度), humidity (湿度), condition (天气)",
    "表名: flights, 字段: flight_no (航班号), departure_city (出发城市), arrival_city (到达城市), depart_date (起飞日期), price (票价), seats (座位数)",
    "表名: hotels, 字段: hotel_name (酒店名称), city (城市), stars (星级), price_per_night (每晚价格), rating (评分)",
    "表名: tickets, 字段: customer_id (客户ID→customers), subject (工单主题), priority (优先级), status (状态), created_date (创建日期), resolved_date (解决日期)",
    "表名: product_sales, 字段: product_name (产品名称), date (统计月份), sales_volume (销量), revenue (营收)",
]

# 中文口语 → 表/字段语义，弥补词法检索对同义词不敏感的短板
SYNONYMS = {
    "客户": "customers", "顾客": "customers", "用户": "customers", "会员": "customers",
    "商品": "products", "产品": "products", "货物": "products",
    "订单": "orders", "下单": "orders",
    "订单明细": "order_items", "明细": "order_items",
    "支付": "payments", "付款": "payments", "收款": "payments",
    "物流": "shipments", "发货": "shipments", "快递": "shipments",
    "评论": "reviews", "评价": "reviews", "评分": "reviews",
    "库存": "inventory", "仓库": "inventory",
    "供应商": "suppliers", "供货": "suppliers",
    "员工": "employees", "工资": "employees", "薪资": "employees", "薪水": "employees",
    "部门": "departments", "预算": "departments",
    "课程": "courses", "课时": "courses",
    "学生": "students",
    "选课": "enrollments", "成绩": "enrollments", "分数": "enrollments",
    "图书": "books", "书": "books", "作者": "books",
    "借书": "loans", "借阅": "loans", "归还": "loans",
    "天气": "weather", "温度": "weather", "湿度": "weather",
    "航班": "flights", "机票": "flights", "飞机": "flights",
    "酒店": "hotels", "住宿": "hotels",
    "工单": "tickets", "客服": "tickets", "投诉": "tickets",
    "销量": "product_sales", "营收": "product_sales", "销售额": "product_sales", "销售": "product_sales",
}

_CJK = re.compile(r"[一-鿿]+")
_ASCII = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _tokenize(text: str) -> list[str]:
    """英文按词切，中文按二字组（bigram）切，避免整句匹配失败。"""
    text = text.lower()
    tokens = _ASCII.findall(text)
    for chunk in _CJK.findall(text):
        if len(chunk) == 1:
            tokens.append(chunk)
        else:
            tokens.extend(chunk[i:i + 2] for i in range(len(chunk) - 1))
    return tokens


def _expand(question: str) -> set[str]:
    tokens = set(_tokenize(question))
    for word, table in SYNONYMS.items():
        if word in question:
            tokens.add(table)
    return tokens


@dataclass(frozen=True)
class SchemaDoc:
    text: str
    table: str


def _table_of(schema_text: str) -> str:
    return schema_text.split(",")[0].removeprefix("表名: ").strip()


def _lexical_search(question: str, k: int) -> list[SchemaDoc]:
    q_tokens = _expand(question)
    scored: list[tuple[float, SchemaDoc]] = []
    for text in SCHEMAS:
        table = _table_of(text)
        doc_tokens = set(_tokenize(text))
        hits = len(q_tokens & doc_tokens)
        score = float(hits)
        # 命中表名权重更高，避免「订单」问题里只匹配到无关表的字段
        if table.lower() in q_tokens or table in question.lower():
            score += 6
        scored.append((score, SchemaDoc(text=text, table=table)))

    scored.sort(key=lambda item: item[0], reverse=True)
    positive = [doc for score, doc in scored if score > 0]
    if not positive:
        # 完全无匹配时给全量 schema，让模型自己挑，好过瞎猜
        return [SchemaDoc(text=text, table=_table_of(text)) for text in SCHEMAS]
    return positive[:k]


class SchemaIndex:
    """向量检索失败自动降级，保证 backend 在任何依赖环境下都能启动。"""

    def __init__(self) -> None:
        self._chroma = self._try_load_chroma()
        self.backend_name = "chroma" if self._chroma is not None else "lexical"

    @staticmethod
    def _try_load_chroma():
        try:
            from langchain_chroma import Chroma
            from langchain_huggingface import HuggingFaceEmbeddings
        except ImportError:
            return None
        try:
            embeddings = HuggingFaceEmbeddings(model_name=MODEL_NAME)
            store = Chroma(
                collection_name=COLLECTION_NAME,
                embedding_function=embeddings,
                persist_directory=str(PERSIST_DIR),
            )
            if store.get(limit=1)["ids"] and store._collection.count() == len(SCHEMAS):
                return store
            store.delete_collection()
            return Chroma.from_texts(
                texts=SCHEMAS,
                embedding=embeddings,
                metadatas=[{"table": _table_of(text)} for text in SCHEMAS],
                collection_name=COLLECTION_NAME,
                persist_directory=str(PERSIST_DIR),
            )
        except Exception:
            return None

    def similarity_search(self, question: str, k: int = 6) -> list[SchemaDoc]:
        if self._chroma is not None:
            try:
                docs = self._chroma.similarity_search(question, k=k)
                return [SchemaDoc(text=doc.page_content, table=doc.metadata.get("table") or _table_of(doc.page_content)) for doc in docs]
            except Exception:
                self._chroma = None
                self.backend_name = "lexical"
        return _lexical_search(question, k)


_index: SchemaIndex | None = None


def get_vectorstore() -> SchemaIndex:
    global _index
    if _index is None:
        _index = SchemaIndex()
    return _index

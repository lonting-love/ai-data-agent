import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "marketing_data.db"

CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "西安", "重庆"]
SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴"]
GIVEN_NAMES = ["伟", "芳", "娜", "敏", "静", "磊", "洋", "勇", "艳", "杰", "涛", "明"]
PRODUCTS = ["手机", "笔记本电脑", "耳机", "键盘", "显示器", "平板", "相机", "智能手表"]
CATEGORIES = ["电子", "服装", "食品", "家居", "图书", "运动", "美妆", "汽车"]
STATUSES = ["active", "inactive", "pending", "completed", "cancelled"]
PAY_METHODS = ["微信", "支付宝", "银行卡", "现金", "信用卡"]
DEPARTMENTS = ["研发部", "市场部", "销售部", "财务部", "人事部", "客服部"]
COURSES = ["高等数学", "大学英语", "数据结构", "操作系统", "计算机网络", "数据库原理"]
CONDITIONS = ["晴", "多云", "阴", "小雨", "大雨", "雪"]
PRIORITIES = ["低", "中", "高", "紧急"]
COMMENTS = ["很满意", "一般般", "质量不错", "发货很快", "有点失望", "性价比高"]
BOOK_TITLES = ["三体", "活着", "百年孤独", "人类简史", "小王子", "围城"]
TICKET_SUBJECTS = ["无法登录", "订单异常", "退款申请", "发票问题", "物流延迟", "账号冻结"]

REF_TABLES = {
    "customer_id": "customers",
    "product_id": "products",
    "order_id": "orders",
    "student_id": "students",
    "course_id": "courses",
    "book_id": "books",
    "hotel_id": "hotels",
}

TABLE_SPECS = [
    ("customers", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("name", "TEXT"),
        ("city", "TEXT"),
        ("email", "TEXT"),
        ("phone", "TEXT"),
        ("signup_date", "TEXT"),
        ("vip_level", "INTEGER"),
    ]),
    ("products", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("product_name", "TEXT"),
        ("category", "TEXT"),
        ("price", "REAL"),
        ("stock", "INTEGER"),
        ("created_date", "TEXT"),
    ]),
    ("orders", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("customer_id", "INTEGER"),
        ("order_date", "TEXT"),
        ("amount", "REAL"),
        ("status", "TEXT"),
    ]),
    ("order_items", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("order_id", "INTEGER"),
        ("product_id", "INTEGER"),
        ("quantity", "INTEGER"),
        ("unit_price", "REAL"),
    ]),
    ("employees", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("name", "TEXT"),
        ("department", "TEXT"),
        ("salary", "INTEGER"),
        ("hire_date", "TEXT"),
    ]),
    ("departments", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("dept_name", "TEXT"),
        ("manager_name", "TEXT"),
        ("budget", "REAL"),
    ]),
    ("suppliers", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("supplier_name", "TEXT"),
        ("city", "TEXT"),
        ("contact_phone", "TEXT"),
        ("rating", "REAL"),
    ]),
    ("inventory", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("product_id", "INTEGER"),
        ("warehouse", "TEXT"),
        ("quantity", "INTEGER"),
        ("last_check_date", "TEXT"),
    ]),
    ("shipments", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("order_id", "INTEGER"),
        ("ship_date", "TEXT"),
        ("carrier", "TEXT"),
        ("tracking_no", "TEXT"),
        ("status", "TEXT"),
    ]),
    ("payments", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("order_id", "INTEGER"),
        ("pay_date", "TEXT"),
        ("amount", "REAL"),
        ("payment_method", "TEXT"),
        ("status", "TEXT"),
    ]),
    ("reviews", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("product_id", "INTEGER"),
        ("customer_id", "INTEGER"),
        ("rating", "REAL"),
        ("comment", "TEXT"),
        ("review_date", "TEXT"),
    ]),
    ("courses", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("course_name", "TEXT"),
        ("teacher", "TEXT"),
        ("price", "REAL"),
        ("hours", "INTEGER"),
    ]),
    ("students", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("name", "TEXT"),
        ("age", "INTEGER"),
        ("city", "TEXT"),
        ("enroll_date", "TEXT"),
    ]),
    ("enrollments", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("student_id", "INTEGER"),
        ("course_id", "INTEGER"),
        ("enroll_date", "TEXT"),
        ("score", "REAL"),
    ]),
    ("books", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("title", "TEXT"),
        ("author", "TEXT"),
        ("category", "TEXT"),
        ("price", "REAL"),
        ("publish_date", "TEXT"),
    ]),
    ("loans", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("book_id", "INTEGER"),
        ("student_id", "INTEGER"),
        ("loan_date", "TEXT"),
        ("return_date", "TEXT"),
        ("status", "TEXT"),
    ]),
    ("weather", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("city", "TEXT"),
        ("record_date", "TEXT"),
        ("temperature", "REAL"),
        ("humidity", "INTEGER"),
        ("condition", "TEXT"),
    ]),
    ("flights", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("flight_no", "TEXT"),
        ("departure_city", "TEXT"),
        ("arrival_city", "TEXT"),
        ("depart_date", "TEXT"),
        ("price", "REAL"),
        ("seats", "INTEGER"),
    ]),
    ("hotels", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("hotel_name", "TEXT"),
        ("city", "TEXT"),
        ("stars", "INTEGER"),
        ("price_per_night", "REAL"),
        ("rating", "REAL"),
    ]),
    ("tickets", [
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("customer_id", "INTEGER"),
        ("subject", "TEXT"),
        ("priority", "TEXT"),
        ("status", "TEXT"),
        ("created_date", "TEXT"),
        ("resolved_date", "TEXT"),
    ]),
]


def random_date() -> str:
    start = date(2023, 1, 1)
    return (start + timedelta(days=random.randint(0, 1400))).isoformat()


def random_value(column: str, sql_type: str, row_index: int, counts: dict[str, int]):
    lower = column.lower()
    type_upper = sql_type.upper()

    if "PRIMARY KEY" in type_upper:
        return None

    if lower.endswith("_id") and lower in REF_TABLES:
        return random.randint(1, max(counts.get(REF_TABLES[lower], 1), 1))

    if "date" in lower or "time" in lower:
        return random_date()
    if "email" in lower:
        return f"user{row_index}@example.com"
    if "phone" in lower or "mobile" in lower:
        return f"1{random.choice(['3', '5', '8'])}{random.randint(100000000, 999999999)}"
    if "city" in lower or "region" in lower:
        return random.choice(CITIES)
    if "status" in lower or "state" in lower:
        return random.choice(STATUSES)
    if "priority" in lower:
        return random.choice(PRIORITIES)
    if "method" in lower:
        return random.choice(PAY_METHODS)
    if "department" in lower or "dept" in lower:
        return random.choice(DEPARTMENTS)
    if "category" in lower or "type" in lower or "kind" in lower:
        return random.choice(CATEGORIES)
    if "product" in lower or "item" in lower:
        return random.choice(PRODUCTS)
    if "course" in lower:
        return random.choice(COURSES)
    if "condition" in lower:
        return random.choice(CONDITIONS)
    if "subject" in lower:
        return random.choice(TICKET_SUBJECTS)
    if "comment" in lower or "review" in lower:
        return random.choice(COMMENTS)
    if "title" in lower:
        return random.choice(BOOK_TITLES)
    if "supplier" in lower:
        return random.choice(["京东", "天猫", "华润", "国美", "苏宁", "永辉"]) + "供应链有限公司"
    if "hotel" in lower:
        return random.choice(["如家", "汉庭", "锦江", "全季", "希尔顿", "万豪"]) + "酒店"
    if "name" in lower or "author" in lower or "teacher" in lower:
        return random.choice(SURNAMES) + random.choice(GIVEN_NAMES)
    if "flight" in lower:
        return f"CA{random.randint(1000, 9999)}"
    if "tracking" in lower:
        return f"SF{random.randint(10**11, 10**12 - 1)}"
    if "warehouse" in lower:
        return f"仓库{random.randint(1, 9)}"
    if "carrier" in lower:
        return random.choice(["顺丰", "中通", "圆通", "京东物流"])
    if "stars" in lower:
        return random.randint(1, 5)
    if "temperature" in lower:
        return round(random.uniform(-10, 40), 1)
    if "rating" in lower:
        return round(random.uniform(1, 5), 1)
    if "price_per_night" in lower:
        return round(random.uniform(100, 2000), 2)
    if "salary" in lower:
        return random.randint(5000, 50000)
    if "age" in lower:
        return random.randint(18, 60)
    if "level" in lower:
        return random.randint(1, 5)
    if "humidity" in lower:
        return random.randint(20, 95)
    if any(k in lower for k in ("quantity", "count", "stock", "seats", "hours")):
        return random.randint(1, 200)

    if "INT" in type_upper:
        return random.randint(1, 1000)
    if any(t in type_upper for t in ("REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL")):
        return round(random.uniform(1, 10000), 2)
    return random.choice(SURNAMES) + random.choice(GIVEN_NAMES)


def create_random_tables() -> None:
    counts: dict[str, int] = {}
    summary: list[str] = []

    conn = sqlite3.connect(DB_PATH)
    try:
        for table_name, columns in TABLE_SPECS:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            column_sql = ", ".join(f"{name} {sql_type}" for name, sql_type in columns)
            conn.execute(f"CREATE TABLE {table_name} ({column_sql})")

            row_count = random.randint(20, 60)
            rows = []
            for index in range(1, row_count + 1):
                rows.append(tuple(
                    random_value(name, sql_type, index, counts)
                    for name, sql_type in columns
                ))

            placeholders = ", ".join("?" for _ in columns)
            conn.executemany(f"INSERT INTO {table_name} VALUES ({placeholders})", rows)
            counts[table_name] = row_count
            summary.append(f"{table_name}({row_count})")

        conn.commit()
    finally:
        conn.close()

    print(f"已生成 {len(TABLE_SPECS)} 张不同的表:")
    print(", ".join(summary))
    print(f"数据库位置: {DB_PATH}")


def ensure_product_sales() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute('''
        create table if not exists product_sales(
            id integer primary key autoincrement,
            product_name text not null,
            date text not null,
            sales_volume integer not null,
            revenue integer not null
        )''')
        cursor.execute('''
        create unique index if not exists ux_product_sales
        on product_sales(product_name, date)''')

        products = ["产品A", "产品B", "产品C", "产品D", "产品E",
                    "产品F", "产品G", "产品H", "产品I", "产品J"]
        records = []
        for product_name in products:
            for year in range(2023, 2027):
                for month in range(1, 13):
                    sale_date = f"{year}-{month:02d}"
                    sales_volume = random.randint(500, 5000)
                    revenue = sales_volume * random.randint(10, 100)
                    records.append((product_name, sale_date, sales_volume, revenue))

        cursor.executemany(
            "insert or ignore into product_sales(product_name, date, sales_volume, revenue) values(?,?,?,?)",
            records,
        )
        conn.commit()
        total = cursor.execute("select count(*) from product_sales").fetchone()[0]
        print(f"product_sales 保留,现有 {total} 条")
    finally:
        conn.close()


if __name__ == "__main__":
    create_random_tables()
    ensure_product_sales()

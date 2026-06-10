"""Generate a sample SQLite database for demos.

Tables:
    - regions    (region_id, region_name)
    - customers  (customer_id, customer_name, region_id, email, signup_date)
    - products   (product_id, product_name, category, price, stock)
    - orders     (order_id, customer_id, order_date, total_amount, status)
    - order_items(order_item_id, order_id, product_id, quantity, unit_price)

Usage:
    python examples/seed_data.py            # default path: examples/sample.db
    python examples/seed_data.py out.db     # custom path
"""
from __future__ import annotations

import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()

REGIONS = [
    ("华东", "East China"),
    ("华南", "South China"),
    ("华北", "North China"),
    ("华中", "Central China"),
    ("西南", "Southwest"),
    ("西北", "Northwest"),
]

CATEGORIES = ["电子产品", "家居用品", "服装鞋帽", "食品饮料", "图书文具", "美妆护肤"]

PRODUCTS = [
    ("iPhone 15 Pro", "电子产品", 8999.0, 120),
    ("MacBook Air M2", "电子产品", 11999.0, 45),
    ("AirPods Pro", "电子产品", 1899.0, 200),
    ("戴森吸尘器", "家居用品", 3290.0, 60),
    ("飞利浦电动牙刷", "家居用品", 499.0, 300),
    ("美的电饭煲", "家居用品", 399.0, 180),
    ("优衣库羽绒服", "服装鞋帽", 599.0, 250),
    ("阿迪达斯跑鞋", "服装鞋帽", 899.0, 320),
    ("三只松鼠坚果礼盒", "食品饮料", 128.0, 500),
    ("可口可乐 24 罐", "食品饮料", 89.0, 800),
    ("Kindle 电子书", "图书文具", 999.0, 150),
    ("晨光文具套装", "图书文具", 39.0, 600),
    ("雅诗兰黛小棕瓶", "美妆护肤", 1280.0, 90),
    ("兰蔻菁纯面霜", "美妆护肤", 2680.0, 50),
    ("SK-II 神仙水", "美妆护肤", 1690.0, 70),
]

FIRST_NAMES = ["张", "王", "李", "赵", "钱", "孙", "周", "吴", "郑", "陈", "刘", "杨", "黄"]
GIVEN_NAMES = [
    "伟", "芳", "娜", "敏", "静", "丽", "强", "磊", "军", "洋",
    "勇", "艳", "杰", "娟", "涛", "明", "超", "秀英", "霞", "平",
]

ORDER_STATUSES = ["completed", "pending", "shipped", "cancelled"]


class Region(Base):
    __tablename__ = "regions"
    region_id = Column(Integer, primary_key=True, autoincrement=True)
    region_name = Column(String(50), nullable=False, unique=True)
    customers = relationship("Customer", back_populates="region")


class Customer(Base):
    __tablename__ = "customers"
    customer_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name = Column(String(100), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.region_id"), nullable=False)
    email = Column(String(200), nullable=False)
    signup_date = Column(Date, nullable=False)
    region = relationship("Region", back_populates="customers")
    orders = relationship("Order", back_populates="customer")


class Product(Base):
    __tablename__ = "products"
    product_id = Column(Integer, primary_key=True, autoincrement=True)
    product_name = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    price = Column(Float, nullable=False)
    stock = Column(Integer, nullable=False, default=0)
    order_items = relationship("OrderItem", back_populates="product")


class Order(Base):
    __tablename__ = "orders"
    order_id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"), nullable=False)
    order_date = Column(DateTime, nullable=False, default=datetime.now)
    total_amount = Column(Float, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="pending")
    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    order_item_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.order_id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.product_id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


def gen_name(rng: random.Random) -> str:
    return rng.choice(FIRST_NAMES) + rng.choice(GIVEN_NAMES) + (rng.choice(GIVEN_NAMES) if rng.random() > 0.5 else "")


def main(db_path: str) -> None:
    p = Path(db_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()
    print(f"Creating database at {p}")

    engine = create_engine(f"sqlite:///{p}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    rng = random.Random(42)

    # Regions
    region_objs = [Region(region_name=cn) for cn, _ in REGIONS]
    session.add_all(region_objs)
    session.flush()

    # Products
    product_objs = [
        Product(product_name=name, category=cat, price=price, stock=stock)
        for name, cat, price, stock in PRODUCTS
    ]
    session.add_all(product_objs)
    session.flush()

    # Customers
    customers: list[Customer] = []
    start_date = date(2022, 1, 1)
    end_date = date(2025, 12, 31)
    days_range = (end_date - start_date).days
    for i in range(500):
        signup = start_date + timedelta(days=rng.randint(0, days_range))
        c = Customer(
            customer_name=gen_name(rng) + (str(i) if rng.random() > 0.7 else ""),
            region_id=rng.choice(region_objs).region_id,
            email=f"user{i:04d}@example.com",
            signup_date=signup,
        )
        customers.append(c)
    session.add_all(customers)
    session.flush()

    # Orders + order items
    today = datetime(2025, 12, 1)
    total_orders = 1500
    for _ in range(total_orders):
        c = rng.choice(customers)
        # orders between customer's signup and today
        earliest = max(c.signup_date, date(2023, 1, 1))
        delta = (today.date() - earliest).days
        if delta <= 0:
            continue
        order_dt = datetime.combine(earliest, datetime.min.time()) + timedelta(
            days=rng.randint(0, delta),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        status = rng.choices(ORDER_STATUSES, weights=[75, 10, 10, 5])[0]
        order = Order(
            customer_id=c.customer_id,
            order_date=order_dt,
            status=status,
            total_amount=0,
        )
        session.add(order)
        session.flush()

        n_items = rng.randint(1, 4)
        total = 0.0
        for _ in range(n_items):
            prod = rng.choice(product_objs)
            qty = rng.randint(1, 3)
            price = prod.price
            item = OrderItem(
                order_id=order.order_id,
                product_id=prod.product_id,
                quantity=qty,
                unit_price=price,
            )
            session.add(item)
            total += qty * price
        order.total_amount = round(total, 2)

    session.commit()
    session.close()

    # Print summary
    insp = create_engine(f"sqlite:///{p}").connect()
    print("Seeded:")
    for tbl in ("regions", "customers", "products", "orders", "order_items"):
        cnt = insp.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
        print(f"  - {tbl}: {cnt} rows")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "examples/sample.db"
    main(out)

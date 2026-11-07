"""SQLite schema and deterministic, explicitly-labelled demo dataset."""
from __future__ import annotations

import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(os.getenv("OSMANX_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
DB_PATH = DATA_DIR / "retail.sqlite3"

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS stores (
 id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL,
 subtitle TEXT NOT NULL DEFAULT '', incentive TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000), source TEXT NOT NULL,
 occurred_at TEXT NOT NULL, external_id TEXT,
 UNIQUE(store_id, source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_visits_store_date ON visits(store_id, occurred_at);
CREATE TABLE IF NOT EXISTS sales (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 amount_kopeks INTEGER NOT NULL CHECK(amount_kopeks >= 0),
 source TEXT NOT NULL, occurred_at TEXT NOT NULL, external_id TEXT,
 UNIQUE(store_id, source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_sales_store_date ON sales(store_id, occurred_at);
CREATE TABLE IF NOT EXISTS signals (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 kind TEXT NOT NULL CHECK(kind IN ('interest','fitting')),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
 occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS demand (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 product TEXT NOT NULL, size TEXT NOT NULL DEFAULT '', color TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','located','notified','converted','closed')),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_demand_store_date ON demand(store_id, created_at);
CREATE TABLE IF NOT EXISTS surveys (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), purchased INTEGER NOT NULL,
 reason TEXT NOT NULL DEFAULT '', liked TEXT NOT NULL DEFAULT '', suggestion TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_surveys_store_date ON surveys(store_id, created_at);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialize_db(demo: bool = False) -> None:
    with connect() as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)
        if demo:
            seed_demo(db)
        elif not db.execute("SELECT 1 FROM stores LIMIT 1").fetchone():
            db.execute("INSERT INTO stores(slug,name,subtitle,incentive,created_at) VALUES (?,?,?,?,?)",
                ("central", "Мой магазин", "Главный филиал", "", now_iso()))
        from backend.retail import ensure_schema
        ensure_schema(db, demo=demo)
        from backend.security import ensure_security_schema
        ensure_security_schema(db, demo=demo, bootstrap_password=os.getenv('OSMANX_ADMIN_PASSWORD',''),
                               bootstrap_email=os.getenv('OSMANX_BOOTSTRAP_EMAIL','owner@osmanx.local'))
        db.commit()


def seed_demo(db: sqlite3.Connection) -> None:
    if db.execute("SELECT 1 FROM stores WHERE slug='central'").fetchone():
        return
    stamp = now_iso()
    db.execute("INSERT INTO stores(slug,name,subtitle,incentive,created_at) VALUES (?,?,?,?,?)",
        ("central", "Бутик Центральный", "OSMANX · демонстрационный филиал", "Покажите экран сотруднику, чтобы узнать о бонусах", stamp))
    store_id = db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()[0]
    rng = random.Random(291106)
    today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    for day in range(32):
        date = today - timedelta(days=day)
        weekend = 1.27 if date.weekday() in (5, 6) else 1.0
        for hour, weight in enumerate([.38, .53, .72, .89, 1.04, 1.23, 1.37, 1.34, 1.09, .65], start=10):
            visitors = max(1, int((16.9 + rng.uniform(-4, 4)) * weight * weekend))
            orders = min(visitors, max(0, int(visitors * (0.18 + 0.08 * (hour >= 16)) + rng.uniform(-2, 2))))
            when = date.replace(hour=hour).isoformat(timespec="seconds")
            db.execute("INSERT INTO visits(store_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?)",
                (store_id, visitors, "demo_sensor", when, f"seed-traffic-{day}-{hour}"))
            for number in range(orders):
                amount = rng.randrange(250000, 1050000, 25000)
                db.execute("INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)",
                    (store_id, amount, "demo_pos", when, f"seed-sale-{day}-{hour}-{number}"))
            db.execute("INSERT INTO signals(store_id,kind,quantity,occurred_at) VALUES(?,?,?,?)",
                (store_id, "interest", max(1, visitors * 61 // 100), when))
            db.execute("INSERT INTO signals(store_id,kind,quantity,occurred_at) VALUES(?,?,?,?)",
                (store_id, "fitting", max(1, visitors * 31 // 100), when))
    items = [
        ("Куртка демисезонная", "XL", "чёрный", "open"),
        ("Худи оверсайз", "M", "графит", "open"),
        ("Джинсы прямые", "32", "синий", "located"),
        ("Пальто классическое", "L", "бежевый", "open"),
        ("Рубашка льняная", "S", "белый", "notified"),
        ("Брюки широкие", "M", "чёрный", "converted"),
        ("Куртка демисезонная", "XL", "чёрный", "open"),
        ("Куртка демисезонная", "XL", "чёрный", "open"),
        ("Худи оверсайз", "M", "графит", "open"),
        ("Джинсы прямые", "32", "синий", "open"),
    ]
    for i in range(76):
        product,size,color,status = items[i % len(items)]
        created = (today - timedelta(days=i % 28, hours=i % 8)).isoformat(timespec="seconds")
        db.execute("INSERT INTO demand(store_id,product,size,color,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (store_id,product,size,color,status,created,created))
    reasons = ["size","price","assortment","just_looking","service","other"]
    likes = ["Атмосфера", "Ассортимент", "Обслуживание", "Качество вещей", "Удобная примерочная"]
    for i in range(115):
        purchased = 1 if i % 4 == 0 else 0
        reason = "" if purchased else reasons[(i * 7 + i // 4) % len(reasons)]
        created = (today - timedelta(days=i % 28, hours=i % 9)).isoformat(timespec="seconds")
        db.execute("INSERT INTO surveys(store_id,rating,purchased,reason,liked,suggestion,created_at) VALUES(?,?,?,?,?,?,?)",
          (store_id, 5 if i % 4 < 2 else 4 if i % 5 else 3, purchased, reason, likes[i%len(likes)], "Больше размеров" if i % 9 == 0 else "", created))

"""Retail operations: audited demand, cross-store stock, reversible pilot plans.

The system never claims that a recorded request is a lost sale. A converted
request needs an actual recorded receipt belonging to the same store.
"""
from __future__ import annotations

import csv
import io
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.database import now_iso


EXTRA_SCHEMA = """
CREATE TABLE IF NOT EXISTS inventory (
 id INTEGER PRIMARY KEY,
 store_id INTEGER NOT NULL REFERENCES stores(id),
 sku TEXT NOT NULL, product TEXT NOT NULL, size TEXT NOT NULL DEFAULT '',
 color TEXT NOT NULL DEFAULT '', quantity INTEGER NOT NULL CHECK(quantity >= 0),
 source TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(store_id, sku)
);
CREATE INDEX IF NOT EXISTS idx_inventory_lookup ON inventory(product,size,color,quantity);
CREATE TABLE IF NOT EXISTS demand_history (
 id INTEGER PRIMARY KEY, demand_id INTEGER NOT NULL REFERENCES demand(id),
 previous_status TEXT NOT NULL, next_status TEXT NOT NULL,
 note TEXT NOT NULL DEFAULT '', occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_demand_history ON demand_history(demand_id,occurred_at);
CREATE TABLE IF NOT EXISTS experiments (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 title TEXT NOT NULL, hypothesis TEXT NOT NULL,
 metric TEXT NOT NULL, baseline REAL, result REAL,
 status TEXT NOT NULL DEFAULT 'planned' CHECK(status IN ('planned','running','finished','cancelled')),
 notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_experiments_store ON experiments(store_id,updated_at);
CREATE TABLE IF NOT EXISTS zones (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 code TEXT NOT NULL, name TEXT NOT NULL,
 x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 100),
 y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 100),
 UNIQUE(store_id,code)
);
CREATE TABLE IF NOT EXISTS zone_events (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 zone_id INTEGER NOT NULL REFERENCES zones(id),
 quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 10000),
 source TEXT NOT NULL, occurred_at TEXT NOT NULL, external_id TEXT NOT NULL,
 UNIQUE(store_id,zone_id,source,external_id)
);
CREATE INDEX IF NOT EXISTS idx_zone_events_date ON zone_events(store_id,occurred_at);
CREATE TABLE IF NOT EXISTS rewards (
 id INTEGER PRIMARY KEY, store_id INTEGER NOT NULL REFERENCES stores(id),
 survey_id INTEGER NOT NULL UNIQUE REFERENCES surveys(id),
 code TEXT NOT NULL UNIQUE, label TEXT NOT NULL,
 expires_at TEXT NOT NULL, redeemed_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rewards_store ON rewards(store_id,created_at);
"""


def ensure_schema(db: sqlite3.Connection, demo: bool = False) -> None:
    """Non-destructive, repeatable migration for R0.2 on both new and R0.1 DBs."""
    for table, additions in {
        "stores": {
            "timezone": "TEXT NOT NULL DEFAULT 'Europe/Moscow'",
            "reward_enabled": "INTEGER NOT NULL DEFAULT 0 CHECK(reward_enabled IN (0,1))",
            "reward_label": "TEXT NOT NULL DEFAULT ''",
        },
        "surveys": {
            "request_id": "TEXT",
            "payload_hash": "TEXT",
            "liked_tags": "TEXT NOT NULL DEFAULT '[]'",
            "improve_tags": "TEXT NOT NULL DEFAULT '[]'",
        },
        "demand": {"sale_id": "INTEGER REFERENCES sales(id)"},
    }.items():
        old = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        for column, declaration in additions.items():
            if column not in old:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    db.executescript(EXTRA_SCHEMA)
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_surveys_request ON surveys(store_id,request_id) WHERE request_id IS NOT NULL")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_demand_sale ON demand(sale_id) WHERE sale_id IS NOT NULL")
    if demo:
        seed_retail_demo(db)


def seed_retail_demo(db: sqlite3.Connection) -> None:
    """Clearly fictional stock, one extra store, and a realistic pilot card."""
    central = db.execute("SELECT id FROM stores WHERE slug='central'").fetchone()
    if not central:
        return
    now = now_iso()
    db.execute("INSERT OR IGNORE INTO stores(slug,name,subtitle,incentive,created_at) VALUES(?,?,?,?,?)",
               ("north", "Бутик Северный", "Демо · второй филиал", "", now))
    north = db.execute("SELECT id FROM stores WHERE slug='north'").fetchone()[0]
    if not db.execute("SELECT 1 FROM visits WHERE store_id=?", (north,)).fetchone():
        for day in range(30):
            for hour in range(11, 20):
                when = (datetime.now(timezone.utc) - timedelta(days=day)).replace(hour=hour,minute=0,second=0,microsecond=0).isoformat(timespec='seconds')
                visitors = 8 + ((day * 7 + hour * 3) % 13)
                db.execute("INSERT INTO visits(store_id,quantity,source,occurred_at) VALUES(?,?,?,?)",
                           (north, visitors, 'demo_sensor', when))
                for i in range(visitors // 5):
                    db.execute("INSERT INTO sales(store_id,amount_kopeks,source,occurred_at) VALUES(?,?,?,?)",
                               (north, 320000 + (hour % 4) * 45000, 'demo_pos', when))
    seed_stock = [
        (central['id'], 'COAT-BLK-L', 'Куртка демисезонная','L','чёрный',0),
        (central['id'], 'JEAN-BLU-32', 'Джинсы прямые','32','синий',0),
        (north, 'COAT-BLK-XL', 'Куртка демисезонная','XL','чёрный',4),
        (north, 'HOOD-GPH-M', 'Худи оверсайз','M','графит',7),
        (north, 'JEAN-BLU-32', 'Джинсы прямые','32','синий',2),
        (north, 'COAT-BGE-L', 'Пальто классическое','L','бежевый',1),
    ]
    for store_id,sku,product,size,color,quantity in seed_stock:
        db.execute("INSERT OR IGNORE INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                   (store_id,sku,product,size,color,quantity,'demo_inventory',now))
    zone_configs=[('entrance','Вход',15,80),('display','Новые коллекции',35,40),
                  ('fitting','Примерочные',76,28),('checkout','Касса',80,78)]
    for code,label,x,y in zone_configs:
        db.execute('INSERT OR IGNORE INTO zones(store_id,code,name,x,y) VALUES(?,?,?,?,?)',
                   (central['id'],code,label,x,y))
    if not db.execute('SELECT 1 FROM zone_events WHERE store_id=?',(central['id'],)).fetchone():
        for index,(code,label,x,y) in enumerate(zone_configs):
            zone_id=db.execute('SELECT id FROM zones WHERE store_id=? AND code=?',(central['id'],code)).fetchone()[0]
            for day in range(28):
                when=(datetime.now(timezone.utc)-timedelta(days=day)).replace(hour=14,minute=0,second=0,microsecond=0).isoformat(timespec='seconds')
                count=12+((day*7+index*9)%18) if index!=3 else 4+(day*3)%9
                db.execute('INSERT INTO zone_events(store_id,zone_id,quantity,source,occurred_at,external_id) VALUES(?,?,?,?,?,?)',
                           (central['id'],zone_id,count,'demo_zone_sensor',when,f'zone-seed-{index}-{day}'))
    if not db.execute("SELECT 1 FROM experiments WHERE store_id=?",(central['id'],)).fetchone():
        db.execute("INSERT INTO experiments(store_id,title,hypothesis,metric,status,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                   (central['id'],'Спрос на размеры XL','Часть запросов можно закрыть переводом товара между филиалами',
                    'confirmed_sales','planned','Демонстрационный план. Результат ещё не измерен.',now,now))


def stock_for_store(db: sqlite3.Connection, store_id: int) -> list[dict]:
    return [dict(r) for r in db.execute("""SELECT sku, product, size, color, quantity, source, updated_at
        FROM inventory WHERE store_id=? ORDER BY product, size LIMIT 500""", (store_id,))]


def stock_matches(db: sqlite3.Connection, store_id: int, product: str, size: str, color: str, organization_id: int | None = None) -> list[dict]:
    """Conservative matching, not speculative fuzzy matching of similar products."""
    rows = db.execute("""SELECT i.sku,i.product,i.size,i.color,i.quantity,i.updated_at,
       s.slug,s.name AS store_name FROM inventory i JOIN stores s ON s.id=i.store_id
       WHERE i.quantity>0 AND i.store_id<>? AND s.organization_id=(SELECT organization_id FROM stores WHERE id=?) ORDER BY i.quantity DESC""", (store_id,store_id)).fetchall()
    normalize = lambda s: ' '.join(s.casefold().strip().split())
    return [dict(r) for r in rows if normalize(r['product']) == normalize(product)
            and normalize(r['size']) == normalize(size)
            and (not color or normalize(r['color']) == normalize(color))][:20]


def traffic_sources(db:sqlite3.Connection,store_id:int,mode:str,start:str,end:str)->tuple[str,...] | None:
    """Explicit source policy prevents silently adding manual counts to a sensor."""
    if mode=='manual': return ('manual',)
    if mode=='sensor': return ('sensor','signed_sensor','demo_sensor')
    if mode=='auto':
        active=db.execute("""SELECT COUNT(*) n FROM visits WHERE store_id=? AND occurred_at>=? AND occurred_at<?
          AND source IN ('sensor','signed_sensor','demo_sensor')""",(store_id,start,end)).fetchone()['n']
        return ('sensor','signed_sensor','demo_sensor') if active else ('manual',)
    return None  # combined, explicitly warn if modes overlap


def traffic_filter(sources:tuple[str,...]|None) -> tuple[str,list[str]]:
    if sources is None: return '',[]
    return ' AND source IN ('+','.join('?' for _ in sources)+')',list(sources)


def observations(db: sqlite3.Connection, store_id: int, start: str, end: str) -> dict:
    sources = [dict(r) for r in db.execute("""SELECT source, SUM(quantity) AS count FROM visits
      WHERE store_id=? AND occurred_at>=? AND occurred_at<? GROUP BY source ORDER BY count DESC""",(store_id,start,end))]
    sale_sources = [dict(r) for r in db.execute("""SELECT source,COUNT(*) AS count FROM sales
      WHERE store_id=? AND occurred_at>=? AND occurred_at<? GROUP BY source ORDER BY count DESC""",(store_id,start,end))]
    total = sum(s['count'] for s in sources)
    receipts = sum(s['count'] for s in sale_sources)
    warnings = []
    if not total:
        warnings.append('Нет данных о входах; конверсию рассчитать нельзя.')
    if total and receipts > total:
        warnings.append('Чеков больше, чем входов: проверьте период и двойной учёт.')
    manual_sources = [r for r in sources if r['source']=='manual']
    sensor_sources = [r for r in sources if r['source'] in ('sensor','signed_sensor','demo_sensor')]
    if manual_sources and sensor_sources:
        warnings.append('Ручные входы и датчик суммируются: проверьте отсутствие дублей.')
    if any(r['source'].startswith('demo') for r in sources+sale_sources):
        warnings.append('В данных присутствуют демонстрационные события.')
    if total and not sale_sources:
        warnings.append('Есть входы, но отсутствуют чеки; проверьте интеграцию кассы.')
    return {'visits':sources,'sales':sale_sources,'warnings':warnings}


def daily_metrics(db: sqlite3.Connection, store_id: int, timezone_name: str, days: int, traffic_mode: str = 'combined') -> list[dict]:
    """Local calendar-day buckets while persisted timestamps remain UTC ISO 8601."""
    tz=ZoneInfo(timezone_name)
    today=datetime.now(tz).date()
    first=today-timedelta(days=days-1)
    start=datetime.combine(first,datetime.min.time(),tzinfo=tz).astimezone(timezone.utc).isoformat(timespec='seconds')
    values={ (first+timedelta(days=i)).isoformat():{'date':(first+timedelta(days=i)).isoformat(), 'visitors':0,'purchases':0,'revenue':0.0} for i in range(days)}
    filter_sql, source_args=traffic_filter(traffic_sources(db,store_id,traffic_mode,start,now_iso()))
    for r in db.execute('SELECT quantity,occurred_at FROM visits WHERE store_id=? AND occurred_at>=?'+filter_sql,
                        (store_id,start,*source_args)):
        key=datetime.fromisoformat(r['occurred_at']).astimezone(tz).date().isoformat()
        if key in values: values[key]['visitors']+=r['quantity']
    for r in db.execute("SELECT amount_kopeks,occurred_at FROM sales WHERE store_id=? AND occurred_at>=?",(store_id,start)):
        key=datetime.fromisoformat(r['occurred_at']).astimezone(tz).date().isoformat()
        if key in values:
            values[key]['purchases']+=1
            values[key]['revenue']+=r['amount_kopeks']/100
    for value in values.values():
        value['revenue']=round(value['revenue'],2)
        value['conversion']=round(100*value['purchases']/value['visitors'],1) if value['visitors'] else None
    return list(values.values())


def safe_spreadsheet_cell(value: object) -> str:
    """Prevent formula injection when reports are opened in Excel/Sheets."""
    text='' if value is None else str(value)
    if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'"+text
    return text


def csv_report(db: sqlite3.Connection, store_id: int, dataset: str) -> str:
    fields={
      'surveys': ('created_at','rating','purchased','reason','liked','suggestion','liked_tags','improve_tags'),
      'demand': ('created_at','product','size','color','status','sale_id'),
      'inventory': ('sku','product','size','color','quantity','source','updated_at'),
      'visits': ('occurred_at','quantity','source'),
      'sales': ('occurred_at','amount_kopeks','source','external_id'),
      'experiments': ('created_at','title','hypothesis','metric','baseline','result','status','notes'),
    }
    if dataset not in fields:
        raise ValueError('Invalid dataset')
    columns=fields[dataset]
    output=io.StringIO()
    writer=csv.writer(output,lineterminator='\r\n')
    writer.writerow(columns)
    query=f"SELECT {','.join(columns)} FROM {dataset} WHERE store_id=? ORDER BY id DESC LIMIT 20000"
    for row in db.execute(query,(store_id,)):
        writer.writerow([safe_spreadsheet_cell(v) for v in row])
    return '\ufeff'+output.getvalue()


def create_reward(db: sqlite3.Connection,store_id: int,survey_id: int,label: str) -> dict:
    """Single-use manual proof code; not an automatic POS discount or entitlement."""
    row=db.execute("SELECT code,label,expires_at,redeemed_at FROM rewards WHERE survey_id=?",(survey_id,)).fetchone()
    if row: return dict(row)
    when=now_iso()
    expires=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat(timespec='seconds')
    for _ in range(5):
        code='OX-'+secrets.token_hex(4).upper()
        try:
            db.execute('INSERT INTO rewards(store_id,survey_id,code,label,expires_at,created_at) VALUES(?,?,?,?,?,?)',
                       (store_id,survey_id,code,label,expires,when))
            return {'code':code,'label':label,'expires_at':expires,'redeemed_at':None}
        except sqlite3.IntegrityError:
            continue
    raise RuntimeError('Reward code collision')


def zone_heatmap(db: sqlite3.Connection,store_id:int,start:str,end:str)->list[dict]:
    return [dict(r) for r in db.execute("""SELECT z.id,z.code,z.name,z.x,z.y,
        COALESCE(SUM(e.quantity),0) AS count,
        COUNT(e.id) AS samples
        FROM zones z LEFT JOIN zone_events e ON e.zone_id=z.id AND e.store_id=z.store_id
        AND e.occurred_at>=? AND e.occurred_at<?
        WHERE z.store_id=? GROUP BY z.id ORDER BY z.id""",(start,end,store_id)).fetchall()]

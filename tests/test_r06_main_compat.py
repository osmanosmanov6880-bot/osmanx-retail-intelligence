"""Compatibility contract with the R0.5 main GitHub schema, not older local draft."""
from datetime import datetime, timedelta, timezone
from test_r06 import site


def replace_legacy_tables_with_published_r05_layout(db):
    with db.connect() as conn:
        # The existing R0.5 schema must not be recreated in production or CI.
        columns={row['name'] for row in conn.execute('PRAGMA table_info(reservations)')}
        has_returns=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='merchandise_returns'").fetchone()
        if 'source_inventory_id' in columns and has_returns:
            return
        conn.execute('PRAGMA foreign_keys=OFF')
        for name in ('reservations','returns_log','decisions'):
            conn.execute(f'DROP TABLE IF EXISTS {name}')
        conn.executescript('''
        CREATE TABLE reservations (
          id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id),
          request_id TEXT NOT NULL,demand_id INTEGER NOT NULL REFERENCES demand(id),
          source_inventory_id INTEGER NOT NULL REFERENCES inventory(id),
          source_store_id INTEGER NOT NULL REFERENCES stores(id),
          destination_store_id INTEGER NOT NULL REFERENCES stores(id),
          quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 20),
          status TEXT NOT NULL CHECK(status IN ('held','collected','cancelled','expired')),
          expires_at TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
          UNIQUE(organization_id,request_id)
        );
        CREATE TABLE merchandise_returns (
          id INTEGER PRIMARY KEY,store_id INTEGER NOT NULL REFERENCES stores(id),
          sale_id INTEGER NOT NULL REFERENCES sales(id),external_id TEXT NOT NULL,
          item_description TEXT NOT NULL,amount_kopeks INTEGER NOT NULL,
          reason TEXT NOT NULL,created_at TEXT NOT NULL,UNIQUE(store_id,external_id)
        );
        ''')
        conn.commit()
        conn.execute('PRAGMA foreign_keys=ON')


def test_r06_reserves_and_converts_using_published_r05_schema(site):
    c,auth,db=site
    replace_legacy_tables_with_published_r05_layout(db)
    north=c.post('/api/admin/stores',headers=auth,json={'slug':'north-r06','name':'Склад Северный'})
    assert north.status_code in (201,409),north.text
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        nid=conn.execute("SELECT id FROM stores WHERE slug='north-r06'").fetchone()['id']
        inventory_id=conn.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                (nid,'WARM-XL','Куртка','XL','чёрный',2,'test',db.now_iso())).lastrowid
        dem=conn.execute('INSERT INTO demand(store_id,product,size,color,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                (sid,'Куртка','XL','чёрный',db.now_iso(),db.now_iso())).lastrowid
        res=conn.execute('''INSERT INTO reservations(organization_id,request_id,demand_id,source_inventory_id,source_store_id,
                 destination_store_id,quantity,status,expires_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (1,'r05-booking-1',dem,inventory_id,nid,sid,1,'held',
                 (datetime.now(timezone.utc)+timedelta(hours=5)).isoformat(timespec='seconds'),db.now_iso(),db.now_iso())).lastrowid
        sale=conn.execute('INSERT INTO sales(store_id,amount_kopeks,source,occurred_at,external_id) VALUES(?,?,?,?,?)',
                (nid,800000,'real-pos',db.now_iso(),'r05-check-1')).lastrowid
        conn.execute('INSERT INTO merchandise_returns(store_id,sale_id,external_id,item_description,amount_kopeks,reason,created_at) VALUES(?,?,?,?,?,?,?)',
                     (nid,sale,'r05-return-1','Куртка',100000,'size',db.now_iso()))
        conn.commit()
    assert c.post('/api/admin/workflows/sale-items',headers=auth,json={'slug':'north-r06','sale_id':sale,'sku':'WARM-XL',
         'quantity':1,'unit_revenue_rub':8000,'unit_cost_rub':4000,'external_id':'line-001'}).status_code==201
    cse=c.post('/api/admin/workflows/cases',headers=auth,json={'slug':'central','demand_id':dem,'sku':'WARM-XL'})
    assert cse.status_code==201,cse.text
    cid=cse.json()['id']
    linked=c.patch(f'/api/admin/workflows/cases/{cid}',headers=auth,json={'action':'reserve','reservation_id':res})
    assert linked.status_code==200,linked.text
    confirmed=c.patch(f'/api/admin/workflows/cases/{cid}',headers=auth,json={'action':'convert','sale_id':sale})
    assert confirmed.status_code==200,confirmed.text
    overview=c.get('/api/admin/workflows/overview?slug=north-r06',headers=auth)
    assert overview.status_code==200,overview.text
    assert overview.json()['finance']['store_returns_kopeks']==100000
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM reservations WHERE id=?',(res,)).fetchone()[0]=='held'
        assert conn.execute('SELECT status FROM demand WHERE id=?',(dem,)).fetchone()[0]=='converted'


def test_receipt_blocks_sku_collision_across_existing_stock_metadata(site):
    c,auth,db=site
    replace_legacy_tables_with_published_r05_layout(db)
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        conn.execute('INSERT INTO inventory(store_id,sku,product,size,color,quantity,source,updated_at) VALUES(?,?,?,?,?,?,?,?)',
                     (sid,'SAME-001','Джинсы','M','синий',5,'source',db.now_iso()))
        conn.commit()
    order=c.post('/api/admin/workflows/orders',headers=auth,json={'slug':'central','supplier':'Factory A',
       'reference':'R06-MISMATCH','lines':[{'sku':'SAME-001','product':'Куртка','size':'XL','color':'чёрный','quantity':3,'unit_cost_rub':'3000'}]})
    assert order.status_code==201,order.text
    oid=order.json()['id']
    line=c.get('/api/admin/workflows/overview',headers=auth).json()['orders'][0]['lines'][0]['id']
    assert c.patch(f'/api/admin/workflows/orders/{oid}',headers=auth,json={'status':'ordered'}).status_code==200
    conflict=c.post(f'/api/admin/workflows/orders/{oid}/receipts',headers=auth,json={'external_id':'document-collision',
        'lines':[{'line_id':line,'quantity':2}]})
    assert conflict.status_code==409,conflict.text
    with db.connect() as conn:
        sid=conn.execute("SELECT id FROM stores WHERE slug='central'").fetchone()['id']
        assert conn.execute('SELECT quantity FROM inventory WHERE store_id=? AND sku=?',(sid,'SAME-001')).fetchone()[0]==5
        assert conn.execute('SELECT COUNT(*) FROM purchase_receipts').fetchone()[0]==0

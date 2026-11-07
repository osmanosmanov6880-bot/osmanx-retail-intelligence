"""Operator-only tenant provisioning, never exposed as a public signup endpoint.

Example:
 OSMANX_NEW_OWNER_PASSWORD='a-strong-private-password' python -m scripts.provision_tenant \
   --slug atelier --name 'Ателье' --store atelier-main --email owner@example.com
"""
from __future__ import annotations
import argparse
import os
import sqlite3
from backend.database import connect, initialize_db, now_iso
from backend.security import hash_password


def provision(db:sqlite3.Connection,*,slug:str,name:str,store_slug:str,email:str,password:str)->dict:
    if not slug or not store_slug or not email or '@' not in email or len(password)<12:
        raise ValueError('Укажите организацию, филиал, почту и пароль (12+ символов)')
    import re
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,40}',slug) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,40}',store_slug):
        raise ValueError('Коды — 2–41 символ: a-z, 0-9, дефис')
    db.execute('BEGIN IMMEDIATE')
    try:
        cur=db.execute('INSERT INTO organizations(slug,name,created_at) VALUES(?,?,?)',(slug,name.strip(),now_iso()))
        org_id=cur.lastrowid
        db.execute('INSERT INTO stores(organization_id,slug,name,timezone,traffic_mode,created_at) VALUES(?,?,?,?,?,?)',
                   (org_id,store_slug,name.strip()+' · главный','Europe/Moscow','auto',now_iso()))
        db.execute('INSERT INTO users(organization_id,email,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?,?)',
                   (org_id,email.strip().lower(),'Владелец',hash_password(password),'owner',now_iso()))
        db.commit()
        return {'organization':slug,'store':store_slug,'owner_email':email.strip().lower()}
    except Exception:
        db.rollback()
        raise


def main():
    parser=argparse.ArgumentParser(description='Provision a separately isolated retail organization')
    parser.add_argument('--slug',required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--store',required=True)
    parser.add_argument('--email',required=True)
    args=parser.parse_args()
    password=os.getenv('OSMANX_NEW_OWNER_PASSWORD','')
    if len(password)<12: parser.error('Set OSMANX_NEW_OWNER_PASSWORD (12+ chars) in environment')
    initialize_db(demo=False)
    with connect() as db:
        print(provision(db,slug=args.slug,name=args.name,store_slug=args.store,email=args.email,password=password))

if __name__=='__main__':
    main()

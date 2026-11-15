"""Pure, side-effect-free R2.3 security checks over an existing OSMANX SQLite DB.

Operational diagnostics, not proof of payment, physical devices or public-host readiness.
No PII is returned; findings are scoped to exactly one store in one organization.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone


def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


def finding(code: str, subject: str, title: str, severity: str = 'block') -> dict:
    return {'code': code, 'subject': subject, 'title': title, 'severity': severity}


def _rows(db: sqlite3.Connection, statement: str, args: tuple) -> list:
    return db.execute(statement, args).fetchall()


def authorization_findings(db: sqlite3.Connection, org_id: int, store_id: int) -> list[dict]:
    """Check actual FK relationships, including malicious cross-tenant assignments."""
    result = []
    rows = _rows(db, '''SELECT a.user_id,u.organization_id AS user_org,s.organization_id AS store_org
        FROM user_store_access a JOIN users u ON u.id=a.user_id
        JOIN stores s ON s.id=a.store_id WHERE a.store_id=? LIMIT 1001''',(store_id,))
    if len(rows) > 1000:
        result.append(finding('access_overflow', str(store_id), 'Более 1000 назначений: нужна постраничная проверка'))
    for r in rows[:1000]:
        if r['user_org'] != r['store_org'] or r['store_org'] != org_id:
            result.append(finding('cross_org_grant', str(r['user_id']), 'Сотрудник другой организации назначен на филиал'))
    devices = _rows(db, '''SELECT id,organization_id FROM devices WHERE store_id=? LIMIT 1001''',(store_id,))
    if len(devices) > 1000:
        result.append(finding('device_overflow', str(store_id), 'Слишком много устройств для полной проверки'))
    for dev in devices[:1000]:
        if dev['organization_id'] != org_id:
            result.append(finding('cross_org_device', str(dev['id']), 'Устройство привязано к чужой организации'))
    if not db.execute('SELECT 1 FROM users WHERE organization_id=? AND role=? AND active=1 LIMIT 1',
                      (org_id,'owner')).fetchone():
        result.append(finding('no_active_owner', str(org_id), 'В организации нет активного владельца'))
    return result


def evidence_findings(db: sqlite3.Connection, org_id: int, store_id: int) -> list[dict]:
    """Validate stored payload digests and foreign-store bindings; never trust labels."""
    result = []
    days = _rows(db, '''SELECT d.id,d.status,d.requested_by,d.reviewed_by,
        r.payload_json,r.payload_sha,r.reviewer_id
      FROM readiness_days_r20 d LEFT JOIN readiness_reviews_r20 r ON r.readiness_id=d.id
      WHERE d.organization_id=? AND d.store_id=? ORDER BY d.id DESC LIMIT 201''',(org_id,store_id))
    if len(days)>200:
        result.append(finding('readiness_overflow',str(store_id),'Слишком много заключений для полной проверки'))
    for d in days[:200]:
        if d['status']!='reviewed':continue
        if not d['payload_json'] or sha_text(d['payload_json'])!=d['payload_sha']:
            result.append(finding('readiness_tampered',str(d['id']),'Подписанный отчёт готовности отсутствует или изменён'))
        if not d['reviewed_by'] or not d['requested_by'] or d['reviewed_by']==d['requested_by'] or d['reviewer_id']!=d['reviewed_by']:
            result.append(finding('readiness_self_review',str(d['id']),'Готовность подтверждена не независимым сотрудником'))
    pilots=_rows(db, '''SELECT p.id,p.status,a.store_id AS proof_store,a.organization_id AS proof_org,
       a.preflight_json,a.preflight_sha FROM pilots_r15 p
       LEFT JOIN assurance_pilot_starts_r21 a ON a.pilot_id=p.id
       WHERE p.organization_id=? AND p.store_id=? ORDER BY p.id DESC LIMIT 501''',(org_id,store_id))
    if len(pilots)>500:
        result.append(finding('pilot_overflow',str(store_id),'Слишком много пилотов для полной проверки'))
    for p in pilots[:500]:
        if p['status']=='draft':continue
        if not p['preflight_json'] or sha_text(p['preflight_json'])!=p['preflight_sha']:
            result.append(finding('pilot_missing_start_proof',str(p['id']),'Пилот запущен без проверенного разрешения R2.1'))
        elif p['proof_org']!=org_id or p['proof_store']!=store_id:
            result.append(finding('pilot_cross_org_proof',str(p['id']),'Разрешение запуска относится к другой организации или филиалу'))
    # A wave may span multiple stores. Include only waves containing the requested store,
    # and check each stage-proof once. Do not accidentally expose another store's data.
    stages=_rows(db, '''SELECT DISTINCT r.id,r.wave_id,r.stage,r.payload_json,r.payload_sha
      FROM rollout_sites_r22 s JOIN rollout_waves_r22 w ON w.id=s.wave_id
      JOIN rollout_stage_proofs_r22 r ON r.wave_id=w.id
      WHERE w.organization_id=? AND s.store_id=? ORDER BY r.id DESC LIMIT 201''',(org_id,store_id))
    if len(stages)>200:
        result.append(finding('rollout_overflow',str(store_id),'Слишком много отчётов волн для полной проверки'))
    for stage in stages[:200]:
        if sha_text(stage['payload_json'])!=stage['payload_sha']:
            result.append(finding('stage_tampered',f"{stage['wave_id']}:{stage['stage']}",'Отчёт этапа масштабирования изменён'))
    return result


def integrity_report(db:sqlite3.Connection,org_id:int,store_id:int)->dict:
    store=db.execute('SELECT id,slug,organization_id FROM stores WHERE id=? AND organization_id=?',(store_id,org_id)).fetchone()
    if not store:raise ValueError('Store does not belong to organization')
    issues=authorization_findings(db,org_id,store_id)+evidence_findings(db,org_id,store_id)
    blocking=sum(x['severity']=='block' for x in issues)
    return {'store':store['slug'],'store_id':store_id,'checks':['store_access','device_scope','owners','readiness_sha','startup_sha','rollout_sha'],
            'status':'blocked' if blocking else 'no_detected_integrity_faults',
            'blocking':blocking,'findings':issues,
            'methodology':'Проверка хешей и связей БД. Не доказывает правильность исходных данных и не является полным аудитом безопасности.'}

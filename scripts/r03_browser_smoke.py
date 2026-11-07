"""R0.3 new module acceptance in real headless Chromium (isolated API TestClient).

Tests the actual UI, forms, rendered layout and API side effects, not an image mockup.
"""
from __future__ import annotations

import os
import sys
import tempfile
import shutil
from datetime import datetime,timezone
from pathlib import Path

from fastapi.testclient import TestClient
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from scripts.visual_smoke import install_page
QA=ROOT/'qa'


def main():
    with tempfile.TemporaryDirectory(prefix='osmanx-r03-ui-') as folder:
        os.environ['OSMANX_DEMO_MODE']='1'
        os.environ['OSMANX_DATA_DIR']=folder
        from backend.app import app
        with TestClient(app) as api, sync_playwright() as playwright:
            browser=playwright.chromium.launch(headless=True,executable_path=shutil.which('chromium') or None,args=['--no-sandbox'])
            page,errors=install_page(browser,api,{'width':1512,'height':950})
            page.get_by_text('Обзор бизнеса').wait_for(timeout=12000)
            page.locator('[data-nav="integrations"]').first.click()
            page.get_by_text('Безопасный импорт',exact=False).wait_for(timeout=6000)
            page.screenshot(path=str(QA/'r03-integrations-desktop.png'),full_page=True)
            page.locator('#import-preview-form select[name="kind"]').select_option('inventory')
            page.locator('#import-preview-form textarea[name="records"]').fill('[{"sku":"R03-XL","product":"Куртка демисезонная","size":"XL","color":"чёрный","quantity":11}]')
            page.locator('#import-preview-form button[type="submit"]').click()
            page.get_by_text('Предпросмотр',exact=False).first.wait_for(timeout=5000)
            page.screenshot(path=str(QA/'r03-import-preview.png'),full_page=True)
            page.on('dialog',lambda d:d.accept())
            page.locator('[data-action="import-apply"]').click()
            page.get_by_text('Импорт применён',exact=False).wait_for(timeout=6000)
            assert any(x['sku']=='R03-XL' and x['quantity']==11 for x in api.get('/api/admin/stock?slug=central').json()['items'])
            page.locator('[data-dialog="device"]').first.click()
            page.locator('#device-form input[name="name"]').fill('Вход A')
            page.locator('#device-form button[type="submit"]').click()
            page.get_by_text('Ключ устройства создан').wait_for(timeout=7000)
            assert page.locator('.code').inner_text().count('dvc_')==1
            page.locator('[data-action="close-dialog"]').click()
            page.locator('[data-nav="team"]').first.click()
            page.get_by_text('Команда и права',exact=False).first.wait_for(timeout=5000)
            page.screenshot(path=str(QA/'r03-team-desktop.png'),full_page=True)
            page.locator('[data-dialog="team"]').first.click()
            page.locator('#team-form input[name="name"]').fill('Тестовый управляющий')
            page.locator('#team-form input[name="email"]').fill('test-manager@example.com')
            page.locator('#team-form input[name="password"]').fill('private-password-2026!')
            page.locator('#team-form button[type="submit"]').click()
            page.get_by_text('Тестовый управляющий',exact=False).first.wait_for(timeout=7000)
            page.locator('[data-nav="settings"]').first.click()
            page.locator('#store-form input[name="reward_daily_limit"]').fill('2')
            page.locator('#store-form select[name="traffic_mode"]').select_option('auto')
            page.locator('#store-form button[type="submit"]').click()
            page.get_by_text('Настройки сохранены').wait_for(timeout=7000)
            assert api.get('/api/admin/stores').json()[0]['reward_daily_limit']==2
            assert not errors, errors
            mobile, errors_m=install_page(browser,api,{'width':390,'height':844})
            mobile.get_by_text('Обзор бизнеса').wait_for(timeout=6000)
            mobile.locator('[data-action="menu"]').click()
            mobile.locator('.sidebar [data-nav="integrations"]').click()
            mobile.get_by_text('Безопасный импорт',exact=False).wait_for(timeout=6000)
            mobile.screenshot(path=str(QA/'r03-integrations-mobile.png'),full_page=True)
            assert not errors_m,errors_m
            browser.close()
            print('R0.3 UI acceptance PASS: import preview/apply, devices, team, settings, 390px mobile')
            print('R0.3 screenshots:',len(list(QA.glob('r03-*.png'))))

if __name__=='__main__':main()

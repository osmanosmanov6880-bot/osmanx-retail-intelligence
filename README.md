# OSMANX Retail Intelligence R0.9 — Evidence Lab

Five real workflows: demand radar, verified recovery cases, finance integrity, pre-registered experiments and immutable evidence dossiers. The software remains local/private — **no public deployment**.

- Open `/static/evidence.html` after local startup.
- See [R0.9 release notes](docs/RELEASE_R09.md).
- Verify: `python -m pytest tests/test_r09.py -q`, `python scripts/r09_browser_smoke.py`.
- Missing stock signals are not guaranteed lost sales. Partial accounting cannot produce a verified profit total.

---

# OSMANX Retail Intelligence R0.8

**Five new commercial decision modules**: restock planning from unmet demand, supplier delivery scorecards, fitting-room insight and evidence-based hypotheses, accountable action queue, and immutable daily management briefs. All in the existing multi-tenant SQLite application; approved dark Russian UI retained. No public deployment.

- Open after local startup: `/static/strategy.html` (login to the main dashboard first outside demo mode).
- [Detailed release and limitations](docs/RELEASE_R08.md).
- Tests: `python -m pytest tests -q` and `python scripts/r08_browser_smoke.py`.
- Additional navigation is provided from the R0.6 and R0.7 operational interfaces.
- Suggestions are **not** forecasts or evidence of missed sales. Purchase order conversion produces a draft and never dispatches it to the supplier.

---

# OSMANX Retail Intelligence R0.7 — операционный центр

**Пять работающих блоков:** инвентаризация с контролем устаревания, безопасные перемещения между филиалами, QR-кнопка консультанта, сравнение зон магазина, проверяемая сводка директора с CSV. Тёмный русскоязычный интерфейс: `/static/operations.html`. Публичный деплой не выполняется.

- [Описание и ограничения R0.7](docs/RELEASE_R07.md)
- Локально: `OSMANX_DEMO_MODE=1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`
- Проверки: `python -m pytest tests -q` и `python scripts/r07_browser_smoke.py`
- **Не выдавайте** демо за реальные продажи; подключение камер, касс и 1С требует отдельной интеграции.

---

# OSMANX Retail Intelligence R0.6

Five linked production-oriented workflows: demand recovery, supplier purchasing, recorded SKU sales and gross margin, before/after pilot evaluations, and an owner action center. Server deployment intentionally deferred. Tests: `python -m pytest tests -q` and Chromium `python scripts/r06_browser_smoke.py`. Read [R0.6 release details](docs/RELEASE_R06.md). The new operational interface is `/static/workflows.html`.

---

# OSMANX Retail Intelligence R0.5

**Five shipped commerce workflows**: cross-branch inventory reservations with transaction-safe stock claims, anonymous fitting-room observations, receipt-linked return logging, scenario-based discount contribution calculations, and a decision center for evidence-based actions. Production deployment remains deferred.

- Release notes and explicit limitations: [R0.5 documentation](docs/RELEASE_R05.md)
- Local demo (synthetic data only): `OSMANX_DEMO_MODE=1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`
- Automated checks: `python -m pytest tests -q` and `python scripts/r05_browser_smoke.py` (requires Playwright Chromium).
- **Reminder**: collecting reserved stock is *not* a POS sale. A manually logged return is *not* a bank refund. Price simulations are *not* revenue forecasts.

---

# OSMANX Retail Intelligence R0.4

**Five working development blocks:** account/session controls, paired survey terminals, signed POS receipt ingestion, source-quality monitoring, and safer SQLite backup/deployment operations. The approved dark navy/red Russian interface is retained. See [R0.4 release notes](docs/RELEASE_R04.md) and [private pilot deployment](docs/DEPLOYMENT.md).

**Local demo only** (synthetic numbers and intentionally open admin access): `OSMANX_DEMO_MODE=1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000`. Visit `/`, `/kiosk/central`, and `/api/ready`.

**Verification:** `PYTHONPATH=. python -m pytest tests -q`, `python scripts/visual_smoke.py`, `python scripts/r03_browser_smoke.py`, `python scripts/r04_browser_smoke.py`.

> Do not expose demo mode to the internet. Real deployment requires TLS, secure credentials, a backup plan, privacy review and actual hardware adapters. R0.4 does not automatically connect to 1C or cameras.

---

# OSMANX RETAIL INTELLIGENCE

**R0.3 — реальное веб-приложение аналитики магазинов одежды.** Функциональный терминал опросов, обезличенный учёт посещений и зон, спрос на отсутствующие товары, остатки по филиалам, подтверждённые покупки, аналитика руководителя, права доступа и безопасный импорт данных. Дизайн: тёмный navy, красные акценты, русский язык, адаптация под планшет и телефон.

> **Статус:** рабочая локальная MVP для пилотов. Это не готовый публичный SaaS. Камеры, оборудование, реальная 1С и кассы **не подключены**. В демо все исторические данные искусственные. Без HTTPS, резервного копирования, проверки безопасности и политики конфиденциальности коммерческое развёртывание запрещено.

## Запуск демонстрации

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
OSMANX_DEMO_MODE=1 python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Windows PowerShell:

```powershell
$env:OSMANX_DEMO_MODE="1"
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

- Кабинет директора: <http://127.0.0.1:8000/>
- Опросник у выхода: <http://127.0.0.1:8000/kiosk/central>
- API docs в локальном демо: <http://127.0.0.1:8000/api/docs>

**Никогда не выставляйте деморежим в публичную сеть:** административные операции в нём доступны без пароля. Docker Compose по умолчанию привязан к `127.0.0.1`.

## Пять инженерных блоков R0.3

| Модуль | Реализовано | Граница ответственности |
|---|---|---|
| Организации и сотрудники | Изолированные организации, роли owner/manager/analyst/viewer, назначение филиалов, отзыв сессий | CLI-подключение компаний, не публичная самостоятельная регистрация |
| Датчики | Подписанные события HMAC-SHA256, отдельные ключи, ротация/отзыв, защиты от повторов | Требуется физическое подключение и HTTPS |
| Импорты | Двухшаговый предпросмотр и атомарная запись чеков/остатков, 24-часовой срок проверки | Нет прямого коннектора 1С; ввод JSON после подготовки экспорта |
| Опросы и бонусы | 4 вопроса, уникальные коды, дневная квота, одноразовое погашение, настраиваемая очистка | Скидки проверяет продавец, не касса; необходима правовая оценка |
| Директор и качество данных | Конверсия, спрос, зоны, пилоты, источники и предупреждения об ошибочном объединении потоков | Нет распознавания лиц или доказанного AI-прогноза продаж |

## Настоящий режим (внутренний защищённый пилот)

**Не храните секреты в GitHub.** Используйте env/secret manager:

```bash
export OSMANX_DEMO_MODE=0
export OSMANX_ADMIN_PASSWORD='choose-a-unique-very-strong-initial-password'
export OSMANX_BOOTSTRAP_EMAIL='owner@yourcompany.example'
export OSMANX_SESSION_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
export OSMANX_DEVICE_MASTER_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(48))')"
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

При первом запуске создаётся основной владелец в SQLite с заданной почтой и хешем пароля. После изменения пароля в env уже созданный аккаунт сам не изменится: это НЕ механизм сброса пароля. Ключи `SESSION_SECRET` и `DEVICE_MASTER_SECRET` следует хранить неизменными и защищёнными. Потеря ключа подписи требует переавторизации пользователей; потеря мастер-ключа устройств требует ротации ключей на шлюзах.

Другую организацию создаёт **оператор сервера** через `scripts/provision_tenant.py`, без публичного API регистрации. Пример и ограничения — [docs/RELEASE_R03.md](docs/RELEASE_R03.md).

## Подключение счётчика входов и зон

1. Войти в кабинет под владельцем/управляющим → «Интеграции» → «Добавить устройство». Выбрать филиал и тип `traffic` или `zones`.
2. Один раз сохранить выданные `device_id` и `secret` в конфигурации **серверного шлюза**, не на публичном планшете.
3. Настроить шлюз отправлять данные по HTTPS в `/api/ingest/v2/traffic` или `/api/ingest/v2/zones`.
4. Передавать три заголовка: `X-OSMANX-Device`, `X-OSMANX-Timestamp` (Unix UTC seconds) и `X-OSMANX-Signature` (HMAC SHA256 в hex). Данные подписи: `timestamp + '\n' + device_id + '\n' + raw_json_bytes`, HMAC key — возвращённый секрет устройства как UTF-8 строка.
5. В теле JSON: `quantity` (1–10000), `external_id` (уникальный ID события устройства), `occurred_at` (ISO 8601 с timezone), и `zone_code` только для зон. Повтор с тем же ID и иным телом запрещён; подпись живёт 5 минут.

Пример реальной подписи и отправки: `python -m scripts.send_device_event --kind traffic --quantity 1 --external-id entrance-001`, настроив `OSMANX_DEVICE_ID`, `OSMANX_DEVICE_SECRET`, `OSMANX_SENSOR_URL` (https или localhost). **Статус API ≠ подключённая камера.**

## Безопасный импорт данных

«Интеграции» → выберите тип → вставьте JSON-массив чеков или остатков → «Проверить импорт» → просмотрите новые/изменённые/повторяющиеся записи → «Подтвердить и применить».

Чек:

```json
[{"external_id":"receipt-123","amount_rub":5490.50,"occurred_at":"2026-11-08T12:00:00+03:00"}]
```

Остаток:

```json
[{"sku":"COAT-BLK-XL","product":"Куртка","size":"XL","color":"чёрный","quantity":4}]
```

Сервер проверяет вход, фиксирует контрольную сумму, ищет конфликты и перепроверяет пакет при применении в одной SQLite-транзакции. Нельзя повторно импортировать чек с тем же ID, но другой суммой без отдельного разбора. Данные в формате CSV/1C сначала нужно преобразовать в эти JSON-структуры. **Автоматической синхронизации с конкретной конфигурацией 1С пока нет.**

## Опросник и хранение данных

Покупатели добровольно оценивают магазин, указывают факт покупки, причину отказа, понравившееся и пожелания. Система не запрашивает лица, имя, телефон или контакты. Свободный текст потенциально может содержать личные данные, введённые по инициативе посетителя. Учитывайте применимые нормы, уведомляйте об обработке данных и не выдавайте автоматическую скидку как гарантированную. Бонус — одноразовый код для ручной проверки, с дневным лимитом.

Владелец задаёт срок хранения ответов 7–365 дней. Для реального применения настройте регулярную очистку на сервере:

```bash
python -m scripts.purge_surveys        # только предварительная оценка
python -m scripts.purge_surveys --apply # реальное удаление ответов и бонусов с истекшим сроком
```

## Проверки

```bash
pip install pytest httpx playwright
python -m pytest tests -q
python -m compileall -q backend scripts
node --check frontend/app.js
python scripts/visual_smoke.py
python scripts/r03_browser_smoke.py
```

Chromium проверяет реальные клики, формы, запись данных, размер экрана 390px. Тестовая среда использует FastAPI TestClient вместо публичного HTTP-адреса; полноценную приёмку защищённого HTTPS-сервера и физического планшета предстоит выполнить отдельно.

**Технические подробности:** [docs/RELEASE_R03.md](docs/RELEASE_R03.md) · **Предыдущий релиз:** [docs/RELEASE_R02.md](docs/RELEASE_R02.md).

© 2026 OSMANX WORLD · osmanx.world

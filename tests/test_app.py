from werkzeug.security import generate_password_hash

from db import (
    get_recent_audit_log,
    get_setting,
    record_login_attempt,
    set_setting,
    upsert_product_from_apilo,
)


def test_login_success_records_audit_entry(app_module, client):
    set_setting(app_module.DB_PATH, "password_hash", generate_password_hash("haslo-testowe"))
    with client.session_transaction() as session:
        session["csrf_token"] = "login-csrf"

    response = client.post(
        "/login",
        data={"password": "haslo-testowe", "csrf_token": "login-csrf"},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with client.session_transaction() as session:
        assert session["logged_in"] is True
    audit_rows = get_recent_audit_log(app_module.DB_PATH, limit=5)
    assert audit_rows[0]["action"] == "login_success"
    assert audit_rows[0]["entity_type"] == "auth"


def test_login_rate_limit_blocks_after_limit(app_module, client):
    set_setting(app_module.DB_PATH, "password_hash", generate_password_hash("inne-haslo"))
    with client.session_transaction() as session:
        session["csrf_token"] = "rate-csrf"

    for _ in range(app_module.LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
        record_login_attempt(app_module.DB_PATH, "127.0.0.1")

    response = client.post(
        "/login",
        data={"password": "zle-haslo", "csrf_token": "rate-csrf"},
        environ_base={"REMOTE_ADDR": "127.0.0.1"},
    )

    assert response.status_code == 429
    assert "Za dużo nieudanych prób logowania" in response.get_data(as_text=True)


def test_post_without_csrf_is_rejected(client):
    response = client.post("/logout")

    assert response.status_code == 400
    assert response.get_data(as_text=True) == "Bad Request"


def test_setup_password_blocks_remote_request_without_setup_token(client):
    response = client.get(
        "/setup-password",
        environ_base={"REMOTE_ADDR": "192.168.1.50"},
    )

    assert response.status_code == 403
    assert "Pierwsze ustawienie hasła jest dozwolone tylko lokalnie" in response.get_data(
        as_text=True
    )


def test_alert_settings_save_and_render(app_module, logged_in_client):
    response = logged_in_client.post(
        "/settings",
        data={
            "action": "alerts_settings",
            "alerts_low_stock_enabled": "1",
            "alerts_low_stock_interval_hours": "12",
            "csrf_token": "test-csrf-token",
        },
    )

    assert response.status_code == 302
    assert get_setting(app_module.DB_PATH, "alerts_low_stock_enabled") == "1"
    assert get_setting(app_module.DB_PATH, "alerts_low_stock_interval_hours") == "12"

    page = logged_in_client.get("/settings")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Włącz automatyczny alert niskich stanów" in html
    assert 'value="12"' in html

    audit_rows = get_recent_audit_log(app_module.DB_PATH, limit=5)
    assert audit_rows[0]["action"] == "low_stock_alert_settings_update"


def test_manual_sync_pull_records_audit_entry(app_module, logged_in_client, monkeypatch):
    monkeypatch.setattr(app_module, "run_sync_pull_with_lock", lambda blocking=False: 7)

    response = logged_in_client.post(
        "/sync/pull",
        data={"csrf_token": "test-csrf-token"},
    )

    assert response.status_code == 302
    audit_rows = get_recent_audit_log(app_module.DB_PATH, limit=5)
    assert audit_rows[0]["action"] == "manual_sync_pull"
    assert audit_rows[0]["new_value"] == "7 produktów"


def test_process_low_stock_alert_skips_duplicate_auto_send(app_module, monkeypatch):
    sent_counts = []
    first_rows = [
        {"name": "Produkt A", "ean": "111", "quantity": 1, "suggested_qty": 5, "shortage_qty": 4},
        {"name": "Produkt B", "ean": "222", "quantity": 0, "suggested_qty": 3, "shortage_qty": 3},
    ]
    second_rows = [
        {"name": "Produkt A", "ean": "111", "quantity": 1, "suggested_qty": 6, "shortage_qty": 5},
    ]
    monkeypatch.setattr(app_module, "get_low_stock_rows", lambda limit=10: first_rows)
    monkeypatch.setattr(
        app_module,
        "send_low_stock_alert_email",
        lambda rows: sent_counts.append(len(rows)),
    )

    manual_result = app_module.process_low_stock_alert(mode="manual")
    auto_duplicate_result = app_module.process_low_stock_alert(mode="auto")
    monkeypatch.setattr(app_module, "get_low_stock_rows", lambda limit=10: second_rows)
    auto_sent_result = app_module.process_low_stock_alert(mode="auto")

    assert manual_result == {"status": "sent", "count": 2}
    assert auto_duplicate_result == {"status": "duplicate", "count": 2}
    assert auto_sent_result == {"status": "sent", "count": 1}
    assert sent_counts == [2, 1]
    assert get_setting(app_module.DB_PATH, "alerts_low_stock_last_result") == (
        "Wysłano alert automatycznie (1 pozycja)."
    )

    audit_rows = get_recent_audit_log(app_module.DB_PATH, limit=10)
    send_actions = [row for row in audit_rows if row["action"] == "low_stock_alert_send"]
    assert len(send_actions) == 2
    assert send_actions[0]["actor_ip"] == "system"


def test_sales_report_uses_realized_query_flag(app_module, logged_in_client, monkeypatch):
    calls = []

    def fake_get_sales_totals(days, realized_only=True):
        calls.append((days, realized_only))
        return (
            {"5901234123457": 3},
            {"orders_total": 5, "orders_used": 3, "realized_filter": realized_only},
            {},
        )

    monkeypatch.setattr(app_module, "tokens_missing", lambda: False)
    monkeypatch.setattr(app_module, "get_sales_totals", fake_get_sales_totals)
    monkeypatch.setattr(
        app_module,
        "build_sales_report_rows",
        lambda db_path, totals: [
            {"ean": "5901234123457", "name": "Produkt testowy", "quantity": 3}
        ],
    )

    response = logged_in_client.get("/sales-report?days=30&realized=0")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert calls == [(30, False)]
    assert "Produkt testowy" in html


def test_healthz_returns_ok_payload(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["version"]


def test_index_csv_export_uses_current_filters(app_module, logged_in_client, monkeypatch):
    monkeypatch.setattr(app_module, "tokens_missing", lambda: False)
    upsert_product_from_apilo(
        app_module.DB_PATH,
        {
            "id": 101,
            "originalCode": "KOD-1",
            "sku": "SKU-ALFA",
            "ean": "5901111111111",
            "name": "Produkt Alfa",
            "priceWithTax": 12.5,
            "priceWithoutTax": 10.16,
            "quantity": 7,
            "status": 1,
        },
    )
    upsert_product_from_apilo(
        app_module.DB_PATH,
        {
            "id": 102,
            "originalCode": "KOD-2",
            "sku": "SKU-BETA",
            "ean": "5902222222222",
            "name": "Produkt Beta",
            "priceWithTax": 22.5,
            "priceWithoutTax": 18.29,
            "quantity": 3,
            "status": 1,
        },
    )

    response = logged_in_client.get(
        "/?search=Alfa&sort=name&order=asc&export=1"
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert "attachment; filename=produkty_all_" in response.headers["Content-Disposition"]
    assert "Produkt Alfa" in body
    assert "Produkt Beta" not in body
    assert "Apilo ID;SKU;Kod oryginalny;Nazwa;EAN;Stan;" in body

    audit_rows = get_recent_audit_log(app_module.DB_PATH, limit=5)
    assert audit_rows[0]["action"] == "products_export_csv"

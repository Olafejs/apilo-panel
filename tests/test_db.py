import sqlite3

from db import (
    get_products,
    get_setting,
    get_tokens,
    migrate_secret_storage,
    save_tokens,
    set_setting,
    upsert_product_from_apilo,
)


def test_secret_settings_are_encrypted_at_rest(app_module):
    set_setting(app_module.DB_PATH, "smtp_password", "smtp-tajne")

    conn = sqlite3.connect(app_module.DB_PATH)
    raw_value = conn.execute(
        "SELECT value FROM settings WHERE key = 'smtp_password'"
    ).fetchone()[0]
    conn.close()

    assert raw_value.startswith("enc:v1:")
    assert get_setting(app_module.DB_PATH, "smtp_password") == "smtp-tajne"


def test_tokens_are_encrypted_and_legacy_plaintext_can_be_migrated(app_module):
    save_tokens(
        app_module.DB_PATH,
        {
            "access_token": "access-secret",
            "access_token_expires_at": "2026-03-12T00:00:00+00:00",
            "refresh_token": "refresh-secret",
            "refresh_token_expires_at": "2026-03-13T00:00:00+00:00",
        },
    )

    conn = sqlite3.connect(app_module.DB_PATH)
    encrypted_tokens = conn.execute(
        "SELECT access_token, refresh_token FROM tokens WHERE id = 1"
    ).fetchone()
    assert encrypted_tokens[0].startswith("enc:v1:")
    assert encrypted_tokens[1].startswith("enc:v1:")

    conn.execute("DELETE FROM tokens")
    conn.execute(
        """
        INSERT INTO tokens (
            id,
            access_token,
            access_token_expires_at,
            refresh_token,
            refresh_token_expires_at,
            updated_at
        ) VALUES (1, ?, ?, ?, ?, ?)
        """,
        (
            "legacy-access",
            "2026-03-12T00:00:00+00:00",
            "legacy-refresh",
            "2026-03-13T00:00:00+00:00",
            "2026-03-11T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    migrated = migrate_secret_storage(app_module.DB_PATH)
    tokens = get_tokens(app_module.DB_PATH)
    conn = sqlite3.connect(app_module.DB_PATH)
    migrated_tokens = conn.execute(
        "SELECT access_token, refresh_token FROM tokens WHERE id = 1"
    ).fetchone()
    conn.close()

    assert migrated["tokens"] == 2
    assert migrated_tokens[0].startswith("enc:v1:")
    assert migrated_tokens[1].startswith("enc:v1:")
    assert tokens["access_token"] == "legacy-access"
    assert tokens["refresh_token"] == "legacy-refresh"


def test_get_products_without_limit_returns_all_filtered_rows(app_module):
    upsert_product_from_apilo(
        app_module.DB_PATH,
        {
            "id": 201,
            "originalCode": "ALFA-1",
            "sku": "SKU-ALFA",
            "ean": "5900000000201",
            "name": "Produkt Alfa",
            "priceWithTax": 10.0,
            "priceWithoutTax": 8.13,
            "quantity": 4,
            "status": 1,
        },
    )
    upsert_product_from_apilo(
        app_module.DB_PATH,
        {
            "id": 202,
            "originalCode": "BETA-2",
            "sku": "SKU-BETA",
            "ean": "5900000000202",
            "name": "Produkt Beta",
            "priceWithTax": 20.0,
            "priceWithoutTax": 16.26,
            "quantity": 2,
            "status": 1,
        },
    )

    rows = get_products(
        app_module.DB_PATH,
        search="Produkt",
        sort="name",
        order="asc",
        limit=None,
        offset=0,
    )

    assert [row["name"] for row in rows] == ["Produkt Alfa", "Produkt Beta"]

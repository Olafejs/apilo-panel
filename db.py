import sqlite3
import os
from datetime import datetime, timezone


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_db(db_path):
    if db_path != ":memory:":
        db_dir = os.path.dirname(os.path.abspath(db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        pass
    return conn


def init_db(db_path):
    conn = get_db(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apilo_id INTEGER UNIQUE,
                original_code TEXT,
                sku TEXT,
                ean TEXT,
                image_url TEXT,
                name TEXT,
                price_with_tax TEXT,
                price_without_tax TEXT,
                allegro_price_with_tax TEXT,
                allegro_auction_id TEXT,
                quantity INTEGER,
                status INTEGER,
                last_synced_quantity INTEGER,
                dirty INTEGER DEFAULT 0,
                updated_at TEXT,
                last_synced_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                access_token TEXT,
                access_token_expires_at TEXT,
                refresh_token TEXT,
                refresh_token_expires_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sales_cache (
                ean TEXT PRIMARY KEY,
                quantity_30d INTEGER,
                daily_json TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sales_cache_year (
                ean TEXT PRIMARY KEY,
                quantity_year INTEGER,
                orders_year INTEGER,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_ean ON products(ean)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_apilo_id ON products(apilo_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_original_code ON products(original_code)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_created ON login_attempts(ip_address, created_at)"
        )
    _ensure_column(db_path, "products", "ean", "TEXT")
    _ensure_column(db_path, "products", "image_url", "TEXT")
    _ensure_column(db_path, "products", "price_with_tax", "TEXT")
    _ensure_column(db_path, "products", "price_without_tax", "TEXT")
    _ensure_column(db_path, "products", "allegro_price_with_tax", "TEXT")
    _ensure_column(db_path, "products", "allegro_auction_id", "TEXT")
    _ensure_column(db_path, "sales_cache", "daily_json", "TEXT")
    _ensure_price_columns_real(db_path)
    conn.close()


def get_tokens(db_path):
    conn = get_db(db_path)
    row = conn.execute("SELECT * FROM tokens WHERE id = 1").fetchone()
    conn.close()
    return dict(row) if row else None


def save_tokens(db_path, tokens):
    now = utc_now_iso()
    conn = get_db(db_path)
    with conn:
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
            ON CONFLICT(id) DO UPDATE SET
                access_token = excluded.access_token,
                access_token_expires_at = excluded.access_token_expires_at,
                refresh_token = excluded.refresh_token,
                refresh_token_expires_at = excluded.refresh_token_expires_at,
                updated_at = excluded.updated_at
            """,
            (
                tokens.get("access_token"),
                tokens.get("access_token_expires_at"),
                tokens.get("refresh_token"),
                tokens.get("refresh_token_expires_at"),
                now,
            ),
        )
    conn.close()


def _ensure_column(db_path, table, column, column_def):
    conn = get_db(db_path)
    columns = conn.execute(f"PRAGMA table_info({table})").fetchall()
    if not any(row["name"] == column for row in columns):
        with conn:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
    conn.close()


def _ensure_price_columns_real(db_path):
    conn = get_db(db_path)
    columns = conn.execute("PRAGMA table_info(products)").fetchall()
    types = {row["name"]: (row["type"] or "").upper() for row in columns}
    targets = ("price_with_tax", "price_without_tax", "allegro_price_with_tax")
    if all(types.get(name) == "REAL" for name in targets):
        conn.close()
        return
    existing = {row["name"] for row in columns}

    def col_expr(name):
        if name not in existing:
            return "NULL"
        if name in targets:
            return f"CAST({name} AS REAL)"
        return name

    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apilo_id INTEGER UNIQUE,
                original_code TEXT,
                sku TEXT,
                ean TEXT,
                image_url TEXT,
                name TEXT,
                price_with_tax REAL,
                price_without_tax REAL,
                allegro_price_with_tax REAL,
                allegro_auction_id TEXT,
                quantity INTEGER,
                status INTEGER,
                last_synced_quantity INTEGER,
                dirty INTEGER DEFAULT 0,
                updated_at TEXT,
                last_synced_at TEXT
            )
            """
        )
        conn.execute(
            f"""
            INSERT INTO products_new (
                id,
                apilo_id,
                original_code,
                sku,
                ean,
                image_url,
                name,
                price_with_tax,
                price_without_tax,
                allegro_price_with_tax,
                allegro_auction_id,
                quantity,
                status,
                last_synced_quantity,
                dirty,
                updated_at,
                last_synced_at
            )
            SELECT
                {col_expr("id")},
                {col_expr("apilo_id")},
                {col_expr("original_code")},
                {col_expr("sku")},
                {col_expr("ean")},
                {col_expr("image_url")},
                {col_expr("name")},
                {col_expr("price_with_tax")},
                {col_expr("price_without_tax")},
                {col_expr("allegro_price_with_tax")},
                {col_expr("allegro_auction_id")},
                {col_expr("quantity")},
                {col_expr("status")},
                {col_expr("last_synced_quantity")},
                {col_expr("dirty")},
                {col_expr("updated_at")},
                {col_expr("last_synced_at")}
            FROM products
            """
        )
        conn.execute("DROP TABLE products")
        conn.execute("ALTER TABLE products_new RENAME TO products")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_ean ON products(ean)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_apilo_id ON products(apilo_id)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_original_code ON products(original_code)"
        )
    conn.close()


def upsert_product_from_apilo(db_path, product):
    now = utc_now_iso()
    conn = get_db(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO products (
                apilo_id,
                original_code,
                sku,
                ean,
                image_url,
                name,
                price_with_tax,
                price_without_tax,
                allegro_price_with_tax,
                allegro_auction_id,
                quantity,
                status,
                last_synced_quantity,
                dirty,
                updated_at,
                last_synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(apilo_id) DO UPDATE SET
                sku = excluded.sku,
                ean = excluded.ean,
                name = excluded.name,
                original_code = excluded.original_code,
                price_with_tax = excluded.price_with_tax,
                price_without_tax = excluded.price_without_tax,
                status = excluded.status,
                quantity = excluded.quantity,
                last_synced_quantity = excluded.last_synced_quantity,
                updated_at = excluded.updated_at,
                last_synced_at = excluded.last_synced_at
            """,
            (
                product.get("id"),
                product.get("originalCode"),
                product.get("sku"),
                product.get("ean"),
                product.get("image_url"),
                product.get("name"),
                product.get("priceWithTax"),
                product.get("priceWithoutTax"),
                None,
                None,
                product.get("quantity"),
                product.get("status"),
                product.get("quantity"),
                0,
                now,
                now,
            ),
        )
    conn.close()


def get_products(
    db_path,
    search=None,
    preset="all",
    sort="name",
    order="asc",
    limit=50,
    offset=0,
    lead_time_days=14,
    safety_pct=20,
    suggest_days=30,
):
    allowed = {
        "name": "name",
        "quantity": "quantity",
        "suggested": "suggested_qty",
        "shortage": "shortage_qty",
        "stock_value": "stock_value",
        "sales_year": "quantity_year",
        "updated": "updated_at",
    }
    sort_col = allowed.get(sort, "name")
    order_dir = "DESC" if order == "desc" else "ASC"
    if sort_col == "name":
        order_clause = f"{sort_col} COLLATE NOCASE {order_dir}"
    else:
        order_clause = f"{sort_col} {order_dir}"
    try:
        suggest_days = int(suggest_days)
    except (TypeError, ValueError):
        suggest_days = 30
    if suggest_days < 1:
        suggest_days = 30
    query_base, params = _build_products_scope(
        search=search,
        preset=preset,
        lead_time_days=lead_time_days,
        safety_pct=safety_pct,
        suggest_days=suggest_days,
    )
    query = f"""
        SELECT *
        FROM ({query_base}) AS computed
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    conn = get_db(db_path)
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return rows


def _build_products_scope(
    search=None,
    preset="all",
    lead_time_days=14,
    safety_pct=20,
    suggest_days=30,
):
    base_query = """
        SELECT
            base.*,
            CASE
                WHEN base.suggested_qty IS NULL THEN NULL
                ELSE base.suggested_qty - COALESCE(base.quantity, 0)
            END AS shortage_qty,
            ROUND(
                COALESCE(base.quantity, 0) * COALESCE(base.allegro_price_with_tax, base.price_with_tax, 0),
                2
            ) AS stock_value
        FROM (
            SELECT
                p.*,
                sc.quantity_30d,
                scy.quantity_year,
                scy.orders_year,
                CASE
                    WHEN sc.quantity_30d IS NULL AND COALESCE(scy.quantity_year, 0) = 0 THEN NULL
                    ELSE CAST(
                        (
                            CASE
                                WHEN COALESCE(sc.quantity_30d, 0) = 0
                                    AND COALESCE(scy.quantity_year, 0) > 0
                                    THEN COALESCE(scy.quantity_year, 0) / 365.0
                                ELSE COALESCE(sc.quantity_30d, 0) / CAST(? AS REAL)
                            END
                        ) * ? * (1 + ? / 100.0) + 0.9999
                        AS INTEGER
                    )
                END AS suggested_qty
            FROM products p
            LEFT JOIN sales_cache sc ON sc.ean = p.ean
            LEFT JOIN sales_cache_year scy ON scy.ean = p.ean
        ) AS base
    """
    params = [suggest_days, lead_time_days, safety_pct]
    where_clauses = []
    if search:
        like = f"%{search}%"
        where_clauses.append("(sku LIKE ? OR name LIKE ? OR original_code LIKE ? OR ean LIKE ?)")
        params.extend([like, like, like, like])
    if preset == "shortage":
        where_clauses.append("COALESCE(shortage_qty, 0) > 0")
    elif preset == "out_of_stock":
        where_clauses.append("COALESCE(quantity, 0) = 0")
    elif preset == "no_ean":
        where_clauses.append("(ean IS NULL OR ean = '')")
    elif preset == "no_image":
        where_clauses.append("(image_url IS NULL OR image_url = '')")
    elif preset == "no_sales":
        where_clauses.append("COALESCE(quantity_year, 0) = 0")
    elif preset == "high_value":
        where_clauses.append("COALESCE(stock_value, 0) > 0")
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    return f"SELECT * FROM ({base_query}) AS computed {where_sql}", params


def get_products_count(
    db_path,
    search=None,
    preset="all",
    lead_time_days=14,
    safety_pct=20,
    suggest_days=30,
):
    query_base, params = _build_products_scope(
        search=search,
        preset=preset,
        lead_time_days=lead_time_days,
        safety_pct=safety_pct,
        suggest_days=suggest_days,
    )
    conn = get_db(db_path)
    row = conn.execute(
        f"SELECT COUNT(*) AS count FROM ({query_base}) AS computed",
        tuple(params),
    ).fetchone()
    conn.close()
    return row["count"] if row else 0


def get_dashboard_metrics(db_path, lead_time_days=14, safety_pct=20, suggest_days=30):
    query_base, params = _build_products_scope(
        search=None,
        preset="all",
        lead_time_days=lead_time_days,
        safety_pct=safety_pct,
        suggest_days=suggest_days,
    )
    conn = get_db(db_path)
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total_products,
            SUM(CASE WHEN COALESCE(shortage_qty, 0) > 0 THEN 1 ELSE 0 END) AS shortage_count,
            SUM(CASE WHEN COALESCE(shortage_qty, 0) > 0 THEN shortage_qty ELSE 0 END) AS shortage_units,
            SUM(CASE WHEN COALESCE(quantity, 0) = 0 THEN 1 ELSE 0 END) AS out_of_stock_count,
            SUM(CASE WHEN ean IS NULL OR ean = '' THEN 1 ELSE 0 END) AS missing_ean_count,
            SUM(CASE WHEN image_url IS NULL OR image_url = '' THEN 1 ELSE 0 END) AS missing_image_count,
            SUM(CASE WHEN COALESCE(quantity_year, 0) = 0 THEN 1 ELSE 0 END) AS no_sales_count,
            SUM(CASE WHEN COALESCE(stock_value, 0) > 0 THEN 1 ELSE 0 END) AS high_value_count,
            ROUND(COALESCE(SUM(stock_value), 0), 2) AS inventory_value
        FROM ({query_base}) AS computed
        """,
        tuple(params),
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_product_by_id(db_path, product_id):
    conn = get_db(db_path)
    row = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    conn.close()
    return row


def get_product_by_apilo_id(db_path, apilo_id):
    conn = get_db(db_path)
    row = conn.execute(
        "SELECT * FROM products WHERE apilo_id = ?",
        (apilo_id,),
    ).fetchone()
    conn.close()
    return row


def get_ean_name_map(db_path):
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT ean, name FROM products WHERE ean IS NOT NULL AND ean != ''"
    ).fetchall()
    conn.close()
    return {row["ean"]: row["name"] for row in rows}


def get_product_maps(db_path):
    conn = get_db(db_path)
    rows = conn.execute(
        """
        SELECT apilo_id, ean, original_code, sku
        FROM products
        WHERE ean IS NOT NULL AND ean != ''
        """
    ).fetchall()
    conn.close()
    by_apilo_id = {}
    by_original_code = {}
    by_sku = {}
    for row in rows:
        ean = row["ean"]
        if row["apilo_id"]:
            by_apilo_id[str(row["apilo_id"])] = ean
        if row["original_code"]:
            by_original_code[row["original_code"]] = ean
        if row["sku"]:
            by_sku[row["sku"]] = ean
    return by_apilo_id, by_original_code, by_sku


def get_product_id_maps(db_path):
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT apilo_id, ean, sku FROM products WHERE apilo_id IS NOT NULL"
    ).fetchall()
    conn.close()
    by_sku = {}
    by_ean = {}
    by_apilo_id = {}
    for row in rows:
        apilo_id = row["apilo_id"]
        if apilo_id is None:
            continue
        by_apilo_id[str(apilo_id)] = apilo_id
        if row["sku"]:
            by_sku[row["sku"]] = apilo_id
        if row["ean"]:
            by_ean[row["ean"]] = apilo_id
    return by_apilo_id, by_sku, by_ean


def update_allegro_prices(db_path, price_map):
    if not price_map:
        return
    conn = get_db(db_path)
    with conn:
        conn.executemany(
            "UPDATE products SET allegro_price_with_tax = ? WHERE apilo_id = ?",
            [(value, key) for key, value in price_map.items()],
        )
    conn.close()


def get_base_price_map(db_path):
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT apilo_id, price_with_tax FROM products WHERE apilo_id IS NOT NULL"
    ).fetchall()
    conn.close()
    result = {}
    for row in rows:
        if row["price_with_tax"] is not None:
            result[row["apilo_id"]] = row["price_with_tax"]
    return result


def update_allegro_auction_ids(db_path, auction_map):
    conn = get_db(db_path)
    try:
        with conn:
            conn.execute("UPDATE products SET allegro_auction_id = NULL")
            if auction_map:
                conn.executemany(
                    "UPDATE products SET allegro_auction_id = ? WHERE apilo_id = ?",
                    [(value, key) for key, value in auction_map.items()],
                )
    finally:
        conn.close()


def get_inventory_value_totals(db_path):
    conn = get_db(db_path)
    row = conn.execute(
        """
        SELECT
            SUM(CASE WHEN price_with_tax IS NOT NULL THEN quantity * price_with_tax ELSE 0 END) AS store_total,
            SUM(CASE WHEN allegro_price_with_tax IS NOT NULL THEN quantity * allegro_price_with_tax ELSE 0 END) AS allegro_total
        FROM products
        """
    ).fetchone()
    conn.close()
    store_total = row["store_total"] if row and row["store_total"] is not None else 0
    allegro_total = row["allegro_total"] if row and row["allegro_total"] is not None else 0
    return float(store_total), float(allegro_total)


def save_sales_cache(db_path, totals, details_map):
    now = utc_now_iso()
    conn = get_db(db_path)
    with conn:
        conn.execute("DELETE FROM sales_cache")
        if totals:
            import json
            conn.executemany(
                """
                INSERT INTO sales_cache (ean, quantity_30d, daily_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (ean, qty, json.dumps(details_map.get(ean, [])), now)
                    for ean, qty in totals.items()
                ],
            )
    conn.close()


def get_sales_cache_map(db_path):
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT ean, quantity_30d FROM sales_cache"
    ).fetchall()
    conn.close()
    return {row["ean"]: row["quantity_30d"] for row in rows}


def get_sales_cache_details_map(db_path):
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT ean, daily_json FROM sales_cache WHERE daily_json IS NOT NULL"
    ).fetchall()
    conn.close()
    import json
    result = {}
    for row in rows:
        try:
            result[row["ean"]] = json.loads(row["daily_json"])
        except (TypeError, json.JSONDecodeError):
            continue
    return result


def save_sales_year_cache(db_path, totals, order_counts):
    now = utc_now_iso()
    conn = get_db(db_path)
    with conn:
        conn.execute("DELETE FROM sales_cache_year")
        rows = [
            (ean, qty, order_counts.get(ean, 0), now)
            for ean, qty in totals.items()
        ]
        conn.executemany(
            """
            INSERT INTO sales_cache_year (ean, quantity_year, orders_year, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
    conn.close()


def get_sales_year_map(db_path):
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT ean, quantity_year, orders_year FROM sales_cache_year"
    ).fetchall()
    conn.close()
    return {
        row["ean"]: {"quantity": row["quantity_year"], "orders": row["orders_year"]}
        for row in rows
    }


def update_product_image(db_path, apilo_id, image_url):
    now = utc_now_iso()
    conn = get_db(db_path)
    with conn:
        conn.execute(
            """
            UPDATE products
            SET image_url = ?,
                updated_at = ?
            WHERE apilo_id = ?
            """,
            (image_url, now, apilo_id),
        )
    conn.close()




def update_product_quantity(db_path, product_id, quantity):
    now = utc_now_iso()
    conn = get_db(db_path)
    with conn:
        conn.execute(
            """
            UPDATE products
            SET quantity = ?,
                dirty = 0,
                last_synced_quantity = ?,
                last_synced_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (quantity, quantity, now, now, product_id),
        )
    conn.close()


def prune_login_attempts(db_path, before_iso):
    conn = get_db(db_path)
    with conn:
        conn.execute("DELETE FROM login_attempts WHERE created_at < ?", (before_iso,))
    conn.close()


def count_recent_login_attempts(db_path, ip_address, since_iso):
    conn = get_db(db_path)
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM login_attempts
        WHERE ip_address = ? AND created_at >= ?
        """,
        (ip_address, since_iso),
    ).fetchone()
    conn.close()
    return row["count"] if row else 0


def record_login_attempt(db_path, ip_address):
    conn = get_db(db_path)
    with conn:
        conn.execute(
            "INSERT INTO login_attempts (ip_address, created_at) VALUES (?, ?)",
            (ip_address, utc_now_iso()),
        )
    conn.close()


def clear_login_attempts(db_path, ip_address):
    conn = get_db(db_path)
    with conn:
        conn.execute("DELETE FROM login_attempts WHERE ip_address = ?", (ip_address,))
    conn.close()


def get_setting(db_path, key):
    conn = get_db(db_path)
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,),
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def set_setting(db_path, key, value):
    now = utc_now_iso()
    conn = get_db(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
    conn.close()

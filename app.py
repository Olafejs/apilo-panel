import csv
import hashlib
import io
import json
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from flask import (
    Flask,
    abort,
    flash,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from app_auth import (
    get_csrf_token,
    is_safe_redirect_target,
    login_required,
    public_error_message,
    render_setup_password as render_auth_setup_password,
    validate_csrf,
)
from apilo import ApiloClient
from app_admin import (
    build_recent_audit_entries,
    build_secret_storage_payload,
    get_api_settings_snapshot,
    get_email_settings_snapshot,
    summarize_api_settings_snapshot,
    summarize_email_settings_snapshot,
    summarize_inventory_values_snapshot,
    summarize_suggestions_settings_snapshot,
    write_audit_event,
)
from app_auth import (
    get_client_ip as resolve_client_ip,
    is_local_setup_request as is_local_setup_request_for_ip,
    is_login_rate_limited as check_login_rate_limited,
    login_window_start_iso as build_login_window_start_iso,
    password_missing as auth_password_missing,
    setup_token_required as auth_setup_token_required,
    tokens_missing as auth_tokens_missing,
)
from app_config import (
    APP_HOST,
    APP_PASSWORD,
    APP_PORT,
    APP_SETUP_TOKEN,
    APP_VERSION,
    DB_PATH,
    DEBUG_MODE,
    FLASK_SECRET_KEY,
    FLASK_SECRET_KEY_SOURCE,
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    LOG_DIR,
    REFRESH_INTERVAL_SECONDS,
    SALES_CACHE_REFRESH_INTERVAL_SECONDS,
    SALES_YEAR_REFRESH_INTERVAL_SECONDS,
    SESSION_COOKIE_SECURE,
    SESSION_LIFETIME_MINUTES,
    THUMB_DIR,
    THUMB_DOWNLOAD_TIMEOUT_SECONDS,
    THUMB_MAX_DOWNLOAD_BYTES,
    THUMB_TTL_SECONDS,
    TRUST_X_FORWARDED_FOR,
)
from app_reporting import (
    build_sales_report_csv,
    build_sales_report_rows,
    get_sales_totals as build_sales_totals,
    normalize_sales_report_days,
)
from app_sync import (
    build_sync_status_payload as build_runtime_sync_status_payload,
    compute_next_run_at,
    ensure_sync_schedule as ensure_runtime_sync_schedule,
    get_sync_status_snapshot,
    is_schedule_due,
    mark_sync_failed as mark_runtime_sync_failed,
    mark_sync_finished,
    mark_sync_started,
    schedule_inventory_sync as schedule_runtime_inventory_sync,
    schedule_sales_refresh as schedule_runtime_sales_refresh,
    should_refresh_year_sales_cache as should_refresh_runtime_year_sales_cache,
    start_background_refresh as start_runtime_background_refresh,
    update_sync_status as update_runtime_sync_status,
)
from app_utils import (
    format_date_pl,
    format_pln,
    format_pull_time,
    parse_bool_value,
    parse_datetime_value,
    parse_float_value,
    parse_int_value,
    utc_now_iso,
)
from db import (
    clear_login_attempts,
    get_dashboard_metrics,
    get_recent_audit_log,
    get_secret_storage_status,
    get_products,
    get_products_count,
    get_product_by_id,
    get_product_by_apilo_id,
    get_sales_cache_details_map,
    get_sales_year_map,
    get_setting,
    migrate_secret_storage,
    set_setting,
    save_sales_cache,
    save_sales_year_cache,
    record_login_attempt,
    get_base_price_map,
    get_inventory_value_totals,
    get_product_id_maps,
    update_allegro_prices,
    update_allegro_auction_ids,
    update_product_quantity,
    update_product_image,
    upsert_product_from_apilo,
)


app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=SESSION_LIFETIME_MINUTES),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
    SESSION_COOKIE_NAME="apilo_session",
)
SYNC_LOCK = threading.Lock()
PRODUCT_PRESET_LABELS = {
    "all": "Wszystkie",
    "shortage": "Braki",
    "out_of_stock": "Zero stanu",
    "no_ean": "Bez EAN",
    "no_image": "Bez zdjecia",
    "no_sales": "Bez sprzedazy",
    "high_value": "Najwyzsza wartosc",
}
PRODUCT_PAGE_LIMITS = (25, 50, 100, 200)
PRODUCT_EXPORT_COLUMNS = (
    "Apilo ID",
    "SKU",
    "Kod oryginalny",
    "Nazwa",
    "EAN",
    "Stan",
    "Sug. stan",
    "Brak",
    "Sprzedaz 30d",
    "Sprzedaz 365d",
    "Zamowienia 365d",
    "Cena sklepowa brutto",
    "Cena Allegro brutto",
    "Wartosc stanu",
    "Allegro ID",
    "URL zdjecia",
    "Aktualizacja",
)
LOW_STOCK_ALERT_ROW_LIMIT = 200

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
app.logger.setLevel(logging.INFO)
app.logger.propagate = True
if FLASK_SECRET_KEY_SOURCE == "generated":
    logging.getLogger(__name__).warning(
        "FLASK_SECRET_KEY nie ustawiony. Wygenerowano klucz i zapisano w settings (flask_secret_key)."
    )
SECRET_MIGRATION_RESULT = migrate_secret_storage(DB_PATH)
SECRET_STORAGE_STATUS = get_secret_storage_status(DB_PATH)
if SECRET_MIGRATION_RESULT["settings"] or SECRET_MIGRATION_RESULT["tokens"]:
    logging.getLogger(__name__).info(
        "Migrated encrypted secrets settings=%s tokens=%s",
        SECRET_MIGRATION_RESULT["settings"],
        SECRET_MIGRATION_RESULT["tokens"],
    )


def get_config_value(env_key, setting_key, default=None):
    env_value = os.getenv(env_key)
    if env_value:
        return env_value
    setting_value = get_setting(DB_PATH, setting_key)
    return setting_value if setting_value is not None else default


def normalize_base_url(value):
    if not value:
        return value
    base = value.rstrip("/")
    if base.endswith("/rest"):
        base = base[:-5]
    if base.endswith("/api"):
        base = base[:-4]
    return base


def get_order_url_template():
    base = normalize_base_url(
        get_config_value("APILO_BASE_URL", "apilo_base_url", "https://api.apilo.com")
    )
    return f"{base}/order/order/detail/{{id}}/"


def build_order_url(order_id):
    template = get_order_url_template()
    base = normalize_base_url(
        get_config_value("APILO_BASE_URL", "apilo_base_url", "https://api.apilo.com")
    )
    return template.replace("{id}", str(order_id or "")).replace("{base}", base)


def get_client():
    return ApiloClient(
        base_url=normalize_base_url(
            get_config_value("APILO_BASE_URL", "apilo_base_url", "https://api.apilo.com")
        ),
        client_id=get_config_value("APILO_CLIENT_ID", "apilo_client_id"),
        client_secret=get_config_value("APILO_CLIENT_SECRET", "apilo_client_secret"),
        developer_id=None,
        db_path=DB_PATH,
        grant_type=os.getenv("APILO_GRANT_TYPE"),
        auth_token=os.getenv("APILO_AUTH_TOKEN"),
    )


def get_sync_job_label(job):
    return SYNC_JOB_LABELS.get(job, "synchronizacja")


def normalize_product_preset(value):
    return value if value in PRODUCT_PRESET_LABELS else "all"


def default_sort_for_preset(preset):
    if preset == "high_value":
        return "stock_value", "desc"
    if preset == "no_sales":
        return "sales_year", "asc"
    if preset in {"out_of_stock", "no_ean", "no_image"}:
        return "name", "asc"
    return "shortage", "desc"


def normalize_sort_order(value, default):
    return value if value in {"asc", "desc"} else default


def build_product_list_state(args):
    search = args.get("search")
    preset = normalize_product_preset(args.get("preset") or "all")
    default_sort, default_order = default_sort_for_preset(preset)
    sort = args.get("sort") or default_sort
    order = normalize_sort_order(args.get("order") or default_order, default_order)
    page = parse_int_value(args.get("page"), 1, min_value=1)
    limit = parse_int_value(args.get("limit"), 50, min_value=1)
    if limit not in PRODUCT_PAGE_LIMITS:
        limit = 50
    lead_time_days = get_suggest_lead_time_days()
    safety_pct = get_suggest_safety_pct()
    suggest_days = get_suggest_days()
    return {
        "export": args.get("export") == "1",
        "search": search,
        "preset": preset,
        "sort": sort,
        "order": order,
        "page": page,
        "limit": limit,
        "offset": (page - 1) * limit,
        "lead_time_days": lead_time_days,
        "safety_pct": safety_pct,
        "suggest_days": suggest_days,
    }


def fetch_product_rows(list_state, *, limit=None, offset=None):
    effective_limit = list_state["limit"] if limit is None else limit
    effective_offset = list_state["offset"] if offset is None else offset
    return get_products(
        DB_PATH,
        search=list_state["search"],
        preset=list_state["preset"],
        sort=list_state["sort"],
        order=list_state["order"],
        limit=effective_limit,
        offset=effective_offset,
        lead_time_days=list_state["lead_time_days"],
        safety_pct=list_state["safety_pct"],
        suggest_days=list_state["suggest_days"],
    )


def serialize_product_export_row(product):
    return [
        product["apilo_id"] or "",
        product["sku"] or "",
        product["original_code"] or "",
        product["name"] or "",
        product["ean"] or "",
        product["quantity"] if product["quantity"] is not None else "",
        product["suggested_qty"] if product["suggested_qty"] is not None else "",
        product["shortage_qty"] if product["shortage_qty"] is not None else "",
        product["quantity_30d"] if product["quantity_30d"] is not None else "",
        product["quantity_year"] if product["quantity_year"] is not None else "",
        product["orders_year"] if product["orders_year"] is not None else "",
        product["price_with_tax"] if product["price_with_tax"] is not None else "",
        product["allegro_price_with_tax"] if product["allegro_price_with_tax"] is not None else "",
        product["stock_value"] if product["stock_value"] is not None else "",
        product["allegro_auction_id"] or "",
        product["image_url"] or "",
        format_pull_time(product["updated_at"] or ""),
    ]


def build_products_csv_response(list_state):
    export_rows = fetch_product_rows(list_state, limit=None, offset=0)
    record_audit_event(
        "products_export_csv",
        "settings",
        entity_label="Eksport produktów CSV",
        new_value=format_position_count(len(export_rows)),
        details={
            "search": list_state["search"] or "",
            "preset": list_state["preset"],
            "sort": list_state["sort"],
            "order": list_state["order"],
        },
    )
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(PRODUCT_EXPORT_COLUMNS)
    for product in export_rows:
        writer.writerow(serialize_product_export_row(product))
    filename = (
        f"produkty_{list_state['preset']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    response = app.response_class(
        output.getvalue(),
        mimetype="text/csv",
    )
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


def ensure_sync_schedule():
    ensure_runtime_sync_schedule(
        last_pull_at=get_setting(DB_PATH, "last_pull_at"),
        sales_cache_at=get_setting(DB_PATH, "sales_cache_at"),
        refresh_interval_seconds=REFRESH_INTERVAL_SECONDS,
        sales_cache_refresh_interval_seconds=SALES_CACHE_REFRESH_INTERVAL_SECONDS,
    )


def update_sync_status(**changes):
    update_runtime_sync_status(**changes)


def schedule_inventory_sync(reference_time=None, retry=False):
    schedule_runtime_inventory_sync(
        REFRESH_INTERVAL_SECONDS,
        reference_time=reference_time,
        retry=retry,
    )


def schedule_sales_refresh(reference_time=None, retry=False):
    schedule_runtime_sales_refresh(
        SALES_CACHE_REFRESH_INTERVAL_SECONDS,
        reference_time=reference_time,
        retry=retry,
    )


def mark_sync_failed(job, exc):
    del job
    mark_runtime_sync_failed(
        public_error_message(exc, default="Synchronizacja nie powiodła się.")
    )


def should_refresh_year_sales_cache(force=False):
    return should_refresh_runtime_year_sales_cache(
        get_setting(DB_PATH, "sales_year_cache_at"),
        get_suggest_days(),
        SALES_YEAR_REFRESH_INTERVAL_SECONDS,
        force=force,
    )


def build_sync_status_payload():
    ensure_sync_schedule()
    return build_runtime_sync_status_payload(
        last_pull_at=get_setting(DB_PATH, "last_pull_at"),
        sales_cache_at=get_setting(DB_PATH, "sales_cache_at"),
        sales_year_cache_at=get_setting(DB_PATH, "sales_year_cache_at"),
    )


def get_suggest_lead_time_days():
    return parse_int_value(get_setting(DB_PATH, "suggest_lead_time_days"), 1, min_value=1)


def get_suggest_safety_pct():
    return parse_float_value(get_setting(DB_PATH, "suggest_safety_pct"), 20.0, min_value=0.0)


def get_suggest_days():
    parsed = parse_int_value(get_setting(DB_PATH, "suggest_days"), 30, min_value=1)
    return parsed if parsed in (30, 60, 120, 180, 365) else 30


def get_allegro_price_list_id():
    return parse_int_value(get_setting(DB_PATH, "allegro_price_list_id"), 20, min_value=1)


def get_low_stock_rows(limit=10):
    lead_time_days = get_suggest_lead_time_days()
    safety_pct = get_suggest_safety_pct()
    suggest_days = get_suggest_days()
    rows = get_products(
        DB_PATH,
        preset="shortage",
        sort="shortage",
        order="desc",
        limit=limit,
        offset=0,
        lead_time_days=lead_time_days,
        safety_pct=safety_pct,
        suggest_days=suggest_days,
    )
    result = []
    for row in rows:
        current_qty = row["quantity"] if row["quantity"] is not None else 0
        suggested_qty = row["suggested_qty"] if row["suggested_qty"] is not None else 0
        shortage_qty = row["shortage_qty"] if row["shortage_qty"] is not None else 0
        result.append(
            {
                "name": row["name"] or "-",
                "ean": row["ean"] or "",
                "quantity": current_qty,
                "suggested_qty": suggested_qty,
                "shortage_qty": shortage_qty,
            }
        )
    return result


def get_low_stock_alert_enabled():
    return parse_bool_value(get_setting(DB_PATH, "alerts_low_stock_enabled"), default=False)


def get_low_stock_alert_interval_hours():
    return parse_int_value(
        get_setting(DB_PATH, "alerts_low_stock_interval_hours"),
        24,
        min_value=1,
        max_value=720,
    )


def summarize_low_stock_alert_settings_snapshot(enabled, interval_hours):
    return f"auto={'1' if enabled else '0'} interval={interval_hours}h"


def format_item_count(count, singular, paucal, plural):
    count = int(count or 0)
    mod10 = count % 10
    mod100 = count % 100
    if count == 1:
        word = singular
    elif 2 <= mod10 <= 4 and not 12 <= mod100 <= 14:
        word = paucal
    else:
        word = plural
    return f"{count} {word}"


def format_position_count(count):
    return format_item_count(count, "pozycja", "pozycje", "pozycji")


def get_low_stock_alert_next_check_iso():
    if not get_low_stock_alert_enabled():
        return ""
    return compute_next_run_at(
        get_setting(DB_PATH, "alerts_low_stock_last_check_at"),
        get_low_stock_alert_interval_hours() * 3600,
    )


def is_low_stock_alert_due(now=None):
    if not get_low_stock_alert_enabled():
        return False
    scheduled_at = parse_datetime_value(get_low_stock_alert_next_check_iso())
    if not scheduled_at:
        return True
    now = now or datetime.now(timezone.utc)
    return scheduled_at <= now


def build_low_stock_alert_signature(rows):
    normalized_rows = []
    for row in rows:
        normalized_rows.append(
            {
                "ean": row.get("ean") or "",
                "name": row.get("name") or "",
                "quantity": int(row.get("quantity") or 0),
                "suggested_qty": int(row.get("suggested_qty") or 0),
                "shortage_qty": int(row.get("shortage_qty") or 0),
            }
        )
    normalized_rows.sort(key=lambda item: (item["ean"], item["name"]))
    payload = json.dumps(normalized_rows, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def update_low_stock_alert_state(
    *,
    checked_at=None,
    result_message=None,
    error_message=None,
    signature=None,
    sent_count=None,
    sent_at=None,
):
    checked_at = checked_at or utc_now_iso()
    set_setting(DB_PATH, "alerts_low_stock_last_check_at", checked_at)
    if result_message is not None:
        set_setting(DB_PATH, "alerts_low_stock_last_result", result_message)
    if error_message:
        set_setting(DB_PATH, "alerts_low_stock_last_error", error_message)
        set_setting(DB_PATH, "alerts_low_stock_last_error_at", checked_at)
    else:
        set_setting(DB_PATH, "alerts_low_stock_last_error", "")
        set_setting(DB_PATH, "alerts_low_stock_last_error_at", "")
    if signature is not None:
        set_setting(DB_PATH, "alerts_low_stock_last_hash", signature)
    if sent_at is not None:
        set_setting(DB_PATH, "alerts_low_stock_sent_at", sent_at)
    if sent_count is not None:
        set_setting(DB_PATH, "alerts_low_stock_sent_count", str(sent_count))


def mark_low_stock_alert_error(message, *, mode="auto"):
    result_prefix = "Błąd automatycznego alertu." if mode == "auto" else "Błąd ręcznego alertu."
    update_low_stock_alert_state(
        checked_at=utc_now_iso(),
        result_message=result_prefix,
        error_message=message,
    )


def process_low_stock_alert(mode="manual"):
    checked_at = utc_now_iso()
    alert_rows = get_low_stock_rows(limit=LOW_STOCK_ALERT_ROW_LIMIT)
    if not alert_rows:
        update_low_stock_alert_state(
            checked_at=checked_at,
            result_message="Brak pozycji do alertu.",
            signature="",
        )
        return {"status": "empty", "count": 0}

    signature = build_low_stock_alert_signature(alert_rows)
    previous_signature = get_setting(DB_PATH, "alerts_low_stock_last_hash") or ""
    if mode == "auto" and previous_signature and secrets.compare_digest(previous_signature, signature):
        update_low_stock_alert_state(
            checked_at=checked_at,
            result_message="Brak zmian od ostatniej wysyłki.",
            signature=signature,
        )
        return {"status": "duplicate", "count": len(alert_rows)}

    send_low_stock_alert_email(alert_rows)
    result_message = (
        f"Wysłano alert automatycznie ({format_position_count(len(alert_rows))})."
        if mode == "auto"
        else f"Wysłano alert ręcznie ({format_position_count(len(alert_rows))})."
    )
    update_low_stock_alert_state(
        checked_at=checked_at,
        result_message=result_message,
        signature=signature,
        sent_count=len(alert_rows),
        sent_at=checked_at,
    )
    record_audit_event(
        "low_stock_alert_send",
        "email",
        entity_label="Alert niskich stanów",
        new_value=format_position_count(len(alert_rows)),
        details={
            "mode": mode,
            "count": len(alert_rows),
            "signature": signature[:16],
        },
        actor_ip="system" if mode == "auto" else None,
    )
    return {"status": "sent", "count": len(alert_rows)}


def run_low_stock_alert_with_lock(blocking):
    acquired = SYNC_LOCK.acquire(blocking=blocking)
    if not acquired:
        return None
    try:
        return process_low_stock_alert(mode="auto")
    finally:
        SYNC_LOCK.release()


def build_low_stock_alert_history(limit=10):
    history = []
    scan_limit = max(limit * 8, 40)
    for row in get_recent_audit_log(DB_PATH, limit=scan_limit):
        if row["action"] != "low_stock_alert_send":
            continue
        details = {}
        details_json = row["details_json"]
        if details_json:
            try:
                details = json.loads(details_json)
            except (TypeError, ValueError, json.JSONDecodeError):
                details = {}
        mode = details.get("mode") or "manual"
        history.append(
            {
                "created_at": format_pull_time(row["created_at"]),
                "mode_label": "Auto" if mode == "auto" else "Ręcznie",
                "count_label": (
                    format_position_count(details["count"])
                    if details.get("count") is not None
                    else row["new_value"] or "-"
                ),
                "actor_ip": row["actor_ip"] or ("system" if mode == "auto" else "-"),
            }
        )
        if len(history) >= limit:
            break
    return history


def record_audit_event(
    action,
    entity_type,
    entity_id=None,
    entity_label=None,
    old_value=None,
    new_value=None,
    details=None,
    actor_ip=None,
):
    resolved_ip = actor_ip
    if resolved_ip is None:
        resolved_ip = get_client_ip() if has_request_context() else ""
    write_audit_event(
        DB_PATH,
        app.logger,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label,
        old_value=old_value,
        new_value=new_value,
        details=details,
        actor_ip=resolved_ip,
    )


def get_client_ip():
    return resolve_client_ip(TRUST_X_FORWARDED_FOR)


def is_local_setup_request():
    return is_local_setup_request_for_ip(get_client_ip())


def login_window_start_iso():
    return build_login_window_start_iso(LOGIN_RATE_LIMIT_WINDOW_SECONDS)


def is_login_rate_limited(client_ip):
    return check_login_rate_limited(
        DB_PATH,
        client_ip,
        LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    )


def setup_token_required():
    return auth_setup_token_required(APP_SETUP_TOKEN, is_local_setup_request())


def run_sync_pull_with_lock(blocking):
    acquired = SYNC_LOCK.acquire(blocking=blocking)
    if not acquired:
        return None
    mark_sync_started("inventory")
    try:
        count = perform_sync_pull()
        mark_sync_finished("inventory")
        schedule_inventory_sync()
        return count
    except Exception as exc:
        mark_sync_failed("inventory", exc)
        schedule_inventory_sync(retry=True)
        raise
    finally:
        SYNC_LOCK.release()


def run_suggestions_refresh_with_lock(blocking, force_year=False):
    acquired = SYNC_LOCK.acquire(blocking=blocking)
    if not acquired:
        return False
    mark_sync_started("sales_cache")
    try:
        refresh_suggestions_cache(force_year=force_year)
        mark_sync_finished("sales_cache")
        schedule_sales_refresh()
        return True
    except Exception as exc:
        mark_sync_failed("sales_cache", exc)
        schedule_sales_refresh(retry=True)
        raise
    finally:
        SYNC_LOCK.release()


@app.before_request
def require_csrf():
    if request.method == "POST":
        if not validate_csrf():
            return ("Bad Request", 400)


def tokens_missing():
    return auth_tokens_missing(DB_PATH)


def password_missing():
    return auth_password_missing(DB_PATH, APP_PASSWORD)


def render_setup_password(status_code=200):
    return render_auth_setup_password(
        require_setup_token=setup_token_required(),
        remote_setup_blocked=(not APP_SETUP_TOKEN and not is_local_setup_request()),
        status_code=status_code,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if password_missing():
        return redirect(url_for("setup_password"))
    if request.method == "POST":
        client_ip = get_client_ip()
        if is_login_rate_limited(client_ip):
            app.logger.warning("Blocked login by rate limit ip=%s path=%s", client_ip, request.path)
            flash(
                "Za dużo nieudanych prób logowania. Odczekaj kilka minut i spróbuj ponownie.",
                "error",
            )
            return render_template("login.html"), 429
        password = request.form.get("password")
        if APP_PASSWORD:
            valid = password and password == APP_PASSWORD
        else:
            password_hash = get_setting(DB_PATH, "password_hash")
            valid = password and password_hash and check_password_hash(
                password_hash, password
            )
        if valid:
            if client_ip and client_ip != "unknown":
                clear_login_attempts(DB_PATH, client_ip)
            session.clear()
            session.permanent = True
            session["logged_in"] = True
            session["logged_in_at"] = utc_now_iso()
            dest = request.args.get("next")
            if not is_safe_redirect_target(dest):
                dest = url_for("index")
            record_audit_event(
                "login_success",
                "auth",
                entity_label="Panel",
                new_value="ok",
                details={"next": dest},
            )
            return redirect(dest)
        if client_ip and client_ip != "unknown":
            record_login_attempt(DB_PATH, client_ip)
        app.logger.warning("Failed login attempt ip=%s path=%s", client_ip, request.path)
        flash("Nieprawidłowe hasło.", "error")
    return render_template("login.html")


@app.route("/setup-password", methods=["GET", "POST"])
def setup_password():
    if not password_missing():
        return redirect(url_for("login"))
    if request.method == "POST":
        client_ip = get_client_ip()
        if setup_token_required():
            provided_setup_token = request.form.get("setup_token") or ""
            if not secrets.compare_digest(provided_setup_token, APP_SETUP_TOKEN):
                app.logger.warning("Blocked password setup with invalid token ip=%s", client_ip)
                flash("Nieprawidłowy token konfiguracji.", "error")
                return render_setup_password()
        elif not is_local_setup_request():
            app.logger.warning("Blocked remote password setup ip=%s", client_ip)
            flash(
                "Pierwsze ustawienie hasła jest dozwolone tylko lokalnie lub z tokenem konfiguracji.",
                "error",
            )
            return render_setup_password(status_code=403)
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        if not password or len(password) < 8:
            flash("Hasło musi mieć minimum 8 znaków.", "error")
            return render_setup_password()
        if password != confirm:
            flash("Hasła nie są zgodne.", "error")
            return render_setup_password()
        set_setting(DB_PATH, "password_hash", generate_password_hash(password))
        record_audit_event(
            "password_setup",
            "security",
            entity_label="Hasło panelu",
            old_value="brak",
            new_value="ustawione",
            details={"setup_token_required": setup_token_required()},
        )
        flash("Hasło ustawione. Zaloguj się.", "success")
        return redirect(url_for("login"))
    if not APP_SETUP_TOKEN and not is_local_setup_request():
        app.logger.warning("Blocked remote password setup form ip=%s", get_client_ip())
        flash(
            "Pierwsze ustawienie hasła jest dozwolone tylko lokalnie lub z tokenem konfiguracji.",
            "error",
        )
        return render_setup_password(status_code=403)
    return render_setup_password()


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    if tokens_missing():
        return redirect(url_for("settings"))
    list_state = build_product_list_state(request.args)
    if list_state["export"]:
        return build_products_csv_response(list_state)
    products = fetch_product_rows(list_state)
    total_count = get_products_count(
        DB_PATH,
        search=list_state["search"],
        preset=list_state["preset"],
        lead_time_days=list_state["lead_time_days"],
        safety_pct=list_state["safety_pct"],
        suggest_days=list_state["suggest_days"],
    )
    total_pages = max(1, (total_count + list_state["limit"] - 1) // list_state["limit"])
    if list_state["page"] > total_pages:
        list_state["page"] = total_pages
        list_state["offset"] = (list_state["page"] - 1) * list_state["limit"]
        products = fetch_product_rows(list_state)
    dashboard = get_dashboard_metrics(
        DB_PATH,
        lead_time_days=list_state["lead_time_days"],
        safety_pct=list_state["safety_pct"],
        suggest_days=list_state["suggest_days"],
    )
    preset_counts = {
        "all": dashboard.get("total_products", 0) or 0,
        "shortage": dashboard.get("shortage_count", 0) or 0,
        "out_of_stock": dashboard.get("out_of_stock_count", 0) or 0,
        "no_ean": dashboard.get("missing_ean_count", 0) or 0,
        "no_image": dashboard.get("missing_image_count", 0) or 0,
        "no_sales": dashboard.get("no_sales_count", 0) or 0,
        "high_value": dashboard.get("high_value_count", 0) or 0,
    }
    preset_options = [
        {
            "id": key,
            "label": label,
            "count": preset_counts.get(key, 0),
            "sort": default_sort_for_preset(key)[0],
            "order": default_sort_for_preset(key)[1],
        }
        for key, label in PRODUCT_PRESET_LABELS.items()
    ]
    details_cache = get_sales_cache_details_map(DB_PATH)
    year_summary = get_sales_year_map(DB_PATH)
    suggestions = {}
    suggest_details = {}
    for product in products:
        ean = product["ean"]
        if not ean:
            continue
        suggested = product["suggested_qty"]
        if suggested is not None:
            suggestions[ean] = max(int(suggested), 0)
        details = details_cache.get(ean)
        if details:
            suggest_details[ean] = [
                {
                    "date": item.get("date"),
                    "qty": item.get("qty"),
                    "order_id": item.get("order_id"),
                    "url": build_order_url(item.get("order_id", "")),
                }
                for item in details
                if item.get("order_id")
            ]
    return render_template(
        "index.html",
        products=products,
        search=list_state["search"] or "",
        preset=list_state["preset"],
        preset_label=PRODUCT_PRESET_LABELS.get(
            list_state["preset"],
            PRODUCT_PRESET_LABELS["all"],
        ),
        preset_options=preset_options,
        sort=list_state["sort"],
        order=list_state["order"],
        page=list_state["page"],
        total_pages=total_pages,
        total_count=total_count,
        limit=list_state["limit"],
        dashboard=dashboard,
        suggestions=suggestions,
        suggest_details=suggest_details,
        year_summary=year_summary,
        suggest_lead_time_days=list_state["lead_time_days"],
        suggest_safety_pct=list_state["safety_pct"],
        sync_status=build_sync_status_payload(),
        product_detail_base_url=normalize_base_url(
            get_config_value("APILO_BASE_URL", "apilo_base_url", "https://api.apilo.com")
        ),
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "email":
            current_email_settings = get_email_settings_snapshot(DB_PATH)
            smtp_password = request.form.get("smtp_password")
            clear_smtp_password = request.form.get("smtp_password_clear") == "1"
            new_email_settings = {
                "smtp_host": request.form.get("smtp_host") or "",
                "smtp_port": request.form.get("smtp_port") or "",
                "smtp_user": request.form.get("smtp_user") or "",
                "smtp_use_tls": request.form.get("smtp_use_tls") or "0",
                "smtp_use_ssl": request.form.get("smtp_use_ssl") or "0",
                "smtp_from": request.form.get("smtp_from") or "",
                "smtp_to": request.form.get("smtp_to") or "",
                "has_password": (
                    False
                    if clear_smtp_password
                    else bool(smtp_password) or current_email_settings["has_password"]
                ),
            }
            set_setting(DB_PATH, "smtp_host", request.form.get("smtp_host") or "")
            set_setting(DB_PATH, "smtp_port", request.form.get("smtp_port") or "")
            set_setting(DB_PATH, "smtp_user", request.form.get("smtp_user") or "")
            if clear_smtp_password:
                set_setting(DB_PATH, "smtp_password", "")
            elif smtp_password:
                set_setting(DB_PATH, "smtp_password", smtp_password)
            set_setting(DB_PATH, "smtp_use_tls", request.form.get("smtp_use_tls") or "0")
            set_setting(DB_PATH, "smtp_use_ssl", request.form.get("smtp_use_ssl") or "0")
            set_setting(DB_PATH, "smtp_from", request.form.get("smtp_from") or "")
            set_setting(DB_PATH, "smtp_to", request.form.get("smtp_to") or "")
            record_audit_event(
                "email_settings_update",
                "email",
                entity_label="Ustawienia SMTP",
                old_value=summarize_email_settings_snapshot(current_email_settings),
                new_value=summarize_email_settings_snapshot(new_email_settings),
            )
            flash("Ustawienia email zapisane.", "success")
        elif action == "api":
            current_api_settings = get_api_settings_snapshot(DB_PATH)
            api_client_secret = request.form.get("apilo_client_secret")
            clear_api_client_secret = request.form.get("apilo_client_secret_clear") == "1"
            new_api_settings = {
                "apilo_base_url": request.form.get("apilo_base_url") or "",
                "apilo_client_id": request.form.get("apilo_client_id") or "",
                "has_client_secret": (
                    False
                    if clear_api_client_secret
                    else bool(api_client_secret) or current_api_settings["has_client_secret"]
                ),
            }
            set_setting(DB_PATH, "apilo_base_url", request.form.get("apilo_base_url") or "")
            set_setting(DB_PATH, "apilo_client_id", request.form.get("apilo_client_id") or "")
            if clear_api_client_secret:
                set_setting(DB_PATH, "apilo_client_secret", "")
            elif api_client_secret:
                set_setting(DB_PATH, "apilo_client_secret", api_client_secret)
            auth_code = request.form.get("apilo_auth_code") or ""
            token_fetch_status = "skipped"
            if auth_code:
                try:
                    client = get_client()
                    client._fetch_tokens("authorization_code", auth_code)
                    token_fetch_status = "ok"
                    flash("Dane API zapisane i tokeny pobrane.", "success")
                except Exception as exc:
                    app.logger.exception("API token fetch failed")
                    token_fetch_status = "error"
                    flash(public_error_message(exc), "error")
            else:
                flash("Ustawienia API Apilo zapisane.", "success")
            record_audit_event(
                "api_settings_update",
                "api",
                entity_label="Ustawienia API Apilo",
                old_value=summarize_api_settings_snapshot(
                    current_api_settings["apilo_base_url"],
                    current_api_settings["apilo_client_id"],
                    current_api_settings["has_client_secret"],
                ),
                new_value=summarize_api_settings_snapshot(
                    new_api_settings["apilo_base_url"],
                    new_api_settings["apilo_client_id"],
                    new_api_settings["has_client_secret"],
                ),
                details={
                    "auth_code_used": bool(auth_code),
                    "token_fetch_status": token_fetch_status,
                },
            )
        elif action == "api_test":
            previous_test_status = get_setting(DB_PATH, "api_test_status") or ""
            try:
                client = get_client()
                client.timeout = 10
                client.test_connection()
                set_setting(DB_PATH, "api_test_status", "ok")
                set_setting(DB_PATH, "api_test_message", "Połączenie działa.")
                set_setting(DB_PATH, "api_test_at", utc_now_iso())
                record_audit_event(
                    "api_connection_test",
                    "api",
                    entity_label="Test połączenia API",
                    old_value=previous_test_status or None,
                    new_value="ok",
                    details={"message": "Połączenie działa."},
                )
                flash("Połączenie działa.", "success")
            except requests.exceptions.Timeout:
                set_setting(DB_PATH, "api_test_status", "error")
                set_setting(DB_PATH, "api_test_message", "Timeout połączenia z API.")
                set_setting(DB_PATH, "api_test_at", utc_now_iso())
                record_audit_event(
                    "api_connection_test",
                    "api",
                    entity_label="Test połączenia API",
                    old_value=previous_test_status or None,
                    new_value="error",
                    details={"message": "Timeout połączenia z API."},
                )
                flash("Timeout połączenia z API.", "error")
            except Exception as exc:
                app.logger.exception("API connection test failed")
                message = public_error_message(exc)
                set_setting(DB_PATH, "api_test_status", "error")
                set_setting(DB_PATH, "api_test_message", message)
                set_setting(DB_PATH, "api_test_at", utc_now_iso())
                record_audit_event(
                    "api_connection_test",
                    "api",
                    entity_label="Test połączenia API",
                    old_value=previous_test_status or None,
                    new_value="error",
                    details={"message": message},
                )
                flash(message, "error")
        elif action == "allegro":
            current_price_list_id = get_setting(DB_PATH, "allegro_price_list_id") or ""
            allegro_price_list_id = parse_int_value(
                request.form.get("allegro_price_list_id"), 20, min_value=1
            )
            set_setting(DB_PATH, "allegro_price_list_id", str(allegro_price_list_id))
            record_audit_event(
                "allegro_settings_update",
                "settings",
                entity_label="Cennik Allegro",
                old_value=current_price_list_id or None,
                new_value=str(allegro_price_list_id),
            )
            flash("Ustawienia Allegro zapisane.", "success")
        elif action == "email_test":
            try:
                send_test_email()
                record_audit_event(
                    "email_test_send",
                    "email",
                    entity_label="Email testowy",
                    new_value=get_setting(DB_PATH, "smtp_to")
                    or get_setting(DB_PATH, "smtp_user")
                    or "-",
                )
                flash("Wysłano testowy email.", "success")
            except Exception as exc:
                app.logger.exception("Email test failed")
                flash(public_error_message(exc), "error")
        elif action == "alerts_settings":
            current_enabled = get_low_stock_alert_enabled()
            current_interval = get_low_stock_alert_interval_hours()
            enabled = request.form.get("alerts_low_stock_enabled") == "1"
            interval_hours = parse_int_value(
                request.form.get("alerts_low_stock_interval_hours"),
                24,
                min_value=1,
                max_value=720,
            )
            set_setting(DB_PATH, "alerts_low_stock_enabled", "1" if enabled else "0")
            set_setting(DB_PATH, "alerts_low_stock_interval_hours", str(interval_hours))
            if enabled and not current_enabled:
                set_setting(DB_PATH, "alerts_low_stock_last_check_at", "")
                set_setting(DB_PATH, "alerts_low_stock_last_result", "Auto alert włączony.")
            elif not enabled:
                set_setting(DB_PATH, "alerts_low_stock_last_result", "Auto alert wyłączony.")
                set_setting(DB_PATH, "alerts_low_stock_last_error", "")
                set_setting(DB_PATH, "alerts_low_stock_last_error_at", "")
            record_audit_event(
                "low_stock_alert_settings_update",
                "settings",
                entity_label="Auto alert niskich stanów",
                old_value=summarize_low_stock_alert_settings_snapshot(
                    current_enabled,
                    current_interval,
                ),
                new_value=summarize_low_stock_alert_settings_snapshot(
                    enabled,
                    interval_hours,
                ),
            )
            flash("Ustawienia auto alertu zapisane.", "success")
        elif action == "alerts_email":
            try:
                result = process_low_stock_alert(mode="manual")
                if result["status"] == "empty":
                    flash("Brak pozycji do alertu niskich stanów.", "info")
                else:
                    flash(
                        f"Wysłano alert niskich stanów ({format_position_count(result['count'])}).",
                        "success",
                    )
            except Exception as exc:
                app.logger.exception("Low stock alert email failed")
                message = public_error_message(exc)
                mark_low_stock_alert_error(message, mode="manual")
                flash(message, "error")
        elif action == "password":
            password = request.form.get("password")
            confirm = request.form.get("confirm")
            if not password or len(password) < 8:
                flash("Hasło musi mieć minimum 8 znaków.", "error")
            elif password != confirm:
                flash("Hasła nie są zgodne.", "error")
            else:
                set_setting(DB_PATH, "password_hash", generate_password_hash(password))
                record_audit_event(
                    "password_change",
                    "security",
                    entity_label="Hasło panelu",
                    old_value="ustawione",
                    new_value="zmienione",
                )
                flash("Hasło zostało zmienione.", "success")
        elif action == "suggestions":
            current_lead_time = get_suggest_lead_time_days()
            current_safety_pct = get_suggest_safety_pct()
            current_suggest_days = get_suggest_days()
            lead_time = parse_int_value(request.form.get("lead_time_days"), 1, min_value=1)
            safety_pct = parse_float_value(request.form.get("safety_pct"), 20.0, min_value=0.0)
            suggest_days = parse_int_value(request.form.get("suggest_days"), 30, min_value=1)
            if suggest_days not in (30, 60, 120, 180, 365):
                suggest_days = 30
            set_setting(DB_PATH, "suggest_lead_time_days", str(lead_time))
            set_setting(DB_PATH, "suggest_safety_pct", str(safety_pct))
            set_setting(DB_PATH, "suggest_days", str(suggest_days))
            record_audit_event(
                "suggestions_settings_update",
                "settings",
                entity_label="Sugestie stanów",
                old_value=summarize_suggestions_settings_snapshot(
                    current_lead_time,
                    current_safety_pct,
                    current_suggest_days,
                ),
                new_value=summarize_suggestions_settings_snapshot(
                    lead_time,
                    safety_pct,
                    suggest_days,
                ),
            )
            flash("Ustawienia sugestii zapisane.", "success")
        elif action == "suggestions_refresh":
            try:
                refreshed = run_suggestions_refresh_with_lock(blocking=False, force_year=True)
                if refreshed:
                    record_audit_event(
                        "suggestions_refresh",
                        "settings",
                        entity_label="Sugestie stanów",
                        new_value="odświeżone",
                        details={"force_year": True},
                    )
                    flash("Sugestie stanów odświeżone.", "success")
                else:
                    flash("Synchronizacja jest już w toku. Spróbuj ponownie za chwilę.", "info")
            except Exception as exc:
                app.logger.exception("Suggestions refresh failed")
                flash(public_error_message(exc), "error")
        elif action == "inventory_value":
            previous_store_total = get_setting(DB_PATH, "inventory_value_store") or ""
            previous_allegro_total = get_setting(DB_PATH, "inventory_value_allegro") or ""
            try:
                store_total, allegro_total = get_inventory_value_totals(DB_PATH)
                set_setting(DB_PATH, "inventory_value_store", f"{store_total:.2f}")
                set_setting(DB_PATH, "inventory_value_allegro", f"{allegro_total:.2f}")
                set_setting(DB_PATH, "inventory_value_at", utc_now_iso())
                record_audit_event(
                    "inventory_value_refresh",
                    "settings",
                    entity_label="Wartość magazynu",
                    old_value=summarize_inventory_values_snapshot(
                        previous_store_total,
                        previous_allegro_total,
                    ),
                    new_value=summarize_inventory_values_snapshot(
                        f"{store_total:.2f}",
                        f"{allegro_total:.2f}",
                    ),
                )
                flash("Przeliczono wartość magazynu.", "success")
            except Exception as exc:
                app.logger.exception("Inventory value calculation failed")
                flash(public_error_message(exc), "error")
        return redirect(url_for("settings"))

    email_snapshot = get_email_settings_snapshot(DB_PATH)
    email_settings = {
        "smtp_host": email_snapshot["smtp_host"],
        "smtp_port": email_snapshot["smtp_port"],
        "smtp_user": email_snapshot["smtp_user"],
        "has_smtp_password": email_snapshot["has_password"],
        "smtp_use_tls": email_snapshot["smtp_use_tls"],
        "smtp_use_ssl": email_snapshot["smtp_use_ssl"],
        "smtp_from": email_snapshot["smtp_from"],
        "smtp_to": email_snapshot["smtp_to"],
    }
    api_settings = {
        "apilo_base_url": get_setting(DB_PATH, "apilo_base_url") or "",
        "apilo_client_id": get_setting(DB_PATH, "apilo_client_id") or "",
        "has_client_secret": bool(get_config_value("APILO_CLIENT_SECRET", "apilo_client_secret")),
    }
    allegro_settings = {
        "allegro_price_list_id": str(get_allegro_price_list_id()),
    }
    api_status = {
        "config_ok": bool(
            get_config_value("APILO_BASE_URL", "apilo_base_url", "")
            and get_config_value("APILO_CLIENT_ID", "apilo_client_id", "")
            and get_config_value("APILO_CLIENT_SECRET", "apilo_client_secret", "")
        ),
        "tokens_ok": not tokens_missing(),
        "test_status": get_setting(DB_PATH, "api_test_status") or "",
        "test_message": get_setting(DB_PATH, "api_test_message") or "",
        "test_at": format_pull_time(get_setting(DB_PATH, "api_test_at") or ""),
    }
    api_locked = api_status["config_ok"] and api_status["tokens_ok"]
    api_edit_mode = request.args.get("edit_api") == "1"
    show_api_form = (not api_locked) or api_edit_mode
    inventory_values = {
        "store": get_setting(DB_PATH, "inventory_value_store") or "",
        "allegro": get_setting(DB_PATH, "inventory_value_allegro") or "",
        "updated_at": format_pull_time(get_setting(DB_PATH, "inventory_value_at") or ""),
    }
    low_stock_dashboard = get_dashboard_metrics(
        DB_PATH,
        lead_time_days=get_suggest_lead_time_days(),
        safety_pct=get_suggest_safety_pct(),
        suggest_days=get_suggest_days(),
    )
    last_sent_count = parse_int_value(get_setting(DB_PATH, "alerts_low_stock_sent_count"), 0, min_value=0)
    low_stock_alerts = {
        "rows": get_low_stock_rows(limit=10),
        "count": low_stock_dashboard.get("shortage_count", 0) or 0,
        "units": low_stock_dashboard.get("shortage_units", 0) or 0,
        "enabled": get_low_stock_alert_enabled(),
        "interval_hours": get_low_stock_alert_interval_hours(),
        "last_sent_at": format_pull_time(get_setting(DB_PATH, "alerts_low_stock_sent_at") or ""),
        "last_sent_count": last_sent_count,
        "last_sent_count_label": format_position_count(last_sent_count),
        "last_check_at": format_pull_time(
            get_setting(DB_PATH, "alerts_low_stock_last_check_at") or ""
        ),
        "next_check_at": format_pull_time(get_low_stock_alert_next_check_iso()),
        "last_result": get_setting(DB_PATH, "alerts_low_stock_last_result") or "",
        "last_error": get_setting(DB_PATH, "alerts_low_stock_last_error") or "",
        "last_error_at": format_pull_time(
            get_setting(DB_PATH, "alerts_low_stock_last_error_at") or ""
        ),
        "history": build_low_stock_alert_history(limit=10),
    }
    return render_template(
        "settings.html",
        required=tokens_missing(),
        email=email_settings,
        api=api_settings,
        allegro=allegro_settings,
        api_status=api_status,
        api_locked=api_locked,
        api_edit_mode=api_edit_mode,
        show_api_form=show_api_form,
        secret_storage=build_secret_storage_payload(SECRET_STORAGE_STATUS),
        inventory_values=inventory_values,
        low_stock_alerts=low_stock_alerts,
        audit_entries=build_recent_audit_entries(DB_PATH, limit=40),
        suggest_lead_time_days=get_suggest_lead_time_days(),
        suggest_safety_pct=get_suggest_safety_pct(),
        suggest_days=get_suggest_days(),
    )


@app.post("/products/<int:product_id>/quantity")
@login_required
def update_quantity(product_id):
    quantity_raw = request.form.get("quantity")
    next_url = request.form.get("next") or request.referrer or url_for("index")
    try:
        quantity = int(quantity_raw)
    except (TypeError, ValueError):
        flash("Invalid quantity value.", "error")
        return redirect(next_url)
    if quantity < 0:
        flash("Stan magazynowy nie może być ujemny.", "error")
        return redirect(next_url)

    try:
        client = get_client()
        target = get_product_by_id(DB_PATH, product_id)
        if not target:
            flash("Produkt nie znaleziony.", "error")
            return redirect(next_url)
        payload = {"quantity": quantity}
        if target["apilo_id"]:
            payload["id"] = target["apilo_id"]
        elif target["original_code"]:
            payload["originalCode"] = target["original_code"]
        else:
            flash("Brak identyfikatora Apilo.", "error")
            return redirect(next_url)
        client.update_quantities([payload])
        previous_quantity = target["quantity"]
        update_product_quantity(DB_PATH, product_id, quantity)
        record_audit_event(
            "product_quantity_update",
            "product",
            entity_id=product_id,
            entity_label=target["name"] or target["sku"] or f"Produkt {product_id}",
            old_value=str(previous_quantity) if previous_quantity is not None else "brak",
            new_value=str(quantity),
            details={"sku": target["sku"] or "", "ean": target["ean"] or ""},
        )
        flash("Stan zaktualizowany w Apilo.", "success")
    except Exception as exc:
        app.logger.exception("Quantity update failed")
        flash(public_error_message(exc), "error")
    return redirect(next_url)


@app.post("/sync/pull")
@login_required
def sync_pull():
    try:
        count = run_sync_pull_with_lock(blocking=False)
        if count is None:
            flash("Synchronizacja jest już w toku. Spróbuj ponownie za chwilę.", "info")
        else:
            record_audit_event(
                "manual_sync_pull",
                "sync",
                entity_label="Pobranie produktów",
                new_value=f"{count} produktów",
            )
            flash(f"Pobrano {count} produktów z Apilo.", "success")
    except Exception as exc:
        app.logger.exception("Manual sync pull failed")
        flash(public_error_message(exc), "error")
    return redirect(url_for("index"))


@app.post("/sync/push")
@login_required
def sync_push():
    flash("Zmiany są wysyłane od razu do Apilo.", "info")
    return redirect(url_for("index"))


@app.get("/sync/status")
@login_required
def sync_status():
    return jsonify(build_sync_status_payload())


@app.route("/sales-report")
@login_required
def sales_report():
    if tokens_missing():
        return redirect(url_for("settings"))
    days = normalize_sales_report_days(request.args.get("days"), default=30)
    export = request.args.get("export") == "1"
    realized_only = request.args.get("realized", "1") != "0"
    now = datetime.now(timezone.utc)
    updated_after = (now - timedelta(days=days)).isoformat()
    try:
        totals, meta, _daily_map = get_sales_totals(days, realized_only=realized_only)
    except Exception as exc:
        app.logger.exception("Sales report generation failed")
        flash(public_error_message(exc), "error")
        return redirect(url_for("index"))
    rows = build_sales_report_rows(DB_PATH, totals)
    if export:
        response = app.response_class(
            build_sales_report_csv(rows),
            mimetype="text/csv",
        )
        response.headers["Content-Disposition"] = "attachment; filename=raport_sprzedazy.csv"
        return response
    return render_template(
        "sales_report.html",
        rows=rows,
        days=days,
        realized_only=realized_only,
        orders_total=meta["orders_total"],
        orders_used=meta["orders_used"],
        realized_filter=meta["realized_filter"],
        updated_after=format_pull_time(updated_after),
    )


def get_sales_totals(days, realized_only=True):
    return build_sales_totals(
        DB_PATH,
        get_client(),
        days,
        realized_only=realized_only,
    )


def perform_sync_pull():
    if tokens_missing():
        raise RuntimeError("Brak tokenów Apilo.")
    client = get_client()
    products = client.list_products()
    for product in products:
        upsert_product_from_apilo(DB_PATH, product)
    product_ids = [p.get("id") for p in products if p.get("id")]
    if product_ids:
        batch_size = 50
        for idx in range(0, len(product_ids), batch_size):
            batch = product_ids[idx : idx + batch_size]
            media = client.get_product_media(batch, only_main=True)
            for item in media:
                update_product_image(DB_PATH, item.get("productId"), item.get("link"))
    platforms = client.list_sale_platforms()
    allegro_ids = {
        platform.get("id")
        for platform in platforms
        if (platform.get("name") or "").lower() == "allegro"
        or (platform.get("alias") or "").upper() == "AL"
    }
    try:
        auctions = client.list_auctions()
        auction_map = {}
        by_apilo_id, by_sku, by_ean = get_product_id_maps(DB_PATH)
        for auction in auctions:
            platform_account = auction.get("platformAccount") or {}
            if allegro_ids and platform_account.get("id") not in allegro_ids:
                continue
            auction_id = auction.get("idExternal")
            if not auction_id or not str(auction_id).isdigit():
                continue
            for auction_product in auction.get("auctionProducts", []):
                product_info = auction_product.get("product") or {}
                product_id = product_info.get("id") or auction_product.get("productId")
                mapped_id = None
                if product_id is not None:
                    mapped_id = by_apilo_id.get(str(product_id))
                if mapped_id is None:
                    sku = auction_product.get("sku") or product_info.get("sku")
                    if sku:
                        mapped_id = by_sku.get(sku)
                if mapped_id is None:
                    ean = auction_product.get("ean")
                    if ean:
                        mapped_id = by_ean.get(ean)
                if auction_id and mapped_id:
                    auction_map[mapped_id] = str(auction_id)
        update_allegro_auction_ids(DB_PATH, auction_map)
    except Exception:
        app.logger.exception("Pobieranie aukcji Allegro nie powiodlo sie.")
    base_price_map = get_base_price_map(DB_PATH)
    allegro_price_id = get_allegro_price_list_id()
    prices = client.list_price_calculated(allegro_price_id)
    price_map = {}
    for item in prices:
        product_id = item.get("product")
        if product_id is None:
            continue
        base_value = base_price_map.get(product_id)
        computed = compute_allegro_price(item, base_value, markup_pct=19.0)
        if computed is not None:
            price_map[product_id] = computed
    update_allegro_prices(DB_PATH, price_map)
    set_setting(DB_PATH, "last_pull_at", utc_now_iso())
    return len(products)


def refresh_suggestions_cache(force_year=False):
    suggest_days = get_suggest_days()
    totals, _, details_map = get_sales_totals(suggest_days)
    save_sales_cache(DB_PATH, totals, details_map)
    set_setting(DB_PATH, "sales_cache_at", utc_now_iso())
    if suggest_days == 365:
        year_totals, year_details = totals, details_map
        force_year = True
    elif force_year or should_refresh_year_sales_cache(force=force_year):
        year_totals, _, year_details = get_sales_totals(365)
    else:
        return
    year_order_counts = {ean: len(items) for ean, items in year_details.items()}
    save_sales_year_cache(DB_PATH, year_totals, year_order_counts)
    set_setting(DB_PATH, "sales_year_cache_at", utc_now_iso())


def background_refresh_loop():
    ensure_sync_schedule()
    while True:
        ran_job = False
        now = datetime.now(timezone.utc)
        try:
            if not tokens_missing() and is_schedule_due(
                get_sync_status_snapshot().get("next_inventory_sync_at"), now
            ):
                count = run_sync_pull_with_lock(blocking=False)
                ran_job = True
                if count is None:
                    schedule_inventory_sync(reference_time=now, retry=True)
                    app.logger.info("Background inventory sync skipped, sync already in progress.")
                else:
                    app.logger.info("Background inventory sync completed, pulled %s products.", count)
        except Exception:
            app.logger.exception("Background inventory sync failed")
        now = datetime.now(timezone.utc)
        try:
            if not tokens_missing() and is_schedule_due(
                get_sync_status_snapshot().get("next_sales_refresh_at"), now
            ):
                force_year_refresh = should_refresh_year_sales_cache()
                refreshed = run_suggestions_refresh_with_lock(
                    blocking=False,
                    force_year=force_year_refresh,
                )
                ran_job = True
                if refreshed:
                    app.logger.info("Background sales cache refresh completed.")
                else:
                    schedule_sales_refresh(reference_time=now, retry=True)
                    app.logger.info("Background sales cache refresh skipped, sync already in progress.")
        except Exception:
            app.logger.exception("Background sales cache refresh failed")
        now = datetime.now(timezone.utc)
        try:
            if is_low_stock_alert_due(now):
                alert_result = run_low_stock_alert_with_lock(blocking=False)
                if alert_result is None:
                    pass
                elif alert_result["status"] == "sent":
                    ran_job = True
                    app.logger.info(
                        "Background low-stock alert sent for %s products.",
                        alert_result["count"],
                    )
                elif alert_result["status"] == "duplicate":
                    ran_job = True
                    app.logger.info("Background low-stock alert skipped, no changes detected.")
                else:
                    ran_job = True
                    app.logger.info("Background low-stock alert skipped, no shortages found.")
        except Exception as exc:
            message = public_error_message(exc)
            mark_low_stock_alert_error(message, mode="auto")
            app.logger.exception("Background low-stock alert failed")
        time.sleep(5 if not ran_job else 1)


def compute_allegro_price(item, base_value, markup_pct=0.0):
    custom_price = item.get("customPriceWithTax")
    if custom_price is not None:
        return f"{float(custom_price):.2f}"
    mode = item.get("customMode")
    modify = item.get("customPriceModify")
    if modify is None and mode is None:
        if base_value is None:
            return None
        try:
            base_val = float(base_value)
        except (TypeError, ValueError):
            return None
        if markup_pct:
            base_val *= 1 + markup_pct / 100.0
        return f"{base_val:.2f}"
    if modify is None:
        return None
    try:
        modify_val = float(modify)
    except (TypeError, ValueError):
        return None
    try:
        base_val = float(base_value) if base_value is not None else None
    except (TypeError, ValueError):
        base_val = None
    if mode == 3:
        return f"{modify_val:.2f}"
    if base_val is None:
        return None
    if mode == 5:
        return f"{base_val * (1 + modify_val / 100.0):.2f}"
    if mode == 7:
        return f"{base_val + modify_val:.2f}"
    if mode == 6:
        if modify_val >= 100:
            return None
        return f"{base_val / (1 - modify_val / 100.0):.2f}"
    return f"{base_val:.2f}"


def start_background_refresh(debug_mode):
    return start_runtime_background_refresh(debug_mode, background_refresh_loop)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), geolocation=(), microphone=()",
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; "
        "img-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "font-src 'self' data:; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'",
    )
    if request.endpoint in {"login", "setup_password"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.context_processor
def inject_now():
    now = datetime.now().astimezone()
    return {
        "now_human": now.strftime("%Y-%m-%d %H:%M:%S"),
        "csrf_token": get_csrf_token,
        "app_version": APP_VERSION,
    }


@app.get("/healthz")
def healthz():
    try:
        get_setting(DB_PATH, "last_pull_at")
        return jsonify(
            {
                "status": "ok",
                "version": APP_VERSION,
                "sync_running": get_sync_status_snapshot().get("running", False),
            }
        )
    except Exception:
        app.logger.exception("Healthcheck failed")
        return (
            jsonify(
                {
                    "status": "error",
                    "version": APP_VERSION,
                }
            ),
            503,
        )

app.template_filter("date_pl")(format_date_pl)
app.template_filter("pln")(format_pln)


def send_email_message(subject, body):
    import smtplib
    from email.message import EmailMessage

    host = get_setting(DB_PATH, "smtp_host") or ""
    port_raw = get_setting(DB_PATH, "smtp_port") or ""
    user = get_setting(DB_PATH, "smtp_user") or ""
    password = get_setting(DB_PATH, "smtp_password") or ""
    use_tls = get_setting(DB_PATH, "smtp_use_tls") == "1"
    use_ssl = get_setting(DB_PATH, "smtp_use_ssl") == "1"
    sender = get_setting(DB_PATH, "smtp_from") or user
    recipient = get_setting(DB_PATH, "smtp_to") or user

    if not host or not port_raw or not sender or not recipient:
        raise RuntimeError("Brak wymaganych ustawień SMTP.")
    try:
        port = int(port_raw)
    except ValueError:
        raise RuntimeError("Nieprawidłowy port SMTP.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(host, port, timeout=30) as server:
        server.ehlo()
        if use_tls and not use_ssl:
            server.starttls()
            server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


def send_test_email():
    send_email_message("Apilo - test email", "Test konfiguracji SMTP z panelu Apilo.")


def send_low_stock_alert_email(rows):
    lines = [
        "Alert niskich stanow - Apilo Panel",
        "",
        f"Liczba pozycji: {len(rows)}",
        "",
    ]
    for row in rows:
        lines.append(
            "- {name} | EAN: {ean} | stan: {qty} | sugerowany: {suggested} | brak: {shortage}".format(
                name=row["name"],
                ean=row["ean"] or "-",
                qty=row["quantity"],
                suggested=row["suggested_qty"],
                shortage=row["shortage_qty"],
            )
        )
    send_email_message("Apilo - alert niskich stanow", "\n".join(lines))


@app.get("/thumb/<int:apilo_id>")
@login_required
def thumb(apilo_id):
    product = get_product_by_apilo_id(DB_PATH, apilo_id)
    if not product or not product["image_url"]:
        abort(404)
    url = product["image_url"]
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        abort(404)
    path = parsed.path
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    filename = f"{apilo_id}{ext}"
    local_path = os.path.join(THUMB_DIR, filename)
    should_download = not os.path.exists(local_path) or THUMB_TTL_SECONDS == 0
    if os.path.exists(local_path):
        age = datetime.now().timestamp() - os.path.getmtime(local_path)
        if THUMB_TTL_SECONDS > 0 and age < THUMB_TTL_SECONDS:
            return send_from_directory(THUMB_DIR, filename)
        should_download = True
    if should_download:
        tmp_path = f"{local_path}.tmp"
        try:
            with requests.get(
                url,
                timeout=THUMB_DOWNLOAD_TIMEOUT_SECONDS,
                stream=True,
            ) as response:
                response.raise_for_status()
                content_type = (response.headers.get("Content-Type") or "").lower()
                if content_type and not content_type.startswith("image/"):
                    raise ValueError("Unsupported thumbnail content type.")
                total_size = 0
                with open(tmp_path, "wb") as handle:
                    for chunk in response.iter_content(chunk_size=8192):
                        if not chunk:
                            continue
                        total_size += len(chunk)
                        if total_size > THUMB_MAX_DOWNLOAD_BYTES:
                            raise ValueError("Thumbnail exceeds size limit.")
                        handle.write(chunk)
            os.replace(tmp_path, local_path)
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            if os.path.exists(local_path):
                return send_from_directory(THUMB_DIR, filename)
            return redirect(url)
    return send_from_directory(THUMB_DIR, filename)


if __name__ == "__main__":
    start_background_refresh(DEBUG_MODE)
    app.run(host=APP_HOST, port=APP_PORT, debug=DEBUG_MODE, use_reloader=DEBUG_MODE)

import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from apilo import ApiloClient
from db import (
    get_tokens,
    get_products,
    get_products_count,
    get_product_by_id,
    get_product_by_apilo_id,
    get_ean_name_map,
    get_product_maps,
    get_sales_cache_details_map,
    get_sales_cache_map,
    get_sales_year_map,
    init_db,
    get_setting,
    set_setting,
    save_sales_cache,
    save_sales_year_cache,
    get_base_price_map,
    get_inventory_value_totals,
    get_product_id_maps,
    update_allegro_prices,
    update_allegro_auction_ids,
    update_product_quantity,
    update_product_image,
    upsert_product_from_apilo,
)

BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

DB_PATH = os.getenv("APILO_DB_PATH", "apilo.sqlite3")
if not os.path.isabs(DB_PATH):
    DB_PATH = os.path.join(BASE_DIR, DB_PATH)
init_db(DB_PATH)
THUMB_DIR = os.path.join(os.path.dirname(__file__), "static", "thumbs")
os.makedirs(THUMB_DIR, exist_ok=True)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def parse_int_value(value, default, min_value=None, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


def parse_float_value(value, default, min_value=None, max_value=None):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and parsed < min_value:
        return default
    if max_value is not None and parsed > max_value:
        return default
    return parsed


THUMB_TTL_SECONDS = parse_int_value(os.getenv("THUMB_TTL_SECONDS"), 86400, min_value=0)
REFRESH_INTERVAL_SECONDS = parse_int_value(
    os.getenv("REFRESH_INTERVAL_SECONDS"), 600, min_value=10
)


def resolve_flask_secret_key():
    env_key = os.getenv("FLASK_SECRET_KEY")
    if env_key:
        return env_key, "env"
    stored_key = get_setting(DB_PATH, "flask_secret_key")
    if stored_key:
        return stored_key, "db"
    generated_key = secrets.token_urlsafe(64)
    set_setting(DB_PATH, "flask_secret_key", generated_key)
    return generated_key, "generated"


app = Flask(__name__)
FLASK_SECRET_KEY, FLASK_SECRET_KEY_SOURCE = resolve_flask_secret_key()
app.secret_key = FLASK_SECRET_KEY
APP_PASSWORD = os.getenv("APP_PASSWORD")
SYNC_LOCK = threading.Lock()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
if FLASK_SECRET_KEY_SOURCE == "generated":
    logging.getLogger(__name__).warning(
        "FLASK_SECRET_KEY nie ustawiony. Wygenerowano klucz i zapisano w settings (flask_secret_key)."
    )


def read_version():
    path = os.path.join(BASE_DIR, "VERSION")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except FileNotFoundError:
        return "0.0.0"


APP_VERSION = read_version()


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
    template = get_setting(DB_PATH, "apilo_order_url_template")
    if template:
        return template
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


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def get_suggest_lead_time_days():
    return parse_int_value(get_setting(DB_PATH, "suggest_lead_time_days"), 1, min_value=1)


def get_suggest_safety_pct():
    return parse_float_value(get_setting(DB_PATH, "suggest_safety_pct"), 20.0, min_value=0.0)


def get_suggest_days():
    parsed = parse_int_value(get_setting(DB_PATH, "suggest_days"), 30, min_value=1)
    return parsed if parsed in (30, 60, 120, 180, 365) else 30


def get_allegro_price_list_id():
    return parse_int_value(get_setting(DB_PATH, "allegro_price_list_id"), 20, min_value=1)


def is_safe_redirect_target(target):
    if not target:
        return False
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return False
    return target.startswith("/") and not target.startswith("//")


def public_error_message(exc, default="Wystąpił błąd."):
    if isinstance(exc, requests.exceptions.Timeout):
        return "Timeout połączenia z API Apilo."
    if isinstance(exc, requests.exceptions.RequestException):
        return "Błąd połączenia z API Apilo."

    message = str(exc).strip()
    if not message:
        return default
    if message.startswith("Apilo API error:") or message.startswith("Token request failed:"):
        return "Błąd komunikacji z API Apilo."
    if isinstance(exc, RuntimeError):
        return message.splitlines()[0][:200]
    return default


def run_sync_pull_with_lock(blocking):
    acquired = SYNC_LOCK.acquire(blocking=blocking)
    if not acquired:
        return None
    try:
        count = perform_sync_pull()
        refresh_suggestions_cache()
        return count
    finally:
        SYNC_LOCK.release()


def run_suggestions_refresh_with_lock(blocking):
    acquired = SYNC_LOCK.acquire(blocking=blocking)
    if not acquired:
        return False
    try:
        refresh_suggestions_cache()
        return True
    finally:
        SYNC_LOCK.release()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def validate_csrf():
    token = session.get("csrf_token")
    provided = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    return token and provided and token == provided


@app.before_request
def require_csrf():
    if request.method == "POST":
        if not validate_csrf():
            return ("Bad Request", 400)


def tokens_missing():
    tokens = get_tokens(DB_PATH) or {}
    return not (tokens.get("access_token") or tokens.get("refresh_token"))


def password_missing():
    if APP_PASSWORD:
        return False
    return get_setting(DB_PATH, "password_hash") is None


@app.route("/login", methods=["GET", "POST"])
def login():
    if password_missing():
        return redirect(url_for("setup_password"))
    if request.method == "POST":
        password = request.form.get("password")
        if APP_PASSWORD:
            valid = password and password == APP_PASSWORD
        else:
            password_hash = get_setting(DB_PATH, "password_hash")
            valid = password and password_hash and check_password_hash(
                password_hash, password
            )
        if valid:
            session.clear()
            session["logged_in"] = True
            dest = request.args.get("next")
            if not is_safe_redirect_target(dest):
                dest = url_for("index")
            return redirect(dest)
        flash("Nieprawidłowe hasło.", "error")
    return render_template("login.html")


@app.route("/setup-password", methods=["GET", "POST"])
def setup_password():
    if not password_missing():
        return redirect(url_for("login"))
    if request.method == "POST":
        password = request.form.get("password")
        confirm = request.form.get("confirm")
        if not password or len(password) < 8:
            flash("Hasło musi mieć minimum 8 znaków.", "error")
            return render_template("setup_password.html")
        if password != confirm:
            flash("Hasła nie są zgodne.", "error")
            return render_template("setup_password.html")
        set_setting(DB_PATH, "password_hash", generate_password_hash(password))
        flash("Hasło ustawione. Zaloguj się.", "success")
        return redirect(url_for("login"))
    return render_template("setup_password.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    if tokens_missing():
        return redirect(url_for("settings"))
    search = request.args.get("search")
    sort = request.args.get("sort") or "shortage"
    order = request.args.get("order") or ("desc" if sort == "shortage" else "asc")
    try:
        page = int(request.args.get("page") or 1)
    except ValueError:
        page = 1
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        limit = 50
    if limit not in (25, 50, 100, 200):
        limit = 50
    if page < 1:
        page = 1
    offset = (page - 1) * limit
    lead_time_days = get_suggest_lead_time_days()
    safety_pct = get_suggest_safety_pct()
    products = get_products(
        DB_PATH,
        search=search,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
        lead_time_days=lead_time_days,
        safety_pct=safety_pct,
    )
    total_count = get_products_count(DB_PATH, search=search)
    total_pages = max(1, (total_count + limit - 1) // limit)
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * limit
        products = get_products(
            DB_PATH,
            search=search,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
            lead_time_days=lead_time_days,
            safety_pct=safety_pct,
        )
    last_pull_at = get_setting(DB_PATH, "last_pull_at") or ""
    last_pull_human = format_pull_time(last_pull_at)
    sales_cache = get_sales_cache_map(DB_PATH)
    details_cache = get_sales_cache_details_map(DB_PATH)
    year_summary = get_sales_year_map(DB_PATH)
    suggestions = {}
    suggest_details = {}
    for ean, qty_30d in sales_cache.items():
        avg_daily = qty_30d / 30.0
        suggested = int((avg_daily * lead_time_days) * (1 + safety_pct / 100.0) + 0.9999)
        suggestions[ean] = max(suggested, 0)
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
        search=search or "",
        sort=sort,
        order=order,
        last_pull_at=last_pull_human,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        limit=limit,
        suggestions=suggestions,
        suggest_details=suggest_details,
        year_summary=year_summary,
        suggest_updated_at=format_pull_time(get_setting(DB_PATH, "sales_cache_at") or ""),
        suggest_lead_time_days=lead_time_days,
        suggest_safety_pct=safety_pct,
        refresh_interval_seconds=REFRESH_INTERVAL_SECONDS,
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
            set_setting(DB_PATH, "smtp_host", request.form.get("smtp_host") or "")
            set_setting(DB_PATH, "smtp_port", request.form.get("smtp_port") or "")
            set_setting(DB_PATH, "smtp_user", request.form.get("smtp_user") or "")
            set_setting(DB_PATH, "smtp_password", request.form.get("smtp_password") or "")
            set_setting(DB_PATH, "smtp_use_tls", request.form.get("smtp_use_tls") or "0")
            set_setting(DB_PATH, "smtp_use_ssl", request.form.get("smtp_use_ssl") or "0")
            set_setting(DB_PATH, "smtp_from", request.form.get("smtp_from") or "")
            set_setting(DB_PATH, "smtp_to", request.form.get("smtp_to") or "")
            flash("Ustawienia email zapisane.", "success")
        elif action == "api":
            set_setting(DB_PATH, "apilo_base_url", request.form.get("apilo_base_url") or "")
            set_setting(DB_PATH, "apilo_client_id", request.form.get("apilo_client_id") or "")
            set_setting(DB_PATH, "apilo_client_secret", request.form.get("apilo_client_secret") or "")
            set_setting(DB_PATH, "apilo_order_url_template", request.form.get("apilo_order_url_template") or "")
            auth_code = request.form.get("apilo_auth_code") or ""
            if auth_code:
                try:
                    client = get_client()
                    client._fetch_tokens("authorization_code", auth_code)
                    flash("Dane API zapisane i tokeny pobrane.", "success")
                except Exception as exc:
                    app.logger.exception("API token fetch failed")
                    flash(public_error_message(exc), "error")
            else:
                flash("Ustawienia API Apilo zapisane.", "success")
        elif action == "api_test":
            try:
                client = get_client()
                client.timeout = 10
                client.test_connection()
                set_setting(DB_PATH, "api_test_status", "ok")
                set_setting(DB_PATH, "api_test_message", "Połączenie działa.")
                set_setting(DB_PATH, "api_test_at", utc_now_iso())
                flash("Połączenie działa.", "success")
            except requests.exceptions.Timeout:
                set_setting(DB_PATH, "api_test_status", "error")
                set_setting(DB_PATH, "api_test_message", "Timeout połączenia z API.")
                set_setting(DB_PATH, "api_test_at", utc_now_iso())
                flash("Timeout połączenia z API.", "error")
            except Exception as exc:
                app.logger.exception("API connection test failed")
                message = public_error_message(exc)
                set_setting(DB_PATH, "api_test_status", "error")
                set_setting(DB_PATH, "api_test_message", message)
                set_setting(DB_PATH, "api_test_at", utc_now_iso())
                flash(message, "error")
        elif action == "allegro":
            allegro_price_list_id = parse_int_value(
                request.form.get("allegro_price_list_id"), 20, min_value=1
            )
            set_setting(DB_PATH, "allegro_price_list_id", str(allegro_price_list_id))
            flash("Ustawienia Allegro zapisane.", "success")
        elif action == "email_test":
            try:
                send_test_email()
                flash("Wysłano testowy email.", "success")
            except Exception as exc:
                app.logger.exception("Email test failed")
                flash(public_error_message(exc), "error")
        elif action == "password":
            password = request.form.get("password")
            confirm = request.form.get("confirm")
            if not password or len(password) < 8:
                flash("Hasło musi mieć minimum 8 znaków.", "error")
            elif password != confirm:
                flash("Hasła nie są zgodne.", "error")
            else:
                set_setting(DB_PATH, "password_hash", generate_password_hash(password))
                flash("Hasło zostało zmienione.", "success")
        elif action == "suggestions":
            lead_time = parse_int_value(request.form.get("lead_time_days"), 1, min_value=1)
            safety_pct = parse_float_value(request.form.get("safety_pct"), 20.0, min_value=0.0)
            suggest_days = parse_int_value(request.form.get("suggest_days"), 30, min_value=1)
            if suggest_days not in (30, 60, 120, 180, 365):
                suggest_days = 30
            set_setting(DB_PATH, "suggest_lead_time_days", str(lead_time))
            set_setting(DB_PATH, "suggest_safety_pct", str(safety_pct))
            set_setting(DB_PATH, "suggest_days", str(suggest_days))
            flash("Ustawienia sugestii zapisane.", "success")
        elif action == "suggestions_refresh":
            try:
                refreshed = run_suggestions_refresh_with_lock(blocking=False)
                if refreshed:
                    flash("Sugestie stanów odświeżone.", "success")
                else:
                    flash("Synchronizacja jest już w toku. Spróbuj ponownie za chwilę.", "info")
            except Exception as exc:
                app.logger.exception("Suggestions refresh failed")
                flash(public_error_message(exc), "error")
        elif action == "inventory_value":
            try:
                store_total, allegro_total = get_inventory_value_totals(DB_PATH)
                set_setting(DB_PATH, "inventory_value_store", f"{store_total:.2f}")
                set_setting(DB_PATH, "inventory_value_allegro", f"{allegro_total:.2f}")
                set_setting(DB_PATH, "inventory_value_at", utc_now_iso())
                flash("Przeliczono wartość magazynu.", "success")
            except Exception as exc:
                app.logger.exception("Inventory value calculation failed")
                flash(public_error_message(exc), "error")
        return redirect(url_for("settings"))

    email_settings = {
        "smtp_host": get_setting(DB_PATH, "smtp_host") or "",
        "smtp_port": get_setting(DB_PATH, "smtp_port") or "",
        "smtp_user": get_setting(DB_PATH, "smtp_user") or "",
        "smtp_password": get_setting(DB_PATH, "smtp_password") or "",
        "smtp_use_tls": get_setting(DB_PATH, "smtp_use_tls") or "0",
        "smtp_use_ssl": get_setting(DB_PATH, "smtp_use_ssl") or "0",
        "smtp_from": get_setting(DB_PATH, "smtp_from") or "",
        "smtp_to": get_setting(DB_PATH, "smtp_to") or "",
    }
    api_settings = {
        "apilo_base_url": get_setting(DB_PATH, "apilo_base_url") or "",
        "apilo_client_id": get_setting(DB_PATH, "apilo_client_id") or "",
        "apilo_client_secret": get_setting(DB_PATH, "apilo_client_secret") or "",
        "apilo_order_url_template": get_setting(DB_PATH, "apilo_order_url_template") or "",
    }
    allegro_settings = {
        "allegro_price_list_id": str(get_allegro_price_list_id()),
    }
    api_status = {
        "config_ok": bool(
            api_settings["apilo_base_url"]
            and api_settings["apilo_client_id"]
            and api_settings["apilo_client_secret"]
        ),
        "tokens_ok": not tokens_missing(),
        "test_status": get_setting(DB_PATH, "api_test_status") or "",
        "test_message": get_setting(DB_PATH, "api_test_message") or "",
        "test_at": format_pull_time(get_setting(DB_PATH, "api_test_at") or ""),
    }
    inventory_values = {
        "store": get_setting(DB_PATH, "inventory_value_store") or "",
        "allegro": get_setting(DB_PATH, "inventory_value_allegro") or "",
        "updated_at": format_pull_time(get_setting(DB_PATH, "inventory_value_at") or ""),
    }
    return render_template(
        "settings.html",
        required=tokens_missing(),
        email=email_settings,
        api=api_settings,
        allegro=allegro_settings,
        api_status=api_status,
        inventory_values=inventory_values,
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
        update_product_quantity(DB_PATH, product_id, quantity)
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
            flash(f"Pobrano {count} produktów z Apilo i odświeżono sprzedaż.", "success")
    except Exception as exc:
        app.logger.exception("Manual sync pull failed")
        flash(public_error_message(exc), "error")
    return redirect(url_for("index"))


@app.post("/sync/push")
@login_required
def sync_push():
    flash("Zmiany są wysyłane od razu do Apilo.", "info")
    return redirect(url_for("index"))


@app.route("/sales-report")
@login_required
def sales_report():
    if tokens_missing():
        return redirect(url_for("settings"))
    try:
        days = int(request.args.get("days") or 30)
    except ValueError:
        days = 30
    if days < 1 or days > 365:
        days = 30
    export = request.args.get("export") == "1"
    now = datetime.now(timezone.utc)
    updated_after = (now - timedelta(days=days)).isoformat()
    try:
        totals, meta, _daily_map = get_sales_totals(days)
    except Exception as exc:
        app.logger.exception("Sales report generation failed")
        flash(public_error_message(exc), "error")
        return redirect(url_for("index"))
    ean_name_map = get_ean_name_map(DB_PATH)
    rows = [
        {
            "ean": ean,
            "name": ean_name_map.get(ean, ""),
            "quantity": qty,
        }
        for ean, qty in totals.items()
    ]
    rows.sort(key=lambda r: r["quantity"], reverse=True)
    if export:
        output = ["EAN;Nazwa;Sprzedane"]
        for row in rows:
            name = (row["name"] or "").replace(";", ",")
            output.append(f"{row['ean']};{name};{row['quantity']}")
        response = app.response_class(
            "\n".join(output),
            mimetype="text/csv",
        )
        response.headers["Content-Disposition"] = "attachment; filename=raport_sprzedazy.csv"
        return response
    return render_template(
        "sales_report.html",
        rows=rows,
        days=days,
        orders_total=meta["orders_total"],
        orders_used=meta["orders_used"],
        realized_filter=meta["realized_filter"],
        updated_after=format_pull_time(updated_after),
    )


def get_sales_totals(days):
    now = datetime.now(timezone.utc)
    ordered_after = (now - timedelta(days=days)).isoformat()
    client = get_client()
    orders = client.list_orders(ordered_after=ordered_after, payment_status=2)
    by_apilo_id, by_original_code, by_sku = get_product_maps(DB_PATH)
    totals = {}
    details_map = {}
    for order in orders:
        day_key = extract_order_day(order)
        order_id = order.get("id")
        external_order_id = pick_external_order_id(order)
        for item in order.get("orderItems", []):
            ean = item.get("ean")
            if not ean:
                product_id = item.get("productId")
                if product_id is not None:
                    ean = by_apilo_id.get(str(product_id))
            if not ean:
                original_code = item.get("originalCode")
                if original_code:
                    ean = by_original_code.get(original_code)
            if not ean:
                sku = item.get("sku")
                if sku:
                    ean = by_sku.get(sku)
            qty = item.get("quantity") or 0
            if not ean:
                continue
            totals[ean] = totals.get(ean, 0) + qty
            if day_key and order_id:
                details_map.setdefault(ean, {})
                entry = details_map[ean].setdefault(
                    order_id,
                    {
                        "date": day_key,
                        "qty": 0,
                        "order_id": order_id,
                        "allegro_id": external_order_id,
                    },
                )
                entry["qty"] += qty
    meta = {
        "orders_total": len(orders),
        "orders_used": len(orders),
        "realized_filter": False,
    }
    details_list = {}
    for ean, orders_map in details_map.items():
        items = list(orders_map.values())
        items.sort(key=lambda x: x["date"], reverse=True)
        details_list[ean] = items
    return totals, meta, details_list


def extract_order_day(order):
    for key in ("orderedAt", "createdAt", "updatedAt"):
        value = order.get(key)
        if value:
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def pick_external_order_id(order):
    candidates = (
        "externalId",
        "externalOrderId",
        "channelOrderId",
        "orderId",
        "marketplaceOrderId",
        "id",
    )
    for key in candidates:
        value = order.get(key)
        if isinstance(value, dict):
            value = value.get("id") or value.get("value")
        if value:
            return str(value)
    return ""


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


def refresh_suggestions_cache():
    suggest_days = get_suggest_days()
    totals, _, details_map = get_sales_totals(suggest_days)
    save_sales_cache(DB_PATH, totals, details_map)
    if suggest_days == 365:
        year_totals, year_details = totals, details_map
    else:
        year_totals, _, year_details = get_sales_totals(365)
    year_order_counts = {ean: len(items) for ean, items in year_details.items()}
    save_sales_year_cache(DB_PATH, year_totals, year_order_counts)
    set_setting(DB_PATH, "sales_cache_at", utc_now_iso())


def background_refresh_loop():
    while True:
        try:
            count = run_sync_pull_with_lock(blocking=False)
            if count is None:
                app.logger.info("Background refresh skipped, sync already in progress.")
            else:
                app.logger.info("Background refresh completed, pulled %s products.", count)
        except Exception:
            app.logger.exception("Background refresh failed")
        time.sleep(REFRESH_INTERVAL_SECONDS)


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
    if os.getenv("WERKZEUG_RUN_MAIN") == "true" or not debug_mode:
        thread = threading.Thread(target=background_refresh_loop, daemon=True)
        thread.start()


@app.context_processor
def inject_now():
    now = datetime.now().astimezone()
    return {
        "now_human": now.strftime("%Y-%m-%d %H:%M:%S"),
        "csrf_token": get_csrf_token,
        "app_version": APP_VERSION,
    }


def format_pull_time(value):
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return value
    return dt.strftime("%d.%m.%Y %H:%M")


@app.template_filter("date_pl")
def format_date_pl(value):
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.astimezone().strftime("%d.%m.%Y")
    try:
        if "T" not in value and " " not in value:
            dt = datetime.fromisoformat(value + "T00:00:00")
        else:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%d.%m.%Y")
    except ValueError:
        return value


@app.template_filter("pln")
def format_pln(value):
    if value is None or value == "":
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    formatted = f"{number:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} zł"


def send_test_email():
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
    msg["Subject"] = "Apilo - test email"
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content("Test konfiguracji SMTP z panelu Apilo.")

    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(host, port, timeout=30) as server:
        server.ehlo()
        if use_tls and not use_ssl:
            server.starttls()
            server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


@app.get("/thumb/<int:apilo_id>")
@login_required
def thumb(apilo_id):
    product = get_product_by_apilo_id(DB_PATH, apilo_id)
    if not product or not product["image_url"]:
        abort(404)
    url = product["image_url"]
    path = urlparse(url).path
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
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            with open(local_path, "wb") as handle:
                handle.write(response.content)
        except Exception:
            return redirect(url)
    return send_from_directory(THUMB_DIR, filename)


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG") == "1"
    start_background_refresh(debug_mode)
    app.run(debug=debug_mode, use_reloader=debug_mode)

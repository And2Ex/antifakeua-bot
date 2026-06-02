import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from config import FREE_TEXT_LIMIT, require_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

REQUEST_STATUSES = {"pending", "published", "skipped", "rejected", "quickcheck"}
SUCCESS_PAYMENT_STATUSES = {"success", "sandbox"}
CHANNEL_MODES = {"manual", "auto"}
V042_FREE_LIMIT_MIGRATION_KEY = "migration_v042_free_limit_to_configured_value"


def get_connection():
    return psycopg.connect(
        require_database_url(),
        row_factory=dict_row,
        connect_timeout=15,
    )


def init_db() -> None:
    sql_script = SCHEMA_PATH.read_text(encoding="utf-8")

    statements = [
        statement.strip()
        for statement in sql_script.split(";")
        if statement.strip()
    ]

    with get_connection() as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)

            _apply_v042_free_limit_migration(cursor)


def _apply_v042_free_limit_migration(cursor) -> None:
    """Move accounts that still use the former default quota to the new default once."""
    cursor.execute(
        "SELECT value FROM app_settings WHERE key = %s",
        (V042_FREE_LIMIT_MIGRATION_KEY,),
    )

    migration = cursor.fetchone()

    if migration is not None and migration["value"] == str(FREE_TEXT_LIMIT):
        return

    cursor.execute(
        """
        UPDATE users
        SET texts_limit = %s,
            free_limit = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE texts_limit = 30 AND free_limit = 30
        """,
        (FREE_TEXT_LIMIT, FREE_TEXT_LIMIT),
    )
    cursor.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (V042_FREE_LIMIT_MIGRATION_KEY, str(FREE_TEXT_LIMIT)),
    )


def check_database_connection() -> dict:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_database() AS database_name, version() AS version"
            )
            return cursor.fetchone()


def get_app_setting(key: str, default: str | None = None) -> str | None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT value FROM app_settings WHERE key = %s",
        (key,)
    )
    row = cursor.fetchone()
    connection.close()

    if row is None:
        return default

    return row["value"]


def set_app_setting(key: str, value: str) -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, value)
    )

    connection.commit()
    connection.close()


def is_admin_notifications_enabled() -> bool:
    return get_app_setting("admin_notifications_enabled", "1") == "1"


def set_admin_notifications_enabled(enabled: bool) -> None:
    set_app_setting("admin_notifications_enabled", "1" if enabled else "0")


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def generate_public_id() -> str:
    return f"check_{secrets.token_urlsafe(6)}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def remember_content(
    content_hash: str,
    original_context: str | None = None,
    original_url: str | None = None
) -> dict:
    now = utc_now_iso()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM content_history
        WHERE content_hash = %s
        """,
        (content_hash,)
    )
    existing = cursor.fetchone()

    if existing is None:
        cursor.execute(
            """
            INSERT INTO content_history (
                content_hash,
                first_seen_at,
                last_seen_at,
                original_context,
                original_url,
                times_seen
            )
            VALUES (%s, %s, %s, %s, %s, 1)
            """,
            (
                content_hash,
                now,
                now,
                original_context,
                original_url,
            )
        )

        connection.commit()
        connection.close()

        return {
            "is_repeat": False,
            "times_seen": 1,
            "first_seen_at": now,
            "last_seen_at": now,
        }

    times_seen = int(existing["times_seen"] or 0) + 1

    cursor.execute(
        """
        UPDATE content_history
        SET last_seen_at = %s,
            times_seen = %s
        WHERE content_hash = %s
        """,
        (now, times_seen, content_hash)
    )

    connection.commit()
    connection.close()

    return {
        "is_repeat": True,
        "times_seen": times_seen,
        "first_seen_at": existing["first_seen_at"],
        "last_seen_at": now,
    }


def add_user(user_id: int, username: str | None, first_name: str | None):
    month = current_month()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO users (
            user_id,
            username,
            first_name,
            texts_limit,
            free_limit,
            last_free_reset_month
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, username, first_name, FREE_TEXT_LIMIT, FREE_TEXT_LIMIT, month)
    )

    connection.commit()
    connection.close()


def get_user(user_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE user_id = %s",
        (user_id,)
    )

    user = cursor.fetchone()
    connection.close()

    return user


def reset_monthly_free_limit_if_needed(user_id: int):
    month = current_month()

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT last_free_reset_month FROM users WHERE user_id = %s",
        (user_id,)
    )
    user = cursor.fetchone()

    if user is not None and user["last_free_reset_month"] != month:
        cursor.execute(
            """
            UPDATE users
            SET free_used = 0,
                last_free_reset_month = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            """,
            (month, user_id)
        )

    connection.commit()
    connection.close()


def use_text_quota(user_id: int) -> tuple[bool, str]:
    reset_monthly_free_limit_if_needed(user_id)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    if user is None:
        connection.close()
        return False, "<b>Користувача не знайдено</b>\n\nНатисни <code>/start</code>, щоб створити профіль у боті."

    free_limit = user["free_limit"]
    free_used = user["free_used"]
    paid_balance = user["paid_balance"]

    if free_used < free_limit:
        cursor.execute(
            """
            UPDATE users
            SET free_used = free_used + 1,
                texts_used = texts_used + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            """,
            (user_id,)
        )

        connection.commit()
        connection.close()

        remaining_free = free_limit - (free_used + 1)

        if paid_balance == 0 and remaining_free <= 3:
            return True, (
                f"<b>Залишилось безкоштовних перевірок:</b> {remaining_free}\n"
                "Підтримати проєкт і отримати додатковий ліміт можна через <code>/support</code>."
            )

        return True, ""

    if paid_balance > 0:
        cursor.execute(
            """
            UPDATE users
            SET paid_balance = paid_balance - 1,
                texts_used = texts_used + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            """,
            (user_id,)
        )

        connection.commit()
        connection.close()

        remaining_paid = paid_balance - 1

        if remaining_paid <= 3:
            return True, (
                f"<b>Залишилось додаткових перевірок:</b> {remaining_paid}\n"
                "Підтримати проєкт і отримати новий додатковий ліміт можна через <code>/support</code>."
            )

        return True, ""

    connection.close()

    return (
        False,
        "<b>Ліміт безкоштовних перевірок вичерпано</b>\n\n"
        f"<b>Безкоштовні перевірки:</b> {free_used}/{free_limit}\n"
        "<b>Додатковий ліміт:</b> 0\n\n"
        "Додаткові перевірки можуть бути надані користувачам, які підтримали AntiFakeUA. Відкрий розділ нижче, щоб передати підтвердження підтримки."
    )


def add_paid_balance(user_id: int, checks: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET paid_balance = paid_balance + %s,
            plan = 'paid',
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
        """,
        (checks, user_id)
    )

    connection.commit()
    connection.close()


def update_user_usage(user_id: int, texts_used: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET texts_used = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
        """,
        (texts_used, user_id)
    )

    connection.commit()
    connection.close()


def reset_user_limits(user_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET texts_used = 0,
            free_used = 0,
            paid_balance = 0,
            last_free_reset_month = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
        """,
        (current_month(), user_id)
    )

    connection.commit()
    connection.close()


def reset_all_limits():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET texts_used = 0,
            free_used = 0,
            last_free_reset_month = %s,
            updated_at = CURRENT_TIMESTAMP
        """,
        (current_month(),)
    )

    connection.commit()
    connection.close()


def set_user_text_limit(user_id: int, texts_limit: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE users
        SET texts_limit = %s,
            free_limit = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
        """,
        (texts_limit, texts_limit, user_id)
    )

    connection.commit()
    connection.close()


def add_request(
    user_id: int,
    request_text: str,
    response_text: str | None = None,
    source_type: str | None = None,
    source_title: str | None = None,
    source_link: str | None = None,
    detected_links: str | None = None,
    detected_domains: str | None = None,
    verdict: str | None = None,
    from_cache: bool = False,
    result: dict | None = None,
    is_publishable: bool = True,
    queue_for_publication: bool = True,
    media: list[dict] | None = None,
    media_group_id: str | None = None,
) -> str:
    connection = get_connection()
    cursor = connection.cursor()

    public_id = generate_public_id()
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
    media_json = json.dumps(media, ensure_ascii=False) if media else None
    publication_status = (
        "pending"
        if is_publishable and queue_for_publication
        else "quickcheck"
        if is_publishable
        else "rejected"
    )

    cursor.execute(
        """
        INSERT INTO requests (
            public_id,
            user_id,
            request_text,
            response_text,
            source_type,
            source_title,
            source_link,
            detected_links,
            detected_domains,
            verdict,
            from_cache,
            result_json,
            is_publishable,
            publication_status,
            media_json,
            media_group_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            public_id,
            user_id,
            request_text,
            response_text,
            source_type,
            source_title,
            source_link,
            detected_links,
            detected_domains,
            verdict,
            from_cache,
            result_json,
            is_publishable,
            publication_status,
            media_json,
            media_group_id,
        )
    )

    connection.commit()
    connection.close()

    return public_id


def get_request_by_public_id(public_id: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM requests WHERE public_id = %s",
        (public_id,)
    )

    request = cursor.fetchone()
    connection.close()

    return request


def refresh_request_fact_check(
    public_id: str,
    response_text: str,
    verdict: str,
    result: dict,
    is_publishable: bool,
) -> bool:
    """Replace an outdated stored fact-check before an admin drafts publication."""
    connection = get_connection()
    cursor = connection.cursor()
    result_json = json.dumps(result, ensure_ascii=False)

    cursor.execute(
        """
        UPDATE requests
        SET response_text = %s,
            verdict = %s,
            result_json = %s,
            is_publishable = %s,
            publication_json = NULL,
            publication_status = CASE
                WHEN %s THEN publication_status
                ELSE 'rejected'
            END
        WHERE public_id = %s
        """,
        (
            response_text,
            verdict,
            result_json,
            is_publishable,
            is_publishable,
            public_id,
        ),
    )

    changed = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return changed


def save_publication_draft(public_id: str, publication: dict) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    publication_json = json.dumps(publication, ensure_ascii=False)

    cursor.execute(
        """
        UPDATE requests
        SET publication_json = %s
        WHERE public_id = %s
        """,
        (publication_json, public_id),
    )

    changed = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return changed


def get_next_pending_request():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM requests
        WHERE publication_status = 'pending'
          AND is_publishable = TRUE
          AND result_json IS NOT NULL
          AND response_text IS NOT NULL
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """
    )

    request = cursor.fetchone()
    connection.close()

    return request


def get_pending_publication_requests(limit: int = 10):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM requests
        WHERE publication_status = 'pending'
          AND is_publishable = TRUE
          AND result_json IS NOT NULL
          AND response_text IS NOT NULL
        ORDER BY created_at ASC, id ASC
        LIMIT %s
        """,
        (limit,),
    )

    requests = cursor.fetchall()
    connection.close()

    return requests


def skip_pending_publication_requests_through(last_id: int) -> int:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE requests
        SET publication_status = 'skipped',
            media_json = NULL,
            media_group_id = NULL
        WHERE publication_status = 'pending'
          AND is_publishable = TRUE
          AND result_json IS NOT NULL
          AND response_text IS NOT NULL
          AND id <= %s
        """,
        (last_id,),
    )

    changed = cursor.rowcount
    connection.commit()
    connection.close()

    return changed


def update_publication_status(
    public_id: str,
    status: str,
    published_message_id: int | None = None,
    clear_media: bool = True,
) -> bool:
    if status not in REQUEST_STATUSES:
        raise ValueError(f"Невідомий статус публікації: {status}")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE requests
        SET publication_status = %s,
            published_message_id = %s,
            media_json = CASE WHEN %s THEN NULL ELSE media_json END,
            media_group_id = CASE WHEN %s THEN NULL ELSE media_group_id END
        WHERE public_id = %s
        """,
        (status, published_message_id, clear_media, clear_media, public_id)
    )

    changed = cursor.rowcount > 0

    connection.commit()
    connection.close()

    return changed


def get_cache(text_hash: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT response_text, verdict, result_json
        FROM cache
        WHERE text_hash = %s
        """,
        (text_hash,)
    )

    result = cursor.fetchone()
    connection.close()

    if result is None or not result.get("result_json"):
        return None

    result["result"] = json.loads(result["result_json"])

    return result


def save_cache(
    text_hash: str,
    original_text: str,
    response_text: str,
    verdict: str | None = None,
    result: dict | None = None,
):
    connection = get_connection()
    cursor = connection.cursor()
    result_json = json.dumps(result, ensure_ascii=False) if result is not None else None

    cursor.execute(
        """
        INSERT INTO cache (
            text_hash,
            original_text,
            response_text,
            verdict,
            result_json
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (text_hash) DO UPDATE SET
            original_text = EXCLUDED.original_text,
            response_text = EXCLUDED.response_text,
            verdict = EXCLUDED.verdict,
            result_json = EXCLUDED.result_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (text_hash, original_text, response_text, verdict, result_json)
    )

    connection.commit()
    connection.close()


def add_feedback(user_id: int, username: str | None, feedback_text: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO feedback (user_id, username, feedback_text)
        VALUES (%s, %s, %s)
        """,
        (user_id, username, feedback_text)
    )

    connection.commit()
    connection.close()


def get_recent_feedback(limit: int = 10):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT id, user_id, username, feedback_text, created_at
        FROM feedback
        ORDER BY id DESC
        LIMIT %s
        """,
        (limit,)
    )

    rows = cursor.fetchall()
    connection.close()

    return rows


def create_payment(
    user_id: int,
    package_id: str,
    package_title: str,
    checks_added: int,
    amount: float,
    currency: str = "UAH"
) -> str:
    order_id = f"afua_{user_id}_{package_id}_{int(datetime.now(timezone.utc).timestamp())}_{secrets.token_hex(4)}"

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO payments (
            order_id,
            user_id,
            package_id,
            package_title,
            checks_added,
            amount,
            currency,
            status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            order_id,
            user_id,
            package_id,
            package_title,
            checks_added,
            amount,
            currency,
            "created"
        )
    )

    connection.commit()
    connection.close()

    return order_id


def get_payment_by_order_id(order_id: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM payments WHERE order_id = %s",
        (order_id,)
    )

    payment = cursor.fetchone()
    connection.close()

    return payment


def update_payment_status(
    order_id: str,
    status: str,
    liqpay_order_id: str | None = None,
    raw_data: dict | None = None,
    paid: bool = False
) -> bool:
    connection = get_connection()
    cursor = connection.cursor()

    paid_at_sql = "CURRENT_TIMESTAMP" if paid else "paid_at"

    cursor.execute(
        f"""
        UPDATE payments
        SET status = %s,
            liqpay_order_id = COALESCE(%s, liqpay_order_id),
            raw_data = COALESCE(%s, raw_data),
            updated_at = CURRENT_TIMESTAMP,
            paid_at = {paid_at_sql}
        WHERE order_id = %s
        """,
        (
            status,
            liqpay_order_id,
            json.dumps(raw_data, ensure_ascii=False) if raw_data else None,
            order_id
        )
    )

    changed = cursor.rowcount > 0

    connection.commit()
    connection.close()

    return changed


def process_successful_payment(order_id: str, callback_data: dict) -> dict:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM payments WHERE order_id = %s",
        (order_id,)
    )
    payment = cursor.fetchone()

    if payment is None:
        connection.close()
        return {
            "ok": False,
            "credited": False,
            "message": "payment_not_found",
        }

    status = callback_data.get("status", "unknown")
    liqpay_order_id = callback_data.get("liqpay_order_id")
    raw_data = json.dumps(callback_data, ensure_ascii=False)

    if payment["status"] in SUCCESS_PAYMENT_STATUSES:
        connection.close()
        return {
            "ok": True,
            "credited": False,
            "already_processed": True,
            "user_id": payment["user_id"],
            "checks_added": payment["checks_added"],
            "message": "already_processed",
        }

    if status in SUCCESS_PAYMENT_STATUSES:
        cursor.execute(
            """
            UPDATE payments
            SET status = %s,
                liqpay_order_id = %s,
                raw_data = %s,
                updated_at = CURRENT_TIMESTAMP,
                paid_at = CURRENT_TIMESTAMP
            WHERE order_id = %s
            """,
            (status, liqpay_order_id, raw_data, order_id)
        )

        cursor.execute(
            """
            INSERT INTO users (user_id, texts_limit, free_limit, last_free_reset_month)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (payment["user_id"], FREE_TEXT_LIMIT, FREE_TEXT_LIMIT, current_month())
        )

        cursor.execute(
            """
            UPDATE users
            SET paid_balance = paid_balance + %s,
                plan = 'paid',
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
            """,
            (payment["checks_added"], payment["user_id"])
        )

        connection.commit()
        connection.close()

        return {
            "ok": True,
            "credited": True,
            "user_id": payment["user_id"],
            "checks_added": payment["checks_added"],
            "package_title": payment["package_title"],
            "message": "credited",
        }

    cursor.execute(
        """
        UPDATE payments
        SET status = %s,
            liqpay_order_id = %s,
            raw_data = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE order_id = %s
        """,
        (status, liqpay_order_id, raw_data, order_id)
    )

    connection.commit()
    connection.close()

    return {
        "ok": True,
        "credited": False,
        "status": status,
        "user_id": payment["user_id"],
        "checks_added": payment["checks_added"],
        "message": "status_saved",
    }


def get_recent_payments(limit: int = 10):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            id,
            order_id,
            user_id,
            package_id,
            package_title,
            checks_added,
            amount,
            currency,
            status,
            created_at,
            updated_at,
            paid_at
        FROM payments
        ORDER BY id DESC
        LIMIT %s
        """,
        (limit,)
    )

    rows = cursor.fetchall()
    connection.close()

    return rows


def get_payment_debug(order_id: str):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM payments WHERE order_id = %s",
        (order_id,)
    )
    payment = cursor.fetchone()

    user = None
    if payment is not None:
        cursor.execute(
            "SELECT * FROM users WHERE user_id = %s",
            (payment["user_id"],)
        )
        user = cursor.fetchone()

    connection.close()

    return payment, user


def admin_add_paid_balance(user_id: int, checks: int) -> bool:
    if checks <= 0:
        return False

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO users (user_id, texts_limit, free_limit, last_free_reset_month)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (user_id, FREE_TEXT_LIMIT, FREE_TEXT_LIMIT, current_month())
    )

    cursor.execute(
        """
        UPDATE users
        SET paid_balance = paid_balance + %s,
            plan = 'paid',
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
        """,
        (checks, user_id)
    )

    changed = cursor.rowcount > 0

    connection.commit()
    connection.close()

    return changed


def get_payment_stats():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM payments")
    payments_count = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM payments
        GROUP BY status
        ORDER BY count DESC
        """
    )
    status_stats = cursor.fetchall()

    cursor.execute(
        """
        SELECT COALESCE(SUM(checks_added), 0) AS total
        FROM payments
        WHERE status IN ('success', 'sandbox')
        """
    )
    paid_checks_total = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM payments
        WHERE status IN ('success', 'sandbox')
        """
    )
    paid_amount_total = cursor.fetchone()["total"]

    connection.close()

    return {
        "payments_count": payments_count,
        "status_stats": status_stats,
        "paid_checks_total": paid_checks_total,
        "paid_amount_total": paid_amount_total,
    }


def get_basic_stats():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) AS count FROM users")
    users_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM requests")
    requests_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM cache")
    cache_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM feedback")
    feedback_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM payments")
    payments_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM channel_settings WHERE mode = 'auto'")
    automatic_channels_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) AS count FROM quick_checks")
    quick_checks_count = cursor.fetchone()["count"]

    cursor.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM quick_checks
        GROUP BY status
        ORDER BY count DESC
        """
    )
    quick_check_status_stats = cursor.fetchall()

    cursor.execute(
        """
        SELECT verdict, COUNT(*) AS count
        FROM requests
        WHERE verdict IS NOT NULL
        GROUP BY verdict
        ORDER BY count DESC
        """
    )
    verdict_stats = cursor.fetchall()

    cursor.execute(
        """
        SELECT publication_status, COUNT(*) AS count
        FROM requests
        GROUP BY publication_status
        ORDER BY count DESC
        """
    )
    publication_stats = cursor.fetchall()

    cursor.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM payments
        GROUP BY status
        ORDER BY count DESC
        """
    )
    payment_status_stats = cursor.fetchall()

    connection.close()

    return {
        "users_count": users_count,
        "requests_count": requests_count,
        "cache_count": cache_count,
        "feedback_count": feedback_count,
        "payments_count": payments_count,
        "automatic_channels_count": automatic_channels_count,
        "quick_checks_count": quick_checks_count,
        "quick_check_status_stats": quick_check_status_stats,
        "verdict_stats": verdict_stats,
        "publication_stats": publication_stats,
        "payment_status_stats": payment_status_stats,
    }


def get_domain_stats():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT detected_domains, verdict
        FROM requests
        WHERE detected_domains IS NOT NULL
          AND detected_domains != ''
          AND verdict IS NOT NULL
        """
    )

    rows = cursor.fetchall()
    connection.close()

    stats = {}

    for row in rows:
        domains = [
            domain.strip()
            for domain in row["detected_domains"].split(",")
            if domain.strip()
        ]

        verdict = row["verdict"]

        for domain in domains:
            if domain not in stats:
                stats[domain] = {}

            stats[domain][verdict] = stats[domain].get(verdict, 0) + 1

    return stats


def get_chat_source_stats():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT source_type, source_title, verdict, COUNT(*) AS count
        FROM requests
        WHERE source_title IS NOT NULL
          AND source_title != ''
          AND source_title != 'Приватний чат'
          AND verdict IS NOT NULL
        GROUP BY source_type, source_title, verdict
        ORDER BY count DESC
        """
    )

    rows = cursor.fetchall()
    connection.close()

    return rows


def set_donation_intent(user_id: int) -> None:
    """Mark the next private photo as a support screenshot until it is consumed."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO donation_intents (user_id, expires_at, updated_at)
        VALUES (%s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET
            expires_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id,),
    )
    connection.commit()
    connection.close()


def has_donation_intent(user_id: int) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT user_id FROM donation_intents WHERE user_id = %s",
        (user_id,),
    )
    row = cursor.fetchone()
    connection.close()

    return row is not None


def consume_donation_intent(user_id: int) -> bool:
    """Consume the active support-screenshot mode without a time limit."""
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        DELETE FROM donation_intents
        WHERE user_id = %s
        RETURNING user_id
        """,
        (user_id,),
    )
    row = cursor.fetchone()
    connection.commit()
    connection.close()

    return row is not None


def create_donation_submission(
    *,
    user_id: int,
    username: str | None,
    first_name: str | None,
    file_id: str,
    file_unique_id: str | None,
    caption: str | None,
) -> int:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        INSERT INTO donation_submissions (
            user_id, username, first_name, file_id, file_unique_id, caption
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, username, first_name, file_id, file_unique_id, caption),
    )
    submission_id = cursor.fetchone()["id"]
    connection.commit()
    connection.close()

    return submission_id


def get_donation_submission(submission_id: int):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        "SELECT * FROM donation_submissions WHERE id = %s",
        (submission_id,),
    )
    row = cursor.fetchone()
    connection.close()

    return row


def update_donation_submission(
    *,
    submission_id: int,
    status: str,
    reviewed_by: int,
    checks_added: int | None = None,
) -> bool:
    if status not in {"approved", "rejected"}:
        raise ValueError("Невідомий статус заявки підтримки")

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        UPDATE donation_submissions
        SET status = %s,
            reviewed_by = %s,
            checks_added = %s,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = %s AND status = 'pending'
        """,
        (status, reviewed_by, checks_added, submission_id),
    )
    changed = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return changed



def approve_donation_and_add_balance(
    *,
    submission_id: int,
    reviewed_by: int,
    checks_added: int,
):
    if checks_added <= 0:
        return None

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT *
        FROM donation_submissions
        WHERE id = %s AND status = 'pending'
        FOR UPDATE
        """,
        (submission_id,),
    )
    submission = cursor.fetchone()

    if submission is None:
        connection.close()
        return None

    cursor.execute(
        """
        INSERT INTO users (user_id, texts_limit, free_limit, last_free_reset_month)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (user_id) DO NOTHING
        """,
        (submission["user_id"], FREE_TEXT_LIMIT, FREE_TEXT_LIMIT, current_month()),
    )
    cursor.execute(
        """
        UPDATE users
        SET paid_balance = paid_balance + %s,
            plan = 'supported',
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = %s
        """,
        (checks_added, submission["user_id"]),
    )
    cursor.execute(
        """
        UPDATE donation_submissions
        SET status = 'approved',
            reviewed_by = %s,
            checks_added = %s,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (reviewed_by, checks_added, submission_id),
    )
    connection.commit()
    connection.close()

    return submission

def approve_latest_pending_donation_for_user(
    *,
    user_id: int,
    reviewed_by: int,
    checks_added: int,
) -> bool:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id
        FROM donation_submissions
        WHERE user_id = %s AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id,),
    )
    row = cursor.fetchone()

    if row is None:
        connection.close()
        return False

    cursor.execute(
        """
        UPDATE donation_submissions
        SET status = 'approved',
            reviewed_by = %s,
            checks_added = %s,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = %s AND status = 'pending'
        """,
        (reviewed_by, checks_added, row["id"]),
    )
    changed = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return changed


def get_recent_donation_submissions(limit: int = 10):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT id, user_id, username, first_name, status, checks_added, created_at, reviewed_at
        FROM donation_submissions
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cursor.fetchall()
    connection.close()

    return rows


def get_donation_stats() -> dict:
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM donation_submissions")
    submissions_count = cursor.fetchone()["count"]
    cursor.execute(
        """
        SELECT status, COUNT(*) AS count
        FROM donation_submissions
        GROUP BY status
        ORDER BY count DESC
        """
    )
    status_stats = cursor.fetchall()
    cursor.execute(
        """
        SELECT COALESCE(SUM(checks_added), 0) AS total
        FROM donation_submissions
        WHERE status = 'approved'
        """
    )
    checks_total = cursor.fetchone()["total"]
    connection.close()

    return {
        "submissions_count": submissions_count,
        "status_stats": status_stats,
        "checks_total": checks_total,
    }

def get_channel_setting(chat_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        "SELECT * FROM channel_settings WHERE chat_id = %s",
        (chat_id,),
    )
    row = cursor.fetchone()
    connection.close()

    return row


def save_channel_setting(
    *,
    chat_id: int,
    chat_title: str | None,
    chat_type: str,
    enabled_by: int,
    mode: str = "manual",
) -> None:
    if mode not in CHANNEL_MODES:
        raise ValueError(f"Невідомий режим QuickCheck: {mode}")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO channel_settings (
            chat_id, chat_title, chat_type, mode, enabled_by, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (chat_id) DO UPDATE SET
            chat_title = EXCLUDED.chat_title,
            chat_type = EXCLUDED.chat_type,
            enabled_by = EXCLUDED.enabled_by,
            updated_at = CURRENT_TIMESTAMP
        """,
        (chat_id, chat_title, chat_type, mode, enabled_by),
    )

    connection.commit()
    connection.close()


def set_channel_mode(chat_id: int, mode: str, enabled_by: int) -> bool:
    if mode not in CHANNEL_MODES:
        raise ValueError(f"Невідомий режим QuickCheck: {mode}")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE channel_settings
        SET mode = %s,
            enabled_by = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE chat_id = %s
        """,
        (mode, enabled_by, chat_id),
    )

    changed = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return changed


def reserve_quick_check(
    *,
    chat_id: int,
    message_id: int,
    post_hash: str,
) -> bool:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO quick_checks (chat_id, source_message_id, post_hash, status)
        VALUES (%s, %s, %s, 'processing')
        ON CONFLICT (chat_id, source_message_id) DO NOTHING
        """,
        (chat_id, message_id, post_hash),
    )

    inserted = cursor.rowcount > 0
    connection.commit()
    connection.close()

    return inserted


def complete_quick_check(
    *,
    chat_id: int,
    message_id: int,
    status: str,
    verdict: str | None = None,
    short_note: str | None = None,
    marker_message_id: int | None = None,
    public_id: str | None = None,
    was_reply: bool = False,
) -> None:
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE quick_checks
        SET status = %s,
            verdict = %s,
            short_note = %s,
            marker_message_id = %s,
            public_id = %s,
            was_reply = %s,
            completed_at = CURRENT_TIMESTAMP
        WHERE chat_id = %s AND source_message_id = %s
        """,
        (status, verdict, short_note, marker_message_id, public_id, was_reply, chat_id, message_id),
    )

    connection.commit()
    connection.close()


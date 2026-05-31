import json
import secrets
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from config import FREE_TEXT_LIMIT, require_database_url


BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

REQUEST_STATUSES = {"pending", "published", "skipped", "rejected"}
SUCCESS_PAYMENT_STATUSES = {"success", "sandbox"}


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
            return True, f"<b>Залишилось безкоштовних перевірок:</b> {remaining_free}\nДодатковий пакет можна активувати командою <code>/buy</code>."

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
            return True, f"<b>Залишилось платних перевірок:</b> {remaining_paid}\nПоповнити баланс можна командою <code>/buy</code>."

        return True, ""

    connection.close()

    return (
        False,
        "<b>Ліміт перевірок вичерпано</b>\n\n"
        f"<b>Безкоштовні перевірки:</b> {free_used}/{free_limit}\n"
        "<b>Платний баланс:</b> 0\n\n"
        "Щоб продовжити перевірку, активуй додатковий пакет командою <code>/buy</code>."
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
    from_cache: bool = False
) -> str:
    connection = get_connection()
    cursor = connection.cursor()

    public_id = generate_public_id()

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
            publication_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            "pending"
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


def get_next_pending_request():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT *
        FROM requests
        WHERE publication_status = 'pending'
          AND response_text IS NOT NULL
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """
    )

    request = cursor.fetchone()
    connection.close()

    return request


def update_publication_status(
    public_id: str,
    status: str,
    published_message_id: int | None = None
) -> bool:
    if status not in REQUEST_STATUSES:
        raise ValueError(f"Невідомий статус публікації: {status}")

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE requests
        SET publication_status = %s,
            published_message_id = %s
        WHERE public_id = %s
        """,
        (status, published_message_id, public_id)
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
        SELECT response_text, verdict
        FROM cache
        WHERE text_hash = %s
        """,
        (text_hash,)
    )

    result = cursor.fetchone()
    connection.close()

    return result


def save_cache(
    text_hash: str,
    original_text: str,
    response_text: str,
    verdict: str | None = None
):
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO cache (
            text_hash,
            original_text,
            response_text,
            verdict
        )
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (text_hash) DO UPDATE SET
            original_text = EXCLUDED.original_text,
            response_text = EXCLUDED.response_text,
            verdict = EXCLUDED.verdict,
            updated_at = CURRENT_TIMESTAMP
        """,
        (text_hash, original_text, response_text, verdict)
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

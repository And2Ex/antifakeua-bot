import base64
import hashlib
import json
from urllib.parse import urlencode

from config import (
    BASE_WEBHOOK_URL,
    LIQPAY_PRIVATE_KEY,
    LIQPAY_PUBLIC_KEY,
    LIQPAY_SANDBOX,
    PAYMENT_RESULT_URL,
)


LIQPAY_CHECKOUT_URL = "https://www.liqpay.ua/api/3/checkout"

PAYMENT_PACKAGES = {
    "basic": {
        "title": "Basic",
        "checks": 100,
        "amount": 99.0,
        "currency": "UAH",
        "description": "100 перевірок AntiFakeUA_Bot",
    },
    "pro": {
        "title": "Pro",
        "checks": 1000,
        "amount": 499.0,
        "currency": "UAH",
        "description": "1000 перевірок AntiFakeUA_Bot",
    },
}


def get_package(package_id: str) -> dict | None:
    return PAYMENT_PACKAGES.get(package_id)


def get_packages_text() -> str:
    lines = [
        "Доступні пакети:",
        "",
    ]

    for package_id, package in PAYMENT_PACKAGES.items():
        lines.append(
            f"• {package['title']} — {package['checks']} перевірок за {package['amount']:.0f} {package['currency']}"
        )

    lines.extend([
        "",
        "Після успішної оплати перевірки автоматично додаються до платного балансу.",
    ])

    return "\n".join(lines)


def require_liqpay_config():
    missing = []

    if not LIQPAY_PUBLIC_KEY:
        missing.append("LIQPAY_PUBLIC_KEY")

    if not LIQPAY_PRIVATE_KEY:
        missing.append("LIQPAY_PRIVATE_KEY")

    if not BASE_WEBHOOK_URL:
        missing.append("BASE_WEBHOOK_URL")

    if missing:
        raise ValueError(
            "Не задані змінні .env для оплати: " + ", ".join(missing)
        )


def encode_payment_data(payload: dict) -> str:
    json_data = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return base64.b64encode(json_data.encode("utf-8")).decode("utf-8")


def make_signature(data: str) -> str:
    sign_string = f"{LIQPAY_PRIVATE_KEY}{data}{LIQPAY_PRIVATE_KEY}".encode("utf-8")
    signature = hashlib.sha1(sign_string).digest()

    return base64.b64encode(signature).decode("utf-8")


def create_checkout_url(order_id: str, package: dict) -> str:
    require_liqpay_config()

    payload = {
        "public_key": LIQPAY_PUBLIC_KEY,
        "version": 3,
        "action": "pay",
        "amount": package["amount"],
        "currency": package["currency"],
        "description": package["description"],
        "order_id": order_id,
        "server_url": f"{BASE_WEBHOOK_URL}/liqpay/callback",
        "language": "uk",
    }

    if PAYMENT_RESULT_URL:
        payload["result_url"] = PAYMENT_RESULT_URL

    if LIQPAY_SANDBOX:
        payload["sandbox"] = 1

    data = encode_payment_data(payload)
    signature = make_signature(data)

    return f"{LIQPAY_CHECKOUT_URL}?{urlencode({'data': data, 'signature': signature})}"


def decode_callback_data(data: str) -> dict:
    decoded = base64.b64decode(data).decode("utf-8")

    return json.loads(decoded)


def verify_callback_signature(data: str, signature: str) -> bool:
    expected_signature = make_signature(data)

    return expected_signature == signature

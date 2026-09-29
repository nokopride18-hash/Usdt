import asyncio
import logging
import os
import re
import sqlite3
import time
from html import escape

import aiohttp
from aiohttp import web

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# =========================================================
# إعدادات
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
PORT = int(os.getenv("PORT", "10000"))

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "").strip()
TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY", "").strip()

BEP20_WALLET_ADDRESS = os.getenv("BEP20_WALLET_ADDRESS", "").strip()
ERC20_WALLET_ADDRESS = os.getenv("ERC20_WALLET_ADDRESS", "").strip()
TRC20_WALLET_ADDRESS = os.getenv("TRC20_WALLET_ADDRESS", "").strip()

# =========================================================
# عقود USDT الحقيقي
# =========================================================

# Ethereum USDT - Tether official
ERC20_USDT_CONTRACT = (
    "0xdAC17F958D2ee523a2206206994597C13D831ec7"
)

# TRON USDT - Tether official
TRC20_USDT_CONTRACT = (
    "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
)

# BSC:
# نضعه كمتغير بيئة حتى لا نثبت عقدًا مختلفًا عن العقد
# الذي يقرر البوت قبول الدفع منه.
BEP20_USDT_CONTRACT = os.getenv(
    "BEP20_USDT_CONTRACT",
    "0x55d398326f99059fF775485246999027B3197955",
).strip()


# =========================================================
# الباقات
# =========================================================

PACKAGES = {
    "BEP20": [
        ("1500", "80"),
        ("3000", "159"),
        ("4500", "235"),
    ],
    "ERC20": [
        ("500", "92"),
        ("1000", "182"),
    ],
    "TRC20": [
        ("1500", "350"),
    ],
}


WALLETS = {
    "BEP20": BEP20_WALLET_ADDRESS,
    "ERC20": ERC20_WALLET_ADDRESS,
    "TRC20": TRC20_WALLET_ADDRESS,
}


# =========================================================
# إعدادات التحقق
# =========================================================

# مدة صلاحية الطلب للبحث عن الدفع
PAYMENT_WINDOW_SECONDS = 60 * 60

# الحد الأدنى للتأكيدات لشبكات EVM
MIN_EVM_CONFIRMATIONS = 12


# =========================================================
# Logging
# =========================================================

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================================================
# SQLite
# =========================================================

DB_PATH = os.getenv("DB_PATH", "orders.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE NOT NULL,
            telegram_user_id INTEGER NOT NULL,
            telegram_username TEXT,
            network TEXT NOT NULL,
            amount TEXT NOT NULL,
            price TEXT NOT NULL,
            receiving_wallet TEXT NOT NULL,
            payment_wallet TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting_payment',
            tx_hash TEXT UNIQUE,
            paid_at INTEGER
        )
        """
    )

    conn.commit()
    conn.close()


def create_order(
    telegram_user_id,
    telegram_username,
    network,
    amount,
    price,
    receiving_wallet,
):
    order_id = f"ORD-{int(time.time())}-{telegram_user_id}"

    conn = get_db()

    conn.execute(
        """
        INSERT INTO orders (
            order_id,
            telegram_user_id,
            telegram_username,
            network,
            amount,
            price,
            receiving_wallet,
            payment_wallet,
            created_at,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            telegram_user_id,
            telegram_username,
            network,
            amount,
            price,
            receiving_wallet,
            WALLETS[network],
            int(time.time()),
            "awaiting_payment",
        ),
    )

    conn.commit()
    conn.close()

    return order_id


def get_order(order_id):
    conn = get_db()

    row = conn.execute(
        "SELECT * FROM orders WHERE order_id = ?",
        (order_id,),
    ).fetchone()

    conn.close()

    return row


def mark_order_paid(order_id, tx_hash):
    conn = get_db()

    conn.execute(
        """
        UPDATE orders
        SET status = 'paid',
            tx_hash = ?,
            paid_at = ?
        WHERE order_id = ?
        """,
        (
            tx_hash,
            int(time.time()),
            order_id,
        ),
    )

    conn.commit()
    conn.close()


def tx_already_used(tx_hash):
    conn = get_db()

    row = conn.execute(
        "SELECT order_id FROM orders WHERE tx_hash = ?",
        (tx_hash,),
    ).fetchone()

    conn.close()

    return row is not None


# =========================================================
# التحقق من العناوين
# =========================================================

EVM_ADDRESS_RE = re.compile(
    r"^0x[a-fA-F0-9]{40}$"
)


def is_valid_evm_address(address):
    return bool(EVM_ADDRESS_RE.fullmatch(address.strip()))


TRON_BASE58_ALPHABET = (
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)


def base58_decode(value):
    num = 0

    for char in value:
        if char not in TRON_BASE58_ALPHABET:
            raise ValueError("Invalid Base58")

        num = (
            num * 58
            + TRON_BASE58_ALPHABET.index(char)
        )

    raw = num.to_bytes(
        (num.bit_length() + 7) // 8,
        "big",
    )

    padding = 0

    for char in value:
        if char == "1":
            padding += 1
        else:
            break

    return b"\x00" * padding + raw


def is_valid_tron_address(address):
    try:
        address = address.strip()

        if not address.startswith("T"):
            return False

        decoded = base58_decode(address)

        if len(decoded) != 25:
            return False

        payload = decoded[:-4]
        checksum = decoded[-4:]

        import hashlib

        first_hash = hashlib.sha256(payload).digest()
        second_hash = hashlib.sha256(first_hash).digest()

        return checksum == second_hash[:4]

    except Exception:
        return False


def validate_wallet(network, address):

    address = address.strip()

    if network in ("BEP20", "ERC20"):
        return is_valid_evm_address(address)

    if network == "TRC20":
        return is_valid_tron_address(address)

    return False


# =========================================================
# واجهة المستخدم
# =========================================================

def main_menu():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🛒 شراء FLASH Token",
                    callback_data="buy",
                )
            ],
            [
                InlineKeyboardButton(
                    "💰 الأسعار والباقات",
                    callback_data="prices",
                )
            ],
        ]
    )


def home_button():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ]
        ]
    )


def network_keyboard():

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🟡 BEP20",
                    callback_data="network:BEP20",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔵 ERC20",
                    callback_data="network:ERC20",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔴 TRC20",
                    callback_data="network:TRC20",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ],
        ]
    )


def package_keyboard(network):

    buttons = []

    for amount, price in PACKAGES[network]:

        buttons.append(
            [
                InlineKeyboardButton(
                    f"💰 {amount} FLASH Token — ${price}",
                    callback_data=(
                        f"package:{network}:{amount}:{price}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                "🔙 العودة للشبكات",
                callback_data="buy",
            )
        ]
    )

    return InlineKeyboardMarkup(buttons)


# =========================================================
# /start
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    text = (
        "👋 <b>مرحبًا بك في متجر FLASH Token</b>\n\n"
        "⚠️ <b>تنبيه:</b>\n"
        "FLASH Token هو توكن منفصل عن Tether USD₮.\n\n"
        "يمكنك شراء الباقات المتاحة والدفع باستخدام "
        "USDT الحقيقي على الشبكة التي تختارها.\n\n"
        "اختر من القائمة 👇"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# =========================================================
# استقبال عنوان محفظة المستخدم
# =========================================================

async def wallet_message_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    if not update.message:
        return

    state = context.user_data.get("state")

    if state != "waiting_wallet":
        return

    network = context.user_data.get("network")
    amount = context.user_data.get("amount")
    price = context.user_data.get("price")

    wallet = update.message.text.strip()

    if not network:
        context.user_data.clear()

        await update.message.reply_text(
            "❌ انتهت صلاحية الطلب. ابدأ من جديد عبر /start"
        )
        return

    if not validate_wallet(network, wallet):

        await update.message.reply_text(
            f"❌ عنوان المحفظة غير صالح لشبكة {network}.\n\n"
            "أرسل عنوانًا صحيحًا للشبكة المختارة."
        )
        return

    user = update.effective_user

    order_id = create_order(
        telegram_user_id=user.id,
        telegram_username=user.username or "",
        network=network,
        amount=amount,
        price=price,
        receiving_wallet=wallet,
    )

    context.user_data["state"] = "awaiting_payment"
    context.user_data["order_id"] = order_id

    payment_wallet = WALLETS[network]

    safe_payment_wallet = escape(payment_wallet)
    safe_receiving_wallet = escape(wallet)

    text = (
        "🧾 <b>تفاصيل الطلب</b>\n\n"
        f"🆔 <b>رقم الطلب:</b> <code>{order_id}</code>\n"
        f"🌐 <b>الشبكة:</b> {network}\n"
        f"💰 <b>الكمية:</b> {amount} FLASH Token\n"
        f"💵 <b>السعر:</b> ${price}\n\n"
        "📥 <b>محفظتك لاستلام الطلب:</b>\n"
        f"<code>{safe_receiving_wallet}</code>\n\n"
        "💳 <b>أرسل USDT الحقيقي إلى:</b>\n"
        f"<code>{safe_payment_wallet}</code>\n\n"
        f"⚠️ استخدم شبكة <b>{network}</b> فقط.\n"
        f"⚠️ أرسل بالضبط <b>{price} USDT</b>.\n\n"
        "بعد إتمام التحويل، اضغط:\n"
        "<b>🔍 تحقق من الدفع</b>\n\n"
        "لن تحتاج إلى إرسال TX Hash."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔍 تحقق من الدفع",
                    callback_data=f"verify:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                )
            ],
        ]
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# =========================================================
# Etherscan
# =========================================================

async def check_evm_payment(
    network,
    payment_wallet,
    expected_amount,
    created_at,
):

    chain_id = "56" if network == "BEP20" else "1"

    contract = (
        BEP20_USDT_CONTRACT
        if network == "BEP20"
        else ERC20_USDT_CONTRACT
    )

    url = "https://api.etherscan.io/v2/api"

    params = {
        "chainid": chain_id,
        "module": "account",
        "action": "tokentx",
        "contractaddress": contract,
        "address": payment_wallet,
        "page": "1",
        "offset": "100",
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.get(
            url,
            params=params,
        ) as response:

            if response.status != 200:
                raise RuntimeError(
                    f"Etherscan HTTP {response.status}"
                )

            data = await response.json()

    if data.get("status") == "0":
        result = data.get("result")

        if isinstance(result, str):
            logger.warning(
                "Etherscan returned: %s",
                result,
            )

        return None

    transfers = data.get("result", [])

    if not isinstance(transfers, list):
        return None

    # USDT amount decimals:
    # Ethereum USDT = 6
    # BSC token commonly used at this address = 18
    decimals = 18 if network == "BEP20" else 6

    expected_raw = int(
        float(expected_amount) * (10 ** decimals)
    )

    payment_wallet_lower = payment_wallet.lower()
    contract_lower = contract.lower()

    candidates = []

    for tx in transfers:

        tx_contract = str(
            tx.get("contractAddress", "")
        ).lower()

        tx_to = str(
            tx.get("to", "")
        ).lower()

        if tx_contract != contract_lower:
            continue

        if tx_to != payment_wallet_lower:
            continue

        try:
            timestamp = int(
                tx.get("timeStamp", "0")
            )
        except Exception:
            continue

        if timestamp < created_at:
            continue

        if timestamp > created_at + PAYMENT_WINDOW_SECONDS:
            continue

        try:
            raw_value = int(
                tx.get("value", "0")
            )
        except Exception:
            continue

        if raw_value != expected_raw:
            continue

        try:
            confirmations = int(
                tx.get("confirmations", "0")
            )
        except Exception:
            confirmations = 0

        if confirmations < MIN_EVM_CONFIRMATIONS:
            continue

        tx_hash = tx.get("hash")

        if not tx_hash:
            continue

        if tx_already_used(tx_hash):
            continue

        candidates.append(
            {
                "tx_hash": tx_hash,
                "timestamp": timestamp,
                "from": tx.get("from", ""),
                "confirmations": confirmations,
            }
        )

    # If exactly one transaction matches,
    # we can safely associate it with this order.
    if len(candidates) == 1:
        return candidates[0]

    # Multiple identical payments cannot safely be
    # attributed automatically.
    if len(candidates) > 1:
        logger.warning(
            "Multiple matching EVM payments found."
        )

    return None


# =========================================================
# TRON
# =========================================================

async def check_tron_payment(
    payment_wallet,
    expected_amount,
    created_at,
):

    url = (
        "https://api.trongrid.io"
        f"/v1/accounts/{payment_wallet}"
        "/transactions/trc20"
    )

    params = {
        "only_confirmed": "true",
        "only_to": "true",
        "limit": "200",
        "order_by": "block_timestamp,desc",
        "min_timestamp": created_at * 1000,
        "max_timestamp": (
            created_at + PAYMENT_WINDOW_SECONDS
        ) * 1000,
        "contract_address": TRC20_USDT_CONTRACT,
    }

    headers = {
        "TRON-PRO-API-KEY": TRONGRID_API_KEY,
        "accept": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(
        timeout=timeout
    ) as session:

        async with session.get(
            url,
            params=params,
            headers=headers,
        ) as response:

            if response.status != 200:
                raise RuntimeError(
                    f"TronGrid HTTP {response.status}"
                )

            data = await response.json()

    transfers = data.get("data", [])

    if not isinstance(transfers, list):
        return None

    candidates = []

    for tx in transfers:

        token_info = tx.get(
            "token_info",
            {},
        )

        token_address = str(
            token_info.get("address", "")
        )

        if token_address.lower() != (
            TRC20_USDT_CONTRACT.lower()
        ):
            continue

        if str(tx.get("to", "")) != payment_wallet:
            continue

        if tx.get("type") != "Transfer":
            continue

        if tx.get("success") is False:
            continue

        decimals = int(
            token_info.get("decimals", 6)
        )

        expected_raw = int(
            float(expected_amount)
            * (10 ** decimals)
        )

        try:
            raw_value = int(
                tx.get("value", "0")
            )
        except Exception:
            continue

        if raw_value != expected_raw:
            continue

        tx_hash = tx.get("transaction_id")

        if not tx_hash:
            continue

        if tx_already_used(tx_hash):
            continue

        candidates.append(
            {
                "tx_hash": tx_hash,
                "timestamp": int(
                    tx.get("block_timestamp", 0)
                ) // 1000,
                "from": tx.get("from", ""),
            }
        )

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        logger.warning(
            "Multiple matching TRON payments found."
        )

    return None


# =========================================================
# التحقق من الدفع
# =========================================================

async def verify_order(order):

    network = order["network"]
    amount = order["price"]
    payment_wallet = order["payment_wallet"]
    created_at = order["created_at"]

    if network in ("BEP20", "ERC20"):

        return await check_evm_payment(
            network=network,
            payment_wallet=payment_wallet,
            expected_amount=amount,
            created_at=created_at,
        )

    if network == "TRC20":

        return await check_tron_payment(
            payment_wallet=payment_wallet,
            expected_amount=amount,
            created_at=created_at,
        )

    return None


# =========================================================
# الأزرار
# =========================================================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data or ""

    # -----------------------------------------------------
    # Home
    # -----------------------------------------------------

    if data == "home":

        context.user_data.clear()

        text = (
            "👋 <b>مرحبًا بك في متجر FLASH Token</b>\n\n"
            "⚠️ FLASH Token هو توكن منفصل عن Tether USD₮.\n\n"
            "يمكنك شراء الباقات والدفع باستخدام USDT الحقيقي."
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

        return

    # -----------------------------------------------------
    # Buy
    # -----------------------------------------------------

    if data == "buy":

        context.user_data.clear()

        await query.edit_message_text(
            "🛒 <b>شراء FLASH Token</b>\n\n"
            "اختر شبكة الدفع:",
            parse_mode="HTML",
            reply_markup=network_keyboard(),
        )

        return

    # -----------------------------------------------------
    # Network
    # -----------------------------------------------------

    if data.startswith("network:"):

        network = data.split(":", 1)[1]

        if network not in PACKAGES:
            await query.answer(
                "الشبكة غير صحيحة.",
                show_alert=True,
            )
            return

        await query.edit_message_text(
            f"🛒 <b>{network}</b>\n\n"
            "اختر الباقة:",
            parse_mode="HTML",
            reply_markup=package_keyboard(network),
        )

        return

    # -----------------------------------------------------
    # Package
    # -----------------------------------------------------

    if data.startswith("package:"):

        parts = data.split(":")

        if len(parts) != 4:
            await query.answer(
                "حدث خطأ.",
                show_alert=True,
            )
            return

        _, network, amount, price = parts

        valid_package = (
            amount,
            price,
        ) in PACKAGES.get(network, [])

        if not valid_package:
            await query.answer(
                "الباقة غير موجودة.",
                show_alert=True,
            )
            return

        context.user_data["state"] = "waiting_wallet"
        context.user_data["network"] = network
        context.user_data["amount"] = amount
        context.user_data["price"] = price

        await query.edit_message_text(
            "📥 <b>أرسل عنوان محفظتك</b>\n\n"
            f"🌐 الشبكة: <b>{network}</b>\n"
            f"💰 الكمية: <b>{amount} FLASH Token</b>\n"
            f"💵 السعر: <b>${price}</b>\n\n"
            "أرسل الآن عنوان المحفظة التي تريد "
            "استلام الـFLASH Token عليها.",
            parse_mode="HTML",
            reply_markup=home_button(),
        )

        return

    # -----------------------------------------------------
    # Verify
    # -----------------------------------------------------

    if data.startswith("verify:"):

        order_id = data.split(":", 1)[1]

        order = get_order(order_id)

        if not order:
            await query.edit_message_text(
                "❌ لم يتم العثور على الطلب.\n\n"
                "ابدأ طلبًا جديدًا من /start"
            )
            return

        if order["telegram_user_id"] != (
            update.effective_user.id
        ):
            await query.answer(
                "هذا الطلب ليس تابعًا لحسابك.",
                show_alert=True,
            )
            return

        if order["status"] == "paid":

            await query.edit_message_text(
                "✅ <b>تم تأكيد الدفع مسبقًا.</b>\n\n"
                f"🆔 رقم الطلب: "
                f"<code>{escape(order['order_id'])}</code>\n"
                f"💰 الكمية: {escape(order['amount'])} "
                "FLASH Token\n\n"
                "سيتم تنفيذ الطلب يدويًا.",
                parse_mode="HTML",
                reply_markup=home_button(),
            )

            return

        if int(time.time()) > (
            order["created_at"]
            + PAYMENT_WINDOW_SECONDS
        ):

            await query.edit_message_text(
                "⌛ <b>انتهت صلاحية الطلب.</b>\n\n"
                "يرجى إنشاء طلب جديد من /start.",
                parse_mode="HTML",
                reply_markup=home_button(),
            )

            return

        await query.edit_message_text(
            "🔍 <b>جاري التحقق من الدفع...</b>\n\n"
            "انتظر قليلًا، يتم فحص البلوكشين الآن."
        )

        try:

            result = await verify_order(order)

        except Exception:

            logger.exception(
                "Payment verification error"
            )

            await query.edit_message_text(
                "⚠️ تعذر الاتصال بشبكة التحقق حاليًا.\n\n"
                "حاول مرة أخرى بعد قليل.",
                reply_markup=home_button(),
            )

            return

        if not result:

            await query.edit_message_text(
                "❌ <b>لم يتم الدفع.</b>\n\n"
                "لم يتم العثور على تحويل USDT حقيقي "
                "مطابق للطلب حتى الآن.\n\n"
                "تأكد من:\n"
                "• الشبكة الصحيحة\n"
                "• المبلغ الصحيح\n"
                "• إرسال USDT إلى محفظة الدفع الظاهرة في الطلب\n\n"
                "إذا كنت قد دفعت للتو، انتظر تأكيد الشبكة "
                "ثم اضغط «تحقق من الدفع» مرة أخرى.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔍 تحقق مرة أخرى",
                                callback_data=(
                                    f"verify:{order_id}"
                                ),
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                "🏠 الرئيسية",
                                callback_data="home",
                            )
                        ],
                    ]
                ),
            )

            return

        tx_hash = result["tx_hash"]

        if tx_already_used(tx_hash):

            await query.edit_message_text(
                "❌ هذه المعاملة مستخدمة بالفعل لطلب آخر.",
                reply_markup=home_button(),
            )

            return

        mark_order_paid(
            order_id,
            tx_hash,
        )

        text = (
            "✅ <b>تم تأكيد الدفع بنجاح!</b>\n\n"
            f"🆔 <b>رقم الطلب:</b> "
            f"<code>{escape(order['order_id'])}</code>\n"
            f"🌐 <b>الشبكة:</b> {escape(order['network'])}\n"
            f"💰 <b>الكمية:</b> "
            f"{escape(order['amount'])} FLASH Token\n\n"
            "📥 <b>محفظة الاستلام:</b>\n"
            f"<code>{escape(order['receiving_wallet'])}</code>\n\n"
            "سيتم تنفيذ إرسال الـFLASH Token يدويًا "
            "إلى المحفظة التي أدخلتها."
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=home_button(),
        )

        return

    # -----------------------------------------------------
    # Prices
    # -----------------------------------------------------

    if data == "prices":

        text = (
            "💰 <b>الأسعار والباقات</b>\n\n"
            "🟡 <b>BEP20</b>\n"
            "• 1500 FLASH Token — $80\n"
            "• 3000 FLASH Token — $159\n"
            "• 4500 FLASH Token — $235\n\n"
            "🔵 <b>ERC20</b>\n"
            "• 500 FLASH Token — $92\n"
            "• 1000 FLASH Token — $182\n\n"
            "🔴 <b>TRC20</b>\n"
            "• 1500 FLASH Token — $350\n\n"
            "⚠️ الدفع يتم باستخدام USDT الحقيقي."
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu(),
        )

        return


# =========================================================
# Error Handler
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
):

    logger.exception(
        "Unhandled exception",
        exc_info=context.error,
    )


# =========================================================
# Webhook
# =========================================================

async def telegram_webhook(
    request: web.Request,
):

    application = request.app["telegram_app"]

    if WEBHOOK_SECRET:

        received_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            "",
        )

        if received_secret != WEBHOOK_SECRET:

            return web.Response(
                status=403,
                text="Forbidden",
            )

    try:

        data = await request.json()

        update = Update.de_json(
            data,
            application.bot,
        )

        if update:

            await application.update_queue.put(
                update
            )

        return web.Response(
            text="OK"
        )

    except Exception:

        logger.exception(
            "Failed to process webhook"
        )

        return web.Response(
            status=500,
            text="Internal Server Error",
        )


# =========================================================
# Health
# =========================================================

async def health_check(
    request: web.Request,
):

    return web.Response(
        text="FLASH Token Bot is running.",
        content_type="text/plain",
    )


# =========================================================
# Main
# =========================================================

async def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set"
        )

    if not WEBHOOK_URL:
        raise RuntimeError(
            "WEBHOOK_URL is not set"
        )

    if not ETHERSCAN_API_KEY:
        raise RuntimeError(
            "ETHERSCAN_API_KEY is not set"
        )

    if not TRONGRID_API_KEY:
        raise RuntimeError(
            "TRONGRID_API_KEY is not set"
        )

    if not BEP20_WALLET_ADDRESS:
        raise RuntimeError(
            "BEP20_WALLET_ADDRESS is not set"
        )

    if not ERC20_WALLET_ADDRESS:
        raise RuntimeError(
            "ERC20_WALLET_ADDRESS is not set"
        )

    if not TRC20_WALLET_ADDRESS:
        raise RuntimeError(
            "TRC20_WALLET_ADDRESS is not set"
        )

    init_db()

    telegram_app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .updater(None)
        .build()
    )

    telegram_app.add_handler(
        CommandHandler(
            "start",
            start,
        )
    )

    telegram_app.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            wallet_message_handler,
        )
    )

    telegram_app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )

    telegram_app.add_error_handler(
        error_handler
    )

    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = (
        f"{WEBHOOK_URL}/webhook"
    )

    webhook_kwargs = {
        "url": webhook_url,
        "allowed_updates": Update.ALL_TYPES,
    }

    if WEBHOOK_SECRET:
        webhook_kwargs[
            "secret_token"
        ] = WEBHOOK_SECRET

    await telegram_app.bot.set_webhook(
        **webhook_kwargs
    )

    logger.info(
        "Webhook configured: %s",
        webhook_url,
    )

    web_app = web.Application()

    web_app["telegram_app"] = telegram_app

    web_app.router.add_get(
        "/",
        health_check,
    )

    web_app.router.add_post(
        "/webhook",
        telegram_webhook,
    )

    runner = web.AppRunner(
        web_app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=PORT,
    )

    await site.start()

    logger.info(
        "Server started on port %s",
        PORT,
    )

    try:

        await asyncio.Event().wait()

    finally:

        logger.info(
            "Shutting down..."
        )

        await telegram_app.bot.delete_webhook()

        await telegram_app.stop()
        await telegram_app.shutdown()

        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

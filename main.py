import asyncio
import logging
import os
import re
import sqlite3
import time
import uuid
from decimal import Decimal, InvalidOperation
from html import escape

import aiohttp
from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============================================================
# إعدادات
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
PORT = int(os.getenv("PORT", "10000"))

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "").strip()
TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY", "").strip()

BEP20_WALLET_ADDRESS = os.getenv("BEP20_WALLET_ADDRESS", "").strip()
ERC20_WALLET_ADDRESS = os.getenv("ERC20_WALLET_ADDRESS", "").strip()
TRC20_WALLET_ADDRESS = os.getenv("TRC20_WALLET_ADDRESS", "").strip()

# BSC USDT contract commonly indexed as BSC-USD.
# It can be overridden in Render with BEP20_USDT_CONTRACT.
BEP20_USDT_CONTRACT = os.getenv(
    "BEP20_USDT_CONTRACT",
    "0x55d398326f99059fF775485246999027B3197955",
).strip()

ETH_USDT_CONTRACT = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
TRON_USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

DB_PATH = os.getenv("DB_PATH", "orders.db")
ORDER_WINDOW_SECONDS = 60 * 60  # 1 hour

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is not set")
if not ETHERSCAN_API_KEY:
    raise RuntimeError("ETHERSCAN_API_KEY is not set")
if not TRONGRID_API_KEY:
    raise RuntimeError("TRONGRID_API_KEY is not set")

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# المنتجات والأسعار
# ============================================================

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

# ============================================================
# محتوى زر «ما هو FLASH USDT؟»
# ============================================================
# اكتب محتوى الزر بين علامتي الاقتباس الثلاثيتين أدناه.
# يمكنك كتابة عدة أسطر بالعربي والإيموجي بشكل طبيعي.
# مهم: لا تحذف FLASH_USDT_INFO = ولا علامتي """ في البداية والنهاية،
# ولا تضع """ أخرى داخل المحتوى نفسه.
FLASH_USDT_INFO = """  عملات FLASH USDT هي  عملات USDT نظامية ولكن هذه العملات تختفي بعد فترة ثلاث شهور من تاريخ إنتاجها ولكنها تظهر قيمة مطابقة لقيمة عملة ال usdt الأصلية داخل المحافظ والتي تقدر ب 1$ لكل عملة وتباعاً لنظام البوت فإن :

 عند اتمام طلب شراؤك يتم تصنيع عملاتك وارسالهم لك بشكل تلقائي وذلك لان البوت تم ربطه مع Software تصنيع  FLASH USDT الخاص بنا وبهذا يتم التصنيع والارسال بشكل مباشر بمدة لا تتعدى الخمس دقائق .

يجب العلم بأن بعد الشراء يتم إرسال FLASH USDT إلى المحفظة التي أرسلت للبوت عنوانها ويجب تصريف هذه العملات قبل اختفاؤها ( تبقى العملات في المحفظة لمدة ثلاث شهور تماما) ويمكن أن يتم إرسال هذه العملات إلى محافظ اخرى دون وجود أي مشاكل .

أين يمكنني تصريف هذه العملات ؟ يمكنك تصريف هذه العملات في مراكز الصرافة أو متاجر الهواتف التي تعرض تصريف العملات الرقمية ولكن احذر من تصريف كميات كبيرة جداً عند ذات المركز لكي لا تثير الشك و يمكنك ايضا ارسال هذه العملات الى محافظ اشخاص وبيعهم اياها على انها usdt حقيقي ويمكنك ايضا التداول بها في الفوركس او ..... اذ يمكن تداولها داخل منصات MT5 و MT4 وغيرها وعند الربح يمكنك التفريق بين الاموال الحقيقية  و FLASH USDT بان FLASH يختفي تلقائيا من المحفظة بعد ثلاث شهور .

من نحن ؟ شبكة من الأشخاص تعمل لصالح تعاون Ted في اكثر من 4 دول ونظرا لتواجدنا في دول تمنع تصريف ال usdt في المراكز المصرفية قررنا ان نقدمه لحضراتكم بأسعار مخفضة .
ملاحظات :
(غير مسؤولين عن تورط احدكم يجب الانتباه والحذر)
(نحن نعمل في هذه المجالات منذ اكثر من خمس سنوات )
( فريقنا يقدم خدمات اخرى مثل تزوير جوازات السفر والهويات الشخصية للدول التالية : الأردن _لبنان_سوريا_العراق_مصر_اليمن و تزوير المعاملات الحكومية بشتى انواعها )
(لا يقتصر عمل فريقنا على هذه الامور فقط ولكن نقدم المزيد والمزيد من الخدمات بعضها يعتبر مشبوها وغير قابل للعرض داخل مجتمعاتكم)
(لدينا موقع يعرض جميع خدماتنا على Dark web )
 (سنضيف خدمات تواصل من أجل الخدمات الاخرى قريبا )
"""


# ============================================================
# أكواد الخصم
# ============================================================
# الأكواد حساسة لحالة الأحرف. كل كود يمنح خصم 20%.
# لا يتم تحويل الكود إلى lowercase أو uppercase.
DISCOUNT_CODES = {
    "67f7": 20,
    "00b1": 20,
    "50ww": 20,
    "17ss": 20,
    "43ks": 20,
    "29aq": 20,
    "q66o": 20,
    "600h": 20,
    "30ty": 20,
    "10ap": 20,
    "11ui": 20,
    "53vx": 20,
    "23p6": 20,
    "m447": 20,
    "z39a": 20,
    "qw31": 20,
    "g908": 20,
    "vt51": 20,
    "ro28": 20,
    "3q3v": 20,
}


# ============================================================
# قاعدة البيانات
# ============================================================

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                telegram_user_id INTEGER NOT NULL,
                network TEXT NOT NULL,
                amount TEXT NOT NULL,
                price TEXT NOT NULL,
                receive_wallet TEXT NOT NULL,
                payment_wallet TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                status TEXT NOT NULL,
                tx_hash TEXT UNIQUE,
                original_price TEXT,
                discount_code TEXT,
                discount_percent INTEGER DEFAULT 0,
                final_price TEXT
            )
            """
        )

        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(orders)").fetchall()
        }
        migrations = {
            "original_price": "ALTER TABLE orders ADD COLUMN original_price TEXT",
            "discount_code": "ALTER TABLE orders ADD COLUMN discount_code TEXT",
            "discount_percent": "ALTER TABLE orders ADD COLUMN discount_percent INTEGER DEFAULT 0",
            "final_price": "ALTER TABLE orders ADD COLUMN final_price TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                conn.execute(statement)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discount_codes (
                code TEXT PRIMARY KEY,
                percent INTEGER NOT NULL,
                used INTEGER NOT NULL DEFAULT 0,
                used_by INTEGER,
                used_order_id TEXT
            )
            """
        )

        for code, percent in DISCOUNT_CODES.items():
            conn.execute(
                """
                INSERT INTO discount_codes (code, percent, used)
                VALUES (?, ?, 0)
                ON CONFLICT(code) DO UPDATE SET percent = excluded.percent
                """,
                (code, percent),
            )

        conn.commit()


def create_order(
    user_id,
    network,
    amount,
    original_price,
    receive_wallet,
    discount_code=None,
    discount_percent=0,
    final_price=None,
):
    order_id = uuid.uuid4().hex[:10].upper()
    if final_price is None:
        final_price = original_price

    with db() as conn:
        conn.execute(
            """
            INSERT INTO orders
            (id, telegram_user_id, network, amount, price,
             receive_wallet, payment_wallet, created_at, status,
             original_price, discount_code, discount_percent, final_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                user_id,
                network,
                amount,
                final_price,
                receive_wallet,
                WALLETS[network],
                int(time.time()),
                "pending",
                original_price,
                discount_code,
                discount_percent,
                final_price,
            ),
        )
        conn.commit()
    return order_id


def get_order(order_id):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ).fetchone()


def confirm_order(order_id, tx_hash):
    # Confirm payment and consume the discount code atomically.
    # A code is consumed only after a valid payment is found.
    with db() as conn:
        conn.execute("BEGIN IMMEDIATE")

        order = conn.execute(
            "SELECT * FROM orders WHERE id = ? AND status = 'pending'",
            (order_id,),
        ).fetchone()

        if not order:
            conn.rollback()
            return False

        if order["discount_code"]:
            result = conn.execute(
                """
                UPDATE discount_codes
                SET used = 1, used_by = ?, used_order_id = ?
                WHERE code = ? AND used = 0
                """,
                (
                    order["telegram_user_id"],
                    order_id,
                    order["discount_code"],
                ),
            )
            if result.rowcount != 1:
                conn.rollback()
                return False

        try:
            result = conn.execute(
                """
                UPDATE orders
                SET status = 'paid', tx_hash = ?
                WHERE id = ? AND status = 'pending'
                """,
                (tx_hash, order_id),
            )
            if result.rowcount != 1:
                conn.rollback()
                return False
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            conn.rollback()
            return False


def tx_already_used(tx_hash):
    with db() as conn:
        row = conn.execute(
            "SELECT id FROM orders WHERE tx_hash = ?",
            (tx_hash,),
        ).fetchone()
        return row is not None


def discount_code_status(code):
    # Exact, case-sensitive comparison. No lower()/upper()/strip().
    if code not in DISCOUNT_CODES:
        return "invalid", None

    with db() as conn:
        row = conn.execute(
            "SELECT percent, used FROM discount_codes WHERE code = ?",
            (code,),
        ).fetchone()

    if not row:
        return "invalid", None
    if row["used"]:
        return "used", None
    return "valid", int(row["percent"])


def discounted_price(price, percent):
    value = Decimal(price)
    final = (value * (Decimal(100) - Decimal(percent)) / Decimal(100)).quantize(
        Decimal("0.01")
    )
    return format(final, "f")


def price_display(price):
    value = Decimal(str(price))
    if value == value.to_integral():
        return f"{value:.0f}"
    return f"{value:.2f}"


# ============================================================
# أدوات الواجهة
# ============================================================

def main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🛒 شراء FLASH USDT", callback_data="buy")],
            [InlineKeyboardButton("💰 الأسعار والباقات", callback_data="prices")],
            [InlineKeyboardButton("🎁 العروض والخصومات", callback_data="offers")],
            [InlineKeyboardButton("ℹ️ ما هو FLASH USDT؟", callback_data="info")],
            [InlineKeyboardButton("🎟️ هل لديك كود خصم؟", callback_data="discount")],
        ]
    )


def home_button():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
    )


def network_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🟡 BEP20", callback_data="network:BEP20")],
            [InlineKeyboardButton("🔵 ERC20", callback_data="network:ERC20")],
            [InlineKeyboardButton("🔴 TRC20", callback_data="network:TRC20")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
        ]
    )


def package_keyboard(network):
    rows = []
    for amount, price in PACKAGES[network]:
        rows.append(
            [
                InlineKeyboardButton(
                    f"💰 {amount} FLASH USDT — {price}$",
                    callback_data=f"package:{network}:{amount}:{price}",
                )
            ]
        )
    rows += [
        [InlineKeyboardButton("🔙 العودة للشبكات", callback_data="buy")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ]
    return InlineKeyboardMarkup(rows)


# ============================================================
# التحقق من عناوين المحافظ
# ============================================================

EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
TRON_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")


def valid_wallet(network, address):
    address = address.strip()
    if network in ("BEP20", "ERC20"):
        return bool(EVM_RE.fullmatch(address))
    if network == "TRC20":
        return bool(TRON_RE.fullmatch(address))
    return False


# ============================================================
# التحقق من الدفع - EVM / Etherscan V2
# ============================================================

async def etherscan_transfers(chain_id, contract, wallet, min_ts):
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": str(chain_id),
        "module": "account",
        "action": "tokentx",
        "contractaddress": contract,
        "address": wallet,
        "startblock": "0",
        "endblock": "99999999",
        "sort": "desc",
        "apikey": ETHERSCAN_API_KEY,
    }

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params) as response:
            data = await response.json(content_type=None)

    if data.get("status") == "0" and data.get("message") not in ("No transactions found", "OK"):
        raise RuntimeError(f"Etherscan error: {data}")

    result = data.get("result", [])
    if not isinstance(result, list):
        return []

    return [
        tx for tx in result
        if int(tx.get("timeStamp", "0") or 0) >= min_ts
    ]


async def verify_evm(network, expected_amount, payment_wallet, created_at):
    if network == "BEP20":
        chain_id = 56
        contract = BEP20_USDT_CONTRACT
        decimals = 18
    else:
        chain_id = 1
        contract = ETH_USDT_CONTRACT
        decimals = 6

    transfers = await etherscan_transfers(
        chain_id,
        contract,
        payment_wallet,
        max(0, created_at - 30),
    )

    expected_raw = int(
        Decimal(expected_amount) * (Decimal(10) ** decimals)
    )

    matches = []

    for tx in transfers:
        if tx_already_used(tx.get("hash", "")):
            continue

        if tx.get("to", "").lower() != payment_wallet.lower():
            continue

        if tx.get("contractAddress", "").lower() != contract.lower():
            continue

        try:
            value = int(tx.get("value", "0"))
        except (TypeError, ValueError):
            continue

        if value != expected_raw:
            continue

        if int(tx.get("timeStamp", "0") or 0) < created_at:
            continue

        # A token transfer indexed by the explorer represents a token Transfer event.
        # Failed/reverted transactions normally do not produce a valid token transfer record.
        matches.append(tx)

    if len(matches) != 1:
        return None

    return matches[0].get("hash")


# ============================================================
# التحقق من الدفع - TRON / TronGrid
# ============================================================

async def verify_tron(expected_amount, payment_wallet, created_at):
    url = (
        f"https://api.trongrid.io/v1/accounts/"
        f"{payment_wallet}/transactions/trc20"
    )

    params = {
        "only_confirmed": "true",
        "only_to": "true",
        "limit": "200",
        "order_by": "block_timestamp,desc",
        "min_timestamp": str(max(0, (created_at - 30) * 1000)),
        "contract_address": TRON_USDT_CONTRACT,
    }

    headers = {
        "TRON-PRO-API-KEY": TRONGRID_API_KEY,
        "accept": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, params=params, headers=headers) as response:
            data = await response.json(content_type=None)

    transfers = data.get("data", [])

    matches = []

    for tx in transfers:
        tx_hash = tx.get("transaction_id", "")
        if not tx_hash or tx_already_used(tx_hash):
            continue

        if tx.get("to", "") != payment_wallet:
            continue

        if tx.get("token_info", {}).get("address") != TRON_USDT_CONTRACT:
            continue

        if tx.get("type") != "Transfer":
            continue

        try:
            decimals = int(tx.get("token_info", {}).get("decimals", 6))
            value = Decimal(tx.get("value", "0")) / (Decimal(10) ** decimals)
        except (InvalidOperation, TypeError, ValueError):
            continue

        if value != Decimal(expected_amount):
            continue

        if int(tx.get("block_timestamp", 0)) < created_at * 1000:
            continue

        if tx.get("success") is False:
            continue

        matches.append(tx_hash)

    if len(matches) != 1:
        return None

    return matches[0]


async def verify_payment(order):
    network = order["network"]

    if network in ("BEP20", "ERC20"):
        return await verify_evm(
            network,
            order["price"],
            order["payment_wallet"],
            order["created_at"],
        )

    if network == "TRC20":
        return await verify_tron(
            order["price"],
            order["payment_wallet"],
            order["created_at"],
        )

    return None


# ============================================================
# /start
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    if not update.message:
        return

    await update.message.reply_text(
        "👋 <b>أهلاً بك في متجر FLASH USDT</b>\n\n"
        "اختر من القائمة التالية 👇",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# ============================================================
# الرسائل النصية - محفظة الاستلام
# ============================================================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    # --------------------------------------------------------
    # إدخال كود الخصم
    # --------------------------------------------------------
    if context.user_data.get("awaiting_discount_code"):
        code = update.message.text

        # Exact, case-sensitive comparison. No lower()/upper()/strip().
        status, percent = discount_code_status(code)
        context.user_data.pop("awaiting_discount_code", None)

        if status == "invalid":
            await update.message.reply_text(
                "❌ <b>كود الخصم غير صحيح.</b>\n\n"
                "تأكد من إدخال الكود كما استلمته، مع مراعاة الأحرف الكبيرة والصغيرة.",
                parse_mode="HTML",
                reply_markup=home_button(),
            )
            return

        if status == "used":
            await update.message.reply_text(
                "❌ <b>كود الخصم مستخدم مسبقًا.</b>\n\n"
                "يرجى استخدام كود خصم آخر.",
                parse_mode="HTML",
                reply_markup=home_button(),
            )
            return

        context.user_data["discount_code"] = code
        context.user_data["discount_percent"] = percent

        await update.message.reply_text(
            "✅ <b>تم تفعيل كود الخصم بنجاح!</b>\n\n"
            f"🎟️ <b>الكود:</b> <code>{escape(code)}</code>\n"
            f"🎉 <b>نسبة الخصم:</b> {percent}%\n\n"
            "يمكنك الآن اختيار الباقة التي تريدها، وسيتم تطبيق الخصم على سعرها تلقائيًا.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🛒 شراء FLASH USDT", callback_data="buy")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ]
            ),
        )
        return

    # --------------------------------------------------------
    # إدخال محفظة الاستلام
    # --------------------------------------------------------
    network = context.user_data.get("awaiting_wallet_network")
    package = context.user_data.get("pending_package")

    if not network or not package:
        return

    wallet = update.message.text.strip()

    if not valid_wallet(network, wallet):
        await update.message.reply_text(
            f"❌ عنوان المحفظة غير صالح لشبكة {network}.\n\n"
            "يرجى إرسال عنوان صحيح ومتوافق مع الشبكة المختارة."
        )
        return

    amount, original_price = package

    discount_code = context.user_data.get("discount_code")
    discount_percent = int(context.user_data.get("discount_percent", 0) or 0)

    if discount_code:
        status, current_percent = discount_code_status(discount_code)
        if status != "valid":
            context.user_data.pop("discount_code", None)
            context.user_data.pop("discount_percent", None)
            await update.message.reply_text(
                "❌ <b>تعذر تطبيق كود الخصم.</b>\n\n"
                "قد يكون الكود مستخدمًا بالفعل أو غير صالح.",
                parse_mode="HTML",
                reply_markup=home_button(),
            )
            return
        discount_percent = current_percent

    final_price = discounted_price(original_price, discount_percent)

    order_id = create_order(
        update.effective_user.id,
        network,
        amount,
        original_price,
        wallet,
        discount_code,
        discount_percent,
        final_price,
    )

    context.user_data.pop("awaiting_wallet_network", None)
    context.user_data.pop("pending_package", None)
    context.user_data["order_id"] = order_id

    payment_wallet = WALLETS[network]
    price_text = price_display(original_price)
    final_price_text = price_display(final_price)

    discount_line = ""
    if discount_code:
        discount_line = (
            f"🎟️ <b>كود الخصم:</b> <code>{escape(discount_code)}</code>\n"
            f"🏷️ <b>الخصم:</b> {discount_percent}%\n"
            f"💵 <b>السعر بعد الخصم:</b> {final_price_text}$\n\n"
        )

    text = (
        "🧾 <b>تفاصيل الطلب</b>\n\n"
        "🪙 <b>المنتج:</b> FLASH USDT\n"
        f"🌐 <b>الشبكة:</b> {network}\n"
        f"💰 <b>الكمية:</b> {amount} FLASH USDT\n"
        f"💵 <b>السعر الأصلي:</b> {price_text}$\n"
        f"{discount_line}"
        f"💳 <b>مبلغ الدفع:</b> {final_price_text} USDT\n"
        f"🔸 <b>يجب إرسال {final_price_text} USDT عبر شبكة {network} فقط.</b>\n\n"
        "👛 <b>محفظة الاستلام:</b>\n"
        f"<code>{escape(wallet)}</code>\n\n"
        "💳 <b>عنوان الدفع:</b>\n"
        f"<code>{escape(payment_wallet)}</code>\n\n"
        f"⚠️ يرجى التأكد من اختيار شبكة <b>{network}</b> عند إجراء عملية الدفع."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔍 تحقق من الدفع", callback_data=f"verify:{order_id}")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
        ]
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )

# ============================================================
# الأزرار
# ============================================================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()
    data = query.data or ""

    if data == "home":
        saved_discount_code = context.user_data.get("discount_code")
        saved_discount_percent = context.user_data.get("discount_percent")
        context.user_data.clear()
        if saved_discount_code:
            context.user_data["discount_code"] = saved_discount_code
            context.user_data["discount_percent"] = saved_discount_percent
        await query.edit_message_text(
            "👋 <b>أهلاً بك في متجر FLASH USDT</b>\n\n"
            "اختر من القائمة التالية 👇",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return

    if data == "buy":
        saved_discount_code = context.user_data.get("discount_code")
        saved_discount_percent = context.user_data.get("discount_percent")
        context.user_data.clear()
        if saved_discount_code:
            context.user_data["discount_code"] = saved_discount_code
            context.user_data["discount_percent"] = saved_discount_percent
        await query.edit_message_text(
            "🛒 <b>شراء FLASH USDT</b>\n\n"
            "اختر الشبكة التي تريدها 👇",
            parse_mode="HTML",
            reply_markup=network_keyboard(),
        )
        return

    if data == "prices":
        await query.edit_message_text(
            "💰 <b>الأسعار والباقات</b>\n\n"
            "🟡 <b>BEP20</b>\n"
            "• 1500 FLASH USDT — 80$\n"
            "• 3000 FLASH USDT — 159$\n"
            "• 4500 FLASH USDT — 235$\n\n"
            "🔵 <b>ERC20</b>\n"
            "• 500 FLASH USDT — 92$\n"
            "• 1000 FLASH USDT — 182$\n\n"
            "🔴 <b>TRC20</b>\n"
            "• 1500 FLASH USDT — 350$",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🛒 شراء FLASH USDT", callback_data="buy")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ]
            ),
        )
        return

    if data == "offers":
        await query.edit_message_text(
            "🎁 <b>العروض والخصومات</b>\n\n"
            "لا توجد عروض أو خصومات متاحة حالياً.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🛒 شراء FLASH USDT", callback_data="buy")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ]
            ),
        )
        return

    if data == "info":
        info_content = FLASH_USDT_INFO.strip()

        if not info_content:
            info_text = (
                "ℹ️ <b>ما هو FLASH USDT؟</b>\n\n"
                "لم تتم إضافة محتوى هذا القسم بعد."
            )
        else:
            info_text = (
                "ℹ️ <b>ما هو FLASH USDT؟</b>\n\n"
                f"{escape(info_content)}"
            )

        await query.edit_message_text(
            info_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🛒 شراء FLASH USDT", callback_data="buy")],
                    [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                ]
            ),
        )
        return

    if data == "discount":
        context.user_data["awaiting_discount_code"] = True
        await query.edit_message_text(
            "🎟️ <b>هل لديك كود خصم؟</b>\n\n"
            "أرسل كود الخصم الآن كما استلمته، مع مراعاة الأحرف الكبيرة والصغيرة.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
            ),
        )
        return

    if data.startswith("network:"):
        network = data.split(":", 1)[1]

        if network not in PACKAGES:
            await query.answer("حدث خطأ.", show_alert=True)
            return

        await query.edit_message_text(
            f"🛒 <b>FLASH USDT — {network}</b>\n\n"
            "اختر الباقة المناسبة لك 👇",
            parse_mode="HTML",
            reply_markup=package_keyboard(network),
        )
        return

    if data.startswith("package:"):
        parts = data.split(":")
        if len(parts) != 4:
            await query.answer("حدث خطأ في الطلب.", show_alert=True)
            return

        _, network, amount, price = parts

        if network not in PACKAGES or not WALLETS.get(network):
            await query.answer("هذه الشبكة غير متاحة حالياً.", show_alert=True)
            return

        if (amount, price) not in PACKAGES[network]:
            await query.answer("هذه الباقة غير متاحة.", show_alert=True)
            return

        context.user_data["awaiting_wallet_network"] = network
        context.user_data["pending_package"] = (amount, price)

        await query.edit_message_text(
            "👛 <b>محفظة الاستلام</b>\n\n"
            "أرسل عنوان المحفظة التي تريد استلام FLASH USDT عليها.\n\n"
            f"تأكد من إدخال عنوان صحيح ومتوافق مع شبكة <b>{network}</b>.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]]
            ),
        )
        return

    if data.startswith("verify:"):
        order_id = data.split(":", 1)[1]
        order = get_order(order_id)

        if not order:
            await query.edit_message_text(
                "❌ لم يتم العثور على الطلب.",
                reply_markup=home_button(),
            )
            return

        if order["telegram_user_id"] != update.effective_user.id:
            await query.answer("هذا الطلب لا يخص حسابك.", show_alert=True)
            return

        if order["status"] == "paid":
            context.user_data.pop("discount_code", None)
            context.user_data.pop("discount_percent", None)
            await query.edit_message_text(
                "✅ <b>تم تأكيد الدفع بنجاح!</b>\n\n"
                f"💰 <b>الكمية:</b> {order['amount']} FLASH USDT\n\n"
                f"👛 <b>محفظة الاستلام:</b>\n"
                f"<code>{escape(order['receive_wallet'])}</code>\n\n"
                "سيتم إرسال طلبك خلال مدة لا تتجاوز <b>5 دقائق</b>.",
                parse_mode="HTML",
                reply_markup=home_button(),
            )
            return

        try:
            tx_hash = await verify_payment(order)
        except Exception:
            logger.exception("Payment verification failed for order %s", order_id)
            tx_hash = None

        if not tx_hash:
            await query.edit_message_text(
                "❌ <b>لم يتم العثور على عملية دفع مكتملة.</b>\n\n"
                "يرجى التأكد من إتمام التحويل ثم المحاولة مرة أخرى.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🔍 تحقق من الدفع", callback_data=f"verify:{order_id}")],
                        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
                    ]
                ),
            )
            return

        if not confirm_order(order_id, tx_hash):
            await query.edit_message_text(
                "❌ <b>تعذر تأكيد الطلب.</b>\n\n"
                "قد تكون عملية الدفع أو كود الخصم قد تم تأكيده مسبقًا.\n"
                "يرجى المحاولة مرة أخرى.",
                parse_mode="HTML",
                reply_markup=home_button(),
            )
            return

        context.user_data.pop("discount_code", None)
        context.user_data.pop("discount_percent", None)

        await query.edit_message_text(
            "✅ <b>تم تأكيد الدفع بنجاح!</b>\n\n"
            f"💰 <b>الكمية:</b> {order['amount']} FLASH USDT\n\n"
            f"👛 <b>محفظة الاستلام:</b>\n"
            f"<code>{escape(order['receive_wallet'])}</code>\n\n"
            "سيتم إرسال طلبك خلال مدة لا تتجاوز <b>5 دقائق</b>.",
            parse_mode="HTML",
            reply_markup=home_button(),
        )
        return


# ============================================================
# الأخطاء
# ============================================================

async def error_handler(update, context):
    logger.exception(
        "Unhandled exception while processing an update",
        exc_info=context.error,
    )


# ============================================================
# Webhook
# ============================================================

async def telegram_webhook(request: web.Request):
    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if incoming != WEBHOOK_SECRET:
            return web.Response(status=403, text="Forbidden")

    application = request.app["telegram_app"]

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)

        if update:
            await application.update_queue.put(update)

        return web.Response(text="OK")

    except Exception:
        logger.exception("Failed to process Telegram webhook update")
        return web.Response(status=500, text="Internal Server Error")


async def health_check(request):
    return web.Response(
        text="FLASH USDT Bot is running.",
        content_type="text/plain",
    )


# ============================================================
# التشغيل
# ============================================================

async def main():
    init_db()

    telegram_app: Application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .updater(None)
        .build()
    )

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )
    telegram_app.add_handler(CallbackQueryHandler(button_handler))
    telegram_app.add_error_handler(error_handler)

    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = f"{WEBHOOK_URL}/webhook"

    await telegram_app.bot.set_webhook(
        url=webhook_url,
        secret_token=WEBHOOK_SECRET or None,
        allowed_updates=Update.ALL_TYPES,
    )

    logger.info("Webhook configured: %s", webhook_url)

    web_app = web.Application()
    web_app["telegram_app"] = telegram_app

    web_app.router.add_get("/", health_check)
    web_app.router.add_post("/webhook", telegram_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()

    site = web.TCPSite(
        runner,
        host="0.0.0.0",
        port=PORT,
    )
    await site.start()

    logger.info("Web server started on port %s", PORT)

    try:
        await asyncio.Event().wait()
    finally:
        await telegram_app.bot.delete_webhook()
        await telegram_app.stop()
        await telegram_app.shutdown()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

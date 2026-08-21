import asyncio
import logging
import os
from html import escape

from aiohttp import web
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)


# =========================
# الإعدادات
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
PORT = int(os.getenv("PORT", "10000"))

SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")

BEP20_WALLET_ADDRESS = os.getenv("BEP20_WALLET_ADDRESS", "").strip()
ERC20_WALLET_ADDRESS = os.getenv("ERC20_WALLET_ADDRESS", "").strip()
TRC20_WALLET_ADDRESS = os.getenv("TRC20_WALLET_ADDRESS", "").strip()

OFFERS_TEXT = os.getenv(
    "OFFERS_TEXT",
    "🎁 <b>العروض والخصومات</b>\n\n"
    "لا توجد خصومات أو عروض متاحة حاليًا.\n\n"
    "تابعنا باستمرار لمعرفة أحدث العروض 🔥",
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

if not WEBHOOK_URL:
    raise RuntimeError("WEBHOOK_URL is not set")

if not SUPPORT_USERNAME:
    raise RuntimeError("SUPPORT_USERNAME is not set")


# =========================
# السجل
# =========================

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# البيانات والأسعار
# =========================

PACKAGES = {
    "BEP20": [
        ("500", "20"),
        ("1000", "40"),
        ("1500", "55"),
    ],
    "ERC20": [
        ("500", "24"),
        ("1000", "48"),
        ("1500", "67"),
    ],
    "TRC20": [
        ("1000", "120"),
        ("1500", "150"),
    ],
}

WALLETS = {
    "BEP20": BEP20_WALLET_ADDRESS,
    "ERC20": ERC20_WALLET_ADDRESS,
    "TRC20": TRC20_WALLET_ADDRESS,
}


# =========================
# لوحة الأزرار الرئيسية
# =========================

def main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(
                "🛒 شراء FLASH USDT",
                callback_data="buy",
            ),
        ],
        [
            InlineKeyboardButton(
                "🎁 العروض والخصومات",
                callback_data="offers",
            ),
        ],
        [
            InlineKeyboardButton(
                "💰 الأسعار والباقات",
                callback_data="prices",
            ),
        ],
        [
            InlineKeyboardButton(
                "📞 الدعم",
                url=f"https://t.me/{SUPPORT_USERNAME}",
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# أزرار الرجوع
# =========================

def back_to_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                ),
            ],
        ]
    )


def back_to_networks() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔙 العودة للشبكات",
                    callback_data="buy",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                ),
            ],
        ]
    )


# =========================
# رسالة البداية
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.message:
        return

    text = (
        "👋 <b>مرحبًا بك في متجر FLASH USDT</b>\n\n"
        "يمكنك من خلال البوت الاطلاع على الأسعار والباقات "
        "وإتمام عملية الشراء والتواصل مع الدعم.\n\n"
        "اختر من القائمة التالية 👇"
    )

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu(),
    )


# =========================
# التعامل مع الأزرار
# =========================

async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query

    if not query:
        return

    await query.answer()

    data = query.data

    # -------------------------
    # الرئيسية
    # -------------------------

    if data == "home":
        text = (
            "👋 <b>مرحبًا بك في متجر FLASH USDT</b>\n\n"
            "يمكنك من خلال البوت الاطلاع على الأسعار والباقات "
            "وإتمام عملية الشراء والتواصل مع الدعم.\n\n"
            "اختر من القائمة التالية 👇"
        )

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        return

    # -------------------------
    # شراء
    # -------------------------

    if data == "buy":
        keyboard = [
            [
                InlineKeyboardButton(
                    "🟡 FLASH USDT — BEP20",
                    callback_data="network:BEP20",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔵 FLASH USDT — ERC20",
                    callback_data="network:ERC20",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔴 FLASH USDT — TRC20",
                    callback_data="network:TRC20",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                ),
            ],
        ]

        await query.edit_message_text(
            "🛒 <b>شراء FLASH USDT</b>\n\n"
            "اختر الشبكة التي تريدها 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # -------------------------
    # اختيار الشبكة
    # -------------------------

    if data.startswith("network:"):
        network = data.split(":", 1)[1]

        if network not in PACKAGES:
            await query.answer("حدث خطأ، يرجى المحاولة مرة أخرى.", show_alert=True)
            return

        buttons = []

        for amount, price in PACKAGES[network]:
            buttons.append(
                [
                    InlineKeyboardButton(
                        f"💰 {amount} FLASH USDT — ${price}",
                        callback_data=f"package:{network}:{amount}:{price}",
                    ),
                ]
            )

        buttons.append(
            [
                InlineKeyboardButton(
                    "🔙 العودة للشبكات",
                    callback_data="buy",
                ),
            ]
        )

        buttons.append(
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                ),
            ]
        )

        await query.edit_message_text(
            f"🛒 <b>شراء FLASH USDT — {network}</b>\n\n"
            "اختر الباقة المناسبة لك 👇",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    # -------------------------
    # اختيار الباقة
    # -------------------------

    if data.startswith("package:"):
        parts = data.split(":")

        if len(parts) != 4:
            await query.answer("حدث خطأ في الباقة.", show_alert=True)
            return

        _, network, amount, price = parts

        wallet_address = WALLETS.get(network, "")

        if not wallet_address:
            logger.error("Wallet address for %s is not configured", network)

            await query.answer(
                "هذه الخدمة غير متاحة حاليًا. يرجى التواصل مع الدعم.",
                show_alert=True,
            )
            return

        safe_wallet = escape(wallet_address)

        text = (
            "🧾 <b>تفاصيل طلبك</b>\n\n"
            "🪙 <b>التوكن:</b> FLASH USDT\n"
            f"🌐 <b>الشبكة:</b> {network}\n"
            f"💰 <b>الكمية:</b> {amount} FLASH USDT\n"
            f"💵 <b>المبلغ المطلوب:</b> ${price}\n\n"
            "💳 <b>أرسل المبلغ إلى عنوان المحفظة التالي:</b>\n\n"
            f"<code>{safe_wallet}</code>\n\n"
            f"⚠️ تأكد من استخدام شبكة <b>{network}</b> عند الدفع.\n\n"
            "📸 <b>بعد نجاح التحويل، خذ لقطة شاشة واضحة "
            "لعملية الدفع واحتفظ بها.</b>\n\n"
            "بعد إتمام التحويل، اضغط على زر «تم الدفع» 👇"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "✅ تم الدفع",
                    callback_data=f"paid:{network}:{amount}:{price}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 العودة للباقات",
                    callback_data=f"network:{network}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                ),
            ],
        ]

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # -------------------------
    # تم الدفع
    # -------------------------

    if data.startswith("paid:"):
        parts = data.split(":")

        if len(parts) != 4:
            await query.answer("حدث خطأ، يرجى المحاولة مرة أخرى.", show_alert=True)
            return

        _, network, amount, price = parts

        text = (
            "✅ <b>شكرًا لتأكيد عملية الدفع</b>\n\n"
            "الخطوة التالية:\n\n"
            "📩 تواصل مع حساب الدعم وأرسل <b>لقطة شاشة واضحة "
            "تثبت نجاح عملية التحويل</b>.\n\n"
            "ويُفضّل أن ترسل أيضًا المعلومات التالية:\n"
            f"• الشبكة: {network}\n"
            f"• الكمية: {amount} FLASH USDT\n"
            f"• المبلغ: ${price}\n\n"
            "سيتم متابعة عملية الشراء من خلال الدعم."
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "💬 التواصل مع الدعم",
                    url=f"https://t.me/{SUPPORT_USERNAME}",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 العودة للرئيسية",
                    callback_data="home",
                ),
            ],
        ]

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # -------------------------
    # العروض والخصومات
    # -------------------------

    if data == "offers":
        await query.edit_message_text(
            OFFERS_TEXT,
            parse_mode="HTML",
            reply_markup=back_to_main(),
        )
        return

    # -------------------------
    # الأسعار والباقات
    # -------------------------

    if data == "prices":
        text = (
            "💰 <b>أسعار وباقات FLASH USDT</b>\n\n"
            "🟡 <b>BEP20</b>\n"
            "• 500 FLASH USDT — $20\n"
            "• 1000 FLASH USDT — $40\n"
            "• 1500 FLASH USDT — $55\n\n"
            "🔵 <b>ERC20</b>\n"
            "• 500 FLASH USDT — $24\n"
            "• 1000 FLASH USDT — $48\n"
            "• 1500 FLASH USDT — $67\n\n"
            "🔴 <b>TRC20</b>\n"
            "• 1000 FLASH USDT — $120\n"
            "• 1500 FLASH USDT — $150"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🛒 شراء FLASH USDT",
                    callback_data="buy",
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏠 الرئيسية",
                    callback_data="home",
                ),
            ],
        ]

        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return


# =========================
# معالجة أخطاء البوت
# =========================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.exception(
        "Unhandled exception while processing an update",
        exc_info=context.error,
    )


# =========================
# Webhook
# =========================

async def telegram_webhook(
    request: web.Request,
) -> web.Response:
    application: Application = request.app["telegram_app"]

    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)

        if update:
            await application.update_queue.put(update)

        return web.Response(text="OK")

    except Exception:
        logger.exception("Failed to process Telegram webhook update")
        return web.Response(status=500, text="Internal Server Error")


# =========================
# الصفحة الرئيسية للسيرفر
# =========================

async def health_check(
    request: web.Request,
) -> web.Response:
    return web.Response(
        text="FLASH USDT Bot is running.",
        content_type="text/plain",
    )


# =========================
# تشغيل السيرفر والبوت
# =========================

async def main() -> None:
    telegram_app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .updater(None)
        .build()
    )

    telegram_app.add_handler(
        CommandHandler("start", start)
    )

    telegram_app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    telegram_app.add_error_handler(
        error_handler
    )

    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = f"{WEBHOOK_URL}/webhook"

    await telegram_app.bot.set_webhook(
        url=webhook_url,
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
        logger.info("Shutting down...")

        await telegram_app.bot.delete_webhook()

        await telegram_app.stop()
        await telegram_app.shutdown()

        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())

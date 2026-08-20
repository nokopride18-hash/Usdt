import os
import logging

from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_WALLET = os.getenv("PAYMENT_WALLET")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

CONTACT_USERNAME = "@Jnoooooooooooop"

PORT = int(os.getenv("PORT", "10000"))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)


PACKAGES = {
    "bep20": {
        "title": "🟡 USDT BEP20",
        "options": [
            ("500 USDT BEP20 — $20", "500 USDT", "$20"),
            ("1000 USDT BEP20 — $40", "1000 USDT", "$40"),
            ("1500 USDT BEP20 — $59", "1500 USDT", "$59"),
        ],
    },
    "erc20": {
        "title": "🔵 USDT ERC20",
        "options": [
            ("500 USDT ERC20 — $30", "500 USDT", "$30"),
            ("1000 USDT ERC20 — $60", "1000 USDT", "$60"),
            ("1500 USDT ERC20 — $89", "1500 USDT", "$89"),
        ],
    },
    "trc20": {
        "title": "🔴 USDT TRC20",
        "options": [
            ("500 USDT TRC20 — $60", "500 USDT", "$60"),
            ("1000 USDT TRC20 — $120", "1000 USDT", "$120"),
            ("1500 USDT TRC20 — $179", "1500 USDT", "$179"),
        ],
    },
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💰 شراء USDT", callback_data="buy")]
    ]

    await update.message.reply_text(
        "👋 أهلاً بك في متجر USDT\n\nاختر الخدمة التي تريدها:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.callback_query

    if query is None:
        return

    await query.answer()

    data = query.data

    if data == "buy":
        keyboard = [
            [InlineKeyboardButton("🟡 USDT BEP20", callback_data="network:bep20")],
            [InlineKeyboardButton("🔵 USDT ERC20", callback_data="network:erc20")],
            [InlineKeyboardButton("🔴 USDT TRC20", callback_data="network:trc20")],
        ]

        await query.edit_message_text(
            "💰 اختر شبكة USDT:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("network:"):
        network = data.split(":", 1)[1]
        package = PACKAGES.get(network)

        if package is None:
            await query.edit_message_text(
                "❌ حدث خطأ. أعد تشغيل البوت باستخدام /start."
            )
            return

        keyboard = []

        for index, option in enumerate(package["options"]):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        option[0],
                        callback_data=f"order:{network}:{index}",
                    )
                ]
            )

        await query.edit_message_text(
            f"{package['title']}\n\nاختر الباقة:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("order:"):
        try:
            _, network, index_text = data.split(":", 2)
            index = int(index_text)

            package = PACKAGES[network]
            label, amount, price = package["options"][index]

        except (KeyError, ValueError, IndexError):
            await query.edit_message_text(
                "❌ حدث خطأ في الطلب.\n\nأعد تشغيل البوت باستخدام /start."
            )
            return

        context.user_data["order"] = {
            "network": network.upper(),
            "amount": amount,
            "price": price,
        }

        wallet_text = PAYMENT_WALLET

        if not wallet_text:
            wallet_text = "سيتم إضافة عنوان المحفظة لاحقاً."

        keyboard = [
            [InlineKeyboardButton("💳 تم الدفع", callback_data="paid")]
        ]

        await query.edit_message_text(
            f"🛒 طلبك: {label}\n\n"
            f"💵 المبلغ المطلوب دفعه: {price}\n\n"
            "💳 أرسل المبلغ إلى عنوان المحفظة التالي:\n\n"
            f"`{wallet_text}`\n\n"
            "⚠️ تأكد من إرسال المبلغ الصحيح وعلى الشبكة المطلوبة.\n"
            "بعد الدفع اضغط على زر «تم الدفع».",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    if data == "paid":
        order = context.user_data.get("order")

        order_text = ""

        if order:
            order_text = (
                "\n\n🛒 طلبك:\n"
                f"{order['amount']} {order['network']}\n"
                f"💵 السعر: {order['price']}"
            )

        await query.edit_message_text(
            "📩 تم تسجيل طلبك بانتظار التحقق من الدفع.\n\n"
            "راسل هذه الجهة الآن وأرسل إثبات الدفع:\n\n"
            f"{CONTACT_USERNAME}"
            f"{order_text}"
        )
        return


async def health(request):
    return web.Response(text="Bot is running")


async def telegram_webhook(request):
    app = request.app["telegram_app"]

    try:
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.update_queue.put(update)

        return web.Response(text="OK")

    except Exception:
        logging.exception("Webhook error")
        return web.Response(status=500, text="Error")


async def on_startup(app):
    telegram_app = app["telegram_app"]

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود.")

    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL غير موجود.")

    await telegram_app.initialize()
    await telegram_app.start()

    await telegram_app.bot.set_webhook(
        url=f"{WEBHOOK_URL}/webhook",
        allowed_updates=Update.ALL_TYPES,
    )

    logging.info("Webhook started successfully")


async def on_shutdown(app):
    telegram_app = app["telegram_app"]

    await telegram_app.bot.delete_webhook()

    await telegram_app.stop()
    await telegram_app.shutdown()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN غير موجود.")

    if not WEBHOOK_URL:
        raise RuntimeError("WEBHOOK_URL غير موجود.")

    telegram_app = (
        Application.builder()
        .token(BOT_TOKEN)
        .updater(None)
        .build()
    )

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(
        CallbackQueryHandler(button_handler)
    )

    web_app = web.Application()

    web_app["telegram_app"] = telegram_app

    web_app.router.add_get("/", health)
    web_app.router.add_get("/health", health)
    web_app.router.add_post("/webhook", telegram_webhook)

    web_app.on_startup.append(on_startup)
    web_app.on_shutdown.append(on_shutdown)

    web.run_app(
        web_app,
        host="0.0.0.0",
        port=PORT,
    )


if __name__ == "__main__":
    main()

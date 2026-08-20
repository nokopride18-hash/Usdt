import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_WALLET = os.getenv("PAYMENT_WALLET")

CONTACT_USERNAME = "@Jnoooooooooooop"


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
        [
            InlineKeyboardButton(
                "💰 شراء USDT",
                callback_data="buy"
            )
        ]
    ]

    await update.message.reply_text(
        "👋 أهلاً بك في متجر USDT\n\n"
        "اختر الخدمة التي تريدها:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query

    if query is None:
        return

    await query.answer()

    data = query.data

    # القائمة الرئيسية
    if data == "buy":

        keyboard = [
            [
                InlineKeyboardButton(
                    "🟡 USDT BEP20",
                    callback_data="network:bep20"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔵 USDT ERC20",
                    callback_data="network:erc20"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔴 USDT TRC20",
                    callback_data="network:trc20"
                )
            ],
        ]

        await query.edit_message_text(
            "💰 اختر شبكة USDT:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return


    # اختيار الشبكة
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

            label = option[0]

            keyboard.append(
                [
                    InlineKeyboardButton(
                        label,
                        callback_data=f"order:{network}:{index}"
                    )
                ]
            )

        await query.edit_message_text(
            f"{package['title']}\n\n"
            "اختر الباقة:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return


    # اختيار الباقة
    if data.startswith("order:"):

        try:

            _, network, index_text = data.split(":", 2)

            index = int(index_text)

            package = PACKAGES[network]

            label, amount, price = package["options"][index]

        except (
            KeyError,
            ValueError,
            IndexError,
        ):

            await query.edit_message_text(
                "❌ حدث خطأ في الطلب.\n\n"
                "أعد تشغيل البوت باستخدام /start."
            )
            return


        # حفظ الطلب مؤقتاً للمستخدم
        context.user_data["order"] = {
            "network": network.upper(),
            "amount": amount,
            "price": price,
        }


        keyboard = [
            [
                InlineKeyboardButton(
                    "💳 تم الدفع",
                    callback_data="paid"
                )
            ]
        ]


        # إذا لم نضف المحفظة بعد
        wallet_text = PAYMENT_WALLET

        if not wallet_text:
            wallet_text = "سيتم إضافة عنوان المحفظة لاحقاً."


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


    # المستخدم ضغط تم الدفع
    if data == "paid":

        order = context.user_data.get("order")

        order_text = ""

        if order:

            order_text = (
                "\n\n"
                "🛒 طلبك:\n"
                f"{order['amount']} {order['network']}\n"
                f"💵 السعر: {order['price']}"
            )


        await query.edit_message_text(
            "✅ تم تسجيل طلبك كمدفوع.\n\n"
            "📩 راسل هذه الجهة الآن وأرسل إثبات الدفع:\n\n"
            f"{CONTACT_USERNAME}"
            f"{order_text}"
        )
        return


    # في حال وصول أمر غير معروف
    await query.edit_message_text(
        "❌ خيار غير معروف.\n\n"
        "أعد تشغيل البوت باستخدام /start."
    )


def main():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN غير موجود. "
            "أضفه كمتغير بيئة على Render."
        )


    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )


    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    app.add_handler(
        CallbackQueryHandler(
            button_handler
        )
    )


    print("Bot is running...")


    app.run_polling()


if __name__ == "__main__":
    main()

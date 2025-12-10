import logging
import json
import os
from datetime import datetime, timedelta
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Bot token
BOT_TOKEN = "8502291504:AAHlvLEFMV_kV8XIMRPkyU3tbQGStKD7pSM"

# SUPERADMIN ID
ADMIN_ID = 5296554946

# VIP foydalanuvchilar (anonim xabarni kim yozganini ko'radi, lekin admin emas)
VIP_USERNAMES = ["Nf0506"]  # @ belgisisiz

# Bot holati
bot_active = True

# Ma'lumotlar fayli
DATA_FILE = "bot_data.json"

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ma'lumotlar bazasi
users_data = {}
pending_questions = {}
all_messages = []


def save_data():
    """Ma'lumotlarni faylga saqlash"""
    data = {
        "users_data": {},
        "all_messages": all_messages
    }
    # users_data ni saqlash (datetime ni string ga o'girish)
    for uid, udata in users_data.items():
        user_copy = udata.copy()
        if user_copy.get("premium_expires"):
            user_copy["premium_expires"] = user_copy["premium_expires"].isoformat()
        data["users_data"][str(uid)] = user_copy

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_data():
    """Ma'lumotlarni fayldan yuklash"""
    global users_data, all_messages

    if not os.path.exists(DATA_FILE):
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # users_data ni yuklash (string dan datetime ga o'girish)
        for uid, udata in data.get("users_data", {}).items():
            if udata.get("premium_expires"):
                udata["premium_expires"] = datetime.fromisoformat(udata["premium_expires"])
            users_data[int(uid)] = udata

        all_messages = data.get("all_messages", [])
        logger.info(f"Ma'lumotlar yuklandi: {len(users_data)} foydalanuvchi, {len(all_messages)} xabar")
    except Exception as e:
        logger.error(f"Ma'lumotlarni yuklashda xato: {e}")

# Premium narxlari
PREMIUM_PRICES = {
    "1_day": {"name": "1 kunlik", "price": "5,000", "days": 1, "emoji": "⚡"},
    "3_day": {"name": "3 kunlik", "price": "10,000", "days": 3, "emoji": "🔥"},
    "1_week": {"name": "1 haftalik", "price": "19,000", "days": 7, "emoji": "⭐"},
    "1_month": {"name": "1 oylik", "price": "39,000", "days": 30, "emoji": "💎"},
    "3_month": {"name": "3 oylik", "price": "89,000", "days": 90, "emoji": "👑"},
    "lifetime": {"name": "Umrbod", "price": "149,000", "days": 36500, "emoji": "🏆"}
}


def get_admin_keyboard():
    """Admin uchun pastki tugmalar"""
    keyboard = [
        [KeyboardButton("👥 Foydalanuvchilar"), KeyboardButton("📨 Xabarlar")],
        [KeyboardButton("📢 Hammaga xabar"), KeyboardButton("📊 Statistika")],
        [KeyboardButton("👑 Premium berish")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_user_keyboard():
    """Oddiy foydalanuvchi uchun pastki tugma"""
    keyboard = [
        [KeyboardButton("👑 Premium olish")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def is_premium(user_id):
    """Foydalanuvchi premium ekanligini tekshirish"""
    if user_id not in users_data:
        return False

    user = users_data[user_id]
    if not user.get("premium"):
        return False

    # Muddatli premium
    expires = user.get("premium_expires")
    if expires and datetime.now() < expires:
        return True

    return False


def is_vip(user_id):
    """Foydalanuvchi VIP ekanligini tekshirish (username bo'yicha)"""
    if user_id not in users_data:
        return False

    username = users_data[user_id].get("username")
    if username and username.lower() in [v.lower() for v in VIP_USERNAMES]:
        return True

    return False


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start buyrug'i"""
    global bot_active
    user = update.effective_user
    args = context.args

    # Foydalanuvchini ro'yxatga olish
    if user.id not in users_data:
        users_data[user.id] = {
            "username": user.username,
            "first_name": user.first_name,
            "questions_received": 0,
            "premium": False,
            "premium_type": None,
            "premium_expires": None
        }
        save_data()

    # Agar link orqali kelgan bo'lsa
    if args and args[0].startswith("q_"):
        if not bot_active and user.id != ADMIN_ID:
            await update.message.reply_text("Bot hozircha ishlamayapti. Keyinroq urinib ko'ring.")
            return

        target_user_id = int(args[0][2:])

        if target_user_id == user.id:
            await update.message.reply_text("Ozingizga savol yubora olmaysiz!")
            return

        if target_user_id not in users_data:
            await update.message.reply_text("Foydalanuvchi topilmadi!")
            return

        pending_questions[user.id] = {"to_user": target_user_id, "waiting": True}

        await update.message.reply_text("Xabaringizni shu yerga yozing:")
        return

    # Oddiy start
    bot_username = (await context.bot.get_me()).username
    user_link = f"https://t.me/{bot_username}?start=q_{user.id}"

    # Admin uchun
    if user.id == ADMIN_ID:
        status_text = "YOQILGAN" if bot_active else "OCHIRILGAN"

        inline_keyboard = [
            [InlineKeyboardButton("📤 Linkni ulashish", url=f"https://t.me/share/url?url={user_link}&text=Menga anonim savol yuboring!")]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard)

        await update.message.reply_text(
            f"Salom, {user.first_name}! [ADMIN]\n\n"
            f"Bot holati: {status_text}\n"
            f"Foydalanuvchilar: {len(users_data)}\n"
            f"Xabarlar: {len(all_messages)}\n\n"
            f"Sizning linkingiz:\n{user_link}",
            reply_markup=get_admin_keyboard()
        )
        await update.message.reply_text("Linkni ulashish:", reply_markup=inline_markup)
    else:
        # Oddiy foydalanuvchi uchun
        premium_status = ""
        if is_premium(user.id):
            expires = users_data[user.id].get("premium_expires")
            if expires:
                premium_status = f"\n👑 Premium: {expires.strftime('%d.%m.%Y %H:%M')} gacha"

        inline_keyboard = [
            [InlineKeyboardButton("📤 Linkni ulashish", url=f"https://t.me/share/url?url={user_link}&text=Menga anonim savol yuboring!")]
        ]
        inline_markup = InlineKeyboardMarkup(inline_keyboard)

        await update.message.reply_text(
            f"Salom, {user.first_name}!\n\n"
            f"Sizning anonim savol linkingiz:\n{user_link}\n\n"
            f"Bu linkni do'stlaringizga yuboring!{premium_status}",
            reply_markup=get_user_keyboard()
        )
        await update.message.reply_text("Linkni ulashish:", reply_markup=inline_markup)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xabarlarni qayta ishlash"""
    global bot_active
    user = update.effective_user
    message = update.message
    text = message.text

    # Foydalanuvchini ro'yxatga olish
    if user.id not in users_data:
        users_data[user.id] = {
            "username": user.username,
            "first_name": user.first_name,
            "questions_received": 0,
            "premium": False,
            "premium_type": None,
            "premium_expires": None
        }
        save_data()

    # ===== ADMIN TUGMALARI =====
    if user.id == ADMIN_ID:

        # Foydalanuvchilar
        if text == "👥 Foydalanuvchilar":
            if not users_data:
                await message.reply_text("Foydalanuvchilar yoq.")
                return

            result = "=== FOYDALANUVCHILAR ===\n\n"
            for uid, udata in list(users_data.items())[:20]:
                name = udata.get('first_name', 'Nomalum')
                username = udata.get('username')
                questions = udata.get('questions_received', 0)
                premium_badge = "👑" if is_premium(uid) else ""

                if username:
                    user_link = f"<a href='https://t.me/{username}'>{name}</a> (@{username})"
                else:
                    user_link = f"<a href='tg://user?id={uid}'>{name}</a>"

                result += f"• {premium_badge}{user_link}\n  ID: {uid} | Savollar: {questions}\n\n"

            await message.reply_text(result, parse_mode="HTML")
            return

        # Xabarlar
        if text == "📨 Xabarlar":
            if not all_messages:
                await message.reply_text("Xabarlar yoq.")
                return

            result = "=== OXIRGI XABARLAR ===\n\n"
            for msg in all_messages[-10:]:
                from_info = f"@{msg['from_username']}" if msg['from_username'] else f"ID:{msg['from_id']}"
                result += f"👤 {msg['from_name']} ({from_info})\n"
                result += f"➡️ {msg['to_name']}\n"
                result += f"💬 {msg['text'][:100]}\n\n"

            await message.reply_text(result)
            return

        # Statistika
        if text == "📊 Statistika":
            status = "Yoqilgan" if bot_active else "O'chirilgan"
            premium_count = sum(1 for uid in users_data if is_premium(uid))
            result = f"=== STATISTIKA ===\n\n"
            result += f"👥 Foydalanuvchilar: {len(users_data)}\n"
            result += f"👑 Premium userlar: {premium_count}\n"
            result += f"📨 Xabarlar: {len(all_messages)}\n"
            result += f"🤖 Bot holati: {status}"
            await message.reply_text(result)
            return

        # Hammaga xabar
        if text == "📢 Hammaga xabar":
            users_data[user.id]["broadcasting"] = True
            await message.reply_text(
                "📢 Hammaga yuboriladigan xabarni yozing:\n\n"
                "Bekor qilish uchun /cancel yozing."
            )
            return

        # Premium berish
        if text == "👑 Premium berish":
            users_data[user.id]["giving_premium"] = True
            await message.reply_text(
                "👑 Premium berish uchun foydalanuvchi ID sini yuboring:\n\n"
                "Bekor qilish uchun /cancel yozing."
            )
            return

        # Premium berish jarayoni
        if users_data.get(user.id, {}).get("giving_premium"):
            try:
                target_id = int(text)
                users_data[user.id]["premium_target"] = target_id
                del users_data[user.id]["giving_premium"]

                keyboard = [
                    [InlineKeyboardButton("⚡ 1 kunlik", callback_data=f"give_premium_{target_id}_1_day")],
                    [InlineKeyboardButton("🔥 3 kunlik", callback_data=f"give_premium_{target_id}_3_day")],
                    [InlineKeyboardButton("⭐ 1 haftalik", callback_data=f"give_premium_{target_id}_1_week")],
                    [InlineKeyboardButton("💎 1 oylik", callback_data=f"give_premium_{target_id}_1_month")],
                    [InlineKeyboardButton("👑 3 oylik", callback_data=f"give_premium_{target_id}_3_month")],
                    [InlineKeyboardButton("🏆 Umrbod", callback_data=f"give_premium_{target_id}_lifetime")],
                    [InlineKeyboardButton("❌ Bekor", callback_data="cancel_give_premium")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                target_name = users_data.get(target_id, {}).get("first_name", "Noma'lum")
                await message.reply_text(
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    "      👑 PREMIUM BERISH 👑\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"👤 Foydalanuvchi: {target_name}\n"
                    f"🆔 ID: {target_id}\n\n"
                    "⬇️ Tarifni tanlang:",
                    reply_markup=reply_markup
                )
            except ValueError:
                await message.reply_text("❌ Noto'g'ri ID. Raqam kiriting.")
            return

        # Broadcast xabari
        if users_data.get(user.id, {}).get("broadcasting"):
            del users_data[user.id]["broadcasting"]

            sent_count = 0
            for uid in users_data.keys():
                if uid != ADMIN_ID:
                    try:
                        await context.bot.send_message(
                            chat_id=uid,
                            text=f"📢 Admin xabari:\n\n{text}"
                        )
                        sent_count += 1
                    except:
                        pass

            await message.reply_text(f"Xabar {sent_count} ta foydalanuvchiga yuborildi!")
            return

    # Oddiy foydalanuvchi premium tugmasi
    if text == "👑 Premium olish" and user.id != ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton(f"⚡ 1 kunlik - 5,000 so'm", callback_data="buy_premium_1_day")],
            [InlineKeyboardButton(f"🔥 3 kunlik - 10,000 so'm", callback_data="buy_premium_3_day")],
            [InlineKeyboardButton(f"⭐ 1 haftalik - 19,000 so'm", callback_data="buy_premium_1_week")],
            [InlineKeyboardButton(f"💎 1 oylik - 39,000 so'm", callback_data="buy_premium_1_month")],
            [InlineKeyboardButton(f"👑 3 oylik - 89,000 so'm", callback_data="buy_premium_3_month")],
            [InlineKeyboardButton(f"🏆 UMRBOD - 149,000 so'm", callback_data="buy_premium_lifetime")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "         👑 PREMIUM OBUNA 👑\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔓 Premium imkoniyatlari:\n"
            "├ ✅ Savolni kim yozganini ko'rish\n"
            "├ ✅ Foydalanuvchi username va ismi\n"
            "└ ✅ Profilga havola\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "         💰 NARXLAR 💰\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ 1 kunlik     ➜  5,000 so'm\n"
            "🔥 3 kunlik     ➜  10,000 so'm\n"
            "⭐ 1 haftalik   ➜  19,000 so'm\n"
            "💎 1 oylik      ➜  39,000 so'm\n"
            "👑 3 oylik      ➜  89,000 so'm\n"
            "🏆 UMRBOD       ➜  149,000 so'm\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⬇️ Kerakli tarifni tanlang:",
            reply_markup=reply_markup
        )
        return

    # Bot o'chirilgan bo'lsa
    if not bot_active and user.id != ADMIN_ID:
        await message.reply_text("Bot hozircha ishlamayapti. Keyinroq urinib ko'ring.")
        return

    # Agar foydalanuvchi savol yubormoqda bo'lsa
    if user.id in pending_questions and pending_questions[user.id]["waiting"]:
        target_user_id = pending_questions[user.id]["to_user"]

        # Xabarni tarixga saqlash
        message_data = {
            "from_id": user.id,
            "from_username": user.username,
            "from_name": user.first_name,
            "to_id": target_user_id,
            "to_name": users_data.get(target_user_id, {}).get("first_name", "Noma'lum"),
            "text": text
        }
        all_messages.append(message_data)
        save_data()

        # Qabul qiluvchi premium, VIP yoki admin ekanligini tekshirish
        target_is_premium = is_premium(target_user_id)
        target_is_admin = (target_user_id == ADMIN_ID)
        target_is_vip = is_vip(target_user_id)

        # Yuboruvchi haqida ma'lumot
        if user.username:
            sender_link = f"<a href='https://t.me/{user.username}'>{user.first_name}</a> (@{user.username})"
        else:
            sender_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a> (ID: {user.id})"

        # Qabul qiluvchiga yuborish - har bir tugma noyob bo'lishi uchun vaqt qo'shamiz
        unique_id = int(time.time() * 1000)
        keyboard = [
            [InlineKeyboardButton("Javob yozish", callback_data=f"reply_{user.id}_{unique_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            # Admin, Premium yoki VIP foydalanuvchiga kim yozganini ko'rsatish
            if target_is_admin or target_is_premium or target_is_vip:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"📩 Yangi anonim savol:\n\n{text}\n\n"
                         f"👤 Kimdan: {sender_link}",
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
            else:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"📩 Yangi anonim savol:\n\n{text}",
                    reply_markup=reply_markup
                )

            if target_user_id in users_data:
                users_data[target_user_id]["questions_received"] += 1
                save_data()

            await message.reply_text("Savolingiz anonim tarzda yuborildi!")

            # ADMINGA XABAR
            if ADMIN_ID and ADMIN_ID != target_user_id:
                # Yuboruvchi linki
                if user.username:
                    sender_link = f"<a href='https://t.me/{user.username}'>{user.first_name}</a> (@{user.username})"
                else:
                    sender_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a> (ID: {user.id})"

                # Qabul qiluvchi linki
                target_data = users_data.get(target_user_id, {})
                target_name = target_data.get("first_name", "Noma'lum")
                target_username = target_data.get("username")
                if target_username:
                    target_link = f"<a href='https://t.me/{target_username}'>{target_name}</a> (@{target_username})"
                else:
                    target_link = f"<a href='tg://user?id={target_user_id}'>{target_name}</a> (ID: {target_user_id})"

                admin_keyboard = [
                    [InlineKeyboardButton("👑 Premium berish", callback_data=f"quick_premium_{user.id}")],
                    [InlineKeyboardButton("🚫 Bloklash", callback_data=f"block_{user.id}")]
                ]
                admin_reply_markup = InlineKeyboardMarkup(admin_keyboard)

                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"📬 Yangi savol:\n\n"
                         f"👤 Kimdan: {sender_link}\n"
                         f"👤 Kimga: {target_link}\n"
                         f"💬 Xabar: {text}",
                    reply_markup=admin_reply_markup,
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Xabar yuborishda xato: {e}")
            await message.reply_text("Xabar yuborishda xatolik yuz berdi.")

        del pending_questions[user.id]
        return

    # Agar foydalanuvchi javob yozmoqda bo'lsa
    if user.id in users_data and "replying_to" in users_data[user.id]:
        sender_id = users_data[user.id]["replying_to"]

        # Javobga ham "Javob berish" tugmasi qo'shamiz
        unique_id = int(time.time() * 1000)
        reply_keyboard = [
            [InlineKeyboardButton("Javob yozish", callback_data=f"reply_{user.id}_{unique_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(reply_keyboard)

        try:
            await context.bot.send_message(
                chat_id=sender_id,
                text=f"💬 Savolingizga javob keldi:\n\n{text}",
                reply_markup=reply_markup
            )
            await message.reply_text("Javobingiz yuborildi!")

            # ADMINGA LOG
            if ADMIN_ID:
                # Javob beruvchi linki
                if user.username:
                    from_link = f"<a href='https://t.me/{user.username}'>{user.first_name}</a> (@{user.username})"
                else:
                    from_link = f"<a href='tg://user?id={user.id}'>{user.first_name}</a> (ID: {user.id})"

                # Savol yuborgan linki
                sender_data = users_data.get(sender_id, {})
                sender_name = sender_data.get("first_name", "Noma'lum")
                sender_username = sender_data.get("username")
                if sender_username:
                    to_link = f"<a href='https://t.me/{sender_username}'>{sender_name}</a> (@{sender_username})"
                else:
                    to_link = f"<a href='tg://user?id={sender_id}'>{sender_name}</a> (ID: {sender_id})"

                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"📬 Javob:\n\n"
                         f"👤 Kimdan: {from_link}\n"
                         f"👤 Kimga: {to_link}\n"
                         f"💬 Javob: {text}",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Javob yuborishda xato: {e}")
            await message.reply_text("Javob yuborishda xatolik.")

        del users_data[user.id]["replying_to"]
        return

    # Boshqa xabarlar
    await message.reply_text(
        "Buyruqlar:\n"
        "/start - Link olish\n"
        "/help - Yordam"
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback query"""
    query = update.callback_query
    user = query.from_user
    data = query.data

    await query.answer()

    # Premium menu
    if data == "premium_menu":
        keyboard = [
            [InlineKeyboardButton(f"⚡ 1 kunlik - 5,000 so'm", callback_data="buy_premium_1_day")],
            [InlineKeyboardButton(f"🔥 3 kunlik - 10,000 so'm", callback_data="buy_premium_3_day")],
            [InlineKeyboardButton(f"⭐ 1 haftalik - 19,000 so'm", callback_data="buy_premium_1_week")],
            [InlineKeyboardButton(f"💎 1 oylik - 39,000 so'm", callback_data="buy_premium_1_month")],
            [InlineKeyboardButton(f"👑 3 oylik - 89,000 so'm", callback_data="buy_premium_3_month")],
            [InlineKeyboardButton(f"🏆 UMRBOD - 149,000 so'm", callback_data="buy_premium_lifetime")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "         👑 PREMIUM OBUNA 👑\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🔓 Premium imkoniyatlari:\n"
            "├ ✅ Savolni kim yozganini ko'rish\n"
            "├ ✅ Foydalanuvchi username va ismi\n"
            "└ ✅ Profilga havola\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "         💰 NARXLAR 💰\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "⚡ 1 kunlik     ➜  5,000 so'm\n"
            "🔥 3 kunlik     ➜  10,000 so'm\n"
            "⭐ 1 haftalik   ➜  19,000 so'm\n"
            "💎 1 oylik      ➜  39,000 so'm\n"
            "👑 3 oylik      ➜  89,000 so'm\n"
            "🏆 UMRBOD       ➜  149,000 so'm\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⬇️ Kerakli tarifni tanlang:",
            reply_markup=reply_markup
        )
        return

    # Premium sotib olish - admin bilan bog'lanish
    if data.startswith("buy_premium_"):
        premium_type = data.replace("buy_premium_", "")

        premium_info = PREMIUM_PRICES.get(premium_type, {})
        premium_name = premium_info.get("name", "Noma'lum")
        premium_price = premium_info.get("price", "0")
        premium_emoji = premium_info.get("emoji", "👑")

        keyboard = [
            [InlineKeyboardButton("📞 Admin bilan bog'lanish", url="https://t.me/Cyber_Security_A7")],
            [InlineKeyboardButton("🔙 Orqaga", callback_data="premium_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"      {premium_emoji} PREMIUM SOTIB OLISH {premium_emoji}\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 Tanlangan tarif: {premium_name}\n"
            f"💰 Narxi: {premium_price} so'm\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📱 TO'LOV USULI:\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "1️⃣ Admin bilan bog'laning\n"
            "2️⃣ Tarifni ayting\n"
            "3️⃣ To'lovni amalga oshiring\n"
            "4️⃣ Premium aktivlashtiriladi\n\n"
            "━━━━━━━━━━━━━━━━━━━━━",
            reply_markup=reply_markup
        )
        return

    # Premium tasdiqlash (admin)
    if data.startswith("approve_premium_") and user.id == ADMIN_ID:
        parts = data.split("_")
        target_id = int(parts[2])
        premium_type = "_".join(parts[3:])

        if target_id not in users_data:
            users_data[target_id] = {
                "username": None,
                "first_name": "Noma'lum",
                "questions_received": 0,
                "premium": False,
                "premium_type": None,
                "premium_expires": None
            }

        users_data[target_id]["premium"] = True
        users_data[target_id]["premium_type"] = premium_type

        premium_info = PREMIUM_PRICES.get(premium_type, {"days": 1, "name": "1 kunlik"})
        days = premium_info.get("days", 1)
        users_data[target_id]["premium_expires"] = datetime.now() + timedelta(days=days)
        save_data()

        premium_name = premium_info.get("name", "Premium")
        expires_date = users_data[target_id]["premium_expires"].strftime("%d.%m.%Y %H:%M")

        # Foydalanuvchiga xabar
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="━━━━━━━━━━━━━━━━━━━━━\n"
                     "   🎉 TABRIKLAYMIZ! 🎉\n"
                     "━━━━━━━━━━━━━━━━━━━━━\n\n"
                     "✅ Premium muvaffaqiyatli aktivlashtirildi!\n\n"
                     f"📦 Tarif: {premium_name}\n"
                     f"📅 Amal qilish: {expires_date} gacha\n\n"
                     "🔓 Endi siz anonim savollarni kim yozganini ko'rishingiz mumkin!"
            )
        except:
            pass

        await query.message.edit_text(f"✅ Premium tasdiqlandi!\n👤 ID: {target_id}\n📦 Tarif: {premium_name}")
        return

    # Premium rad etish (admin)
    if data.startswith("reject_premium_") and user.id == ADMIN_ID:
        target_id = int(data.split("_")[2])

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="❌ Premium so'rovingiz rad etildi."
            )
        except:
            pass

        await query.message.edit_text(f"❌ Premium rad etildi. (ID: {target_id})")
        return

    # Admin premium berish
    if data.startswith("give_premium_") and user.id == ADMIN_ID:
        parts = data.split("_")
        target_id = int(parts[2])
        premium_type = "_".join(parts[3:])

        if target_id not in users_data:
            users_data[target_id] = {
                "username": None,
                "first_name": "Noma'lum",
                "questions_received": 0,
                "premium": False,
                "premium_type": None,
                "premium_expires": None
            }

        users_data[target_id]["premium"] = True
        users_data[target_id]["premium_type"] = premium_type

        premium_info = PREMIUM_PRICES.get(premium_type, {"days": 1, "name": "1 kunlik"})
        days = premium_info.get("days", 1)
        users_data[target_id]["premium_expires"] = datetime.now() + timedelta(days=days)
        save_data()

        premium_name = premium_info.get("name", "Premium")
        premium_emoji = premium_info.get("emoji", "👑")
        expires_date = users_data[target_id]["premium_expires"].strftime("%d.%m.%Y %H:%M")

        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="━━━━━━━━━━━━━━━━━━━━━\n"
                     "   🎉 TABRIKLAYMIZ! 🎉\n"
                     "━━━━━━━━━━━━━━━━━━━━━\n\n"
                     "✅ Premium muvaffaqiyatli aktivlashtirildi!\n\n"
                     f"{premium_emoji} Tarif: {premium_name}\n"
                     f"📅 Amal qilish: {expires_date} gacha\n\n"
                     "🔓 Endi siz anonim savollarni kim yozganini ko'rishingiz mumkin!"
            )
        except:
            pass

        target_name = users_data.get(target_id, {}).get("first_name", "Noma'lum")
        await query.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "   ✅ PREMIUM BERILDI ✅\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Foydalanuvchi: {target_name}\n"
            f"🆔 ID: {target_id}\n"
            f"{premium_emoji} Tarif: {premium_name}\n"
            f"📅 Gacha: {expires_date}"
        )
        return

    if data == "cancel_give_premium":
        await query.message.edit_text("Bekor qilindi.")
        return

    # Tezkor premium berish (xabardan)
    if data.startswith("quick_premium_") and user.id == ADMIN_ID:
        target_id = int(data.split("_")[2])

        keyboard = [
            [InlineKeyboardButton("⚡ 1 kunlik", callback_data=f"give_premium_{target_id}_1_day")],
            [InlineKeyboardButton("🔥 3 kunlik", callback_data=f"give_premium_{target_id}_3_day")],
            [InlineKeyboardButton("⭐ 1 haftalik", callback_data=f"give_premium_{target_id}_1_week")],
            [InlineKeyboardButton("💎 1 oylik", callback_data=f"give_premium_{target_id}_1_month")],
            [InlineKeyboardButton("👑 3 oylik", callback_data=f"give_premium_{target_id}_3_month")],
            [InlineKeyboardButton("🏆 Umrbod", callback_data=f"give_premium_{target_id}_lifetime")],
            [InlineKeyboardButton("❌ Bekor", callback_data="cancel_give_premium")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        target_name = users_data.get(target_id, {}).get("first_name", "Noma'lum")
        await query.message.edit_text(
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "      👑 PREMIUM BERISH 👑\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Foydalanuvchi: {target_name}\n"
            f"🆔 ID: {target_id}\n\n"
            "⬇️ Tarifni tanlang:",
            reply_markup=reply_markup
        )
        return

    # Orqaga qaytish
    if data == "back_to_start":
        bot_username = (await context.bot.get_me()).username
        user_link = f"https://t.me/{bot_username}?start=q_{user.id}"

        premium_status = ""
        if is_premium(user.id):
            expires = users_data[user.id].get("premium_expires")
            if expires:
                premium_status = f"\n👑 Premium: {expires.strftime('%d.%m.%Y %H:%M')} gacha"

        keyboard = [
            [InlineKeyboardButton("📤 Linkni ulashish", url=f"https://t.me/share/url?url={user_link}&text=Menga anonim savol yuboring!")],
            [InlineKeyboardButton("👑 Premium", callback_data="premium_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            f"Sizning anonim savol linkingiz:\n{user_link}\n\n"
            f"Bu linkni do'stlaringizga yuboring!{premium_status}",
            reply_markup=reply_markup
        )
        return

    # Javob yozish
    if data.startswith("reply_"):
        parts = data.split("_")
        sender_id = int(parts[1])  # reply_USERID_UNIQUEID formatidan faqat USERID ni olamiz

        if user.id not in users_data:
            users_data[user.id] = {
                "username": user.username,
                "first_name": user.first_name,
                "questions_received": 0,
                "premium": False,
                "premium_type": None,
                "premium_expires": None
            }

        users_data[user.id]["replying_to"] = sender_id
        await query.message.reply_text("Javobingizni yozing:")
        return

    # Bloklash (admin)
    if data.startswith("block_") and user.id == ADMIN_ID:
        blocked_id = int(data.split("_")[1])
        if blocked_id in users_data:
            del users_data[blocked_id]
        if blocked_id in pending_questions:
            del pending_questions[blocked_id]
        await query.message.reply_text(f"Foydalanuvchi {blocked_id} bloklandi!")
        return


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bekor qilish"""
    user = update.effective_user
    if user.id in users_data:
        if "broadcasting" in users_data[user.id]:
            del users_data[user.id]["broadcasting"]
        if "giving_premium" in users_data[user.id]:
            del users_data[user.id]["giving_premium"]
    await update.message.reply_text("Bekor qilindi.", reply_markup=get_admin_keyboard() if user.id == ADMIN_ID else None)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yordam"""
    await update.message.reply_text(
        "Anonim Savol-Javob Bot\n\n"
        "Buyruqlar:\n"
        "/start - Botni ishga tushirish\n"
        "/help - Yordam\n\n"
        "Qanday ishlaydi:\n"
        "1. /start bosing va linkingizni oling\n"
        "2. Linkni dostlaringizga yuboring\n"
        "3. Ular sizga anonim savollar yuboradi\n"
        "4. Siz javob yozishingiz mumkin\n\n"
        "👑 Premium bilan kim yozganini ko'ring!"
    )


async def set_commands(application):
    """Menu buyruqlarini sozlash"""
    commands = [
        BotCommand("start", "Botni ishga tushirish"),
        BotCommand("cancel", "Bekor qilish"),
        BotCommand("help", "Yordam")
    ]
    await application.bot.set_my_commands(commands)


def main():
    """Botni ishga tushirish"""
    # Ma'lumotlarni yuklash
    load_data()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.post_init = set_commands

    print("Bot ishga tushdi...")
    print(f"Admin ID: {ADMIN_ID}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

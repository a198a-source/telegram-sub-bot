
# Telegram Subscription Bot (Manual UPI + Auto Expiry)
# Install: pip install python-telegram-bot==21.6 aiosqlite
# Run: python bot.py

import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ==========================
# CONFIG (EDIT THESE)
# ==========================
BOT_TOKEN = "8627626550:AAGqR10bjvkkbfE01chwV3NvCU2D0DclnOA"
ADMIN_USERNAME = "Gucu686p7"   # without @
UPI_ID = "Q273417373@ybl"

# IMPORTANT:
# Replace with your PRIVATE CHANNEL ID after adding bot as admin.
# Example: -1001234567890
CHANNEL_ID = -1000000000000

CHANNEL_INVITE_LINK = "https://t.me/+TJ1Aqp1ejhBiMTk1"

PLANS = {
    "1_day": ("1 Day", 10, 1),
    "7_days": ("7 Days", 19, 7),
    "1_month": ("1 Month", 29, 30),
    "1_year": ("1 Year", 99, 365),
    "permanent": ("Permanent", 199, None),
}

logging.basicConfig(level=logging.INFO)

db = sqlite3.connect("subscriptions.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS subscriptions(
user_id INTEGER PRIMARY KEY,
username TEXT,
plan_key TEXT,
expiry TEXT,
permanent INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS pending_payments(
user_id INTEGER PRIMARY KEY,
username TEXT,
plan_key TEXT
)
""")
db.commit()


def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("₹10 • 1 Day", callback_data="1_day")],
        [InlineKeyboardButton("₹19 • 7 Days", callback_data="7_days")],
        [InlineKeyboardButton("₹29 • 1 Month", callback_data="1_month")],
        [InlineKeyboardButton("₹99 • 1 Year", callback_data="1_year")],
        [InlineKeyboardButton("₹199 • Permanent", callback_data="permanent")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎓 *UPSC Subscription Bot*\n\n"
        "Choose a subscription plan:"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard())


async def plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    plan_key = q.data
    name, price, _ = PLANS[plan_key]

    cur.execute(
        "INSERT OR REPLACE INTO pending_payments(user_id, username, plan_key) VALUES (?, ?, ?)",
        (q.from_user.id, q.from_user.username or "", plan_key)
    )
    db.commit()

    msg = (
        f"🧾 *Selected Plan:* {name}\n"
        f"💰 Amount: ₹{price}\n\n"
        f"Pay to UPI ID:\n`{UPI_ID}`\n\n"
        "After payment, send payment screenshot or UTR number in this chat."
    )
    await q.message.reply_text(msg, parse_mode="Markdown")


async def receive_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    cur.execute("SELECT plan_key FROM pending_payments WHERE user_id=?", (user.id,))
    row = cur.fetchone()

    if not row:
        await update.message.reply_text("Please choose a plan first using /start")
        return

    plan_key = row[0]
    plan_name, price, _ = PLANS[plan_key]

    admin_text = (
        f"💳 Payment Request\n\n"
        f"User: @{user.username or 'NoUsername'}\n"
        f"User ID: {user.id}\n"
        f"Plan: {plan_name}\n"
        f"Amount: ₹{price}\n\n"
        f"Approve:\n/approve_{user.id}\n"
        f"Reject:\n/reject_{user.id}"
    )

    # forward screenshot/text to admin
    try:
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            await context.bot.send_photo(chat_id=f"@{ADMIN_USERNAME}", photo=file_id, caption=admin_text)
        else:
            txt = update.message.text or "No text"
            await context.bot.send_message(chat_id=f"@{ADMIN_USERNAME}", text=admin_text + f"\n\nUTR/Text: {txt}")
    except Exception as e:
        await update.message.reply_text(f"Admin notification failed: {e}")
        return

    await update.message.reply_text("✅ Payment submitted. Wait for admin approval.")


async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.username
    if admin != ADMIN_USERNAME:
        return

    try:
        user_id = int(update.message.text.split("_")[1])
    except:
        await update.message.reply_text("Invalid command.")
        return

    cur.execute("SELECT username, plan_key FROM pending_payments WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        await update.message.reply_text("No pending payment found.")
        return

    username, plan_key = row
    _, _, days = PLANS[plan_key]

    permanent = 1 if days is None else 0
    expiry = None if permanent else (datetime.utcnow() + timedelta(days=days)).isoformat()

    cur.execute("""
    INSERT OR REPLACE INTO subscriptions(user_id, username, plan_key, expiry, permanent)
    VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, plan_key, expiry, permanent))

    cur.execute("DELETE FROM pending_payments WHERE user_id=?", (user_id,))
    db.commit()

    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Payment approved! Join your channel:\n{CHANNEL_INVITE_LINK}"
    )

    await update.message.reply_text("Approved successfully.")


async def reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = update.effective_user.username
    if admin != ADMIN_USERNAME:
        return

    try:
        user_id = int(update.message.text.split("_")[1])
    except:
        return

    cur.execute("DELETE FROM pending_payments WHERE user_id=?", (user_id,))
    db.commit()

    await context.bot.send_message(chat_id=user_id, text="❌ Payment rejected.")
    await update.message.reply_text("Rejected.")


async def auto_remove(context: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow()

    cur.execute("SELECT user_id, expiry FROM subscriptions WHERE permanent=0")
    rows = cur.fetchall()

    for user_id, expiry in rows:
        if not expiry:
            continue

        exp = datetime.fromisoformat(expiry)
        if now >= exp:
            try:
                await context.bot.ban_chat_member(CHANNEL_ID, user_id)
                await context.bot.unban_chat_member(CHANNEL_ID, user_id)
            except Exception:
                pass

            cur.execute("DELETE FROM subscriptions WHERE user_id=?", (user_id,))
            db.commit()

            try:
                await context.bot.send_message(
                    user_id,
                    "⛔ Your subscription expired and access was removed."
                )
            except:
                pass


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(plan_selected))
    app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, receive_payment))
    app.add_handler(MessageHandler(filters.Regex(r"^/approve_\d+$"), approve))
    app.add_handler(MessageHandler(filters.Regex(r"^/reject_\d+$"), reject))

    app.job_queue.run_repeating(auto_remove, interval=3600, first=30)

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()

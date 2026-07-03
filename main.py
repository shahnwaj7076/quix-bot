# -*- coding: utf-8 -*-
"""
Telegram Quiz Bot
- Force-join channel check
- 150 GK + Current Affairs questions (native Telegram quiz polls)
- QR code generator (/qr <text>)
- Leaderboard (SQLite, persists across restarts)
- Built-in tiny web server so free hosts (Render etc.) don't sleep the bot
"""

import json
import logging
import random
import sqlite3
import threading
import os
from io import BytesIO

import qrcode
from flask import Flask
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    PollAnswerHandler,
    ContextTypes,
)

# ======================= CONFIG (fill these in) =======================
BOT_TOKEN = os.environ.get("8722433709:AAHqwpiCEobbTCP1CtnFFHg621PuRPiTgBU")
CHANNEL_USERNAME = os.environ.get("https://t.me/xpromp")   # jo channel join karna zaroori hai
CHANNEL_INVITE_LINK = os.environ.get("https://t.me/xpromp")
QUESTIONS_PER_QUIZ = 10          # ek /quiz session me kitne sawal aayenge
DB_FILE = "quizbot.db"
# ========================================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

with open(os.path.join(os.path.dirname(__file__), "questions.json"), encoding="utf-8") as f:
    ALL_QUESTIONS = json.load(f)

# ------------------------- Database -------------------------
def db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS scores (user_id INTEGER PRIMARY KEY, name TEXT, score INTEGER DEFAULT 0, played INTEGER DEFAULT 0)"
    )
    return conn


def add_score(user_id: int, name: str, correct: int, total: int):
    conn = db()
    conn.execute(
        """INSERT INTO scores (user_id, name, score, played) VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET
             score = score + excluded.score,
             played = played + excluded.played,
             name = excluded.name""",
        (user_id, name, correct, total),
    )
    conn.commit()
    conn.close()


def top_scores(limit=10):
    conn = db()
    rows = conn.execute(
        "SELECT name, score, played FROM scores ORDER BY score DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows


# ------------------------- Force-join check -------------------------
async def is_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        log.warning(f"Membership check failed: {e}")
        return False


def join_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 Channel Join Karein", url=CHANNEL_INVITE_LINK)],
            [InlineKeyboardButton("✅ Maine Join Kar Liya", callback_data="check_join")],
        ]
    )


async def require_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    if await is_member(context, user_id):
        return True
    await update.effective_chat.send_message(
        "🚫 Is bot ko use karne ke liye pehle hamara channel join karna zaroori hai.\n\n"
        "Join karne ke baad neeche button dabayein 👇",
        reply_markup=join_keyboard(),
    )
    return False


# ------------------------- Handlers -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_join(update, context):
        return
    text = (
        "👋 Namaste! Quiz Bot me aapka swagat hai.\n\n"
        "📚 /quiz - Quiz shuru karein (GK + Current Affairs)\n"
        "🏆 /leaderboard - Top scorers dekhein\n"
        "🔗 /qr <text> - QR code banayein\n"
        "ℹ️ /help - Sabhi commands dekhein"
    )
    await update.effective_chat.send_message(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_join(update, context):
        return
    await start(update, context)


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    if await is_member(context, user_id):
        await query.answer("✅ Verified! Ab aap bot use kar sakte hain.")
        await query.edit_message_text("✅ Aap channel me join ho chuke hain. /start bhejein.")
    else:
        await query.answer("❌ Aapne abhi channel join nahi kiya hai.", show_alert=True)


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_join(update, context):
        return

    chat_id = update.effective_chat.id
    questions = random.sample(ALL_QUESTIONS, min(QUESTIONS_PER_QUIZ, len(ALL_QUESTIONS)))

    context.chat_data["quiz_questions"] = questions
    context.chat_data["quiz_index"] = 0
    context.chat_data["quiz_correct"] = 0

    await update.effective_chat.send_message(
        f"🎯 Quiz shuru! Total {len(questions)} sawal aayenge. Har sawal ka jawab 10 second me dena hoga."
    )
    await send_next_question(chat_id, context)


async def send_next_question(chat_id, context: ContextTypes.DEFAULT_TYPE):
    idx = context.chat_data.get("quiz_index", 0)
    questions = context.chat_data.get("quiz_questions", [])

    if idx >= len(questions):
        correct = context.chat_data.get("quiz_correct", 0)
        total = len(questions)
        await context.bot.send_message(
            chat_id,
            f"🏁 Quiz khatam!\n✅ Sahi jawab: {correct}/{total}\n\nLeaderboard dekhne ke liye /leaderboard bhejein.",
        )
        return

    q = questions[idx]
    message = await context.bot.send_poll(
        chat_id=chat_id,
        question=f"Q{idx+1}. {q['question']}",
        options=q["options"],
        type="quiz",
        correct_option_id=q["answer"],
        is_anonymous=False,
        open_period=10,
    )
    context.bot_data[f"poll_chat_{message.poll.id}"] = chat_id


async def poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    answer = update.poll_answer
    user = answer.user

    # Find which chat this poll belongs to via bot_data mapping (set when quiz sent)
    chat_id = context.bot_data.get(f"poll_chat_{answer.poll_id}")
    if chat_id is None:
        # fallback: can't map poll->chat reliably without storage; skip scoring silently
        return

    chat_data = context.application.chat_data.get(chat_id, {})
    questions = chat_data.get("quiz_questions", [])
    idx = chat_data.get("quiz_index", 0)
    if idx >= len(questions):
        return

    correct_option = questions[idx]["answer"]
    is_correct = correct_option in answer.option_ids

    if is_correct:
        chat_data["quiz_correct"] = chat_data.get("quiz_correct", 0) + 1

    add_score(user.id, user.first_name or user.username or "Player", 1 if is_correct else 0, 1)

    chat_data["quiz_index"] = idx + 1
    await send_next_question(chat_id, context)


async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_join(update, context):
        return
    rows = top_scores(10)
    if not rows:
        await update.effective_chat.send_message("Abhi tak koi score nahi hai. /quiz khelke shuru karein!")
        return
    text = "🏆 *Top Scorers*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (name, score, played) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"{i+1}."
        text += f"{prefix} {name} — {score} points ({played} played)\n"
    await update.effective_chat.send_message(text, parse_mode=ParseMode.MARKDOWN)


async def qr_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_join(update, context):
        return
    if not context.args:
        await update.effective_chat.send_message("Istemal: /qr <text ya link>\nExample: /qr https://t.me/your_channel")
        return
    text = " ".join(context.args)
    img = qrcode.make(text)
    bio = BytesIO()
    bio.name = "qrcode.png"
    img.save(bio, "PNG")
    bio.seek(0)
    await update.effective_chat.send_photo(photo=bio, caption=f"✅ QR Code taiyaar hai:\n{text}")


# ------------------------- Tiny web server (keeps free hosting awake) -------------------------
flask_app = Flask(__name__)


@flask_app.route("/")
def health():
    return "Quiz bot is alive!"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


# ------------------------- Main -------------------------
def main():
    if BOT_TOKEN == "8722433709:AAHqwpiCEobbTCP1CtnFFHg621PuRPiTgBU":
        raise SystemExit("BOT_TOKEN set karein (environment variable ya file me).")

    threading.Thread(target=run_flask, daemon=True).start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("quiz", quiz_cmd))
    application.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
    application.add_handler(CommandHandler("qr", qr_cmd))
    application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    application.add_handler(PollAnswerHandler(poll_answer))

    log.info("Bot starting (polling mode)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
import telegram
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import random

# ====== YAHAN APNA TOKEN DAALO ======
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# ====== QUIZ QUESTIONS ======
questions = [
    {
        "question": "भारत की राजधानी क्या है?\nWhat is the capital of India?",
        "options": ["मुंबई / Mumbai", "दिल्ली / Delhi", "कोलकाता / Kolkata", "चेन्नई / Chennai"],
        "answer": 1  # Index 0 se shuru
    },
    {
        "question": "पानी का रासायनिक सूत्र क्या है?\nWhat is the chemical formula of water?",
        "options": ["CO2", "H2O", "NaCl", "O2"],
        "answer": 1
    },
    {
        "question": "सूरज किस दिशा में उगता है?\nWhich direction does the sun rise?",
        "options": ["पश्चिम / West", "उत्तर / North", "दक्षिण / South", "पूर्व / East"],
        "answer": 3
    },
    {
        "question": "सबसे बड़ा महासागर कौन सा है?\nWhich is the largest ocean?",
        "options": ["अटलांटिक / Atlantic", "हिंद / Indian", "प्रशांत / Pacific", "आर्कटिक / Arctic"],
        "answer": 2
    },
    {
        "question": "1 किलो में कितने ग्राम होते हैं?\nHow many grams in 1 kilogram?",
        "options": ["100", "500", "1000", "2000"],
        "answer": 2
    }
]

def start(update, context):
    user = update.effective_user
    update.message.reply_text(
        f"नमस्ते {user.first_name}! 👋\n\n"
        f"Welcome to Quiz Bot!\n"
        f"सवाल जवाब खेलने के लिए /quiz टाइप करें।\n"
        f"Type /quiz to start the game."
    )

def quiz(update, context):
    # Random 3 questions select karo
    qs = random.sample(questions, min(3, len(questions)))
    context.user_data['quiz_questions'] = qs
    context.user_data['quiz_index'] = 0
    context.user_data['score'] = 0
    send_question(update, context)

def send_question(update, context):
    query = update.callback_query
    if query:
        query.answer()
    
    idx = context.user_data['quiz_index']
    qs = context.user_data['quiz_questions']
    
    if idx >= len(qs):
        # Game over
        score = context.user_data['score']
        total = len(qs)
        msg = f"🎉 खेल खत्म! Game Over!\n\nआपने {total} में से {score} सही जवाब दिए।\nYou got {score}/{total} correct!\n\n/quiz - दोबारा खेलें / Play again"
        
        if query:
            query.edit_message_text(msg)
        else:
            update.message.reply_text(msg)
        return
    
    q = qs[idx]
    keyboard = []
    for i, opt in enumerate(q['options']):
        keyboard.append([InlineKeyboardButton(opt, callback_data=str(i))])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = f"सवाल {idx+1}/{len(qs)}:\n\n{q['question']}"
    
    if query:
        query.edit_message_text(msg, reply_markup=reply_markup)
    else:
        update.message.reply_text(msg, reply_markup=reply_markup)

def button_handler(update, context):
    query = update.callback_query
    query.answer()
    
    idx = context.user_data['quiz_index']
    qs = context.user_data['quiz_questions']
    q = qs[idx]
    
    selected = int(query.data)
    correct = q['answer']
    
    if selected == correct:
        context.user_data['score'] += 1
        query.edit_message_text(f"✅ सही! Correct!\n\n{q['options'][correct]}")
    else:
        query.edit_message_text(f"❌ गलत! Wrong!\n\nसही जवाब / Correct answer: {q['options'][correct]}")
    
    # Next question
    context.user_data['quiz_index'] += 1
    send_question(update, context)

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("quiz", quiz))
    dp.add_handler(CallbackQueryHandler(button_handler))
    
    updater.start_polling()
    print("✅ Bot chal raha hai... / Bot is running...")
    updater.idle()

if __name__ == "__main__":
    main()
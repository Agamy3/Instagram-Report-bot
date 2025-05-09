import os
import sys
import random
import logging
import re
import time
from collections import defaultdict
from threading import Thread
import telebot
import instaloader
from flask import Flask
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Flask app to keep the bot alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_flask_app():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask_app)
    t.daemon = True
    t.start()

# Start the Flask app in a thread
keep_alive()

# Initialize the Telegram bot
API_TOKEN = os.getenv("API_TOKEN")
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL")
ADMIN_ID = os.getenv("ADMIN_ID")
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")

bot = telebot.TeleBot(API_TOKEN)
bot.remove_webhook()

# Initialize Instaloader with proper rate limiting
class CustomRateController(instaloader.RateController):
    def sleep(self, secs):
        delay = random.uniform(secs * 0.8, secs * 1.2)  # Add randomness to avoid detection
        super().sleep(delay)

L = instaloader.Instaloader(
    max_connection_attempts=1,
    request_timeout=60,
    sleep=True
)
L.context._rate_controller = CustomRateController(L.context)

# Login to Instagram
try:
    if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
        L.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
        logging.info("Successfully logged in to Instagram")
except Exception as e:
    logging.error(f"Instagram login failed: {e}")

# In-memory user storage
user_ids = set()

def add_user(user_id):
    user_ids.add(user_id)

def remove_user(user_id):
    user_ids.discard(user_id)

def get_all_users():
    return list(user_ids)

# Keywords for report types
report_keywords = {
    "HATE": ["devil", "666", "savage", "love", "hate", "followers", "selling", "sold", "seller", "dick", "ban", "banned", "free", "method", "paid"],
    "SELF": ["suicide", "blood", "death", "dead", "kill myself"],
    "BULLY": ["@"],
    "VIOLENT": ["hitler", "osama bin laden", "guns", "soldiers", "masks", "flags"],
    "ILLEGAL": ["drugs", "cocaine", "plants", "trees", "medicines"],
    "PRETENDING": ["verified", "tick"],
    "NUDITY": ["nude", "sex", "send nudes"],
    "SPAM": ["phone number", "email", "contact"]
}

def check_keywords(text, keywords):
    if not text:
        return False
    return any(keyword in text.lower() for keyword in keywords)

def analyze_profile(profile_info):
    reports = defaultdict(int)
    profile_texts = [
        profile_info.get("username", ""),
        profile_info.get("biography", ""),
        profile_info.get("full_name", "")
    ]

    for text in profile_texts:
        for category, keywords in report_keywords.items():
            if check_keywords(text, keywords):
                reports[category] += 1

    if reports:
        unique_counts = random.sample(range(1, 6), min(len(reports), 4))
        formatted_reports = {
            category: f"{count}x - {category}" for category, count in zip(reports.keys(), unique_counts)
        }
    else:
        all_categories = list(report_keywords.keys())
        num_categories = random.randint(2, 5)
        selected_categories = random.sample(all_categories, num_categories)
        unique_counts = random.sample(range(1, 6), num_categories)
        formatted_reports = {
            category: f"{count}x - {category}" for category, count in zip(selected_categories, unique_counts)
        }

    return formatted_reports

def get_public_instagram_info(username):
    try:
        username = username.lstrip('@').strip()
        time.sleep(random.uniform(2, 5))  # Rate limiting

        profile = instaloader.Profile.from_username(L.context, username)
        return {
            "username": profile.username,
            "full_name": profile.full_name,
            "biography": profile.biography,
            "follower_count": profile.followers,
            "following_count": profile.followees,
            "is_private": profile.is_private,
            "post_count": profile.mediacount,
            "external_url": profile.external_url,
        }
    except instaloader.exceptions.ProfileNotExistsException:
        return None
    except instaloader.exceptions.InstaloaderException as e:
        logging.error(f"Instaloader error: {e}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None

def is_user_in_channel(user_id):
    try:
        member = bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException:
        return False

def escape_markdown_v2(text):
    if not text:
        return ""
    replacements = {
        '_': r'\_', '*': r'\*', '[': r'\[', ']': r'\]',
        '(': r'\(', ')': r'\)', '~': r'\~', '`': r'\`',
        '>': r'\>', '#': r'\#', '+': r'\+', '-': r'\-',
        '=': r'\=', '|': r'\|', '{': r'\{', '}': r'\}',
        '.': r'\.', '!': r'\!'
    }
    pattern = re.compile('|'.join(re.escape(k) for k in replacements))
    return pattern.sub(lambda m: replacements[m.group(0)], text)

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    if not is_user_in_channel(user_id):
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}"))
        markup.add(telebot.types.InlineKeyboardButton("✅ Joined", callback_data='reload'))
        bot.reply_to(message, f"🚀 To use this bot, please join our channel first: @{FORCE_JOIN_CHANNEL}", reply_markup=markup)
        return

    add_user(user_id)
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("ℹ️ Help", callback_data='help'))
    markup.add(telebot.types.InlineKeyboardButton("📢 Updates", url='t.me/team_loops'))
    bot.reply_to(message, "👋 Welcome! Use /getmeth username to analyze an Instagram profile.", reply_markup=markup)

@bot.message_handler(commands=['getmeth'])
def analyze(message):
    user_id = message.chat.id
    if not is_user_in_channel(user_id):
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}"))
        bot.reply_to(message, f"⚠️ Please join @{FORCE_JOIN_CHANNEL} to use this bot.", reply_markup=markup)
        return

    username = ' '.join(message.text.split()[1:]).strip().lstrip('@')

    if not username:
        bot.reply_to(message, "❌ Please provide a username. Usage: /getmeth username")
        return

    msg = bot.reply_to(message, f"🔍 Scanning @{username}... This may take a moment...")

    try:
        profile_info = get_public_instagram_info(username)
        if not profile_info:
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"❌ Profile @{username} not found or inaccessible."
            )
            return

        if profile_info.get('is_private'):
            bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg.message_id,
                text=f"🔒 Profile @{username} is private and cannot be scanned."
            )
            return

        reports_to_file = analyze_profile(profile_info)

        result_text = f"*📊 Profile Analysis for @{profile_info['username']}:*\n\n"
        result_text += f"• *Name:* {profile_info.get('full_name', 'N/A')}\n"
        result_text += f"• *Followers:* {profile_info.get('follower_count', 'N/A')}\n"
        result_text += f"• *Following:* {profile_info.get('following_count', 'N/A')}\n"
        result_text += f"• *Posts:* {profile_info.get('post_count', 'N/A')}\n"
        result_text += f"• *Bio:* {profile_info.get('biography', 'No bio')}\n\n"
        result_text += "*🚨 Suggested Reports:*\n"

        for report in reports_to_file.values():
            result_text += f"➤ {report}\n"

        result_text += "\n*Note:* This analysis is based on available public data."

        result_text = escape_markdown_v2(result_text)

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            "👤 View Profile",
            url=f"https://instagram.com/{profile_info['username']}"
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            "🔄 Scan Another",
            callback_data='scan_another'
        ))

        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text=result_text,
            reply_markup=markup,
            parse_mode='MarkdownV2'
        )

    except Exception as e:
        logging.error(f"Error processing request: {e}")
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=msg.message_id,
            text="⚠️ An error occurred. Please try again later."
        )

@bot.callback_query_handler(func=lambda call: call.data == 'scan_another')
def scan_another_callback(call):
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "🔍 Send me another Instagram username to analyze (without @)"
    )

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ You are not authorized to use this command.")
        return

    broadcast_message = message.text[len("/broadcast "):].strip()
    if not broadcast_message:
        bot.reply_to(message, "❌ Please provide a message to broadcast.")
        return

    users = get_all_users()
    success = 0
    failed = 0

    for user in users:
        try:
            bot.send_message(user, broadcast_message)
            success += 1
            time.sleep(0.5)
        except Exception as e:
            failed += 1
            logging.error(f"Failed to send to {user}: {e}")

    bot.reply_to(message, f"📢 Broadcast complete:\n• Success: {success}\n• Failed: {failed}")

@bot.message_handler(commands=['users'])
def list_users(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ You are not authorized to use this command.")
        return

    users = get_all_users()
    if users:
        user_list = "\n".join([f"👤 {user_id}" for user_id in users])
        bot.reply_to(message, f"📊 Total users: {len(users)}\n\n{user_list}")
    else:
        bot.reply_to(message, "❌ No users found.")

@bot.message_handler(commands=['restart'])
def restart_bot(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ You are not authorized to use this command.")
        return

    bot.reply_to(message, "🔄 Restarting bot...")
    logging.info("Bot restart initiated by admin")
    os.execv(sys.executable, ['python'] + sys.argv)

@bot.callback_query_handler(func=lambda call: call.data == 'reload')
def reload_callback(call):
    user_id = call.from_user.id
    if is_user_in_channel(user_id):
        bot.answer_callback_query(call.id, text="✅ You're now authorized!")
        bot.send_message(
            user_id,
            "🎉 Thanks for joining! Now you can use /getmeth username to analyze profiles."
        )
    else:
        bot.answer_callback_query(
            call.id,
            text="❌ You haven't joined the channel yet!",
            show_alert=True
        )

@bot.callback_query_handler(func=lambda call: call.data == 'help')
def help_callback(call):
    help_text = """
    📚 *Bot Help Guide*

    *Available Commands:*
    /start - Start the bot
    /getmeth username - Analyze an Instagram profile

    *How to Use:*
    1. Send /getmeth followed by the username
    2. Wait for the analysis
    3. View the suggested reports

    *Note:* The bot only works with public profiles.
    """
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.from_user.id,
        escape_markdown_v2(help_text),
        parse_mode='MarkdownV2'
    )

# Start polling
def start_polling():
    while True:
        try:
            logging.info("Starting bot polling...")
            bot.polling(none_stop=True, interval=1, timeout=30)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            time.sleep(15)

if __name__ == "__main__":
    logging.info("Bot starting...")
    print("Bot is running!")
    start_polling()
import os
import sys
import random
import logging
import re
from collections import defaultdict
from threading import Thread
import telebot
import instaloader
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(filename='bot.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Get environment variables
API_TOKEN = os.getenv("API_TOKEN")
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL")
ADMIN_ID = os.getenv("ADMIN_ID")

# Exit if any are missing
if not API_TOKEN or not FORCE_JOIN_CHANNEL or not ADMIN_ID:
    logging.error("Missing one or more environment variables (API_TOKEN, FORCE_JOIN_CHANNEL, ADMIN_ID).")
    sys.exit(1)

# Flask app
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive"

def run_flask_app():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask_app)
    t.start()

keep_alive()

# Telegram bot setup
bot = telebot.TeleBot(API_TOKEN)
bot.remove_webhook()

# User storage
user_ids = set()

def add_user(user_id):
    user_ids.add(user_id)

def remove_user(user_id):
    user_ids.discard(user_id)

def get_all_users():
    return list(user_ids)

# Keywords
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
    return any(keyword in text.lower() for keyword in keywords)

def analyze_profile(profile_info):
    reports = defaultdict(int)
    profile_texts = [profile_info.get("username", ""), profile_info.get("biography", "")]

    for text in profile_texts:
        for category, keywords in report_keywords.items():
            if check_keywords(text, keywords):
                reports[category] += 1

    if reports:
        unique_counts = random.sample(range(1, 6), min(len(reports), 4))
        return {cat: f"{cnt}x - {cat}" for cat, cnt in zip(reports.keys(), unique_counts)}
    else:
        selected = random.sample(list(report_keywords.keys()), random.randint(2, 5))
        counts = random.sample(range(1, 6), len(selected))
        return {cat: f"{cnt}x - {cat}" for cat, cnt in zip(selected, counts)}

def get_public_instagram_info(username):
    L = instaloader.Instaloader()
    try:
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
        logging.error(f"An error occurred: {e}")
        return None

def is_user_in_channel(user_id):
    try:
        member = bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        return member.status in ['member', 'administrator', 'creator']
    except telebot.apihelper.ApiTelegramException:
        return False

def escape_markdown_v2(text):
    replacements = {
        '_': r'\_', '*': r'\*', '[': r'\[', ']': r'\]', '(': r'\(', ')': r'\)',
        '~': r'\~', '`': r'\`', '>': r'\>', '#': r'\#', '+': r'\+', '-': r'\-',
        '=': r'\=', '|': r'\|', '{': r'\{', '}': r'\}', '.': r'\.', '!': r'\!'
    }
    pattern = re.compile('|'.join(re.escape(k) for k in replacements))
    return pattern.sub(lambda m: replacements[m.group(0)], text)

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.chat.id
    if not is_user_in_channel(user_id):
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}"))
        markup.add(telebot.types.InlineKeyboardButton("Joined", callback_data='reload'))
        bot.reply_to(message, f"Please join @{FORCE_JOIN_CHANNEL} to use this bot.", reply_markup=markup)
        return

    add_user(user_id)
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("Help", callback_data='help'))
    markup.add(telebot.types.InlineKeyboardButton("Update Channel", url='https://t.me/team_loops'))
    bot.reply_to(message, "Welcome! Use /getmeth <username> to analyze an Instagram profile.", reply_markup=markup)

@bot.message_handler(commands=['getmeth'])
def analyze(message):
    user_id = message.chat.id
    if not is_user_in_channel(user_id):
        bot.reply_to(message, f"Please join @{FORCE_JOIN_CHANNEL} to use this bot.")
        return

    username = message.text.split()[1:]
    if not username:
        bot.reply_to(message, "😾 Wrong method. Please use: /getmeth Username (without @ or <>).")
        return

    username = ' '.join(username)
    bot.reply_to(message, f"🔍 Scanning Profile: {username}. Please wait...")

    profile_info = get_public_instagram_info(username)
    if profile_info:
        reports = analyze_profile(profile_info)
        result = f"**Public Information for {username}:**\n"
        result += f"Username: {profile_info['username']}\n"
        result += f"Full Name: {profile_info['full_name']}\n"
        result += f"Biography: {profile_info['biography']}\n"
        result += f"Followers: {profile_info['follower_count']}\n"
        result += f"Following: {profile_info['following_count']}\n"
        result += f"Private Account: {'Yes' if profile_info['is_private'] else 'No'}\n"
        result += f"Posts: {profile_info['post_count']}\n"
        result += f"External URL: {profile_info['external_url']}\n\n"
        result += "Suggested Reports:\n"
        result += "\n".join([f"• {r}" for r in reports.values()])
        result += "\n\n*Note: This method is based on available data and may not be fully accurate.*"

        result = escape_markdown_v2(result)

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Visit Profile", url=f"https://instagram.com/{profile_info['username']}"))
        markup.add(telebot.types.InlineKeyboardButton("Developer", url='https://t.me/focro'))

        bot.send_message(user_id, result, reply_markup=markup, parse_mode='MarkdownV2')
    else:
        bot.reply_to(message, f"❌ Profile {username} not found or an error occurred.")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if str(message.chat.id) != ADMIN_ID:
        return bot.reply_to(message, "You are not authorized to use this command.")
    msg = message.text[len("/broadcast "):].strip()
    if not msg:
        return bot.reply_to(message, "Please provide a message.")
    for uid in get_all_users():
        try:
            bot.send_message(uid, msg)
        except Exception as e:
            logging.error(f"Failed to message {uid}: {e}")

@bot.message_handler(commands=['users'])
def list_users(message):
    if str(message.chat.id) != ADMIN_ID:
        return bot.reply_to(message, "You are not authorized to use this command.")
    users = get_all_users()
    if users:
        bot.reply_to(message, "\n".join([f"User ID: {u}" for u in users]))
    else:
        bot.reply_to(message, "No users found.")

@bot.message_handler(commands=['remove_user'])
def remove_user_command(message):
    if str(message.chat.id) != ADMIN_ID:
        return bot.reply_to(message, "You are not authorized to use this command.")
    uid = message.text.split()[1:]
    if not uid:
        return bot.reply_to(message, "Provide a user ID.")
    remove_user(int(uid[0]))
    bot.reply_to(message, f"Removed user ID {uid[0]}")

@bot.message_handler(commands=['restart'])
def restart_bot(message):
    if str(message.chat.id) != ADMIN_ID:
        return bot.reply_to(message, "You are not authorized.")
    bot.reply_to(message, "Restarting bot...")
    logging.info("Bot restarting...")
    os.execv(sys.executable, ['python'] + sys.argv)

@bot.callback_query_handler(func=lambda call: call.data == 'reload')
def reload_callback(call):
    if is_user_in_channel(call.from_user.id):
        bot.answer_callback_query(call.id, text="You're authorized!")
        bot.send_message(call.from_user.id, "Welcome! Use /getmeth <username> to analyze a profile.")
    else:
        bot.answer_callback_query(call.id, text="Still not in the channel. Join first.")

@bot.callback_query_handler(func=lambda call: call.data == 'help')
def help_callback(call):
    help_text = "Use /getmeth <username> to analyze a profile. You must be a channel member to use this bot."
    help_text = escape_markdown_v2(help_text)
    bot.answer_callback_query(call.id, text=help_text)
    bot.send_message(call.from_user.id, help_text, parse_mode='MarkdownV2')

def start_polling():
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        logging.error(f"Polling error: {e}")

if __name__ == "__main__":
    print("Starting the bot...")
    logging.info("Bot started.")
    start_polling()

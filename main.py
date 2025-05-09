import os
import sys
import random
import logging
import re
import time
from collections import defaultdict
from threading import Thread, Lock
import telebot
import instaloader
from flask import Flask
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

# Flask app for keep-alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

# Start Flask in a thread
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()

# Bot configuration
API_TOKEN = os.getenv("API_TOKEN")
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL")
ADMIN_ID = os.getenv("ADMIN_ID")
INSTAGRAM_USER = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASS = os.getenv("INSTAGRAM_PASSWORD")

# Initialize bot with file storage to prevent conflicts
bot = telebot.TeleBot(API_TOKEN, num_threads=1)
bot.remove_webhook()

# Custom rate controller
class CustomRateController:
    def __init__(self, controller):
        self._controller = controller
        self.last_request = 0
        self.lock = Lock()

    def sleep(self, secs):
        with self.lock:
            elapsed = time.time() - self.last_request
            if elapsed < secs:
                time.sleep(secs - elapsed)
            self.last_request = time.time()

# Instagram manager class
class InstagramManager:
    def __init__(self):
        self.lock = Lock()
        self.last_request = 0
        self.login_status = False
        self.login_attempts = 0
        self.last_error = None
        self.loader = None

    def initialize(self):
        with self.lock:
            try:
                self.loader = instaloader.Instaloader(
                    max_connection_attempts=1,
                    request_timeout=60,
                    sleep=True,
                    rate_controller=lambda x: CustomRateController(x)
                )

                if INSTAGRAM_USER and INSTAGRAM_PASS:
                    self._attempt_login()
                else:
                    logging.info("Instagram: Running in anonymous mode")
                    self.login_status = False

                return True
            except Exception as e:
                self.last_error = str(e)
                logging.error(f"Instagram init failed: {e}")
                return False

    def _attempt_login(self):
        try:
            if self.login_attempts >= 3:
                logging.warning("Too many login attempts, staying anonymous")
                return False

            self.loader.login(INSTAGRAM_USER, INSTAGRAM_PASS)
            self.login_status = True
            self.login_attempts = 0
            logging.info("Instagram login successful")
            return True
        except Exception as e:
            self.login_status = False
            self.login_attempts += 1
            self.last_error = str(e)
            logging.error(f"Instagram login failed (attempt {self.login_attempts}): {e}")
            return False

    def get_profile(self, username):
        with self.lock:
            if not self.loader:
                return None

            username = username.lstrip('@').strip()
            if not username:
                return None

            try:
                elapsed = time.time() - self.last_request
                if elapsed < 5:
                    time.sleep(5 - elapsed)

                profile = instaloader.Profile.from_username(self.loader.context, username)
                self.last_request = time.time()

                return {
                    "username": profile.username,
                    "name": profile.full_name,
                    "bio": profile.biography,
                    "followers": profile.followers,
                    "following": profile.followees,
                    "private": profile.is_private,
                    "posts": profile.mediacount,
                    "url": f"https://instagram.com/{profile.username}"
                }
            except instaloader.exceptions.ProfileNotExistsException:
                return None
            except Exception as e:
                self.last_error = str(e)
                logging.error(f"Profile fetch error: {e}")
                return None

    def get_status(self):
        return {
            "logged_in": self.login_status,
            "attempts": self.login_attempts,
            "last_error": self.last_error,
            "anonymous": not (INSTAGRAM_USER and INSTAGRAM_PASS)
        }

# Initialize Instagram manager
instagram = InstagramManager()
if not instagram.initialize():
    logging.error("Failed to initialize Instagram connection")

# User storage
user_storage = set()
storage_lock = Lock()

def add_user(user_id):
    with storage_lock:
        user_storage.add(user_id)

def get_users():
    with storage_lock:
        return list(user_storage)

# Profile analysis
report_categories = {
    "HATE": ["devil", "666", "hate"],
    "SELF": ["suicide", "kill myself"],
    "BULLY": ["@"],
    "VIOLENT": ["hitler", "guns"],
    "ILLEGAL": ["drugs", "cocaine"],
    "PRETENDING": ["verified", "official"],
    "NUDITY": ["nude", "sex"],
    "SPAM": ["whatsapp", "contact me"]
}

def analyze_text(text):
    results = {}
    text = (text or "").lower()
    for category, terms in report_categories.items():
        if any(term in text for term in terms):
            results[category] = random.randint(1, 5)
    return results or {k: random.randint(1, 3) for k in random.sample(list(report_categories.keys()), 3)}

# Telegram handlers
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.chat.id
    try:
        member = bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", user_id)
        if member.status not in ['member', 'administrator', 'creator']:
            raise Exception("Not a member")
    except:
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("Join Channel", url=f"t.me/{FORCE_JOIN_CHANNEL}"))
        bot.reply_to(message, "Please join our channel first:", reply_markup=markup)
        return

    add_user(user_id)
    bot.reply_to(message, "Welcome! Send /analyze username to check an Instagram profile")

@bot.message_handler(commands=['analyze', 'getmeth'])
def analyze_cmd(message):
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "Usage: /analyze username")
        return

    username = ' '.join(args[1:])
    msg = bot.reply_to(message, f"🔍 Scanning @{username}...")

    status = instagram.get_status()
    if not status['anonymous'] and not status['logged_in'] and status['attempts'] >= 3:
        bot.edit_message_text(
            "⚠️ Instagram login failed multiple times. Using limited anonymous mode.",
            message.chat.id,
            msg.message_id
        )
        time.sleep(2)

    profile = instagram.get_profile(username)
    if not profile:
        bot.edit_message_text("❌ Profile not found or private", message.chat.id, msg.message_id)
        return

    if profile['private']:
        bot.edit_message_text("🔒 Private profile - cannot analyze", message.chat.id, msg.message_id)
        return

    reports = {
        **analyze_text(profile['name']),
        **analyze_text(profile['bio'])
    }

    response = f"*{profile['username']} Analysis*\n\n"
    response += f"👤 *Name:* {profile['name'] or 'None'}\n"
    response += f"📝 *Bio:* {profile['bio'] or 'None'}\n"
    response += f"👥 *Followers:* {profile['followers']}\n"
    response += f"🔄 *Following:* {profile['following']}\n\n"
    response += "*Suggested Reports:*\n"

    for cat, count in reports.items():
        response += f"- {count}x {cat}\n"

    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("View Profile", url=profile['url']))

    bot.edit_message_text(
        response,
        message.chat.id,
        msg.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.message_handler(commands=['instastatus'])
def insta_status(message):
    if str(message.chat.id) != ADMIN_ID:
        bot.reply_to(message, "⛔ Command restricted to admin")
        return

    status = instagram.get_status()
    response = "📊 Instagram Connection Status:\n\n"

    if status['anonymous']:
        response += "🔓 Mode: Anonymous (no login credentials provided)\n"
    else:
        response += f"🔐 Mode: {'Logged In' if status['logged_in'] else 'Not Logged In'}\n"
        response += f"🔢 Login Attempts: {status['attempts']}/3\n"

    if status['last_error']:
        response += f"\n❌ Last Error: {status['last_error']}\n"

    response += "\nℹ️ Note: Anonymous mode has stricter rate limits"

    bot.reply_to(message, response)

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if str(message.chat.id) != ADMIN_ID:
        return

    text = message.text.replace('/broadcast', '').strip()
    if not text:
        bot.reply_to(message, "Usage: /broadcast message")
        return

    users = get_users()
    for user in users:
        try:
            bot.send_message(user, text)
            time.sleep(0.3)
        except:
            continue

    bot.reply_to(message, f"Broadcast sent to {len(users)} users")

@bot.callback_query_handler(func=lambda call: True)
def handle_errors(call):
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

# Start the bot with conflict prevention
def polling():
    while True:
        try:
            logging.info("Starting bot polling...")
            bot.polling(none_stop=True, interval=3, timeout=30)
        except Exception as e:
            logging.error(f"Polling error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    logging.info("Bot starting...")
    polling()
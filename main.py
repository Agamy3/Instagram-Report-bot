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

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='bot.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Flask app for keeping bot alive
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

keep_alive()

# Bot configuration
bot = telebot.TeleBot(os.getenv("API_TOKEN"))
bot.remove_webhook()

# Instagram loader with login
L = instaloader.Instaloader()
try:
    if os.getenv("INSTAGRAM_USER") and os.getenv("INSTAGRAM_PASS"):
        L.login(os.getenv("INSTAGRAM_USER"), os.getenv("INSTAGRAM_PASS"))
        logging.info("Instagram login successful")
except Exception as e:
    logging.error(f"Instagram login failed: {e}")

# User storage
user_storage = set()

# Report categories
REPORT_CATEGORIES = {
    "HATE": ["hate", "racist", "sexist"],
    "SCAM": ["scam", "fraud", "cheat"],
    "SPAM": ["promo", "dm me", "buy followers"],
    "FAKE": ["fake", "impersonator"],
    "NSFW": ["nude", "onlyfans", "nsfw"]
}

def analyze_profile(profile):
    reports = {}
    bio = profile.get("biography", "").lower()

    for category, keywords in REPORT_CATEGORIES.items():
        if any(keyword in bio for keyword in keywords):
            reports[category] = random.randint(1, 5)

    if not reports:
        reports = {random.choice(list(REPORT_CATEGORIES.keys())): random.randint(1, 3)}

    return reports

def get_instagram_data(username):
    try:
        username = re.sub(r"[^a-zA-Z0-9._]", "", username.strip().lower())
        if not username:
            return None

        time.sleep(2)  # Rate limiting

        profile = instaloader.Profile.from_username(L.context, username)
        return {
            "username": profile.username,
            "full_name": profile.full_name,
            "biography": profile.biography,
            "followers": profile.followers,
            "following": profile.followees,
            "is_private": profile.is_private,
            "posts": profile.mediacount,
            "external_url": profile.external_url
        }
    except instaloader.ProfileNotExistsException:
        logging.error(f"Profile @{username} not found")
        return None
    except Exception as e:
        logging.error(f"Error fetching @{username}: {str(e)}")
        return None

def escape_markdown(text):
    return re.sub(r"([_*\[\]()~`>#+\-=|{}.!])", r"\\\1", text)

@bot.message_handler(commands=['start'])
def start(message):
    user_storage.add(message.chat.id)
    bot.reply_to(message,
        "🔍 *Instagram Profile Analyzer*\n\n"
        "Use `/getmeth username` to analyze any public Instagram profile\n\n"
        "Example: `/getmeth cristiano`",
        parse_mode="MarkdownV2")

@bot.message_handler(commands=['getmeth'])
def analyze(message):
    try:
        if len(message.text.split()) < 2:
            bot.reply_to(message, "❌ Please provide a username\nExample: /getmeth username")
            return

        username = " ".join(message.text.split()[1:])
        bot.send_chat_action(message.chat.id, 'typing')

        profile = get_instagram_data(username)
        if not profile:
            bot.reply_to(message, f"❌ Profile @{username} not found or private")
            return

        reports = analyze_profile(profile)
        report_text = "\n".join([f"• {count}x {cat}" for cat, count in reports.items()])

        response = (
            f"📊 *Profile Analysis*: @{profile['username']}\n\n"
            f"👤 *Name*: {escape_markdown(profile['full_name'] or 'N/A')}\n"
            f"📝 *Bio*: {escape_markdown(profile['biography'] or 'N/A')}\n"
            f"👥 *Followers*: {profile['followers']:,}\n"
            f"🔄 *Following*: {profile['following']:,}\n"
            f"📸 *Posts*: {profile['posts']:,}\n\n"
            f"⚠️ *Detected Issues*:\n{report_text}\n\n"
            "_Note: This is an automated analysis_"
        )

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            "View Profile",
            url=f"https://instagram.com/{profile['username']}"))

        bot.reply_to(message, response,
                   parse_mode="MarkdownV2",
                   reply_markup=markup,
                   disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Command error: {str(e)}")
        bot.reply_to(message, "⚠️ An error occurred. Please try again later.")

@bot.message_handler(commands=['stats'])
def stats(message):
    if str(message.chat.id) != os.getenv("ADMIN_ID"):
        return
    bot.reply_to(message, f"👥 Total users: {len(user_storage)}")

def run_bot():
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            logging.error(f"Bot crashed: {str(e)}")
            time.sleep(15)

if __name__ == "__main__":
    logging.info("Starting bot...")
    Thread(target=run_bot).start()
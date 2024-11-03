#!/usr/bin/env python
import io
import json
import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from pydub import AudioSegment
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

script_path = os.path.abspath(__file__)
script_dir = os.path.dirname(script_path)

# Create voices directory if it doesn't exist
VOICES_DIR = Path(script_dir + "/voices")
VOICES_DIR.mkdir(exist_ok=True)

# Database setup
DB_PATH = Path(script_dir + "/users.db")


def init_db():
    """Initialize SQLite database with users table"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            chat_id TEXT PRIMARY KEY,
            thread_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    conn.commit()
    conn.close()


def load_config():
    """Load configuration from config.json"""
    with open(script_dir + "/config.json", "r") as config_file:
        return json.load(config_file)


config = load_config()
BOT_TOKEN = config["bot_token"]
SERVICE_PASSWORD = config["service_password"]  # New configuration item
client = OpenAI(api_key=config["OPENAI_API_KEY"])


def is_user_subscribed(chat_id):
    """Check if user is subscribed"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT thread_id FROM users WHERE chat_id = ?", (str(chat_id),))
    result = c.fetchone()
    conn.close()
    return result is not None


def get_user_thread(chat_id):
    """Get user's thread ID"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT thread_id FROM users WHERE chat_id = ?", (str(chat_id),))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None


def add_user(chat_id, thread_id):
    """Add new user to database"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (chat_id, thread_id) VALUES (?, ?)",
        (str(chat_id), thread_id),
    )
    conn.commit()
    conn.close()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    await update.message.reply_text(
        "Hello! I am your AI assistant bot. To subscribe to the service, please use:\n"
        "/subscribe <password>\n\n"
        "Once subscribed, I can handle text, images, and audio messages."
    )


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /subscribe command"""
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /subscribe <password>")
        return

    if context.args[0] != SERVICE_PASSWORD:
        await update.message.reply_text("Invalid password. Please try again.")
        return

    chat_id = str(update.message.chat_id)
    if is_user_subscribed(chat_id):
        await update.message.reply_text("You are already subscribed!")
        return

    # Create a new thread for the user
    thread = client.beta.threads.create()
    add_user(chat_id, thread.id)

    await update.message.reply_text(
        "Successfully subscribed! You can now use the AI assistant."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command"""
    if not is_user_subscribed(str(update.message.chat_id)):
        await update.message.reply_text(
            "Please subscribe first using /subscribe <password>"
        )
        return

    help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
/subscribe <password> - Subscribe to the service

You can send:
• Text messages
• Images (photos)
• Voice messages
"""
    await update.message.reply_text(help_text)


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for regular text messages"""
    chat_id = str(update.message.chat_id)
    if not is_user_subscribed(chat_id):
        await update.message.reply_text("I am just a dumb bot.. oh uh..")
        return

    thread_id = get_user_thread(chat_id)
    message_type = update.message.chat.type
    text = str(datetime.now()) + " - " + update.message.text
    logging.info(f"Received text message: {text} in chat type: {message_type}")

    thread_message = client.beta.threads.messages.create(
        thread_id,
        role="user",
        content=text,
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=thread_id, assistant_id=config["assistant_id"]
    )

    thread_messages = list(
        client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id)
    )

    response = thread_messages[0].content[0].text.value

    await update.message.reply_text(response)


async def handle_image_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for image messages"""
    chat_id = str(update.message.chat_id)
    if not is_user_subscribed(chat_id):
        await update.message.reply_text("I am just a dumb bot.. oh uh..")
        return

    thread_id = get_user_thread(chat_id)
    try:
        photo = max(update.message.photo, key=lambda x: x.file_size)
        photo_file = await context.bot.get_file(photo.file_id)
        file_url = photo_file.file_path

        logging.info(f"Received image URL: {file_url}")

        caption = update.message.caption or "Image received"
        message_text = f"{datetime.now()} - {caption}"

        thread_message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=[
                {"type": "text", "text": message_text},
                {"type": "image_url", "image_url": {"url": file_url}},
            ],
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=config["assistant_id"]
        )

        thread_messages = client.beta.threads.messages.list(thread_id)

        response = ""
        for msg in thread_messages.data:
            if msg.run_id == run.id:
                response = msg.content[0].text.value

        await update.message.reply_text(response)

    except Exception as e:
        logging.error(f"Error handling image: {str(e)}")
        await update.message.reply_text(
            "Sorry, I encountered an error processing your image."
        )


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for voice messages"""
    chat_id = str(update.message.chat_id)
    if not is_user_subscribed(chat_id):
        await update.message.reply_text("I am just a dumb bot.. oh uh..")
        return

    thread_id = get_user_thread(chat_id)
    try:
        voice = update.message.voice
        voice_file = await context.bot.get_file(voice.file_id)

        base_filename = f"voice_{update.effective_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ogg_path = VOICES_DIR / f"{base_filename}.ogg"
        mp3_path = VOICES_DIR / f"{base_filename}.mp3"

        await voice_file.download_to_drive(ogg_path)

        audio = AudioSegment.from_file(ogg_path, format="ogg")
        audio.export(mp3_path, format="mp3")

        logging.info(f"Processing voice message: {mp3_path}")

        with open(mp3_path, "rb") as audio_file:
            transcript = client.audio.translations.create(
                model="whisper-1", file=audio_file
            )

        message_text = f"{datetime.now()} - {transcript.text}"
        logging.info(f"Transcription: {transcript.text}")

        thread_message = client.beta.threads.messages.create(
            thread_id=thread_id, role="user", content=message_text
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=config["assistant_id"]
        )

        thread_messages = client.beta.threads.messages.list(thread_id)

        response = ""
        for msg in thread_messages.data:
            if msg.run_id == run.id:
                response = msg.content[0].text.value

        await update.message.reply_text(f"{response}")

        os.remove(ogg_path)
        os.remove(mp3_path)

    except Exception as e:
        logging.error(f"Error handling voice message: {str(e)}")
        await update.message.reply_text(
            f"Sorry, I encountered an error processing your voice message: {str(e)}"
        )


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for file uploads"""
    chat_id = str(update.message.chat_id)
    if not is_user_subscribed(chat_id):
        await update.message.reply_text("I am just a dumb bot.. oh uh..")
        return

    thread_id = get_user_thread(chat_id)
    try:
        file = update.message.document
        file_info = await context.bot.get_file(file.file_id)

        logging.info(f"Received file: {file.file_name}")

        caption = update.message.caption or "File uploaded"
        message_text = f"{datetime.now()} - {caption}"

        file_bytes = await file_info.download_as_bytearray()
        file_obj = io.BytesIO(file_bytes)
        file_obj.name = file.file_name

        file_response = client.files.create(file=file_obj, purpose="assistants")

        thread_message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=[{"type": "text", "text": message_text}],
            attachments=[
                {"file_id": file_response.id, "tools": [{"type": "file_search"}]}
            ],
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=config["assistant_id"]
        )

        thread_messages = client.beta.threads.messages.list(thread_id)

        response = ""
        for msg in thread_messages.data:
            if msg.run_id == run.id:
                response = msg.content[0].text.value

        await update.message.reply_text(response)

    except Exception as e:
        logging.error(f"Error handling file upload: {str(e)}")
        await update.message.reply_text(
            f"Sorry, I encountered an error processing your file: {str(e)}"
        )


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    logging.error(f"Update {update} caused error {context.error}")


def main():
    """Main function to run the bot"""
    try:
        # Initialize database
        init_db()

        # Create application
        app = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("subscribe", subscribe_command))
        app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message)
        )
        app.add_handler(MessageHandler(filters.PHOTO, handle_image_message))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
        app.add_handler(MessageHandler(filters.Document.ALL, handle_file_upload))

        # Add error handler
        app.add_error_handler(error)

        # Start polling
        logging.info("Starting bot...")
        app.run_polling(poll_interval=3)

    except Exception as e:
        logging.error(f"Error running bot: {e}")


if __name__ == "__main__":
    main()

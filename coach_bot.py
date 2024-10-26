# bot.py
import json
import logging
from datetime import datetime
from pathlib import Path

from openai import OpenAI
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

# Load configuration
def load_config():
    with open("config.json", "r") as config_file:
        return json.load(config_file)

config = load_config()
CHAT_ID = config["chat_id"]
BOT_TOKEN = config["bot_token"]
client = OpenAI(
    api_key=config["OPENAI_API_KEY"]
)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    await update.message.reply_text(
        "Hello! I am your Telegram bot. I can handle text, images, and audio messages. How can I help you today?"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    help_text = """
Available commands:
/start - Start the bot
/help - Show this help message

You can send:
• Text messages
• Images (photos)
• Voice messages
"""
    await update.message.reply_text(help_text)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for regular text messages"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    message_type = update.message.chat.type
    text = str(datetime.now()) + " - " + update.message.text
    logging.info(f"Received text message: {text} in chat type: {message_type}")

    thread_message = client.beta.threads.messages.create(
        config["thread_id"],
        role="user",
        content=text,
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=config["thread_id"], 
        assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
    )

    thread_messages = client.beta.threads.messages.list(config["thread_id"])
    
    response = ""
    for msg in thread_messages.data:
        if msg.run_id == run.id:
            response = msg.content[0].text.value

    await update.message.reply_text(response)

async def handle_image_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for image messages"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    try:
        # Get the largest available photo
        photo = max(update.message.photo, key=lambda x: x.file_size)
        
        # Get the file URL directly from Telegram
        photo_file = await context.bot.get_file(photo.file_id)
        file_url = photo_file.file_path  # This is the direct URL to the image
        
        logging.info(f"Received image URL: {file_url}")

        # Get caption if it exists
        caption = update.message.caption or "Image received"
        message_text = f"{datetime.now()} - {caption}"

        # Create message with image URL
        thread_message = client.beta.threads.messages.create(
            thread_id=config["thread_id"],
            role="user",
            content=[
                {
                    "type": "text",
                    "text": message_text
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": file_url
                    }
                }
            ]
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=config["thread_id"],
            assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
        )

        thread_messages = client.beta.threads.messages.list(config["thread_id"])
        
        response = ""
        for msg in thread_messages.data:
            if msg.run_id == run.id:
                response = msg.content[0].text.value

        await update.message.reply_text(response)

    except Exception as e:
        logging.error(f"Error handling image: {str(e)}")
        await update.message.reply_text("Sorry, I encountered an error processing your image.")

async def handle_audio_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for voice messages"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    # Get the voice message
    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)
    file_url = voice_file.file_path
    
    logging.info(f"Received voice message URL: {file_url}")

    # For now, just acknowledge receipt of audio
    message_text = f"{datetime.now()} - Received voice message (duration: {voice.duration}s)"
    
    thread_message = client.beta.threads.messages.create(
        thread_id=config["thread_id"],
        role="user",
        content=message_text
    )

    run = client.beta.threads.runs.create_and_poll(
        thread_id=config["thread_id"],
        assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
    )

    thread_messages = client.beta.threads.messages.list(config["thread_id"])
    
    response = ""
    for msg in thread_messages.data:
        if msg.run_id == run.id:
            response = msg.content[0].text.value

    await update.message.reply_text(response)

async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    logging.error(f"Update {update} caused error {context.error}")

def main():
    """Main function to run the bot"""
    try:
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
        app.add_handler(MessageHandler(filters.PHOTO, handle_image_message))
        app.add_handler(MessageHandler(filters.VOICE, handle_audio_message))

        # Add error handler
        app.add_error_handler(error)

        # Start polling
        logging.info("Starting bot...")
        app.run_polling(poll_interval=3)

    except Exception as e:
        logging.error(f"Error running bot: {e}")

if __name__ == "__main__":
    main()

# bot.py
import io
import json
import logging
import os
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

# Create voices directory if it doesn't exist
VOICES_DIR = Path("voices")
VOICES_DIR.mkdir(exist_ok=True)


# Load configuration
def load_config():
    with open("config.json", "r") as config_file:
        return json.load(config_file)


config = load_config()
CHAT_ID = config["chat_id"]
BOT_TOKEN = config["bot_token"]
client = OpenAI(api_key=config["OPENAI_API_KEY"])


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
        thread_id=config["thread_id"], assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
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
                {"type": "text", "text": message_text},
                {"type": "image_url", "image_url": {"url": file_url}},
            ],
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=config["thread_id"], assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
        )

        thread_messages = client.beta.threads.messages.list(config["thread_id"])

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
    """Handler for voice messages with transcription"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    try:
        # Get the voice message
        voice = update.message.voice
        voice_file = await context.bot.get_file(voice.file_id)

        # Generate filenames
        base_filename = f"voice_{update.effective_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ogg_path = VOICES_DIR / f"{base_filename}.ogg"
        mp3_path = VOICES_DIR / f"{base_filename}.mp3"

        # Download the voice message
        await voice_file.download_to_drive(ogg_path)

        # Convert OGG to MP3 using pydub
        audio = AudioSegment.from_file(ogg_path, format="ogg")
        audio.export(mp3_path, format="mp3")

        logging.info(f"Processing voice message: {mp3_path}")

        # Transcribe the audio using Whisper
        with open(mp3_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file
            )

        # Create message with transcription
        message_text = f"{datetime.now()} - {transcript.text}"
        logging.info(f"Transcription: {transcript.text}")

        # Send transcription to OpenAI assistant
        thread_message = client.beta.threads.messages.create(
            thread_id=config["thread_id"], role="user", content=message_text
        )

        # Get assistant's response
        run = client.beta.threads.runs.create_and_poll(
            thread_id=config["thread_id"], assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
        )

        thread_messages = client.beta.threads.messages.list(config["thread_id"])

        response = ""
        for msg in thread_messages.data:
            if msg.run_id == run.id:
                response = msg.content[0].text.value

        # Send both transcription and response
        await update.message.reply_text(f"{response}")

        # Cleanup temporary files
        os.remove(ogg_path)
        os.remove(mp3_path)

    except Exception as e:
        logging.error(f"Error handling voice message: {str(e)}")
        await update.message.reply_text(
            f"Sorry, I encountered an error processing your voice message: {str(e)}"
        )


async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for file uploads"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    try:
        # Get file information
        file = update.message.document
        file_info = await context.bot.get_file(file.file_id)

        logging.info(f"Received file: {file.file_name}")

        # Create a message with the file URL and any caption
        caption = update.message.caption or "File uploaded"
        message_text = f"{datetime.now()} - {caption}"

        # Download file and convert to file-like object
        file_bytes = await file_info.download_as_bytearray()
        file_obj = io.BytesIO(file_bytes)
        # Set the name attribute for proper MIME type detection
        file_obj.name = file.file_name

        # Upload file to OpenAI
        file_response = client.files.create(file=file_obj, purpose="assistants")

        # Send message with file to the thread
        thread_message = client.beta.threads.messages.create(
            thread_id=config["thread_id"],
            role="user",
            content=[{"type": "text", "text": message_text}],
            attachments=[
                {"file_id": file_response.id, "tools": [{"type": "file_search"}]}
            ],
        )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=config["thread_id"], assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
        )

        thread_messages = client.beta.threads.messages.list(config["thread_id"])

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
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
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

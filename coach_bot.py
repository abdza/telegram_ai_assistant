# bot.py
import json
import logging
from datetime import datetime

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
    # This is the default and can be omitted
    api_key=config["OPENAI_API_KEY"]
)


# Command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    await update.message.reply_text(
        "Hello! I am your Telegram bot. How can I help you today?"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    help_text = """
Available commands:
/start - Start the bot
/help - Show this help message
"""
    await update.message.reply_text(help_text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for regular messages"""
    if str(update.message.chat_id) != CHAT_ID:
        return

    message_type = update.message.chat.type
    text = str(datetime.now()) + " - " + update.message.text
    # Log the received message
    logging.info(f"Received message: {text} in chat type: {message_type}")

    my_thread = client.beta.threads.retrieve(config["thread_id"])
    thread_message = client.beta.threads.messages.create(
        config["thread_id"],
        role="user",
        content=text,
    )
    print("Created thread message:", thread_message)

    run = client.beta.threads.runs.create_and_poll(
        thread_id=config["thread_id"], assistant_id="asst_KGI7hfOHHJlH367w9QSeQtbJ"
    )
    print("Run done:", run)

    thread_messages = client.beta.threads.messages.list(config["thread_id"])
    print("Messages:", thread_messages)

    # Echo the message back to user
    # response = f"You said: {text}"
    response = ""

    for msg in thread_messages.data:
        print("Msg :", msg, " Run:", msg.run_id)
        if msg.run_id == run.id:
            print("Content:", msg.content[0].text.value)
            response = msg.content[0].text.value

    await update.message.reply_text(response)


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Error handler"""
    logging.error(f"Update {update} caused error {context.error}")


def main():
    """Main function to run the bot"""
    try:
        # empty_thread = client.beta.threads.create()
        # print("AI Thread:", empty_thread)
        # Create application
        app = Application.builder().token(BOT_TOKEN).build()

        # Add handlers
        app.add_handler(CommandHandler("start", start_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        # Add error handler
        app.add_error_handler(error)

        # Start polling
        logging.info("Starting bot...")
        app.run_polling(poll_interval=3)

    except Exception as e:
        logging.error(f"Error running bot: {e}")


if __name__ == "__main__":
    main()

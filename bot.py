from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters
)
from dotenv import load_dotenv
from openai import OpenAI
import os
import sys

# Load environment variables
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ABACUS_API_KEY = os.getenv("ABACUS_API_KEY")

if not TOKEN or not ABACUS_API_KEY:
    print("❌ Missing BOT_TOKEN or ABACUS_API_KEY in .env")
    sys.exit(1)

# Setup Abacus-AI RouteLLM via OpenAI SDK (OpenAI-compatible API)
client = OpenAI(
    base_url="https://routellm.abacus.ai/v1",
    api_key=ABACUS_API_KEY
)

# Store each user’s model, chat history & stats
current_model = {}
user_history = {}
user_stats = {}

# Limit number of exchanges remembered
MAX_MEMORY = 10


# --- Commands --- #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    current_model[user_id] = "gpt-5"   # default
    user_history[user_id] = []         # reset history
    user_stats[user_id] = {"prompt": 0, "completion": 0, "total": 0}
    await update.message.reply_text(
        "👋 Hello! I am your **Telegram AI Solution Bot** 🤖\n"
        "By default, I use GPT‑5.\n\n"
        "Type /help to see available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Telegram AI Solution Bot* 📘\n\n"
        "Powered by Abacus.AI RouteLLM 🌐\n\n"
        "📌 Commands:\n"
        "/start - Restart bot & clear memory\n"
        "/help - Show this menu\n"
        "/model - Show current AI model\n"
        "/reset - Reset your conversation memory\n"
        "/stats - Show your token usage\n\n"
        "📌 Switch Models:\n"
        "/gpt5 - GPT‑5\n"
        "/gpt5thinking - GPT‑5 Thinking\n"
        "/claude - Claude Sonnet 4\n"
        "/gemini - Gemini 2.5 Pro\n"
        "/grok - Grok 4\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# Show current model
async def current_model_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    model = current_model.get(user_id, "gpt-5")
    await update.message.reply_text(f"🤖 You are currently using: *{model}*", parse_mode="Markdown")


# Reset memory
async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_history[user_id] = []
    await update.message.reply_text("♻️ Conversation memory has been reset.")


# Show token stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    stats = user_stats.get(user_id)

    if not stats:
        await update.message.reply_text("⚠️ No usage data available yet. Try chatting first.")
        return

    # cost estimate (flat rate example: $0.002/1K tokens, adjust if you have per-model pricing)
    cost = stats["total"] / 1000 * 0.002

    msg = (
        f"📊 *Your Usage Stats* 📊\n\n"
        f"Prompt tokens: {stats['prompt']}\n"
        f"Completion tokens: {stats['completion']}\n"
        f"Total tokens: {stats['total']}\n\n"
        f"💰 Estimated cost: ${cost:.4f}"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


# --- Model Switching --- #
async def set_model(update: Update, context: ContextTypes.DEFAULT_TYPE, model: str, name: str):
    user_id = update.message.from_user.id
    current_model[user_id] = model
    await update.message.reply_text(f"✅ Switched to *{name}*", parse_mode="Markdown")


async def gpt5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_model(update, context, "gpt-5", "GPT‑5")


async def gpt5thinking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_model(update, context, "gpt-5-thinking", "GPT‑5 Thinking")


async def claude(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_model(update, context, "claude-sonnet-4", "Claude Sonnet 4")


async def gemini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_model(update, context, "gemini-2.5-pro", "Gemini 2.5 Pro")


async def grok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await set_model(update, context, "grok-4", "Grok 4")


# --- AI Message handler (with memory & safe stats) --- #
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_message = update.message.text
    model = current_model.get(user_id, "gpt-5")

    # Init memory and stats if missing
    if user_id not in user_history:
        user_history[user_id] = []
    if user_id not in user_stats:
        user_stats[user_id] = {"prompt": 0, "completion": 0, "total": 0}

    # Add user message
    user_history[user_id].append({"role": "user", "content": user_message})

    # Enforce memory limit
    if len(user_history[user_id]) > MAX_MEMORY * 2:
        user_history[user_id] = user_history[user_id][-MAX_MEMORY * 2:]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=user_history[user_id]
        )
        reply = response.choices[0].message.content

        # Add assistant reply to history
        user_history[user_id].append({"role": "assistant", "content": reply})

        # ✅ Safe usage handling
        usage = getattr(response, "usage", None)
        if usage:
            prompt_tokens = usage.prompt_tokens or 0
            completion_tokens = usage.completion_tokens or 0
            total_tokens = usage.total_tokens or 0

            user_stats[user_id]["prompt"] += prompt_tokens
            user_stats[user_id]["completion"] += completion_tokens
            user_stats[user_id]["total"] += total_tokens
        else:
            print("⚠️ No usage info returned for this model")

        # Enforce memory limit after assistant response
        if len(user_history[user_id]) > MAX_MEMORY * 2:
            user_history[user_id] = user_history[user_id][-MAX_MEMORY * 2:]

    except Exception as e:
        reply = f"⚠️ AI Error: {str(e)}"

    await update.message.reply_text(reply)


# --- Main --- #
def main():
    app = Application.builder().token(TOKEN).build()

    # Core commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("model", current_model_cmd))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stats", stats))

    # Model switching
    app.add_handler(CommandHandler("gpt5", gpt5))
    app.add_handler(CommandHandler("gpt5thinking", gpt5thinking))
    app.add_handler(CommandHandler("claude", claude))
    app.add_handler(CommandHandler("gemini", gemini))
    app.add_handler(CommandHandler("grok", grok))

    # Catch all text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Bot is running with Abacus.AI RouteLLM + memory + stats...")
    app.run_polling()


if __name__ == "__main__":
    main()
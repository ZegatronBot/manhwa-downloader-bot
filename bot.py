# bot.py
import requests
from bs4 import BeautifulSoup
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from fpdf import FPDF
from io import BytesIO
import os

BOT_TOKEN = os.environ["BOT_TOKEN"]
BASE_URL = "https://olympustaff.com"

# Step 1: /start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📚 Send me a manhwa name to search:")

# Step 2: Search manhwa
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().replace(" ", "+")
    url = f"{BASE_URL}/search?q={query}"
    resp = requests.get(url)
    soup = BeautifulSoup(resp.text, "html.parser")

    results = []
    for a in soup.select("a.series-title"):  # adapt selector if needed
        title = a.text.strip()
        link = a['href']
        results.append((title, link))

    if not results:
        await update.message.reply_text("❌ No results found.")
        return

    buttons = [
        [InlineKeyboardButton(r[0], callback_data=f"m_{i}")] for i, r in enumerate(results)
    ]
    context.user_data['search_results'] = results
    await update.message.reply_text("🔍 Search results:", reply_markup=InlineKeyboardMarkup(buttons))

# Step 3: Show chapters
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("m_"):  # manhwa selected
        idx = int(data.split("_")[1])
        title, link = context.user_data['search_results'][idx]
        resp = requests.get(link)
        soup = BeautifulSoup(resp.text, "html.parser")

        chapters = []
        for a in soup.select("a.chapter-title"):  # adapt selector if needed
            chap_title = a.text.strip()
            chap_link = a['href']
            chapters.append((chap_title, chap_link))

        if not chapters:
            await query.edit_message_text("❌ No chapters found.")
            return

        buttons = [
            [InlineKeyboardButton(c[0], callback_data=f"c_{i}")] for i, c in enumerate(chapters)
        ]
        context.user_data['chapters'] = chapters
        await query.edit_message_text("📖 Select chapter:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("c_"):  # chapter selected
        idx = int(data.split("_")[1])
        chap_title, chap_link = context.user_data['chapters'][idx]

        await query.edit_message_text(f"⬇️ Downloading {chap_title} ...")

        # Fetch chapter images
        resp = requests.get(chap_link)
        soup = BeautifulSoup(resp.text, "html.parser")
        images = [img['src'] for img in soup.select("div.image_list img")]

        pdf = FPDF()
        pdf.set_auto_page_break(0)

        for img_url in images:
            img_data = requests.get(img_url).content
            pdf.add_page()
            pdf.image(BytesIO(img_data), x=0, y=0, w=210, h=297)  # A4 size

        pdf_buffer = BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)

        await query.message.reply_document(document=pdf_buffer, filename=f"{chap_title}.pdf")

# Main
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", start))
app.add_handler(CommandHandler("search", search))
app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()

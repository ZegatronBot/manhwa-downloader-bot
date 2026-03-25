import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

TOKEN = "8658154819:AAHe_8LLpT7SPz7qca6wKCDbsJqqe38hSok"

# ---------------- SEARCH FUNCTION ----------------
def search_site(keyword):
    url = f"https://olympustaff.com/ajax/search?keyword={keyword}"
    headers = {"User-Agent": "Mozilla/5.0"}
    soup = BeautifulSoup(requests.get(url, headers=headers).text, "html.parser")

    results = []
    for a in soup.find_all("a"):
        title = a.find("h4")
        if title:
            results.append((title.text.strip(), a.get("href")))
    return results[:10]

# ---------------- GET CHAPTERS ----------------
def get_chapters(series_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    soup = BeautifulSoup(requests.get(series_url, headers=headers).text, "html.parser")

    chapters = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if "/series/" in href and "chapter" in text.lower():
            chapters.append((text, href))
    chapters = chapters[::-1]  # Chapter 1 first
    return chapters[:20]

# ---------------- EXTRACT IMAGES ----------------
def extract_images(chapter_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    soup = BeautifulSoup(requests.get(chapter_url, headers=headers).text, "html.parser")

    images = []
    for img in soup.find_all("img", class_="manga-chapter-img"):
        images.append(img["src"])
    return images

# ---------------- CREATE PDF ----------------
def create_pdf(image_urls):
    images = []
    for url in image_urls:
        resp = requests.get(url)
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        images.append(img)

    pdf_path = "chapter.pdf"
    if images:
        images[0].save(pdf_path, save_all=True, append_images=images[1:])
    return pdf_path

# ---------------- TELEGRAM BOT ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me the name of the manhwa you want to search:")

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text
    results = search_site(keyword)
    if not results:
        await update.message.reply_text("No results found.")
        return

    buttons = [[InlineKeyboardButton(title, callback_data=f"series|{link}")] for title, link in results]
    await update.message.reply_text("📚 Search results:", reply_markup=InlineKeyboardMarkup(buttons))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("series|"):
        series_url = data.split("|")[1]
        chapters = get_chapters(series_url)
        if not chapters:
            await query.edit_message_text("No chapters found.")
            return

        buttons = [[InlineKeyboardButton(title, callback_data=f"chap|{link}")] for title, link in chapters]
        await query.edit_message_text("📖 Choose chapter:", reply_markup=InlineKeyboardMarkup(buttons))

    elif data.startswith("chap|"):
        chapter_url = data.split("|")[1]
        await query.edit_message_text("Downloading chapter, please wait...")
        images = extract_images(chapter_url)
        pdf_path = create_pdf(images)
        await query.message.reply_document(open(pdf_path, "rb"))
        os.remove(pdf_path)

# ---------------- RUN BOT ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))
app.add_handler(CallbackQueryHandler(button))

print("Bot is running...")
app.run_polling()

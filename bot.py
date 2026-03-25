import os
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext
import time

TOKEN = "8658154819:AAHe_8LLpT7SPz7qca6wKCDbsJqqe38hSok"
CACHE_DIR = "cached_pdfs"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ------------------ Utilities ------------------
def get_chapters(series_url):
    """Detect all chapters perfectly and sort them by number."""
    soup = BeautifulSoup(requests.get(series_url, headers=HEADERS).text, "html.parser")
    chapters = []
    for a in soup.select("a[href*='/series/']"):
        href = a["href"]
        title = a.get_text(strip=True)
        if "chapter" in title.lower() or title.lower().startswith("ch"):
            try:
                num = float(title.lower().replace("chapter", "").replace("ch", "").strip())
            except:
                num = 0
            chapters.append((num, title, href))
    chapters.sort(key=lambda x: x[0])
    return [(t[1], t[2]) for t in chapters]

def get_chapter_images(chapter_url):
    """Extract all image URLs of a chapter."""
    soup = BeautifulSoup(requests.get(chapter_url, headers=HEADERS).text, "html.parser")
    imgs = []
    for img in soup.select(".reading-content img.manga-chapter-img"):
        src = img.get("src")
        if src:
            imgs.append(src)
    return imgs

def download_images_to_pdf(img_urls, pdf_path, update=None, chat_id=None, context=None):
    """Download images and convert to PDF with progress."""
    pdf = FPDF()
    total = len(img_urls)
    for idx, url in enumerate(img_urls, 1):
        img_data = requests.get(url, headers=HEADERS).content
        img_path = f"temp_{idx}.webp"
        with open(img_path, "wb") as f:
            f.write(img_data)
        pdf.add_page()
        pdf.image(img_path, x=0, y=0, w=210)  # full A4 width
        os.remove(img_path)
        if update and context:
            progress = int((idx / total) * 100)
            context.bot.send_message(chat_id, f"Progress: {progress}%")
            time.sleep(0.2)  # delay between updates
    pdf.output(pdf_path)

# ------------------ Bot Handlers ------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Send the series URL to get the chapter list."
    )

def handle_series_url(update: Update, context: CallbackContext):
    url = update.message.text.strip()
    try:
        chapters = get_chapters(url)
        if not chapters:
            update.message.reply_text("No chapters found.")
            return
        buttons = [
            [InlineKeyboardButton(t[0], callback_data=t[1])] for t in chapters
        ]
        update.message.reply_text(
            "Select a chapter:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        context.user_data["series_url"] = url
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def handle_chapter_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    chapter_url = query.data
    chapter_name = chapter_url.split("/")[-1]
    pdf_path = os.path.join(CACHE_DIR, f"{chapter_name}.pdf")
    
    if os.path.exists(pdf_path):
        query.edit_message_text("PDF already cached. Sending...")
        context.bot.send_document(query.message.chat.id, open(pdf_path, "rb"))
        return

    query.edit_message_text("Downloading chapter and converting to PDF...")
    img_urls = get_chapter_images(chapter_url)
    if not img_urls:
        query.edit_message_text("No images found for this chapter.")
        return
    download_images_to_pdf(img_urls, pdf_path, update, query.message.chat.id, context)
    context.bot.send_document(query.message.chat.id, open(pdf_path, "rb"))

# ------------------ Main ------------------
def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(filters=None, callback=handle_series_url))
    dp.add_handler(CallbackQueryHandler(handle_chapter_selection))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()

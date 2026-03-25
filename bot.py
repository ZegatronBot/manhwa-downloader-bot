import os
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
import asyncio

TOKEN = "8658154819:AAHe_8LLpT7SPz7qca6wKCDbsJqqe38hSok"
CACHE_DIR = "cached_pdfs"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

HEADERS = {"User-Agent": "Mozilla/5.0"}

# ------------------ Utilities ------------------
def get_chapters(series_url):
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
    soup = BeautifulSoup(requests.get(chapter_url, headers=HEADERS).text, "html.parser")
    imgs = []
    for img in soup.select(".reading-content img.manga-chapter-img"):
        src = img.get("src")
        if src:
            imgs.append(src)
    return imgs

def download_images_to_pdf(img_urls, pdf_path, progress_callback=None):
    pdf = FPDF()
    total = len(img_urls)
    for idx, url in enumerate(img_urls, 1):
        img_data = requests.get(url, headers=HEADERS).content
        img_path = f"temp_{idx}.webp"
        with open(img_path, "wb") as f:
            f.write(img_data)
        pdf.add_page()
        pdf.image(img_path, x=0, y=0, w=210)
        os.remove(img_path)
        if progress_callback:
            progress_callback(idx, total)
    pdf.output(pdf_path)

# ------------------ Bot Handlers ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send the series URL to get the chapter list.")

async def handle_series_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    try:
        chapters = get_chapters(url)
        if not chapters:
            await update.message.reply_text("No chapters found.")
            return

        # Store chapters in user_data
        context.user_data["chapters"] = chapters

        buttons = [
            [InlineKeyboardButton(f"{idx+1}. {chap[0]}", callback_data=str(idx))]
            for idx, chap in enumerate(chapters[:20])  # show first 20 for simplicity
        ]
        await update.message.reply_text(
            "Select a chapter (first 20 shown, send number for more):",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        context.user_data["series_url"] = url
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def handle_chapter_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data)
    chapters = context.user_data.get("chapters")
    if not chapters:
        await query.edit_message_text("No chapters stored. Send series URL first.")
        return
    chapter_name, chapter_url = chapters[idx]
    pdf_path = os.path.join(CACHE_DIR, f"{chapter_name}.pdf")

    if os.path.exists(pdf_path):
        await query.edit_message_text("PDF already cached. Sending...")
        await context.bot.send_document(query.message.chat.id, open(pdf_path, "rb"))
        return

    await query.edit_message_text(f"Downloading chapter '{chapter_name}' and converting to PDF...")

    img_urls = get_chapter_images(chapter_url)
    if not img_urls:
        await query.edit_message_text("No images found for this chapter.")
        return

    # Progress callback
    async def progress_callback(idx_done, total):
        await query.edit_message_text(f"Downloading page {idx_done}/{total}...")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, download_images_to_pdf, img_urls, pdf_path, lambda i, t: asyncio.run_coroutine_threadsafe(progress_callback(i, t), loop))
    await context.bot.send_document(query.message.chat.id, open(pdf_path, "rb"))

# ------------------ Main ------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_series_url))
    app.add_handler(CallbackQueryHandler(handle_chapter_selection))
    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()

import requests
import asyncio
import os
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from PIL import Image
from io import BytesIO

BOT_TOKEN = "8658154819:AAHe_8LLpT7SPz7qca6wKCDbsJqqe38hSok"
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)


# 🔍 Search
def search_site(keyword):
    url = f"https://olympustaff.com/ajax/search?keyword={keyword}"
    headers = {"User-Agent": "Mozilla/5.0"}

    soup = BeautifulSoup(requests.get(url, headers=headers).text, "html.parser")

    for a in soup.find_all("a"):
        return a.get("href")

    return None


# 📚 Get chapters list (CLEAN TITLES)
def get_chapters(series_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    soup = BeautifulSoup(requests.get(series_url, headers=headers).text, "html.parser")

    chapters = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.text.strip()
        if "/series/" in href and text.lower().startswith("chapter"):
            chapters.append((text, href))

    # sort by chapter number if possible
    def chapter_number(title):
        import re
        m = re.search(r"\d+", title)
        return int(m.group()) if m else 0

    chapters.sort(key=lambda x: chapter_number(x[0]))
    return chapters[:10]  # limit


# 🖼 Extract images
def extract_images(chapter_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    soup = BeautifulSoup(requests.get(chapter_url, headers=headers).text, "html.parser")
    return [img["src"] for img in soup.find_all("img", class_="manga-chapter-img")]


# 📄 Create PDF
def create_pdf(image_urls, filename):
    images = []
    for url in image_urls:
        img_data = requests.get(url).content
        img = Image.open(BytesIO(img_data)).convert("RGB")
        images.append(img)
    if images:
        images[0].save(filename, save_all=True, append_images=images[1:])


# 💬 Handle search
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip()
    msg = await update.message.reply_text("🔍 Searching...")

    series_url = search_site(keyword)

    if not series_url:
        await msg.edit_text("❌ No results")
        return

    chapters = get_chapters(series_url)

    if not chapters:
        await msg.edit_text("❌ No chapters found")
        return

    buttons = [
        [InlineKeyboardButton(f"{c[0]}", callback_data=c[1])]
        for c in chapters
    ]

    await msg.edit_text("📚 Choose a chapter:", reply_markup=InlineKeyboardMarkup(buttons))


# 🔘 Handle chapter click
async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chapter_url = query.data
    msg = await query.edit_message_text("📥 Preparing...")

    file_id = chapter_url.split("/")[-1]
    pdf_path = f"{CACHE_DIR}/{file_id}.pdf"

    if os.path.exists(pdf_path):
        await msg.edit_text("⚡ Sending from cache...")
        await query.message.reply_document(open(pdf_path, "rb"))
        return

    await msg.edit_text("📥 Downloading images...")
    images = extract_images(chapter_url)

    if not images:
        await msg.edit_text("❌ No images found")
        return

    total = len(images)
    pil_images = []

    for i, url in enumerate(images):
        img_data = requests.get(url).content
        img = Image.open(BytesIO(img_data)).convert("RGB")
        pil_images.append(img)
        if i % 3 == 0:
            await msg.edit_text(f"📊 Downloading: {i+1}/{total}")
            await asyncio.sleep(0.2)

    await msg.edit_text("📄 Creating PDF...")
    pil_images[0].save(pdf_path, save_all=True, append_images=pil_images[1:])

    await msg.edit_text("📤 Sending...")
    await query.message.reply_document(open(pdf_path, "rb"))

    await msg.edit_text("✅ Done")


# 🚀 Run bot
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(handle_button))
app.run_polling()

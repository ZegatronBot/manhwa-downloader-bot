import requests
import asyncio
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from PIL import Image
from io import BytesIO

BOT_TOKEN = "8658154819:AAHe_8LLpT7SPz7qca6wKCDbsJqqe38hSok"


def search_site(keyword):
    url = f"https://olympustaff.com/ajax/search?keyword={keyword}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://olympustaff.com/"
    }

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    for a in soup.find_all("a"):
        link = a.get("href")
        if link:
            return link  # first result only

    return None


def get_first_chapter(series_url):
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(series_url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    # find first chapter link
    chap = soup.find("a", href=True)
    if chap:
        return chap["href"]

    return None


def extract_images(chapter_url):
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(chapter_url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    images = []

    for img in soup.find_all("img", class_="manga-chapter-img"):
        src = img.get("src")
        if src:
            images.append(src)

    return images


def create_pdf(image_urls):
    images = []

    for url in image_urls:
        img_data = requests.get(url).content
        img = Image.open(BytesIO(img_data)).convert("RGB")
        images.append(img)

    pdf_path = "chapter.pdf"

    if images:
        images[0].save(pdf_path, save_all=True, append_images=images[1:])

    return pdf_path


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip()

    msg = await update.message.reply_text("🔍 Searching...")

    series_url = search_site(keyword)

    if not series_url:
        await msg.edit_text("❌ No results")
        return

    await msg.edit_text("📖 Getting first chapter...")

    chapter_url = get_first_chapter(series_url)

    if not chapter_url:
        await msg.edit_text("❌ No chapter found")
        return

    await msg.edit_text("📥 Downloading images...")

    images = extract_images(chapter_url)

    if not images:
        await msg.edit_text("❌ No images found")
        return

    await msg.edit_text("📄 Creating PDF...")

    pdf_path = create_pdf(images)

    await msg.edit_text("📤 Sending PDF...")

    with open(pdf_path, "rb") as f:
        await update.message.reply_document(f)

    await msg.edit_text("✅ Done")


app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()

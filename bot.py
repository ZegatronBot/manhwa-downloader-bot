import requests
import asyncio
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

BOT_TOKEN = "8658154819:AAHe_8LLpT7SPz7qca6wKCDbsJqqe38hSok"


def search_site(keyword):
    url = f"https://olympustaff.com/ajax/search?keyword={keyword}"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "*/*",
        "Referer": "https://olympustaff.com/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
    except:
        return []

    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for a in soup.find_all("a"):
        title_tag = a.find("h4")
        chapter_tag = a.find("p")

        if title_tag:
            results.append({
                "title": title_tag.text.strip(),
                "link": a.get("href"),
                "chapters": chapter_tag.text.strip() if chapter_tag else "Unknown"
            })

    return results


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip()

    msg = await update.message.reply_text(f"🔍 Searching: {keyword}...")

    results = search_site(keyword)

    if not results:
        await msg.edit_text("❌ No results found.")
        return

    await msg.edit_text(f"✅ Found {len(results)} results:")

    for item in results[:10]:
        text = f"📚 {item['title']}\n📖 {item['chapters']}"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open", url=item['link'])]
        ])

        await update.message.reply_text(text, reply_markup=keyboard)

        await asyncio.sleep(0.2)


app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
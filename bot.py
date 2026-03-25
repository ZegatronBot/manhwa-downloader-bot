import os
import logging
import asyncio
import aiohttp
import re
from io import BytesIO
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Spacer
from reportlab.lib.units import inch
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from bs4 import BeautifulSoup

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
BASE_URL   = "https://olympustaff.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) "
        "Gecko/20100101 Firefox/148.0"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json;charset=UTF-8",
    "Referer": BASE_URL,
}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Scraping helpers ─────────────────────────────────────────────────────────

async def search_manhwa(keyword: str) -> list[dict]:
    """Search olympustaff and return list of {title, url, cover, chapters}."""
    url = f"{BASE_URL}/ajax/search"
    params = {"keyword": keyword}
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(url, params=params) as resp:
            html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")
    results = []
    for a in soup.find_all("a", href=True):
        img_tag = a.find("img")
        h4_tag  = a.find("h4")
        p_tag   = a.find("p")
        if not (img_tag and h4_tag):
            continue
        # extract chapter count
        chap_text = p_tag.get_text(strip=True) if p_tag else ""
        chap_num  = re.search(r"\d+", chap_text)
        results.append({
            "title":    h4_tag.get_text(strip=True),
            "url":      a["href"],
            "cover":    img_tag.get("src", ""),
            "chapters": chap_num.group() if chap_num else "?",
            "slug":     a["href"].rstrip("/").split("/")[-1],
        })
    return results


async def get_series_details(series_url: str) -> dict:
    """Scrape the series page and return details + chapter list."""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(series_url) as resp:
            html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else "Unknown"

    # Cover
    cover_img = soup.find("img", class_=re.compile(r"thumb|cover|poster", re.I))
    cover = cover_img["src"] if cover_img else ""

    # Description
    desc_tag = soup.find(class_=re.compile(r"summary|description|desc|synopsis", re.I))
    description = desc_tag.get_text(strip=True)[:500] if desc_tag else "No description."

    # Chapters  – olympustaff lists them as <a href="/series/slug/NUMBER">
    slug = series_url.rstrip("/").split("/")[-1]
    chapter_links = soup.find_all(
        "a", href=re.compile(rf"/series/{re.escape(slug)}/\d+")
    )
    chapters = []
    seen = set()
    for a in chapter_links:
        href = a["href"]
        if href in seen:
            continue
        seen.add(href)
        num_match = re.search(r"/(\d+(?:\.\d+)?)$", href)
        num = num_match.group(1) if num_match else href.split("/")[-1]
        label = a.get_text(strip=True) or f"Chapter {num}"
        chapters.append({"label": label, "url": f"{BASE_URL}{href}", "num": num})

    # Reverse so newest is last (ascending order)
    chapters = list(reversed(chapters))

    return {
        "title":       title,
        "cover":       cover,
        "description": description,
        "chapters":    chapters,
        "slug":        slug,
    }


async def get_chapter_images(chapter_url: str) -> list[str]:
    """Return list of image URLs for a chapter."""
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        async with session.get(chapter_url) as resp:
            html = await resp.text()

    soup = BeautifulSoup(html, "html.parser")
    images = []
    for img in soup.find_all("img", class_="manga-chapter-img"):
        src = img.get("src", "").strip()
        if src:
            images.append(src)
    return images


async def download_image(session: aiohttp.ClientSession, url: str) -> bytes | None:
    """Download a single image, return bytes or None on failure."""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                return await resp.read()
    except Exception as e:
        logger.warning(f"Failed to download {url}: {e}")
    return None


async def images_to_pdf(image_urls: list[str], title: str) -> BytesIO:
    """Download all chapter images and combine into a PDF (BytesIO)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=0, rightMargin=0,
        topMargin=0,  bottomMargin=0,
    )
    page_w, page_h = A4
    story = []

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        tasks  = [download_image(session, u) for u in image_urls]
        raw_images = await asyncio.gather(*tasks)

    for data in raw_images:
        if not data:
            continue
        try:
            pil_img = Image.open(BytesIO(data)).convert("RGB")
            img_w, img_h = pil_img.size
            # Scale to fit page width
            scale   = page_w / img_w
            disp_w  = page_w
            disp_h  = img_h * scale
            tmp = BytesIO()
            pil_img.save(tmp, format="JPEG", quality=85)
            tmp.seek(0)
            story.append(RLImage(tmp, width=disp_w, height=disp_h))
        except Exception as e:
            logger.warning(f"Image processing error: {e}")

    doc.build(story)
    buf.seek(0)
    return buf


# ── Bot handlers ─────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Manhwa Bot*\n\n"
        "Send me a manhwa title to search for it.\n"
        "Example: `Solo Leveling`",
        parse_mode="Markdown",
    )


async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    msg = await update.message.reply_text(f"🔍 Searching for *{query}*…", parse_mode="Markdown")

    results = await search_manhwa(query)
    if not results:
        await msg.edit_text("❌ No results found. Try a different keyword.")
        return

    # Store results in user_data
    context.user_data["search_results"] = results

    keyboard = []
    for i, r in enumerate(results[:8]):  # max 8 results
        keyboard.append([
            InlineKeyboardButton(
                f"📖 {r['title']} ({r['chapters']} ch)",
                callback_data=f"series:{i}",
            )
        ])

    await msg.edit_text(
        f"✅ Found *{len(results)}* result(s):\n\nChoose a series:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def handle_series_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split(":")[1])
    results = context.user_data.get("search_results", [])
    if idx >= len(results):
        await query.edit_message_text("❌ Invalid selection.")
        return

    series = results[idx]
    await query.edit_message_text(f"⏳ Loading *{series['title']}*…", parse_mode="Markdown")

    details = await get_series_details(series["url"])
    context.user_data["current_series"] = details
    context.user_data["chapter_page"]   = 0

    await send_series_details(query.message, details, page=0, edit=True)


async def send_series_details(
    message, details: dict, page: int = 0, edit: bool = False
):
    chapters  = details["chapters"]
    per_page  = 10
    total_pages = max(1, (len(chapters) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))

    start_i = page * per_page
    end_i   = start_i + per_page
    page_chapters = chapters[start_i:end_i]

    text = (
        f"📚 *{details['title']}*\n\n"
        f"{details['description']}\n\n"
        f"📄 *{len(chapters)} Chapters* | Page {page + 1}/{total_pages}"
    )

    keyboard = []
    for ch in page_chapters:
        keyboard.append([
            InlineKeyboardButton(
                ch["label"] or f"Chapter {ch['num']}",
                callback_data=f"chapter:{ch['num']}",
            )
        ])

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{page + 1}"))
    if nav_row:
        keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔍 New Search", callback_data="new_search")])

    markup = InlineKeyboardMarkup(keyboard)

    if edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


async def handle_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    page    = int(query.data.split(":")[1])
    details = context.user_data.get("current_series")
    if not details:
        await query.edit_message_text("❌ Session expired. Please search again.")
        return

    context.user_data["chapter_page"] = page
    await send_series_details(query.message, details, page=page, edit=True)


async def handle_chapter_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chap_num = query.data.split(":")[1]
    details  = context.user_data.get("current_series")
    if not details:
        await query.edit_message_text("❌ Session expired. Please search again.")
        return

    # Find the chapter
    chapter = next(
        (c for c in details["chapters"] if c["num"] == chap_num), None
    )
    if not chapter:
        await query.edit_message_text("❌ Chapter not found.")
        return

    slug  = details["slug"]
    title = details["title"]
    await query.edit_message_text(
        f"⏳ Fetching Chapter {chap_num} of *{title}*…\n"
        "This may take a moment, please wait.",
        parse_mode="Markdown",
    )

    chapter_url = chapter["url"]
    image_urls  = await get_chapter_images(chapter_url)

    if not image_urls:
        await query.message.edit_text(
            "❌ Could not find images for this chapter. "
            "The site may have changed its structure."
        )
        return

    await query.message.edit_text(
        f"📥 Downloading *{len(image_urls)}* pages and building PDF…",
        parse_mode="Markdown",
    )

    try:
        pdf_buf = await images_to_pdf(image_urls, title)
        filename = f"{slug}_ch{chap_num}.pdf"
        await query.message.reply_document(
            document=InputFile(pdf_buf, filename=filename),
            caption=f"📖 *{title}* — Chapter {chap_num}",
            parse_mode="Markdown",
        )
        await query.message.edit_text(
            f"✅ Chapter {chap_num} sent!\n\n"
            "Use the buttons below to browse more chapters.",
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        await query.message.edit_text("❌ Failed to generate PDF. Please try again.")

    # Re-show the series page so user can pick another chapter
    page = context.user_data.get("chapter_page", 0)
    await send_series_details(query.message, details, page=page, edit=False)


async def handle_new_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 Send me a manhwa title to search for it."
    )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    if data.startswith("series:"):
        await handle_series_select(update, context)
    elif data.startswith("chapter:"):
        await handle_chapter_select(update, context)
    elif data.startswith("page:"):
        await handle_page(update, context)
    elif data == "new_search":
        await handle_new_search(update, context)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))
    logger.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()

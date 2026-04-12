#!/usr/bin/env python3
"""🌐 VoidManga Web Manager v9 - Direct Browser Download & Streaming PDF"""
import os, sys, re, uuid, tempfile, shutil, threading, time, urllib.parse
from typing import Optional, List, Literal
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup
from PIL import Image
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="VoidManga")

# Add CORS (allow your Render domain + localhost for testing)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with ["https://yourapp.onrender.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────
# Config & State
# ─────────────────────────────────────────────────────────────
MANGA_LIST_FILE = "manga_output.txt"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ar;q=0.8',
    'Referer': 'https://olympustaff.com/',
    'Connection': 'keep-alive',
}
session = requests.Session()
session.headers.update(HEADERS)

db_lock = threading.Lock()
MANGA_DB = []

# ─────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────
def sanitize_name(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name.strip('_. ') or 'untitled'

def load_database():
    global MANGA_DB
    if not os.path.exists(MANGA_LIST_FILE):
        print(f"⚠️ {MANGA_LIST_FILE} missing.")
        return
    with open(MANGA_LIST_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    with db_lock:
        MANGA_DB.clear()
        for block in content.split("-" * 100):
            m = {}
            for line in block.strip().splitlines():
                if ':' in line:
                    k, _, v = line.partition(':')
                    if k.strip().lower() in ['title','cover image','link','status','type']:
                        m[k.strip().lower()] = v.strip()
            if m.get('title') and m.get('link'):
                MANGA_DB.append(m)
    print(f"✅ Loaded {len(MANGA_DB)} manga.")

def extract_slug(url: str) -> str:
    return url.rstrip('/').split('/')[-1]

def parse_chapter_input(inp: str) -> List[int]:
    clean = inp.replace(' ', '')
    if '-' in clean:
        s, e = clean.split('-')
        if s.isdigit() and e.isdigit():
            start, end = int(s), int(e)
            return list(range(min(start, end), max(start, end) + 1))
    elif clean.isdigit():
        return [int(clean)]
    return []

# ─────────────────────────────────────────────────────────────
# 🌐 API Routes
# ─────────────────────────────────────────────────────────────
SortOption = Literal["title_asc", "title_desc", "status_asc", "type_asc", "recent"]

@app.get("/api/browse")
def api_browse(page: int = Query(1, ge=1), per_page: int = Query(15, ge=10, le=50), sort: SortOption = Query("title_asc"), search: Optional[str] = Query(None)):
    results = MANGA_DB[:]
    if search:
        q = search.lower()
        results = [m for m in results if q in m.get('title', '').lower()]
    if sort == "title_asc": results.sort(key=lambda x: x.get('title', '').lower())
    elif sort == "title_desc": results.sort(key=lambda x: x.get('title', '').lower(), reverse=True)
    elif sort == "status_asc": results.sort(key=lambda x: x.get('status', ''))
    elif sort == "type_asc": results.sort(key=lambda x: x.get('type', ''))

    total = len(results)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = min(page, total_pages)
    start, end = (page - 1) * per_page, page * per_page
    return {
        "data": [{"title": m["title"], "cover": m.get("cover image", ""), 
                  "slug": extract_slug(m["link"]), "status": m.get("status", ""), 
                  "type": m.get("type", "")} for m in results[start:end]],
        "pagination": {"page": page, "per_page": per_page, "total": total, 
                       "total_pages": total_pages, "has_next": end < total, "has_prev": page > 1},
        "filters": {"sort": sort, "search": search}
    }

@app.get("/", response_class=HTMLResponse)
@app.get("/manga/{slug}", response_class=HTMLResponse)
@app.get("/read/{slug}/{ch_num}", response_class=HTMLResponse)
# Add a health check endpoint (Render uses this)
@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "VoidManga"}

# In your download endpoint, reduce workers for free tier memory limits:
# Change ThreadPoolExecutor(max_workers=8) to max_workers=2 or 3
async def serve_ui():
    with open("index.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/api/details/{slug}")
def api_details(slug: str):
    d = {'title': slug, 'status': 'Unknown', 'type': 'Unknown', 'genres': '', 'description': ''}
    try:
        resp = session.get(f"https://olympustaff.com/series/{slug}", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for block in soup.find_all('div', class_='full-list-info'):
            sm = block.find_all('small')
            if len(sm) >= 2:
                lbl, val = sm[0].get_text(strip=True), sm[1].get_text(strip=True)
                if any(k in lbl for k in ['النوع', 'Type']): d['type'] = val
                elif any(k in lbl for k in ['الحالة', 'Status']): d['status'] = val
                elif any(k in lbl for k in ['الرسام', 'Artist']): d['artist'] = val
                elif any(k in lbl for k in ['التقييمات', 'Rating']): d['ratings'] = val
        if soup.find('div', class_='review-author-info'):
            d['genres'] = ' | '.join(a.get_text(strip=True) for a in soup.find_all('a', class_='subtitle') if a.get_text(strip=True))
        desc_div = soup.find('div', class_='review-content')
        if desc_div and desc_div.find('p'): d['description'] = desc_div.find('p').get_text(strip=True)
        ch_tab = soup.find('a', id='chapter-contact-tab')
        if ch_tab:
            m = re.search(r'\((\d+)\)', ch_tab.get_text())
            if m: d['chapter_count'] = m.group(1)
        img = soup.find('div', class_='limit').find('img') if soup.find('div', class_='limit') else None
        if img and img.get('src'): d['cover_image'] = img['src'].strip()
    except Exception: pass

    for manga in MANGA_DB:
        if extract_slug(manga['link']) == slug:
            d['cover_image'] = d.get('cover_image') or manga.get('cover image', '')
            if d['title'] == slug: d['title'] = manga.get('title', slug)
            if d['status'] == 'Unknown': d['status'] = manga.get('status', 'Unknown')
            if d['type'] == 'Unknown': d['type'] = manga.get('type', 'Unknown')
            break
    return d

@app.get("/api/chapters/{slug}")
def api_chapters(slug: str):
    try:
        resp = session.get(f"https://olympustaff.com/series/{slug}", timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        chapters = []
        seen = set()
        containers = soup.find_all(['div', 'ul'], class_=re.compile(r'chapter.*list|ch-list|listupd', re.I))
        if not containers: containers = [soup.find('div', id='chapterlist') or soup.find('div', class_='entry-content') or soup]
        for container in containers:
            for a in container.find_all('a', href=True):
                match = re.search(r'/(\d+)/?$', a['href'])
                if match:
                    ch_num = int(match.group(1))
                    if 0 < ch_num < 50000 and ch_num not in seen:
                        seen.add(ch_num)
                        chapters.append({"num": ch_num, "title": a.get_text(strip=True) or f"Chapter {ch_num}"})
        if chapters:
            max_ch = max(ch['num'] for ch in chapters)
            if len(chapters) < max_ch:
                chapters = [{"num": i, "title": f"Chapter {i}"} for i in range(max_ch, 0, -1)]
            else:
                chapters.sort(key=lambda x: x["num"], reverse=True)
        else:
            meta = soup.find('a', id='chapter-contact-tab')
            if meta:
                m = re.search(r'\((\d+)\)', meta.get_text())
                if m: max_ch = int(m.group(1))
                chapters = [{"num": i, "title": f"Chapter {i}"} for i in range(max_ch, 0, -1)]
        return {"chapters": chapters[:1000], "total": len(chapters)}
    except Exception as e:
        return {"error": str(e), "chapters": [], "total": 0}

@app.get("/api/chapter/{slug}/{ch_num}")
def api_chapter_images(slug: str, ch_num: int):
    try:
        headers = {'User-Agent': HEADERS['User-Agent'], 'Referer': f'https://olympustaff.com/series/{slug}/'}
        url = f"https://olympustaff.com/series/{slug}/{ch_num}"
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200: raise ValueError(f"HTTP {resp.status_code}")
        soup = BeautifulSoup(resp.text, 'html.parser')
        img_list = soup.find('div', class_='image_list')
        if not img_list: raise ValueError("Image list container not found.")
        images = [{'page': i, 'url': img['src'].strip()} 
                  for i, page in enumerate(img_list.find_all('div', class_='page-break'), 1) 
                  if (img := page.find('img', class_='manga-chapter-img'))]
        if not images: raise ValueError("No images found.")
        return {"images": images, "slug": slug, "ch_num": ch_num}
    except Exception as e:
        raise HTTPException(404, f"Failed to load Ch{ch_num}: {str(e)}")

@app.get("/api/image-proxy")
def proxy_image(url: str):
    if not url: raise HTTPException(400)
    try:
        headers = {'User-Agent': HEADERS['User-Agent'], 'Referer': 'https://olympustaff.com/', 'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8'}
        resp = requests.get(url, headers=headers, stream=True, timeout=20)
        resp.raise_for_status()
        ct = resp.headers.get('Content-Type', 'image/jpeg')
        return StreamingResponse(resp.iter_content(chunk_size=8192), media_type=ct)
    except Exception:
        raise HTTPException(404, "Image unavailable via proxy")

# ─────────────────────────────────────────────────────────────
# 📥 DIRECT BROWSER DOWNLOAD ENDPOINT (Streaming)
# ─────────────────────────────────────────────────────────────
@app.post("/api/download")
def direct_download(req: dict):
    import logging, time, os, urllib.parse, asyncio
    from pathlib import Path
    from fastapi import BackgroundTasks
    
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    slug = req.get("slug")
    title = req.get("title", "manga")
    chapters = parse_chapter_input(req.get("chapters", ""))
    if not chapters: 
        raise HTTPException(400, "Invalid chapter range")

    logger.info(f"📥 Starting download: {title} Ch{chapters[0]}{'-'+str(chapters[-1]) if len(chapters)>1 else ''}")
    
    # ✅ Use a persistent downloads folder instead of temp
    DOWNLOADS_DIR = Path("downloads")
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    
    all_images = []
    headers = {'User-Agent': HEADERS['User-Agent'], 'Referer': f'https://olympustaff.com/series/{slug}/'}
    
    # Download images chapter by chapter
    for ch in chapters:
        logger.info(f"  📖 Fetching chapter {ch}...")
        try:
            html = requests.get(f"https://olympustaff.com/series/{slug}/{ch}", headers=headers, timeout=20).text
            soup = BeautifulSoup(html, 'html.parser')
            img_list = soup.find('div', class_='image_list')
            if not img_list: 
                logger.warning(f"  ⚠️ No image list for Ch{ch}")
                continue
                
            images = [{'page': i, 'url': img['src'].strip()} 
                      for i, page in enumerate(img_list.find_all('div', class_='page-break'), 1) 
                      if (img := page.find('img', class_='manga-chapter-img'))]
            
            if not images:
                logger.warning(f"  ⚠️ No images found for Ch{ch}")
                continue
                
            ch_temp = DOWNLOADS_DIR / f"ch_{ch}"
            ch_temp.mkdir(exist_ok=True)
            
            def dl_img(u, p):
                try:
                    r = requests.get(u, headers=headers, timeout=0, stream=True)
                    r.raise_for_status()
                    ext = '.webp' if '.webp' in u.lower() else '.jpg'
                    fp = ch_temp / f"{p:04d}{ext}"
                    with open(fp, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            if chunk: f.write(chunk)
                    return True, fp
                except Exception as e:
                    logger.error(f"    ❌ Failed to download page {p}: {e}")
                    return False, None
            
            downloaded = 0
            with ThreadPoolExecutor(max_workers=3) as ex:
                futures = {ex.submit(dl_img, im['url'], im['page']): im for im in images}
                for fut in as_completed(futures):
                    success, path = fut.result()
                    if success and path:
                        all_images.append((ch, futures[fut]['page'], path))
                        downloaded += 1
            
            logger.info(f"  ✅ Ch{ch}: {downloaded}/{len(images)} images downloaded")
            
        except Exception as e:
            logger.error(f"  ❌ Failed to process Ch{ch}: {e}")
            continue
    
    if not all_images:
        raise HTTPException(404, "No images found for selected chapters")
    
    # Sort and create PDF
    all_images.sort(key=lambda x: (x[0], x[1]))
    image_paths = [p for _, _, p in all_images]
    logger.info(f"📊 Total images: {len(image_paths)}")
    
    # Create PDF filename
    sanitized = sanitize_name(title)
    ch_start, ch_end = chapters[0], chapters[-1]
    pdf_filename = f"{sanitized}_Ch{ch_start}_to_{ch_end}.pdf" if ch_start != ch_end else f"{sanitized}_Ch{ch_start}.pdf"
    pdf_path = DOWNLOADS_DIR / pdf_filename
    
    # Create PDF with batching to manage memory
    batch_size = 50
    first_batch = True
    
    for i in range(0, len(image_paths), batch_size):
        batch = image_paths[i:i+batch_size]
        batch_imgs = []
        
        for p in batch:
            try:
                im = Image.open(p)
                if im.mode != 'RGB': 
                    im = im.convert('RGB')
                batch_imgs.append(im)
            except Exception as e:
                logger.warning(f"  ⚠️ Skipping corrupted image {p}: {e}")
                continue
        
        if batch_imgs:
            if first_batch:
                batch_imgs[0].save(pdf_path, "PDF", resolution=100, save_all=True, append_images=batch_imgs[1:])
                first_batch = False
            else:
                with Image.open(pdf_path) as base:
                    base.save(pdf_path, "PDF", resolution=100, save_all=True, append_images=batch_imgs)
        
        for im in batch_imgs:
            im.close()
        batch_imgs.clear()
        
        logger.info(f"📑 Processed batch {i//batch_size + 1}/{(len(image_paths)+batch_size-1)//batch_size}")
    
    if not pdf_path.exists() or pdf_path.stat().st_size == 0:
        raise HTTPException(500, "Failed to create PDF")
    
    # Stream the file
    def iterfile():
        with open(pdf_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk
    
    logger.info(f"✅ PDF ready: {pdf_filename} ({pdf_path.stat().st_size/1024/1024:.1f} MB)")
    
    # Return streaming response with proper headers
    response = StreamingResponse(
        iterfile(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{urllib.parse.quote(pdf_filename)}',
            "Content-Length": str(pdf_path.stat().st_size)
        }
    )
    
    # ✅ Schedule cleanup AFTER response is sent (5 second delay)
    async def cleanup_after_response():
        await asyncio.sleep(5)  # Wait for browser to start download
        try:
            pdf_path.unlink(missing_ok=True)
            # Also clean up chapter temp folders
            for ch in chapters:
                ch_temp = DOWNLOADS_DIR / f"ch_{ch}"
                if ch_temp.exists():
                    shutil.rmtree(ch_temp, ignore_errors=True)
            logger.info(f"🧹 Cleaned up: {pdf_filename}")
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
    
    # Add cleanup task to response background
    response.background = BackgroundTasks()
    response.background.add_task(cleanup_after_response)
    
    return response

@app.on_event("startup")
def startup(): load_database()
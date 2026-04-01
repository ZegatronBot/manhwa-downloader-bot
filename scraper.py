import requests
from bs4 import BeautifulSoup

BASE = "https://olympustaff.com"

def search_manga(query):
    url = f"{BASE}/series?search={query}"
    res = requests.get(url, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")

    results = []

    for item in soup.select(".series-card"):
        title = item.select_one(".title").text.strip()
        link = item.find("a")["href"]

        results.append({
            "title": title,
            "link": BASE + link
        })

    return results


def get_chapters(series_url):
    res = requests.get(series_url, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")

    chapters = []

    for ch in soup.select(".chapter-list a"):
        title = ch.text.strip()
        link = ch["href"]

        chapters.append({
            "title": title,
            "link": BASE + link
        })

    return chapters


def get_images(chapter_url):
    res = requests.get(chapter_url, timeout=10)
    soup = BeautifulSoup(res.text, "html.parser")

    images = []

    for img in soup.select("img"):
        src = img.get("src")
        if src and "uploads/manga_" in src:
            images.append(src)

    return images

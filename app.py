from flask import Flask, render_template, request, send_file
from scraper import search_manga, get_chapters, get_images
from pdf import images_to_pdf
import os


app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/search")
def search():
    query = request.args.get("q")
    results = search_manga(query)
    return render_template("results.html", results=results)


@app.route("/chapters")
def chapters():
    url = request.args.get("url")
    ch = get_chapters(url)
    return render_template("chapters.html", chapters=ch)


@app.route("/download")
def download():
    url = request.args.get("url")

    images = get_images(url)
    pdf_file = images_to_pdf(images)

    return send_file(pdf_file, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

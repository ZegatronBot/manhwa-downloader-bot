import requests
from PIL import Image
from io import BytesIO

def images_to_pdf(image_urls, output="chapter.pdf"):
    images = []

    for url in image_urls:
        res = requests.get(url, timeout=10)
        img = Image.open(BytesIO(res.content)).convert("RGB")
        images.append(img)

    images[0].save(
        output,
        save_all=True,
        append_images=images[1:]
    )

    return output

<<<<<<< HEAD
from pathlib import Path

import webview

from api import PySentinelAPI


BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "web" / "index.html"


def main():
    if not INDEX_FILE.is_file():
        raise FileNotFoundError(f"Frontend not found: {INDEX_FILE}")

    api = PySentinelAPI()

    window = webview.create_window(
        title="PySentinel | Security Center",
        url=INDEX_FILE.as_uri(),
        js_api=api,
        width=1250,
        height=800,
        min_size=(900, 600),
        background_color="#0F111A",
    )

    api.set_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
=======
from pathlib import Path

import webview

from api import PySentinelAPI


BASE_DIR = Path(__file__).resolve().parent
INDEX_FILE = BASE_DIR / "web" / "index.html"


def main():
    if not INDEX_FILE.is_file():
        raise FileNotFoundError(f"Frontend not found: {INDEX_FILE}")

    api = PySentinelAPI()

    window = webview.create_window(
        title="PySentinel | Security Center",
        url=INDEX_FILE.as_uri(),
        js_api=api,
        width=1250,
        height=800,
        min_size=(900, 600),
        background_color="#0F111A",
    )

    api.set_window(window)
    webview.start(debug=False)


if __name__ == "__main__":
>>>>>>> 113abfb7e89e747a5927a33b4cb931806d6c83aa
    main()
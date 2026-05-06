import urllib.request
import requests
import base64
import os
import ssl
import certifi
import re
from urllib.parse import unquote
from urllib.parse import urlsplit, urlunsplit

# ---------------- SSL FIX (macOS) ----------------
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())


DEFAULT_PATH = "file/git_subs/default.txt"
WHITELIST_PATH = "file/git_subs/whiteList.txt"

OUT_VLESS = "file/git_keys/default/vless.txt"
OUT_SS = "file/git_keys/default/ss.txt"
OUT_WHITE = "file/git_keys/whiteList/keys.txt"
FLAG_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")


# ---------------- URL LIST ----------------
def load_urls(path):
    with open(path, "r", encoding="utf-8") as f:
        return [x.strip() for x in f if x.strip()]


# ---------------- URL NORMALIZATION ----------------
def normalize_url(url):
    raw = url.strip()

    # Fragments in source lists (e.g. #OBWL) are local anchors, not part of remote file path.
    if "#" in raw:
        raw = raw.split("#", 1)[0]

    # Common GitHub mistake: web blob URL instead of raw URL.
    if raw.startswith("https://github.com/") and "/blob/" in raw:
        raw = raw.replace("https://github.com/", "https://raw.githubusercontent.com/", 1)
        raw = raw.replace("/blob/", "/", 1)

    # Drop accidental trailing slash if it appears after query-only path.
    parts = urlsplit(raw)
    cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
    return cleaned


# ---------------- FETCH LAYER ----------------
def fetch_requests(url):
    try:
        r = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code == 200:
            return r.text
    except:
        return None


def fetch_urllib(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except:
        return None


def fetch(url):
    # 1 уровень — requests
    data = fetch_requests(url)
    if data:
        return data

    # 2 уровень — urllib fallback
    data = fetch_urllib(url)
    if data:
        return data

    print("FAILED:", url)
    return ""


# ---------------- CLEAN ----------------
def clean(line):
    raw = line.strip()
    if "#" not in raw:
        return raw

    base, fragment = raw.split("#", 1)
    desc = unquote(fragment)
    match = FLAG_RE.search(desc)
    if not match:
        return base.strip()
    # Keep only flag from old description so downstream formatter can rebuild
    # canonical description as: tg channel + number + flag.
    return f"{base.strip()}#{match.group(0)}"


# ---------------- BASE64 ----------------
def maybe_base64(text):
    if "vless://" in text or "ss://" in text:
        return text

    try:
        decoded = base64.b64decode(text + "==", validate=False)
        return decoded.decode("utf-8", errors="ignore")
    except:
        return text


# ---------------- EXTRACT ----------------
def extract(text):
    vless = []
    ss = []

    for line in text.splitlines():
        line = clean(line)

        if not line:
            continue

        # приоритет VLESS (чтобы не дублилось)
        if line.startswith("vless://"):
            vless.append(line)
            continue

        if line.startswith("ss://"):
            ss.append(line)

    return vless, ss


def dedupe(lst):
    return list(set(lst))


def ensure(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)


# ---------------- PROCESS PIPELINE ----------------
def process(urls):
    vless_all = []
    ss_all = []

    for original_url in urls:
        url = normalize_url(original_url)
        if url != original_url:
            print("fetch:", original_url, "->", url)
        else:
            print("fetch:", url)

        text = fetch(url)
        print("size:", len(text))

        text = maybe_base64(text)

        vless, ss = extract(text)

        print("found:", len(vless), len(ss))

        vless_all.extend(vless)
        ss_all.extend(ss)

    return dedupe(vless_all), dedupe(ss_all)


# ---------------- SAVE ----------------
def save(path, data):
    ensure(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(data))


# ---------------- MAIN ----------------
if __name__ == "__main__":
    default_urls = load_urls(DEFAULT_PATH)
    white_urls = load_urls(WHITELIST_PATH)

    # DEFAULT
    vless, ss = process(default_urls)

    save(OUT_VLESS, vless)
    save(OUT_SS, ss)

    print("\nDEFAULT RESULT:")
    print("vless:", len(vless))
    print("ss:", len(ss))

    # WHITELIST
    all_keys = dedupe(vless + ss)

    vless_w, ss_w = process(white_urls)

    save(OUT_WHITE, dedupe(all_keys + vless_w + ss_w))

    print("\nWHITELIST DONE")
    print("total keys:", len(dedupe(all_keys + vless_w + ss_w)))

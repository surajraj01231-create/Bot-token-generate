import os
import html
import json
import time
import random
import string
import threading
import requests
from flask import Flask, request, jsonify, redirect
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

BOT_TOKEN = "9080932798:AAFtYGGZOaG0E6Jxo_FmRx2qHuJ9_kMfNaI"
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

DB_FILE = "keys_db.json"
db_lock = threading.Lock()
CACHED_USERNAME = ""


def get_bot_username():
    global CACHED_USERNAME
    if CACHED_USERNAME:
        return CACHED_USERNAME
    try:
        res = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=8).json()
        if res.get("ok"):
            CACHED_USERNAME = res["result"]["username"]
    except Exception:
        pass
    return CACHED_USERNAME


def load_db():
    if not os.path.exists(DB_FILE):
        return {"tokens": {}, "keys": {}}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tokens": {}, "keys": {}}


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def gen_token(length=12):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


# 12 characters: small + capital + numbers + @#&*€¥$
def gen_strong_key(length=12):
    symbols = "@#&*€¥$"
    all_chars = string.ascii_lowercase + string.ascii_uppercase + string.digits + symbols
    key_list = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits),
        random.choice(symbols),
    ]
    key_list += random.choices(all_chars, k=length - 4)
    random.shuffle(key_list)
    return "".join(key_list)


def delete_tg_message_later(chat_id, message_id, delay=300):
    def _delete():
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
                timeout=10,
            )
        except Exception:
            pass

    t = threading.Timer(delay, _delete)
    t.daemon = True
    t.start()


@app.route("/")
def home():
    get_bot_username()
    if BOT_TOKEN and RENDER_URL:
        try:
            requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                params={"url": f"{RENDER_URL}/webhook"},
                timeout=8,
            )
        except Exception:
            pass
    return "Mr.Sanskari 24H Key Server is Live!"


# Arolinks ke baad user is link par aayega
@app.route("/claim")
def claim_redirect():
    bot_user = get_bot_username()
    if not bot_user:
        return "Bot username fetch nahi ho paya, page refresh karein.", 500

    token = gen_token(12)
    with db_lock:
        db = load_db()
        db["tokens"][token] = time.time() + 300  # 5 min valid
        save_db(db)

    return redirect(f"https://t.me/{bot_user}?start={token}")


# Telegram Bot Webhook
@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    msg = update.get("message", {})
    text = msg.get("text", "")
    chat_id = msg.get("chat", {}).get("id")

    if not chat_id or not text.startswith("/start"):
        return "ok"

    parts = text.split()
    if len(parts) < 2:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "❌ Direct start allowed nahi hai!\n\nApp mein 'GET FREE KEY' button par click karke aayein.",
            },
        )
        return "ok"

    token = parts[1].strip()
    now = time.time()

    with db_lock:
        db = load_db()
        exp = db["tokens"].get(token)
        if not exp or now > exp:
            if token in db["tokens"]:
                del db["tokens"][token]
                save_db(db)
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "⚠️ Yeh link expire ho chuka hai ya pehle use ho gaya hai!\nApp se dobara 'GET FREE KEY' dabayein.",
                },
            )
            return "ok"

        del db["tokens"][token]
        new_key = gen_strong_key(12)
        db["keys"][new_key] = {
            "created_at": now,
            "activated_at": None,
            "expires_at": None,
            "device_id": None,
        }
        save_db(db)

    safe_key = html.escape(new_key)
    reply_text = (
        f"🔥 <b>Mr.Sanskari 24-Hour Access Key</b>\n\n"
        f"🔑 Key: <code>{safe_key}</code>\n"
        f"⏳ Validity: <b>24 Hours</b> (Unlock karne ke baad)\n\n"
        f"⚠️ <i>Security ke liye yeh message 5 minute mein automatically delete ho jayega!</i>"
    )

    res = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": reply_text, "parse_mode": "HTML"},
    ).json()

    sent_msg_id = res.get("result", {}).get("message_id")
    if sent_msg_id:
        delete_tg_message_later(chat_id, sent_msg_id, delay=300)

    return "ok"


# App Dialog Box yahan se 24h key check karega
@app.route("/api.php")
def verify_key():
    key = request.args.get("key", "").strip()
    device_id = request.args.get("device_id", "").strip()
    now = time.time()

    if not key or not device_id:
        return jsonify({"status": False, "reason": "Key ya Device ID missing hai!"})

    with db_lock:
        db = load_db()
        info = db["keys"].get(key)

        if not info:
            return jsonify({"status": False, "reason": "Invalid Key! Sahi key dalein."})

        # Pehli baar unlock par 24 ghante ka timer shuru
        if info["device_id"] is None:
            info["device_id"] = device_id
            info["activated_at"] = now
            info["expires_at"] = now + 86400  # 24 Hours
            db["keys"][key] = info
            save_db(db)
            return jsonify({"status": True})

        # Dusre phone me block
        if info["device_id"] != device_id:
            return jsonify({"status": False, "reason": "Yeh Key kisi aur device mein use ho chuki hai!"})

        # 24 ghante poore hone par key delete -> user ko nayi key leni padegi
        if now > info["expires_at"]:
            del db["keys"][key]
            save_db(db)
            return jsonify({"status": False, "reason": "24 Hours poore ho gaye! Nayi Key lein."})

        return jsonify({"status": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

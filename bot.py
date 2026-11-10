"""Telegram bot: /start, Stars to'lovlari (long polling)."""
import asyncio, os, aiohttp
TOKEN = os.getenv("BOT_TOKEN", "")
URL = os.getenv("WEBAPP_URL", "")          # https://sizning-domen.uz
API = f"https://api.telegram.org/bot{TOKEN}/"

async def call(method, **p):
    async with aiohttp.ClientSession() as s:
        async with s.post(API + method, json=p, timeout=aiohttp.ClientTimeout(total=70)) as r:
            return (await r.json()).get("result")

async def me():
    r = await call("getMe")
    return r["username"] if r else ""

async def poll(credit):
    off = 0
    while True:
        try:
            ups = await call("getUpdates", offset=off, timeout=50,
                             allowed_updates=["message", "pre_checkout_query"]) or []
            for u in ups:
                off = u["update_id"] + 1
                if "pre_checkout_query" in u:
                    await call("answerPreCheckoutQuery", pre_checkout_query_id=u["pre_checkout_query"]["id"], ok=True)
                m = u.get("message")
                if not m:
                    continue
                sp = m.get("successful_payment")
                if sp and sp["invoice_payload"].startswith("stars:"):
                    await credit(sp["invoice_payload"][6:], "star", sp["total_amount"],
                                 "tg:" + sp["telegram_payment_charge_id"])
                elif (m.get("text") or "").startswith("/start"):
                    arg = m["text"][6:].strip()
                    url = URL + ("?ref=" + arg[4:] if arg.startswith("ref_") else "")
                    await call("sendMessage", chat_id=m["chat"]["id"],
                               text="🎮 Arena — aqlli o'yinlar / умные игры / smart games",
                               reply_markup={"inline_keyboard": [[{"text": "▶ Play", "web_app": {"url": url}}]]})
        except Exception as e:
            print("bot:", e)
            await asyncio.sleep(3)

"""Arena server: python server.py"""
import asyncio, json, os, re, sqlite3, hmac, hashlib, secrets
from urllib.parse import parse_qsl
from aiohttp import web
import bot, wallet

PORT = int(os.getenv("PORT", "3000")); TOKEN = bot.TOKEN
TEST = os.getenv("TEST_MODE") == "1"; FEE = 0.10; BOT_NAME = ""
GAMES = {"chess", "checkers", "connect4", "gomoku", "reversi"}
STAKES = {"star": [10, 50, 100, 250], "ton": [0.1, 0.25, 0.5, 1]}

db = sqlite3.connect("arena.db", check_same_thread=False); db.row_factory = sqlite3.Row
db.executescript("""CREATE TABLE IF NOT EXISTS users(uid TEXT PRIMARY KEY,name TEXT,star REAL DEFAULT 0,
ton REAL DEFAULT 0,games INT DEFAULT 0,wins INT DEFAULT 0,refs INT DEFAULT 0,ref_by TEXT,guest INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS tx(id TEXT PRIMARY KEY);""")
conns, queues = {}, {}

def user(uid):
    r = db.execute("SELECT * FROM users WHERE uid=?", (uid,)).fetchone()
    return dict(r) if r else None
def pub(u): return {k: u[k] for k in ("star", "ton", "games", "wins", "refs")}
def add(uid, cur, amt):
    assert cur in ("star", "ton")
    db.execute(f"UPDATE users SET {cur}=ROUND({cur}+?,2) WHERE uid=?", (amt, uid)); db.commit()

class C:
    def __init__(s, ws): s.ws = ws; s.uid = None; s.name = ""; s.q = None; s.t = None; s.seat = 0
async def send(c, o):
    try: await c.ws.send_str(json.dumps(o))
    except Exception: pass
async def bcast(o):
    for c in list(conns.values()): await send(c, o)

def verify(m):
    init = m.get("init") or ""
    if TOKEN and init:
        d = dict(parse_qsl(init)); h = d.pop("hash", "")
        chk = "\n".join(f"{k}={d[k]}" for k in sorted(d))
        key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        if hmac.compare_digest(hmac.new(key, chk.encode(), hashlib.sha256).hexdigest(), h):
            u = json.loads(d.get("user", "{}"))
            if u.get("id"): return "tg%s" % u["id"], u.get("first_name", "Player"), 0
    return "g" + re.sub(r"\W", "", str(m.get("uid", "x")))[:20], "", 1   # mehmon: depozit/stavka yo'q

async def credit(uid, cur, amt, txid):
    if not user(uid) or db.execute("SELECT 1 FROM tx WHERE id=?", (txid,)).fetchone(): return
    db.execute("INSERT INTO tx VALUES(?)", (txid,)); db.commit(); add(uid, cur, amt)
    c = conns.get(uid)
    if c: await send(c, {"t": "dep", "ok": True, "user": pub(user(uid)), cur: amt})

async def settle(t, w):
    if t["done"]: return
    t["done"] = True; cur, st = t["cur"], t["stake"]
    for i, uid in enumerate(t["u"]):
        amt = 0
        if cur != "free":
            amt = st if w == -1 else round(st * 2 * (1 - FEE), 2) if w == i else 0
            if amt: add(uid, cur, amt)
        db.execute("UPDATE users SET games=games+1,wins=wins+? WHERE uid=?", (1 if w == i else 0, uid)); db.commit()
        c = conns.get(uid)
        if c: await send(c, {"t": "paid", "user": pub(user(uid)), "amount": amt})

def dequeue(c):
    if c.q and c in queues.get(c.q, []): queues[c.q].remove(c)
    c.q = None

async def pair(key):
    q = queues[key]; g, cur, st = key
    while len(q) >= 2:
        a, b = q.pop(0), q.pop(0); ok = []
        for p in (a, b):
            if cur == "free" or user(p.uid)[cur] >= st: ok.append(p)
            else: await send(p, {"t": "err", "code": "balance"}); p.q = None
        if len(ok) < 2:
            for p in ok: q.insert(0, p)
            continue
        for p in ok:
            p.q = None
            if cur != "free": add(p.uid, cur, -st)
        t = {"u": [p.uid for p in ok], "p": ok, "cur": cur, "stake": st, "done": False, "res": {}}
        for i, p in enumerate(ok):
            p.t, p.seat = t, i
            await send(p, {"t": "me", "user": pub(user(p.uid))})
            await send(p, {"t": "start", "seat": i, "players": [{"name": x.name} for x in ok],
                           "game": g, "cur": cur, "stake": st, "max": 2})
    if len(q) == 1: await send(q[0], {"t": "wait", "have": 1, "max": 2})

async def leave(c):
    t = c.t; c.t = None
    if t and not t["done"]:
        await send(t["p"][1 - c.seat], {"t": "opp_left"}); await settle(t, 1 - c.seat)

async def drop(c):
    if not c.uid: return
    dequeue(c); await leave(c)
    if conns.get(c.uid) is c: del conns[c.uid]
    c.uid = None; await bcast({"t": "online", "n": len(conns)})

async def on_msg(c, m):
    k = m.get("t")
    if k == "hello":
        uid, nm, guest = verify(m)
        name = re.sub(r"[<>]", "", m.get("name") or nm or "Player")[:20]
        if not user(uid):
            ref = str(m.get("ref") or "")[:24]; okref = ref != uid and user(ref)
            db.execute("INSERT INTO users(uid,name,guest,ref_by) VALUES(?,?,?,?)", (uid, name, guest, ref if okref else None))
            if okref: db.execute("UPDATE users SET refs=refs+1 WHERE uid=?", (ref,))
        else: db.execute("UPDATE users SET name=? WHERE uid=?", (name, uid))
        db.commit()
        old = conns.get(uid)
        if old and old is not c: await drop(old); await old.ws.close()
        c.uid, c.name = uid, name; conns[uid] = c
        await send(c, {"t": "me", "user": pub(user(uid)), "bot": BOT_NAME, "test": TEST, "online": len(conns)})
        await bcast({"t": "online", "n": len(conns)}); return
    if not c.uid: return
    if k == "name":
        c.name = re.sub(r"[<>]", "", str(m.get("name", "")))[:20] or c.name
        db.execute("UPDATE users SET name=? WHERE uid=?", (c.name, c.uid)); db.commit()
    elif k == "quick":
        g, cur = m.get("game"), m.get("cur"); st = float(m.get("stake") or 0)
        if g not in GAMES or c.t and not c.t["done"]: return
        if cur == "free": st = 0
        elif st not in STAKES.get(cur, []): return
        elif user(c.uid)[cur] < st: return await send(c, {"t": "err", "code": "balance"})
        dequeue(c); key = (g, cur, st); queues.setdefault(key, []).append(c); c.q = key
        await send(c, {"t": "wait", "have": 1, "max": 2}); await pair(key)
    elif k == "cancel": dequeue(c)
    elif k == "move" and c.t and not c.t["done"]:
        await send(c.t["p"][1 - c.seat], {"t": "move", "d": m.get("d"), "from": c.seat})
    elif k == "chat" and c.t:
        txt = str(m.get("text", ""))[:200]
        for p in c.t["p"]: await send(p, {"t": "chat", "from": c.seat, "name": c.name, "text": txt})
    elif k == "result" and c.t and not c.t["done"]:
        w, t = m.get("winner"), c.t
        if w not in (-1, 0, 1): return
        t["res"][c.seat] = w
        if len(t["res"]) == 2: await settle(t, w if t["res"][0] == t["res"][1] else -1)
        else:   # ikkinchi o'yinchi 15 soniyada javob bermasa, birinchisining natijasi olinadi
            asyncio.get_running_loop().call_later(15, lambda: asyncio.create_task(settle(t, w)))
    elif k == "leave": await leave(c)
    elif k == "lb":
        rows = db.execute("SELECT uid,name,wins,games FROM users WHERE games>0 ORDER BY wins DESC,games ASC LIMIT 50")
        await send(c, {"t": "lb", "list": [dict(r) for r in rows]})
    elif k == "deposit":
        meth, amt = m.get("method"), float(m.get("amount") or 0)
        if not 0 < amt <= 10000: return
        if TEST: return await credit(c.uid, "ton" if meth == "ton" else "star", amt, secrets.token_hex(8))
        no = {"t": "dep", "ok": False}
        if not TOKEN or user(c.uid)["guest"]: return await send(c, no)
        if meth == "star":
            link = await wallet.stars_link(c.uid, int(amt)); await send(c, {**no, "link": link} if link else no)
        elif meth == "ton" and wallet.TON_ADDR:
            await send(c, {**no, "ton": {"addr": wallet.TON_ADDR, "comment": "dep:" + c.uid, "amount": amt}})
        else: await send(c, no)

async def ws_handler(req):
    ws = web.WebSocketResponse(heartbeat=25); await ws.prepare(req); c = C(ws)
    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT: continue
            try: await on_msg(c, json.loads(msg.data))
            except Exception as e: print("ws:", e)
    finally: await drop(c)
    return ws

async def on_start(app):
    global BOT_NAME
    if TOKEN:
        BOT_NAME = await bot.me() or ""
        app["tasks"] = [asyncio.create_task(bot.poll(credit)), asyncio.create_task(wallet.ton_poll(credit))]

app = web.Application(); app.on_startup.append(on_start)
app.add_routes([web.get("/ws", ws_handler), web.get("/", lambda r: web.FileResponse("static/index.html"))])
app.router.add_static("/", "static")
if __name__ == "__main__":
    print(f"Arena: http://localhost:{PORT}  TEST_MODE={TEST}"); web.run_app(app, port=PORT)

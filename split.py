"""Eski index.html ni  static/index.html + style.css + app.js  ga ajratadi va yangilanishni qo'shadi.
Ishlatish:  python split.py eski_index.html"""
import re, os, sys
o = open(sys.argv[1], encoding="utf-8").read()
u = open("arena-upgrade.html", encoding="utf-8").read()
css = re.search(r"<style>(.*?)</style>", o, re.S).group(1)
js = re.findall(r"<script>(.*?)</script>", o, re.S)[-1]
ucss = re.search(r"<style>(.*?)</style>", u, re.S).group(1)
ujs = re.search(r"<script>(.*?)</script>", u, re.S).group(1)
PATCH = r"""
/* ---- server bilan ulanish: Telegram initData va to'lov javoblari ---- */
const _S=S;window.S=o=>{if(o.t==='hello'&&tg)o.init=tg.initData;_S(o)};
window.depResult=m=>{
  if(m.ok){me=m.user;upd();return drawDep(`<div class="note ok">✅ ${t('depOk')}: ${m.star?'+'+m.star+' ⭐ ':''}${m.ton?'+'+m.ton+' 💎':''}</div>`)}
  if(m.link){try{tg&&tg.openInvoice?tg.openInvoice(m.link):window.open(m.link,'_blank')}catch(e){}return drawDep('<div class="note">⭐ …</div>')}
  if(m.ton){const x=m.ton,n=Math.round(x.amount*1e9);return drawDep(`<div class="note">💎 ${esc(x.amount)} TON → <code>${esc(x.addr)}</code><br>Comment: <code>${esc(x.comment)}</code><br><a style="color:#22d3ee" href="ton://transfer/${esc(x.addr)}?amount=${n}&text=${encodeURIComponent(x.comment)}">Open wallet</a></div>`)}
  drawDep(`<div class="note err">${t('depOff')}</div>`)};
"""
os.makedirs("static", exist_ok=True)
open("static/style.css", "w", encoding="utf-8").write(css + "\n" + ucss)
open("static/app.js", "w", encoding="utf-8").write(js + "\n" + ujs + "\n" + PATCH)
h = re.sub(r"<style>.*?</style>", lambda m: '<link rel="stylesheet" href="/style.css">', o, count=1, flags=re.S)
h = re.sub(r"<script>.*?</script>", lambda m: '<script src="/app.js"></script>', h, count=1, flags=re.S)
open("static/index.html", "w", encoding="utf-8").write(h)
print("Tayyor: static/index.html, static/style.css, static/app.js")

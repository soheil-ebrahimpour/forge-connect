#!/usr/bin/python3
"""Minimal polling Telegram storefront; payments are manually verified in the panel."""
import json,sqlite3,time,urllib.parse,urllib.request
from pathlib import Path
DB=Path('/var/lib/ikev2-manager/panel.sqlite3')

def db():
 c=sqlite3.connect(DB,timeout=10);c.row_factory=sqlite3.Row;c.execute('PRAGMA busy_timeout=10000');return c
def settings():
 with db() as c:return {r['key']:r['value'] for r in c.execute("SELECT key,value FROM app_settings WHERE key LIKE 'telegram_%' OR key LIKE 'payment_%'")}
def tg(token,method,data=None,timeout=35):
 raw=urllib.parse.urlencode(data or {}).encode()
 req=urllib.request.Request(f'https://api.telegram.org/bot{token}/{method}',data=raw)
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.loads(r.read())
def send(token,chat,text,markup=None):
 data={'chat_id':chat,'text':text,'parse_mode':'HTML','disable_web_page_preview':'true'}
 if markup:data['reply_markup']=json.dumps(markup)
 return tg(token,'sendMessage',data)
def handle(token,admin,upd):
 msg=upd.get('message') or {}; chat=msg.get('chat',{}).get('id'); who=msg.get('from',{}); name=(who.get('username') or who.get('first_name') or 'Telegram user')[:80]
 if not chat:return
 text=msg.get('text','')
 if text.startswith('/start') or text.startswith('/plans'):
  with db() as c:plans=c.execute('SELECT id,name,days,quota_bytes,price FROM plans WHERE enabled=1 ORDER BY sort_order,id').fetchall()
  if not plans:send(token,chat,'در حال حاضر طرحی برای فروش فعال نیست.');return
  buttons=[]
  for p in plans:buttons.append([{'text':f"{p['name']} · {p['days']} روز · {p['quota_bytes']/1e9:g} GB · {p['price']}",'callback_data':f"plan:{p['id']}"}])
  send(token,chat,'طرح موردنظر را انتخاب کنید:',{'inline_keyboard':buttons});return
 photo=msg.get('photo')
 if photo:
  with db() as c:
   row=c.execute("SELECT id FROM sales_orders WHERE telegram_id=? AND status='awaiting_payment' ORDER BY id DESC LIMIT 1",(chat,)).fetchone()
   if row:c.execute("UPDATE sales_orders SET proof_file_id=?,status='pending_review' WHERE id=?",(photo[-1]['file_id'],row['id']))
  if row:
   send(token,chat,'رسید دریافت شد و برای بررسی مدیر ارسال شد. نتیجه پس از بررسی اطلاع داده می‌شود.')
   if admin:
    tg(token,'sendPhoto',{'chat_id':admin,'photo':photo[-1]['file_id'],'caption':f'رسید سفارش #{row["id"]} از {name} (Telegram ID: {chat})'})
  else:send(token,chat,'سفارش پرداخت‌نشده‌ای پیدا نشد. ابتدا /plans را بزنید.')
 elif text.startswith('/'):send(token,chat,'برای دیدن طرح‌ها دستور /plans را بزنید.')

def callbacks(token,admin,q):
 data=q.get('data','');user=q.get('from',{});chat=q.get('message',{}).get('chat',{}).get('id')
 if not data.startswith('plan:') or not chat:return
 try:pid=int(data.split(':',1)[1])
 except ValueError:return
 with db() as c:
  p=c.execute('SELECT * FROM plans WHERE id=? AND enabled=1',(pid,)).fetchone()
  if not p:send(token,chat,'این طرح دیگر فعال نیست.');return
  c.execute("UPDATE sales_orders SET status='cancelled' WHERE telegram_id=? AND status='awaiting_payment'",(chat,))
  cur=c.execute("INSERT INTO sales_orders(telegram_id,telegram_name,plan_id,status,created_at) VALUES(?,?,?,'awaiting_payment',?)",(chat,(user.get('username') or user.get('first_name') or '')[:80],pid,int(time.time())))
  order=cur.lastrowid
 s=settings(); card=s.get('payment_card','');holder=s.get('payment_holder','')
 if not card:send(token,chat,'اطلاعات پرداخت هنوز تنظیم نشده است.');return
 send(token,chat,f"سفارش <b>#{order}</b> ثبت شد.\nطرح: {p['name']}\nمبلغ: {p['price']}\nشماره کارت: <code>{card}</code>\nبه نام: {holder or '—'}\n\nپس از پرداخت، تصویر رسید را همین‌جا ارسال کنید.")
 if admin:send(token,admin,f'سفارش جدید #{order}\nTelegram ID: {chat}\nطرح: {p["name"]} · {p["price"]}')

def deliver(token):
 with db() as c:rows=c.execute("""SELECT o.id,o.telegram_id,o.status,o.delivery_pending,u.username,u.vpn_password
 FROM sales_orders o LEFT JOIN vpn_users u ON u.id=o.vpn_user_id WHERE o.delivery_pending=1 ORDER BY o.id LIMIT 20""").fetchall()
 for o in rows:
  try:
   if o['status']=='approved':
    host=Path('/etc/ikev2-manager/domain').read_text().strip()
    send(token,o['telegram_id'],f"حساب شما آماده شد ✅\nنام کاربری VPN و پورتال: <code>{o['username']}</code>\nرمز: <code>{o['vpn_password']}</code>\nپورتال: https://{host}/portal\n\nدر پورتال، پروفایل اتصال و راهنمای دستگاه‌ها در دسترس است.")
   elif o['status']=='rejected':send(token,o['telegram_id'],f"رسید سفارش #{o['id']} تأیید نشد. برای پیگیری با مدیر تماس بگیرید و دوباره /plans را بزنید.")
   else:continue
  except Exception:continue
  with db() as c:c.execute('UPDATE sales_orders SET delivery_pending=0 WHERE id=?',(o['id'],))

def run():
 offset=-1;token=''
 while True:
  try:
   s=settings();new=s.get('telegram_token','');admin=s.get('telegram_admin_chat','')
   if not new:time.sleep(4);continue
   if new!=token:token=new;offset=-1
   deliver(token)
   updates=tg(token,'getUpdates',{'offset':offset,'timeout':25,'allowed_updates':json.dumps(['message','callback_query'])},timeout=35).get('result',[])
   for u in updates:
    offset=u['update_id']+1
    try:
     if 'callback_query' in u:callbacks(token,admin,u['callback_query']);tg(token,'answerCallbackQuery',{'callback_query_id':u['callback_query']['id']})
     else:handle(token,admin,u)
    except Exception as e:print(f'update handling failed: {e}',flush=True)
  except Exception as e:print(f'poll failed: {e}',flush=True);time.sleep(5)
if __name__=='__main__':run()

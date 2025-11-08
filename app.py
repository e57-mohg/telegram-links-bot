import os
import asyncio
import logging
from flask import Flask, jsonify
from telethon import TelegramClient, events, Button
from telethon.tl.types import MessageEntityUrl, MessageEntityTextUrl
from telethon.errors import SessionPasswordNeededError
import sqlite3
import re
import json
import threading

# إعدادات API - استخدم القيم الخاصة بك
API_ID = int(os.getenv('API_ID', '24676697'))
API_HASH = os.getenv('API_HASH', '8528b9a4d9252f4035fe58f23a92f41f')
BOT_TOKEN = os.getenv('BOT_TOKEN', '8156882118:AAECt_gS31xGTsyjVFoIYqEQViVepRSbPlY')

app = Flask(__name__)

# إنشاء المجلدات اللازمة
os.makedirs('sessions', exist_ok=True)
os.makedirs('data', exist_ok=True)

# تهيئة قاعدة البيانات
def init_db():
    conn = sqlite3.connect('data/links.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT UNIQUE,
            chat_title TEXT,
            account_name TEXT,
            date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ تم تهيئة قاعدة البيانات")

init_db()

# إدارة الحسابات
accounts_file = 'data/accounts.json'

def load_accounts():
    try:
        with open(accounts_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_accounts(accounts):
    with open(accounts_file, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)

# متغيرات الحالة
user_states = {}
accounts = load_accounts()
account_clients = {}
user_temp_data = {}
bot_client = None

def save_link(link, chat_title, account_name):
    try:
        conn = sqlite3.connect('data/links.db')
        cursor = conn.cursor()
        cursor.execute(
            'INSERT OR IGNORE INTO links (link, chat_title, account_name) VALUES (?, ?, ?)',
            (link, chat_title, account_name)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ الرابط: {e}")
        return False

def get_stats():
    try:
        conn = sqlite3.connect('data/links.db')
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM links')
        total = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(DISTINCT chat_title) FROM links')
        groups = cursor.fetchone()[0]
        conn.close()
        return total, groups
    except:
        return 0, 0

async def connect_account(phone, account_name, event):
    try:
        session_name = f"account_{phone.replace('+', '')}"
        client = TelegramClient(f'sessions/{session_name}', API_ID, API_HASH)
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await event.edit("📞 **جاري إرسال رمز التحقق إلى هاتفك...**")
            
            await client.send_code_request(phone)
            await event.edit("✅ **تم إرسال رمز التحقق**\n\n📝 **الرجاء إرسال رمز التحقق:**")
            
            # في الاستضافة، سنستخدم طريقة مبسطة
            await event.edit("🔗 **في هذا الإصدار، يرجى استخدام التطبيق المحلي لإضافة الحسابات**")
            return None
        
        me = await client.get_me()
        await event.edit(f"✅ **تم الاتصال بالحساب بنجاح!**\n\n👤 **الاسم:** {me.first_name}")
        
        # حفظ الحساب
        accounts[phone] = {
            'session_name': session_name,
            'account_name': account_name
        }
        save_accounts(accounts)
        account_clients[phone] = client
        
        return client
        
    except Exception as e:
        await event.edit(f"❌ **خطأ في الاتصال:** {str(e)}")
        return None

async def show_main_menu(event):
    """عرض القائمة الرئيسية"""
    total, groups = get_stats()
    
    text = f"""
🤖 **بوت استخراج روابط Telegram**

🟢 **يعمل على الاستضافة السحابية**

📊 **الإحصائيات:**
• الروابط المحفوظة: **{total}**
• المجموعات المفحوصة: **{groups}**
• الحسابات المضافة: **{len(accounts)}**

🎯 **اختر من القائمة:**
    """
    
    buttons = [
        [Button.inline("🔍 استخراج الروابط", "extract_links")],
        [Button.inline("📊 الإحصائيات", "show_stats")],
        [Button.inline("🆘 المساعدة", "show_help")],
        [Button.inline("❤️ حالة البوت", "bot_status")]
    ]
    
    await event.reply(text, buttons=buttons)

async def extract_links_demo(event):
    """عرض تجريبي للاستخراج"""
    demo_links = [
        "https://t.me/joinchat/EXAMPLE1",
        "https://t.me/joinchat/EXAMPLE2", 
        "https://t.me/+1234567890",
        "https://t.me/joinchat/EXAMPLE3"
    ]
    
    await event.edit("🔍 **جاري استخراج الروابط...**")
    await asyncio.sleep(2)
    
    await event.edit(f"✅ **تم العثور على {len(demo_links)} رابط**\n\n📤 **جاري إرسالها...**")
    
    for i in range(0, len(demo_links), 2):
        batch = demo_links[i:i+2]
        await event.reply("📦 **روابط نموذجية:**\n" + "\n".join(batch))
        await asyncio.sleep(1)
    
    await event.reply("🎉 **هذا عرض تجريبي!**\n\nللاستخدام الكامل، أضف حساباتك أولاً.")

# routes للويب
@app.route('/')
def home():
    return """
    <html dir="rtl">
    <head>
        <meta charset="UTF-8">
        <title>بوت Telegram</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f0f2f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            .status { color: #22c55e; font-weight: bold; }
            .info { background: #e8f4fd; padding: 15px; border-radius: 5px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 بوت استخراج روابط Telegram</h1>
            <div class="info">
                <p class="status">🟢 البوت يعمل بنجاح على Railway</p>
                <p>هذا البوت يعمل 24/7 على استضافة سحابية مجانية</p>
            </div>
            <p><strong>🚀 المميزات:</strong></p>
            <ul style="text-align: right; display: inline-block;">
                <li>استخراج روابط الدعوة من مجموعات Telegram</li>
                <li>عمل مستمر 24/7</li>
                <li>واجهة تفاعلية في Telegram</li>
                <li>حفظ تلقائي للبيانات</li>
            </ul>
            <p style="margin-top: 30px;">
                <strong>💬 اذهب إلى Telegram وابحث عن البوت للبدء!</strong>
            </p>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    total, groups = get_stats()
    return jsonify({
        'status': 'healthy',
        'service': 'telegram-links-bot',
        'stats': {
            'total_links': total,
            'total_groups': groups,
            'total_accounts': len(accounts)
        }
    })

@app.route('/api/stats')
def api_stats():
    total, groups = get_stats()
    return jsonify({
        'total_links': total,
        'total_groups': groups,
        'accounts_count': len(accounts)
    })

# معالجات البوت
async def setup_bot_handlers():
    global bot_client
    
    @bot_client.on(events.NewMessage(pattern='/start'))
    async def start_handler(event):
        await show_main_menu(event)
    
    @bot_client.on(events.NewMessage(pattern='/status'))
    async def status_handler(event):
        total, groups = get_stats()
        await event.reply(f"""
🟢 **حالة البوت:**

• البوت: **يعمل على الاستضافة**
• الروابط: **{total}**
• المجموعات: **{groups}**
• الحسابات: **{len(accounts)}**

🚀 **مستعد للعمل!**
        """)
    
    @bot_client.on(events.CallbackQuery)
    async def callback_handler(event):
        data = event.data.decode()
        
        if data == "extract_links":
            await extract_links_demo(event)
        
        elif data == "show_stats":
            total, groups = get_stats()
            await event.edit(f"""
📊 **الإحصائيات:**

• إجمالي الروابط: **{total}**
• المجموعات المفحوصة: **{groups}**
• الحسابات النشطة: **{len(accounts)}**

💪 **استمر في العمل!**
            """)
        
        elif data == "show_help":
            await event.edit("""
🆘 **دليل الاستخدام:**

1. أرسل **/start** للبدء
2. اضغط **استخراج الروابط** 
3. شاهد النتائج

💡 **ملاحظات:**
- البوت يعمل 24/7
- البيانات تحفظ تلقائياً
- يمكنك إضافة حسابات متعددة
            """)
        
        elif data == "bot_status":
            await event.edit("🟢 **البوت يعمل بشكل طبيعي على الاستضافة السحابية**\n\n🚀 **مستعد لخدمتك!**")

async def run_bot():
    """تشغيل البوت بشكل مستمر"""
    global bot_client
    
    while True:
        try:
            bot_client = TelegramClient('sessions/bot', API_ID, API_HASH)
            await setup_bot_handlers()
            await bot_client.start(bot_token=BOT_TOKEN)
            
            me = await bot_client.get_me()
            print(f"✅ البوت يعمل: @{me.username}")
            print("🚀 البوت نشط على Railway!")
            
            await bot_client.run_until_disconnected()
            
        except Exception as e:
            print(f"❌ خطأ في البوت: {e}")
            print("🔄 إعادة المحاولة خلال 10 ثوان...")
            await asyncio.sleep(10)

def start_bot():
    """بدء البوت في thread منفصل"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_bot())

if __name__ == '__main__':
    # بدء البوت في الخلفية
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()
    
    # بدء خادم الويب
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 بدء خادم الويب على المنفذ {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
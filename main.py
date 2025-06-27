import os
import re
import requests
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from yt_dlp import YoutubeDL
from spotipy import Spotify
from spotipy.oauth2 import SpotifyClientCredentials

# إعدادات البوت
BOT_TOKEN = '7385925406:AAEQ9G4NjjHWpATuA7jur7HiRE0fmaF2tgk'
SPOTIFY_CLIENT_ID = "4a0e078682ff49a580960c90ec59c42a"
SPOTIFY_CLIENT_SECRET = "e87aeec6060d4a87903fbb77b06d44a5"

bot = telebot.TeleBot(BOT_TOKEN)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Spotify
sp = Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

user_search_pages = {}
pending_search = {}

# /start
@bot.message_handler(commands=['start'])
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

def welcome(msg):
    text = (
        "🎶 <b>أهلًا بيك في بوت الأغاني!</b>\n\n"
        "تكدر تحمل أغانيك بكل سهولة وبساطة من <b>سبوتفاي</b> و<b>يوتيوب</b>.\n"
        "فقط أرسل رابط الأغنية مباشرة، أو اكتب <b>بحث</b> متبوعًا باسم أغنيتك، وروق! 😊"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("المطور 👨‍💻", url="https://t.me/oliv17"))

    bot.send_message(
        msg.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=markup
    )

# أمر البحث
@bot.message_handler(func=lambda msg: msg.text.lower().startswith("بحث "))
def handle_search(msg):
    query = msg.text[5:].strip()
    if not query:
        return bot.send_message(msg.chat.id, "❌ الرجاء كتابة الكلمة بعد 'بحث'.")

    pending_search[msg.chat.id] = query

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🔴 يوتيوب", callback_data="src_youtube"),
        InlineKeyboardButton("🟢 سبوتفاي", callback_data="src_spotify")
    )

    bot.send_message(msg.chat.id, "🎯 اختر مصدر البحث:", reply_markup=markup)

# عند اختيار المصدر
@bot.callback_query_handler(func=lambda call: call.data.startswith("src_"))
def handle_source_selection(call):
    user_id = call.message.chat.id
    query = pending_search.get(user_id)
    if not query:
        return bot.answer_callback_query(call.id, "❌ لا يوجد طلب بحث محفوظ.")

    source = call.data.split("_")[1]
    del pending_search[user_id]

    # إرسال رسالة جديدة تحتوي "📥 جاري تجهيز النتائج..."
    sent = bot.send_message(user_id, "📥 جاري تجهيز النتائج...", disable_web_page_preview=True)

    if source == "youtube":
        results = search_youtube(query)
    else:
        results = search_spotify(query)

    if not results:
        bot.edit_message_text("❌ لم أجد نتائج.", user_id, sent.message_id)
        return

    user_search_pages[user_id] = {
        'results': results,
        'page': 0,
        'source': source,
        'message_id': sent.message_id
    }

    send_search_page(user_id)

# البحث من YouTube
def search_youtube(query, max_results=50):
    ydl_opts = {
        'quiet': True,
        'extract_flat': False,
        'skip_download': True,
        'default_search': 'ytsearch',
    }
    with YoutubeDL(ydl_opts) as ydl:
        data = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
        return data.get("entries", [])

# البحث من Spotify
def search_spotify(query, max_results=20):
    results = sp.search(q=query, limit=max_results, type='track')
    tracks = results['tracks']['items']
    formatted = []
    for track in tracks:
        formatted.append({
            'title': f"{track['name']} - {track['artists'][0]['name']}",
            'id': track['external_urls']['spotify'],
            'duration': track['duration_ms'] // 1000,
            'filesize_approx': 0  # No size info in Spotify
        })
    return formatted

# إرسال النتائج
def send_search_page(user_id):
    data = user_search_pages[user_id]
    results = data['results']
    source = data['source']
    page = data['page']
    per_page = 10
    start = page * per_page
    end = start + per_page
    page_results = results[start:end]

    text = f"🔍 نتائج البحث ({start+1}-{min(end, len(results))}):\n\n"
    for i, entry in enumerate(page_results, start=1+start):
        if source == 'youtube':
            title = entry.get('title', 'بدون عنوان')
            duration = entry.get('duration', 0)
            filesize = entry.get('filesize_approx', 0) or entry.get('filesize', 0)
            video_id = entry.get('id')
        else:
            title = entry['title']
            duration = entry['duration']
            filesize = entry['filesize_approx']
            video_id = entry['id'].split("/")[-1]  # last part of Spotify link

        min, sec = divmod(duration, 60)
        size_mb = round((filesize or 0) / 1024 / 1024, 2) if filesize else "?"
        text += f"{i}. 🎵 {title}\n⏱️ {min}:{str(sec).zfill(2)} — 💾 {size_mb} MB\n🟢 /{video_id}\n\n"

    markup = InlineKeyboardMarkup()
    if page > 0:
        markup.add(InlineKeyboardButton("◀️ الرجوع", callback_data="prev"))
    if end < len(results):
        markup.add(InlineKeyboardButton("▶️ التالي", callback_data="next"))

    bot.edit_message_text(
        text, user_id, data['message_id'],
        reply_markup=markup,
        disable_web_page_preview=True
    )

# التنقل بين الصفحات
@bot.callback_query_handler(func=lambda call: call.data in ['next', 'prev'])
def paginate(call):
    user_id = call.message.chat.id
    if user_id not in user_search_pages:
        return

    if call.data == 'next':
        user_search_pages[user_id]['page'] += 1
    else:
        user_search_pages[user_id]['page'] -= 1

    send_search_page(user_id)
    bot.answer_callback_query(call.id)

# أمر /ID للتحميل
@bot.message_handler(regexp=r"^/[\w-]{11}$")
def handle_download_command(msg):
    video_id = msg.text[1:]
    full_url = f"https://www.youtube.com/watch?v={video_id}"
    msg.text = full_url
    download_music(msg)

# روابط مباشرة للتحميل
@bot.message_handler(func=lambda msg: is_url(msg.text))
def download_music(msg):
    url = msg.text.strip()
    bot.send_chat_action(msg.chat.id, 'upload_audio')

    if 'spotify.com/track/' in url:
        title = get_spotify_title(url)
        if title:
            bot.send_message(msg.chat.id, f"🔍 تم التعرف على الأغنية: {title}")
            url = get_youtube_url(title)
            if not url:
                return bot.send_message(msg.chat.id, "❌ لم أجدها على YouTube.")
        else:
            return bot.send_message(msg.chat.id, "❌ لم أتمكن من تحليل رابط Spotify.")

    bot.send_message(msg.chat.id, "🎶 جاري التحميل...")

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
            'quiet': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title')
            performer = info.get('uploader')
            thumb_url = info.get('thumbnail')
            filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")

        thumb_data = requests.get(thumb_url).content
        with open("thumb.jpg", "wb") as f:
            f.write(thumb_data)

        with open(filename, 'rb') as audio, open("thumb.jpg", 'rb') as thumb:
            bot.send_audio(msg.chat.id, audio, title=title, performer=performer, thumb=thumb)

        os.remove(filename)
        os.remove("thumb.jpg")

    except Exception as e:
        print(f"[❌] Error: {e}")
        bot.send_message(msg.chat.id, "❌ فشل التحميل.")

# Spotify: اسم الأغنية من الرابط
def get_spotify_title(url):
    try:
        track_id = url.split("track/")[1].split("?")[0]
        track_info = sp.track(track_id)
        name = track_info['name']
        artist = track_info['artists'][0]['name']
        return f"{name} {artist}"
    except:
        return None

# تحويل اسم إلى YouTube
def get_youtube_url(query):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'default_search': 'ytsearch1',
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if info and info['entries']:
            return f"https://www.youtube.com/watch?v={info['entries'][0]['id']}"
        return None

# التحقق من الرابط
def is_url(text):
    return re.match(r'https?://', text)

# بدء البوت
print("🤖 البوت يعمل الآن...")
bot.infinity_polling()

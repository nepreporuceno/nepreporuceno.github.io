import os
import json
import re
import hashlib
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from datetime import datetime, timedelta

app = Flask(__name__)

# Putanje do fajlova
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'tracked_subjects.json')
SENT_FILE = os.path.join(BASE_DIR, 'sent_posts.json')
FLUIDI_HASH_FILE = os.path.join(BASE_DIR, 'fluidi_hash.json')
TEHNOLOGIJA_HASH_FILE = os.path.join(BASE_DIR, 'tehnologija_hash.json')

# Učitavanje Telegram podataka iz Render Environment Variables
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')


def load_subjects():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Greška pri čitanju {DATA_FILE}: {e}")
    return [
        {"id": 65, "name": "Mehanika 3"}
    ]


def save_subjects(subjects):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(subjects, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Greška pri snimanju {DATA_FILE}: {e}")


def load_sent_posts():
    if os.path.exists(SENT_FILE):
        try:
            with open(SENT_FILE, 'r', encoding='utf-8') as f:
                return set(json.load(f))
        except Exception as e:
            print(f"Greška pri čitanju {SENT_FILE}: {e}")
    return set()


def save_sent_posts(sent_posts):
    try:
        with open(SENT_FILE, 'w', encoding='utf-8') as f:
            json.dump(list(sent_posts), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Greška pri snimanju {SENT_FILE}: {e}")


def send_telegram_notification(subject_name, title, link):
    """Šalje obaveštenje na Telegram profil"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    message = f"📌 *{subject_name}*\n\n{title}\n\n🔗 [Otvori link]({link})"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': False
    }
    
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Greška pri slanju na Telegram: {e}")


def send_custom_message(text_message, chat_id=None):
    """Šalje običnu tekstualnu poruku na Telegram"""
    target_chat = chat_id or TELEGRAM_CHAT_ID
    if not TELEGRAM_BOT_TOKEN or not target_chat:
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': target_chat,
        'text': text_message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Greška pri slanju poruke: {e}")


def get_all_available_subjects():
    url = "https://nastava.mas.bg.ac.rs/nastava/viewforum.php?f=4"
    headers = {'User-Agent': 'Mozilla/5.0'}
    available = []
    seen_ids = set()

    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            links = soup.find_all('a', href=re.compile(r'viewforum\.php\?f=\d+'))
            
            for link in links:
                href = link.get('href', '')
                match = re.search(r'f=(\d+)', href)
                if match:
                    forum_id = int(match.group(1))
                    name = link.get_text(strip=True)
                    
                    if forum_id != 4 and forum_id not in seen_ids and name:
                        seen_ids.add(forum_id)
                        available.append({'id': forum_id, 'name': name})
                        
    except Exception as e:
        print(f"Greška pri učitavanju predmeta sa foruma: {e}")
        
    available.sort(key=lambda x: x['name'])
    return available


def parse_iso_date(date_str):
    if not date_str:
        return datetime.min
    try:
        clean_str = date_str.replace('Z', '+00:00')
        return datetime.fromisoformat(clean_str)
    except Exception:
        return datetime.min


def fetch_subject_feed(subject_id):
    url = f"https://nastava.mas.bg.ac.rs/nastava/feed.php?f={subject_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    entries = []
    
    try:
        response = requests.get(url, headers=headers, timeout=8)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            
            for entry in root.findall('atom:entry', ns):
                title_elem = entry.find('atom:title', ns)
                link_elem = entry.find('atom:link', ns)
                updated_elem = entry.find('atom:updated', ns)
                
                title = title_elem.text if title_elem is not None else "Bez naslova"
                link = link_elem.attrib.get('href', '#') if link_elem is not None else "#"
                updated_raw = updated_elem.text if updated_elem is not None else ""
                
                dt_obj = parse_iso_date(updated_raw)
                formatted_date = dt_obj.strftime('%d.%m.%Y. u %H:%M') if dt_obj != datetime.min else updated_raw

                entries.append({
                    'title': title,
                    'link': link,
                    'updated': formatted_date,
                    'dt_obj': dt_obj
                })
    except Exception as e:
        print(f"Greška pri preuzimanju fid-a za f={subject_id}: {e}")
        
    return entries


def check_fluidi_site_change():
    url = "https://fluidi.mas.bg.ac.rs/mfb/index.html"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=8)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            current_hash = hashlib.md5(response.text.encode('utf-8')).hexdigest()
            saved_hash = None
            if os.path.exists(FLUIDI_HASH_FILE):
                try:
                    with open(FLUIDI_HASH_FILE, 'r', encoding='utf-8') as f:
                        saved_hash = json.load(f).get('hash')
                except Exception:
                    pass
            
            if saved_hash is None:
                with open(FLUIDI_HASH_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'hash': current_hash}, f)
            elif saved_hash != current_hash:
                send_telegram_notification("Katedra za fluide", "Izvršena je izmena na sajtu katedre!", url)
                with open(FLUIDI_HASH_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'hash': current_hash}, f)
    except Exception as e:
        print(f"Greška pri proveri Fluidi sajta: {e}")


def check_tehnologija_site_change():
    url = "https://cent.mas.bg.ac.rs/tehnologija-masinske-obrade/obavestenja/#title"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=8)
        response.encoding = 'utf-8'
        if response.status_code == 200:
            current_hash = hashlib.md5(response.text.encode('utf-8')).hexdigest()
            saved_hash = None
            if os.path.exists(TEHNOLOGIJA_HASH_FILE):
                try:
                    with open(TEHNOLOGIJA_HASH_FILE, 'r', encoding='utf-8') as f:
                        saved_hash = json.load(f).get('hash')
                except Exception:
                    pass
            
            if saved_hash is None:
                with open(TEHNOLOGIJA_HASH_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'hash': current_hash}, f)
            elif saved_hash != current_hash:
                send_telegram_notification("Tehnologija mašinske obrade", "Izvršena je izmena na sajtu obaveštenja!", url)
                with open(TEHNOLOGIJA_HASH_FILE, 'w', encoding='utf-8') as f:
                    json.dump({'hash': current_hash}, f)
    except Exception as e:
        print(f"Greška pri proveri Tehnologija sajta: {e}")


@app.route('/cron')
def cron_check():
    """Ultra-lagana ruta koja ne vraća nikakav suvišan tekst"""
    tracked_subjects = load_subjects()
    
    # Samo tiha provera foruma i slanje notifikacija za nove postove
    for subject in tracked_subjects:
        posts = fetch_subject_feed(subject['id'])
        sent_posts = load_sent_posts()
        new_sent = False
        now = datetime.now()
        
        for post in posts[:3]: # Proverava samo top 3 najnovija radi brzine
            is_recent = (now - post['dt_obj'].replace(tzinfo=None)) < timedelta(hours=48) if post['dt_obj'] != datetime.min else True
            if post['link'] not in sent_posts:
                if is_recent:
                    send_telegram_notification(subject['name'], post['title'], post['link'])
                sent_posts.add(post['link'])
                new_sent = True
        
        if new_sent:
            save_sent_posts(sent_posts)

    # Tiha provera spoljnih sajtova
    check_fluidi_site_change()
    check_tehnologija_site_change()

    # Vraća isključivo minimalni JSON od 12 karaktera da cron-job.org nikad ne prikaže grešku
    return '{"status":"ok"}', 200
@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Prima poruke od Telegrama kada mu pošalješ poruku u čet"""
    data = request.json
    if data and 'message' in data:
        message = data['message']
        chat_id = message['chat']['id']
        text = message.get('text', '').strip().lower()
        
        # Ako mu pošalješ "proveri" ili bilo šta, poslaće ti poslednje objave i stanje sajtova
        if text:
            tracked_subjects = load_subjects()
            report = "🔄 *Ručna provera svih izvora:*\n\n"
            
            # 1. Poslednje sa foruma
            for subject in tracked_subjects:
                posts = fetch_subject_feed(subject['id'])
                if posts:
                    latest = posts[0]
                    report += f"📚 *{subject['name']}*\n• [{latest['title']}]({latest['link']})\n\n"
            
            # 2. Stanje spoljnih sajtova sa linkovima
            fluidi_changed, fluidi_url = check_fluidi_site_change(force_report=True)
            tehn_changed, tehn_url = check_tehnologija_site_change(force_report=True)
            
            report += f"🔗 *Katedra za fluide:*\n{fluidi_url}\n\n"
            report += f"🔗 *Tehnologija mašinske obrade:*\n{tehn_url}"
            
            send_custom_message(report, chat_id=chat_id)
            
    return jsonify({"status": "ok"}), 200


@app.route('/add', methods=['POST'])
def add_subject():
    data = request.json
    subject_id = int(data.get('id'))
    name = data.get('name')

    subjects = load_subjects()
    if not any(s['id'] == subject_id for s in subjects):
        subjects.append({"id": subject_id, "name": name})
        save_subjects(subjects)

    return jsonify({"status": "success"})


@app.route('/remove', methods=['POST'])
def remove_subject():
    data = request.json
    subject_id = int(data.get('id'))

    subjects = load_subjects()
    subjects = [s for s in subjects if s['id'] != subject_id]
    save_subjects(subjects)

    return jsonify({"status": "success"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)


@app.route('/add', methods=['POST'])
def add_subject():
    data = request.json
    subject_id = int(data.get('id'))
    name = data.get('name')

    subjects = load_subjects()
    if not any(s['id'] == subject_id for s in subjects):
        subjects.append({"id": subject_id, "name": name})
        save_subjects(subjects)

    return jsonify({"status": "success"})


@app.route('/remove', methods=['POST'])
def remove_subject():
    data = request.json
    subject_id = int(data.get('id'))

    subjects = load_subjects()
    subjects = [s for s in subjects if s['id'] != subject_id]
    save_subjects(subjects)

    return jsonify({"status": "success"})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
    

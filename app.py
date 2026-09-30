import os
import json
import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, 'tracked_subjects.json')

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

PREDEFINED_SUBJECTS = [
    {"id": 65, "name": "Mehanika 3"},
    {"id": 807, "name": "Računarski alati"},
    {"id": 73, "name": "Numeričke metode"},
    {"id": 4, "name": "Opšta obaveštenja"}
]

def load_subjects():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [{"id": 65, "name": "Mehanika 3"}]

def save_subjects(subjects):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(subjects, f, ensure_ascii=False, indent=2)

def send_telegram_notification(subject_name, title, link):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    message = f"📌 *Obaveštenje: {subject_name}*\n\n{title}\n\n🔗 [Otvori na forumu]({link})"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        requests.post(url, json=payload, timeout=3)
    except Exception as e:
        print(f"Telegram error: {e}")

def fetch_feed_fast(subject_id):
    url = f"https://nastava.mas.bg.ac.rs/nastava/feed.php?f={subject_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    entries = []
    try:
        res = requests.get(url, headers=headers, timeout=3)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            for entry in root.findall('atom:entry', ns)[:3]:
                title = entry.find('atom:title', ns).text
                link = entry.find('atom:link', ns).attrib.get('href', '#')
                updated_raw = entry.find('atom:updated', ns).text if entry.find('atom:updated', ns) is not None else ""
                
                entries.append({
                    'title': title,
                    'link': link,
                    'dt_raw': updated_raw
                })
    except Exception as e:
        print(f"Error fetching f={subject_id}: {e}")
    return entries

from datetime import datetime, timedelta

@app.route('/')
def index():
    tracked_subjects = load_subjects()
    available_subjects = get_all_available_subjects()
    
    all_posts = []
    for subject in tracked_subjects:
        posts = fetch_subject_feed(subject['id'])
        for post in posts:
            post['subject_name'] = subject['name']
            all_posts.append(post)
            
    # Sortiramo objave od najnovijih ka starijim
    all_posts.sort(key=lambda x: x['dt_obj'], reverse=True)
    latest_posts = all_posts[:5]
    
    sent_posts = load_sent_posts()
    new_sent = False
    
    # Trenutno vreme za poređenje
    now = datetime.now()
    
    for post in latest_posts:
        # 1. USLOV: Objava mora biti novija od 48 sati da uopšte razmatramo slanje
        # (Ovo sprečava bot da šalje stare vesti ako se fajl obriše)
        is_recent = (now - post['dt_obj']) < timedelta(hours=48) if post['dt_obj'] != datetime.min else False
        
        if post['link'] not in sent_posts:
            if is_recent:
                # Šaljemo na Telegram samo ako je objava sveža
                send_telegram_notification(post['subject_name'], post['title'], post['link'])
            
            # Svakako ga beležimo u poslate da ga više ne uzima u obzir
            sent_posts.add(post['link'])
            new_sent = True
            
    if new_sent:
        save_sent_posts(sent_posts)
    
    return render_template(
        'index.html', 
        subjects=tracked_subjects, 
        available_subjects=available_subjects, 
        posts=latest_posts
    )

@app.route('/cron-check')
def cron_check():
    tracked = load_subjects()
    
    for subj in tracked:
        posts = fetch_feed_fast(subj['id'])
        if posts:
            top_post = posts[0]
            send_telegram_notification(subj['name'], top_post['title'], top_post['link'])
            
    return "OK", 200

@app.route('/add', methods=['POST'])
def add_subject():
    data = request.json
    sid = int(data.get('id'))
    name = data.get('name')
    subjects = load_subjects()
    if not any(s['id'] == sid for s in subjects):
        subjects.append({"id": sid, "name": name})
        save_subjects(subjects)
    return jsonify({"status": "success"})

@app.route('/remove', methods=['POST'])
def remove_subject():
    data = request.json
    sid = int(data.get('id'))
    subjects = [s for s in load_subjects() if s['id'] != sid]
    save_subjects(subjects)
    return jsonify({"status": "success"})

if __name__ == '__main__':
    app.run(debug=True)

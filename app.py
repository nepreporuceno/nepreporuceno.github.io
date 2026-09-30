import os
import json
import re
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify
from datetime import datetime

app = Flask(__name__)
DATA_FILE = 'tracked_subjects.json'

def load_subjects():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [
        {"id": 65, "name": "Mehanika 3"}
    ]

def save_subjects(subjects):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(subjects, f, ensure_ascii=False, indent=2)

def get_all_available_subjects():
    """Skida stranicu kategorije (f=4) i izvlači sve dostupne predmete/podforume"""
    url = "https://nastava.mas.bg.ac.rs/nastava/viewforum.php?f=4"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
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
        print(f"Greška pri učitavanju liste predmeta sa f=4: {e}")
        
    available.sort(key=lambda x: x['name'])
    return available

def parse_iso_date(date_str):
    """Prevara ISO 8601 datum iz RSS-a u Python datetime objekat za pouzdano sortiranje"""
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
                
                # Pretvaranje u datetime objekat
                dt_obj = parse_iso_date(updated_raw)
                
                # Lepše formatiran prikaz za korisnika (npr. 30.09.2026. u 14:30)
                formatted_date = dt_obj.strftime('%d.%m.%Y. u %H:%M') if dt_obj != datetime.min else updated_raw

                entries.append({
                    'title': title,
                    'link': link,
                    'updated': formatted_date,
                    'dt_obj': dt_obj  # Koristi se za precizno sortiranje
                })
    except Exception as e:
        print(f"Greška pri preuzimanju za f={subject_id}: {e}")
        
    return entries

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
            
    # Sortiranje svih objava od najnovije ka najstarijoj prema datumu i vremenu
    all_posts.sort(key=lambda x: x['dt_obj'], reverse=True)
    
    return render_template(
        'index.html', 
        subjects=tracked_subjects, 
        available_subjects=available_subjects, 
        posts=all_posts
    )

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
    print("Sajt je pokrenut na http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
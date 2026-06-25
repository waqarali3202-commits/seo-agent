from flask import Flask, request, Response, make_response, session, redirect, url_for, jsonify
from urllib.parse import quote, unquote, urljoin, urlparse
import requests as req
import re
import os
import json
import hashlib
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mrwebsol_secret_2026")
API_KEY = os.environ.get("GROQ_API_KEY", "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")
HEADERS_BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

# ─── SIMPLE USER DATABASE (file-based) ───
USERS_FILE = "/tmp/users.json"
USAGE_FILE = "/tmp/usage.json"

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {}

def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)
    except: pass

def load_usage():
    try:
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {}

def save_usage(usage):
    try:
        with open(USAGE_FILE, 'w') as f:
            json.dump(usage, f)
    except: pass

def hash_password(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

def get_user():
    return session.get('user')

def get_user_plan(email):
    users = load_users()
    user = users.get(email, {})
    plan = user.get('plan', 'free')
    trial_end = user.get('trial_end', '')
    if trial_end:
        try:
            trial_date = datetime.strptime(trial_end, '%Y-%m-%d')
            if datetime.now() < trial_date:
                return 'trial'
            else:
                return 'free'
        except: pass
    return plan

def get_usage(email):
    usage = load_usage()
    today = datetime.now().strftime('%Y-%m-%d')
    key = f"{email}_{today}"
    return usage.get(key, {'searches': 0, 'articles': 0})

def increment_usage(email, type_='search'):
    usage = load_usage()
    today = datetime.now().strftime('%Y-%m-%d')
    key = f"{email}_{today}"
    if key not in usage:
        usage[key] = {'searches': 0, 'articles': 0}
    if type_ == 'search':
        usage[key]['searches'] += 1
    else:
        usage[key]['articles'] += 1
    save_usage(usage)

def can_use(email, type_='search'):
    plan = get_user_plan(email)
    if plan in ['trial', 'basic', 'pro']:
        return True, plan
    usage = get_usage(email)
    if type_ == 'search' and usage['searches'] >= 15:
        return False, 'free'
    if type_ == 'article' and usage['articles'] >= 3:
        return False, 'free'
    return True, 'free'

# ─── HELPERS ───
def fetch_html(url):
    try:
        r = req.get(url, headers=HEADERS_BROWSER, timeout=15, allow_redirects=True)
        return r.text, r.status_code, r.url
    except Exception:
        return None, 0, url

def get_all_links(html, base_url):
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    full = []
    for l in links:
        if l.startswith('#') or l.startswith('mailto:') or l.startswith('tel:') or l.startswith('javascript:'):
            continue
        full.append(urljoin(base_url, l))
    return list(set(full))

def get_internal_links(html, base_url):
    all_links = get_all_links(html, base_url)
    base_domain = urlparse(base_url).netloc
    return [l for l in all_links if urlparse(l).netloc == base_domain or urlparse(l).netloc == '']

def get_external_links(html, base_url):
    all_links = get_all_links(html, base_url)
    base_domain = urlparse(base_url).netloc
    return [l for l in all_links if urlparse(l).netloc != base_domain and urlparse(l).netloc != '']

def get_images(html):
    return re.findall(r'<img[^>]+>', html, re.IGNORECASE)

def check_ssl(url):
    return url.startswith('https://')

def get_meta(html):
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    desc  = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html, re.IGNORECASE)
    robots_meta = re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']*)["\']', html, re.IGNORECASE)
    canonical = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)["\']', html, re.IGNORECASE)
    h1 = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    h2 = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.IGNORECASE | re.DOTALL)
    return {
        "title": title.group(1).strip() if title else None,
        "description": desc.group(1).strip() if desc else None,
        "robots": robots_meta.group(1).strip() if robots_meta else None,
        "canonical": canonical.group(1).strip() if canonical else None,
        "h1_count": len(h1),
        "h1_text": re.sub('<[^<]+?>', '', h1[0]).strip() if h1 else None,
        "h2_count": len(h2),
    }

def check_url_status(url, timeout=8):
    try:
        r = req.head(url, headers=HEADERS_BROWSER, timeout=timeout, allow_redirects=True)
        return r.status_code
    except:
        try:
            r = req.get(url, headers=HEADERS_BROWSER, timeout=timeout, allow_redirects=True)
            return r.status_code
        except:
            return None

def ai_call(prompt, max_tokens=900):
    try:
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        data = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
        r = req.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"Error: {r.text}"
    except Exception as e:
        return f"Error: {str(e)}"

# ─── LOGO SVG ───
LOGO_SVG = '''<svg width="180" height="50" viewBox="0 0 180 50" xmlns="http://www.w3.org/2000/svg">
  <circle cx="25" cy="25" r="22" fill="#667eea" opacity="0.15"/>
  <rect x="12" y="30" width="6" height="10" rx="2" fill="#667eea"/>
  <rect x="21" y="22" width="6" height="18" rx="2" fill="#764ba2"/>
  <rect x="30" y="15" width="6" height="25" rx="2" fill="#667eea"/>
  <path d="M10 32 Q25 18 38 12" stroke="#764ba2" stroke-width="2" fill="none" stroke-linecap="round"/>
  <polygon points="38,8 42,14 36,14" fill="#764ba2"/>
  <line x1="47" y1="8" x2="47" y2="42" stroke="#667eea" stroke-width="1.5" opacity="0.5"/>
  <text x="54" y="24" font-family="Arial" font-size="13" font-weight="800" fill="#2c3e50">MR WEBSOL</text>
  <text x="55" y="38" font-family="Arial" font-size="9" font-weight="400" fill="#667eea" letter-spacing="2">SEO AGENT</text>
</svg>'''

FAVICON = '''<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 50 50'><rect width='50' height='50' rx='10' fill='%23667eea'/><rect x='10' y='32' width='5' height='10' rx='1' fill='white'/><rect x='18' y='24' width='5' height='18' rx='1' fill='white'/><rect x='26' y='16' width='5' height='26' rx='1' fill='white'/><path d='M8 34 Q25 18 34 10' stroke='white' stroke-width='2.5' fill='none' stroke-linecap='round'/><polygon points='34,6 38,12 30,12' fill='white'/></svg>">'''

COUNTRIES = [
    "Pakistan 🇵🇰","United States 🇺🇸","United Kingdom 🇬🇧","India 🇮🇳","Australia 🇦🇺",
    "Canada 🇨🇦","UAE 🇦🇪","Saudi Arabia 🇸🇦","Germany 🇩🇪","France 🇫🇷",
    "Italy 🇮🇹","Spain 🇪🇸","Netherlands 🇳🇱","Turkey 🇹🇷","Bangladesh 🇧🇩",
    "Malaysia 🇲🇾","Indonesia 🇮🇩","Singapore 🇸🇬","South Africa 🇿🇦","Nigeria 🇳🇬",
    "Egypt 🇪🇬","Jordan 🇯🇴","Kuwait 🇰🇼","Qatar 🇶🇦","Bahrain 🇧🇭",
    "Oman 🇴🇲","Morocco 🇲🇦","Kenya 🇰🇪","Brazil 🇧🇷","Mexico 🇲🇽",
    "Argentina 🇦🇷","Philippines 🇵🇭","Thailand 🇹🇭","Vietnam 🇻🇳","Japan 🇯🇵",
    "South Korea 🇰🇷","China 🇨🇳","Russia 🇷🇺","Poland 🇵🇱","Sweden 🇸🇪",
    "Norway 🇳🇴","Denmark 🇩🇰","Finland 🇫🇮","Switzerland 🇨🇭","Belgium 🇧🇪",
    "Portugal 🇵🇹","Greece 🇬🇷","Czech Republic 🇨🇿","Romania 🇷🇴","Global 🌍"
]

LANGUAGES = [
    "English 🇬🇧","Urdu 🇵🇰","Arabic 🇸🇦","Hindi 🇮🇳","French 🇫🇷",
    "German 🇩🇪","Spanish 🇪🇸","Italian 🇮🇹","Portuguese 🇧🇷","Turkish 🇹🇷",
    "Malay 🇲🇾","Indonesian 🇮🇩","Bengali 🇧🇩","Swahili 🇰🇪","Russian 🇷🇺",
    "Chinese 🇨🇳","Japanese 🇯🇵","Korean 🇰🇷","Dutch 🇳🇱","Polish 🇵🇱",
    "Swedish 🇸🇪","Greek 🇬🇷","Romanian 🇷🇴","Vietnamese 🇻🇳","Thai 🇹🇭"
]

CATEGORIES = [
    "🛍️ Ecommerce / Online Store","🏢 Corporate / Business","📝 Blog / Content Site",
    "⚙️ Services / Agency","🏥 Health & Medical","🏠 Real Estate",
    "🍕 Food & Restaurant","📚 Education","💻 Technology / Software",
    "🌍 Travel & Tourism","💰 Finance & Banking","⚖️ Law & Legal",
    "🎨 Creative / Design","🚗 Automotive","👗 Fashion & Lifestyle",
    "💪 Fitness & Sports","🎮 Gaming","📱 Mobile Apps",
    "🔧 Home Improvement","🌿 Environment & Nature","🎵 Music & Entertainment",
    "📸 Photography","🧴 Beauty & Skincare","🐾 Pets & Animals",
    "🏗️ Construction","✈️ Airlines & Transport","🎓 Online Courses",
    "🔬 Science & Research","🛡️ Cybersecurity","🌐 Digital Marketing",
]

# ─── STYLE ───
def get_style(direction="ltr"):
    return f"""
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);min-height:100vh;padding:0;direction:{direction};}}
.navbar{{background:rgba(255,255,255,0.05);backdrop-filter:blur(10px);padding:12px 30px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.1);position:sticky;top:0;z-index:100;}}
.navbar-logo{{display:flex;align-items:center;gap:10px;text-decoration:none;}}
.nav-links{{display:flex;gap:15px;align-items:center;}}
.nav-links a{{color:rgba(255,255,255,0.8);text-decoration:none;font-size:13px;font-weight:600;padding:6px 14px;border-radius:20px;transition:all 0.3s;}}
.nav-links a:hover{{background:rgba(255,255,255,0.1);color:white;}}
.nav-btn{{background:linear-gradient(135deg,#667eea,#764ba2);color:white!important;border-radius:20px!important;}}
.plan-badge{{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;}}
.badge-free{{background:#e8f5e9;color:#27ae60;}}
.badge-trial{{background:#fff3e0;color:#e67e22;}}
.badge-basic{{background:#e8f0ff;color:#667eea;}}
.badge-pro{{background:#f3e8ff;color:#764ba2;}}
.container{{max-width:1000px;margin:30px auto;background:#fff;border-radius:24px;padding:40px;box-shadow:0 30px 80px rgba(0,0,0,0.5);}}
.logo{{text-align:center;margin-bottom:25px;}}
.logo h1{{font-size:26px;background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-weight:800;}}
.logo p{{color:#95a5a6;margin-top:6px;font-size:14px;}}
.divider{{height:3px;background:linear-gradient(135deg,#667eea,#764ba2);border-radius:3px;margin:20px 0;}}
.step-badge{{display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:5px 18px;border-radius:25px;font-size:13px;font-weight:700;margin-bottom:15px;}}
.form-group{{margin-bottom:20px;}}
label{{display:block;font-weight:700;color:#2c3e50;margin-bottom:8px;font-size:13px;text-transform:uppercase;letter-spacing:0.5px;}}
input[type=text],input[type=email],input[type=password],select{{width:100%;padding:13px 16px;border:2px solid #e8e8e8;border-radius:12px;font-size:15px;color:#2c3e50;transition:all 0.3s;background:#fafafa;}}
input:focus,select:focus{{border-color:#667eea;background:#fff;outline:none;box-shadow:0 0 0 4px rgba(102,126,234,0.1);}}
.grid-2{{display:grid;grid-template-columns:1fr 1fr;gap:18px;}}
.grid-3{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;}}
.website-type-group{{display:flex;gap:15px;margin-top:10px;}}
.website-type-card{{flex:1;padding:20px 15px;border:3px solid #e0e0e0;border-radius:14px;text-align:center;cursor:pointer;transition:all 0.3s;background:#fafafa;}}
.website-type-card:hover{{transform:translateY(-3px);box-shadow:0 8px 25px rgba(0,0,0,0.1);}}
.website-type-card input[type=radio]{{display:none;}}
.website-type-card .icon{{font-size:35px;margin-bottom:10px;}}
.website-type-card .name{{font-weight:700;color:#2c3e50;font-size:15px;}}
.website-type-card .desc{{font-size:12px;color:#95a5a6;margin-top:5px;}}
.website-type-card.selected{{border-color:#667eea;background:linear-gradient(135deg,#f0f2ff,#f8f0ff);transform:translateY(-3px);box-shadow:0 8px 25px rgba(102,126,234,0.2);}}
.seo-type-group{{display:flex;gap:15px;flex-wrap:wrap;}}
.seo-type-card{{flex:1;min-width:140px;padding:18px 15px;border:3px solid #e0e0e0;border-radius:14px;text-align:center;cursor:pointer;transition:all 0.3s;background:#fafafa;position:relative;}}
.seo-type-card:hover{{transform:translateY(-3px);box-shadow:0 8px 25px rgba(0,0,0,0.1);}}
.seo-type-card input[type=radio]{{display:none;}}
.seo-type-card .icon{{font-size:30px;margin-bottom:8px;}}
.seo-type-card .name{{font-weight:700;color:#2c3e50;font-size:14px;}}
.seo-type-card .desc{{font-size:12px;color:#95a5a6;margin-top:4px;}}
.seo-type-card.selected{{border-color:#667eea;background:linear-gradient(135deg,#f0f2ff,#f8f0ff);transform:translateY(-3px);box-shadow:0 8px 25px rgba(102,126,234,0.2);}}
.plan-tag{{position:absolute;top:-10px;right:10px;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:800;}}
.tag-free{{background:#27ae60;color:white;}}
.tag-basic{{background:#667eea;color:white;}}
.tag-pro{{background:#764ba2;color:white;}}
.sub-type-group{{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:15px;margin-top:10px;}}
.sub-type-card{{padding:18px 12px;border:3px solid #e0e0e0;border-radius:14px;text-align:center;cursor:pointer;transition:all 0.3s;background:#fafafa;text-decoration:none;display:block;position:relative;}}
.sub-type-card:hover{{border-color:#667eea;transform:translateY(-3px);box-shadow:0 8px 25px rgba(102,126,234,0.15);background:linear-gradient(135deg,#f0f2ff,#f8f0ff);}}
.sub-type-card .icon{{font-size:28px;margin-bottom:7px;}}
.sub-type-card .name{{font-weight:700;color:#2c3e50;font-size:13px;}}
.sub-type-card .desc{{font-size:11px;color:#95a5a6;margin-top:4px;}}
.sub-type-card.locked{{opacity:0.7;cursor:not-allowed;}}
.sub-type-card.locked:hover{{transform:none;box-shadow:none;}}
.btn-main{{width:100%;padding:16px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:12px;font-size:17px;cursor:pointer;font-weight:700;transition:all 0.3s;margin-top:10px;}}
.btn-main:hover{{transform:translateY(-2px);box-shadow:0 10px 30px rgba(102,126,234,0.4);}}
.btn-green{{background:linear-gradient(135deg,#27ae60,#2ecc71)!important;}}
.btn-orange{{background:linear-gradient(135deg,#e67e22,#f39c12)!important;}}
table{{width:100%;border-collapse:collapse;margin-top:10px;}}
th{{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:12px 14px;text-align:left;font-size:12px;font-weight:700;text-transform:uppercase;}}
th:first-child{{border-radius:10px 0 0 0;}}th:last-child{{border-radius:0 10px 0 0;}}
td{{padding:11px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#2c3e50;word-break:break-all;}}
tr:hover{{background:#f8f9ff;}}
.badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;}}
.badge-easy{{background:#d5f5e3;color:#27ae60;}}
.badge-medium{{background:#fef9e7;color:#e67e22;}}
.badge-hard{{background:#fdecea;color:#e74c3c;}}
.step{{background:#f8f9ff;border-radius:14px;padding:20px;margin-bottom:20px;border-left:5px solid #667eea;}}
.step h3{{color:#2c3e50;margin-bottom:12px;font-size:14px;font-weight:700;}}
.checkbox-group{{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;}}
.checkbox-item{{display:flex;align-items:center;gap:8px;background:white;padding:8px 14px;border-radius:25px;border:2px solid #e0e0e0;cursor:pointer;font-size:13px;transition:all 0.2s;}}
.checkbox-item:hover{{border-color:#667eea;background:#f8f9ff;}}
.checkbox-item input{{width:15px;height:15px;cursor:pointer;}}
.keyword-badge{{display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:5px 16px;border-radius:25px;font-size:13px;font-weight:600;margin-bottom:20px;}}
.meta-card{{background:linear-gradient(135deg,#eaf4ff,#f0f0ff);border-radius:14px;padding:18px 22px;margin-bottom:20px;font-size:14px;color:#2c3e50;line-height:2;border-left:5px solid #667eea;}}
.article-box{{background:#f8f9fa;border-radius:14px;padding:25px;line-height:1.95;max-height:500px;overflow-y:auto;border-left:5px solid #27ae60;font-size:14px;color:#2c3e50;margin-bottom:20px;white-space:pre-wrap;}}
.seo-box{{background:linear-gradient(135deg,#fff9e6,#fffbf0);border-radius:14px;padding:25px;border-left:5px solid #f39c12;font-size:13px;color:#2c3e50;line-height:2;margin-bottom:20px;}}
.result-card{{border-radius:14px;margin-bottom:22px;overflow:hidden;border:2px solid #e8e8e8;}}
.result-card-head{{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:12px 20px;font-size:15px;font-weight:700;}}
.result-card-head.green{{background:linear-gradient(135deg,#27ae60,#2ecc71);}}
.result-card-head.red{{background:linear-gradient(135deg,#e74c3c,#c0392b);}}
.result-card-head.orange{{background:linear-gradient(135deg,#e67e22,#f39c12);}}
.result-card-body{{padding:20px;background:#fff;font-size:14px;line-height:1.9;white-space:pre-wrap;}}
.stat-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-bottom:25px;}}
.stat-box{{background:#f8f9ff;border-radius:12px;padding:16px;text-align:center;border:2px solid #e8e8e8;}}
.stat-box .stat-num{{font-size:26px;font-weight:800;color:#667eea;}}
.stat-box .stat-num.red{{color:#e74c3c;}}
.stat-box .stat-num.green{{color:#27ae60;}}
.stat-box .stat-num.orange{{color:#e67e22;}}
.stat-box .stat-label{{font-size:12px;color:#95a5a6;margin-top:5px;font-weight:600;}}
.url-item{{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;flex-wrap:wrap;}}
.url-item:last-child{{border-bottom:none;}}
.url-text{{color:#2c3e50;word-break:break-all;flex:1;}}
.url-text a{{color:#667eea;text-decoration:none;}}
.url-text a:hover{{text-decoration:underline;}}
.status-200{{color:#27ae60;font-weight:700;font-size:12px;white-space:nowrap;}}
.status-301{{color:#e67e22;font-weight:700;font-size:12px;white-space:nowrap;}}
.status-404{{color:#e74c3c;font-weight:700;font-size:12px;white-space:nowrap;}}
.info-bar{{color:#95a5a6;margin-bottom:20px;font-size:13px;display:flex;gap:10px;flex-wrap:wrap;}}
.info-bar span{{background:#f8f9fa;padding:5px 12px;border-radius:20px;border:1px solid #e0e0e0;}}
h2{{background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:22px;margin-bottom:8px;}}
.success-icon{{font-size:36px;margin-bottom:8px;text-align:center;}}
.note-box{{background:#fffbf0;border:2px dashed #f39c12;border-radius:12px;padding:14px 18px;font-size:13px;color:#856404;margin-bottom:20px;line-height:1.7;}}
.buttons{{display:flex;gap:12px;flex-wrap:wrap;margin-top:15px;}}
.btn{{flex:1;min-width:130px;padding:13px;border-radius:12px;text-align:center;font-size:14px;font-weight:700;cursor:pointer;border:none;text-decoration:none;transition:all 0.2s;display:inline-block;}}
.btn-g{{background:linear-gradient(135deg,#27ae60,#2ecc71);color:white;}}
.btn-p{{background:linear-gradient(135deg,#667eea,#764ba2);color:white;}}
.btn-gr{{background:#f0f0f0;color:#2c3e50;}}
.btn-r{{background:linear-gradient(135deg,#e74c3c,#c0392b);color:white;}}
.btn:hover{{transform:translateY(-2px);opacity:0.95;}}
.back-link{{display:inline-block;margin-top:18px;padding:9px 20px;background:#f0f0f0;border-radius:10px;text-decoration:none;color:#2c3e50;font-weight:600;font-size:13px;}}
.custom-input{{display:none;margin-top:10px;border-color:#667eea!important;background:#f8f9ff!important;}}
.issue-critical{{background:#fff5f5;border-left:5px solid #e74c3c;border-radius:10px;padding:15px;margin-bottom:12px;}}
.issue-important{{background:#fff9f0;border-left:5px solid #e67e22;border-radius:10px;padding:15px;margin-bottom:12px;}}
.issue-minor{{background:#f0fff4;border-left:5px solid #27ae60;border-radius:10px;padding:15px;margin-bottom:12px;}}
.issue-title{{font-weight:700;font-size:14px;margin-bottom:6px;}}
.issue-desc{{font-size:13px;color:#555;line-height:1.6;}}
.usage-bar{{background:#f0f0f0;border-radius:10px;height:8px;margin-top:5px;overflow:hidden;}}
.usage-fill{{height:100%;border-radius:10px;background:linear-gradient(135deg,#667eea,#764ba2);transition:width 0.3s;}}
.upgrade-box{{background:linear-gradient(135deg,#667eea,#764ba2);border-radius:14px;padding:20px 25px;color:white;margin-bottom:20px;text-align:center;}}
.upgrade-box h3{{font-size:18px;margin-bottom:8px;}}
.upgrade-box p{{font-size:13px;opacity:0.9;margin-bottom:15px;}}
.upgrade-btn{{background:white;color:#667eea;border:none;padding:10px 25px;border-radius:25px;font-weight:700;cursor:pointer;font-size:14px;text-decoration:none;display:inline-block;}}
.auth-card{{max-width:450px;margin:60px auto;background:white;border-radius:20px;padding:40px;box-shadow:0 20px 60px rgba(0,0,0,0.4);}}
.auth-card h2{{text-align:center;margin-bottom:25px;font-size:24px;}}
.trial-banner{{background:linear-gradient(135deg,#f59e0b,#ef4444);color:white;text-align:center;padding:10px;font-size:13px;font-weight:600;}}
.pricing-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px;margin:20px 0;}}
.pricing-card{{border:2px solid #e8e8e8;border-radius:16px;padding:25px;text-align:center;}}
.pricing-card.featured{{border-color:#667eea;background:linear-gradient(135deg,#f0f2ff,#f8f0ff);}}
.pricing-card h3{{font-size:18px;font-weight:800;margin-bottom:5px;}}
.pricing-card .price{{font-size:36px;font-weight:800;color:#667eea;margin:10px 0;}}
.pricing-card ul{{text-align:left;list-style:none;margin:15px 0;}}
.pricing-card ul li{{padding:5px 0;font-size:13px;color:#555;}}
.pricing-card ul li::before{{content:'✅ ';}}
@media(max-width:600px){{.container{{padding:20px 15px;margin:10px;}}.grid-2,.grid-3{{grid-template-columns:1fr;}}.seo-type-group,.website-type-group{{flex-direction:column;}}.stat-grid{{grid-template-columns:repeat(2,1fr);}}}}
</style>
<script>
function selectSeoType(el){{document.querySelectorAll('.seo-type-card').forEach(c=>c.classList.remove('selected'));el.classList.add('selected');el.querySelector('input[type=radio]').checked=true;}}
function selectWebsiteType(el){{document.querySelectorAll('.website-type-card').forEach(c=>c.classList.remove('selected'));el.classList.add('selected');el.querySelector('input[type=radio]').checked=true;}}
function checkCustom(sel,id){{var inp=document.getElementById(id);if(sel.value.includes('✏️')){{inp.style.display='block';inp.focus();}}else{{inp.style.display='none';}}}}
function submitSuggestForm(){{
var cV=document.getElementById('cat_select').value.includes('✏️')?document.getElementById('cat_input').value:document.getElementById('cat_select').value;
var tV=document.getElementById('title_select').value.includes('✏️')?document.getElementById('title_input').value:document.getElementById('title_select').value;
var dV=document.getElementById('desc_select').value.includes('✏️')?document.getElementById('desc_input').value:document.getElementById('desc_select').value;
if(!cV||!tV||!dV){{alert('Please fill all fields!');return;}}
document.getElementById('final_category').value=cV;
document.getElementById('final_title').value=tV;
document.getElementById('final_desc').value=dV;
document.getElementById('mainform').submit();
}}
</script>
"""

def head(title="Mr Websol SEO Agent"):
    user = get_user()
    plan = get_user_plan(user['email']) if user else 'guest'
    usage = get_usage(user['email']) if user else {'searches':0,'articles':0}
    plan_color = {'free':'badge-free','trial':'badge-trial','basic':'badge-basic','pro':'badge-pro'}.get(plan,'badge-free')

    nav_right = f"""
    <span class="plan-badge {plan_color}">{plan.upper()}</span>
    <span style="color:white;font-size:12px">🔍 {usage['searches']}/15 &nbsp; ✍️ {usage['articles']}/3</span>
    <a href="/pricing" class="nav-links" style="color:#f59e0b;font-weight:700;font-size:13px">⚡ Upgrade</a>
    <a href="/logout" class="nav-links" style="color:rgba(255,255,255,0.7);font-size:13px">Logout</a>
    """ if user else """
    <a href="/login">Login</a>
    <a href="/register" class="nav-btn">Get Started Free</a>
    """

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="google-site-verification" content="lBsWiBHSa9xwXDUaF6duDp3BcH3o2sGfZNkQkHBVDp8">
<meta name="description" content="Free AI Powered Professional SEO Platform. Website Audit, On-Page SEO, Technical SEO, Off-Page SEO tools.">
<meta name="keywords" content="SEO tool, free SEO audit, AI SEO, keyword research, technical SEO, backlinks, website audit">
<meta property="og:title" content="Mr Websol SEO Agent — Free AI SEO Tool">
<meta property="og:description" content="Free AI Powered Professional SEO Platform">
<meta property="og:url" content="https://seo-agent.mrwebsol.com">
{FAVICON}
<title>{title} — Mr Websol SEO Agent</title>
{get_style()}
</head><body>
<div class="trial-banner">🎉 New users get 7 days FREE trial — All features unlocked! <a href="/register" style="color:white;font-weight:800;margin-left:10px">Start Free Trial →</a></div>
<nav class="navbar">
  <a href="/" class="navbar-logo">{LOGO_SVG}</a>
  <div class="nav-links">{nav_right}</div>
</nav>"""

def logo_html():
    return f"""<div class="logo">
    {LOGO_SVG}
    <p>AI Powered Professional SEO Platform</p>
</div><div class="divider"></div>"""

# ═══════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","").strip()
        if not name or not email or not password:
            return register_page("All fields are required!")
        users = load_users()
        if email in users:
            return register_page("Email already registered! Please login.")
        trial_end = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
        users[email] = {
            "name": name,
            "email": email,
            "password": hash_password(password),
            "plan": "free",
            "trial_end": trial_end,
            "created": datetime.now().strftime('%Y-%m-%d')
        }
        save_users(users)
        session['user'] = {"name": name, "email": email}
        return redirect("/")
    return register_page()

def register_page(error=""):
    return f"""{head("Register")}
<div class="auth-card">
    <div style="text-align:center;margin-bottom:20px">{LOGO_SVG}</div>
    <h2>Create Free Account</h2>
    <p style="text-align:center;color:#95a5a6;font-size:13px;margin-bottom:20px">🎉 7 Days FREE Trial — No Credit Card Required!</p>
    {"<div style='background:#fdecea;color:#e74c3c;padding:12px;border-radius:10px;margin-bottom:15px;font-size:13px'>" + error + "</div>" if error else ""}
    <form method="POST">
        <div class="form-group">
            <label>Full Name</label>
            <input type="text" name="name" placeholder="Your name" required>
        </div>
        <div class="form-group">
            <label>Email Address</label>
            <input type="email" name="email" placeholder="your@email.com" required>
        </div>
        <div class="form-group">
            <label>Password</label>
            <input type="password" name="password" placeholder="Create password" required>
        </div>
        <button class="btn-main" type="submit">🚀 Start Free Trial</button>
    </form>
    <p style="text-align:center;margin-top:20px;font-size:13px;color:#95a5a6">Already have account? <a href="/login" style="color:#667eea;font-weight:700">Login</a></p>
</div></body></html>"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","").strip()
        users = load_users()
        user = users.get(email)
        if not user or user['password'] != hash_password(password):
            return login_page("Invalid email or password!")
        session['user'] = {"name": user['name'], "email": email}
        return redirect("/")
    return login_page()

def login_page(error=""):
    return f"""{head("Login")}
<div class="auth-card">
    <div style="text-align:center;margin-bottom:20px">{LOGO_SVG}</div>
    <h2>Welcome Back!</h2>
    {"<div style='background:#fdecea;color:#e74c3c;padding:12px;border-radius:10px;margin-bottom:15px;font-size:13px'>" + error + "</div>" if error else ""}
    <form method="POST">
        <div class="form-group">
            <label>Email Address</label>
            <input type="email" name="email" placeholder="your@email.com" required>
        </div>
        <div class="form-group">
            <label>Password</label>
            <input type="password" name="password" placeholder="Your password" required>
        </div>
        <button class="btn-main" type="submit">Login →</button>
    </form>
    <p style="text-align:center;margin-top:20px;font-size:13px;color:#95a5a6">New user? <a href="/register" style="color:#667eea;font-weight:700">Create Free Account</a></p>
</div></body></html>"""

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/pricing")
def pricing():
    return f"""{head("Pricing")}
<div class="container">
    {logo_html()}
    <h2 style="text-align:center">Choose Your Plan</h2>
    <p style="text-align:center;color:#95a5a6;margin-bottom:30px;font-size:14px">Start with 7 days free trial — No credit card required!</p>
    <div class="pricing-grid">
        <div class="pricing-card">
            <h3>🆓 Free</h3>
            <div class="price">$0</div>
            <p style="color:#95a5a6;font-size:13px">Forever free</p>
            <ul>
                <li>15 searches per day</li>
                <li>3 articles per day</li>
                <li>Article Writer only</li>
                <li>Basic website audit</li>
            </ul>
            <a href="/register" class="btn-main" style="display:block;text-align:center;text-decoration:none;margin-top:15px">Get Started</a>
        </div>
        <div class="pricing-card featured">
            <div style="background:#667eea;color:white;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;display:inline-block;margin-bottom:10px">MOST POPULAR</div>
            <h3>💎 Basic</h3>
            <div class="price">$9<span style="font-size:16px;color:#95a5a6">/mo</span></div>
            <ul>
                <li>Unlimited searches</li>
                <li>Unlimited articles</li>
                <li>All On-Page tools</li>
                <li>Full website audit</li>
                <li>Priority support</li>
            </ul>
            <a href="/register" class="btn-main" style="display:block;text-align:center;text-decoration:none;margin-top:15px">Start Free Trial</a>
        </div>
        <div class="pricing-card">
            <h3>🔥 Pro</h3>
            <div class="price">$10<span style="font-size:16px;color:#95a5a6">/mo</span></div>
            <ul>
                <li>Everything in Basic</li>
                <li>Technical SEO (full)</li>
                <li>Off-Page SEO tools</li>
                <li>Competitor analysis</li>
                <li>Backlink opportunities</li>
            </ul>
            <a href="/register" class="btn-main btn-orange" style="display:block;text-align:center;text-decoration:none;margin-top:15px">Start Free Trial</a>
        </div>
    </div>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>"""

# ═══════════════════════════════════════════════
# HOME — STEP 1
# ═══════════════════════════════════════════════
@app.route("/")
def home():
    user = get_user()
    if not user:
        return redirect("/register")

    plan = get_user_plan(user['email'])
    usage = get_usage(user['email'])
    cat_opts = "".join([f'<option value="{c}">{c}</option>' for c in CATEGORIES])
    country_opts = "".join([f'<option value="{c}">{c}</option>' for c in COUNTRIES])
    lang_opts = "".join([f'<option value="{l}">{l}</option>' for l in LANGUAGES])

    plan_color = {'free':'badge-free','trial':'badge-trial','basic':'badge-basic','pro':'badge-pro'}.get(plan,'badge-free')

    usage_html = f"""
    <div style="background:#f8f9ff;border-radius:12px;padding:15px 20px;margin-bottom:20px;border:2px solid #e8e8e8;">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
            <div>
                <strong style="color:#2c3e50">Welcome, {user['name']}! 👋</strong>
                <span class="plan-badge {plan_color}" style="margin-left:10px">{plan.upper()}</span>
                {"<span style='color:#e67e22;font-size:12px;margin-left:8px'>Trial ends " + (load_users().get(user['email'],{}).get('trial_end','')) + "</span>" if plan == 'trial' else ""}
            </div>
            <div style="display:flex;gap:20px;align-items:center;">
                <div style="text-align:center">
                    <div style="font-size:11px;color:#95a5a6">SEARCHES TODAY</div>
                    <div style="font-weight:700;color:#667eea">{usage['searches']}/{"∞" if plan in ["trial","basic","pro"] else "15"}</div>
                    {"<div class='usage-bar'><div class='usage-fill' style='width:" + str(min(100, usage['searches']*100//15)) + "%'></div></div>" if plan == 'free' else ""}
                </div>
                <div style="text-align:center">
                    <div style="font-size:11px;color:#95a5a6">ARTICLES TODAY</div>
                    <div style="font-weight:700;color:#764ba2">{usage['articles']}/{"∞" if plan in ["trial","basic","pro"] else "3"}</div>
                </div>
                {"<a href='/pricing' style='background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:8px 16px;border-radius:20px;font-size:12px;font-weight:700;text-decoration:none'>⚡ Upgrade</a>" if plan == 'free' else ""}
            </div>
        </div>
    </div>"""

    return f"""{head()}
<div class="container">
    {logo_html()}
    {usage_html}
    <form action="/audit" method="POST">
        <div class="step-badge">⚙️ Step 1 — Website Setup</div>
        <div class="grid-2">
            <div class="form-group">
                <label>📂 Business Category</label>
                <select name="category" required>
                    <option value="">-- Select Category --</option>
                    {cat_opts}
                </select>
            </div>
            <div class="form-group">
                <label>🌐 Website URL</label>
                <input type="text" name="website" placeholder="https://yourwebsite.com" required>
            </div>
            <div class="form-group">
                <label>🌍 Target Country</label>
                <select name="country">{country_opts}</select>
            </div>
            <div class="form-group">
                <label>🗣️ Language</label>
                <select name="language">{lang_opts}</select>
            </div>
        </div>
        <div class="form-group">
            <label>🌐 Website Status</label>
            <div class="website-type-group">
                <div class="website-type-card selected" onclick="selectWebsiteType(this)">
                    <input type="radio" name="website_age" value="new" checked>
                    <div class="icon">🆕</div>
                    <div class="name">New Website</div>
                    <div class="desc">Recently launched or under development</div>
                </div>
                <div class="website-type-card" onclick="selectWebsiteType(this)">
                    <input type="radio" name="website_age" value="old">
                    <div class="icon">🏛️</div>
                    <div class="name">Existing Website</div>
                    <div class="desc">Already live, want to improve SEO</div>
                </div>
            </div>
        </div>
        <button class="btn-main" type="submit">🔍 Audit Your Website →</button>
    </form>
</div></body></html>"""

# ═══════════════════════════════════════════════
# STEP 2 — FULL AUDIT
# ═══════════════════════════════════════════════
@app.route("/audit", methods=["POST"])
def audit():
    user = get_user()
    if not user:
        return redirect("/login")

    can, plan = can_use(user['email'], 'search')
    if not can:
        return redirect("/pricing")
    increment_usage(user['email'], 'search')

    category = request.form.get("category")
    website  = request.form.get("website","").strip()
    country  = request.form.get("country")
    language = request.form.get("language")
    website_age = request.form.get("website_age","old")

    if not website.startswith("http"):
        website = "https://" + website

    html_content, status_code, final_url = fetch_html(website)
    target_url = final_url if final_url else website
    domain = urlparse(target_url).netloc

    if not html_content:
        return make_response(f"""{head()}
        <div class="container">{logo_html()}
        <h2>❌ Could Not Fetch Website</h2>
        <div class="result-card"><div class="result-card-head red">⚠️ Connection Error</div>
        <div class="result-card-body">Could not connect to <strong><a href="{website}" target="_blank">{website}</a></strong>.<br>Please check the URL and try again.</div></div>
        <div class="buttons"><a href="/" class="btn btn-p">← Try Again</a></div>
        </div></body></html>""")

    meta = get_meta(html_content)
    page_size_kb = len(html_content.encode('utf-8')) / 1024
    images = get_images(html_content)
    internal_links = get_internal_links(html_content, target_url)
    external_links = get_external_links(html_content, target_url)
    has_ssl = check_ssl(target_url)
    has_viewport = re.search(r'<meta[^>]+name=["\']viewport["\']', html_content, re.IGNORECASE) is not None
    has_jsonld = '"@context"' in html_content
    schema_types = list(set(re.findall(r'"@type"\s*:\s*"([^"]+)"', html_content)))
    og_title = re.search(r'<meta[^>]+property=["\']og:title["\']', html_content, re.IGNORECASE) is not None
    og_image = re.search(r'<meta[^>]+property=["\']og:image["\']', html_content, re.IGNORECASE) is not None

    missing_alt = []
    for img in images:
        if 'alt=""' in img or "alt=''" in img or 'alt=' not in img.lower():
            src_m = re.search(r'src=["\']([^"\']+)["\']', img)
            missing_alt.append(src_m.group(1) if src_m else "unknown")

    anchors = re.findall(r'<a[^>]+href=[^>]+>([^<]*)</a>', html_content, re.IGNORECASE)
    generic_anchors = list(set([a.strip() for a in anchors if a.strip().lower() in ["click here","here","read more","learn more","more","link"]]))

    robots_url = target_url.rstrip("/") + "/robots.txt"
    robots_html, robots_status, _ = fetch_html(robots_url)
    robots_found = robots_status == 200 and robots_html
    robots_blocks_all = robots_found and "Disallow: /" in (robots_html or "")

    sitemap_url = target_url.rstrip("/") + "/sitemap.xml"
    sitemap_html, sitemap_status, _ = fetch_html(sitemap_url)
    sitemap_found = sitemap_status == 200 and sitemap_html

    is_noindex = meta.get("robots") and "noindex" in meta.get("robots","").lower()

    # Score
    score = 100
    issues = {'critical':[],'important':[],'minor':[]}

    if not has_ssl:
        score -= 15
        issues['critical'].append(("No SSL/HTTPS", "Your website doesn't have SSL. Google penalizes HTTP sites. Install SSL certificate immediately."))
    if is_noindex:
        score -= 25
        issues['critical'].append(("Homepage Noindex", "Your homepage has noindex tag! Google cannot index your site."))
    if robots_blocks_all:
        score -= 20
        issues['critical'].append(("Robots.txt Blocking Site", "Your robots.txt is blocking all search engines from crawling your site!"))
    if not meta.get("title"):
        score -= 10
        issues['critical'].append(("Missing Title Tag", "No title tag found. This is critical for SEO rankings."))
    if not meta.get("description"):
        score -= 8
        issues['important'].append(("Missing Meta Description", "No meta description found. Add one to improve click-through rates in search results."))
    if meta.get("h1_count",0) == 0:
        score -= 8
        issues['important'].append(("No H1 Tag", "No H1 heading found on homepage. Every page needs exactly one H1 tag."))
    if meta.get("h1_count",0) > 1:
        score -= 5
        issues['important'].append(("Multiple H1 Tags", f"Found {meta.get('h1_count')} H1 tags. Use only ONE H1 per page."))
    if not sitemap_found:
        score -= 7
        issues['important'].append(("No XML Sitemap", "No sitemap.xml found. Create and submit sitemap to Google Search Console."))
    if not robots_found:
        score -= 5
        issues['important'].append(("No Robots.txt", "No robots.txt found. Create one to guide search engine crawlers."))
    if missing_alt:
        score -= min(10, len(missing_alt)*2)
        issues['important'].append((f"{len(missing_alt)} Images Missing Alt Tags", "Images without alt text hurt accessibility and image SEO."))
    if not has_jsonld:
        score -= 6
        issues['minor'].append(("No Schema Markup", "No structured data found. Add schema markup to enable rich results in Google."))
    if not has_viewport:
        score -= 8
        issues['important'].append(("No Mobile Viewport", "Missing viewport meta tag. Your site may not display correctly on mobile."))
    if not og_title or not og_image:
        score -= 4
        issues['minor'].append(("Incomplete Open Graph Tags", "Missing OG tags. Add them so your pages look good when shared on social media."))
    if generic_anchors:
        score -= 3
        issues['minor'].append(("Generic Anchor Texts", f"Found generic anchors: {', '.join(generic_anchors)}. Use descriptive keyword-rich anchor text."))
    if page_size_kb > 500:
        score -= 5
        issues['minor'].append(("Large Page Size", f"Page size is {page_size_kb:.0f}KB. Optimize images and minify code to improve speed."))
    if meta.get("title") and len(meta.get("title","")) > 60:
        score -= 3
        issues['minor'].append(("Title Too Long", f"Title is {len(meta.get('title',''))} characters. Keep it under 60 characters."))
    if meta.get("description") and len(meta.get("description","")) > 160:
        score -= 2
        issues['minor'].append(("Meta Description Too Long", f"Description is {len(meta.get('description',''))} characters. Keep it under 160."))

    score = max(0, score)
    score_color = "#27ae60" if score>=80 else "#f39e0b" if score>=60 else "#e74c3c"

    # Build issues HTML
    def issues_html(items, cls, icon):
        html = ""
        for title, desc in items:
            html += f'<div class="issue-{cls}"><div class="issue-title">{icon} {title}</div><div class="issue-desc">{desc}</div></div>'
        return html or f'<div style="color:#27ae60;padding:10px">✅ No {cls} issues found!</div>'

    total_issues = len(issues['critical']) + len(issues['important']) + len(issues['minor'])

    return make_response(f"""{head("Website Audit")}
<div class="container">
    {logo_html()}
    <div class="step-badge">📊 Step 2 — Complete Website Audit</div>
    <h2>Website Audit Report</h2>
    <div class="info-bar">
        <span>🌐 <a href="{target_url}" target="_blank" style="color:#667eea">{target_url}</a></span>
        <span>📂 {category}</span><span>🌍 {country}</span>
        <span>🌐 {"New Website" if website_age=="new" else "Existing Website"}</span>
    </div>

    <div style="text-align:center;margin-bottom:25px">
        <div style="width:100px;height:100px;border-radius:50%;background:{score_color};display:flex;align-items:center;justify-content:center;margin:0 auto 10px;flex-direction:column">
            <span style="font-size:32px;font-weight:800;color:white">{score}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.8)">/100</span>
        </div>
        <strong style="font-size:16px;color:#2c3e50">SEO Health Score</strong>
        <p style="color:#95a5a6;font-size:13px;margin-top:5px">{total_issues} issues found</p>
    </div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL/HTTPS</div></div>
        <div class="stat-box"><div class="stat-num">{page_size_kb:.0f}KB</div><div class="stat-label">Page Size</div></div>
        <div class="stat-box"><div class="stat-num">{len(images)}</div><div class="stat-label">Images</div></div>
        <div class="stat-box"><div class="stat-num">{len(internal_links)}</div><div class="stat-label">Internal Links</div></div>
        <div class="stat-box"><div class="stat-num">{len(external_links)}</div><div class="stat-label">External Links</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_viewport else "red"}">{"✅" if has_viewport else "❌"}</div><div class="stat-label">Mobile Ready</div></div>
    </div>

    <div class="result-card">
        <div class="result-card-head">📋 Page Meta Information</div>
        <div class="result-card-body" style="white-space:normal">
            <strong>Title:</strong> {meta.get('title') or '❌ Missing'} {f"({len(meta.get('title',''))} chars)" if meta.get('title') else ""}<br>
            <strong>Description:</strong> {meta.get('description') or '❌ Missing'}<br>
            <strong>H1 Tags:</strong> {meta.get('h1_count',0)} found {"✅" if meta.get('h1_count')==1 else "⚠️"} {f"— {meta.get('h1_text','')[:60]}" if meta.get('h1_text') else ""}<br>
            <strong>Canonical:</strong> {meta.get('canonical') or '❌ Not set'}<br>
            <strong>Schema:</strong> {", ".join(schema_types) if schema_types else "❌ Not found"}<br>
            <strong>Robots.txt:</strong> {"✅ Found" if robots_found else "❌ Missing"} | <strong>Sitemap:</strong> {"✅ Found" if sitemap_found else "❌ Missing"}
        </div>
    </div>

    <h3 style="color:#e74c3c;margin-bottom:15px">🔴 Critical Issues ({len(issues['critical'])})</h3>
    {issues_html(issues['critical'], 'critical', '🔴')}

    <h3 style="color:#e67e22;margin:20px 0 15px">🟡 Important Issues ({len(issues['important'])})</h3>
    {issues_html(issues['important'], 'important', '🟡')}

    <h3 style="color:#27ae60;margin:20px 0 15px">🟢 Minor Issues ({len(issues['minor'])})</h3>
    {issues_html(issues['minor'], 'minor', '🟢')}

    <form action="/fix-guide" method="POST" style="margin-top:25px">
        <input type="hidden" name="category" value="{category}">
        <input type="hidden" name="website" value="{target_url}">
        <input type="hidden" name="country" value="{country}">
        <input type="hidden" name="language" value="{language}">
        <input type="hidden" name="website_age" value="{website_age}">
        <input type="hidden" name="score" value="{score}">
        <input type="hidden" name="issues" value="{quote(json.dumps(issues))}">
        <button class="btn-main" type="submit">🔧 How to Fix These Issues →</button>
    </form>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

# ═══════════════════════════════════════════════
# STEP 3 — FIX GUIDE
# ═══════════════════════════════════════════════
@app.route("/fix-guide", methods=["POST"])
def fix_guide():
    user = get_user()
    if not user: return redirect("/login")

    category = request.form.get("category")
    website  = request.form.get("website")
    country  = request.form.get("country")
    language = request.form.get("language")
    website_age = request.form.get("website_age")
    score = request.form.get("score")
    issues_raw = unquote(request.form.get("issues","{}"))

    try:
        issues = json.loads(issues_raw)
    except:
        issues = {'critical':[],'important':[],'minor':[]}

    all_issues = issues.get('critical',[]) + issues.get('important',[]) + issues.get('minor',[])
    issues_text = "\n".join([f"- {title}: {desc}" for title, desc in all_issues])

    prompt = f"""You are a Senior SEO Expert. Website: {website}, Category: {category}, Country: {country}, SEO Score: {score}/100.

These issues were found:
{issues_text}

For each issue, provide:
1. Simple step-by-step fix instructions (2-4 steps)
2. Priority level (Do it NOW / Do it this week / Do it this month)
3. Expected improvement after fixing

Format each issue clearly with the issue name as header. Be specific and actionable. Keep each fix explanation clear and simple."""

    guide = ai_call(prompt, max_tokens=1500)
    guide_display = guide.replace('<','&lt;').replace('>','&gt;')

    return make_response(f"""{head("Fix Guide")}
<div class="container">
    {logo_html()}
    <div class="step-badge">🔧 Step 3 — How to Fix Issues</div>
    <h2>Complete Fix Guide</h2>
    <div class="info-bar">
        <span>🌐 <a href="{website}" target="_blank" style="color:#667eea">{website}</a></span>
        <span>📊 Score: {score}/100</span>
        <span>📂 {category}</span>
    </div>

    <div class="result-card">
        <div class="result-card-head green">✅ AI-Generated Fix Guide</div>
        <div class="result-card-body">{guide_display}</div>
    </div>

    <form action="/seo-tools" method="POST" style="margin-top:25px">
        <input type="hidden" name="category" value="{category}">
        <input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}">
        <input type="hidden" name="language" value="{language}">
        <button class="btn-main" type="submit">🚀 Continue to SEO Tools →</button>
    </form>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

# ═══════════════════════════════════════════════
# STEP 4 — SEO TOOLS SELECTION
# ═══════════════════════════════════════════════
@app.route("/seo-tools", methods=["POST"])
def seo_tools():
    user = get_user()
    if not user: return redirect("/login")

    category = request.form.get("category")
    website  = request.form.get("website")
    country  = request.form.get("country")
    language = request.form.get("language")
    plan = get_user_plan(user['email'])

    return make_response(f"""{head("SEO Tools")}
<div class="container">
    {logo_html()}
    <div class="step-badge">🎯 Step 4 — Choose SEO Tool</div>
    <h2>Select SEO Type</h2>
    <div class="info-bar">
        <span>🌐 <a href="{website}" target="_blank" style="color:#667eea">{website}</a></span>
        <span>📂 {category}</span><span>🌍 {country}</span>
    </div>

    <form action="/seo-route" method="POST">
        <input type="hidden" name="category" value="{category}">
        <input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}">
        <input type="hidden" name="language" value="{language}">
        <div class="seo-type-group">
            <div class="seo-type-card selected" onclick="selectSeoType(this)">
                <div class="plan-tag tag-free">FREE</div>
                <input type="radio" name="seo_type" value="On-Page" checked>
                <div class="icon">🟢</div>
                <div class="name">On-Page SEO</div>
                <div class="desc">Content & Keywords</div>
            </div>
            <div class="seo-type-card" onclick="selectSeoType(this)">
                <div class="plan-tag tag-pro">PRO $10</div>
                <input type="radio" name="seo_type" value="Technical">
                <div class="icon">🔵</div>
                <div class="name">Technical SEO</div>
                <div class="desc">Full Site Audit</div>
            </div>
            <div class="seo-type-card" onclick="selectSeoType(this)">
                <div class="plan-tag tag-pro">PRO $10</div>
                <input type="radio" name="seo_type" value="Off-Page">
                <div class="icon">🔴</div>
                <div class="name">Off-Page SEO</div>
                <div class="desc">Backlinks & Competitors</div>
            </div>
        </div>
        <button class="btn-main" type="submit" style="margin-top:20px">Next Step →</button>
    </form>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

@app.route("/seo-route", methods=["POST"])
def seo_route():
    user = get_user()
    if not user: return redirect("/login")

    seo_type = request.form.get("seo_type")
    category = request.form.get("category")
    website  = request.form.get("website")
    country  = request.form.get("country")
    language = request.form.get("language")
    plan = get_user_plan(user['email'])

    if seo_type in ["Technical","Off-Page"] and plan not in ["trial","pro"]:
        return redirect("/pricing")

    if seo_type == "On-Page":
        return onpage_subtypes(category, website, country, language, plan)
    elif seo_type == "Technical":
        return technical_report(category, website, country, language)
    else:
        return offpage_report(category, website, country, language)

# ═══════════════════════════════════════════════
# ON-PAGE
# ═══════════════════════════════════════════════
def onpage_subtypes(category, website, country, language, plan):
    subtypes = [
        ("✍️","Article Writer","Blog & informational articles","article_writer","free"),
        ("📄","Page Content Writer","Homepage, About, landing pages","page_content","basic"),
        ("⚙️","Service Page Writer","Service description pages","service_page","basic"),
        ("📍","Service Areas Writer","Location-based service pages","service_areas","basic"),
        ("🧠","Semantic SEO Writer","Topic clusters & semantic content","semantic_seo","basic"),
    ]

    tag_map = {"free":"tag-free","basic":"tag-basic","pro":"tag-pro"}
    label_map = {"free":"FREE","basic":"$9/mo","pro":"$10/mo"}

    cards = ""
    for icon,name,desc,val,req_plan in subtypes:
        allowed = plan in ["trial","pro","basic"] or req_plan == "free"
        locked_class = "" if allowed else " locked"
        lock_icon = "" if allowed else " 🔒"
        cards += f"""<form action="/onpage-writer" method="POST" style="display:contents">
            <input type="hidden" name="category" value="{category}">
            <input type="hidden" name="website" value="{website}">
            <input type="hidden" name="country" value="{country}">
            <input type="hidden" name="language" value="{language}">
            <input type="hidden" name="writer_type" value="{val}">
            <button type="submit" style="background:none;border:none;padding:0;cursor:pointer;display:block;width:100%" {"disabled" if not allowed else ""}>
                <div class="sub-type-card{locked_class}">
                    <div class="plan-tag {tag_map[req_plan]}">{label_map[req_plan]}</div>
                    <div class="icon">{icon}</div>
                    <div class="name">{name}{lock_icon}</div>
                    <div class="desc">{desc}</div>
                </div>
            </button></form>"""

    upgrade = f"""<div class="upgrade-box" style="margin-top:20px">
        <h3>⚡ Unlock All On-Page Tools</h3>
        <p>Get Page Content Writer, Service Page Writer, Service Areas Writer & Semantic SEO Writer</p>
        <a href="/pricing" class="upgrade-btn">Upgrade to Basic — $9/mo</a>
    </div>""" if plan == 'free' else ""

    return make_response(f"""{head("On-Page SEO")}
<div class="container">{logo_html()}
    <div class="step-badge">🟢 On-Page SEO</div>
    <h2>Select Content Type</h2>
    <div class="sub-type-group">{cards}</div>
    {upgrade}
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

@app.route("/onpage-writer", methods=["POST"])
def onpage_writer():
    user = get_user()
    if not user: return redirect("/login")

    can, plan = can_use(user['email'], 'search')
    if not can: return redirect("/pricing")
    increment_usage(user['email'], 'search')

    category=request.form.get("category"); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language"); writer_type=request.form.get("writer_type")

    wl={"article_writer":"✍️ Article Writer","page_content":"📄 Page Content Writer","service_page":"⚙️ Service Page Writer","service_areas":"📍 Service Areas Writer","semantic_seo":"🧠 Semantic SEO Writer"}
    label=wl.get(writer_type,"Content Writer")

    kw_map={"article_writer":"blog article topics, informational keywords, long-tail question keywords","page_content":"homepage, about page, landing page keywords","service_page":"service-specific commercial keywords","service_areas":"local SEO, location-based service keywords","semantic_seo":"semantic clusters, LSI keywords, topic authority keywords"}
    kw_focus=kw_map.get(writer_type,"SEO keywords")

    result=ai_call(f"""SEO expert. Website: {website}, Business: {category}, Country: {country}\nFocus: {kw_focus}\nReturn ONLY 10 keywords in pipe format:\nkeyword | 40,000/mo | EASY | Informational\n10 lines only. No extra text.""")

    rows=""
    for line in result.strip().split('\n'):
        if '|' in line:
            p=[x.strip() for x in line.split('|')]
            if len(p)>=4:
                kd=p[2].upper()
                badge=f'<span class="badge {"badge-easy" if "EASY" in kd else "badge-medium" if "MEDIUM" in kd else "badge-hard"}">{p[2]}</span>'
                rows+=f"""<tr><td><strong>{p[0]}</strong></td><td>📊 {p[1]}</td><td>{badge}</td><td>{p[3]}</td>
                <td><form action="/article-settings" method="POST" style="margin:0">
                    <input type="hidden" name="keyword" value="{p[0]}"><input type="hidden" name="website" value="{website}">
                    <input type="hidden" name="country" value="{country}"><input type="hidden" name="language" value="{language}">
                    <input type="hidden" name="category" value="{category}"><input type="hidden" name="writer_type" value="{writer_type}">
                    <button type="submit" style="padding:6px 14px;font-size:12px;border-radius:8px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;cursor:pointer;font-weight:600">✍️ Write</button>
                </form></td></tr>"""

    custom_row=f"""<tr style="background:#f8f9ff"><td colspan="4"><strong>✏️ Custom Keyword</strong></td>
    <td><form action="/article-settings" method="POST" style="margin:0;display:flex;gap:6px">
        <input type="hidden" name="website" value="{website}"><input type="hidden" name="country" value="{country}">
        <input type="hidden" name="language" value="{language}"><input type="hidden" name="category" value="{category}">
        <input type="hidden" name="writer_type" value="{writer_type}">
        <input type="text" name="keyword" placeholder="Your keyword..." style="padding:6px 10px;border-radius:8px;border:2px solid #667eea;font-size:12px;width:150px">
        <button type="submit" style="padding:6px 12px;font-size:12px;border-radius:8px;background:linear-gradient(135deg,#27ae60,#2ecc71);color:white;border:none;cursor:pointer;font-weight:600">Go</button>
    </form></td></tr>"""

    return make_response(f"""{head("Keywords Found")}
<div class="container">{logo_html()}
<h2>🔍 Keywords Found!</h2>
<div class="info-bar"><span>🌐 <a href="{website}" target="_blank" style="color:#667eea">{website}</a></span><span>📂 {category}</span><span>🌍 {country}</span><span>{label}</span></div>
<table><thead><tr><th>Keyword</th><th>Volume</th><th>Difficulty</th><th>Intent</th><th>Action</th></tr></thead>
<tbody>{rows or "<tr><td colspan='5' style='text-align:center;padding:20px;color:#e74c3c'>Could not load keywords. Try again.</td></tr>"}{custom_row}</tbody></table>
<a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

@app.route("/article-settings", methods=["POST"])
def article_settings():
    user = get_user()
    if not user: return redirect("/login")

    keyword=request.form.get("keyword","").strip(); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language")
    category=request.form.get("category"); writer_type=request.form.get("writer_type")
    if not keyword: return "<h3 style='color:red;padding:30px'>Keyword missing.</h3>"

    return make_response(f"""{head("Article Settings")}
<div class="container">{logo_html()}
    <div class="step-badge">✍️ Article Settings</div><h2>Configure Your Article</h2>
    <span class="keyword-badge">🎯 {keyword}</span>
    <form action="/ai-suggest" method="POST">
        <input type="hidden" name="keyword" value="{keyword}"><input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}"><input type="hidden" name="language" value="{language}">
        <input type="hidden" name="category" value="{category}"><input type="hidden" name="writer_type" value="{writer_type}">
        <div class="step"><h3>📊 Article Length</h3>
            <select name="length"><option value="500">Short — 500 words</option><option value="1000" selected>Medium — 1000 words</option><option value="2000">Long — 2000 words</option><option value="3000">Extra Long — 3000 words</option></select></div>
        <div class="step"><h3>🎯 Writing Intent</h3>
            <select name="intent"><option value="Informational">📚 Informational</option><option value="Professional">💼 Professional</option><option value="Casual">😊 Casual</option><option value="Transactional">🛒 Transactional</option><option value="Commercial">💰 Commercial</option></select></div>
        <div class="step"><h3>🏪 Content Type</h3>
            <select name="content_type"><option value="Blogging Site">📝 Blogging Site</option><option value="Ecommerce Site">🛍️ Ecommerce</option><option value="Services Site">⚙️ Services</option></select></div>
        <div class="step"><h3>✨ Extra Sections</h3>
            <div class="checkbox-group">
                <label class="checkbox-item"><input type="checkbox" name="intro" value="yes" checked> 📖 Strong Intro</label>
                <label class="checkbox-item"><input type="checkbox" name="faqs" value="yes"> ❓ FAQs</label>
                <label class="checkbox-item"><input type="checkbox" name="paa" value="yes"> 🔎 People Also Ask</label>
                <label class="checkbox-item"><input type="checkbox" name="conclusion" value="yes" checked> 📝 Conclusion</label>
            </div></div>
        <button class="btn-main" type="submit">🤖 Get AI Suggestions →</button>
    </form>
    <a href="javascript:history.back()" class="back-link">← Go Back</a>
</div></body></html>""")

@app.route("/ai-suggest", methods=["POST"])
def ai_suggest():
    user = get_user()
    if not user: return redirect("/login")

    keyword=request.form.get("keyword"); website=request.form.get("website"); country=request.form.get("country")
    language=request.form.get("language"); category=request.form.get("category"); writer_type=request.form.get("writer_type")
    length=request.form.get("length"); intent=request.form.get("intent"); content_type=request.form.get("content_type")
    intro=request.form.get("intro",""); faqs=request.form.get("faqs",""); paa=request.form.get("paa",""); conclusion=request.form.get("conclusion","")

    result=ai_call(f"""SEO expert. Keyword: '{keyword}', Business: {category}, Country: {country}\nReturn ONLY:\nCATEGORIES: Cat One | Cat Two | Cat Three\nTITLE1: ...\nTITLE2: ...\nTITLE3: ...\nDESC1: ...\nDESC2: ...\nDESC3: ...\nNothing else.""")

    cats,titles,descs=[],[],[]
    for line in result.strip().split('\n'):
        l=line.strip()
        if l.upper().startswith('CATEGORIES:'): cats=[c.strip() for c in l.split(':',1)[-1].split('|') if c.strip()]
        elif l.upper().startswith('TITLE'):
            v=l.split(':',1)[-1].strip()
            if v: titles.append(v)
        elif l.upper().startswith('DESC'):
            v=l.split(':',1)[-1].strip()
            if v: descs.append(v)

    if not cats: cats=["Products","Services","Information"]
    if not titles: titles=[f"Best {keyword} 2026",f"Top {keyword} Guide",f"Complete {keyword} Tips"]
    if not descs: descs=[f"Learn about {keyword}.",f"Discover {keyword} tips.",f"Complete {keyword} guide."]

    cats.append("✏️ Custom"); titles.append("✏️ Custom"); descs.append("✏️ Custom")
    co="".join([f'<option value="{c}">{c}</option>' for c in cats])
    to="".join([f'<option value="{t}">{t}</option>' for t in titles])
    do="".join([f'<option value="{d}">{d}</option>' for d in descs])

    return make_response(f"""{head("AI Suggestions")}
<div class="container">{logo_html()}
    <div class="step-badge">🤖 AI Suggestions</div><h2>Select Your Preferences</h2>
    <span class="keyword-badge">🎯 {keyword}</span>
    <form action="/generate-article" method="POST" id="mainform">
        <input type="hidden" name="keyword" value="{keyword}"><input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}"><input type="hidden" name="language" value="{language}">
        <input type="hidden" name="length" value="{length}"><input type="hidden" name="intent" value="{intent}">
        <input type="hidden" name="content_type" value="{content_type}"><input type="hidden" name="category" value="{category}">
        <input type="hidden" name="writer_type" value="{writer_type}"><input type="hidden" name="intro" value="{intro}">
        <input type="hidden" name="faqs" value="{faqs}"><input type="hidden" name="paa" value="{paa}">
        <input type="hidden" name="conclusion" value="{conclusion}">
        <input type="hidden" name="sub_category" id="final_category"><input type="hidden" name="meta_title" id="final_title"><input type="hidden" name="meta_desc" id="final_desc">
        <div class="step"><h3>📂 Select Category</h3><select id="cat_select" onchange="checkCustom(this,'cat_input')">{co}</select><input type="text" id="cat_input" class="custom-input" placeholder="Custom category..."></div>
        <div class="step"><h3>📌 Select Meta Title</h3><select id="title_select" onchange="checkCustom(this,'title_input')">{to}</select><input type="text" id="title_input" class="custom-input" placeholder="Custom meta title..."></div>
        <div class="step"><h3>📝 Select Meta Description</h3><select id="desc_select" onchange="checkCustom(this,'desc_input')">{do}</select><input type="text" id="desc_input" class="custom-input" placeholder="Custom meta description..."></div>
        <button class="btn-main" type="button" onclick="submitSuggestForm()">🚀 Generate Article!</button>
    </form>
    <a href="javascript:history.back()" class="back-link">← Go Back</a>
</div></body></html>""")

@app.route("/generate-article", methods=["POST"])
def generate_article():
    user = get_user()
    if not user: return redirect("/login")

    can, plan = can_use(user['email'], 'article')
    if not can:
        return make_response(f"""{head()}
        <div class="container">{logo_html()}
        <div class="upgrade-box">
            <h3>✍️ Daily Article Limit Reached!</h3>
            <p>You've used all 3 free articles today. Upgrade to write unlimited articles!</p>
            <a href="/pricing" class="upgrade-btn">Upgrade Now</a>
        </div>
        <a href="/" class="back-link">← Go Back</a>
        </div></body></html>""")

    increment_usage(user['email'], 'article')

    keyword=request.form.get("keyword"); website=request.form.get("website"); country=request.form.get("country")
    language=request.form.get("language"); length=request.form.get("length"); intent=request.form.get("intent")
    content_type=request.form.get("content_type"); category=request.form.get("category"); writer_type=request.form.get("writer_type")
    sub_category=request.form.get("sub_category"); meta_title=request.form.get("meta_title"); meta_desc=request.form.get("meta_desc")
    intro=request.form.get("intro",""); faqs=request.form.get("faqs",""); paa=request.form.get("paa",""); conclusion=request.form.get("conclusion","")

    wl={"article_writer":"Article Writer","page_content":"Page Content Writer","service_page":"Service Page Writer","service_areas":"Service Areas Writer","semantic_seo":"Semantic SEO Writer"}
    wlab=wl.get(writer_type,"Content Writer")

    secs=[]
    if intro=="yes": secs.append("## Introduction")
    secs+=["## Main Section 1","## Main Section 2","## Main Section 3"]
    if faqs=="yes": secs.append("## FAQs (5 with answers)")
    if paa=="yes": secs.append("## People Also Ask (5 with answers)")
    if conclusion=="yes": secs.append("## Conclusion")

    article=ai_call(f"""Write a {length}-word SEO article in {language}.\nKeyword: "{keyword}", Meta Title: {meta_title}\nBusiness: {category} — {sub_category}, Country: {country}, Intent: {intent}, Type: {content_type}\nStructure:\n# {meta_title}\n{chr(10).join(secs)}\nRules: keyword in first 100 words, keyword in 2+ headings, write fully in {language}, professional SEO content.""", max_tokens=2000)

    seo_guide="1. H1: ONE H1 with main keyword\n2. H2: Each section\n3. H3: Sub-points & FAQs\n4. Internal Links: 2-3 to your pages\n5. External Links: 1-2 authority sites\n6. URL: yoursite.com/keyword\n7. Keyword Density: 1-2%\n8. Image Alt: include keyword\n9. Meta Title: 50-60 chars\n10. Meta Description: 150-160 chars"

    fn=keyword.strip().replace(" ","_")+"_article.txt"
    content=f"META TITLE: {meta_title}\nMETA DESC: {meta_desc}\nKEYWORD: {keyword}\nLANGUAGE: {language}\nCOUNTRY: {country}\n\n{'='*50}\n\n{article}\n\n{'='*50}\nSEO GUIDELINES\n{'='*50}\n\n{seo_guide}"
    enc=quote(content)
    ad=article.replace('<','&lt;').replace('>','&gt;')

    return make_response(f"""{head("Article Ready")}
<div class="container">{logo_html()}
    <div class="success-icon">✅</div><h2>Article Ready!</h2>
    <div class="meta-card"><strong>🏷️ Writer:</strong> {wlab}<br><strong>📌 Meta Title:</strong> {meta_title}<br><strong>📝 Meta Desc:</strong> {meta_desc}<br><strong>📂 Category:</strong> {category} — {sub_category}<br><strong>🎯 Keyword:</strong> {keyword} | <strong>🌍</strong> {country} | <strong>🗣️</strong> {language}</div>
    <div class="article-box">{ad}</div>
    <div class="seo-box"><strong style="font-size:15px;color:#e67e22">📚 SEO Guidelines</strong><br><br>{seo_guide.replace(chr(10),'<br>')}</div>
    <div class="buttons">
        <a href="/download-file?content={enc}&filename={fn}" class="btn btn-g">⬇️ Download</a>
        <a href="/" class="btn btn-p">🔄 New Article</a>
        <a href="javascript:history.back()" class="btn btn-gr">← Back</a>
    </div>
</div></body></html>""")

# ═══════════════════════════════════════════════
# TECHNICAL SEO REPORT
# ═══════════════════════════════════════════════
def technical_report(category, website, country, language):
    html_content, status_code, final_url = fetch_html(website)
    target_url = final_url if final_url else website
    if not html_content:
        return make_response(f"""{head()}<div class="container">{logo_html()}<h2>❌ Could Not Fetch Website</h2><a href="/" class="back-link">← Back</a></div></body></html>""")

    meta = get_meta(html_content)
    page_size_kb = len(html_content.encode('utf-8')) / 1024
    images = get_images(html_content)
    internal_links = get_internal_links(html_content, target_url)
    external_links = get_external_links(html_content, target_url)
    has_ssl = check_ssl(target_url)
    has_viewport = re.search(r'<meta[^>]+name=["\']viewport["\']', html_content, re.IGNORECASE) is not None
    has_jsonld = '"@context"' in html_content
    schema_types = list(set(re.findall(r'"@type"\s*:\s*"([^"]+)"', html_content)))
    og_title = re.search(r'<meta[^>]+property=["\']og:title["\']', html_content, re.IGNORECASE) is not None
    og_image = re.search(r'<meta[^>]+property=["\']og:image["\']', html_content, re.IGNORECASE) is not None
    twitter_card = re.search(r'<meta[^>]+name=["\']twitter:card["\']', html_content, re.IGNORECASE) is not None

    missing_alt = []
    for img in images:
        if 'alt=""' in img or "alt=''" in img or 'alt=' not in img.lower():
            src_m = re.search(r'src=["\']([^"\']+)["\']', img)
            missing_alt.append(src_m.group(1) if src_m else "unknown")

    robots_url = target_url.rstrip("/") + "/robots.txt"
    robots_html, robots_status, _ = fetch_html(robots_url)
    robots_found = robots_status == 200 and robots_html

    sitemap_url = target_url.rstrip("/") + "/sitemap.xml"
    sitemap_html, sitemap_status, _ = fetch_html(sitemap_url)
    sitemap_found = sitemap_status == 200 and sitemap_html
    sitemap_url_count = len(re.findall(r'<url>', sitemap_html)) if sitemap_html else 0

    is_noindex = meta.get("robots") and "noindex" in meta.get("robots","").lower()

    score = 100
    deductions = []
    if not has_ssl: score-=15; deductions.append("No SSL/HTTPS (-15)")
    if not meta.get("title"): score-=8; deductions.append("Missing title tag (-8)")
    if not meta.get("description"): score-=8; deductions.append("Missing meta description (-8)")
    if meta.get("h1_count",0)==0: score-=8; deductions.append("No H1 tag (-8)")
    if missing_alt: score-=min(10,len(missing_alt)*2); deductions.append(f"{len(missing_alt)} images missing alt (-{min(10,len(missing_alt)*2)})")
    if not robots_found: score-=5; deductions.append("No robots.txt (-5)")
    if not sitemap_found: score-=7; deductions.append("No XML sitemap (-7)")
    if not has_jsonld: score-=6; deductions.append("No schema markup (-6)")
    if not has_viewport: score-=8; deductions.append("No mobile viewport (-8)")
    if not og_title or not og_image: score-=4; deductions.append("Incomplete OG tags (-4)")
    if is_noindex: score-=25; deductions.append("Homepage noindex! (-25)")
    score=max(0,score)
    score_color="#27ae60" if score>=80 else "#f39e0b" if score>=60 else "#e74c3c"

    ai_summary = ai_call(f"""Senior Technical SEO auditor. Real data for {target_url} ({category}, {country}):
- SSL: {"Yes" if has_ssl else "No"}, Score: {score}/100
- Meta Title: {meta.get('title') or 'MISSING'}
- Meta Desc: {"Present" if meta.get('description') else "MISSING"}
- H1: {meta.get('h1_count',0)}, Images Missing Alt: {len(missing_alt)}/{len(images)}
- Robots.txt: {"Found" if robots_found else "Missing"}, Sitemap: {"Found - " + str(sitemap_url_count) + " URLs" if sitemap_found else "Missing"}
- Schema: {"Found: " + ", ".join(schema_types[:3]) if has_jsonld else "Not found"}
- Mobile Viewport: {"Yes" if has_viewport else "No"}
- Internal Links: {len(internal_links)}, External: {len(external_links)}
Write 4-5 sentence professional summary. Only state facts from this data.""", max_tokens=400)

    ai_recs = ai_call(f"""Technical SEO expert. Issues for {target_url}:\n{chr(10).join(['- '+d for d in deductions]) if deductions else 'No major issues'}\nGive TOP 5 priority fixes with specific HOW-TO steps. Be concise.""", max_tokens=600)

    rows_int = "".join([f'<div class="url-item"><span class="url-text"><a href="{l}" target="_blank">{l}</a></span><span class="status-200">Internal</span></div>' for l in internal_links[:10]])

    return make_response(f"""{head("Technical SEO Report")}
<div class="container">
    {logo_html()}
    <div class="step-badge">🔵 Technical SEO — Full Report</div>
    <h2>Technical SEO Analysis</h2>
    <div class="info-bar"><span>🌐 <a href="{target_url}" target="_blank" style="color:#667eea">{target_url}</a></span><span>📂 {category}</span><span>🌍 {country}</span></div>

    <div style="text-align:center;margin-bottom:25px">
        <div style="width:100px;height:100px;border-radius:50%;background:{score_color};display:flex;align-items:center;justify-content:center;margin:0 auto 10px;flex-direction:column">
            <span style="font-size:32px;font-weight:800;color:white">{score}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.8)">/100</span>
        </div>
        <strong style="font-size:16px;color:#2c3e50">Technical SEO Score</strong>
    </div>

    <div class="result-card"><div class="result-card-head">📝 Executive Summary</div><div class="result-card-body">{ai_summary.replace('<','&lt;').replace('>','&gt;')}</div></div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL/HTTPS</div></div>
        <div class="stat-box"><div class="stat-num">{page_size_kb:.0f}KB</div><div class="stat-label">Page Size</div></div>
        <div class="stat-box"><div class="stat-num">{len(images)}</div><div class="stat-label">Images</div></div>
        <div class="stat-box"><div class="stat-num red">{len(missing_alt)}</div><div class="stat-label">Missing Alt Tags</div></div>
        <div class="stat-box"><div class="stat-num">{len(internal_links)}</div><div class="stat-label">Internal Links</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_viewport else "red"}">{"✅" if has_viewport else "❌"}</div><div class="stat-label">Mobile Ready</div></div>
    </div>

    <div class="result-card"><div class="result-card-head">🔍 Site Audit</div>
    <div class="result-card-body" style="white-space:normal">
        <strong>Meta Title:</strong> {meta.get('title') or '❌ Missing'} {f"({len(meta.get('title',''))} chars)" if meta.get('title') else ""}<br>
        <strong>Meta Description:</strong> {meta.get('description') or '❌ Missing'}<br>
        <strong>H1 Tags:</strong> {meta.get('h1_count',0)} {"✅" if meta.get('h1_count')==1 else "⚠️"}<br>
        <strong>Canonical:</strong> {meta.get('canonical') or '❌ Not set'}<br>
        <strong>Robots.txt:</strong> {"✅ Found" if robots_found else "❌ Missing"} | <strong>Sitemap:</strong> {"✅ Found (" + str(sitemap_url_count) + " URLs)" if sitemap_found else "❌ Missing"}<br>
        <strong>Schema:</strong> {", ".join(schema_types) if schema_types else "❌ Not found"}<br>
        <strong>OG Tags:</strong> Title: {"✅" if og_title else "❌"} | Image: {"✅" if og_image else "❌"} | Twitter Card: {"✅" if twitter_card else "❌"}<br>
        <strong>Homepage Indexing:</strong> {"❌ NOINDEX SET!" if is_noindex else "✅ Indexable"}
    </div></div>

    <div class="result-card"><div class="result-card-head">🔗 Internal Links</div>
    <div class="result-card-body">{rows_int or "<p>No internal links found.</p>"}</div></div>

    <div class="result-card"><div class="result-card-head orange">🎯 Top Priority Fixes</div>
    <div class="result-card-body">{ai_recs.replace('<','&lt;').replace('>','&gt;')}</div></div>

    <div class="buttons">
        <a href="/" class="btn btn-p">🔄 New Audit</a>
        <a href="javascript:history.back()" class="btn btn-gr">← Back</a>
    </div>
</div></body></html>""")

# ═══════════════════════════════════════════════
# OFF-PAGE SEO REPORT
# ═══════════════════════════════════════════════
def offpage_report(category, website, country, language):
    html_content, status_code, final_url = fetch_html(website)
    target_url = final_url if final_url else website
    if not html_content:
        return make_response(f"""{head()}<div class="container">{logo_html()}<h2>❌ Could Not Fetch Website</h2><a href="/" class="back-link">← Back</a></div></body></html>""")

    domain = urlparse(target_url).netloc
    external_links = get_external_links(html_content, target_url)
    ext_domains = list(set([urlparse(l).netloc for l in external_links]))
    has_ssl = check_ssl(target_url)
    social_platforms = ['facebook.com','twitter.com','x.com','instagram.com','linkedin.com','youtube.com','tiktok.com','pinterest.com']
    social_links = [d for d in ext_domains if any(sp in d for sp in social_platforms)]
    other_links = [d for d in ext_domains if d not in social_links]

    rows_social = "".join([f'<div class="url-item"><span class="url-text"><a href="https://{d}" target="_blank">{d}</a></span><span class="badge badge-blue">Social</span></div>' for d in social_links]) or "<p>No social media links found on homepage.</p>"
    rows_other = "".join([f'<div class="url-item"><span class="url-text"><a href="https://{d}" target="_blank">{d}</a></span><span class="badge badge-easy">External</span></div>' for d in other_links[:10]]) or "<p>No other external domains found.</p>"

    backlink_result = ai_call(f"""Off-Page SEO expert. {category} business in {country} (website: {domain}):\nProvide 12 REAL backlink platforms specific to {category} niche in {country}.\nFormat:\nPLATFORM: name\nTYPE: type\nWHY: one sentence reason\n(repeat 12 times, nothing else)""", max_tokens=900)

    platforms,ptypes,whys=[],[],[]
    for line in backlink_result.strip().split('\n'):
        l=line.strip()
        if l.upper().startswith('PLATFORM:'): platforms.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('TYPE:'): ptypes.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('WHY:'): whys.append(l.split(':',1)[-1].strip())

    rows_opp="".join([f'<tr><td><strong>{platforms[i]}</strong></td><td><span class="badge badge-blue">{ptypes[i]}</span></td><td style="font-size:13px">{whys[i]}</td></tr>' for i in range(min(len(platforms),len(ptypes),len(whys)))])
    if not rows_opp: rows_opp="<tr><td colspan='3' style='text-align:center;padding:20px;color:#e74c3c'>Could not generate suggestions.</td></tr>"

    competitor_result = ai_call(f"""SEO expert. Category: "{category}", Country: {country}, Domain: {domain}.\nIdentify 3 REAL competitor websites. Format:\nNAME: ...\nURL: ...\nSTRENGTH: ...\n(repeat 3 times)""", max_tokens=600)

    comp_names,comp_urls,comp_strengths=[],[],[]
    for line in competitor_result.strip().split('\n'):
        l=line.strip()
        if l.upper().startswith('NAME:'): comp_names.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('URL:'): comp_urls.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('STRENGTH:'): comp_strengths.append(l.split(':',1)[-1].strip())

    competitor_cards=""
    for i in range(min(len(comp_names),len(comp_urls),len(comp_strengths))):
        competitor_cards+=f"""<div class="result-card"><div class="result-card-head red">🏆 {comp_names[i]}</div>
        <div class="result-card-body"><strong>🌐 <a href="https://{comp_urls[i]}" target="_blank">{comp_urls[i]}</a></strong><br><br>{comp_strengths[i]}</div></div>"""

    strategy = ai_call(f"""Off-Page SEO expert. {category} business ({domain}) in {country}:\n{len(external_links)} outbound links, {len(social_links)} social profiles ({', '.join(social_links) or 'none'}).\nWrite 5-6 sentence off-page strategy summary with 90-day action plan.""", max_tokens=500)

    return make_response(f"""{head("Off-Page SEO Report")}
<div class="container">
    {logo_html()}
    <div class="step-badge" style="background:linear-gradient(135deg,#e74c3c,#c0392b)">🔴 Off-Page SEO — Full Report</div>
    <h2>Backlink & Off-Page Analysis</h2>
    <div class="info-bar"><span>🌐 <a href="{target_url}" target="_blank" style="color:#667eea">{target_url}</a></span><span>📂 {category}</span><span>🌍 {country}</span></div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num">{len(external_links)}</div><div class="stat-label">Outbound Links</div></div>
        <div class="stat-box"><div class="stat-num">{len(ext_domains)}</div><div class="stat-label">Referring Domains</div></div>
        <div class="stat-box"><div class="stat-num">{len(social_links)}</div><div class="stat-label">Social Profiles</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL Active</div></div>
    </div>

    <div class="result-card"><div class="result-card-head red">📋 Strategy Summary</div>
    <div class="result-card-body">{strategy.replace('<','&lt;').replace('>','&gt;')}</div></div>

    <div class="result-card"><div class="result-card-head">📱 Social Media Profiles</div><div class="result-card-body">{rows_social}</div></div>
    <div class="result-card"><div class="result-card-head orange">🌐 External Links Found</div><div class="result-card-body">{rows_other}</div></div>

    <h2 style="margin-top:10px">🎯 Backlink Opportunities</h2>
    <table><thead><tr><th>Platform</th><th>Type</th><th>Why It's Relevant</th></tr></thead>
    <tbody>{rows_opp}</tbody></table>

    <h2 style="margin-top:30px">🏆 Top Competitors</h2>
    {competitor_cards or "<p style='color:#e74c3c;padding:15px'>Could not identify competitors.</p>"}

    <div class="note-box">⚠️ Outbound link data is from real website crawl. Backlink opportunities and competitors are AI-curated based on your niche.</div>

    <div class="buttons">
        <a href="/" class="btn btn-p">🔄 New Report</a>
        <a href="javascript:history.back()" class="btn btn-gr">← Back</a>
    </div>
</div></body></html>""")

# ─── DOWNLOAD ───
@app.route("/download-file")
def download_file():
    content=unquote(request.args.get("content",""))
    filename=request.args.get("filename","article.txt")
    return Response(content,mimetype="text/plain",headers={"Content-Disposition":f"attachment; filename={filename}"})

if __name__ == "__main__":
    app.run(debug=True)

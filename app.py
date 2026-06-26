from flask import Flask, request, Response, make_response, session, redirect, jsonify
from urllib.parse import quote, unquote, urljoin, urlparse
import requests as req
import re, os, json, hashlib
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "mrwebsol_secret_2026")
API_KEY = os.environ.get("GROQ_API_KEY", "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")
HEADERS_BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
LOGO_URL = "https://raw.githubusercontent.com/waqarali3202-commits/seo-agent/main/logo.png"
USERS_FILE = "/tmp/users.json"
USAGE_FILE = "/tmp/usage.json"

# ─── USER DB ───
def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE,'r') as f: return json.load(f)
    except: pass
    return {}

def save_users(u):
    try:
        with open(USERS_FILE,'w') as f: json.dump(u,f)
    except: pass

def load_usage():
    try:
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE,'r') as f: return json.load(f)
    except: pass
    return {}

def save_usage(u):
    try:
        with open(USAGE_FILE,'w') as f: json.dump(u,f)
    except: pass

def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()
def get_user(): return session.get('user')

def get_plan(email):
    users = load_users()
    user = users.get(email,{})
    trial_end = user.get('trial_end','')
    if trial_end:
        try:
            if datetime.now() < datetime.strptime(trial_end,'%Y-%m-%d'): return 'trial'
        except: pass
    return user.get('plan','free')

def get_usage(email):
    usage = load_usage()
    today = datetime.now().strftime('%Y-%m-%d')
    return usage.get(f"{email}_{today}",{'searches':0,'articles':0})

def inc_usage(email, t='search'):
    usage = load_usage()
    today = datetime.now().strftime('%Y-%m-%d')
    k = f"{email}_{today}"
    if k not in usage: usage[k]={'searches':0,'articles':0}
    if t=='search': usage[k]['searches']+=1
    else: usage[k]['articles']+=1
    save_usage(usage)

def can_use(email, t='search'):
    plan = get_plan(email)
    if plan in ['trial','basic','pro']: return True
    u = get_usage(email)
    if t=='search' and u['searches']>=15: return False
    if t=='article' and u['articles']>=3: return False
    return True

# ─── WEB HELPERS ───
def fetch_html(url):
    try:
        r = req.get(url, headers=HEADERS_BROWSER, timeout=15, allow_redirects=True)
        return r.text, r.status_code, r.url
    except: return None, 0, url

def get_all_links(html, base_url):
    links = re.findall(r'href=["\']([^"\']+)["\']', html)
    full = []
    for l in links:
        if l.startswith(('#','mailto:','tel:','javascript:')): continue
        full.append(urljoin(base_url, l))
    return list(set(full))

def get_internal_links(html, base_url):
    bd = urlparse(base_url).netloc
    return [l for l in get_all_links(html,base_url) if urlparse(l).netloc==bd or urlparse(l).netloc=='']

def get_external_links(html, base_url):
    bd = urlparse(base_url).netloc
    return [l for l in get_all_links(html,base_url) if urlparse(l).netloc!=bd and urlparse(l).netloc!='']

def get_images(html): return re.findall(r'<img[^>]+>', html, re.IGNORECASE)
def check_ssl(url): return url.startswith('https://')

def get_meta(html):
    title = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE|re.DOTALL)
    desc = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']*)["\']', html, re.IGNORECASE)
    robots = re.search(r'<meta[^>]+name=["\']robots["\'][^>]+content=["\']([^"\']*)["\']', html, re.IGNORECASE)
    canonical = re.search(r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\']([^"\']*)["\']', html, re.IGNORECASE)
    h1 = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE|re.DOTALL)
    h2 = re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.IGNORECASE|re.DOTALL)
    return {
        "title": title.group(1).strip() if title else None,
        "description": desc.group(1).strip() if desc else None,
        "robots": robots.group(1).strip() if robots else None,
        "canonical": canonical.group(1).strip() if canonical else None,
        "h1_count": len(h1), "h1_text": re.sub('<[^<]+?>','',h1[0]).strip() if h1 else None,
        "h2_count": len(h2)
    }

def ai_call(prompt, max_tokens=900):
    try:
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
        data = {"model": "llama-3.3-70b-versatile", "messages": [{"role":"user","content":prompt}], "max_tokens": max_tokens}
        r = req.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=data, timeout=60)
        if r.status_code==200: return r.json()["choices"][0]["message"]["content"]
        return f"Error: {r.text}"
    except Exception as e: return f"Error: {str(e)}"

# ─── DATA ───
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
def get_style():
    return """
<style>
*{margin:0;padding:0;box-sizing:border-box;}
body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);min-height:100vh;}
.trial-bar{background:linear-gradient(135deg,#f59e0b,#ef4444);color:white;text-align:center;padding:10px;font-size:13px;font-weight:600;}
.trial-bar a{color:white;font-weight:800;margin-left:10px;text-decoration:underline;}
.navbar{background:rgba(255,255,255,0.05);backdrop-filter:blur(10px);padding:10px 30px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid rgba(255,255,255,0.1);position:sticky;top:0;z-index:100;}
.navbar-logo img{height:45px;object-fit:contain;}
.nav-links{display:flex;gap:12px;align-items:center;}
.nav-links a{color:rgba(255,255,255,0.8);text-decoration:none;font-size:13px;font-weight:600;padding:6px 14px;border-radius:20px;transition:all 0.3s;}
.nav-links a:hover{background:rgba(255,255,255,0.1);color:white;}
.nav-btn{background:linear-gradient(135deg,#667eea,#764ba2)!important;color:white!important;}
.plan-badge{padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;}
.bf{background:#e8f5e9;color:#27ae60;}.bt{background:#fff3e0;color:#e67e22;}.bb{background:#e8f0ff;color:#667eea;}.bp{background:#f3e8ff;color:#764ba2;}
.container{max-width:1000px;margin:30px auto;background:#fff;border-radius:24px;padding:40px;box-shadow:0 30px 80px rgba(0,0,0,0.5);}
.logo-center{text-align:center;margin-bottom:20px;}
.logo-center img{height:60px;object-fit:contain;}
.logo-center p{color:#95a5a6;margin-top:6px;font-size:14px;}
.divider{height:3px;background:linear-gradient(135deg,#667eea,#764ba2);border-radius:3px;margin:20px 0;}
.step-badge{display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:5px 18px;border-radius:25px;font-size:13px;font-weight:700;margin-bottom:15px;}
.form-group{margin-bottom:20px;}
label{display:block;font-weight:700;color:#2c3e50;margin-bottom:8px;font-size:13px;text-transform:uppercase;letter-spacing:0.5px;}
input[type=text],input[type=email],input[type=password],select,textarea{width:100%;padding:13px 16px;border:2px solid #e8e8e8;border-radius:12px;font-size:15px;color:#2c3e50;transition:all 0.3s;background:#fafafa;}
input:focus,select:focus{border-color:#667eea;background:#fff;outline:none;box-shadow:0 0 0 4px rgba(102,126,234,0.1);}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:18px;}
.wtype-group{display:flex;gap:15px;margin-top:10px;}
.wtype-card{flex:1;padding:20px;border:3px solid #e0e0e0;border-radius:14px;text-align:center;cursor:pointer;transition:all 0.3s;background:#fafafa;}
.wtype-card:hover{transform:translateY(-3px);box-shadow:0 8px 25px rgba(0,0,0,0.1);}
.wtype-card input[type=radio]{display:none;}
.wtype-card .icon{font-size:35px;margin-bottom:8px;}
.wtype-card .name{font-weight:700;color:#2c3e50;font-size:15px;}
.wtype-card .desc{font-size:12px;color:#95a5a6;margin-top:4px;}
.wtype-card.selected{border-color:#667eea;background:linear-gradient(135deg,#f0f2ff,#f8f0ff);transform:translateY(-3px);}
.seo-group{display:flex;gap:15px;flex-wrap:wrap;}
.seo-card{flex:1;min-width:140px;padding:18px 15px;border:3px solid #e0e0e0;border-radius:14px;text-align:center;cursor:pointer;transition:all 0.3s;background:#fafafa;position:relative;}
.seo-card:hover{transform:translateY(-3px);box-shadow:0 8px 25px rgba(0,0,0,0.1);}
.seo-card input[type=radio]{display:none;}
.seo-card .icon{font-size:30px;margin-bottom:8px;}
.seo-card .name{font-weight:700;color:#2c3e50;font-size:14px;}
.seo-card .desc{font-size:12px;color:#95a5a6;margin-top:4px;}
.seo-card.selected{border-color:#667eea;background:linear-gradient(135deg,#f0f2ff,#f8f0ff);transform:translateY(-3px);}
.ptag{position:absolute;top:-10px;right:10px;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:800;}
.tf{background:#27ae60;color:white;}.tb{background:#667eea;color:white;}.tp{background:#764ba2;color:white;}
.sub-group{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:15px;margin-top:10px;}
.sub-card{padding:18px 12px;border:3px solid #e0e0e0;border-radius:14px;text-align:center;cursor:pointer;transition:all 0.3s;background:#fafafa;text-decoration:none;display:block;position:relative;}
.sub-card:hover{border-color:#667eea;transform:translateY(-3px);box-shadow:0 8px 25px rgba(102,126,234,0.15);background:linear-gradient(135deg,#f0f2ff,#f8f0ff);}
.sub-card .icon{font-size:28px;margin-bottom:7px;}
.sub-card .name{font-weight:700;color:#2c3e50;font-size:13px;}
.sub-card .desc{font-size:11px;color:#95a5a6;margin-top:4px;}
.sub-card.locked{opacity:0.6;cursor:not-allowed;}
.sub-card.locked:hover{transform:none;box-shadow:none;}
.btn-main{width:100%;padding:16px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:12px;font-size:17px;cursor:pointer;font-weight:700;transition:all 0.3s;margin-top:10px;}
.btn-main:hover{transform:translateY(-2px);box-shadow:0 10px 30px rgba(102,126,234,0.4);}
.btn-green{background:linear-gradient(135deg,#27ae60,#2ecc71)!important;}
.btn-orange{background:linear-gradient(135deg,#e67e22,#f39c12)!important;}
table{width:100%;border-collapse:collapse;margin-top:10px;}
th{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:12px 14px;text-align:left;font-size:12px;font-weight:700;text-transform:uppercase;}
th:first-child{border-radius:10px 0 0 0;}th:last-child{border-radius:0 10px 0 0;}
td{padding:11px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#2c3e50;word-break:break-all;}
tr:hover{background:#f8f9ff;}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:700;}
.be{background:#d5f5e3;color:#27ae60;}.bm{background:#fef9e7;color:#e67e22;}.bh{background:#fdecea;color:#e74c3c;}.bb2{background:#e8f0ff;color:#667eea;}
.step{background:#f8f9ff;border-radius:14px;padding:20px;margin-bottom:20px;border-left:5px solid #667eea;}
.step h3{color:#2c3e50;margin-bottom:12px;font-size:14px;font-weight:700;}
.chk-group{display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;}
.chk-item{display:flex;align-items:center;gap:8px;background:white;padding:8px 14px;border-radius:25px;border:2px solid #e0e0e0;cursor:pointer;font-size:13px;transition:all 0.2s;}
.chk-item:hover{border-color:#667eea;background:#f8f9ff;}
.chk-item input{width:15px;height:15px;cursor:pointer;}
.kw-badge{display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:5px 16px;border-radius:25px;font-size:13px;font-weight:600;margin-bottom:20px;}
.meta-card{background:linear-gradient(135deg,#eaf4ff,#f0f0ff);border-radius:14px;padding:18px 22px;margin-bottom:20px;font-size:14px;color:#2c3e50;line-height:2;border-left:5px solid #667eea;}
.art-box{background:#f8f9fa;border-radius:14px;padding:25px;line-height:1.95;max-height:500px;overflow-y:auto;border-left:5px solid #27ae60;font-size:14px;color:#2c3e50;margin-bottom:20px;white-space:pre-wrap;}
.seo-box{background:linear-gradient(135deg,#fff9e6,#fffbf0);border-radius:14px;padding:25px;border-left:5px solid #f39c12;font-size:13px;color:#2c3e50;line-height:2;margin-bottom:20px;}
.rcard{border-radius:14px;margin-bottom:22px;overflow:hidden;border:2px solid #e8e8e8;}
.rcard-head{background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:12px 20px;font-size:15px;font-weight:700;}
.rcard-head.green{background:linear-gradient(135deg,#27ae60,#2ecc71);}
.rcard-head.red{background:linear-gradient(135deg,#e74c3c,#c0392b);}
.rcard-head.orange{background:linear-gradient(135deg,#e67e22,#f39c12);}
.rcard-body{padding:20px;background:#fff;font-size:14px;line-height:1.9;}
.stat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px;margin-bottom:25px;}
.stat-box{background:#f8f9ff;border-radius:12px;padding:16px;text-align:center;border:2px solid #e8e8e8;}
.stat-num{font-size:26px;font-weight:800;color:#667eea;}
.stat-num.red{color:#e74c3c;}.stat-num.green{color:#27ae60;}.stat-num.orange{color:#e67e22;}
.stat-label{font-size:12px;color:#95a5a6;margin-top:5px;font-weight:600;}
.url-item{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid #f0f0f0;font-size:13px;flex-wrap:wrap;}
.url-item:last-child{border-bottom:none;}
.url-text{color:#2c3e50;word-break:break-all;flex:1;}
.url-text a{color:#667eea;text-decoration:none;}.url-text a:hover{text-decoration:underline;}
.s200{color:#27ae60;font-weight:700;font-size:12px;}.s301{color:#e67e22;font-weight:700;font-size:12px;}.s404{color:#e74c3c;font-weight:700;font-size:12px;}
.info-bar{color:#95a5a6;margin-bottom:20px;font-size:13px;display:flex;gap:10px;flex-wrap:wrap;}
.info-bar span{background:#f8f9fa;padding:5px 12px;border-radius:20px;border:1px solid #e0e0e0;}
h2{background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;-webkit-text-fill-color:transparent;font-size:22px;margin-bottom:8px;}
.note-box{background:#fffbf0;border:2px dashed #f39c12;border-radius:12px;padding:14px 18px;font-size:13px;color:#856404;margin-bottom:20px;line-height:1.7;}
.btns{display:flex;gap:12px;flex-wrap:wrap;margin-top:15px;}
.btn{flex:1;min-width:130px;padding:13px;border-radius:12px;text-align:center;font-size:14px;font-weight:700;cursor:pointer;border:none;text-decoration:none;transition:all 0.2s;display:inline-block;}
.btn-g{background:linear-gradient(135deg,#27ae60,#2ecc71);color:white;}
.btn-p{background:linear-gradient(135deg,#667eea,#764ba2);color:white;}
.btn-gr{background:#f0f0f0;color:#2c3e50;}
.btn-r{background:linear-gradient(135deg,#e74c3c,#c0392b);color:white;}
.btn:hover{transform:translateY(-2px);opacity:0.95;}
.back-link{display:inline-block;margin-top:18px;padding:9px 20px;background:#f0f0f0;border-radius:10px;text-decoration:none;color:#2c3e50;font-weight:600;font-size:13px;}
.ci{display:none;margin-top:10px;border-color:#667eea!important;background:#f8f9ff!important;}
.issue-c{background:#fff5f5;border-left:5px solid #e74c3c;border-radius:10px;padding:15px;margin-bottom:12px;}
.issue-i{background:#fff9f0;border-left:5px solid #e67e22;border-radius:10px;padding:15px;margin-bottom:12px;}
.issue-m{background:#f0fff4;border-left:5px solid #27ae60;border-radius:10px;padding:15px;margin-bottom:12px;}
.issue-title{font-weight:700;font-size:14px;margin-bottom:6px;}
.issue-desc{font-size:13px;color:#555;line-height:1.6;}
.upg-box{background:linear-gradient(135deg,#667eea,#764ba2);border-radius:14px;padding:20px 25px;color:white;margin-bottom:20px;text-align:center;}
.upg-box h3{font-size:18px;margin-bottom:8px;}
.upg-box p{font-size:13px;opacity:0.9;margin-bottom:15px;}
.upg-btn{background:white;color:#667eea;border:none;padding:10px 25px;border-radius:25px;font-weight:700;cursor:pointer;font-size:14px;text-decoration:none;display:inline-block;}
.auth-card{max-width:450px;margin:40px auto;background:white;border-radius:20px;padding:40px;box-shadow:0 20px 60px rgba(0,0,0,0.4);}
.auth-card h2{text-align:center;margin-bottom:20px;font-size:24px;}
.price-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;margin:20px 0;}
.price-card{border:2px solid #e8e8e8;border-radius:16px;padding:25px;text-align:center;}
.price-card.featured{border-color:#667eea;background:linear-gradient(135deg,#f0f2ff,#f8f0ff);}
.price-card h3{font-size:18px;font-weight:800;margin-bottom:5px;}
.price{font-size:36px;font-weight:800;color:#667eea;margin:10px 0;}
.price-card ul{text-align:left;list-style:none;margin:15px 0;}
.price-card ul li{padding:5px 0;font-size:13px;color:#555;}
.price-card ul li::before{content:'✅ ';}
.score-circle{width:100px;height:100px;border-radius:50%;display:flex;align-items:center;justify-content:center;margin:0 auto 10px;flex-direction:column;}
.dl-btn{display:block;width:100%;padding:14px;background:linear-gradient(135deg,#27ae60,#2ecc71);color:white;border:none;border-radius:12px;font-size:15px;cursor:pointer;font-weight:700;text-align:center;text-decoration:none;margin-bottom:10px;}
.dl-btn:hover{transform:translateY(-2px);opacity:0.95;}
@media(max-width:600px){.container{padding:20px 15px;margin:10px;}.grid-2{grid-template-columns:1fr;}.seo-group,.wtype-group{flex-direction:column;}.stat-grid{grid-template-columns:repeat(2,1fr);}}
</style>
<script>
function selSeo(el){document.querySelectorAll('.seo-card').forEach(c=>c.classList.remove('selected'));el.classList.add('selected');el.querySelector('input[type=radio]').checked=true;}
function selW(el){document.querySelectorAll('.wtype-card').forEach(c=>c.classList.remove('selected'));el.classList.add('selected');el.querySelector('input[type=radio]').checked=true;}
function chkCustom(s,id){var i=document.getElementById(id);if(s.value.includes('✏️')){i.style.display='block';i.focus();}else{i.style.display='none';}}
function submitSuggest(){
var cV=document.getElementById('cs').value.includes('✏️')?document.getElementById('ci').value:document.getElementById('cs').value;
var tV=document.getElementById('ts').value.includes('✏️')?document.getElementById('ti').value:document.getElementById('ts').value;
var dV=document.getElementById('ds').value.includes('✏️')?document.getElementById('di').value:document.getElementById('ds').value;
if(!cV||!tV||!dV){alert('Please fill all fields!');return;}
document.getElementById('fc').value=cV;document.getElementById('ft').value=tV;document.getElementById('fd').value=dV;
document.getElementById('mf').submit();}
</script>
"""

def page_head(title="Mr Websol SEO Agent"):
    user = get_user()
    plan = get_plan(user['email']) if user else 'guest'
    usage = get_usage(user['email']) if user else {'searches':0,'articles':0}
    pc = {'free':'bf','trial':'bt','basic':'bb','pro':'bp'}.get(plan,'bf')
    nav_r = f"""
    <span class="plan-badge {pc}">{plan.upper()}</span>
    <span style="color:rgba(255,255,255,0.7);font-size:12px">🔍{usage['searches']}/{"∞" if plan!="free" else "15"} ✍️{usage['articles']}/{"∞" if plan!="free" else "3"}</span>
    <a href="/pricing" style="color:#f59e0b;font-weight:700;font-size:13px;text-decoration:none">⚡Upgrade</a>
    <a href="/logout" class="nav-links" style="color:rgba(255,255,255,0.7);font-size:13px;text-decoration:none">Logout</a>
    """ if user else """<a href="/login">Login</a><a href="/register" class="nav-btn">Get Started Free</a>"""

    return f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="google-site-verification" content="lBsWiBHSa9xwXDUaF6duDp3BcH3o2sGfZNkQkHBVDp8">
<meta name="description" content="Free AI Powered Professional SEO Platform. Website Audit, On-Page, Technical, Off-Page SEO tools.">
<meta property="og:title" content="Mr Websol SEO Agent — Free AI SEO Tool">
<meta property="og:url" content="https://seo-agent.mrwebsol.com">
<link rel="icon" type="image/png" href="{LOGO_URL}">
<title>{title} — Mr Websol SEO Agent</title>
{get_style()}</head><body>
<div class="trial-bar">🎉 New users get 7 days FREE Trial — All features unlocked! <a href="/register">Start Free Trial →</a></div>
<nav class="navbar">
  <a href="/" class="navbar-logo"><img src="{LOGO_URL}" alt="Mr Websol SEO Agent"></a>
  <div class="nav-links">{nav_r}</div>
</nav>"""

def logo_section():
    return f"""<div class="logo-center"><img src="{LOGO_URL}" alt="Mr Websol SEO Agent" style="height:55px"><p>AI Powered Professional SEO Platform</p></div><div class="divider"></div>"""

# ═══ AUTH ═══
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        name=request.form.get("name","").strip()
        email=request.form.get("email","").strip().lower()
        pwd=request.form.get("password","").strip()
        if not name or not email or not pwd:
            return reg_page("All fields required!")
        users=load_users()
        if email in users: return reg_page("Email already registered! Please login.")
        trial_end=(datetime.now()+timedelta(days=7)).strftime('%Y-%m-%d')
        users[email]={"name":name,"email":email,"password":hash_pw(pwd),"plan":"free","trial_end":trial_end,"created":datetime.now().strftime('%Y-%m-%d')}
        save_users(users)
        session['user']={"name":name,"email":email}
        return redirect("/")
    return reg_page()

def reg_page(err=""):
    return f"""{page_head("Register")}<div class="auth-card">
    <div style="text-align:center;margin-bottom:20px"><img src="{LOGO_URL}" style="height:50px"></div>
    <h2>Create Free Account</h2>
    <p style="text-align:center;color:#95a5a6;font-size:13px;margin-bottom:20px">🎉 7 Days FREE Trial — No Credit Card Required!</p>
    {"<div style='background:#fdecea;color:#e74c3c;padding:12px;border-radius:10px;margin-bottom:15px;font-size:13px'>"+err+"</div>" if err else ""}
    <form method="POST">
        <div class="form-group"><label>Full Name</label><input type="text" name="name" placeholder="Your name" required></div>
        <div class="form-group"><label>Email</label><input type="email" name="email" placeholder="your@email.com" required></div>
        <div class="form-group"><label>Password</label><input type="password" name="password" placeholder="Create password" required></div>
        <button class="btn-main" type="submit">🚀 Start Free Trial</button>
    </form>
    <p style="text-align:center;margin-top:20px;font-size:13px;color:#95a5a6">Already have account? <a href="/login" style="color:#667eea;font-weight:700">Login</a></p>
    </div></body></html>"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        pwd=request.form.get("password","").strip()
        users=load_users()
        u=users.get(email)
        if not u or u['password']!=hash_pw(pwd): return login_page("Invalid email or password!")
        session['user']={"name":u['name'],"email":email}
        return redirect("/")
    return login_page()

def login_page(err=""):
    return f"""{page_head("Login")}<div class="auth-card">
    <div style="text-align:center;margin-bottom:20px"><img src="{LOGO_URL}" style="height:50px"></div>
    <h2>Welcome Back!</h2>
    {"<div style='background:#fdecea;color:#e74c3c;padding:12px;border-radius:10px;margin-bottom:15px;font-size:13px'>"+err+"</div>" if err else ""}
    <form method="POST">
        <div class="form-group"><label>Email</label><input type="email" name="email" placeholder="your@email.com" required></div>
        <div class="form-group"><label>Password</label><input type="password" name="password" placeholder="Your password" required></div>
        <button class="btn-main" type="submit">Login →</button>
    </form>
    <p style="text-align:center;margin-top:20px;font-size:13px;color:#95a5a6">New user? <a href="/register" style="color:#667eea;font-weight:700">Create Free Account</a></p>
    </div></body></html>"""

@app.route("/logout")
def logout():
    session.clear(); return redirect("/")

@app.route("/pricing")
def pricing():
    return f"""{page_head("Pricing")}<div class="container">{logo_section()}
    <h2 style="text-align:center">Choose Your Plan</h2>
    <p style="text-align:center;color:#95a5a6;margin-bottom:30px;font-size:14px">Start with 7 days free trial!</p>
    <div class="price-grid">
        <div class="price-card"><h3>🆓 Free</h3><div class="price">$0</div><p style="color:#95a5a6;font-size:13px">Forever free</p><ul><li>15 searches/day</li><li>3 articles/day</li><li>Article Writer only</li><li>Basic website audit</li></ul><a href="/register" class="btn-main" style="display:block;text-align:center;text-decoration:none;margin-top:15px">Get Started</a></div>
        <div class="price-card featured"><div style="background:#667eea;color:white;padding:4px 12px;border-radius:20px;font-size:11px;font-weight:700;display:inline-block;margin-bottom:10px">MOST POPULAR</div><h3>💎 Basic</h3><div class="price">$9<span style="font-size:16px;color:#95a5a6">/mo</span></div><ul><li>Unlimited searches</li><li>Unlimited articles</li><li>All On-Page tools</li><li>Full website audit</li><li>Priority support</li></ul><a href="/register" class="btn-main" style="display:block;text-align:center;text-decoration:none;margin-top:15px">Start Free Trial</a></div>
        <div class="price-card"><h3>🔥 Pro</h3><div class="price">$10<span style="font-size:16px;color:#95a5a6">/mo</span></div><ul><li>Everything in Basic</li><li>Technical SEO</li><li>Off-Page SEO</li><li>Competitor analysis</li><li>Backlink opportunities</li></ul><a href="/register" class="btn-main btn-orange" style="display:block;text-align:center;text-decoration:none;margin-top:15px">Start Free Trial</a></div>
    </div>
    <a href="/" class="back-link">← Go Back</a></div></body></html>"""

# ═══ HOME ═══
@app.route("/")
def home():
    user=get_user()
    if not user: return redirect("/register")
    plan=get_plan(user['email'])
    usage=get_usage(user['email'])
    cat_opts="".join([f'<option value="{c}">{c}</option>' for c in CATEGORIES])
    co="".join([f'<option value="{c}">{c}</option>' for c in COUNTRIES])
    lo="".join([f'<option value="{l}">{l}</option>' for l in LANGUAGES])
    pc={'free':'bf','trial':'bt','basic':'bb','pro':'bp'}.get(plan,'bf')
    trial_info=""
    if plan=='trial':
        users=load_users()
        te=users.get(user['email'],{}).get('trial_end','')
        trial_info=f"<span style='color:#e67e22;font-size:12px'>Trial ends {te}</span>"

    usage_html=f"""<div style="background:#f8f9ff;border-radius:12px;padding:15px 20px;margin-bottom:20px;border:2px solid #e8e8e8;">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
        <div><strong style="color:#2c3e50">Welcome, {user['name']}! 👋</strong> <span class="plan-badge {pc}">{plan.upper()}</span> {trial_info}</div>
        <div style="display:flex;gap:20px;align-items:center;">
            <div style="text-align:center"><div style="font-size:11px;color:#95a5a6">SEARCHES TODAY</div><div style="font-weight:700;color:#667eea">{usage['searches']}/{"∞" if plan!="free" else "15"}</div></div>
            <div style="text-align:center"><div style="font-size:11px;color:#95a5a6">ARTICLES TODAY</div><div style="font-weight:700;color:#764ba2">{usage['articles']}/{"∞" if plan!="free" else "3"}</div></div>
            {"<a href='/pricing' style='background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:8px 16px;border-radius:20px;font-size:12px;font-weight:700;text-decoration:none'>⚡ Upgrade</a>" if plan=='free' else ""}
        </div>
    </div></div>"""

    return f"""{page_head()}<div class="container">{logo_section()}{usage_html}
    <form action="/audit" method="POST">
        <div class="step-badge">⚙️ Step 1 — Website Setup</div>
        <div class="grid-2">
            <div class="form-group"><label>📂 Business Category</label><select name="category" required><option value="">-- Select Category --</option>{cat_opts}</select></div>
            <div class="form-group"><label>🌐 Website URL</label><input type="text" name="website" placeholder="https://yourwebsite.com" required></div>
            <div class="form-group"><label>🌍 Target Country</label><select name="country">{co}</select></div>
            <div class="form-group"><label>🗣️ Language</label><select name="language">{lo}</select></div>
        </div>
        <div class="form-group"><label>🌐 Website Status</label>
        <div class="wtype-group">
            <div class="wtype-card selected" onclick="selW(this)"><input type="radio" name="website_age" value="new" checked><div class="icon">🆕</div><div class="name">New Website</div><div class="desc">Recently launched</div></div>
            <div class="wtype-card" onclick="selW(this)"><input type="radio" name="website_age" value="old"><div class="icon">🏛️</div><div class="name">Existing Website</div><div class="desc">Already live</div></div>
        </div></div>
        <button class="btn-main" type="submit">🔍 Audit Your Website →</button>
    </form></div></body></html>"""

# ═══ AUDIT ═══
@app.route("/audit", methods=["POST"])
def audit():
    user=get_user()
    if not user: return redirect("/login")
    if not can_use(user['email'],'search'): return redirect("/pricing")
    inc_usage(user['email'],'search')

    category=request.form.get("category"); website=request.form.get("website","").strip()
    country=request.form.get("country"); language=request.form.get("language")
    website_age=request.form.get("website_age","old")
    if not website.startswith("http"): website="https://"+website

    html_content,status_code,final_url=fetch_html(website)
    target_url=final_url if final_url else website

    if not html_content:
        return make_response(f"""{page_head()}<div class="container">{logo_section()}
        <h2>❌ Could Not Fetch Website</h2>
        <div class="rcard"><div class="rcard-head red">⚠️ Error</div>
        <div class="rcard-body">Could not connect to <strong><a href="{website}" target="_blank">{website}</a></strong>. Please check URL.</div></div>
        <a href="/" class="back-link">← Try Again</a></div></body></html>""")

    meta=get_meta(html_content)
    page_size_kb=len(html_content.encode('utf-8'))/1024
    images=get_images(html_content)
    internal_links=get_internal_links(html_content,target_url)
    external_links=get_external_links(html_content,target_url)
    has_ssl=check_ssl(target_url)
    has_viewport=re.search(r'<meta[^>]+name=["\']viewport["\']',html_content,re.IGNORECASE) is not None
    has_jsonld='"@context"' in html_content
    schema_types=list(set(re.findall(r'"@type"\s*:\s*"([^"]+)"',html_content)))
    og_title=re.search(r'<meta[^>]+property=["\']og:title["\']',html_content,re.IGNORECASE) is not None
    og_image=re.search(r'<meta[^>]+property=["\']og:image["\']',html_content,re.IGNORECASE) is not None
    twitter=re.search(r'<meta[^>]+name=["\']twitter:card["\']',html_content,re.IGNORECASE) is not None

    missing_alt=[]
    for img in images:
        if 'alt=""' in img or "alt=''" in img or 'alt=' not in img.lower():
            sm=re.search(r'src=["\']([^"\']+)["\']',img)
            missing_alt.append(sm.group(1) if sm else "unknown")

    anchors=re.findall(r'<a[^>]+href=[^>]+>([^<]*)</a>',html_content,re.IGNORECASE)
    generic_anchors=list(set([a.strip() for a in anchors if a.strip().lower() in ["click here","here","read more","learn more","more","link"]]))

    robots_url=target_url.rstrip("/")+"/robots.txt"
    rh,rs,_=fetch_html(robots_url)
    robots_found=rs==200 and rh
    robots_blocks=robots_found and "Disallow: /" in (rh or "")

    sitemap_url=target_url.rstrip("/")+"/sitemap.xml"
    sh,ss,_=fetch_html(sitemap_url)
    sitemap_found=ss==200 and sh
    sitemap_count=len(re.findall(r'<url>',sh)) if sh else 0

    is_noindex=meta.get("robots") and "noindex" in meta.get("robots","").lower()

    # ── Full AI Audit ──
    audit_prompt=f"""You are a Senior SEO Expert. Analyze this website comprehensively:
URL: {target_url}
Category: {category}, Country: {country}, Language: {language}
Website Type: {"New Website" if website_age=="new" else "Existing Website"}

Real Data:
- SSL/HTTPS: {"Yes" if has_ssl else "No"}
- Page Size: {page_size_kb:.0f}KB
- Meta Title: {meta.get('title') or 'MISSING'}
- Meta Description: {"Present: "+meta.get('description','')[:100] if meta.get('description') else 'MISSING'}
- H1: {meta.get('h1_count',0)} tags, H2: {meta.get('h2_count',0)} tags
- H1 Text: {meta.get('h1_text','N/A')}
- Internal Links: {len(internal_links)}, External Links: {len(external_links)}
- Images Total: {len(images)}, Missing Alt Tags: {len(missing_alt)}
- Robots.txt: {"Found" if robots_found else "Missing"} {"(BLOCKING SITE!)" if robots_blocks else ""}
- XML Sitemap: {"Found - "+str(sitemap_count)+" URLs" if sitemap_found else "Missing"}
- Schema Markup: {"Found: "+", ".join(schema_types[:5]) if has_jsonld else "Not found"}
- Mobile Viewport: {"Present" if has_viewport else "Missing"}
- Open Graph: Title {"✅" if og_title else "❌"} Image {"✅" if og_image else "❌"}
- Twitter Card: {"✅" if twitter else "❌"}
- Noindex Homepage: {"YES - CRITICAL!" if is_noindex else "No"}
- Generic Anchors: {generic_anchors if generic_anchors else "None"}
- Canonical: {meta.get('canonical','Not set')}

Provide a FULL SEO Audit with these 3 sections:

## 📊 ON-PAGE SEO AUDIT
Analyze: Title tag, Meta description, H1/H2 structure, Content quality, Internal linking, Keyword optimization, URL structure recommendations

## 🔧 TECHNICAL SEO AUDIT  
Analyze: SSL, Page speed assessment, Mobile optimization, Robots.txt, Sitemap, Schema markup, Core Web Vitals recommendations, Crawlability

## 🔗 OFF-PAGE SEO AUDIT
Analyze: Current external link profile ({len(external_links)} links), Domain authority assessment, Social signals, Link building opportunities for {category} in {country}

For each section give: Current Status, Issues Found, Priority Fixes (numbered)
Be specific, professional, and base everything on the real data provided."""

    full_audit=ai_call(audit_prompt, max_tokens=2000)

    # Score
    score=100
    issues={'critical':[],'important':[],'minor':[]}
    if not has_ssl: score-=15; issues['critical'].append(("No SSL/HTTPS","Install SSL certificate immediately. Google penalizes HTTP sites."))
    if is_noindex: score-=25; issues['critical'].append(("Homepage Noindex!","Your homepage cannot be indexed by Google. Remove noindex tag NOW."))
    if robots_blocks: score-=20; issues['critical'].append(("Robots.txt Blocking Site","robots.txt is blocking all crawlers. Fix immediately!"))
    if not meta.get("title"): score-=10; issues['critical'].append(("Missing Title Tag","No title tag found. Critical for rankings."))
    if not meta.get("description"): score-=8; issues['important'].append(("Missing Meta Description","Add meta description to improve CTR."))
    if meta.get("h1_count",0)==0: score-=8; issues['important'].append(("No H1 Tag","Every page needs exactly one H1 tag."))
    if meta.get("h1_count",0)>1: score-=5; issues['important'].append((f"Multiple H1 Tags ({meta.get('h1_count')})","Use only ONE H1 per page."))
    if not sitemap_found: score-=7; issues['important'].append(("No XML Sitemap","Create and submit sitemap to Google Search Console."))
    if not robots_found: score-=5; issues['important'].append(("No Robots.txt","Create robots.txt to guide search engine crawlers."))
    if missing_alt: score-=min(10,len(missing_alt)*2); issues['important'].append((f"{len(missing_alt)} Images Missing Alt Tags","Add descriptive alt text to all images."))
    if not has_jsonld: score-=6; issues['minor'].append(("No Schema Markup","Add structured data for rich results in Google."))
    if not has_viewport: score-=8; issues['important'].append(("No Mobile Viewport","Site may not display correctly on mobile."))
    if not og_title or not og_image: score-=4; issues['minor'].append(("Incomplete OG Tags","Add OG tags for better social media sharing."))
    if generic_anchors: score-=3; issues['minor'].append(("Generic Anchor Texts","Replace 'click here' with keyword-rich anchors."))
    if page_size_kb>500: score-=5; issues['minor'].append((f"Large Page Size ({page_size_kb:.0f}KB)","Optimize images and minify code."))
    if meta.get("title") and len(meta.get("title",""))>60: score-=3; issues['minor'].append(("Title Too Long","Keep title under 60 characters."))
    score=max(0,score)
    score_color="#27ae60" if score>=80 else "#f39e0b" if score>=60 else "#e74c3c"

    def iss_html(items,cls,icon):
        html=""
        for t,d in items: html+=f'<div class="issue-{cls}"><div class="issue-title">{icon} {t}</div><div class="issue-desc">{d}</div></div>'
        return html or f'<div style="color:#27ae60;padding:10px">✅ No {cls} issues found!</div>'

    total_issues=len(issues['critical'])+len(issues['important'])+len(issues['minor'])
    audit_display=full_audit.replace('<','&lt;').replace('>','&gt;')

    # Download content
    download_content=f"""MR WEBSOL SEO AGENT - FULL WEBSITE AUDIT
Website: {target_url}
Category: {category} | Country: {country} | Language: {language}
Website Status: {"New Website" if website_age=="new" else "Existing Website"}
Audit Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}
SEO Score: {score}/100

{'='*60}
REAL DATA SUMMARY
{'='*60}
SSL/HTTPS: {"Yes" if has_ssl else "No"}
Page Size: {page_size_kb:.0f}KB
Meta Title: {meta.get('title') or 'MISSING'}
Meta Description: {meta.get('description') or 'MISSING'}
H1 Tags: {meta.get('h1_count',0)}
Internal Links: {len(internal_links)}
External Links: {len(external_links)}
Images: {len(images)} total, {len(missing_alt)} missing alt tags
Robots.txt: {"Found" if robots_found else "Missing"}
XML Sitemap: {"Found - "+str(sitemap_count)+" URLs" if sitemap_found else "Missing"}
Schema Markup: {"Found: "+", ".join(schema_types) if has_jsonld else "Not found"}
Mobile Viewport: {"Yes" if has_viewport else "No"}

{'='*60}
FULL AI AUDIT REPORT
{'='*60}

{full_audit}

{'='*60}
ISSUES SUMMARY
{'='*60}
CRITICAL: {len(issues['critical'])} issues
IMPORTANT: {len(issues['important'])} issues
MINOR: {len(issues['minor'])} issues
"""
    enc_dl=quote(download_content)
    fn=f"{urlparse(target_url).netloc}_audit_{datetime.now().strftime('%Y%m%d')}.txt"

    return make_response(f"""{page_head("Website Audit")}<div class="container">{logo_section()}
    <div class="step-badge">📊 Step 2 — Full Website Audit</div>
    <h2>Complete SEO Audit Report</h2>
    <div class="info-bar">
        <span>🌐 <a href="{target_url}" target="_blank" style="color:#667eea">{target_url}</a></span>
        <span>📂 {category}</span><span>🌍 {country}</span>
        <span>{"🆕 New Website" if website_age=="new" else "🏛️ Existing Website"}</span>
    </div>

    <div style="text-align:center;margin-bottom:25px">
        <div class="score-circle" style="background:{score_color}">
            <span style="font-size:32px;font-weight:800;color:white">{score}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.8)">/100</span>
        </div>
        <strong style="font-size:16px;color:#2c3e50">Overall SEO Score</strong>
        <p style="color:#95a5a6;font-size:13px;margin-top:5px">{total_issues} issues found</p>
    </div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL/HTTPS</div></div>
        <div class="stat-box"><div class="stat-num">{page_size_kb:.0f}KB</div><div class="stat-label">Page Size</div></div>
        <div class="stat-box"><div class="stat-num">{len(images)}</div><div class="stat-label">Images</div></div>
        <div class="stat-box"><div class="stat-num red">{len(missing_alt)}</div><div class="stat-label">Missing Alt</div></div>
        <div class="stat-box"><div class="stat-num">{len(internal_links)}</div><div class="stat-label">Internal Links</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_viewport else "red"}">{"✅" if has_viewport else "❌"}</div><div class="stat-label">Mobile</div></div>
    </div>

    <a href="/download-file?content={enc_dl}&filename={fn}" class="dl-btn">⬇️ Download Full Audit Report</a>

    <div class="rcard">
        <div class="rcard-head">📊 AI Full SEO Audit (On-Page + Technical + Off-Page)</div>
        <div class="rcard-body" style="white-space:pre-wrap;line-height:1.9;max-height:600px;overflow-y:auto">{audit_display}</div>
    </div>

    <h3 style="color:#e74c3c;margin-bottom:15px">🔴 Critical Issues ({len(issues['critical'])})</h3>
    {iss_html(issues['critical'],'c','🔴')}
    <h3 style="color:#e67e22;margin:20px 0 15px">🟡 Important Issues ({len(issues['important'])})</h3>
    {iss_html(issues['important'],'i','🟡')}
    <h3 style="color:#27ae60;margin:20px 0 15px">🟢 Minor Issues ({len(issues['minor'])})</h3>
    {iss_html(issues['minor'],'m','🟢')}

    <form action="/fix-guide" method="POST" style="margin-top:25px">
        <input type="hidden" name="category" value="{category}">
        <input type="hidden" name="website" value="{target_url}">
        <input type="hidden" name="country" value="{country}">
        <input type="hidden" name="language" value="{language}">
        <input type="hidden" name="score" value="{score}">
        <input type="hidden" name="issues" value="{quote(json.dumps(issues))}">
        <button class="btn-main" type="submit">🔧 How to Fix These Issues →</button>
    </form>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

# ═══ FIX GUIDE ═══
@app.route("/fix-guide", methods=["POST"])
def fix_guide():
    user=get_user()
    if not user: return redirect("/login")
    category=request.form.get("category"); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language")
    score=request.form.get("score")
    issues_raw=unquote(request.form.get("issues","{}"))
    try: issues=json.loads(issues_raw)
    except: issues={'critical':[],'important':[],'minor':[]}
    all_issues=issues.get('critical',[])+issues.get('important',[])+issues.get('minor',[])
    issues_text="\n".join([f"- {t}: {d}" for t,d in all_issues])

    guide=ai_call(f"""Senior SEO Expert. Website: {website}, Category: {category}, Country: {country}, Score: {score}/100.
Issues found:
{issues_text}
For EACH issue provide:
1. Step-by-step fix (2-4 concrete steps)
2. Priority: NOW / THIS WEEK / THIS MONTH
3. Expected improvement after fixing
Be specific and actionable. Format clearly with issue name as header.""", max_tokens=1500)

    dl_content=f"FIX GUIDE - {website}\nDate: {datetime.now().strftime('%Y-%m-%d')}\nScore: {score}/100\n\n{'='*50}\n\n{guide}"
    enc_dl=quote(dl_content)

    return make_response(f"""{page_head("Fix Guide")}<div class="container">{logo_section()}
    <div class="step-badge">🔧 Step 3 — How to Fix Issues</div>
    <h2>Complete Fix Guide</h2>
    <div class="info-bar"><span>🌐 <a href="{website}" target="_blank" style="color:#667eea">{website}</a></span><span>📊 Score: {score}/100</span></div>
    <a href="/download-file?content={enc_dl}&filename=fix_guide.txt" class="dl-btn">⬇️ Download Fix Guide</a>
    <div class="rcard"><div class="rcard-head green">✅ AI Fix Guide</div>
    <div class="rcard-body" style="white-space:pre-wrap;line-height:1.9;max-height:600px;overflow-y:auto">{guide.replace('<','&lt;').replace('>','&gt;')}</div></div>
    <form action="/seo-tools" method="POST" style="margin-top:20px">
        <input type="hidden" name="category" value="{category}">
        <input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}">
        <input type="hidden" name="language" value="{language}">
        <button class="btn-main" type="submit">🚀 Continue to SEO Tools →</button>
    </form>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

# ═══ SEO TOOLS ═══
@app.route("/seo-tools", methods=["POST"])
def seo_tools():
    user=get_user()
    if not user: return redirect("/login")
    category=request.form.get("category"); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language")
    plan=get_plan(user['email'])
    return make_response(f"""{page_head("SEO Tools")}<div class="container">{logo_section()}
    <div class="step-badge">🎯 Step 4 — Choose SEO Tool</div>
    <h2>Select SEO Type</h2>
    <div class="info-bar"><span>🌐 <a href="{website}" target="_blank" style="color:#667eea">{website}</a></span><span>📂 {category}</span></div>
    <form action="/seo-route" method="POST">
        <input type="hidden" name="category" value="{category}">
        <input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}">
        <input type="hidden" name="language" value="{language}">
        <div class="seo-group">
            <div class="seo-card selected" onclick="selSeo(this)">
                <div class="ptag tf">FREE</div>
                <input type="radio" name="seo_type" value="On-Page" checked>
                <div class="icon">🟢</div><div class="name">On-Page SEO</div><div class="desc">Content & Keywords</div>
            </div>
            <div class="seo-card" onclick="selSeo(this)">
                <div class="ptag tp">PRO $10</div>
                <input type="radio" name="seo_type" value="Technical">
                <div class="icon">🔵</div><div class="name">Technical SEO</div><div class="desc">Score & URL Analysis</div>
            </div>
            <div class="seo-card" onclick="selSeo(this)">
                <div class="ptag tp">PRO $10</div>
                <input type="radio" name="seo_type" value="Off-Page">
                <div class="icon">🔴</div><div class="name">Off-Page SEO</div><div class="desc">Backlinks & Competitors</div>
            </div>
        </div>
        <button class="btn-main" type="submit" style="margin-top:20px">Next Step →</button>
    </form>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>""")

@app.route("/seo-route", methods=["POST"])
def seo_route():
    user=get_user()
    if not user: return redirect("/login")
    seo_type=request.form.get("seo_type"); category=request.form.get("category")
    website=request.form.get("website"); country=request.form.get("country"); language=request.form.get("language")
    plan=get_plan(user['email'])
    if seo_type in ["Technical","Off-Page"] and plan not in ["trial","pro"]: return redirect("/pricing")
    if seo_type=="On-Page": return onpage_subtypes(category,website,country,language,plan)
    elif seo_type=="Technical": return technical_report(category,website,country,language)
    else: return offpage_report(category,website,country,language)

# ═══ ON-PAGE ═══
def onpage_subtypes(category,website,country,language,plan):
    subtypes=[
        ("✍️","Article Writer","Blog & informational articles","article_writer","free"),
        ("📄","Page Content Writer","Homepage, About, landing pages","page_content","basic"),
        ("⚙️","Service Page Writer","Service description pages","service_page","basic"),
        ("📍","Service Areas Writer","Location-based service pages","service_areas","basic"),
        ("🧠","Semantic SEO Writer","Topic clusters & semantic content","semantic_seo","basic"),
    ]
    tmap={"free":"tf","basic":"tb","pro":"tp"}
    lmap={"free":"FREE","basic":"$9/mo","pro":"$10/mo"}
    cards=""
    for icon,name,desc,val,rp in subtypes:
        allowed=plan in ["trial","pro","basic"] or rp=="free"
        lc=" locked" if not allowed else ""
        li=" 🔒" if not allowed else ""
        cards+=f"""<form action="/onpage-writer" method="POST" style="display:contents">
            <input type="hidden" name="category" value="{category}"><input type="hidden" name="website" value="{website}">
            <input type="hidden" name="country" value="{country}"><input type="hidden" name="language" value="{language}">
            <input type="hidden" name="writer_type" value="{val}">
            <button type="submit" style="background:none;border:none;padding:0;cursor:pointer;display:block;width:100%" {"disabled" if not allowed else ""}>
                <div class="sub-card{lc}"><div class="ptag {tmap[rp]}">{lmap[rp]}</div><div class="icon">{icon}</div><div class="name">{name}{li}</div><div class="desc">{desc}</div></div>
            </button></form>"""
    upg=f"""<div class="upg-box" style="margin-top:20px"><h3>⚡ Unlock All On-Page Tools</h3><p>Get Page Content, Service Page, Service Areas & Semantic SEO Writers</p><a href="/pricing" class="upg-btn">Upgrade to Basic — $9/mo</a></div>""" if plan=='free' else ""
    return make_response(f"""{page_head("On-Page SEO")}<div class="container">{logo_section()}
    <div class="step-badge">🟢 On-Page SEO</div><h2>Select Content Type</h2>
    <div class="sub-group">{cards}</div>{upg}
    <a href="/" class="back-link">← Go Back</a></div></body></html>""")

@app.route("/onpage-writer", methods=["POST"])
def onpage_writer():
    user=get_user()
    if not user: return redirect("/login")
    if not can_use(user['email'],'search'): return redirect("/pricing")
    inc_usage(user['email'],'search')
    category=request.form.get("category"); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language"); writer_type=request.form.get("writer_type")
    wl={"article_writer":"✍️ Article Writer","page_content":"📄 Page Content Writer","service_page":"⚙️ Service Page Writer","service_areas":"📍 Service Areas Writer","semantic_seo":"🧠 Semantic SEO Writer"}
    label=wl.get(writer_type,"Content Writer")
    kmap={"article_writer":"blog article topics, informational keywords, long-tail question keywords","page_content":"homepage, about page, landing page keywords","service_page":"service-specific commercial keywords","service_areas":"local SEO, location-based service keywords","semantic_seo":"semantic clusters, LSI keywords, topic authority keywords"}
    result=ai_call(f"""SEO expert. Website: {website}, Business: {category}, Country: {country}\nFocus: {kmap.get(writer_type,"SEO keywords")}\nReturn ONLY 10 keywords:\nkeyword | 40,000/mo | EASY | Informational\n10 lines only.""")
    rows=""
    for line in result.strip().split('\n'):
        if '|' in line:
            p=[x.strip() for x in line.split('|')]
            if len(p)>=4:
                kd=p[2].upper()
                badge=f'<span class="badge {"be" if "EASY" in kd else "bm" if "MEDIUM" in kd else "bh"}">{p[2]}</span>'
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
    return make_response(f"""{page_head("Keywords")}<div class="container">{logo_section()}
    <h2>🔍 Keywords Found!</h2>
    <div class="info-bar"><span>🌐 <a href="{website}" target="_blank" style="color:#667eea">{website}</a></span><span>📂 {category}</span><span>🌍 {country}</span><span>{label}</span></div>
    <table><thead><tr><th>Keyword</th><th>Volume</th><th>Difficulty</th><th>Intent</th><th>Action</th></tr></thead>
    <tbody>{rows or "<tr><td colspan='5' style='text-align:center;padding:20px;color:#e74c3c'>Could not load keywords.</td></tr>"}{custom_row}</tbody></table>
    <a href="/" class="back-link">← Go Back</a></div></body></html>""")

@app.route("/article-settings", methods=["POST"])
def article_settings():
    user=get_user()
    if not user: return redirect("/login")
    keyword=request.form.get("keyword","").strip(); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language")
    category=request.form.get("category"); writer_type=request.form.get("writer_type")
    if not keyword: return "<h3 style='color:red;padding:30px'>Keyword missing.</h3>"
    return make_response(f"""{page_head("Article Settings")}<div class="container">{logo_section()}
    <div class="step-badge">✍️ Article Settings</div><h2>Configure Your Article</h2>
    <span class="kw-badge">🎯 {keyword}</span>
    <form action="/ai-suggest" method="POST">
        <input type="hidden" name="keyword" value="{keyword}"><input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}"><input type="hidden" name="language" value="{language}">
        <input type="hidden" name="category" value="{category}"><input type="hidden" name="writer_type" value="{writer_type}">
        <div class="step"><h3>📊 Article Length</h3><select name="length"><option value="500">Short — 500 words</option><option value="1000" selected>Medium — 1000 words</option><option value="2000">Long — 2000 words</option><option value="3000">Extra Long — 3000 words</option></select></div>
        <div class="step"><h3>🎯 Writing Intent</h3><select name="intent"><option value="Informational">📚 Informational</option><option value="Professional">💼 Professional</option><option value="Casual">😊 Casual</option><option value="Transactional">🛒 Transactional</option><option value="Commercial">💰 Commercial</option></select></div>
        <div class="step"><h3>🏪 Content Type</h3><select name="content_type"><option value="Blogging Site">📝 Blogging Site</option><option value="Ecommerce Site">🛍️ Ecommerce</option><option value="Services Site">⚙️ Services</option></select></div>
        <div class="step"><h3>✨ Extra Sections</h3><div class="chk-group">
            <label class="chk-item"><input type="checkbox" name="intro" value="yes" checked> 📖 Strong Intro</label>
            <label class="chk-item"><input type="checkbox" name="faqs" value="yes"> ❓ FAQs</label>
            <label class="chk-item"><input type="checkbox" name="paa" value="yes"> 🔎 People Also Ask</label>
            <label class="chk-item"><input type="checkbox" name="conclusion" value="yes" checked> 📝 Conclusion</label>
        </div></div>
        <button class="btn-main" type="submit">🤖 Get AI Suggestions →</button>
    </form><a href="javascript:history.back()" class="back-link">← Go Back</a></div></body></html>""")

@app.route("/ai-suggest", methods=["POST"])
def ai_suggest():
    user=get_user()
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
    return make_response(f"""{page_head("AI Suggestions")}<div class="container">{logo_section()}
    <div class="step-badge">🤖 AI Suggestions</div><h2>Select Your Preferences</h2>
    <span class="kw-badge">🎯 {keyword}</span>
    <form action="/generate-article" method="POST" id="mf">
        <input type="hidden" name="keyword" value="{keyword}"><input type="hidden" name="website" value="{website}">
        <input type="hidden" name="country" value="{country}"><input type="hidden" name="language" value="{language}">
        <input type="hidden" name="length" value="{length}"><input type="hidden" name="intent" value="{intent}">
        <input type="hidden" name="content_type" value="{content_type}"><input type="hidden" name="category" value="{category}">
        <input type="hidden" name="writer_type" value="{writer_type}"><input type="hidden" name="intro" value="{intro}">
        <input type="hidden" name="faqs" value="{faqs}"><input type="hidden" name="paa" value="{paa}"><input type="hidden" name="conclusion" value="{conclusion}">
        <input type="hidden" name="sub_category" id="fc"><input type="hidden" name="meta_title" id="ft"><input type="hidden" name="meta_desc" id="fd">
        <div class="step"><h3>📂 Select Category</h3><select id="cs" onchange="chkCustom(this,'ci')">{co}</select><input type="text" id="ci" class="ci" placeholder="Custom category..."></div>
        <div class="step"><h3>📌 Select Meta Title</h3><select id="ts" onchange="chkCustom(this,'ti')">{to}</select><input type="text" id="ti" class="ci" placeholder="Custom meta title..."></div>
        <div class="step"><h3>📝 Select Meta Description</h3><select id="ds" onchange="chkCustom(this,'di')">{do}</select><input type="text" id="di" class="ci" placeholder="Custom meta description..."></div>
        <button class="btn-main" type="button" onclick="submitSuggest()">🚀 Generate Article!</button>
    </form><a href="javascript:history.back()" class="back-link">← Go Back</a></div></body></html>""")

@app.route("/generate-article", methods=["POST"])
def generate_article():
    user=get_user()
    if not user: return redirect("/login")
    if not can_use(user['email'],'article'):
        return make_response(f"""{page_head()}<div class="container">{logo_section()}
        <div class="upg-box"><h3>✍️ Daily Article Limit Reached!</h3><p>Upgrade to write unlimited articles!</p><a href="/pricing" class="upg-btn">Upgrade Now</a></div>
        <a href="/" class="back-link">← Go Back</a></div></body></html>""")
    inc_usage(user['email'],'article')
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
    article=ai_call(f"""Write a {length}-word SEO article in {language}.\nKeyword: "{keyword}", Meta Title: {meta_title}\nBusiness: {category} — {sub_category}, Country: {country}, Intent: {intent}\nStructure:\n# {meta_title}\n{chr(10).join(secs)}\nRules: keyword in first 100 words, keyword in 2+ headings, write in {language}, professional SEO.""",max_tokens=2000)
    seo_guide="1. H1: ONE H1 with keyword\n2. H2: Each section\n3. Internal Links: 2-3 pages\n4. External Links: 1-2 authority sites\n5. URL: yoursite.com/keyword\n6. Keyword Density: 1-2%\n7. Image Alt: include keyword\n8. Meta Title: 50-60 chars\n9. Meta Desc: 150-160 chars"
    fn=keyword.strip().replace(" ","_")+"_article.txt"
    content=f"META TITLE: {meta_title}\nMETA DESC: {meta_desc}\nKEYWORD: {keyword}\nLANGUAGE: {language}\n\n{'='*50}\n\n{article}\n\n{'='*50}\nSEO GUIDELINES\n{'='*50}\n\n{seo_guide}"
    enc=quote(content)
    return make_response(f"""{page_head("Article Ready")}<div class="container">{logo_section()}
    <div style="font-size:36px;text-align:center;margin-bottom:10px">✅</div><h2>Article Ready!</h2>
    <div class="meta-card"><strong>🏷️ Writer:</strong> {wlab}<br><strong>📌 Meta Title:</strong> {meta_title}<br><strong>📝 Meta Desc:</strong> {meta_desc}<br><strong>🎯 Keyword:</strong> {keyword} | <strong>🌍</strong> {country} | <strong>🗣️</strong> {language}</div>
    <div class="art-box">{article.replace('<','&lt;').replace('>','&gt;')}</div>
    <div class="seo-box"><strong style="font-size:15px;color:#e67e22">📚 SEO Guidelines</strong><br><br>{seo_guide.replace(chr(10),'<br>')}</div>
    <div class="btns">
        <a href="/download-file?content={enc}&filename={fn}" class="btn btn-g">⬇️ Download</a>
        <a href="/" class="btn btn-p">🔄 New Article</a>
        <a href="javascript:history.back()" class="btn btn-gr">← Back</a>
    </div></div></body></html>""")

# ═══ TECHNICAL SEO ═══
def technical_report(category, website, country, language):
    html_content,_,final_url=fetch_html(website)
    target_url=final_url if final_url else website
    if not html_content:
        return make_response(f"""{page_head()}<div class="container">{logo_section()}<h2>❌ Cannot Fetch Website</h2><a href="/" class="back-link">← Back</a></div></body></html>""")

    meta=get_meta(html_content)
    page_size_kb=len(html_content.encode('utf-8'))/1024
    internal_links=get_internal_links(html_content,target_url)
    has_ssl=check_ssl(target_url)
    has_viewport=re.search(r'<meta[^>]+name=["\']viewport["\']',html_content,re.IGNORECASE) is not None
    has_jsonld='"@context"' in html_content
    schema_types=list(set(re.findall(r'"@type"\s*:\s*"([^"]+)"',html_content)))
    images=get_images(html_content)
    missing_alt=[]; 
    for img in images:
        if 'alt=""' in img or "alt=''" in img or 'alt=' not in img.lower():
            sm=re.search(r'src=["\']([^"\']+)["\']',img)
            missing_alt.append(sm.group(1) if sm else "?")

    score=100
    deductions=[]
    if not has_ssl: score-=15; deductions.append("No SSL/HTTPS")
    if not meta.get("title"): score-=10; deductions.append("Missing title tag")
    if not meta.get("description"): score-=8; deductions.append("Missing meta description")
    if meta.get("h1_count",0)==0: score-=8; deductions.append("No H1 tag")
    if missing_alt: score-=min(10,len(missing_alt)*2); deductions.append(f"{len(missing_alt)} images missing alt tags")
    if not has_jsonld: score-=6; deductions.append("No schema markup")
    if not has_viewport: score-=8; deductions.append("No mobile viewport")
    score=max(0,score)
    score_color="#27ae60" if score>=80 else "#f39e0b" if score>=60 else "#e74c3c"

    # URL Structure Analysis
    url_analysis=ai_call(f"""Technical SEO expert. Analyze URL structure for: {target_url}
Category: {category}, Country: {country}
Internal pages found: {[l for l in internal_links[:15]]}
Current meta title: {meta.get('title','N/A')}

Provide:
1. URL Structure Score (X/10) with explanation
2. Current URL pattern analysis
3. SEO-friendly URL recommendations for {category} website
4. Specific URL structure examples to implement
5. Common URL mistakes found""", max_tokens=600)

    rows_int="".join([f'<div class="url-item"><span class="url-text"><a href="{l}" target="_blank">{l}</a></span><span class="s200">Internal</span></div>' for l in internal_links[:15]])

    dl_content=f"TECHNICAL SEO REPORT\nWebsite: {target_url}\nScore: {score}/100\nDate: {datetime.now().strftime('%Y-%m-%d')}\n\n{'='*50}\nURL ANALYSIS\n{'='*50}\n\n{url_analysis}"
    enc_dl=quote(dl_content)

    return make_response(f"""{page_head("Technical SEO")}<div class="container">{logo_section()}
    <div class="step-badge">🔵 Technical SEO</div><h2>Technical SEO Analysis</h2>
    <div class="info-bar"><span>🌐 <a href="{target_url}" target="_blank" style="color:#667eea">{target_url}</a></span><span>📂 {category}</span></div>

    <div style="text-align:center;margin-bottom:25px">
        <div class="score-circle" style="background:{score_color}">
            <span style="font-size:32px;font-weight:800;color:white">{score}</span>
            <span style="font-size:11px;color:rgba(255,255,255,0.8)">/100</span>
        </div>
        <strong style="font-size:16px;color:#2c3e50">Technical SEO Score</strong>
    </div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL/HTTPS</div></div>
        <div class="stat-box"><div class="stat-num">{page_size_kb:.0f}KB</div><div class="stat-label">Page Size</div></div>
        <div class="stat-box"><div class="stat-num">{meta.get('h1_count',0)}</div><div class="stat-label">H1 Tags</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_viewport else "red"}">{"✅" if has_viewport else "❌"}</div><div class="stat-label">Mobile</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_jsonld else "red"}">{"✅" if has_jsonld else "❌"}</div><div class="stat-label">Schema</div></div>
        <div class="stat-box"><div class="stat-num red">{len(missing_alt)}</div><div class="stat-label">Missing Alt</div></div>
    </div>

    <div class="rcard">
        <div class="rcard-head">📋 Page Details</div>
        <div class="rcard-body" style="white-space:normal">
            <strong>Meta Title:</strong> {meta.get('title') or '❌ Missing'} {f"({len(meta.get('title',''))} chars)" if meta.get('title') else ""}<br>
            <strong>Meta Description:</strong> {meta.get('description') or '❌ Missing'}<br>
            <strong>H1:</strong> {meta.get('h1_count',0)} found {"✅" if meta.get('h1_count')==1 else "⚠️"} — {meta.get('h1_text','N/A')[:80] if meta.get('h1_text') else 'N/A'}<br>
            <strong>Schema Types:</strong> {", ".join(schema_types) if schema_types else "❌ None found"}<br>
            <strong>Canonical:</strong> {meta.get('canonical') or '❌ Not set'}<br>
            <strong>Issues:</strong> {" | ".join(deductions) if deductions else "✅ No major issues"}
        </div>
    </div>

    <div class="rcard">
        <div class="rcard-head orange">🔗 URL Structure Analysis</div>
        <div class="rcard-body" style="white-space:pre-wrap;line-height:1.9">{url_analysis.replace('<','&lt;').replace('>','&gt;')}</div>
    </div>

    <div class="rcard">
        <div class="rcard-head">🔗 Internal Pages Found ({len(internal_links)})</div>
        <div class="rcard-body" style="max-height:300px;overflow-y:auto">{rows_int or "<p>No internal links found.</p>"}</div>
    </div>

    <a href="/download-file?content={enc_dl}&filename=technical_seo.txt" class="dl-btn">⬇️ Download Technical Report</a>
    <div class="btns">
        <a href="/" class="btn btn-p">🔄 New Audit</a>
        <a href="javascript:history.back()" class="btn btn-gr">← Back</a>
    </div></div></body></html>""")

# ═══ OFF-PAGE SEO ═══
def offpage_report(category, website, country, language):
    html_content,_,final_url=fetch_html(website)
    target_url=final_url if final_url else website
    if not html_content:
        return make_response(f"""{page_head()}<div class="container">{logo_section()}<h2>❌ Cannot Fetch Website</h2><a href="/" class="back-link">← Back</a></div></body></html>""")

    domain=urlparse(target_url).netloc
    external_links=get_external_links(html_content,target_url)
    ext_domains=list(set([urlparse(l).netloc for l in external_links]))
    has_ssl=check_ssl(target_url)
    social_platforms=['facebook.com','twitter.com','x.com','instagram.com','linkedin.com','youtube.com','tiktok.com','pinterest.com']
    social_links=[d for d in ext_domains if any(sp in d for sp in social_platforms)]

    # AI Research — Competitors
    competitor_result=ai_call(f"""Off-Page SEO expert. Research competitors for:
Domain: {domain}
Category: {category}
Country: {country}

Find 3 REAL, well-known competitor websites currently operating in {category} niche targeting {country}.
Research their actual domain names.

Format EXACTLY:
NAME: Company Name
URL: domain.com
STRENGTH: What makes them strong in SEO (backlinks, content, DA)
WHY_THREAT: Why they outrank similar sites

(repeat for all 3, nothing else)""", max_tokens=700)

    comp_names,comp_urls,comp_strengths,comp_threats=[],[],[],[]
    for line in competitor_result.strip().split('\n'):
        l=line.strip()
        if l.upper().startswith('NAME:'): comp_names.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('URL:'): comp_urls.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('STRENGTH:'): comp_strengths.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('WHY_THREAT:'): comp_threats.append(l.split(':',1)[-1].strip())

    competitor_cards=""
    for i in range(min(len(comp_names),len(comp_urls))):
        s=comp_strengths[i] if i<len(comp_strengths) else ""
        t=comp_threats[i] if i<len(comp_threats) else ""
        competitor_cards+=f"""<div class="rcard" style="margin-bottom:15px">
        <div class="rcard-head red">🏆 {comp_names[i]} — <a href="https://{comp_urls[i]}" target="_blank" style="color:white">{comp_urls[i]}</a></div>
        <div class="rcard-body"><strong>💪 Strength:</strong> {s}<br><strong>⚠️ Why They Rank:</strong> {t}</div></div>"""

    # AI Research — Backlink Sites
    backlink_result=ai_call(f"""Off-Page SEO expert. Research high-quality backlink sources for:
Domain: {domain}
Category: {category}
Country: {country}

Find 12 REAL, currently-active platforms where {category} websites in {country} can get quality backlinks.
Do actual research for the best platforms specific to this niche.

Format EXACTLY:
PLATFORM: platform name
URL: platform.com
TYPE: Guest Post/Directory/Forum/Press/Profile/Social
DA: estimated domain authority (number)
HOW: Specific method to get backlink here

(repeat 12 times, nothing else)""", max_tokens=1000)

    platforms,urls_p,ptypes,das,hows=[],[],[],[],[]
    for line in backlink_result.strip().split('\n'):
        l=line.strip()
        if l.upper().startswith('PLATFORM:'): platforms.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('URL:'): urls_p.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('TYPE:'): ptypes.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('DA:'): das.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('HOW:'): hows.append(l.split(':',1)[-1].strip())

    rows_bl=""
    for i in range(min(len(platforms),len(ptypes),len(das),len(hows))):
        u=urls_p[i] if i<len(urls_p) else ""
        rows_bl+=f"""<tr>
            <td><strong>{platforms[i]}</strong><br><a href="https://{u}" target="_blank" style="color:#667eea;font-size:11px">{u}</a></td>
            <td><span class="badge bb2">{ptypes[i]}</span></td>
            <td><strong style="color:#667eea">DA {das[i]}</strong></td>
            <td style="font-size:12px">{hows[i]}</td>
        </tr>"""
    if not rows_bl: rows_bl="<tr><td colspan='4' style='text-align:center;padding:20px;color:#e74c3c'>Could not generate suggestions.</td></tr>"

    social_html="".join([f'<div class="url-item"><span class="url-text"><a href="https://{d}" target="_blank">{d}</a></span><span class="badge bb2">Social</span></div>' for d in social_links]) or "<p style='color:#95a5a6;padding:10px'>No social profiles linked from homepage.</p>"

    dl_content=f"OFF-PAGE SEO REPORT\nWebsite: {target_url}\nDate: {datetime.now().strftime('%Y-%m-%d')}\n\nCOMPETITORS:\n{competitor_result}\n\nBACKLINK OPPORTUNITIES:\n{backlink_result}"
    enc_dl=quote(dl_content)

    return make_response(f"""{page_head("Off-Page SEO")}<div class="container">{logo_section()}
    <div class="step-badge" style="background:linear-gradient(135deg,#e74c3c,#c0392b)">🔴 Off-Page SEO Analysis</div>
    <h2>Backlinks & Competitor Research</h2>
    <div class="info-bar"><span>🌐 <a href="{target_url}" target="_blank" style="color:#667eea">{target_url}</a></span><span>📂 {category}</span><span>🌍 {country}</span></div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num">{len(external_links)}</div><div class="stat-label">Outbound Links</div></div>
        <div class="stat-box"><div class="stat-num">{len(ext_domains)}</div><div class="stat-label">External Domains</div></div>
        <div class="stat-box"><div class="stat-num">{len(social_links)}</div><div class="stat-label">Social Profiles</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL Active</div></div>
    </div>

    <div class="rcard"><div class="rcard-head">📱 Social Media Profiles on Website</div>
    <div class="rcard-body">{social_html}</div></div>

    <h2 style="margin-top:10px">🏆 Top Competitors in Your Niche</h2>
    <p style="color:#95a5a6;margin-bottom:15px;font-size:13px">AI researched real competitors for {category} in {country}:</p>
    {competitor_cards or "<p style='color:#e74c3c;padding:15px'>Could not identify competitors. Try again.</p>"}

    <h2 style="margin-top:20px">🎯 Backlink Opportunities</h2>
    <p style="color:#95a5a6;margin-bottom:15px;font-size:13px">AI researched real platforms for {category} niche in {country}:</p>
    <table><thead><tr><th>Platform</th><th>Type</th><th>Authority</th><th>How to Get Backlink</th></tr></thead>
    <tbody>{rows_bl}</tbody></table>

    <a href="/download-file?content={enc_dl}&filename=offpage_report.txt" class="dl-btn" style="margin-top:20px">⬇️ Download Off-Page Report</a>

    <div class="note-box" style="margin-top:15px">⚠️ Social profile data is from real website crawl. Competitors and backlink platforms are AI-researched based on your niche and country.</div>
    <div class="btns"><a href="/" class="btn btn-p">🔄 New Report</a><a href="javascript:history.back()" class="btn btn-gr">← Back</a></div>
</div></body></html>""")

# ─── DOWNLOAD ───
@app.route("/download-file")
def download_file():
    content=unquote(request.args.get("content",""))
    filename=request.args.get("filename","report.txt")
    return Response(content,mimetype="text/plain",headers={"Content-Disposition":f"attachment; filename={filename}"})

if __name__ == "__main__":
    app.run(debug=True)

from flask import Flask, request, Response, make_response
from urllib.parse import quote, unquote, urljoin, urlparse
import requests as req
import re
import os

app = Flask(__name__)
API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
HEADERS_BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
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
    return {
        "title": title.group(1).strip() if title else None,
        "description": desc.group(1).strip() if desc else None,
        "robots": robots_meta.group(1).strip() if robots_meta else None,
        "canonical": canonical.group(1).strip() if canonical else None,
        "h1_count": len(h1),
        "h1_text": re.sub('<[^<]+?>', '', h1[0]).strip() if h1 else None,
    }

def ai_call(prompt, max_tokens=900):
    try:
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "Mr Websol SEO Agent"
        }
        data = {"model": "google/gemma-3-12b-it:free", "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
        r = req.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data, timeout=60)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"API Error: {r.text}"
    except Exception as e:
        return f"Error: {str(e)}"

def check_url_status(url, timeout=8):
    try:
        r = req.head(url, headers=HEADERS_BROWSER, timeout=timeout, allow_redirects=True)
        return r.status_code
    except Exception:
        try:
            r = req.get(url, headers=HEADERS_BROWSER, timeout=timeout, allow_redirects=True)
            return r.status_code
        except Exception:
            return None

# ─────────────────────────────────────────────
# STYLE
# ─────────────────────────────────────────────
def get_style(direction="ltr"):
    return f"""
<style>
* {{ margin:0;padding:0;box-sizing:border-box; }}
body {{
    font-family:'Segoe UI',sans-serif;
    background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);
    min-height:100vh; padding:0; direction:{direction};
}}
.container {{
    max-width:100%; margin:0 auto; background:#fff;
    border-radius:0; padding:40px 60px;
    min-height:100vh;
}}
.logo {{ text-align:center; margin-bottom:25px; }}
.logo h1 {{
    font-size:26px;
    background:linear-gradient(135deg,#667eea,#764ba2);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    font-weight:800;
}}
.logo p {{ color:#95a5a6; margin-top:6px; font-size:14px; }}
.divider {{ height:3px; background:linear-gradient(135deg,#667eea,#764ba2); border-radius:3px; margin:20px 0; }}
.step-badge {{
    display:inline-block;
    background:linear-gradient(135deg,#667eea,#764ba2);
    color:white; padding:5px 18px; border-radius:25px;
    font-size:13px; font-weight:700; margin-bottom:15px;
}}
.red-badge {{
    display:inline-block;
    background:linear-gradient(135deg,#e74c3c,#c0392b);
    color:white; padding:5px 18px; border-radius:25px;
    font-size:13px; font-weight:700; margin-bottom:15px;
}}
.form-group {{ margin-bottom:20px; }}
label {{
    display:block; font-weight:700; color:#2c3e50;
    margin-bottom:8px; font-size:13px; text-transform:uppercase; letter-spacing:0.5px;
}}
input[type=text], select {{
    width:100%; padding:13px 16px; border:2px solid #e8e8e8;
    border-radius:12px; font-size:15px; color:#2c3e50;
    transition:all 0.3s; background:#fafafa;
}}
input[type=text]:focus, select:focus {{
    border-color:#667eea; background:#fff; outline:none;
    box-shadow:0 0 0 4px rgba(102,126,234,0.1);
}}
.grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
.seo-type-group {{ display:flex; gap:15px; margin-top:10px; flex-wrap:wrap; }}
.seo-type-card {{
    flex:1; min-width:140px; padding:18px 15px;
    border:3px solid #e0e0e0; border-radius:14px;
    text-align:center; cursor:pointer; transition:all 0.3s; background:#fafafa;
}}
.seo-type-card:hover {{ transform:translateY(-3px); box-shadow:0 8px 25px rgba(0,0,0,0.1); }}
.seo-type-card input[type=radio] {{ display:none; }}
.seo-type-card .icon {{ font-size:30px; margin-bottom:8px; }}
.seo-type-card .name {{ font-weight:700; color:#2c3e50; font-size:14px; }}
.seo-type-card .desc {{ font-size:12px; color:#95a5a6; margin-top:4px; }}
.seo-type-card.selected {{
    border-color:#667eea;
    background:linear-gradient(135deg,#f0f2ff,#f8f0ff);
    transform:translateY(-3px); box-shadow:0 8px 25px rgba(102,126,234,0.2);
}}
.sub-type-group {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(155px,1fr)); gap:15px; margin-top:10px; }}
.sub-type-card {{
    padding:18px 12px; border:3px solid #e0e0e0; border-radius:14px;
    text-align:center; cursor:pointer; transition:all 0.3s; background:#fafafa;
    text-decoration:none; display:block;
}}
.sub-type-card:hover {{
    border-color:#667eea; transform:translateY(-3px);
    box-shadow:0 8px 25px rgba(102,126,234,0.15);
    background:linear-gradient(135deg,#f0f2ff,#f8f0ff);
}}
.sub-type-card .icon {{ font-size:28px; margin-bottom:7px; }}
.sub-type-card .name {{ font-weight:700; color:#2c3e50; font-size:13px; }}
.sub-type-card .desc {{ font-size:11px; color:#95a5a6; margin-top:4px; }}
.btn-main {{
    width:100%; padding:15px;
    background:linear-gradient(135deg,#667eea,#764ba2);
    color:white; border:none; border-radius:12px;
    font-size:16px; cursor:pointer; font-weight:700;
    transition:all 0.3s; margin-top:8px;
}}
.btn-main:hover {{ transform:translateY(-2px); box-shadow:0 10px 30px rgba(102,126,234,0.4); }}
table {{ width:100%; border-collapse:collapse; margin-top:10px; }}
th {{
    background:linear-gradient(135deg,#667eea,#764ba2);
    color:white; padding:12px 14px; text-align:left;
    font-size:12px; font-weight:700; text-transform:uppercase;
}}
th:first-child {{ border-radius:10px 0 0 0; }}
th:last-child {{ border-radius:0 10px 0 0; }}
td {{ padding:11px 14px; border-bottom:1px solid #f0f0f0; font-size:13px; color:#2c3e50; word-break:break-all; }}
tr:hover {{ background:#f8f9ff; }}
.badge {{ display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px; font-weight:700; }}
.badge-easy {{ background:#d5f5e3; color:#27ae60; }}
.badge-medium {{ background:#fef9e7; color:#e67e22; }}
.badge-hard {{ background:#fdecea; color:#e74c3c; }}
.badge-blue {{ background:#e8f0ff; color:#667eea; }}
.step {{ background:#f8f9ff; border-radius:14px; padding:20px; margin-bottom:20px; border-left:5px solid #667eea; }}
.step h3 {{ color:#2c3e50; margin-bottom:12px; font-size:14px; font-weight:700; }}
.checkbox-group {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }}
.checkbox-item {{
    display:flex; align-items:center; gap:8px;
    background:white; padding:8px 14px; border-radius:25px;
    border:2px solid #e0e0e0; cursor:pointer; font-size:13px; transition:all 0.2s;
}}
.checkbox-item:hover {{ border-color:#667eea; background:#f8f9ff; }}
.checkbox-item input {{ width:15px; height:15px; cursor:pointer; }}
.keyword-badge {{
    display:inline-block;
    background:linear-gradient(135deg,#667eea,#764ba2);
    color:white; padding:5px 16px; border-radius:25px;
    font-size:13px; font-weight:600; margin-bottom:20px;
}}
.meta-card {{
    background:linear-gradient(135deg,#eaf4ff,#f0f0ff);
    border-radius:14px; padding:18px 22px; margin-bottom:20px;
    font-size:14px; color:#2c3e50; line-height:2; border-left:5px solid #667eea;
}}
.article-box {{
    background:#f8f9fa; border-radius:14px; padding:25px;
    line-height:1.95; max-height:500px; overflow-y:auto;
    border-left:5px solid #27ae60; font-size:14px; color:#2c3e50;
    margin-bottom:20px; white-space:pre-wrap;
}}
.seo-box {{
    background:linear-gradient(135deg,#fff9e6,#fffbf0);
    border-radius:14px; padding:25px; border-left:5px solid #f39c12;
    font-size:13px; color:#2c3e50; line-height:2; margin-bottom:20px;
}}
.result-card {{ border-radius:14px; margin-bottom:22px; overflow:hidden; border:2px solid #e8e8e8; }}
.result-card-head {{ background:linear-gradient(135deg,#667eea,#764ba2); color:white; padding:12px 20px; font-size:15px; font-weight:700; display:flex; align-items:center; gap:8px; }}
.result-card-head.green {{ background:linear-gradient(135deg,#27ae60,#2ecc71); }}
.result-card-head.red {{ background:linear-gradient(135deg,#e74c3c,#c0392b); }}
.result-card-head.orange {{ background:linear-gradient(135deg,#e67e22,#f39c12); }}
.result-card-body {{ padding:20px; background:#fff; font-size:14px; line-height:1.9; white-space:pre-wrap; }}
.stat-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin-bottom:25px; }}
.stat-box {{ background:#f8f9ff; border-radius:12px; padding:16px; text-align:center; border:2px solid #e8e8e8; }}
.stat-box .stat-num {{ font-size:26px; font-weight:800; color:#667eea; }}
.stat-box .stat-num.red {{ color:#e74c3c; }}
.stat-box .stat-num.green {{ color:#27ae60; }}
.stat-box .stat-num.orange {{ color:#e67e22; }}
.stat-box .stat-label {{ font-size:12px; color:#95a5a6; margin-top:5px; font-weight:600; }}
.url-item {{ display:flex; align-items:center; gap:10px; padding:9px 14px; border-bottom:1px solid #f0f0f0; font-size:13px; flex-wrap:wrap; }}
.url-item:last-child {{ border-bottom:none; }}
.url-text {{ color:#2c3e50; word-break:break-all; flex:1; }}
.status-200 {{ color:#27ae60; font-weight:700; font-size:12px; white-space:nowrap; }}
.status-301 {{ color:#e67e22; font-weight:700; font-size:12px; white-space:nowrap; }}
.status-404 {{ color:#e74c3c; font-weight:700; font-size:12px; white-space:nowrap; }}
.info-bar {{ color:#95a5a6; margin-bottom:20px; font-size:13px; display:flex; gap:10px; flex-wrap:wrap; }}
.info-bar span {{ background:#f8f9fa; padding:5px 12px; border-radius:20px; border:1px solid #e0e0e0; }}
h2 {{
    background:linear-gradient(135deg,#667eea,#764ba2);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    font-size:22px; margin-bottom:8px;
}}
.success-icon {{ font-size:36px; margin-bottom:8px; text-align:center; }}
.note-box {{ background:#fffbf0; border:2px dashed #f39c12; border-radius:12px; padding:14px 18px; font-size:13px; color:#856404; margin-bottom:20px; line-height:1.7; }}
.score-circle {{
    width:90px; height:90px; border-radius:50%;
    display:flex; align-items:center; justify-content:center;
    font-size:24px; font-weight:800; color:white;
    margin:0 auto 10px; flex-shrink:0;
}}
.toc {{ background:#f8f9ff; border-radius:14px; padding:18px 22px; margin-bottom:25px; border-left:5px solid #667eea; }}
.toc a {{ color:#667eea; text-decoration:none; font-weight:600; font-size:13px; }}
.toc-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:8px; margin-top:10px; }}
.custom-input {{ display:none; margin-top:10px; border-color:#667eea !important; background:#f8f9ff !important; }}
.buttons {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:15px; }}
.btn {{
    flex:1; min-width:130px; padding:13px; border-radius:12px;
    text-align:center; font-size:14px; font-weight:700;
    cursor:pointer; border:none; text-decoration:none;
    transition:all 0.2s; display:inline-block;
}}
.btn-green {{ background:linear-gradient(135deg,#27ae60,#2ecc71); color:white; }}
.btn-purple {{ background:linear-gradient(135deg,#667eea,#764ba2); color:white; }}
.btn-gray {{ background:#f0f0f0; color:#2c3e50; }}
.btn-red {{ background:linear-gradient(135deg,#e74c3c,#c0392b); color:white; }}
.btn:hover {{ transform:translateY(-2px); opacity:0.95; }}
.back-link {{
    display:inline-block; margin-top:18px; padding:9px 20px;
    background:#f0f0f0; border-radius:10px; text-decoration:none;
    color:#2c3e50; font-weight:600; font-size:13px;
}}
.loading-screen {{
    text-align:center; padding:60px 20px;
}}
.loading-screen .spinner {{
    width:60px; height:60px; border:6px solid #f0f0f0;
    border-top:6px solid #667eea; border-radius:50%;
    animation:spin 1s linear infinite; margin:0 auto 25px;
}}
@keyframes spin {{ 0%{{transform:rotate(0deg)}} 100%{{transform:rotate(360deg)}} }}
.loading-screen h2 {{ margin-bottom:10px; }}
.loading-screen p {{ color:#95a5a6; font-size:14px; }}
@media(max-width:600px) {{
    .container {{ padding:20px 15px; }}
    .grid-2 {{ grid-template-columns:1fr; }}
    .seo-type-group {{ flex-direction:column; }}
    .stat-grid {{ grid-template-columns:repeat(2,1fr); }}
    .toc-grid {{ grid-template-columns:1fr 1fr; }}
}}
</style>
<script>
function selectSeoType(el) {{
    document.querySelectorAll('.seo-type-card').forEach(c => c.classList.remove('selected'));
    el.classList.add('selected');
    el.querySelector('input[type=radio]').checked = true;
}}
function checkCustom(selectEl, inputId) {{
    var input = document.getElementById(inputId);
    if (selectEl.value.includes('✏️')) {{ input.style.display='block'; input.focus(); }}
    else {{ input.style.display='none'; }}
}}
function submitSuggestForm() {{
    var catVal = document.getElementById('cat_select').value.includes('✏️') ? document.getElementById('cat_input').value : document.getElementById('cat_select').value;
    var titleVal = document.getElementById('title_select').value.includes('✏️') ? document.getElementById('title_input').value : document.getElementById('title_select').value;
    var descVal = document.getElementById('desc_select').value.includes('✏️') ? document.getElementById('desc_input').value : document.getElementById('desc_select').value;
    if (!catVal || !titleVal || !descVal) {{ alert('Please fill all fields!'); return; }}
    document.getElementById('final_category').value = catVal;
    document.getElementById('final_title').value = titleVal;
    document.getElementById('final_desc').value = descVal;
    document.getElementById('mainform').submit();
}}
</script>
"""

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

def logo_html():
    return """<div class="logo">
        <h1>🚀 Mr Websol SEO Agent</h1>
        <p>AI Powered Professional SEO Platform</p>
    </div><div class="divider"></div>"""

# ═══════════════════════════════════════════════
# HOME — STEP 1
# ═══════════════════════════════════════════════
@app.route("/")
def home():
    cat_opts = "".join([f'<option value="{c}">{c}</option>' for c in CATEGORIES])
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mr Websol SEO Agent</title>{get_style()}</head>
<body><div class="container">
    {logo_html()}
    <form action="/seo-type" method="POST">
        <div class="step-badge">⚙️ Step 1 — Business Setup</div>
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
                <select name="country">
                    <option value="Pakistan">🇵🇰 Pakistan</option>
                    <option value="United States">🇺🇸 United States</option>
                    <option value="United Kingdom">🇬🇧 United Kingdom</option>
                    <option value="India">🇮🇳 India</option>
                    <option value="Australia">🇦🇺 Australia</option>
                    <option value="Canada">🇨🇦 Canada</option>
                    <option value="UAE">🇦🇪 UAE</option>
                    <option value="Saudi Arabia">🇸🇦 Saudi Arabia</option>
                    <option value="Germany">🇩🇪 Germany</option>
                    <option value="Global">🌍 Global</option>
                </select>
            </div>
            <div class="form-group">
                <label>🗣️ Language</label>
                <select name="language">
                    <option value="English">🇬🇧 English</option>
                    <option value="Urdu">🇵🇰 Urdu</option>
                    <option value="Arabic">🇸🇦 Arabic</option>
                </select>
            </div>
        </div>
        <div class="form-group">
            <label>🎯 Select SEO Type</label>
            <div class="seo-type-group">
                <div class="seo-type-card selected" onclick="selectSeoType(this)">
                    <input type="radio" name="seo_type" value="On-Page" checked>
                    <div class="icon">🟢</div><div class="name">On-Page SEO</div>
                    <div class="desc">Content & Keywords</div>
                </div>
                <div class="seo-type-card" onclick="selectSeoType(this)">
                    <input type="radio" name="seo_type" value="Technical">
                    <div class="icon">🔵</div><div class="name">Technical SEO</div>
                    <div class="desc">Full Site Audit Report</div>
                </div>
                <div class="seo-type-card" onclick="selectSeoType(this)">
                    <input type="radio" name="seo_type" value="Off-Page">
                    <div class="icon">🔴</div><div class="name">Off-Page SEO</div>
                    <div class="desc">Backlinks & Competitors</div>
                </div>
            </div>
        </div>
        <button class="btn-main" type="submit">Next Step →</button>
    </form>
</div></body></html>"""

@app.route("/seo-type", methods=["POST"])
def seo_type_route():
    seo_type=request.form.get("seo_type"); category=request.form.get("category")
    website=request.form.get("website"); country=request.form.get("country"); language=request.form.get("language")
    if not website.startswith("http"): website = "https://" + website
    if seo_type == "On-Page": return onpage_subtypes(category, website, country, language)
    elif seo_type == "Technical": return technical_full_report(category, website, country, language)
    else: return offpage_full_report(category, website, country, language)

# ═══════════════════════════════════════════════════════
# ON-PAGE (UNCHANGED — Same as before)
# ═══════════════════════════════════════════════════════
def onpage_subtypes(category, website, country, language):
    subtypes = [
        ("✍️","Article Writer","Blog & informational articles","article_writer"),
        ("📄","Page Content Writer","Homepage, About, landing pages","page_content"),
        ("⚙️","Service Page Writer","Service description pages","service_page"),
        ("📍","Service Areas Writer","Location-based service pages","service_areas"),
        ("🧠","Semantic SEO Writer","Topic clusters & semantic content","semantic_seo"),
    ]
    cards = ""
    for icon,name,desc,val in subtypes:
        cards += f"""<form action="/onpage-writer" method="POST" style="display:contents">
            <input type="hidden" name="category" value="{category}">
            <input type="hidden" name="website" value="{website}">
            <input type="hidden" name="country" value="{country}">
            <input type="hidden" name="language" value="{language}">
            <input type="hidden" name="writer_type" value="{val}">
            <button type="submit" style="background:none;border:none;padding:0;cursor:pointer;display:block;width:100%">
                <div class="sub-type-card"><div class="icon">{icon}</div><div class="name">{name}</div><div class="desc">{desc}</div></div>
            </button></form>"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>On-Page SEO</title>{get_style()}</head>
<body><div class="container">{logo_html()}
    <div class="step-badge">🟢 On-Page SEO — Step 2</div>
    <h2>Select Content Type</h2>
    <p style="color:#95a5a6;margin-bottom:20px;font-size:14px">What kind of content do you want to create?</p>
    <div class="sub-type-group">{cards}</div>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>"""

@app.route("/onpage-writer", methods=["POST"])
def onpage_writer():
    category=request.form.get("category"); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language"); writer_type=request.form.get("writer_type")
    wl = {"article_writer":"✍️ Article Writer","page_content":"📄 Page Content Writer","service_page":"⚙️ Service Page Writer","service_areas":"📍 Service Areas Writer","semantic_seo":"🧠 Semantic SEO Writer"}
    label = wl.get(writer_type,"Content Writer")
    kw_map = {"article_writer":"blog article topics, informational keywords, long-tail question keywords","page_content":"homepage, about page, landing page keywords","service_page":"service-specific commercial keywords, transactional keywords","service_areas":"local SEO, location-based service keywords, city+service combinations","semantic_seo":"semantic clusters, LSI keywords, topic authority keywords"}
    kw_focus = kw_map.get(writer_type,"SEO keywords")
    prompt = f"""SEO expert. Website: {website}, Business: {category}, Country: {country}\nFocus: {kw_focus}\nReturn ONLY 10 keywords in pipe format:\nkeyword | 40,000/mo | EASY | Informational\n10 lines only. No extra text."""
    result = ai_call(prompt)
    rows = ""
    for line in result.strip().split('\n'):
        if '|' in line:
            p = [x.strip() for x in line.split('|')]
            if len(p) >= 4:
                kd = p[2].upper()
                badge = f'<span class="badge {"badge-easy" if "EASY" in kd else "badge-medium" if "MEDIUM" in kd else "badge-hard"}">{p[2]}</span>'
                rows += f"""<tr><td><strong>{p[0]}</strong></td><td>📊 {p[1]}</td><td>{badge}</td><td>{p[3]}</td>
                    <td><form action="/article-settings" method="POST" style="margin:0">
                        <input type="hidden" name="keyword" value="{p[0]}"><input type="hidden" name="website" value="{website}">
                        <input type="hidden" name="country" value="{country}"><input type="hidden" name="language" value="{language}">
                        <input type="hidden" name="category" value="{category}"><input type="hidden" name="writer_type" value="{writer_type}">
                        <button type="submit" style="padding:6px 14px;font-size:12px;border-radius:8px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;cursor:pointer;font-weight:600">✍️ Write</button>
                    </form></td></tr>"""
    custom_row = f"""<tr style="background:#f8f9ff"><td colspan="4"><strong>✏️ Custom Keyword</strong></td>
        <td><form action="/article-settings" method="POST" style="margin:0;display:flex;gap:6px">
            <input type="hidden" name="website" value="{website}"><input type="hidden" name="country" value="{country}">
            <input type="hidden" name="language" value="{language}"><input type="hidden" name="category" value="{category}">
            <input type="hidden" name="writer_type" value="{writer_type}">
            <input type="text" name="keyword" placeholder="Your keyword..." style="padding:6px 10px;border-radius:8px;border:2px solid #667eea;font-size:12px;width:150px">
            <button type="submit" style="padding:6px 12px;font-size:12px;border-radius:8px;background:linear-gradient(135deg,#27ae60,#2ecc71);color:white;border:none;cursor:pointer;font-weight:600">Go</button>
        </form></td></tr>"""
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Keywords</title>{get_style()}</head>
<body><div class="container">{logo_html()}<h2>🔍 Keywords Found!</h2>
    <div class="info-bar"><span>🌐 {website}</span><span>📂 {category}</span><span>🌍 {country}</span><span>{label}</span></div>
    <table><thead><tr><th>Keyword</th><th>Volume</th><th>Difficulty</th><th>Intent</th><th>Action</th></tr></thead>
    <tbody>{rows or "<tr><td colspan='5' style='text-align:center;padding:20px;color:#e74c3c'>Could not load keywords.</td></tr>"}{custom_row}</tbody></table>
    <a href="/" class="back-link">← Go Back</a>
</div></body></html>"""

@app.route("/article-settings", methods=["POST"])
def article_settings():
    keyword=request.form.get("keyword","").strip(); website=request.form.get("website")
    country=request.form.get("country"); language=request.form.get("language")
    category=request.form.get("category"); writer_type=request.form.get("writer_type")
    if not keyword: return "<h3 style='color:red;padding:30px'>Keyword missing.</h3>"
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Article Settings</title>{get_style()}</head>
<body><div class="container">{logo_html()}
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
</div></body></html>"""

@app.route("/ai-suggest", methods=["POST"])
def ai_suggest():
    keyword=request.form.get("keyword"); website=request.form.get("website"); country=request.form.get("country")
    language=request.form.get("language"); category=request.form.get("category"); writer_type=request.form.get("writer_type")
    length=request.form.get("length"); intent=request.form.get("intent"); content_type=request.form.get("content_type")
    intro=request.form.get("intro",""); faqs=request.form.get("faqs",""); paa=request.form.get("paa",""); conclusion=request.form.get("conclusion","")
    result = ai_call(f"""SEO expert. Keyword: '{keyword}', Business: {category}, Country: {country}\nReturn ONLY:\nCATEGORIES: Cat One | Cat Two | Cat Three\nTITLE1: ...\nTITLE2: ...\nTITLE3: ...\nDESC1: ...\nDESC2: ...\nDESC3: ...\nNothing else.""")
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
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Suggestions</title>{get_style()}</head>
<body><div class="container">{logo_html()}
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
</div></body></html>"""

@app.route("/generate-article", methods=["POST"])
def generate_article():
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
    article = ai_call(f"""Write a {length}-word SEO article in {language}.\nKeyword: "{keyword}", Meta Title: {meta_title}\nBusiness: {category} — {sub_category}, Country: {country}, Intent: {intent}, Type: {content_type}\nStructure:\n# {meta_title}\n{chr(10).join(secs)}\nRules: keyword in first 100 words, keyword in 2+ headings, write fully in {language}, professional SEO content.""", max_tokens=2000)
    seo_guide="1. H1: ONE H1 with main keyword\n2. H2: Each section\n3. H3: Sub-points & FAQs\n4. Internal Links: 2-3 to your pages\n5. External Links: 1-2 authority sites\n6. URL: yoursite.com/keyword\n7. Keyword Density: 1-2%\n8. Image Alt: include keyword\n9. Meta Title: 50-60 chars\n10. Meta Description: 150-160 chars"
    fn=keyword.strip().replace(" ","_")+"_article.txt"
    content=f"META TITLE: {meta_title}\nMETA DESC: {meta_desc}\nKEYWORD: {keyword}\nLANGUAGE: {language}\nCOUNTRY: {country}\n\n{'='*50}\n\n{article}\n\n{'='*50}\nSEO GUIDELINES\n{'='*50}\n\n{seo_guide}"
    enc=quote(content)
    ad=article.replace('<','&lt;').replace('>','&gt;')
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Article Ready</title>{get_style()}</head>
<body><div class="container">{logo_html()}
    <div class="success-icon">✅</div><h2>Article Ready!</h2>
    <div class="meta-card"><strong>🏷️ Writer:</strong> {wlab}<br><strong>📌 Meta Title:</strong> {meta_title}<br><strong>📝 Meta Desc:</strong> {meta_desc}<br><strong>📂 Category:</strong> {category} — {sub_category}<br><strong>🎯 Keyword:</strong> {keyword} | <strong>🌍</strong> {country} | <strong>🗣️</strong> {language}</div>
    <div class="article-box">{ad}</div>
    <div class="seo-box"><strong style="font-size:15px;color:#e67e22">📚 SEO Guidelines</strong><br><br>{seo_guide.replace(chr(10),'<br>')}</div>
    <div class="buttons">
        <a href="/download-file?content={enc}&filename={fn}" class="btn btn-green">⬇️ Download</a>
        <a href="/" class="btn btn-purple">🔄 New Article</a>
        <a href="javascript:history.back()" class="btn btn-gray">← Back</a>
    </div>
</div></body></html>"""

# ═══════════════════════════════════════════════════════════════
# TECHNICAL SEO — FULL AUTOMATIC REPORT (Single Page, Real Data)
# ═══════════════════════════════════════════════════════════════
def technical_full_report(category, website, country, language):
    html_content, status_code, final_url = fetch_html(website)
    target_url = final_url if final_url else website

    if not html_content:
        return make_response(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{get_style()}</head><body><div class="container">{logo_html()}
        <div class="step-badge">🔵 Technical SEO</div><h2>❌ Could Not Fetch Website</h2>
        <div class="result-card"><div class="result-card-head red">⚠️ Error</div>
        <div class="result-card-body">Could not connect to <strong>{website}</strong>. Please check the URL (make sure it's correct and the site is online) and try again from Home.</div></div>
        <div class="buttons"><a href="/" class="btn btn-gray">🏠 Home</a></div>
        </div></body></html>""")

    domain = urlparse(target_url).netloc
    meta = get_meta(html_content)
    page_size_kb = len(html_content.encode('utf-8')) / 1024
    images = get_images(html_content)
    internal_links = get_internal_links(html_content, target_url)
    external_links = get_external_links(html_content, target_url)
    has_ssl = check_ssl(target_url)

    # ---- 1. SITE AUDIT (real checks) ----
    sample_links = internal_links[:12]
    broken, redirected, working = [], [], []
    for lnk in sample_links:
        sc = check_url_status(lnk)
        if sc is None or sc >= 400: broken.append((lnk, sc or "Error"))
        elif sc in [301,302,307,308]: redirected.append((lnk, sc))
        else: working.append((lnk, sc))

    # Images missing alt
    missing_alt = []
    for img in images:
        if 'alt=""' in img or "alt=''" in img or 'alt=' not in img.lower():
            src_m = re.search(r'src=["\']([^"\']+)["\']', img)
            missing_alt.append(src_m.group(1) if src_m else "unknown")

    # Generic anchors
    anchors = re.findall(r'<a[^>]+href=[^>]+>([^<]*)</a>', html_content, re.IGNORECASE)
    generic_anchors = list(set([a.strip() for a in anchors if a.strip().lower() in ["click here","here","read more","learn more","more","link"]]))

    # ---- 2. INDEXING & CRAWLABILITY ----
    robots_url = target_url.rstrip("/") + "/robots.txt"
    robots_html, robots_status, _ = fetch_html(robots_url)
    robots_found = robots_status == 200 and robots_html
    robots_blocks_all = robots_found and "Disallow: /" in robots_html and "Disallow: /*" not in robots_html
    sitemap_in_robots = robots_found and "Sitemap:" in (robots_html or "")

    sitemap_url = target_url.rstrip("/") + "/sitemap.xml"
    sitemap_html, sitemap_status, _ = fetch_html(sitemap_url)
    sitemap_found = sitemap_status == 200 and sitemap_html
    sitemap_url_count = len(re.findall(r'<url>', sitemap_html)) if sitemap_html else 0

    is_noindex_home = meta.get("robots") and "noindex" in meta.get("robots","").lower()

    # ---- 3. SCHEMA MARKUP ----
    has_jsonld = '"@context"' in html_content or 'application/ld+json' in html_content.lower()
    schema_types = list(set(re.findall(r'"@type"\s*:\s*"([^"]+)"', html_content)))

    # ---- 4. SECURITY ----
    mixed_content = has_ssl and 'src="http://' in html_content
    has_hsts = False
    try:
        r2 = req.get(target_url, headers=HEADERS_BROWSER, timeout=10)
        has_hsts = 'strict-transport-security' in [h.lower() for h in r2.headers.keys()]
    except: pass

    # ---- 5. OPEN GRAPH / SOCIAL ----
    og_title = re.search(r'<meta[^>]+property=["\']og:title["\']', html_content, re.IGNORECASE) is not None
    og_image = re.search(r'<meta[^>]+property=["\']og:image["\']', html_content, re.IGNORECASE) is not None
    twitter_card = re.search(r'<meta[^>]+name=["\']twitter:card["\']', html_content, re.IGNORECASE) is not None

    # ---- 6. MOBILE ----
    has_viewport = re.search(r'<meta[^>]+name=["\']viewport["\']', html_content, re.IGNORECASE) is not None

    # ---- Calculate overall score ----
    score = 100
    deductions = []
    if not has_ssl: score -= 15; deductions.append("No SSL/HTTPS (-15)")
    if broken: score -= min(15, len(broken)*3); deductions.append(f"{len(broken)} broken links (-{min(15,len(broken)*3)})")
    if not meta.get("title"): score -= 8; deductions.append("Missing title tag (-8)")
    if not meta.get("description"): score -= 8; deductions.append("Missing meta description (-8)")
    if meta.get("h1_count",0) == 0: score -= 8; deductions.append("No H1 tag (-8)")
    if meta.get("h1_count",0) > 1: score -= 4; deductions.append("Multiple H1 tags (-4)")
    if missing_alt: score -= min(10, len(missing_alt)*2); deductions.append(f"{len(missing_alt)} images missing alt (-{min(10,len(missing_alt)*2)})")
    if not robots_found: score -= 5; deductions.append("No robots.txt (-5)")
    if robots_blocks_all: score -= 20; deductions.append("robots.txt blocks entire site! (-20)")
    if not sitemap_found: score -= 7; deductions.append("No XML sitemap (-7)")
    if not has_jsonld: score -= 6; deductions.append("No schema markup (-6)")
    if not has_viewport: score -= 8; deductions.append("No mobile viewport tag (-8)")
    if not og_title or not og_image: score -= 4; deductions.append("Incomplete Open Graph tags (-4)")
    if generic_anchors: score -= 3; deductions.append("Generic anchor texts found (-3)")
    if mixed_content: score -= 5; deductions.append("Mixed content detected (-5)")
    if is_noindex_home: score -= 25; deductions.append("Homepage set to noindex! (-25)")
    score = max(0, score)
    score_color = "#27ae60" if score>=80 else "#f39c12" if score>=60 else "#e74c3c"

    # ---- AI overall summary (uses real data) ----
    summary_prompt = f"""You are a senior Technical SEO auditor. Based on this REAL crawled data for {target_url} ({category}, {country}), write a 5-6 sentence executive summary of the site's technical SEO health. Be specific and professional — mention the overall score is {score}/100, and reference 2-3 specific real findings from this data:

- SSL/HTTPS: {"Yes" if has_ssl else "No"}
- Meta Title: {meta.get('title') or 'MISSING'}
- Meta Description: {"Present" if meta.get('description') else "MISSING"}
- H1 Tags: {meta.get('h1_count',0)} found
- Broken Links (sampled): {len(broken)} of {len(sample_links)}
- Images Missing Alt: {len(missing_alt)} of {len(images)}
- Robots.txt: {"Found" if robots_found else "Missing"}
- XML Sitemap: {"Found with " + str(sitemap_url_count) + " URLs" if sitemap_found else "Missing"}
- Schema Markup: {"Found (" + ", ".join(schema_types[:3]) + ")" if has_jsonld else "Not found"}
- Mobile Viewport Tag: {"Present" if has_viewport else "Missing"}
- Internal Links: {len(internal_links)}, External Links: {len(external_links)}

Only state facts consistent with this data — do not invent numbers."""
    ai_summary = ai_call(summary_prompt, max_tokens=400)

    # ---- AI recommendations (priority fixes) ----
    rec_prompt = f"""You are a Technical SEO expert. Based on the real issues found for {target_url} ({category} business in {country}):
{chr(10).join(['- '+d for d in deductions]) if deductions else '- No major issues found'}

Give a prioritized action plan: list the TOP 5 fixes in order of impact, each with 1-2 sentence explanation of HOW to fix it specifically. Number them 1-5. Be concise and actionable. Do not invent issues not listed above."""
    ai_recommendations = ai_call(rec_prompt, max_tokens=600)

    # Build rows
    rows_broken = "".join([f'<div class="url-item"><span class="url-text">{l}</span><span class="status-404">❌ {s}</span></div>' for l,s in broken]) or "<p style='color:#27ae60'>✅ No broken links found in sample check.</p>"
    rows_redirect = "".join([f'<div class="url-item"><span class="url-text">{l}</span><span class="status-301">↪️ {s}</span></div>' for l,s in redirected]) or "<p style='color:#27ae60'>✅ No redirect chains found.</p>"
    rows_alt = "".join([f'<div class="url-item"><span class="url-text">{a}</span><span class="status-404">❌ No Alt</span></div>' for a in missing_alt[:10]]) or "<p style='color:#27ae60'>✅ All sampled images have alt tags.</p>"
    rows_internal = "".join([f'<div class="url-item"><span class="url-text">{l}</span><span class="status-200">Internal</span></div>' for l in internal_links[:10]]) or "<p>No internal links found.</p>"

    schema_html = f"✅ Schema markup found: <strong>{', '.join(schema_types[:6])}</strong>" if has_jsonld else "❌ No structured data (JSON-LD schema) found on this page."

    ai_summary_display = ai_summary.replace('<','&lt;').replace('>','&gt;')
    ai_rec_display = ai_recommendations.replace('<','&lt;').replace('>','&gt;')

    return make_response(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Technical SEO Report</title>{get_style()}</head>
<body><div class="container">
    {logo_html()}
    <div class="step-badge">🔵 Technical SEO — Full Site Report</div>
    <h2>📊 Complete Technical Audit</h2>
    <div class="info-bar"><span>🌐 {target_url}</span><span>📂 {category}</span><span>🌍 {country}</span></div>

    <div style="text-align:center;margin-bottom:25px">
        <div class="score-circle" style="background:{score_color}">{score}</div>
        <strong style="font-size:16px;color:#2c3e50">Overall Technical SEO Score: {score}/100</strong>
    </div>

    <div class="result-card"><div class="result-card-head">📝 Executive Summary</div>
    <div class="result-card-body">{ai_summary_display}</div></div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL / HTTPS</div></div>
        <div class="stat-box"><div class="stat-num">{page_size_kb:.0f} KB</div><div class="stat-label">Page Size</div></div>
        <div class="stat-box"><div class="stat-num">{len(images)}</div><div class="stat-label">Total Images</div></div>
        <div class="stat-box"><div class="stat-num">{len(internal_links)}</div><div class="stat-label">Internal Links</div></div>
        <div class="stat-box"><div class="stat-num">{len(external_links)}</div><div class="stat-label">External Links</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_viewport else "red"}">{"✅" if has_viewport else "❌"}</div><div class="stat-label">Mobile Viewport</div></div>
    </div>

    <!-- SITE AUDIT -->
    <div class="result-card"><div class="result-card-head">🔍 Site Audit</div>
    <div class="result-card-body">
        <strong>Meta Title:</strong> {meta.get('title') or '❌ Missing'} {f"({len(meta.get('title',''))} chars)" if meta.get('title') else ""}<br>
        <strong>Meta Description:</strong> {meta.get('description') or '❌ Missing'} {f"({len(meta.get('description',''))} chars)" if meta.get('description') else ""}<br>
        <strong>H1 Tags Found:</strong> {meta.get('h1_count',0)} {"✅" if meta.get('h1_count')==1 else "⚠️ Should be exactly 1"} {f"— '{meta.get('h1_text')}'" if meta.get('h1_text') else ""}<br>
        <strong>Canonical Tag:</strong> {meta.get('canonical') or '❌ Not set'}<br><br>
        <strong>🔗 Broken Links (sample of {len(sample_links)} internal links checked):</strong>
    </div></div>
    <div class="result-card"><div class="result-card-head {"red" if broken else "green"}">❌ Broken Links Found: {len(broken)}</div>
    <div class="result-card-body">{rows_broken}</div></div>
    <div class="result-card"><div class="result-card-head {"orange" if redirected else "green"}">↪️ Redirects Found: {len(redirected)}</div>
    <div class="result-card-body">{rows_redirect}</div></div>

    <!-- INDEXING -->
    <div class="result-card"><div class="result-card-head">🤖 Indexing & Crawlability</div>
    <div class="result-card-body">
        <strong>Robots.txt:</strong> {"✅ Found at " + robots_url if robots_found else "❌ Not found"}<br>
        {f"<strong>⚠️ CRITICAL:</strong> robots.txt may be blocking your entire site!<br>" if robots_blocks_all else ""}
        <strong>Sitemap listed in robots.txt:</strong> {"✅ Yes" if sitemap_in_robots else "⚠️ No"}<br>
        <strong>XML Sitemap:</strong> {"✅ Found at " + sitemap_url + f" ({sitemap_url_count} URLs)" if sitemap_found else "❌ Not found at " + sitemap_url}<br>
        <strong>Homepage Indexing:</strong> {"❌ NOINDEX is set — your homepage won't appear in Google!" if is_noindex_home else "✅ Indexable (no noindex tag)"}<br>
        <strong>Robots Meta Tag:</strong> {meta.get('robots') or 'Not set (default: index, follow)'}
    </div></div>

    <!-- INTERNAL LINKS -->
    <div class="result-card"><div class="result-card-head">🔗 Internal Link Structure</div>
    <div class="result-card-body">
        Found <strong>{len(internal_links)}</strong> internal links and <strong>{len(external_links)}</strong> external links on the homepage.<br>
        {"<strong>⚠️ Generic anchor texts found:</strong> " + ", ".join(generic_anchors) + " — replace with descriptive keyword-rich text." if generic_anchors else "✅ No generic 'click here' style anchors found."}
        <br><br>{rows_internal}
    </div></div>

    <!-- SCHEMA -->
    <div class="result-card"><div class="result-card-head">📊 Schema Markup</div>
    <div class="result-card-body">{schema_html}<br><br>
    {"💡 Recommended: Add LocalBusiness, FAQ, and Breadcrumb schema for " + category + " websites to enable rich results in Google." if not has_jsonld else "💡 Consider adding additional schema types (FAQ, Breadcrumb, Review) for more rich result opportunities."}
    </div></div>

    <!-- MOBILE -->
    <div class="result-card"><div class="result-card-head">📱 Mobile SEO</div>
    <div class="result-card-body">
        <strong>Viewport Meta Tag:</strong> {"✅ Present — site is configured for mobile" if has_viewport else "❌ Missing — site may not display correctly on mobile devices. Add: &lt;meta name='viewport' content='width=device-width, initial-scale=1'&gt;"}
    </div></div>

    <!-- SECURITY -->
    <div class="result-card"><div class="result-card-head">🔒 Security SEO</div>
    <div class="result-card-body">
        <strong>HTTPS/SSL:</strong> {"✅ Active" if has_ssl else "❌ Not Active — install SSL certificate immediately, this is a major ranking factor"}<br>
        <strong>Mixed Content:</strong> {"⚠️ Found HTTP resources on HTTPS page" if mixed_content else "✅ No mixed content detected"}<br>
        <strong>HSTS Header:</strong> {"✅ Present" if has_hsts else "⚠️ Not set — recommended for HTTPS sites"}
    </div></div>

    <!-- SOCIAL / OG -->
    <div class="result-card"><div class="result-card-head">📢 Open Graph & Social Tags</div>
    <div class="result-card-body">
        <strong>og:title:</strong> {"✅ Present" if og_title else "❌ Missing"}<br>
        <strong>og:image:</strong> {"✅ Present" if og_image else "❌ Missing"}<br>
        <strong>Twitter Card:</strong> {"✅ Present" if twitter_card else "❌ Missing"}<br>
        {f"💡 Add Open Graph tags so your {category} pages look good when shared on social media." if not (og_title and og_image) else ""}
    </div></div>

    <!-- IMAGE SEO -->
    <div class="result-card"><div class="result-card-head {"red" if missing_alt else "green"}">🖼️ Image SEO — {len(missing_alt)}/{len(images)} Missing Alt Tags</div>
    <div class="result-card-body">{rows_alt}</div></div>

    <!-- PRIORITY RECOMMENDATIONS -->
    <div class="result-card"><div class="result-card-head orange">🎯 Top Priority Fixes (AI Recommended)</div>
    <div class="result-card-body">{ai_rec_display}</div></div>

    <div class="note-box">⚠️ <strong>Note:</strong> This audit checks your homepage and a sample of internal links. Page Speed (Core Web Vitals) requires Google PageSpeed Insights for precise lab data — for full coverage, also run your site through Google Search Console.</div>

    <div class="buttons">
        <a href="/" class="btn btn-purple">🔄 New Audit</a>
        <a href="javascript:history.back()" class="btn btn-gray">← Back</a>
    </div>
</div></body></html>""")

# ═══════════════════════════════════════════════════════════════
# OFF-PAGE SEO — FULL AUTOMATIC REPORT (Backlinks + Opportunities + Competitors)
# ═══════════════════════════════════════════════════════════════
def offpage_full_report(category, website, country, language):
    html_content, status_code, final_url = fetch_html(website)
    target_url = final_url if final_url else website

    if not html_content:
        return make_response(f"""<!DOCTYPE html><html><head><meta charset="UTF-8">{get_style()}</head><body><div class="container">{logo_html()}
        <div class="red-badge">🔴 Off-Page SEO</div><h2>❌ Could Not Fetch Website</h2>
        <div class="result-card"><div class="result-card-head red">⚠️ Error</div>
        <div class="result-card-body">Could not connect to <strong>{website}</strong>. Please check the URL and try again from Home.</div></div>
        <div class="buttons"><a href="/" class="btn btn-gray">🏠 Home</a></div>
        </div></body></html>""")

    domain = urlparse(target_url).netloc
    meta = get_meta(html_content)
    external_links = get_external_links(html_content, target_url)
    ext_domains = list(set([urlparse(l).netloc for l in external_links]))
    has_ssl = check_ssl(target_url)

    # Categorize external domains (social vs other)
    social_platforms = ['facebook.com','twitter.com','x.com','instagram.com','linkedin.com','youtube.com','tiktok.com','pinterest.com','whatsapp.com']
    social_links = [d for d in ext_domains if any(sp in d for sp in social_platforms)]
    other_links = [d for d in ext_domains if d not in social_links]

    # ── SECTION 1: Outbound Link Profile (real data) ──
    rows_social = "".join([f'<div class="url-item"><span class="url-text">{d}</span><span class="badge badge-blue">Social Profile</span></div>' for d in social_links]) or "<p>No social media links found on homepage.</p>"
    rows_other = "".join([f'<div class="url-item"><span class="url-text">{d}</span><span class="badge badge-easy">External Reference</span></div>' for d in other_links[:15]]) or "<p>No other external domains found on homepage.</p>"

    # ── SECTION 2: AI Backlink Opportunities (niche-specific) ──
    backlink_prompt = f"""You are an Off-Page SEO expert. For a {category} business in {country} (website: {domain}):

Provide 12 REAL, well-known, currently-active platforms where this business could realistically get backlinks, specific to the {category} niche and {country} market. For each, give:
PLATFORM: name
TYPE: (Directory/Guest Post/Profile/Forum/Press)
WHY: one sentence why it's relevant for {category} in {country}

Use real platform names (e.g. industry directories, local business listings relevant to {country}, niche forums, guest posting sites). Format strictly as:
PLATFORM: ...
TYPE: ...
WHY: ...
(repeat 12 times, nothing else)"""
    backlink_result = ai_call(backlink_prompt, max_tokens=900)

    platforms, ptypes, whys = [], [], []
    for line in backlink_result.strip().split('\n'):
        l = line.strip()
        if l.upper().startswith('PLATFORM:'):
            platforms.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('TYPE:'):
            ptypes.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('WHY:'):
            whys.append(l.split(':',1)[-1].strip())

    rows_opportunities = ""
    for i in range(min(len(platforms), len(ptypes), len(whys))):
        rows_opportunities += f"""<tr>
            <td><strong>{platforms[i]}</strong></td>
            <td><span class="badge badge-blue">{ptypes[i]}</span></td>
            <td style="font-size:13px">{whys[i]}</td>
        </tr>"""
    if not rows_opportunities:
        rows_opportunities = "<tr><td colspan='3' style='text-align:center;padding:20px;color:#e74c3c'>Could not generate suggestions, please try again.</td></tr>"

    # ── SECTION 3: Competitor Discovery (AI based on real meta data) ──
    competitor_prompt = f"""You are an SEO market research expert. A business operates in the "{category}" category, targeting "{country}", with website {domain}. Their homepage title is: "{meta.get('title','N/A')}" and meta description: "{meta.get('description','N/A')}".

Identify 3 REAL, well-known competitor websites/companies that operate in this same niche and target market ({country}). For each competitor give:
NAME: Company/website name
URL: their website domain (real, well-known)
STRENGTH: 1-2 sentences on what makes them strong competitors (their SEO/content/backlink strategy strengths)

Format strictly:
NAME: ...
URL: ...
STRENGTH: ...
(repeat 3 times, nothing else). Only name real, currently operating companies/websites."""
    competitor_result = ai_call(competitor_prompt, max_tokens=600)

    comp_names, comp_urls, comp_strengths = [], [], []
    for line in competitor_result.strip().split('\n'):
        l = line.strip()
        if l.upper().startswith('NAME:'): comp_names.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('URL:'): comp_urls.append(l.split(':',1)[-1].strip())
        elif l.upper().startswith('STRENGTH:'): comp_strengths.append(l.split(':',1)[-1].strip())

    competitor_cards = ""
    for i in range(min(len(comp_names), len(comp_urls), len(comp_strengths))):
        competitor_cards += f"""<div class="result-card"><div class="result-card-head red">🏆 {comp_names[i]}</div>
        <div class="result-card-body"><strong>🌐 {comp_urls[i]}</strong><br><br>{comp_strengths[i]}</div></div>"""
    if not competitor_cards:
        competitor_cards = "<p style='color:#e74c3c;padding:15px'>Could not identify competitors, please try again.</p>"

    # ── SECTION 4: Off-Page Strategy Summary ──
    strategy_prompt = f"""Off-Page SEO expert. For a {category} business ({domain}) in {country}:
This website has {len(external_links)} outbound links, {len(social_links)} social profile links ({', '.join(social_links) if social_links else 'none'}).
SSL: {"Yes" if has_ssl else "No"}

Write a 5-6 sentence off-page SEO strategy summary for this business — current social presence assessment, link building priorities for the next 90 days, and what type of content would attract the most backlinks in the {category} niche."""
    strategy_result = ai_call(strategy_prompt, max_tokens=500)
    strategy_display = strategy_result.replace('<','&lt;').replace('>','&gt;')

    return make_response(f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Off-Page SEO Report</title>{get_style()}</head>
<body><div class="container">
    {logo_html()}
    <div class="red-badge">🔴 Off-Page SEO — Full Report</div>
    <h2>🔗 Backlink & Off-Page Analysis</h2>
    <div class="info-bar"><span>🌐 {target_url}</span><span>📂 {category}</span><span>🌍 {country}</span></div>

    <div class="stat-grid">
        <div class="stat-box"><div class="stat-num">{len(external_links)}</div><div class="stat-label">Outbound Links Found</div></div>
        <div class="stat-box"><div class="stat-num">{len(ext_domains)}</div><div class="stat-label">Unique External Domains</div></div>
        <div class="stat-box"><div class="stat-num">{len(social_links)}</div><div class="stat-label">Social Profiles Linked</div></div>
        <div class="stat-box"><div class="stat-num {"green" if has_ssl else "red"}">{"✅" if has_ssl else "❌"}</div><div class="stat-label">SSL Active</div></div>
    </div>

    <div class="result-card"><div class="result-card-head red">📋 Off-Page Strategy Summary</div>
    <div class="result-card-body">{strategy_display}</div></div>

    <!-- SOCIAL PROFILES -->
    <div class="result-card"><div class="result-card-head">📱 Social Media Profiles Found on Website</div>
    <div class="result-card-body">{rows_social}</div></div>

    <!-- OTHER OUTBOUND LINKS -->
    <div class="result-card"><div class="result-card-head">🌐 Other External Links Found</div>
    <div class="result-card-body">{rows_other}</div></div>

    <!-- BACKLINK OPPORTUNITIES -->
    <h2 style="margin-top:10px">🎯 Backlink Opportunities for {category}</h2>
    <p style="color:#95a5a6;margin-bottom:15px;font-size:13px">AI-curated platforms relevant to your niche and target country where you can build quality backlinks:</p>
    <table><thead><tr><th>Platform</th><th>Type</th><th>Why It's Relevant</th></tr></thead>
    <tbody>{rows_opportunities}</tbody></table>

    <!-- COMPETITORS -->
    <h2 style="margin-top:30px">🏆 Top Competitors in Your Niche</h2>
    <p style="color:#95a5a6;margin-bottom:15px;font-size:13px">Based on your category ({category}) and target market ({country}):</p>
    {competitor_cards}

    <div class="note-box">⚠️ <strong>Note:</strong> Outbound link data above is extracted directly from your homepage HTML (100% real). Backlink opportunities and competitor suggestions are AI-curated based on your niche and market — for live backlink/competitor data with exact numbers, pair this with tools like Ahrefs, SEMrush, or Moz.</div>

    <div class="buttons">
        <a href="/" class="btn btn-purple">🔄 New Report</a>
        <a href="javascript:history.back()" class="btn btn-gray">← Back</a>
    </div>
</div></body></html>""")

# ═══════════════════════════════════════════════
# DOWNLOAD
# ═══════════════════════════════════════════════
@app.route("/download-file")
def download_file():
    content=unquote(request.args.get("content",""))
    filename=request.args.get("filename","article.txt")
    return Response(content,mimetype="text/plain",headers={"Content-Disposition":f"attachment; filename={filename}"})

if __name__ == "__main__":
    app.run(debug=True)

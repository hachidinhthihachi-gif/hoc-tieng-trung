"""
Lặp Từ Vựng Tiếng Trung - chạy bằng Python, không tốn token Claude.

Cài 1 lần:   pip install pypinyin jieba
Chạy:        python vocab_app.py
Rồi mở:      http://localhost:8000   (Chrome hoặc Edge)
Dùng trên điện thoại cùng Wi-Fi:  python vocab_app.py --lan   (rồi mở http://<IP máy tính>:8000)
"""
import argparse
import json
import os
import re
import socket
import urllib.request
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import jieba
from pypinyin import Style, pinyin

from pathlib import Path

try:  # chietu.json nằm cùng thư mục với file này
    CHIETU = json.loads(Path(__file__).with_name("chietu.json").read_text(encoding="utf-8"))
except Exception:
    CHIETU = {}
CJK = re.compile(r"[\u4e00-\u9fff]")
_cache = {}


last_error = ""


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def tr(text, src, dst):
    """Dịch: thử Google (gtx) trước, lỗi thì thử MyMemory. Có nhớ kết quả."""
    global last_error
    key = (text, src, dst)
    if key in _cache:
        return _cache[key]
    q = quote(text)
    out = ""
    try:
        d = _get_json(f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={dst}&dt=t&q={q}")
        out = "".join(part[0] for part in d[0] if part[0]).strip()
    except Exception as e:
        last_error = f"Google: {e}"
        print("  ! Lỗi dịch (Google):", e)
    if not out:
        try:
            d = _get_json(f"https://api.mymemory.translated.net/get?q={q}&langpair={src}|{dst}")
            out = (d.get("responseData", {}).get("translatedText") or "").strip()
        except Exception as e:
            last_error = f"MyMemory: {e}"
            print("  ! Lỗi dịch (MyMemory):", e)
    if out:
        _cache[key] = out
    return out


def py(text):
    return " ".join(s[0] for s in pinyin(text, style=Style.TONE))


def lookup(q):
    """Gõ hán tự -> pinyin + nghĩa Việt. Gõ tiếng Việt -> ra hán tự tương ứng."""
    if CJK.search(q):
        hanzi, meaning = q, tr(q, "zh-CN", "vi")
    else:
        hanzi, meaning = tr(q, "vi", "zh-CN"), q
    r = {"hanzi": hanzi, "pinyin": py(hanzi), "meaning": meaning, "icon": "📌"}
    r["breakdown"] = [dict(char=c, **CHIETU[c]) for c in dict.fromkeys(hanzi) if c in CHIETU]
    if not meaning or not hanzi:
        r["error"] = last_error or "Không dịch được"
    return r


def translate(text):
    """Câu Việt <-> Trung + pinyin + bảng từ vựng (tách từ bằng jieba)."""
    if CJK.search(text):
        zh, vi = text, tr(text, "zh-CN", "vi")
    else:
        vi, zh = text, tr(text, "vi", "zh-CN")
    seen, words = set(), []
    for w in jieba.cut(zh):
        if CJK.search(w) and w not in seen:
            seen.add(w)
            words.append(w)
    with ThreadPoolExecutor(8) as ex:
        meanings = list(ex.map(lambda w: tr(w, "zh-CN", "vi"), words))
    return {
        "error": "" if (zh and vi) else (last_error or "Không dịch được"),
        "chinese": zh, "pinyin": py(zh), "vietnamese": vi,
        "words": [{"hanzi": w, "pinyin": py(w), "meaning": m or "?"} for w, m in zip(words, meanings)],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query).get("q", [""])[0].strip()
        if u.path == "/":
            self._send(PAGE, "text/html")
        elif u.path == "/api/lookup" and q:
            self._send(json.dumps(lookup(q), ensure_ascii=False), "application/json")
        elif u.path == "/api/translate" and q:
            self._send(json.dumps(translate(q), ensure_ascii=False), "application/json")
        else:
            self.send_error(404)

    def log_message(self, *a):  # tắt log rối mắt
        pass


PAGE = r"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Lặp Từ Vựng Tiếng Trung</title>
<style>
:root{--bg:#faf9f7;--card:#fff;--ink:#1c1a17;--sub:#6b6560;--accent:#b91c1c;--accent-ink:#fff;--line:#e8e4de}
@media (prefers-color-scheme:dark){:root{--bg:#17140f;--card:#211d17;--ink:#f3efe8;--sub:#a39c92;--accent:#f0655a;--accent-ink:#1a1310;--line:#332c22}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;justify-content:center;padding:32px 16px}
.wrap{width:100%;max-width:480px}
h1{font-size:1.3rem;margin:0 0 6px}
p.desc{color:var(--sub);margin:0 0 28px;font-size:.95rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px;margin-bottom:16px}
label{display:block;font-size:.85rem;color:var(--sub);margin-bottom:6px;font-weight:600}
input[type=text],textarea{width:100%;padding:14px 16px;font-size:1.4rem;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);margin-bottom:12px;font-family:inherit}
textarea{font-size:1.05rem;padding:12px 14px;resize:vertical;margin-bottom:0}
input:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
#meaningBox{display:none;margin:0 0 18px;padding:12px 14px;border-radius:10px;background:var(--bg);border:1px solid var(--line)}
#pinyin{font-family:monospace;color:var(--accent);font-size:1.1rem}
.row{display:flex;gap:16px;margin-bottom:18px}.field{flex:1}
select,input[type=number]{width:100%;padding:10px 12px;font-size:1rem;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink)}
.reps{display:flex;align-items:center;gap:10px}
.reps button{width:38px;height:38px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:1.1rem;cursor:pointer}
.reps input{text-align:center;width:60px}
.playbar{display:flex;gap:10px;margin-top:22px}
button.main{flex:1;padding:14px;font-size:1.05rem;font-weight:700;border:none;border-radius:10px;background:var(--accent);color:var(--accent-ink);cursor:pointer}
button.main:disabled{opacity:.5}
button.stop{padding:14px 18px;font-size:1rem;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.status{margin-top:16px;text-align:center;color:var(--sub);font-size:.9rem;min-height:1.2em}
.count{font-size:2rem;font-weight:800;text-align:center;margin-top:6px;color:var(--accent)}
.hint{font-size:.8rem;color:var(--sub);margin:20px 0;line-height:1.5}
.comp-row{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.comp-chip{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:10px;background:var(--bg);border:1px solid var(--line);min-width:110px;flex:1}
.cchar{font-size:1.5rem;color:var(--accent);font-weight:800;line-height:1}
.cinfo{font-size:.75rem;color:var(--sub);line-height:1.35}.cinfo b{color:var(--ink);font-size:.85rem}
.story-box{padding:10px 12px;border-radius:10px;background:var(--bg);border-left:3px solid var(--accent);font-size:.92rem;line-height:1.65}
.hz{color:var(--accent);font-weight:800}
.decomp+.decomp{margin-top:14px;padding-top:12px;border-top:1px dashed var(--line)}
.vocab-row{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}
.vocab-row:last-child{border-bottom:none}
.vocab-play{flex-shrink:0;width:38px;height:38px;border-radius:50%;border:1px solid var(--line);background:var(--bg);color:var(--accent);font-size:1.05rem;cursor:pointer}
.vocab-info b{font-size:1.1rem}
.vpinyin{color:var(--accent);font-family:monospace;margin-left:6px;font-size:.9rem}
.vmeaning{color:var(--sub);font-size:.85rem;margin-top:2px}
.quiz-opt{padding:12px 14px;border-radius:10px;border:1px solid var(--line);background:var(--bg);color:var(--ink);font-size:1rem;text-align:left;cursor:pointer}
.quiz-opt.correct{background:#dcfce7;border-color:#22c55e;color:#14532d}
.quiz-opt.wrong{background:#fee2e2;border-color:#ef4444;color:#7f1d1d}
</style></head>
<body><div class="wrap">
<h1>🔁 Lặp Từ Vựng Tiếng Trung</h1>
<p class="desc">Gõ hán tự (hoặc tiếng Việt), tự động hiện pinyin + nghĩa tiếng Việt, bấm Phát để nghe lặp lại liên tục.</p>

<div class="card">
  <label for="word">Hán tự / cụm từ</label>
  <input type="text" id="word" placeholder="ví dụ: 你好" autocomplete="off">
  <div id="meaningBox"><div style="display:flex;align-items:center;gap:10px">
    <div id="icon" style="font-size:2rem;line-height:1"></div>
    <div style="flex:1"><div id="pinyin"></div><div id="meaning" style="margin-top:4px"></div></div></div>
    <div id="breakdown" style="margin-top:8px;padding-top:8px;border-top:1px dashed var(--line)"></div></div>
  <div class="row">
    <div class="field"><label for="voice">Giọng đọc</label><select id="voice"></select></div>
    <div class="field"><label for="rate">Tốc độ</label>
      <select id="rate"><option value="0.6">Chậm</option><option value="0.8">Hơi chậm</option>
      <option value="1" selected>Bình thường</option><option value="1.2">Nhanh</option></select></div>
  </div>
  <label>Số lần lặp</label>
  <div class="reps"><button id="dec" type="button">−</button>
    <input type="number" id="reps" value="10" min="1" max="50"><button id="inc" type="button">+</button></div>
  <div class="playbar"><button class="main" id="play">▶️ Phát</button><button class="stop" id="stop">⏹ Dừng</button></div>
  <div class="count" id="count"></div><div class="status" id="status">Sẵn sàng</div>
</div>
<p class="hint">Mẹo: chọn giọng đọc có "zh" (tiếng Trung) trong mục "Giọng đọc" để phát âm đúng.</p>

<div class="card">
  <label for="sentence">📝 Dịch câu (Việt ⇄ Trung) + bảng từ vựng</label>
  <textarea id="sentence" rows="2" placeholder="Nhập câu tiếng Việt hoặc tiếng Trung..."></textarea>
  <button class="main" id="translateBtn" type="button" style="margin-top:10px;width:100%">Dịch</button>
  <div id="translateResult" style="display:none;margin-top:16px">
    <div id="tSentence" style="font-size:1.2rem;font-weight:700"></div>
    <div id="tPinyin" style="color:var(--accent);font-family:monospace;margin-bottom:6px"></div>
    <div id="tVn" style="color:var(--sub);margin-bottom:12px"></div>
    <div id="vocabTable"></div>
  </div>
</div>

<div class="card" id="quizCard" style="display:none">
  <label style="margin-bottom:14px">🎯 Kiểm tra từ đã học</label>
  <div id="quizIntro" style="font-size:.9rem;color:var(--sub);margin-bottom:14px"></div>
  <button class="main" id="quizStart" type="button" style="width:100%">Bắt đầu kiểm tra</button>
  <div id="quizBody" style="display:none">
    <div style="text-align:center;margin:6px 0 4px;font-size:2rem;font-weight:800" id="qMain"></div>
    <div style="text-align:center;color:var(--sub);font-family:monospace;margin-bottom:16px" id="qSub"></div>
    <div id="qOpts" style="display:flex;flex-direction:column;gap:10px"></div>
    <div id="qFb" style="margin-top:14px;text-align:center;font-weight:700;min-height:1.4em"></div>
    <button class="main" id="qNext" type="button" style="width:100%;margin-top:14px;display:none">Từ tiếp theo ▶️</button>
  </div>
</div>
</div>

<script>
const $ = id => document.getElementById(id);
const wordEl=$('word'), voiceEl=$('voice'), rateEl=$('rate'), repsEl=$('reps'), playBtn=$('play'), statusEl=$('status'), countEl=$('count');
let voices=[], playing=false, stopRequested=false;

// ---- Giọng đọc + lặp ----
function loadVoices(){
  const all = speechSynthesis.getVoices();
  voices = all.filter(v => v.lang.toLowerCase().startsWith('zh'));
  if(!voices.length) voices = all;
  voiceEl.innerHTML = '';
  voices.forEach((v,i) => { const o=document.createElement('option'); o.value=i; o.textContent=v.name+' ('+v.lang+')'; voiceEl.appendChild(o); });
}
loadVoices();
if('onvoiceschanged' in speechSynthesis) speechSynthesis.onvoiceschanged = loadVoices;
$('dec').onclick = () => repsEl.value = Math.max(1,(+repsEl.value||1)-1);
$('inc').onclick = () => repsEl.value = Math.min(50,(+repsEl.value||1)+1);

function speakOnce(text, voice, rate){
  return new Promise(res => {
    const u = new SpeechSynthesisUtterance(text);
    if(voice) u.voice = voice;
    u.lang='zh-CN'; u.rate=rate; u.onend=res; u.onerror=res;
    speechSynthesis.speak(u);
  });
}
const say = t => { speechSynthesis.cancel(); speakOnce(t, voices[+voiceEl.value]||null, +rateEl.value||1); };

async function playLoop(){
  const text = wordEl.value.trim();
  if(!text){ statusEl.textContent='Vui lòng nhập hán tự hoặc cụm từ.'; return; }
  const total = Math.min(50, Math.max(1, +repsEl.value||1));
  const speakText = /[\u4e00-\u9fff]/.test(text) ? text : (current && current.hanzi) || text;
  playing=true; stopRequested=false; playBtn.disabled=true; statusEl.textContent='Đang phát...';
  for(let i=1;i<=total;i++){
    if(stopRequested) break;
    countEl.textContent = i+' / '+total;
    await speakOnce(speakText, voices[+voiceEl.value]||null, +rateEl.value||1);
    await new Promise(r => setTimeout(r,350));
  }
  playing=false; playBtn.disabled=false;
  statusEl.textContent = stopRequested ? 'Đã dừng.' : 'Hoàn tất!';
}
playBtn.onclick = () => { if(playing) return; speechSynthesis.cancel(); playLoop(); };
$('stop').onclick = () => { stopRequested=true; speechSynthesis.cancel(); playing=false; playBtn.disabled=false; statusEl.textContent='Đã dừng.'; };
wordEl.addEventListener('keydown', e => { if(e.key==='Enter') playBtn.click(); });

// ---- Danh sách từ đã học (lưu trong trình duyệt) ----
let learned = [];
try{ learned = JSON.parse(localStorage.getItem('learned')||'[]'); }catch(e){}
function addLearned(hanzi, py, meaning){
  if(!hanzi || !meaning || meaning==='?' || learned.some(w => w.hanzi===hanzi)) return;
  learned.push({hanzi, pinyin:py, meaning, icon:'📌'});
  if(learned.length>60) learned.shift();
  try{ localStorage.setItem('learned', JSON.stringify(learned)); }catch(e){}
  refreshQuizIntro();
}
function refreshQuizIntro(){
  if(!learned.length) return;
  $('quizCard').style.display='block';
  $('quizIntro').textContent = 'Đã học '+learned.length+' từ. Bấm bắt đầu để tự kiểm tra.';
}
refreshQuizIntro();

// ---- Tra pinyin + nghĩa khi gõ ----
let timer=null, lastQ='', current=null;
wordEl.addEventListener('input', () => {
  clearTimeout(timer);
  const text = wordEl.value.trim();
  if(!text){ $('meaningBox').style.display='none'; return; }
  timer = setTimeout(() => lookup(text), 600);
});
async function lookup(text){
  if(text===lastQ) return;
  lastQ = text;
  $('meaningBox').style.display='block'; $('pinyin').textContent=''; $('meaning').textContent='Đang tra...';
  try{
    const r = await (await fetch('/api/lookup?q='+encodeURIComponent(text))).json();
    if(text !== wordEl.value.trim()) return;
    current = r;
    $('pinyin').textContent = r.hanzi+'  '+r.pinyin;
    $('meaning').textContent = r.error ? '⚠️ Lỗi dịch: '+r.error : (r.meaning || '(không rõ nghĩa)');
    $('icon').textContent = r.icon;
    const bd = r.breakdown || [];
    const hl = t => (t||'').replace(/[\u4e00-\u9fff]/g, m => '<span class="hz">'+m+'</span>');
    $('breakdown').innerHTML = bd.length ? '<b>📖 Chiết tự:</b>'+bd.map(p =>
      '<div class="decomp">'+(bd.length>1?'<div style="font-weight:800;font-size:1.5rem">'+p.char+'</div>':'')+
      '<div class="comp-row">'+(p.components||[]).map(c => '<div class="comp-chip"><div class="cchar">'+c.comp+'</div><div class="cinfo">/'+c.pinyin+'/ '+c.hanviet+'<br><b>'+c.meaning+'</b></div></div>').join('')+'</div>'+
      (p.story?'<div class="story-box">'+hl(p.story)+'</div>':'')+'</div>').join('') : '';
    addLearned(r.hanzi, r.pinyin, r.meaning);
  }catch(e){ $('meaning').textContent='Không tra được nghĩa lúc này.'; }
}

// ---- Dịch câu + bảng từ vựng ----
let tWords=[];
async function doTranslate(){
  const text = $('sentence').value.trim(); if(!text) return;
  const btn=$('translateBtn'); btn.disabled=true; btn.textContent='Đang dịch...';
  $('translateResult').style.display='block';
  $('tSentence').textContent=''; $('tPinyin').textContent=''; $('tVn').textContent='';
  $('vocabTable').innerHTML='<div style="color:var(--sub);font-size:.9rem">Đang xử lý...</div>';
  try{
    const r = await (await fetch('/api/translate?q='+encodeURIComponent(text))).json();
    if(r.error){ $('tSentence').textContent='⚠️ Lỗi dịch: '+r.error; $('vocabTable').innerHTML=''; btn.disabled=false; btn.textContent='Dịch'; return; }
    $('tSentence').textContent = r.chinese; $('tPinyin').textContent = r.pinyin; $('tVn').textContent = '🇻🇳 '+r.vietnamese;
    tWords = r.words;
    $('vocabTable').innerHTML = tWords.map((w,i) =>
      '<div class="vocab-row"><button type="button" class="vocab-play" data-i="'+i+'">🔊</button>'+
      '<div class="vocab-info"><b>'+w.hanzi+'</b><span class="vpinyin">'+w.pinyin+'</span><div class="vmeaning">'+w.meaning+'</div></div></div>').join('');
    document.querySelectorAll('.vocab-play').forEach(b => b.onclick = () => say(tWords[+b.dataset.i].hanzi));
    tWords.forEach(w => addLearned(w.hanzi, w.pinyin, w.meaning));
  }catch(e){ $('tSentence').textContent='Không dịch được lúc này, thử lại nhé.'; $('vocabTable').innerHTML=''; }
  btn.disabled=false; btn.textContent='Dịch';
}
$('translateBtn').onclick = doTranslate;
$('sentence').addEventListener('keydown', e => { if(e.key==='Enter' && !e.shiftKey){ e.preventDefault(); doTranslate(); } });

// ---- Kiểm tra ----
const shuffle = a => { a=a.slice(); for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]];} return a; };
const pick = a => a[Math.floor(Math.random()*a.length)];
let lastType=null;
function render(opts, correct){
  $('qOpts').innerHTML='';
  opts.forEach(o => {
    const b=document.createElement('button'); b.className='quiz-opt'; b.type='button'; b.textContent=o;
    b.onclick = () => {
      document.querySelectorAll('#qOpts button').forEach(x => { x.disabled=true; if(x.textContent===correct) x.classList.add('correct'); });
      if(o===correct){ $('qFb').textContent='✅ Chính xác!'; $('qFb').style.color='#16a34a'; setTimeout(nextQ,900); }
      else { b.classList.add('wrong'); $('qFb').textContent='❌ Chưa đúng — đáp án là: '+correct; $('qFb').style.color='#dc2626'; $('qNext').style.display='block'; }
    };
    $('qOpts').appendChild(b);
  });
}
function nextQ(){
  if(learned.length<2){ $('quizBody').style.display='block'; $('qFb').textContent='Cần học ít nhất 2 từ để kiểm tra.'; return; }
  $('qFb').textContent=''; $('qNext').style.display='none'; $('quizBody').style.display='block'; $('quizStart').style.display='none';
  const t = pick(['zh2vi','vi2zh','pinyin','listen'].filter(x => x!==lastType)); lastType=t;
  const w = pick(learned), o = shuffle(learned.filter(x => x!==w)).slice(0,4);
  if(t==='zh2vi'){ $('qMain').textContent=w.icon+'  '+w.hanzi; $('qSub').textContent=w.pinyin; render(shuffle([w.meaning,...o.map(x=>x.meaning)]), w.meaning); }
  if(t==='vi2zh'){ const f=x=>x.hanzi+'  ('+x.pinyin+')'; $('qMain').textContent=w.icon+'  '+w.meaning; $('qSub').textContent='(chọn hán tự đúng)'; render(shuffle([f(w),...o.map(f)]), f(w)); }
  if(t==='pinyin'){ $('qMain').textContent=w.icon+'  '+w.hanzi; $('qSub').textContent='(chọn pinyin đúng)'; render(shuffle([...new Set([w.pinyin,...o.map(x=>x.pinyin)])]), w.pinyin); }
  if(t==='listen'){
    $('qMain').innerHTML='🔊 <button type="button" id="again" class="stop" style="font-size:.95rem">Nghe lại</button>';
    $('qSub').textContent='Nghe rồi chọn đúng hán tự';
    $('again').onclick = () => say(w.hanzi); setTimeout(() => say(w.hanzi), 200);
    const f=x=>x.icon+'  '+x.hanzi; render(shuffle([f(w),...o.map(f)]), f(w));
  }
}
$('quizStart').onclick = nextQ; $('qNext').onclick = nextQ;
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--lan", action="store_true", help="cho điện thoại cùng Wi-Fi truy cập")
    a = ap.parse_args()
    # Khi chạy trên hosting (Render...), dịch vụ đặt biến PORT -> mở cho mọi người truy cập
    host = "0.0.0.0" if (a.lan or "PORT" in os.environ) else "127.0.0.1"
    print(f"Mở trình duyệt: http://localhost:{a.port}")
    if a.lan:
        print(f"Điện thoại (cùng Wi-Fi): http://{socket.gethostbyname(socket.gethostname())}:{a.port}")
    print("Nhấn Ctrl+C để tắt.")
    ThreadingHTTPServer((host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()

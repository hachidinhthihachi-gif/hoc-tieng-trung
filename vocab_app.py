"""
Lặp Từ Vựng Tiếng Trung - chạy bằng Python, tích hợp Đoạn Đối Thoại 4-6 câu.
"""
import argparse
import json
import os
import random
import re
import socket
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import jieba
from pypinyin import Style, pinyin

try:  # chietu.json nằm cùng thư mục với file này
    CHIETU = json.loads(Path(__file__).with_name("chietu.json").read_text(encoding="utf-8"))
except Exception:
    CHIETU = {}

CJK = re.compile(r"[\u4e00-\u9fff]")
_cache = {}
last_error = ""

# Danh sách bài hội thoại mẫu dự phòng
SAMPLE_DIALOGUES = [
    {
        "topic": "Chào hỏi & Gặp gỡ",
        "lines": [
            {"speaker": "A", "zh": "你好！很高兴认识你。", "vi": "Xin chào! Rất vui được quen biết bạn."},
            {"speaker": "B", "zh": "你好！我也很高兴认识你。", "vi": "Chào bạn! Tôi cũng rất vui được quen biết bạn."},
            {"speaker": "A", "zh": "你今天忙吗？", "vi": "Hôm nay bạn có bận không?"},
            {"speaker": "B", "zh": "我不忙，你呢？", "vi": "Tôi không bận, còn bạn thì sao?"},
            {"speaker": "A", "zh": "我们一起去喝茶吧！", "vi": "Chúng ta cùng đi uống trà nhé!"},
            {"speaker": "B", "zh": "太好了，我们走吧！", "vi": "Tốt quá, chúng ta đi thôi!"}
        ]
    },
    {
        "topic": "Thời tiết & Sinh hoạt",
        "lines": [
            {"speaker": "A", "zh": "今天天气怎么样？", "vi": "Thời tiết hôm nay thế nào?"},
            {"speaker": "B", "zh": "今天天气很温和，不冷也不热。", "vi": "Thời tiết hôm nay rất ấm áp, không lạnh cũng không nóng."},
            {"speaker": "A", "zh": "太好了，我想出去拿东西。", "vi": "Tốt quá, tôi muốn ra ngoài lấy đồ."},
            {"speaker": "B", "zh": "你看，外面天很蓝。", "vi": "Bạn xem, bên ngoài trời rất xanh."},
            {"speaker": "A", "zh": "那我们现在就出发吧。", "vi": "Vậy bây giờ chúng ta xuất phát thôi."},
            {"speaker": "B", "zh": "好的，拿好钥匙。", "vi": "Được rồi, cầm chắc chìa khóa nhé."}
        ]
    }
]


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def tr(text, src, dst):
    """Dịch: thử Google (gtx) trước, lỗi thì thử MyMemory."""
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
    if not out:
        try:
            d = _get_json(f"https://api.mymemory.translated.net/get?q={q}&langpair={src}|{dst}")
            out = (d.get("responseData", {}).get("translatedText") or "").strip()
        except Exception as e:
            last_error = f"MyMemory: {e}"
    if out:
        _cache[key] = out
    return out


def py(text):
    return " ".join(s[0] for s in pinyin(text, style=Style.TONE))


def lookup(q):
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


def generate_dialogue(words_str=""):
    sample = random.choice(SAMPLE_DIALOGUES)
    res_lines = []
    for line in sample["lines"]:
        res_lines.append({
            "speaker": line["speaker"],
            "zh": line["zh"],
            "pinyin": py(line["zh"]),
            "vi": line["vi"]
        })
    return {"topic": sample["topic"], "dialogue": res_lines}


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
        elif u.path == "/api/dialogue":
            self._send(json.dumps(generate_dialogue(q), ensure_ascii=False), "application/json")
        else:
            self.send_error(404)

    def log_message(self, *a):
        pass


PAGE = """<!DOCTYPE html>
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

.dialogue-item{display:flex;gap:10px;margin-bottom:12px;align-items:flex-start}
.speaker-badge{background:var(--accent);color:var(--accent-ink);padding:4px 8px;border-radius:6px;font-weight:bold;font-size:.85rem}
.dialogue-content{flex:1;background:var(--bg);padding:10px;border-radius:8px;border:1px solid var(--line)}
.dialogue-zh{font-size:1.1rem;font-weight:600}
.dialogue-py{color:var(--accent);font-size:.85rem;font-family:monospace}
.dialogue-vi{color:var(--sub);font-size:.85rem;margin-top:2px}
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

<div class="card">
  <label>💬 Đoạn đối thoại mẫu (4–6 câu)</label>
  <div id="dialogueTopic" style="font-weight:700;margin-bottom:12px;color:var(--accent)">Chủ đề: Luyện tập</div>
  <div id="dialogueList"></div>
  <button class="main" id="genDialogueBtn" type="button" style="margin-top:12px;width:100%">🔄 Đổi đoạn đối thoại khác</button>
</div>

</div>

<script>
const $ = id => document.getElementById(id);
const wordEl=$('word'), voiceEl=$('voice'), rateEl=$('rate'), repsEl=$('reps'), playBtn=$('play'), statusEl=$('status'), countEl=$('count');
let voices=[], playing=false, stopRequested=false;

function loadVoices(){
  const all = speechSynthesis.getVoices();
  voices = all.filter(v => v.lang.toLowerCase().startsWith('zh'));
  if(!voices.length) voices = all;
  voiceEl.innerHTML = '';
  voices.forEach((v,i) => { const o=document.createElement('option'); o.value=i; o.textContent=v.name+' ('+v.lang+')'; voiceEl.appendChild(o); });
}
loadVoices();
if('onvoiceschanged' in speechSynthesis) speechSynthesis.onvoiceschanged = loadVoices;

function speakOnce(text, voice, rate){
  return new Promise(res => {
    const u = new SpeechSynthesisUtterance(text);
    if(voice) u.voice = voice;
    u.lang='zh-CN'; u.rate=rate; u.onend=res; u.onerror=res;
    speechSynthesis.speak(u);
  });
}
const say = t => { speechSynthesis.cancel(); speakOnce(t, voices[+voiceEl.value]||null, +rateEl.value||1); };

async function loadDialogue(){
  try{
    const r = await (await fetch('/api/dialogue')).json();
    $('dialogueTopic').textContent = 'Chủ đề: ' + r.topic;
    $('dialogueList').innerHTML = r.dialogue.map((item) => 
      '<div class="dialogue-item">'+
        '<span class="speaker-badge">'+item.speaker+'</span>'+
        '<div class="dialogue-content">'+
          '<div class="dialogue-zh">'+item.zh+' <button onclick="say(\''+item.zh.replace(/'/g, "\\'")+'\')" style="border:none;background:none;cursor:pointer">🔊</button></div>'+
          '<div class="dialogue-py">'+item.pinyin+'</div>'+
          '<div class="dialogue-vi">'+item.vi+'</div>'+
        '</div>'+
      '</div>'
    ).join('');
  }catch(e){
    $('dialogueList').textContent = 'Không thể tải hội thoại.';
  }
}
$('genDialogueBtn').onclick = loadDialogue;
loadDialogue();

</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    ap.add_argument("--lan", action="store_true", help="cho điện thoại cùng Wi-Fi truy cập")
    a = ap.parse_args()
    host = "0.0.0.0" if (a.lan or "PORT" in os.environ) else "127.0.0.1"
    print(f"Mở trình duyệt: http://localhost:{a.port}")
    ThreadingHTTPServer((host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
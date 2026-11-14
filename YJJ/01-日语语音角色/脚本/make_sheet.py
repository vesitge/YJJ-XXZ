# -*- coding: utf-8 -*-
"""生成校对表与训练清单：把「切分结果 + ASR 文本 + 环境筛选」合成一张可操作的网页。

好处：ASR 只跑一次，之后加什么筛选条件（环境、音量、时长、相似度）都只是重跑这个脚本，
     不用再等四十分钟转写。

用法：
    python tools/make_sheet.py            # 用默认路径
"""
import os, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "工作")
META = os.path.join(WORK, "meta.json")
ENVJ = os.path.join(WORK, "环境筛选.json")
SHEET = os.path.join(WORK, "校对表.html")
TRAIN = os.path.join(WORK, "train.list")

HTML = r"""<!doctype html><html lang="ja"><meta charset="utf-8">
<title>素材校对表</title>
<style>
:root{--bg:#0f1115;--fg:#e8e8e8;--dim:#8a8f98;--accent:#4da3ff;--warn:#ffb454;--bad:#ff6b6b;--ok:#4ade80;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 system-ui,"Microsoft YaHei",sans-serif}
header{position:sticky;top:0;z-index:9;background:#161a21;padding:10px 16px;border-bottom:1px solid #262b35;
  display:flex;gap:14px;align-items:center;flex-wrap:wrap}
header b{font-size:15px}
button{background:#232a35;color:var(--fg);border:1px solid #333c4a;border-radius:6px;padding:6px 12px;cursor:pointer}
button:hover{background:#2c3542}
button.primary{background:#1d4ed8;border-color:#2563eb}
table{width:100%;border-collapse:collapse}
td{padding:7px 9px;border-bottom:1px solid #1d222b;vertical-align:top}
tr:hover{background:#151a22}
tr.dropped{opacity:.42}
tr.dropped textarea{text-decoration:line-through}
.mono{color:var(--dim);font-family:ui-monospace,monospace;white-space:nowrap}
textarea{width:100%;background:#11151c;color:var(--fg);border:1px solid #2b3442;border-radius:5px;
  padding:5px 8px;font:14px/1.5 inherit;resize:vertical;min-height:32px}
textarea:focus{outline:none;border-color:var(--accent)}
textarea.changed{border-color:var(--warn)}
.tag{display:inline-block;font-size:11px;padding:1px 6px;border-radius:4px;margin-left:4px;white-space:nowrap}
.tag.ok{background:#12351f;color:var(--ok)}
.tag.warn{background:#3a2a10;color:var(--warn)}
.tag.bad{background:#3a1515;color:var(--bad)}
.tag.env{background:#1b2430;color:#7fb0e0}
.tag.neutral{background:#232a35;color:#9aa4b2}
label.keep{cursor:pointer;user-select:none}
</style>
<header>
  <b>素材校对表</b>
  <span id="stat" style="color:var(--dim)"></span>
  <span style="flex:1"></span>
  <label style="color:var(--dim)"><input type="checkbox" id="only"> 只看可疑</label>
  <label style="color:var(--dim)"><input type="checkbox" id="hideDrop"> 隐藏已剔除</label>
  <button onclick="revert()">全部恢复</button>
  <button class="primary" onclick="exportAll()">导出结果</button>
</header>
<table><thead><tr style="color:#8a8f98;font-size:12px;text-align:left">
  <th style="width:46px">保留</th><th style="width:64px">编号</th><th style="width:62px">时长</th>
  <th style="width:56px">试听</th><th style="width:190px">环境</th><th>日文文本</th>
</tr></thead><tbody id="tb"></tbody></table>
<script>
const DATA = __DATA__;
const edited = {};
const drop = {};
function suspect(d){ return (d.sim !== null && d.sim < 0.55) || d.env === '可疑'; }
function esc(s){ return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function render(){
  const only = document.getElementById('only').checked;
  const hideDrop = document.getElementById('hideDrop').checked;
  const tb = document.getElementById('tb');
  tb.innerHTML = '';
  DATA.forEach((d,i)=>{
    if (only && !suspect(d)) return;
    if (hideDrop && drop[i]) return;
    const st = d.sim === null ? ['neutral','台本对齐']
             : d.sim >= 0.75 ? ['ok','好']
             : d.sim >= 0.55 ? ['warn','存疑'] : ['bad','可疑'];
    const envCls = d.env === '可疑' ? 'bad' : d.env === '偏湿' ? 'warn' : 'ok';
    const tr = document.createElement('tr');
    if (drop[i]) tr.className='dropped';
    tr.innerHTML =
      `<td><input type="checkbox" class="keep" data-i="${i}" ${drop[i]?'':'checked'}></td>
       <td class="mono">${String(d.id).padStart(4,'0')}</td>
       <td class="mono">${d.dur.toFixed(2)}s</td>
       <td><button data-i="${i}">▶</button></td>
       <td><span class="tag env">${d.env||'—'}</span> <span style="color:#67707d">${d.decay_ms?Math.round(d.decay_ms)+'ms':''}</span></td>
       <td><textarea data-i="${i}" rows="1">${esc(d.text)}</textarea>
           <span class="tag ${st[0]}">${st[1]}${d.sim===null?'':' · '+(d.sim*100|0)+'%'}</span></td>`;
    tb.appendChild(tr);
  });
  tb.querySelectorAll('button[data-i]').forEach(b=>b.onclick=()=>play(+b.dataset.i));
  tb.querySelectorAll('textarea[data-i]').forEach(t=>{
    t.oninput=()=>{ edited[+t.dataset.i]=t.value; t.classList.add('changed'); stat(); };
  });
  tb.querySelectorAll('.keep').forEach(c=>{
    c.onchange=()=>{ drop[+c.dataset.i]=!c.checked; render(); };
  });
  stat();
}
function play(i){ const a=new Audio('片段/'+DATA[i].file); a.play(); }
function stat(){
  const n=Object.keys(edited).length;
  const d=DATA.filter((_,i)=>drop[i]).length;
  const s=DATA.filter(suspect).length;
  document.getElementById('stat').textContent =
    `共 ${DATA.length} 条 · 可疑 ${s} · 已剔除 ${d} · 已改 ${n}`;
}
function revert(){ for(const k in drop) delete drop[k]; for(const k in edited) delete edited[k]; render(); }
function exportAll(){
  const out = DATA.map((d,i)=>({
    ...d,
    text: edited[i]!==undefined ? edited[i] : d.text,
    keep: !drop[i]
  }));
  const blob=new Blob([JSON.stringify(out,null,1)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='校对结果.json'; a.click();
}
document.getElementById('only').onchange=render;
document.getElementById('hideDrop').onchange=render;
render();
</script></html>"""


def norm(s):
    import re, unicodedata
    s = unicodedata.normalize("NFKC", s or "")
    return re.sub(r"[\s、。,.!?！？…‥・「」『』（）()【】\-—ー~〜]", "", s)


def expand_text(meta):
    """决定每段该标多少文字。

    切分时相邻的短句会被并进同一段，所以「命中第 6 行」不代表这段只含第 6 行。
    做法：以该段命中的行结尾，往前试探「起点」，
    用 ASR 转写文字当裁判，取相似度最高的那个起点。
    """
    from difflib import SequenceMatcher
    if not meta or "_script" not in meta[0]:
        return {}
    script = meta[0]["_script"]
    out = {}
    prev = 0                      # 上一段已经用到第几行（1-based）
    for m in meta:
        j = m.get("script_line")
        if not j:
            continue
        end = j                    # 1-based，含
        asr = norm(m.get("asr", ""))
        best_span, best_sc = (end, end), -1.0
        for start in range(prev + 1, end + 1):
            cand = "".join(script[start - 1:end])
            sc = SequenceMatcher(None, asr, norm(cand)).ratio() if asr else 0.0
            if sc > best_sc + 1e-9:
                best_sc, best_span = sc, (start, end)
        s, e = best_span
        out[m["id"]] = "".join(script[s - 1:e])
        prev = e
    return out


def main():
    meta = json.load(open(META, encoding="utf-8")) if os.path.exists(META) else []
    env = {}
    median = None
    if os.path.exists(ENVJ):
        d = json.load(open(ENVJ, encoding="utf-8"))
        median = d.get("median_ms")
        for r in d["rows"]:
            env[r["file"]] = r

    rows = []
    kept = 0
    spans = expand_text(meta)
    for m in meta:
        e = env.get(m["file"], {})
        # 字段名在两条流水线里不一样：prep.py 用 final/asr，cut_by_lrc.py 用 text
        text = spans.get(m["id"]) or m.get("text") or m.get("final") or m.get("asr") or ""
        row = {
            "id": m["id"], "file": m["file"], "dur": m["dur"],
            "text": text,
            "sim": m.get("sim"),
            "env": e.get("flag", "未测"),
            "decay_ms": e.get("decay_ms"),
            "score": e.get("score"),
        }
        rows.append(row)
        if row["env"] != "可疑":
            kept += 1

    html = HTML.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
    open(SHEET, "w", encoding="utf-8").write(html)

    with open(TRAIN, "w", encoding="utf-8") as f:
        for r in rows:
            if r["env"] == "可疑":
                continue
            f.write("%s|speaker|ja|%s\n" % (os.path.join(WORK, "片段", r["file"]), r["text"]))

    print("校对表 → %s" % SHEET)
    print("训练清单 → %s（%d 行，已排除环境可疑）" % (TRAIN, sum(1 for r in rows if r["env"] != "可疑")))
    print("总片段 %d，环境可疑 %d，可用于训练 %d" % (len(rows), len(rows) - kept, kept))
    if median:
        print("混响基线：落尾 %.0f ms" % median)
    print("\n打开校对表后：")
    print("  · 环境列绿=干声，黄=偏湿，红=可疑（默认不勾保留）")
    print("  · 取消勾选 = 剔除这段，不进训练集")
    print("  · 改完点「导出结果」，再跑 tools/apply_sheet.py 落地")
    return 0


if __name__ == "__main__":
    sys.exit(main())

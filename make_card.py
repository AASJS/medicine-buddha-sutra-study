#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
药师经 · 圣为 · 正文篇 出卡脚本
================================

用法：
    python make_card.py            # 查看哪些卡可以出（文案齐全的）
    python make_card.py 01         # 出第 1 大愿卡（按 JSON 里的 no 字段）
    python make_card.py 01 02 03   # 批量出卡
    python make_card.py 01-1       # 出第 1 大愿第 1 张细分卡（支持子序，01-1 / 1-1 / 1 均可）

流程：
    1. 从 药师经/卡片数据.json 读取卡片文案
    2. 用内置模板生成 9:16 HTML（1080×1920 逻辑尺寸）
    3. 起 local http server + playwright-cli 以 2 倍像素密度截图
    4. 输出 cards/<序号>-<品名>.png（2160×3840 高清）

依赖：
    - playwright-cli（npm install -g @playwright/cli@latest，并安装浏览器）
      或本机已装 python playwright + chromium（自动回退）
    - 配图放 images/ 或 JSON 里给路径；图缺失时自动渲染"配图待放"占位框

移植自《地藏经》项目 AASJS/dizangjing-cards（make_card.py），仅替换数据源与系列名。
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import functools
from http.server import HTTPServer, SimpleHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(ROOT, "药师经", "卡片数据.json")
OUT_DIR = os.path.join(ROOT, "cards")
SCALE = 2                      # 像素密度：2 = 2160×3840
LOGICAL_W, LOGICAL_H = 1080, 1920


# ---------------------------------------------------------------- 数据 ----

def load_cards():
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)


def card_ready(card):
    """文案三段齐全才算可出卡"""
    return all(card.get(k, "").strip() for k in ("白话", "深一层", "收尾"))


def out_path(card):
    return os.path.join(OUT_DIR, f"{card['no']}-{card['品名短']}.png")


# ---------------------------------------------------------------- HTML ----

TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<style>
  *{margin:0;padding:0;box-sizing:border-box;}
  html{overflow:auto;}
  body{
    width:@@W@@px;height:@@H@@px;
    background:
      radial-gradient(circle at 50% -5%, #f2f8f6 0%, transparent 45%),
      linear-gradient(180deg,#eef5f3 0%,#e1ecec 100%);
    font-family:"Noto Serif SC","Songti SC","Source Han Serif SC",STSong,SimSun,serif;
    color:#2a3a38;position:relative;
  }
  .frame{position:absolute;inset:30px;border:2px solid #bcae7a;border-radius:0;
    box-shadow:0 0 0 8px rgba(188,174,122,.12);}
  .inner{position:absolute;inset:58px 66px;display:flex;flex-direction:column;align-items:center;}
  .head{display:flex;align-items:center;gap:26px;margin-top:4px;}
  .series{font-size:24px;letter-spacing:.4em;color:#3f7d77;text-indent:.4em;}
  .no{background:#2f6f6a;color:#f4faf8;border-radius:0;
    padding:8px 36px;font-size:27px;letter-spacing:.25em;text-indent:.25em;}
  .title{margin-top:24px;font-size:76px;font-weight:700;letter-spacing:.1em;
    color:#2a3a38;text-align:center;line-height:1.15;}
  .title small{display:block;font-size:30px;font-weight:400;color:#6f8a82;
    letter-spacing:.35em;margin-top:10px;text-indent:.35em;}
  .imgwrap{margin-top:32px;width:940px;height:740px;border-radius:0;overflow:hidden;
    border:1px solid #bcd0cf;box-shadow:0 10px 30px rgba(40,90,90,.15);
    display:flex;align-items:center;justify-content:center;}
  .imgwrap img{width:100%;height:100%;object-fit:contain;object-position:center;display:block;}
  .imgwrap .ph{color:#7a9a92;font-size:40px;letter-spacing:.3em;text-indent:.3em;}
  .quote{margin-top:34px;width:920px;text-align:center;
    background:linear-gradient(180deg,#f4faf8,#e9f2f0);
    border:1px solid #c3d6d4;border-radius:0;padding:26px 40px 20px;position:relative;}
  .quote::before{content:"「";position:absolute;left:26px;top:0;font-size:56px;
    color:#bcae7a;font-family:serif;}
  .quote .q{font-size:40px;line-height:1.6;color:#3a4a46;font-weight:600;}
  .quote .who{margin-top:10px;font-size:24px;color:#7a8a82;letter-spacing:.15em;}
  .sections{margin-top:34px;width:940px;display:flex;flex-direction:column;gap:24px;}
  .sec{display:flex;gap:24px;align-items:flex-start;}
  .sec .tag{flex:0 0 112px;text-align:center;background:#d6e6e3;color:#3f7d77;
    border-radius:0;padding:10px 0;font-size:28px;letter-spacing:.2em;text-indent:.2em;font-weight:600;}
  .sec p{font-size:31px;line-height:1.68;color:#2f3a38;}
  .footer{margin-top:auto;margin-bottom:2px;width:940px;
    border-top:2px solid #c3d6d4;padding-top:20px;
    display:flex;justify-content:space-between;align-items:center;
    font-size:24px;color:#7a8a82;letter-spacing:.1em;}
</style>
</head>
<body>
  <div class="frame"></div>
  <div class="inner">
    <div class="head">
      <div class="series">药师经 · 圣为 · 正文篇</div>
      <div class="no">@@编号@@</div>
    </div>
    <div class="title">@@品名@@<small>@@副题@@</small></div>

    <div class="imgwrap">@@图@@</div>

    <div class="quote">
      <div class="q">@@金句@@</div>
      <div class="who">—— @@出处@@</div>
    </div>

    <div class="sections">
      <div class="sec"><div class="tag">白话</div><p>@@白话@@</p></div>
      <div class="sec"><div class="tag">深一层</div><p>@@深一层@@</p></div>
      <div class="sec"><div class="tag">收尾</div><p>@@收尾@@</p></div>
    </div>

    <div class="footer">
      <span>@@品名全@@</span>
      <span>@@关键词@@</span>
    </div>
  </div>
</body>
</html>
"""


def build_html(card):
    img = card.get("配图", "").strip()
    if img and os.path.exists(os.path.join(ROOT, img)):
        img_html = f'<img src="{img}" alt="配图">'
    else:
        img_html = '<div class="ph">配图待放</div>'
        print(f"  ⚠ 配图缺失，使用占位框：{img or '(未填)'}")
    values = dict(
        W=str(LOGICAL_W), H=str(LOGICAL_H),
        编号=card["编号"], 品名=card["品名"], 副题=card.get("副题", ""),
        图=img_html, 金句=card["金句"].replace("\n", "<br>"),
        出处=card.get("出处", ""), 白话=card["白话"],
        深一层=card["深一层"], 收尾=card["收尾"],
        品名全=card["品名全"], 关键词=card.get("关键词", ""),
    )
    html = TEMPLATE
    for k, v in values.items():
        html = html.replace("@@" + k + "@@", v)
    return html


# ---------------------------------------------------------------- 渲染 ----

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def render_js(url, png):
    """playwright 渲染脚本：自适应缩字号 + 溢出硬校验 + 截图"""
    ctx_opt = "{viewport:{width:%d,height:%d}, deviceScaleFactor:%d}" % (LOGICAL_W, LOGICAL_H, SCALE)
    return (
        "async page => {"
        "const browser = page.context().browser();"
        "const ctx = await browser.newContext(" + ctx_opt + ");"
        "const p = await ctx.newPage();"
        "await p.goto('" + url + "', {waitUntil:'networkidle'});"
        "await p.evaluate(() => Promise.all(Array.from(document.images).filter(i=>!i.complete).map(i=>new Promise(r=>{i.onload=i.onerror=r;}))));"
        # 防溢出：文案过长时逐级缩小正文字号，直到页脚不超出容器
        "const fit=()=>{for(let i=0;i<5;i++){const inner=document.querySelector('.inner');"
        "const foot=document.querySelector('.footer');if(!foot)break;"
        "if(foot.getBoundingClientRect().bottom<=inner.getBoundingClientRect().bottom-2)break;"
        "document.querySelectorAll('.sec p').forEach(el=>{const fs=parseFloat(getComputedStyle(el).fontSize);el.style.fontSize=(fs-1.5)+'px';});"
        "const sec=document.querySelector('.sections');if(sec)sec.style.gap=Math.max(14,parseFloat(getComputedStyle(sec).gap)-3)+'px';}};"
        "await p.evaluate(fit);"
        # 硬校验：自适应后页脚仍超界则报错，保证卡片高度统一（2160×3840）且不裁字
        "const ok = await p.evaluate(()=>{const inner=document.querySelector('.inner');"
        "const foot=document.querySelector('.footer');"
        "return foot.getBoundingClientRect().bottom <= inner.getBoundingClientRect().bottom - 1;});"
        "if(!ok) throw new Error('OVERFLOW: 文案过长，自适应后仍溢出，请精简文案');"
        "await p.screenshot({path:'" + png + "'});"
        "await ctx.close();"
        "return 'ok'; }"
    )


def _render_cli(url, out_png):
    """优先后端：playwright-cli（仓库标准后端，原行为不变）"""
    png = out_png.replace("\\", "/")
    js = render_js(url, png)
    pw = shutil.which("playwright-cli")
    if not pw:
        raise RuntimeError("找不到 playwright-cli，请先：npm install -g @playwright/cli@latest")
    subprocess.run([pw, "close"], capture_output=True, timeout=30)
    subprocess.run([pw, "open", "about:blank"], capture_output=True, timeout=60, check=True)
    r = subprocess.run([pw, "run-code", js], capture_output=True, text=True, timeout=120)
    if "ok" not in r.stdout:
        print(r.stdout[-500:], r.stderr[-500:])
        raise RuntimeError("playwright 渲染失败")


def _render_py(url, out_png):
    """回退后端：本机已装 python playwright + chromium 时可用，无需 playwright-cli"""
    from playwright.sync_api import sync_playwright
    ctx_opt = dict(viewport={"width": LOGICAL_W, "height": LOGICAL_H},
                   device_scale_factor=SCALE)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        try:
            ctx = browser.new_context(**ctx_opt)
            p = ctx.new_page()
            p.goto(url, wait_until="networkidle")
            p.evaluate("() => Promise.all(Array.from(document.images).filter(i=>!i.complete).map(i=>new Promise(r=>{i.onload=i.onerror=r;})));")
            # 防溢出：文案过长时逐级缩小正文字号，直到页脚不超出容器
            for _ in range(5):
                inner = p.query_selector(".inner")
                foot = p.query_selector(".footer")
                if not foot:
                    break
                ib = inner.bounding_box(); fb = foot.bounding_box()
                if fb["y"] + fb["height"] <= ib["y"] + ib["height"] - 2:
                    break
                for el in p.query_selector_all(".sec p"):
                    fs = float(p.evaluate("el=>parseFloat(getComputedStyle(el).fontSize)", el))
                    p.evaluate("(el,fs)=>el.style.fontSize=fs+'px'", el, fs - 1.5)
                sec = p.query_selector(".sections")
                if sec:
                    gap = float(p.evaluate("el=>parseFloat(getComputedStyle(el).gap)", sec))
                    p.evaluate("(el,g)=>el.style.gap=g+'px'", sec, max(14, gap - 3))
            # 硬校验：自适应后页脚仍超界则报错，保证卡片高度统一（2160×3840）且不裁字
            ok = p.evaluate("()=>{const inner=document.querySelector('.inner');const foot=document.querySelector('.footer');return foot.getBoundingClientRect().bottom <= inner.getBoundingClientRect().bottom - 1;}")
            if not ok:
                raise RuntimeError("OVERFLOW: 文案过长，自适应后仍溢出，请精简文案")
            p.screenshot(path=out_png)
            ctx.close()
        finally:
            browser.close()


def render(html_file, out_png):
    """渲染一张卡。优先 playwright-cli，缺失时回退 python playwright。"""
    port = free_port()

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    handler = functools.partial(Quiet, directory=ROOT)
    server = HTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{port}/{os.path.relpath(html_file, ROOT).replace(os.sep, '/')}"
    try:
        if shutil.which("playwright-cli"):
            _render_cli(url, out_png)
        else:
            print("  · 未找到 playwright-cli，改用 python playwright 回退渲染")
            _render_py(url, out_png)
    finally:
        server.shutdown()

    from PIL import Image
    im = Image.open(out_png)
    expect = (LOGICAL_W * SCALE, LOGICAL_H * SCALE)
    assert im.size == expect, f"尺寸异常：{im.size}，应为 {expect}"
    return im.size


def norm_no(no):
    """归一化卡号：01/1 -> 01 ；01-1/1-1 -> 01-1（支持细分卡子序）"""
    no = no.strip()
    if "-" in no:
        head, tail = no.split("-", 1)
        return f"{head.zfill(2)}-{tail}"
    return no.zfill(2)


# ---------------------------------------------------------------- 主流程 ----

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    cards = load_cards()
    by_no = {c["no"]: c for c in cards}

    args = sys.argv[1:]
    if not args:
        ready = [c["no"] for c in cards if card_ready(c)]
        todo = [c["no"] for c in cards if not card_ready(c)]
        print("可出卡：", " ".join(ready) or "（无）")
        print("缺文案：", " ".join(todo) or "（无）")
        print("用法：python make_card.py 01 [02 03 ...]")
        return

    for no in args:
        no = norm_no(no)
        card = by_no.get(no)
        if not card:
            print(f"✗ 找不到编号 {no}"); continue
        if not card_ready(card):
            print(f"✗ 第{no}张文案不全（白话/深一层/收尾），先补 卡片数据.json"); continue

        tmp_html = os.path.join(ROOT, f"_card_{no}.html")
        with open(tmp_html, "w", encoding="utf-8") as f:
            f.write(build_html(card))

        out = out_path(card)
        w, h = render(tmp_html, out)
        size_kb = os.path.getsize(out) // 1024
        print(f"✓ {card['编号']}（品{int(no.split('-')[0])}）→ {os.path.relpath(out, ROOT)}  {w}×{h}  {size_kb}KB")
        os.remove(tmp_html)


if __name__ == "__main__":
    main()
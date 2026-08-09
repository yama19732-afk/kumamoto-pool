import json,re,datetime,urllib.request,urllib.parse,html
from pathlib import Path

UA={"User-Agent":"Mozilla/5.0 (compatible; KumamotoPoolInfo/1.4)"}
BASE=Path(__file__).resolve().parent
data_path=BASE/"data.json"
data=json.loads(data_path.read_text(encoding="utf-8"))
JST=datetime.timezone(datetime.timedelta(hours=9))
NOW=datetime.datetime.now(JST)
STAMP=NOW.strftime("%Y/%m/%d %H:%M")

def get_html(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=25) as r:
        return r.read().decode("utf-8","ignore")

def textify(raw):
    x=re.sub(r"<script.*?</script>"," ",raw,flags=re.S|re.I)
    x=re.sub(r"<style.*?</style>"," ",x,flags=re.S|re.I)
    x=re.sub(r"<[^>]+>"," ",x)
    return re.sub(r"\s+"," ",html.unescape(x)).strip()

def anchors(raw,base):
    out=[]
    for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw,flags=re.S|re.I):
        out.append((textify(label),urllib.parse.urljoin(base,html.unescape(href))))
    return out

# V3-compatible generic warning detection: keep this unchanged for other facilities.
KEYWORDS=["臨時休館","臨時閉鎖","利用休止","利用停止","プール休止","プール利用休止","営業再開"]
for p in data.get("pools",[]):
    try:
        txt=textify(get_html(p["official"]))
        hits=[]
        for kw in KEYWORDS:
            for m in re.finditer(re.escape(kw),txt):
                s=txt[max(0,m.start()-55):m.start()+145].strip()
                if s not in hits:hits.append(s)
        p["alert"]=" / ".join(hits[:2]) if hits else None
    except Exception:
        p["alert"]="公式情報の自動取得に失敗しました。公式サイトを確認してください。"

aqua=next((p for p in data.get("pools",[]) if p.get("id")=="aqua"),None)
if aqua:
    aqua.setdefault("main_pool",{"name":"メインプール","length":"50m","total_lanes":10,"season_text":"夏季"})
    aqua.setdefault("sub_pool",{"name":"サブプール","length":"25m","total_lanes":7,"season_text":"通年"})
    aqua["courses"]="メイン10 / サブ7"
    aqua["aqua_important_title"]=None
    aqua["aqua_important_url"]=None
    aqua["aqua_important_note"]=None
    aqua["aqua_today_events"]=[]

    # A) Verified current official notice.
    # The SKS official notice dated 2026-08-03 lists Aqua Dome among the facilities
    # affected by the Kumamoto earthquake and describes partial reopening / continuing restrictions.
    # This fallback is intentionally time-limited so it cannot remain forever as stale data.
    fallback_start=datetime.datetime(2026,8,3,tzinfo=JST)
    fallback_end=datetime.datetime(2026,9,15,23,59,tzinfo=JST)
    if fallback_start <= NOW <= fallback_end:
        aqua["aqua_important_title"]="令和8年熊本地震に伴う臨時休館施設の一部利用再開について"
        aqua["aqua_important_url"]="https://kc-sks.jp/news/newsdata.html?id=id6a70822576a30"
        aqua["aqua_important_note"]="2026/8/3付の熊本市文化スポーツ財団公式情報。アクアドームが対象施設に含まれるため、利用可能範囲を公式ページで確認してください。"

    # B) Automatic detection from Aqua and SKS news pages.
    important_words=["臨時休館","一部利用再開","利用休止","利用停止","営業再開","熊本地震","地震"]
    pages=[
        "https://kc-sks.jp/aqua/news.html",
        "https://kc-sks.jp/news/news.html",
        "https://kc-sks.jp/"
    ]
    found=[]
    for page in pages:
        try:
            raw=get_html(page)
            for label,url in anchors(raw,page):
                if label and any(w in label for w in important_words):
                    found.append((label,url))
        except Exception:
            pass

    # Prefer items explicitly naming Aqua Dome.
    chosen=None
    for label,url in found:
        if "アクアドーム" in label:
            chosen=(label,url);break
    if not chosen:
        for label,url in found[:20]:
            try:
                detail=textify(get_html(url))
            except Exception:
                detail=""
            if "アクアドーム" in detail and any(w in (label+" "+detail) for w in important_words):
                chosen=(label,url);break
    if chosen:
        aqua["aqua_important_title"]=chosen[0]
        aqua["aqua_important_url"]=chosen[1]
        aqua["aqua_important_note"]="公式サイトから自動検出した重要情報です。"

    # C) Direct pool/training status page. Because its body is dynamically rendered on some clients,
    # always provide the official link even if the text cannot be extracted.
    status_url="https://kc-sks.jp/aqua/newsdata.html?id=id60e79a8642ea9"
    for key in ["main_pool","sub_pool"]:
        obj=aqua[key]
        obj["status_url"]=status_url
        obj["status_checked_at"]=STAMP
        obj["status_text"]="10:30頃更新の公式レーン貸し情報を確認してください。"

    # D) Aqua news list: if server-rendered lane-lending links are visible, attach them separately.
    aqua_news="https://kc-sks.jp/aqua/news.html"
    lane=[]
    try:
        raw=get_html(aqua_news)
        for label,url in anchors(raw,aqua_news):
            if "レーン貸し" in label or "レーンの利用" in label:
                lane.append((label,url))
    except Exception:
        pass
    for key,needle in [("main_pool","メイン"),("sub_pool","サブ")]:
        obj=aqua[key]
        matches=[x for x in lane if needle in x[0]]
        obj["lane_notice_url"]=matches[0][1] if matches else aqua_news
        if matches:
            obj["status_text"]=matches[0][0]

    # E) Today calendar; keep conservative to avoid fabricating an event.
    cal_url="https://kc-sks.jp/aqua/calendar.html"
    try:
        cal=textify(get_html(cal_url))
        day=NOW.day
        pats=[
            rf"(?:^|\s){day}\s*[\(（][^）)]*[\)）][\.\s]*(.*?)(?=\s{day+1}\s*[\(（]|$)" if day<31 else rf"(?:^|\s){day}\s*[\(（][^）)]*[\)）][\.\s]*(.*)$",
            rf"(?:^|\s){day}\s+(.*?)(?=\s{day+1}\s|$)" if day<31 else rf"(?:^|\s){day}\s+(.*)$"
        ]
        event=""
        for pat in pats:
            m=re.search(pat,cal)
            if m:
                event=m.group(1).strip()
                break
        if event:
            event=re.split(r"\s(?:前月|次月|HOME)\b",event)[0].strip()
            if event and event not in ["-","－"]:
                aqua["aqua_today_events"]=[{"title":event[:220],"url":cal_url}]
    except Exception:
        pass

data["updated_at"]=STAMP
data_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

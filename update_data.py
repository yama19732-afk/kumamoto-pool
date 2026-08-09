import json,re,datetime,urllib.request,urllib.parse,html
from pathlib import Path
UA={"User-Agent":"Mozilla/5.0 (compatible; KumamotoPoolInfo/1.3)"}
BASE=Path(__file__).resolve().parent
data_path=BASE/"data.json"
data=json.loads(data_path.read_text(encoding="utf-8"))
JST=datetime.timezone(datetime.timedelta(hours=9)); NOW=datetime.datetime.now(JST); STAMP=NOW.strftime("%Y/%m/%d %H:%M")
def get_html(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode("utf-8","ignore")
def textify(raw):
    x=re.sub(r"<script.*?</script>"," ",raw,flags=re.S|re.I);x=re.sub(r"<style.*?</style>"," ",x,flags=re.S|re.I);x=re.sub(r"<[^>]+>"," ",x)
    return re.sub(r"\s+"," ",html.unescape(x)).strip()
def anchors(raw,base):
    return [(textify(label),urllib.parse.urljoin(base,html.unescape(href))) for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw,flags=re.S|re.I)]

# Generic V3-compatible warnings for all facilities.
KEYWORDS=["臨時休館","臨時閉鎖","利用休止","利用停止","プール休止","プール利用休止","営業再開"]
for p in data.get("pools",[]):
    try:
        txt=textify(get_html(p["official"]));hits=[]
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
    aqua["aqua_important_title"]=None;aqua["aqua_important_url"]=None;aqua["aqua_today_events"]=[]

    # 1) Official dedicated pool/training status page linked from Aqua Dome top page.
    status_url="https://kc-sks.jp/aqua/newsdata.html?id=id60e79a8642ea9"
    try:
        status_txt=textify(get_html(status_url))
    except Exception:
        status_txt=""

    # Store concise main/sub status independently. We search around each pool name.
    for key,needle in [("main_pool","メインプール"),("sub_pool","サブプール")]:
        obj=aqua[key]; obj["status_url"]=status_url; obj["status_checked_at"]=STAMP
        pos=status_txt.find(needle)
        if pos>=0:
            snippet=status_txt[pos:pos+500]
            snippet=re.split(r"(?:スケートリンク|トレーニングルーム|会議室|一覧に戻る)",snippet)[0].strip()
            obj["status_text"]=snippet[:260]
        else:
            obj["status_text"]="公式「プール・トレーニングの状況」を確認してください。"

    # 2) Global SKS important-news list catches earthquake/closure notices that Aqua top HTML may not expose.
    global_news="https://kc-sks.jp/news/news.html"
    important_words=["臨時休館","一部利用再開","利用休止","利用停止","営業再開","熊本地震","地震"]
    candidates=[]
    try:
        raw=get_html(global_news)
        for label,url in anchors(raw,global_news):
            if label and any(w in label for w in important_words):
                candidates.append((label,url))
    except Exception:pass
    # Prefer notices mentioning Aqua Dome in title or detail, otherwise current disaster-wide notice.
    chosen=None
    for label,url in candidates[:15]:
        if "アクアドーム" in label:
            chosen=(label,url);break
        try:
            detail=textify(get_html(url))
        except Exception:
            detail=""
        if "アクアドーム" in detail or ("熊本地震" in label and "臨時休館" in detail):
            chosen=(label,url);break
    if not chosen and candidates:chosen=candidates[0]
    if chosen:aqua["aqua_important_title"],aqua["aqua_important_url"]=chosen

    # 3) Aqua news list: lane-lending details, if exposed.
    aqua_news="https://kc-sks.jp/aqua/news.html"
    lane=[]
    try:
        raw=get_html(aqua_news)
        for label,url in anchors(raw,aqua_news):
            if "レーン貸し" in label or "レーンの利用" in label:
                lane.append((label,url))
    except Exception:pass
    for key,needle in [("main_pool","メイン"),("sub_pool","サブ")]:
        obj=aqua[key]
        matches=[x for x in lane if needle in x[0]]
        obj["lane_notice_url"]=matches[0][1] if matches else aqua_news
        if matches and not obj.get("status_text"):
            obj["status_text"]=matches[0][0]

    # 4) Today's calendar entry, including cancellations.
    cal_url="https://kc-sks.jp/aqua/calendar.html"
    try:
        cal=textify(get_html(cal_url))
        day=NOW.day
        # Specially capture the current day row; tolerant of "9(日)." etc.
        pats=[rf"(?:^|\s){day}\s*[\(（][^）)]*[\)）][\.\s]*(.*?)(?=\s{day+1}\s*[\(（]|$)" if day<31 else rf"(?:^|\s){day}\s*[\(（][^）)]*[\)）][\.\s]*(.*)$",
              rf"(?:^|\s){day}\s+(.*?)(?=\s{day+1}\s|$)" if day<31 else rf"(?:^|\s){day}\s+(.*)$"]
        event=""
        for pat in pats:
            m=re.search(pat,cal)
            if m:event=m.group(1).strip();break
        if event:
            event=re.split(r"\s(?:前月|次月|HOME)\b",event)[0].strip()
            if event and event not in ["-","－"]:aqua["aqua_today_events"]=[{"title":event[:220],"url":cal_url}]
    except Exception:pass

data["updated_at"]=STAMP
data_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

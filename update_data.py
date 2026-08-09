import json,re,datetime,urllib.request,urllib.parse,html
from pathlib import Path
UA={"User-Agent":"Mozilla/5.0 (compatible; KumamotoPoolInfo/1.5)"}
BASE=Path(__file__).resolve().parent
data_path=BASE/"data.json"
data=json.loads(data_path.read_text(encoding="utf-8"))
JST=datetime.timezone(datetime.timedelta(hours=9));NOW=datetime.datetime.now(JST);STAMP=NOW.strftime("%Y/%m/%d %H:%M")
def get_html(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode("utf-8","ignore")
def textify(raw):
    x=re.sub(r"<script.*?</script>"," ",raw,flags=re.S|re.I);x=re.sub(r"<style.*?</style>"," ",x,flags=re.S|re.I);x=re.sub(r"<[^>]+>"," ",x)
    return re.sub(r"\s+"," ",html.unescape(x)).strip()
def anchors(raw,base):
    return [(textify(label),urllib.parse.urljoin(base,html.unescape(href))) for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw,flags=re.S|re.I)]

KEYWORDS=["臨時休館","臨時閉鎖","利用休止","利用停止","プール休止","プール利用休止","営業再開"]
for p in data.get("pools",[]):
    try:
        txt=textify(get_html(p["official"]));hits=[]
        for kw in KEYWORDS:
            for m in re.finditer(re.escape(kw),txt):
                s=txt[max(0,m.start()-55):m.start()+145].strip()
                if s not in hits:hits.append(s)
        p["alert"]=" / ".join(hits[:2]) if hits else None
    except Exception:p["alert"]="公式情報の自動取得に失敗しました。公式サイトを確認してください。"

aqua=next((p for p in data.get("pools",[]) if p.get("id")=="aqua"),None)
if aqua:
    aqua.setdefault("main_pool",{"name":"メインプール","length":"50m","total_lanes":10,"season_text":"夏季"})
    aqua.setdefault("sub_pool",{"name":"サブプール","length":"25m","total_lanes":7,"season_text":"通年"})
    aqua["courses"]="メイン10 / サブ7";aqua["aqua_important_title"]=None;aqua["aqua_important_url"]=None;aqua["aqua_important_note"]=None;aqua["aqua_today_events"]=[]

    # Current verified earthquake notice (time-limited).
    if datetime.datetime(2026,8,3,tzinfo=JST)<=NOW<=datetime.datetime(2026,9,15,23,59,tzinfo=JST):
        aqua["aqua_important_title"]="令和8年熊本地震に伴う臨時休館施設の一部利用再開について"
        aqua["aqua_important_url"]="https://kc-sks.jp/news/newsdata.html?id=id6a70822576a30"
        aqua["aqua_important_note"]="2026/8/3付の公式情報。アクアドームが対象施設に含まれるため、利用可能範囲を確認してください。"

    # Aqua staff blog is server-indexed and can expose closure/disaster wording more reliably.
    try:
        blog=textify(get_html("https://kc-sks.jp/aqua/blog.html"))
        if "臨時休館" in blog or "熊本地震" in blog:
            aqua["aqua_important_title"]=aqua["aqua_important_title"] or "令和8年度熊本地震による施設状況について"
            aqua["aqua_important_url"]="https://kc-sks.jp/aqua/blog.html"
            aqua["aqua_important_note"]="アクアドーム公式スタッフブログにも地震・臨時休館に関する案内があります。"
    except Exception:pass

    # Direct official status and lane-info links.
    status_url="https://kc-sks.jp/aqua/newsdata.html?id=id60e79a8642ea9"
    aqua_news="https://kc-sks.jp/aqua/news.html"
    lane=[]
    try:
        raw=get_html(aqua_news)
        lane=[(label,url) for label,url in anchors(raw,aqua_news) if "レーン貸し" in label or "レーンの利用" in label]
    except Exception:pass
    for key,needle in [("main_pool","メイン"),("sub_pool","サブ")]:
        obj=aqua[key];obj["status_url"]=status_url;obj["status_checked_at"]=STAMP
        matches=[x for x in lane if needle in x[0]]
        obj["lane_notice_url"]=matches[0][1] if matches else aqua_news
        obj["status_text"]=matches[0][0] if matches else "10:30頃更新の公式レーン貸し情報を確認してください。"

    # Today calendar entry.
    cal_url="https://kc-sks.jp/aqua/calendar.html"
    try:
        cal=textify(get_html(cal_url));day=NOW.day
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

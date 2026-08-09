import json, re, datetime, urllib.request, urllib.parse, html
from pathlib import Path

UA={"User-Agent":"Mozilla/5.0 (compatible; KumamotoPoolInfo/1.2)"}
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

# Preserve the V3-style generic detection for all facilities.
KEYWORDS=["臨時休館","臨時閉鎖","利用休止","利用停止","プール休止","プール利用休止","営業再開"]
for p in data.get("pools",[]):
    try:
        txt=textify(get_html(p["official"]))
        hits=[]
        for kw in KEYWORDS:
            for m in re.finditer(re.escape(kw),txt):
                snip=txt[max(0,m.start()-55):m.start()+145].strip()
                if snip not in hits: hits.append(snip)
        p["alert"]=" / ".join(hits[:2]) if hits else None
    except Exception:
        p["alert"]="公式情報の自動取得に失敗しました。公式サイトを確認してください。"

# Aqua Dome dedicated processing.
aqua=next((p for p in data.get("pools",[]) if p.get("id")=="aqua"),None)
if aqua:
    aqua.setdefault("main_pool",{"name":"メインプール","length":"50m","total_lanes":10,"season_text":"夏季"})
    aqua.setdefault("sub_pool",{"name":"サブプール","length":"25m","total_lanes":7,"season_text":"通年"})
    aqua["courses"]="メイン10 / サブ7"
    aqua["aqua_important_title"]=None
    aqua["aqua_important_url"]=None
    aqua["aqua_today_events"]=[]

    news_url="https://kc-sks.jp/aqua/news.html"
    news_candidates=[]
    try:
        raw=get_html(news_url)
        for label,url in anchors(raw,news_url):
            if "newsdata.html" in url and label:
                news_candidates.append((label,url))
    except Exception:
        pass

    # If the list page is sparse in returned HTML, use any newsdata links exposed on the top page too.
    try:
        raw=get_html("https://kc-sks.jp/aqua/")
        for label,url in anchors(raw,"https://kc-sks.jp/aqua/"):
            if "newsdata.html" in url and label:
                news_candidates.append((label,url))
    except Exception:
        pass

    # Deduplicate, newest list order first.
    seen=set(); news=[]
    for item in news_candidates:
        if item not in seen:
            seen.add(item); news.append(item)

    important_words=["臨時休館","利用休止","利用停止","一部利用再開","施設再開","地震","大雨","台風"]
    lane_main=[]; lane_sub=[]
    important=[]
    for label,url in news:
        if any(w in label for w in important_words):
            important.append((label,url))
        if "レーン貸し" in label:
            if "メイン" in label: lane_main.append((label,url))
            if "サブ" in label: lane_sub.append((label,url))

    # Also inspect a limited number of detail pages because some list labels can be generic.
    for label,url in news[:12]:
        if important and lane_main and lane_sub:
            break
        try:
            detail=textify(get_html(url))
        except Exception:
            continue
        if not any(x[1]==url for x in important) and any(w in detail for w in important_words):
            title=label or detail[:100]
            important.append((title,url))
        if "レーン貸し" in detail:
            if "メインプール" in detail and not any(x[1]==url for x in lane_main):
                lane_main.append((label or "メインプール レーン貸しのお知らせ",url))
            if "サブプール" in detail and not any(x[1]==url for x in lane_sub):
                lane_sub.append((label or "サブプール レーン貸しのお知らせ",url))

    if important:
        aqua["aqua_important_title"]=important[0][0]
        aqua["aqua_important_url"]=important[0][1]

    for key,matches in [("main_pool",lane_main),("sub_pool",lane_sub)]:
        obj=aqua[key]
        if matches:
            obj["lane_notice_title"]=matches[0][0]
            obj["lane_notice_url"]=matches[0][1]
        else:
            obj["lane_notice_title"]=None
            obj["lane_notice_url"]=news_url
        obj["lane_notice_checked_at"]=STAMP

    # Today's calendar entries. The calendar page contains day-number cells and event text.
    cal_url="https://kc-sks.jp/aqua/calendar.html"
    try:
        cal_txt=textify(get_html(cal_url))
        day=NOW.day
        # Capture text after today's day marker until the next day marker, with conservative fallbacks.
        patterns=[
            rf"(?:^|\s){day}\s*[\(（][^）)]*[\)）]\s*(.*?)(?=\s{day+1}\s*[\(（]|$)" if day<31 else rf"(?:^|\s){day}\s*[\(（][^）)]*[\)）]\s*(.*)$",
            rf"(?:^|\s){day}\s+(.*?)(?=\s{day+1}\s|$)" if day<31 else rf"(?:^|\s){day}\s+(.*)$"
        ]
        event_text=""
        for pat in patterns:
            m=re.search(pat,cal_txt)
            if m:
                event_text=m.group(1).strip()
                break
        if event_text and len(event_text)<500:
            # Remove obvious navigation/noise.
            event_text=re.split(r"\s(?:前月|次月|HOME|アクアドームくまもと)\b",event_text)[0].strip()
            if event_text and event_text not in ["-", "－"]:
                aqua["aqua_today_events"]=[{"title":event_text[:220],"url":cal_url}]
    except Exception:
        pass

data["updated_at"]=STAMP
data_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

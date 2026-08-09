import json, re, datetime, urllib.request, urllib.parse, html
from pathlib import Path
UA={"User-Agent":"Mozilla/5.0 (compatible; KumamotoPoolInfo/1.1)"}
BASE=Path(__file__).resolve().parent
data_path=BASE/"data.json"
data=json.loads(data_path.read_text(encoding="utf-8"))
jst=datetime.timezone(datetime.timedelta(hours=9))
stamp=datetime.datetime.now(jst).strftime("%Y/%m/%d %H:%M")
def get_html(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=25) as r:return r.read().decode("utf-8","ignore")
def textify(raw):
    x=re.sub(r"<script.*?</script>"," ",raw,flags=re.S|re.I);x=re.sub(r"<style.*?</style>"," ",x,flags=re.S|re.I);x=re.sub(r"<[^>]+>"," ",x)
    return re.sub(r"\s+"," ",html.unescape(x))
KEYWORDS=["臨時休館","臨時閉鎖","利用休止","利用停止","プール休止","営業再開"]
for p in data["pools"]:
    try:
        text=textify(get_html(p["official"]));hits=[]
        for kw in KEYWORDS:
            for m in re.finditer(kw,text):hits.append(text[max(0,m.start()-50):m.start()+120].strip())
        p["alert"]=" / ".join(dict.fromkeys(hits[:2])) if hits else None
    except Exception:p["alert"]="公式情報の自動取得に失敗しました。公式サイトを確認してください。"
aqua=next((p for p in data["pools"] if p["id"]=="aqua"),None)
if aqua:
    candidates=[]
    for u in ["https://kc-sks.jp/aqua/","https://kc-sks.jp/aqua/news.html"]:
        try:
            raw=get_html(u)
            for href,label in re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',raw,flags=re.S|re.I):
                label=textify(label)
                if "レーン貸し" in label:
                    candidates.append((label,urllib.parse.urljoin(u,html.unescape(href))))
        except Exception:pass
    seen=set();uniq=[]
    for x in candidates:
        if x not in seen:seen.add(x);uniq.append(x)
    for key,needle in [("main_pool","メインプール"),("sub_pool","サブプール")]:
        obj=aqua[key];matches=[x for x in uniq if needle in x[0] and "レーン貸し" in x[0]]
        if matches:
            obj["lane_notice_title"],obj["lane_notice_url"]=matches[0]
        else:
            obj["lane_notice_title"]=None
            obj["lane_notice_url"]="https://kc-sks.jp/aqua/news.html"
        obj["lane_notice_checked_at"]=stamp
data["updated_at"]=stamp
data_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

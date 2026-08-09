import json, re, datetime, urllib.request
from pathlib import Path

UA={"User-Agent":"Mozilla/5.0 (compatible; KumamotoPoolInfo/1.0)"}
BASE=Path(__file__).resolve().parents[1]
data_path=BASE/"data.json"
data=json.loads(data_path.read_text(encoding="utf-8"))

KEYWORDS=["臨時休館","臨時閉鎖","利用休止","利用停止","プール休止","プール利用休止","重要なお知らせ","営業再開"]
def fetch(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=20) as r:
        raw=r.read().decode("utf-8","ignore")
    text=re.sub(r"<script.*?</script>"," ",raw,flags=re.S|re.I)
    text=re.sub(r"<style.*?</style>"," ",text,flags=re.S|re.I)
    text=re.sub(r"<[^>]+>"," ",text)
    return re.sub(r"\s+"," ",text)

for p in data["pools"]:
    try:
        text=fetch(p["official"])
        hits=[]
        for kw in KEYWORDS:
            i=text.find(kw)
            if i>=0:
                snippet=text[max(0,i-45):i+95].strip()
                hits.append(snippet)
        # 「重要なお知らせ」だけの一般見出しはノイズになりやすいため、
        # 休止/閉鎖/再開など具体語があるときだけ警告表示する。
        concrete=[h for h in hits if any(k in h for k in ["臨時休館","臨時閉鎖","利用休止","利用停止","プール休止","営業再開"])]
        p["alert"]=" / ".join(dict.fromkeys(concrete[:2])) if concrete else None
    except Exception as e:
        p["alert"]="公式情報の自動取得に失敗しました。公式サイトを確認してください。"

jst=datetime.timezone(datetime.timedelta(hours=9))
data["updated_at"]=datetime.datetime.now(jst).strftime("%Y/%m/%d %H:%M")
data_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")

"""Amostra da estrutura de dados do Buscapé (busca e página de produto). Grava data/sondagem.json."""
import json, re, urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def next_data(pg):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', pg, re.S)
    return json.loads(m.group(1)) if m else None


def walk(o, path=""):
    if isinstance(o, dict):
        yield path, o
        for k, v in o.items():
            yield from walk(v, path + "." + k)
    elif isinstance(o, list):
        for i, v in enumerate(o[:40]):
            yield from walk(v, path + f"[{i}]")


def corta(o, n=0):
    if n > 3:
        return "…"
    if isinstance(o, dict):
        return {k: corta(v, n + 1) for k, v in list(o.items())[:30]}
    if isinstance(o, list):
        return [corta(v, n + 1) for v in o[:3]]
    if isinstance(o, str):
        return o[:140]
    return o


out = {"quando": datetime.now(timezone.utc).isoformat()}
try:
    nd = next_data(baixar("https://www.buscape.com.br/search?q=geladeira%20consul%20inox"))
    hit = nd["props"]["initialReduxState"]["hits"]["hits"][0]
    url = "https://www.buscape.com.br" + hit["url"]
    pp = baixar(url)
    out["produto_url"] = url
    nd2 = next_data(pp)
    st = nd2["props"]["initialReduxState"]
    out["chaves_estado"] = list(st.keys())
    achados = []
    for path, d in walk(nd2):
        ks = set(d.keys())
        if ("price" in ks or "value" in ks) and any("merchant" in k.lower() or "store" in k.lower() or "seller" in k.lower() for k in ks):
            achados.append({"path": path, "item": corta(d)})
        if len(achados) >= 4:
            break
    pp_ = nd2["props"]["pageProps"]
    out["pageProps_chaves"] = {k: (list(v.keys())[:40] if isinstance(v, dict) else type(v).__name__) for k, v in pp_.items()}
    ofl = []
    for path, d in walk(nd2):
        for k, v in d.items():
            if "offer" in k.lower() and isinstance(v, list) and v and isinstance(v[0], dict):
                ofl.append({"path": path + "." + k, "n": len(v), "primeiro": corta(v[0])})
        if len(ofl) >= 4:
            break
    out["listas_ofertas"] = ofl
    ol = nd2["props"]["initialReduxState"]["offers"]["offerList"]
    out["offer_keys"] = list(ol[0].keys())
    out["offer_extra"] = {k: ol[0][k] for k in list(ol[0].keys())[30:]}
    out["sellers"] = [(o.get("sellerName"), o.get("price"), o.get("sellerIsMarketplace")) for o in ol]
    out["leadParams"] = nd2["props"]["pageProps"]["page"].get("leadParams")
    out["lead_html"] = sorted(set(re.findall(r'[^"\s]{0,60}/lead[^"\s]{0,160}', pp)))[:8]
    out["ofertas"] = []
    out["links_saida"] = sorted(set(re.findall(r'https?://[^"\s]*(?:lead|redirect|offer|out)[^"\s]{0,120}', pp)))[:10]
except Exception as e:  # noqa: BLE001
    out["erro"] = repr(e)[:300]
json.dump(out, open("data/sondagem.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok")

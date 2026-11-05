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
for site, url in [("buscape", "https://www.buscape.com.br/search?q=geladeira%20consul%20inox"),
                  ("zoom", "https://www.zoom.com.br/search?q=geladeira%20consul%20inox")]:
    try:
        pg = baixar(url)
        nd = next_data(pg)
        cand = []
        for path, d in walk(nd):
            ks = set(d.keys())
            if ("price" in ks or "minPrice" in ks or "bestPrice" in ks) and ("name" in ks or "title" in ks):
                cand.append({"path": path, "item": corta(d)})
            if len(cand) >= 3:
                break
        out[site + "_busca"] = cand
        # primeiro link de produto
        links = re.findall(r'href="(/[^"]+)"', pg)
        prod = next((l for l in links if re.search(r"/(geladeira|refrigerador)[^/]*$", l) or "/p/" in l), None)
        out[site + "_links_exemplo"] = [l for l in links if "geladeira" in l][:8]
        if prod:
            pp = baixar(("https://www.buscape.com.br" if site == "buscape" else "https://www.zoom.com.br") + prod)
            nd2 = next_data(pp)
            ofs = []
            for path, d in walk(nd2):
                ks = set(d.keys())
                if "price" in ks and any(k in ks for k in ("store", "merchant", "seller", "storeName", "shop")):
                    ofs.append({"path": path, "item": corta(d)})
                if len(ofs) >= 3:
                    break
            out[site + "_produto_url"] = prod
            out[site + "_produto_ofertas"] = ofs
            out[site + "_produto_ldjson"] = [b[:1500] for b in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', pp, re.S)][:2]
    except Exception as e:  # noqa: BLE001
        out[site + "_erro"] = str(e)[:200]
json.dump(out, open("data/sondagem.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("ok")

"""Amostra da estrutura de dados das novas fontes. Grava data/sondagem.json."""
import json, re, urllib.request
from datetime import datetime, timezone
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
def baixar(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "ignore")
def walk(o, path=""):
    if isinstance(o, dict):
        yield path, o
        for k, v in o.items():
            yield from walk(v, path + "." + k)
    elif isinstance(o, list):
        for i, v in enumerate(o[:60]):
            yield from walk(v, path + f"[{i}]")
def corta(o, n=0):
    if n > 2: return "…"
    if isinstance(o, dict): return {k: corta(v, n + 1) for k, v in list(o.items())[:40]}
    if isinstance(o, list): return [corta(v, n + 1) for v in o[:2]]
    if isinstance(o, str): return o[:100]
    return o
def jsons(pg):
    out = []
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', pg, re.S)
    if m: out.append(json.loads(m.group(1)))
    for m in re.finditer(r'(?:__PRELOADED_STATE__|__INITIAL_STATE__)\s*=\s*(\{.*?\});?\s*</script>', pg, re.S):
        try: out.append(json.loads(m.group(1)))
        except Exception: pass
    for b in re.findall(r'<script[^>]+application/(?:ld\+)?json[^>]*>(.*?)</script>', pg, re.S):
        try: out.append(json.loads(b))
        except Exception: pass
    return out
FONTES = {
 "americanas": "https://www.americanas.com.br/busca/cooktop-electrolux-ke4gr",
 "kabum": "https://www.kabum.com.br/busca/cooktop-electrolux-ke4gr",
 "promobit": "https://www.promobit.com.br/buscar/?q=cooktop",
 "mercadolivre": "https://lista.mercadolivre.com.br/cooktop-electrolux-ke4gr",
}
out = {"quando": datetime.now(timezone.utc).isoformat()}
for nome, url in FONTES.items():
    try:
        pg = baixar(url)
        achados = []
        for j in jsons(pg):
            for path, d in walk(j):
                ks = {k.lower() for k in d}
                if any("price" in k or "preco" in k for k in ks) and any(k in ks for k in ("name", "title", "productname", "nome")):
                    achados.append({"path": path[-90:], "item": corta(d)})
                if len(achados) >= 2: break
            if len(achados) >= 2: break
        out[nome] = {"achados": achados, "trecho_ke4gr": [pg[max(0, i - 200): i + 250] for i in [m.start() for m in re.finditer("(?i)ke4gr", pg)][:1]]}
    except Exception as e:  # noqa: BLE001
        out[nome] = {"erro": str(e)[:100]}
json.dump(out, open("data/sondagem.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

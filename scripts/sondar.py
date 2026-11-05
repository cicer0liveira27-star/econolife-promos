"""Testa quais fontes respondem a partir do GitHub. Grava data/sondagem.json (resumo curto)."""
import json, re, urllib.request
from datetime import datetime, timezone
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
Q = "cooktop electrolux ke4gr"
ALVOS = {
 "zoom": "https://www.zoom.com.br/search?q=" + Q.replace(" ", "%20"),
 "americanas": "https://www.americanas.com.br/busca/" + Q.replace(" ", "-"),
 "submarino": "https://www.submarino.com.br/busca/" + Q.replace(" ", "-"),
 "shoptime": "https://www.shoptime.com.br/busca/" + Q.replace(" ", "-"),
 "mercadolivre_html": "https://lista.mercadolivre.com.br/" + Q.replace(" ", "-"),
 "mercadolivre_api": "https://api.mercadolibre.com/sites/MLB/search?q=" + Q.replace(" ", "%20"),
 "amazon": "https://www.amazon.com.br/s?k=" + Q.replace(" ", "+"),
 "magalu": "https://www.magazineluiza.com.br/busca/" + Q.replace(" ", "+") + "/",
 "casasbahia": "https://www.casasbahia.com.br/" + Q.replace(" ", "-") + "/b",
 "pontofrio": "https://www.pontofrio.com.br/" + Q.replace(" ", "-") + "/b",
 "kabum": "https://www.kabum.com.br/busca/" + Q.replace(" ", "-"),
 "fastshop": "https://site.fastshop.com.br/busca?q=" + Q.replace(" ", "%20"),
 "carrefour": "https://www.carrefour.com.br/busca/" + Q.replace(" ", "%20"),
 "electrolux": "https://loja.electrolux.com.br/busca?q=ke4gr",
 "brastemp": "https://www.brastemp.com.br/busca?q=geladeira",
 "webcontinental": "https://www.webcontinental.com.br/busca?q=" + Q.replace(" ", "+"),
 "leroy": "https://www.leroymerlin.com.br/search?term=cooktop",
 "ferreiracosta": "https://www.ferreiracosta.com/busca?q=cooktop",
 "pelando": "https://www.pelando.com.br/busca/cooktop",
 "promobit": "https://www.promobit.com.br/buscar/?q=cooktop",
 "google_shopping": "https://www.google.com/search?tbm=shop&hl=pt-BR&gl=br&q=" + Q.replace(" ", "+"),
 "bing_shopping": "https://www.bing.com/shop?q=" + Q.replace(" ", "+"),
 "jacotei": "https://www.jacotei.com.br/busca/?q=" + Q.replace(" ", "+"),
 "comparamais": "https://www.compare.com.br/busca?q=" + Q.replace(" ", "+"),
}
out = {"quando": datetime.now(timezone.utc).isoformat(), "r": {}}
for nome, url in ALVOS.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=20) as r:
            b = r.read().decode("utf-8", "ignore")
        out["r"][nome] = f"{r.status} tam={len(b)} ld={b.count('ld+json')} next={'__NEXT_DATA__' in b} R$={len(re.findall(r'R\$', b))} ke4gr={'ke4gr' in b.lower()}"
    except Exception as e:  # noqa: BLE001
        out["r"][nome] = "ERRO " + str(e)[:60]
json.dump(out, open("data/sondagem.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

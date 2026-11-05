"""Teste de quais lojas/fontes respondem a partir dos servidores do GitHub. Grava data/sondagem.json."""
import json, re, urllib.request
from datetime import datetime, timezone

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
ALVOS = {
    "ml_api_busca": "https://api.mercadolibre.com/sites/MLB/search?q=geladeira%20consul%20inox&limit=3",
    "ml_api_item": "https://api.mercadolibre.com/items/MLB3456789012",
    "ml_api_produtos": "https://api.mercadolibre.com/products/search?status=active&site_id=MLB&q=geladeira%20consul",
    "ml_lista_html": "https://lista.mercadolivre.com.br/geladeira-consul-inox",
    "magalu_busca": "https://www.magazineluiza.com.br/busca/geladeira+consul+inox/",
    "amazon_busca": "https://www.amazon.com.br/s?k=geladeira+consul+inox",
    "americanas_busca": "https://www.americanas.com.br/busca/geladeira-consul-inox",
    "casasbahia_busca": "https://www.casasbahia.com.br/geladeira-consul-inox/b",
    "kabum_busca": "https://www.kabum.com.br/busca/geladeira-consul",
    "leroy_busca": "https://www.leroymerlin.com.br/search?term=porcelanato",
    "carrefour_busca": "https://www.carrefour.com.br/busca/geladeira%20consul",
    "fastshop_busca": "https://site.fastshop.com.br/busca?q=geladeira%20consul",
    "electrolux_busca": "https://loja.electrolux.com.br/busca?q=microondas",
    "brastemp_busca": "https://www.brastemp.com.br/busca?q=geladeira",
    "zoom_busca": "https://www.zoom.com.br/search?q=geladeira%20consul%20inox",
    "buscape_busca": "https://www.buscape.com.br/search?q=geladeira%20consul%20inox",
    "google_shopping": "https://www.google.com/search?tbm=shop&q=geladeira+consul+inox&hl=pt-BR&gl=br",
    "pelando": "https://www.pelando.com.br/busca/geladeira",
}
out = {"quando": datetime.now(timezone.utc).isoformat(), "resultados": {}}
for nome, url in ALVOS.items():
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8", "ignore")
            out["resultados"][nome] = {"status": r.status, "tamanho": len(body),
                                       "ldjson": body.count("application/ld+json"), "next_data": "__NEXT_DATA__" in body,
                                       "preco_R$": len(re.findall(r"R\$\s?\d", body)), "inicio": body[:160]}
    except Exception as e:  # noqa: BLE001
        out["resultados"][nome] = {"erro": str(e)[:120]}
json.dump(out, open("data/sondagem.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False)[:3000])

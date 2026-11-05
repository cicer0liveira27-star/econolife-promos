"""Robô gratuito do Econolife Promos (roda no GitHub Actions, sem usar o Claude).

A cada execução:
  1. Abre a página de cada oferta já conhecida e atualiza preço, foto e disponibilidade.
  2. Para produtos sem ofertas (ou com poucas), procura na busca da Magazine Luiza e do Mercado Livre.
  3. Atualiza histórico, cria alertas e manda no Telegram quando o preço fica bom.
  4. Grava um relatório em data/checagem.json.
"""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import enviar_whatsapp as avisos  # noqa: E402

AGORA = datetime.now(timezone.utc)
ISO = AGORA.strftime("%Y-%m-%dT%H:%M:%SZ")
from datetime import timedelta
HOJE = (AGORA - timedelta(hours=3)).strftime("%Y-%m-%d")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
TRUSTED = ["amazon.com.br", "mercadolivre.com.br", "magazineluiza.com.br", "casasbahia.com.br", "pontofrio.com.br",
           "ponto.com.br", "extra.com.br", "americanas.com.br", "submarino.com.br", "shoptime.com.br", "carrefour.com.br",
           "fastshop.com.br", "kabum.com.br", "girafa.com.br", "leroymerlin.com.br", "telhanorte.com.br", "cec.com.br",
           "obramax.com.br", "ferreiracosta.com", "madeiramadeira.com.br", "tokstok.com.br", "mobly.com.br",
           "brastemp.com.br", "consul.com.br", "electrolux.com.br", "midea.com", "samsung.com", "lg.com", "dako.com.br",
           "philco.com.br", "britania.com.br", "portobello.com.br", "portobelloshop.com.br", "eliane.com",
           "tramontina.com.br", "stella.com.br", "balaroti.com.br"]
LOJA_POR_DOMINIO = {"magazineluiza.com.br": "Magazine Luiza", "mercadolivre.com.br": "Mercado Livre",
                    "amazon.com.br": "Amazon", "casasbahia.com.br": "Casas Bahia", "americanas.com.br": "Americanas",
                    "kabum.com.br": "KaBuM", "leroymerlin.com.br": "Leroy Merlin", "fastshop.com.br": "Fast Shop"}
log = {"quando": ISO, "verificados": 0, "atualizados": 0, "fotos": 0, "descobertas": 0, "falhas": [], "alertas": 0}


# ---------------- util ----------------
def confiavel(url):
    try:
        u = urllib.parse.urlparse(url)
        h = u.hostname or ""
        h = h[4:] if h.startswith("www.") else h
        return u.scheme == "https" and any(h == d or h.endswith("." + d) for d in TRUSTED)
    except Exception:  # noqa: BLE001
        return False


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else None
    s = str(v).strip()
    s = re.sub(r"[^\d,\.]", "", s)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        f = float(s)
        return f if f > 0 else None
    except ValueError:
        return None


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


def meta(pagina, prop):
    m = re.search(r'<meta[^>]+(?:property|name|itemprop)=["\']' + re.escape(prop) + r'["\'][^>]*content=["\']([^"\']+)', pagina, re.I) \
        or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']' + re.escape(prop) + r'["\']', pagina, re.I)
    return html.unescape(m.group(1)) if m else None


def ler_produto(pagina):
    """Extrai preço, imagem, título e disponibilidade de uma página de produto."""
    info = {"preco": None, "imagem": None, "titulo": None, "esgotado": False}
    for bloco in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', pagina, re.S | re.I):
        try:
            dado = json.loads(html.unescape(bloco.strip()), strict=False)
        except Exception:  # noqa: BLE001
            continue
        for d in walk(dado):
            tipo = d.get("@type")
            tipos = tipo if isinstance(tipo, list) else [tipo]
            if "Product" not in tipos:
                continue
            info["titulo"] = info["titulo"] or d.get("name")
            img = d.get("image")
            if isinstance(img, list):
                img = img[0] if img else None
            if isinstance(img, dict):
                img = img.get("url")
            info["imagem"] = info["imagem"] or img
            ofs = d.get("offers")
            ofs = ofs if isinstance(ofs, list) else [ofs] if ofs else []
            precos = []
            for of in ofs:
                if not isinstance(of, dict):
                    continue
                p = num(of.get("price")) or num(of.get("lowPrice"))
                if p:
                    precos.append(p)
                if "OutOfStock" in str(of.get("availability", "")):
                    info["esgotado"] = True
            if precos:
                info["preco"] = min(precos)
    info["preco"] = info["preco"] or num(meta(pagina, "product:price:amount")) or num(meta(pagina, "og:price:amount"))
    info["imagem"] = info["imagem"] or meta(pagina, "og:image")
    info["titulo"] = info["titulo"] or meta(pagina, "og:title")
    if info["imagem"] and info["imagem"].startswith("//"):
        info["imagem"] = "https:" + info["imagem"]
    if info["imagem"] and not info["imagem"].startswith("https://"):
        info["imagem"] = None
    return info


# ---------------- busca de novas ofertas ----------------
def palavras_chave(p):
    base = sem_acento(p["nome"])
    base = re.sub(r"[^a-z0-9 ]", " ", base)
    return [w for w in base.split() if len(w) > 2 and w not in {"com", "para", "porta", "bocas", "lacrado"}]


def marcas(p):
    m = sem_acento(p.get("marcas") or "")
    m = re.sub(r"\(.*?\)", " ", m)
    return [w.strip() for w in re.split(r",| ou | e |/", m) if w.strip() and len(w.strip()) > 1]


def combina(p, titulo):
    t = sem_acento(titulo)
    chaves = palavras_chave(p)
    if chaves and not any(k in t for k in chaves):
        return False
    ms = marcas(p)
    if ms and not any(m.split()[0] in t for m in ms):
        return False
    for ruim in ("capa", "pelicula", "suporte", "filtro refil", "peca", "usado", "recondicionado", "seminovo", "vitrine"):
        if ruim in t:
            return False
    return True


def consulta(p):
    partes = [p["nome"]]
    ms = marcas(p)
    if ms and sem_acento(ms[0]) not in sem_acento(p["nome"]):
        partes.append(ms[0])
    det = (p.get("detalhes") or "").split(",")[0]
    if det and len(det) < 25:
        partes.append(det)
    return " ".join(partes)


def buscar_magalu(p):
    q = urllib.parse.quote(consulta(p))
    pagina = baixar(f"https://www.magazineluiza.com.br/busca/{q}/")
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', pagina, re.S)
    achados = []
    if m:
        dado = json.loads(m.group(1))
        for d in walk(dado):
            if not isinstance(d.get("title"), str):
                continue
            preco = d.get("price")
            if isinstance(preco, dict):
                preco = preco.get("bestPrice") or preco.get("price")
            preco = num(preco)
            path = d.get("url") or d.get("path")
            if not preco or not isinstance(path, str):
                continue
            url = path if path.startswith("http") else "https://www.magazineluiza.com.br/" + path.lstrip("/")
            img = d.get("image")
            if isinstance(img, str):
                img = img.replace("{w}", "600").replace("{h}", "450")
                if img.startswith("//"):
                    img = "https:" + img
            seller = d.get("seller")
            vend = seller.get("description") if isinstance(seller, dict) else None
            achados.append({"loja": "Magazine Luiza", "vendedor": vend if vend and "magalu" not in sem_acento(vend) and "magazine" not in sem_acento(vend) else None,
                            "titulo": d["title"], "preco": preco, "url": url.split("?")[0],
                            "imagem": img if isinstance(img, str) and img.startswith("https://") else None})
    return achados


def buscar_ml(p):
    q = urllib.parse.quote(consulta(p).replace(" ", "-"))
    pagina = baixar(f"https://lista.mercadolivre.com.br/{q}_NoIndex_True")
    achados = []
    for bloco in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', pagina, re.S | re.I):
        try:
            dado = json.loads(html.unescape(bloco), strict=False)
        except Exception:  # noqa: BLE001
            continue
        for d in walk(dado):
            if d.get("@type") != "Product":
                continue
            ofs = d.get("offers") or {}
            ofs = ofs if isinstance(ofs, dict) else (ofs[0] if ofs else {})
            preco, url = num(ofs.get("price")), ofs.get("url") or d.get("url")
            img = d.get("image")
            if isinstance(img, list):
                img = img[0] if img else None
            if preco and isinstance(url, str):
                achados.append({"loja": "Mercado Livre", "vendedor": None, "titulo": d.get("name", ""), "preco": preco,
                                 "url": url.split("#")[0].split("?")[0], "imagem": img if isinstance(img, str) and img.startswith("https://") else None})
    return achados


# ---------------- principal ----------------
def brl(v):
    return avisos.brl(v)


def main():
    prods = json.load(open("data/produtos.json", encoding="utf-8")).get("produtos", [])
    try:
        dados = json.load(open("data/ofertas.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        dados = {}
    itens = dados.setdefault("itens", {})
    alertas = dados.setdefault("alertas", [])
    ids = {p["id"] for p in prods}
    for k in list(itens):
        if k not in ids:
            del itens[k]
    novos_alertas = []

    # descoberta só de hora em hora (minuto < 15) ou para itens sem oferta
    hora_de_descobrir = AGORA.minute < 15

    for p in prods:
        if p.get("ativo") is False:
            continue
        it = itens.setdefault(p["id"], {"ofertas": [], "historico": []})
        antes = min((o["preco"] for o in it["ofertas"] if o.get("preco")), default=None)

        # 1) reconfere ofertas conhecidas
        validas = []
        for o in it["ofertas"]:
            if not confiavel(o.get("url", "")):
                continue
            try:
                info = ler_produto(baixar(o["url"]))
                log["verificados"] += 1
                if info["esgotado"]:
                    continue
                if info["preco"] and (not o.get("preco") or 0.4 < info["preco"] / o["preco"] < 1.6):
                    if info["preco"] != o.get("preco"):
                        log["atualizados"] += 1
                    o["preco"] = round(info["preco"], 2)
                    o["verificado"] = True
                    o["encontradoEm"] = ISO
                if info["imagem"] and not o.get("imagem"):
                    o["imagem"] = info["imagem"]
                    log["fotos"] += 1
            except Exception as e:  # noqa: BLE001
                log["falhas"].append({"produto": p["id"], "loja": o.get("loja"), "motivo": str(e)[:80]})
            validas.append(o)
            time.sleep(1)

        # 2) procura novas ofertas
        if not validas or len(validas) < 3 and hora_de_descobrir:
            for busca in (buscar_magalu, buscar_ml):
                try:
                    for a in busca(p):
                        if not confiavel(a["url"]) or not combina(p, a["titulo"]):
                            continue
                        if any(v["url"] == a["url"] for v in validas):
                            continue
                        a.update(observacao="", verificado=False, encontradoEm=ISO)
                        validas.append(a)
                        log["descobertas"] += 1
                except Exception as e:  # noqa: BLE001
                    log["falhas"].append({"produto": p["id"], "loja": busca.__name__, "motivo": str(e)[:80]})
                time.sleep(1)

        validas.sort(key=lambda o: o.get("preco") or 1e12)
        # mantém as 5 melhores, sem repetir o mesmo anúncio
        vistos, top = set(), []
        for o in validas:
            if o["url"] in vistos:
                continue
            vistos.add(o["url"])
            top.append(o)
        it["ofertas"] = top[:5]
        if not it["ofertas"]:
            it["ultimaBusca"] = ISO
            continue
        it["ultimaBusca"] = ISO
        b = it["ofertas"][0]
        agora = b["preco"]

        # histórico (um ponto por dia, menor preço)
        h = it.setdefault("historico", [])
        if h and h[-1].get("d") == HOJE:
            if agora < h[-1]["p"]:
                h[-1] = {"d": HOJE, "p": agora, "loja": b["loja"]}
        else:
            h.append({"d": HOJE, "p": agora, "loja": b["loja"]})
        it["historico"] = h[-180:]

        # alertas
        alvo = p.get("precoAlvo")
        criar = False
        if alvo and agora <= alvo and (antes is None or antes > alvo or agora <= antes * 0.97):
            criar = True
        if antes and agora <= antes * 0.92:
            criar = True
        if criar:
            extra = f" ({brl(alvo - agora)} abaixo do alvo)" if alvo and agora <= alvo else f" (caiu {round((1 - agora / antes) * 100)}%)"
            a = {"id": f"{p['id']}-{AGORA.strftime('%Y%m%d%H%M')}", "produtoId": p["id"], "produtoNome": p["nome"],
                 "texto": f"{p['nome']}: {b['titulo'][:70]} por {brl(agora)} na {b['loja']}{extra}",
                 "preco": agora, "loja": b["loja"], "url": b["url"], "criadoEm": ISO}
            alertas.append(a)
            novos_alertas.append(a)

    dados["alertas"] = sorted(alertas, key=lambda a: a.get("criadoEm", ""))[-200:]
    dados["atualizadoEm"] = ISO
    dados["status"] = {"resumo": f"{log['verificados']} páginas conferidas, {log['descobertas']} ofertas novas",
                       "produtosVerificados": sum(1 for p in prods if p.get("ativo") is not False),
                       "alertas": len(novos_alertas)}
    log["alertas"] = len(novos_alertas)
    log["falhas"] = log["falhas"][:30]
    json.dump(dados, open("data/ofertas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(log, open("data/checagem.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(log, ensure_ascii=False)[:800])

    # Telegram
    cfg = {}
    try:
        cfg = json.load(open("data/config.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    if novos_alertas and cfg.get("notificacoes") is not False:
        partes = [f"🔥 {a['texto']}\n{a['url']}" for a in novos_alertas[:6]]
        extra = f"\n\n+{len(novos_alertas) - 6} outros no app" if len(novos_alertas) > 6 else ""
        avisos.enviar("🛒 Econolife Promos\n\n" + "\n\n".join(partes) + extra + "\n\n" + avisos.SITE)


if __name__ == "__main__":
    main()

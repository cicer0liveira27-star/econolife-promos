"""Robô gratuito do Econolife Promos (roda no GitHub Actions a cada 15 min, sem usar o Claude).

As grandes lojas bloqueiam os servidores do GitHub, então o robô usa o Buscapé (e o Zoom como reserva),
que já comparam Americanas, Magalu, Amazon, Casas Bahia, Fast Shop etc. Para cada produto da lista:
  1. Busca no Buscapé e escolhe os anúncios que batem com nome, marca e detalhes.
  2. Abre a página de cada anúncio e lê as ofertas por loja (preço, foto, link).
  3. Fica só com lojas confiáveis, atualiza histórico, cria alertas e avisa no Telegram.
"""
import html, json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import enviar_whatsapp as avisos  # noqa: E402

AGORA = datetime.now(timezone.utc)
ISO = AGORA.strftime("%Y-%m-%dT%H:%M:%SZ")
HOJE = (AGORA - timedelta(hours=3)).strftime("%Y-%m-%d")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")
FONTES = ["https://www.buscape.com.br", "https://www.zoom.com.br"]

# Lojas aceitas (nome como aparece no Buscapé, sem acento e minúsculo)
LOJAS_OK = ["americanas", "magazine luiza", "magalu", "amazon", "casas bahia", "ponto", "pontofrio", "extra",
            "submarino", "shoptime", "carrefour", "fast shop", "kabum", "girafa", "mercado livre", "leroy merlin",
            "telhanorte", "c&c", "obramax", "ferreira costa", "madeiramadeira", "tok&stok", "tok stok", "mobly",
            "webcontinental", "brastemp", "consul", "electrolux", "loja electrolux", "midea", "samsung", "lg",
            "apple", "dako", "philco", "britania", "tramontina", "portobello", "eliane", "balaroti", "colombo",
            "lojas colombo", "havan", "efacil", "zema"]

log = {"quando": ISO, "fonte": None, "buscas": 0, "paginas": 0, "ofertas": 0, "fotos": 0, "alertas": 0,
       "semResultado": [], "falhas": [], "debug": {}}


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9",
                                               "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def next_data(pg):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', pg, re.S)
    return json.loads(m.group(1)) if m else {}


def sa(s):
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def loja_ok(nome):
    n = sa(nome).replace("!", "").strip()
    return any(n == l or n.startswith(l + " ") or n.endswith(" " + l) for l in LOJAS_OK)


# ---------------- filtros do produto ----------------
PARADAS = {"com", "para", "de", "da", "do", "e", "ou", "a", "o", "cor", "porta", "bocas", "lacrado", "linha", "novo", "original"}


def tokens(s):
    return [w for w in re.sub(r"[^a-z0-9 ]", " ", sa(s)).split() if w not in PARADAS and len(w) > 1]


def marcas(p):
    m = re.sub(r"\(.*?\)", " ", sa(p.get("marcas") or ""))
    return [w.strip() for w in re.split(r",| ou | e |/", m) if len(w.strip()) > 1]


def consultas(p):
    """Busca principal e, de reserva, uma por marca com o nome enxuto."""
    ms = marcas(p)
    enxuto = " ".join(w for w in tokens(p["nome"]))
    qs = [p["nome"] + (" " + ms[0] if len(ms) == 1 and ms[0] not in sa(p["nome"]) else "")]
    qs += [f"{enxuto} {m}" for m in ms[:4] if m not in enxuto]
    if enxuto and enxuto not in qs:
        qs.append(enxuto)
    if "maquina lavar" in enxuto:
        qs += [f"lavadora frontal {m}" for m in ms[:3]] or ["lavadora frontal"]
    return list(dict.fromkeys(q.strip() for q in qs if q.strip()))


def combina(p, titulo):
    t = sa(titulo)
    chave = [w for w in tokens(p["nome"]) if len(w) > 2 and not w.isdigit()]
    if "lavar" in chave:
        chave.append("lavadora")
    if chave and not any(w in t for w in chave):
        return False
    ms = marcas(p)
    implicita = {"iphone": "apple", "ipad": "apple", "macbook": "apple", "airpods": "apple", "galaxy": "samsung"}
    if ms and not any(marca_no_titulo(m, titulo) or any(k in t and v == m.split()[0] for k, v in implicita.items()) for m in ms):
        return False
    for n in re.findall(r"\b\d+\b", sa(p["nome"])):
        if not re.search(r"(?<![\d])" + n + r"(?![\d])", t):
            return False
    # palavra que está no nome E nos detalhes é obrigatória (ex.: "frontal" na lavadora)
    for w in set(tokens(p["nome"])) & set(tokens(p.get("detalhes") or "")):
        if len(w) > 2 and not w.isdigit() and w not in t:
            return False
    nome_sa = sa(p["nome"])
    for variante in ("pro", "max", "plus", "mini", "ultra", "lite", "fe"):
        if re.search(r"\b" + variante + r"\b", t) and not re.search(r"\b" + variante + r"\b", nome_sa) and re.search(r"\b(iphone|galaxy|ipad|xiaomi|redmi|moto)\b", t):
            return False
    for ruim in ("capa ", "pelicula", "suporte", "refil", "usado", "recondicionado", "seminovo", "vitrine", "peca "):
        if ruim in t + " ":
            return False
    return True


def nota_detalhe(p, titulo):
    """Quantos detalhes pedidos (cor, tamanho...) aparecem no título."""
    t = sa(titulo)
    return sum(1 for w in tokens(p.get("detalhes") or "") if len(w) > 1 and w in t)


# ---------------- coleta ----------------
def buscar_uma(fonte, q):
    nd = next_data(baixar(f"{fonte}/search?q={urllib.parse.quote(q)}"))
    log["buscas"] += 1
    hits = (((nd.get("props") or {}).get("initialReduxState") or {}).get("hits") or {}).get("hits") or []
    return [h for h in hits if h.get("type") == "product" and h.get("url") and h.get("name")]


def buscar(fonte, p):
    vistos, todos = set(), []
    for i, q in enumerate(consultas(p)):
        hits = buscar_uma(fonte, q)
        for h in hits:
            if h["url"] not in vistos:
                vistos.add(h["url"])
                todos.append(h)
        if i == 0 and any(combina(p, h["name"]) for h in hits) and len(marcas(p)) <= 1:
            break
        time.sleep(1)
    return todos


def ofertas_do_produto(fonte, hit):
    nd = next_data(baixar(fonte + hit["url"]))
    log["paginas"] += 1
    ol = ((((nd.get("props") or {}).get("initialReduxState") or {}).get("offers") or {}).get("offerList")) or []
    saida = []
    for o in ol:
        preco = o.get("price")
        loja = (o.get("sellerName") or "").strip()
        if not isinstance(preco, (int, float)) or preco <= 0 or not loja_ok(loja) or o.get("sellerIsMarketplace"):
            continue
        img = o.get("imageUrl") or hit.get("image")
        saida.append({
            "loja": loja.replace("KaBuM!", "KaBuM"), "vendedor": None,
            "titulo": (o.get("name") or hit["name"])[:120], "preco": round(float(preco), 2),
            "url": f"{fonte}/lead?oid={o.get('id')}&channel=1",
            "pagina": fonte + hit["url"],
            "imagem": img if isinstance(img, str) and img.startswith("https://") else None,
            "observacao": f"ou {o.get('numParcels')}x de {avisos.brl(o['parcelValue'])}" if o.get("numParcels", 0) > 1 and o.get("parcelValue") else "",
            "verificado": True, "encontradoEm": ISO,
        })
    return saida


# ---------------- modelos específicos ----------------
UNIDADE = re.compile(r"^\d+(l|w|v|kg|cm|gb|mm|pol|btu|hz)$")
GENERICAS = {"geladeira", "refrigerador", "cooktop", "micro", "ondas", "ventilador", "tecnologia", "funcao", "painel",
             "integrado", "acendimento", "automatico", "efficient", "com", "cor", "frost", "free", "duplex", "bivolt", "smartbivolt", "inox", "preto", "look", "espelhado", "mesa", "vidro", "gas", "glp"}


def codigo_modelo(m):
    """Código do modelo (ex.: IF44S, TF70S, KE4GR, BVT301), se houver."""
    for w in re.findall(r"[A-Za-z0-9]+", m):
        wl = w.lower()
        if re.search(r"\d", wl) and re.search(r"[a-z]", wl) and 4 <= len(wl) <= 12 and not UNIDADE.match(wl):
            return wl
    return None


def combina_modelo(modelo, titulo):
    t = sa(titulo).replace("-", "").replace(" ", "")
    cod = codigo_modelo(modelo)
    if cod:
        return cod in t
    ws = [w for w in tokens(modelo) if not UNIDADE.match(w) and not w.isdigit()]
    raras = [w for w in ws if w not in GENERICAS]
    tt = sa(titulo)
    return bool(raras) and all(w in tt for w in raras[:2])


def consulta_modelo(modelo, p):
    cod = codigo_modelo(modelo)
    marca = next((m for m in marcas(p) if m.split()[0] in sa(modelo)), None) or next(
        (w for w in ("electrolux", "brastemp", "consul", "midea", "samsung", "lg", "dako", "britania", "philco", "mondial", "apple") if w in sa(modelo)), "")
    if cod:
        return f"{marca} {cod}".strip()
    ws = [w for w in tokens(modelo) if not UNIDADE.match(w) and not w.isdigit()]
    raras = [w for w in ws if w not in GENERICAS]
    return " ".join(([ws[0]] if ws else []) + raras[:2])


def coletar_modelos(p, fontes=None):
    modelos = [m.strip() for m in p.get("modelos") or [] if m.strip()]
    for fonte in fontes or FONTES:
        ofertas, achou_algum, erro = [], 0, False
        for modelo in modelos:
            try:
                hits = buscar_uma(fonte, consulta_modelo(modelo, p))
            except Exception as e:  # noqa: BLE001
                log["falhas"].append({"produto": p["id"], "onde": fonte, "motivo": str(e)[:80]})
                erro = True
                break
            bons = [h for h in hits if combina_modelo(modelo, h["name"])]
            bons.sort(key=lambda h: h.get("price") or 1e12)
            achou_algum += bool(bons)
            for h in bons[:2]:
                try:
                    for o in ofertas_do_produto(fonte, h):
                        o["modelo"] = modelo
                        ofertas.append(o)
                except Exception as e:  # noqa: BLE001
                    log["falhas"].append({"produto": p["id"], "onde": h["url"][:60], "motivo": str(e)[:80]})
                time.sleep(1)
            time.sleep(1)
        if erro:
            continue
        log["debug"][p["id"]] = {"modelos": len(modelos), "modelosAchados": achou_algum, "ofertas": len(ofertas)}
        return ofertas, fonte
    return None, None


# ---------------- links colados pelo usuário ----------------
NOME_LOJA = {"magazineluiza": "Magazine Luiza", "mercadolivre": "Mercado Livre", "amazon": "Amazon", "casasbahia": "Casas Bahia",
             "americanas": "Americanas", "pontofrio": "Ponto", "ponto": "Ponto", "extra": "Extra", "fastshop": "Fast Shop",
             "kabum": "KaBuM", "carrefour": "Carrefour", "leroymerlin": "Leroy Merlin", "electrolux": "Electrolux",
             "brastemp": "Brastemp", "consul": "Consul", "webcontinental": "Webcontinental", "samsung": "Samsung",
             "britania": "Britânia", "dako": "Dako", "midea": "Midea", "shoptime": "Shoptime", "submarino": "Submarino"}


def loja_do_link(u):
    h = (urllib.parse.urlparse(u).hostname or "").replace("www.", "")
    for k, v in NOME_LOJA.items():
        if k in h.replace("-", ""):
            return v
    return h.split(".")[0].capitalize()


def ler_pagina_loja(pagina):
    """Preço/foto/título de uma página de produto (JSON-LD ou metatags)."""
    info = {"preco": None, "imagem": None, "titulo": None, "esgotado": False}
    for bloco in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', pagina, re.S | re.I):
        try:
            dado = json.loads(html.unescape(bloco.strip()), strict=False)
        except Exception:  # noqa: BLE001
            continue
        pilha = [dado]
        while pilha:
            d = pilha.pop()
            if isinstance(d, list):
                pilha += d
                continue
            if not isinstance(d, dict):
                continue
            pilha += [v for v in d.values() if isinstance(v, (dict, list))]
            tipo = d.get("@type")
            if "Product" not in (tipo if isinstance(tipo, list) else [tipo]):
                continue
            info["titulo"] = info["titulo"] or d.get("name")
            img = d.get("image")
            img = img[0] if isinstance(img, list) and img else img
            img = img.get("url") if isinstance(img, dict) else img
            info["imagem"] = info["imagem"] or (img if isinstance(img, str) and img.startswith("https://") else None)
            ofs = d.get("offers")
            ofs = ofs if isinstance(ofs, list) else [ofs] if ofs else []
            for of in ofs:
                if not isinstance(of, dict):
                    continue
                v = of.get("price") or of.get("lowPrice")
                try:
                    v = float(str(v).replace(",", "."))
                except (TypeError, ValueError):
                    v = None
                if v and v > 0:
                    info["preco"] = min(info["preco"] or v, v)
                if "OutOfStock" in str(of.get("availability", "")):
                    info["esgotado"] = True
    return info


def slug_do_link(u):
    path = urllib.parse.unquote(urllib.parse.urlparse(u).path)
    partes = [x for x in re.split(r"[/]", path) if x and not re.fullmatch(r"(p|dp|mlb|produto|item)", x, re.I)]
    melhor = max(partes, key=lambda x: x.count("-"), default="")
    return re.sub(r"[-_]+", " ", melhor)


def coletar_links(p):
    ofertas = []
    for link in [l.strip() for l in p.get("links") or [] if l.strip().startswith("http")]:
        host = (urllib.parse.urlparse(link).hostname or "").replace("www.", "")
        try:
            # 1) página de produto do Buscapé/Zoom: lê as ofertas de todas as lojas
            if host in ("buscape.com.br", "zoom.com.br") and "/search" not in link:
                fonte = "https://www." + host
                path = urllib.parse.urlparse(link).path
                for o in ofertas_do_produto(fonte, {"url": path, "name": "", "image": None}):
                    o["modelo"] = link
                    ofertas.append(o)
                continue
            # 2) link de loja: tenta abrir direto
            try:
                info = ler_pagina_loja(baixar(link))
                log["paginas"] += 1
                if info["preco"] and not info["esgotado"]:
                    ofertas.append({"loja": loja_do_link(link), "vendedor": None, "titulo": (info["titulo"] or slug_do_link(link))[:120],
                                    "preco": round(info["preco"], 2), "url": link, "imagem": info["imagem"], "observacao": "seu link",
                                    "verificado": True, "encontradoEm": ISO, "modelo": link})
                    continue
            except Exception:  # noqa: BLE001
                pass  # loja bloqueou o robô: procura o mesmo produto no Buscapé
            # 3) procura o produto do link no Buscapé pelo nome que está no endereço
            nome = slug_do_link(link)
            if not nome:
                continue
            ref = {"nome": nome, "marcas": "", "detalhes": ""}
            cod = codigo_modelo(nome)
            hits = buscar_uma(FONTES[0], consulta_modelo(nome, ref) if cod else " ".join(tokens(nome)[:7]))
            def parecido(h):
                return combina_modelo(nome, h["name"])
            bons = sorted([h for h in hits if parecido(h)], key=lambda h: h.get("price") or 1e12)[:2]
            for h in bons:
                for o in ofertas_do_produto(FONTES[0], h):
                    o["modelo"] = link
                    ofertas.append(o)
                time.sleep(1)
            if not bons:
                log["falhas"].append({"produto": p["id"], "onde": host, "motivo": "produto do link não encontrado"})
        except Exception as e:  # noqa: BLE001
            log["falhas"].append({"produto": p["id"], "onde": host, "motivo": str(e)[:80]})
        time.sleep(1)
    return ofertas


def marca_no_titulo(marca, titulo):
    from difflib import SequenceMatcher
    m = sa(marca).split()[0] if sa(marca).split() else ""
    if not m:
        return True
    if m in sa(titulo):
        return True
    return any(SequenceMatcher(None, m, w).ratio() >= 0.8 for w in tokens(titulo))  # aceita "Eletrolux" ~ "Electrolux"


def guarda(p, titulo):
    """Trava final: marca pedida, números do nome (ex.: 4 bocas) e nada de acessório."""
    t = sa(titulo)
    ms = marcas(p)
    if ms and not any(marca_no_titulo(m, titulo) for m in ms):
        return False
    for n in re.findall(r"\b\d+\b", sa(p["nome"])):
        if not re.search(r"(?<!\d)" + n + r"(?!\d)", t):
            return False
    return not any(r in t + " " for r in ("capa ", "pelicula", "suporte", "refil", "usado", "recondicionado", "seminovo", "vitrine", "peca "))


def coletar(p):
    extras = coletar_links(p) if p.get("links") else []
    ofertas, fonte = coletar_base(p) if (p.get("modelos") or not p.get("links")) else ([], FONTES[0])
    if ofertas is None and not extras:
        return None, None
    todas = (ofertas or []) + extras
    boas = [o for o in todas if guarda(p, o["titulo"])]
    if len(boas) < len(todas):
        log["debug"].setdefault(p["id"], {})["barradasNaTrava"] = len(todas) - len(boas)
    return boas, fonte or FONTES[0]


def coletar_base(p):
    """Consulta Buscapé e Zoom e junta as ofertas (o menor preço por loja fica depois)."""
    todas, fonte_ok = [], None
    for f in FONTES:
        ofs, fonte = (coletar_modelos(p, [f]) if p.get("modelos") else coletar_geral(p, [f]))
        if ofs is None:
            continue
        fonte_ok = fonte_ok or fonte
        todas += ofs
        time.sleep(1)
    return (todas, fonte_ok) if fonte_ok else (None, None)


def coletar_geral(p, fontes=None):
    for fonte in fontes or FONTES:
        try:
            hits = buscar(fonte, p)
        except Exception as e:  # noqa: BLE001
            log["falhas"].append({"produto": p["id"], "onde": fonte, "motivo": str(e)[:80]})
            continue
        bons = [h for h in hits if combina(p, h["name"])]
        if not bons:
            log["debug"][p["id"]] = {"hits": len(hits), "combinam": 0, "exemplos": [h["name"][:60] for h in hits[:4]]}
            return [], fonte
        melhor_nota = max(nota_detalhe(p, h["name"]) for h in bons)
        if melhor_nota > 0:
            bons = [h for h in bons if nota_detalhe(p, h["name"]) == melhor_nota] or bons
        bons.sort(key=lambda h: h.get("price") or 1e12)
        ofertas = []
        for h in bons[:4]:
            try:
                for o in ofertas_do_produto(fonte, h):
                    if combina(p, o["titulo"]) or combina(p, h["name"]) and not re.search(r"\d", sa(p["nome"])) and any(w in sa(o["titulo"]) for w in tokens(p["nome"])):
                        ofertas.append(o)
            except Exception as e:  # noqa: BLE001
                log["falhas"].append({"produto": p["id"], "onde": h["url"][:60], "motivo": str(e)[:80]})
            time.sleep(1)
        if (p.get("detalhes") or "").strip():
            com_detalhe = [o for o in ofertas if nota_detalhe(p, o["titulo"]) > 0]
            if com_detalhe:
                ofertas = com_detalhe
            else:
                for o in ofertas:
                    o["observacao"] = ("confira cor/tamanho · " + o["observacao"]).strip(" ·")
        log["debug"][p["id"]] = {"hits": len(hits), "combinam": len(bons), "ofertas": len(ofertas)}
        return ofertas, fonte
    return None, None


# ---------------- links para conferir manualmente ----------------
LOJAS_MANUAIS = [
    ("Amazon", "https://www.amazon.com.br/s?k={q}"),
    ("Mercado Livre", "https://lista.mercadolivre.com.br/{d}"),
    ("Magalu", "https://www.magazineluiza.com.br/busca/{q}/"),
    ("Casas Bahia", "https://www.casasbahia.com.br/{d}/b"),
    ("Google Shopping", "https://www.google.com/search?tbm=shop&hl=pt-BR&gl=br&q={q}"),
]
LOJAS_OBRA = [("Leroy Merlin", "https://www.leroymerlin.com.br/search?term={q}")]


def termo_busca(p, modelo=None):
    if modelo:
        return consulta_modelo(modelo, p)
    ms = marcas(p)
    t = p["nome"]
    if len(ms) == 1 and ms[0] not in sa(t):
        t += " " + ms[0]
    return t


def links_manuais(p, modelo=None):
    q = termo_busca(p, modelo)
    lojas = LOJAS_MANUAIS + (LOJAS_OBRA if p.get("categoria") in ("Construção", "Pisos e revestimentos", "Iluminação") else [])
    return [(n, u.format(q=urllib.parse.quote_plus(q), d=urllib.parse.quote("-".join(q.split())))) for n, u in lojas]


def h(s):
    return html.escape(str(s or ""), quote=True)


def bloco_links(p, modelo=None):
    return " · ".join(f'<a href="{h(u)}">{h(n)}</a>' for n, u in links_manuais(p, modelo))


# ---------------- principal ----------------
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
    novos = []

    # ofertas do robô do PC (Amazon, Mercado Livre, Magalu, Casas Bahia e links colados), se forem recentes
    pc = {}
    try:
        pcd = json.load(open("data/ofertas_pc.json", encoding="utf-8"))
        idade = (AGORA - datetime.fromisoformat(pcd["atualizadoEm"].replace("Z", "+00:00"))).total_seconds()
        if idade <= 90 * 60:
            pc = pcd.get("itens") or {}
        log["pc"] = {"atualizadoEm": pcd.get("atualizadoEm"), "usado": bool(pc)}
    except Exception:  # noqa: BLE001
        log["pc"] = {"usado": False}

    for p in prods:
        if p.get("ativo") is False:
            continue
        it = itens.setdefault(p["id"], {"ofertas": [], "historico": []})
        antes = min((o["preco"] for o in it.get("ofertas", []) if o.get("preco")), default=None)
        ofertas, fonte = coletar(p)
        do_pc = [o for o in pc.get(p["id"], []) if isinstance(o.get("preco"), (int, float)) and guarda(p, o.get("titulo", ""))]
        if do_pc:
            ofertas = (ofertas or []) + do_pc
        log["fonte"] = log["fonte"] or fonte
        it["ultimaBusca"] = ISO
        if ofertas is None:          # fonte fora do ar: mantém o que já tinha
            continue
        if not ofertas:
            log["semResultado"].append(p["id"])
            it["ofertas"] = [o for o in it.get("ofertas", []) if guarda(p, o.get("titulo", ""))]
            if p.get("modelos") or p.get("links"):
                ok = set(p.get("modelos") or []) | set(p.get("links") or [])
                it["ofertas"] = [o for o in it.get("ofertas", []) if o.get("modelo") in ok]
            else:
                it["ofertas"] = [o for o in it.get("ofertas", []) if combina(p, o.get("titulo", ""))]
            continue
        ofertas.sort(key=lambda o: o["preco"])
        vistos, top = set(), []
        for o in ofertas:            # uma oferta por loja (a mais barata)
            chave = sa(o["loja"])
            if chave in vistos:
                continue
            vistos.add(chave)
            top.append(o)
        it["ofertas"] = top[:5]
        log["ofertas"] += len(it["ofertas"])
        log["fotos"] += sum(1 for o in it["ofertas"] if o.get("imagem"))
        b = it["ofertas"][0]
        agora = b["preco"]

        h = it.setdefault("historico", [])
        if h and h[-1].get("d") == HOJE:
            if agora < h[-1]["p"]:
                h[-1] = {"d": HOJE, "p": agora, "loja": b["loja"]}
        else:
            h.append({"d": HOJE, "p": agora, "loja": b["loja"]})
        it["historico"] = h[-180:]

        alvo = p.get("precoAlvo")
        criar = bool(alvo and agora <= alvo and (antes is None or antes > alvo or agora <= antes * 0.97))
        if antes and agora <= antes * 0.92:
            criar = True
        if criar:
            extra = f" ({avisos.brl(alvo - agora)} abaixo do alvo)" if alvo and agora <= alvo else f" (caiu {round((1 - agora / antes) * 100)}%)"
            a = {"id": f"{p['id']}-{AGORA.strftime('%Y%m%d%H%M')}", "produtoId": p["id"], "produtoNome": p["nome"],
                 "texto": f"{p['nome']}: {b['titulo'][:70]} por {avisos.brl(agora)} na {b['loja']}{extra}",
                 "preco": agora, "loja": b["loja"], "url": b["url"], "criadoEm": ISO, "modelo": b.get("modelo")}
            alertas.append(a)
            novos.append(a)
        time.sleep(1)

    dados["alertas"] = sorted(alertas, key=lambda a: a.get("criadoEm", ""))[-200:]
    dados["atualizadoEm"] = ISO
    dados["status"] = {"resumo": f"{log['ofertas']} ofertas de lojas confiáveis via Buscapé e Zoom",
                       "produtosVerificados": sum(1 for p in prods if p.get("ativo") is not False), "alertas": len(novos)}
    log["alertas"] = len(novos)
    log["falhas"] = log["falhas"][:30]
    json.dump(dados, open("data/ofertas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(log, open("data/checagem.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(log, ensure_ascii=False)[:1500])

    cfg = {}
    try:
        cfg = json.load(open("data/config.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    porid = {p["id"]: p for p in prods}
    if novos and cfg.get("notificacoes") is not False:
        partes = []
        for a in novos[:6]:
            p = porid.get(a["produtoId"], {"nome": a["produtoNome"], "marcas": ""})
            mod = a.get("modelo") if a.get("modelo") in (p.get("modelos") or []) else None
            partes.append(f"🔥 <b>{h(a['texto'])}</b>\n👉 <a href=\"{h(a['url'])}\">Abrir oferta na {h(a['loja'])}</a>\n"
                          f"🔎 Conferir você mesmo: {bloco_links(p, mod)}")
        extra = f"\n\n+{len(novos) - 6} outros no app" if len(novos) > 6 else ""
        avisos.enviar_telegram("🛒 <b>Econolife Promos</b>\n\n" + "\n\n".join(partes) + extra +
                               f"\n\n<a href=\"{h(avisos.SITE)}\">Abrir o app</a>", html_mode=True)

    # resumo diário (uma vez por dia, a partir das 9h de Brasília) com os links para conferir à mão
    hora_br = (AGORA - timedelta(hours=3)).hour
    if hora_br >= 9 and dados.get("ultimoResumo") != HOJE and cfg.get("notificacoes") is not False and avisos.TG_TOKEN:
        blocos = []
        for p in prods:
            if p.get("ativo") is False:
                continue
            of = (itens.get(p["id"]) or {}).get("ofertas") or []
            b = of[0] if of else None
            linha = f"<b>{h(p['nome'])}</b>"
            if b:
                alvo = p.get("precoAlvo")
                marca = " ✅" if alvo and b["preco"] <= alvo else ""
                linha += f"\n🤖 Robô achou: <a href=\"{h(b['url'])}\">{h(avisos.brl(b['preco']))} na {h(b['loja'])}</a>{marca}"
                if alvo:
                    linha += f" · alvo {h(avisos.brl(alvo))}"
            else:
                linha += "\n🤖 Robô ainda não achou"
            mods = p.get("modelos") or [None]
            for m in mods[:3]:
                rot = (codigo_modelo(m) or "").upper() if m else ""
                linha += f"\n🔎 {h(rot + ': ') if rot else ''}{bloco_links(p, m)}"
            blocos.append(linha)
        for i in range(0, len(blocos), 5):
            cab = "📋 <b>Resumo do dia — Econolife Promos</b>\n\n" if i == 0 else ""
            avisos.enviar_telegram(cab + "\n\n".join(blocos[i:i + 5]), html_mode=True)
            time.sleep(1)
        dados["ultimoResumo"] = HOJE
        json.dump(dados, open("data/ofertas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

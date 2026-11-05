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
    if ms and not any(m.split()[0] in t or any(k in t and v == m.split()[0] for k, v in implicita.items()) for m in ms):
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


def coletar(p):
    for fonte in FONTES:
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

    for p in prods:
        if p.get("ativo") is False:
            continue
        it = itens.setdefault(p["id"], {"ofertas": [], "historico": []})
        antes = min((o["preco"] for o in it.get("ofertas", []) if o.get("preco")), default=None)
        ofertas, fonte = coletar(p)
        log["fonte"] = log["fonte"] or fonte
        it["ultimaBusca"] = ISO
        if ofertas is None:          # fonte fora do ar: mantém o que já tinha
            continue
        if not ofertas:
            log["semResultado"].append(p["id"])
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
                 "preco": agora, "loja": b["loja"], "url": b["url"], "criadoEm": ISO}
            alertas.append(a)
            novos.append(a)
        time.sleep(1)

    dados["alertas"] = sorted(alertas, key=lambda a: a.get("criadoEm", ""))[-200:]
    dados["atualizadoEm"] = ISO
    dados["status"] = {"resumo": f"{log['ofertas']} ofertas de lojas confiáveis via {(log['fonte'] or '').replace('https://www.', '')}",
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
    if novos and cfg.get("notificacoes") is not False:
        partes = [f"🔥 {a['texto']}\n{a['url']}" for a in novos[:6]]
        extra = f"\n\n+{len(novos) - 6} outros no app" if len(novos) > 6 else ""
        avisos.enviar("🛒 Econolife Promos\n\n" + "\n\n".join(partes) + extra + "\n\n" + avisos.SITE)


if __name__ == "__main__":
    main()

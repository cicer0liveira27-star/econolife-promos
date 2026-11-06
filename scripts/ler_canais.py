"""Leitor de canais de promoção do Telegram (Pelando, Promobit e outros) — grátis, sem login.

Lê a página pública t.me/s/<canal> de cada canal da lista, procura nos posts novos os produtos
da sua lista (mesmos filtros de marca/modelo do robô) e, quando acha, manda no seu Telegram
no formato de oferta e registra em data/ofertas.json -> alertas.
Estado (último post lido por canal) fica em data/canais_estado.json.
"""
import html, json, os, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))
import checar_precos as rb  # noqa: E402
import enviar_whatsapp as avisos  # noqa: E402

AGORA = datetime.now(timezone.utc)
ISO = AGORA.strftime("%Y-%m-%dT%H:%M:%SZ")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"

CANAIS_PADRAO = [
    "pelando", "pelandooficial", "pelando_br", "pelandobr", "promobit", "promobitoficial", "cupons_desconto",
    "promotop", "promotopbr", "boletando", "boletandocom", "achadosdotb", "achados_do_tb", "gatry", "gatrypromo",
    "peguei_descontos", "pegueidescontos", "hardmob_promocoes", "fadadoscupons", "ninjadasofertas", "ofertaseletro",
    "eletrodomesticosemoferta", "promocoeseletro", "mundodasofertas", "ofertasdodia", "achadosdacasa", "casaeoferta",
    "ofertas_casa", "economizeja", "tecmundoofertas", "tudoemoferta",
]


def baixar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def limpar(fragmento):
    t = re.sub(r"<br\s*/?>", "\n", fragmento)
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


def ler_canal(canal, depois_de=0, paginas=3):
    """Posts do canal mais novos que depois_de (id). Retorna (titulo_canal, [posts])."""
    posts, antes, titulo = [], None, None
    for _ in range(paginas):
        pg = baixar(f"https://t.me/s/{canal}" + (f"?before={antes}" if antes else ""))
        if titulo is None:
            m = re.search(r'<meta property="og:title" content="([^"]*)"', pg)
            titulo = html.unescape(m.group(1)) if m else ""
            if "tgme_channel_info" not in pg and "tgme_widget_message" not in pg:
                return None, []  # não é canal público
        blocos = re.split(r'(?=<div class="tgme_widget_message_wrap)', pg)
        menor = None
        for b in blocos:
            m = re.search(r'data-post="([^"/]+)/(\d+)"', b)
            if not m:
                continue
            pid = int(m.group(2))
            menor = pid if menor is None else min(menor, pid)
            if pid <= depois_de:
                continue
            tm = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', b, re.S)
            texto = limpar(tm.group(1)) if tm else ""
            links = [html.unescape(u) for u in re.findall(r'<a href="(https?://[^"]+)"', tm.group(1) if tm else "")]
            foto = re.search(r"tgme_widget_message_photo_wrap[^>]*background-image:url\('([^']+)'\)", b)
            quando = re.search(r'<time datetime="([^"]+)"', b)
            posts.append({"id": pid, "texto": texto, "links": [l for l in links if "t.me/" not in l],
                          "foto": foto.group(1) if foto else None, "quando": quando.group(1) if quando else None,
                          "post": f"https://t.me/{canal}/{pid}"})
        if menor is None or menor <= depois_de + 1:
            break
        antes = menor
        time.sleep(1)
    return titulo, posts


def preco_do_post(texto):
    t = texto.replace("\xa0", " ")
    m = re.search(r"(?i)\bpor\b[^\dR]{0,12}R\$\s*([\d\.]+(?:,\d{1,2})?)", t)
    vals = []
    if m:
        vals = [m.group(1)]
    else:
        vals = [v for v in re.findall(r"R\$\s*([\d\.]+(?:,\d{1,2})?)", t)]
    nums = []
    for v in vals:
        try:
            nums.append(float(v.replace(".", "").replace(",", ".")))
        except ValueError:
            pass
    nums = [n for n in nums if n > 1]
    if not nums:
        return None
    if m:
        return nums[0]
    teto = max(nums)
    ok = [n for n in nums if n >= teto * 0.4]  # ignora parcela/frete
    return min(ok) if ok else None


def bate(p, texto):
    for modelo in p.get("modelos") or []:
        if rb.combina_modelo(modelo, texto):
            return modelo
    if p.get("modelos"):
        return None
    primeira = texto.split("\n")[0]
    for alvo_txt in (primeira, texto[:300]):
        if rb.combina(p, alvo_txt) and rb.guarda(p, alvo_txt):
            return "nome"
    return None


def main():
    prods = [p for p in json.load(open("data/produtos.json", encoding="utf-8")).get("produtos", []) if p.get("ativo") is not False]
    try:
        cfg = json.load(open("data/config.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cfg = {}
    canais = cfg.get("canais") or CANAIS_PADRAO
    try:
        estado = json.load(open("data/canais_estado.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        estado = {}
    try:
        dados = json.load(open("data/ofertas.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        dados = {"itens": {}, "alertas": []}
    alertas = dados.setdefault("alertas", [])
    recentes = {(a.get("produtoId"), a.get("post") or a.get("url")) for a in alertas}
    limite_primeira = AGORA - timedelta(hours=3)
    novos, rel = [], {"quando": ISO, "canais": {}}

    for canal in canais:
        st = estado.get(canal, {})
        if st.get("invalido") and AGORA.hour != 12:  # canal que não existe: reconfere 1x por dia
            continue
        try:
            titulo, posts = ler_canal(canal, st.get("ultimo", 0))
        except Exception as e:  # noqa: BLE001
            rel["canais"][canal] = "erro: " + str(e)[:60]
            continue
        if titulo is None:
            rel["canais"][canal] = "não existe ou não é público"
            estado[canal] = {"invalido": True}
            continue
        achou = 0
        primeira_vez = "ultimo" not in st
        for post in sorted(posts, key=lambda x: x["id"]):
            if primeira_vez and post["quando"]:
                try:
                    if datetime.fromisoformat(post["quando"]) < limite_primeira:
                        continue
                except ValueError:
                    pass
            for p in prods:
                quem = bate(p, post["texto"])
                if not quem or (p["id"], post["post"]) in recentes:
                    continue
                preco = preco_do_post(post["texto"])
                alvo = p.get("precoAlvo")
                melhor = min((o["preco"] for o in (dados.get("itens", {}).get(p["id"], {}).get("ofertas") or []) if o.get("preco")), default=None)
                # avisa se: abaixo do alvo, ou mais barato que o melhor que o robô já tinha, ou sem preço legível
                if preco and alvo and preco > alvo and (not melhor or preco >= melhor):
                    continue
                link = post["links"][0] if post["links"] else post["post"]
                titulo_post = post["texto"].split("\n")[0][:120] or p["nome"]
                a = {"id": f"{p['id']}-tg-{canal}-{post['id']}", "produtoId": p["id"], "produtoNome": p["nome"],
                     "texto": f"{p['nome']}: {titulo_post}" + (f" por {avisos.brl(preco)}" if preco else "") + f" (canal {titulo or canal})",
                     "titulo": titulo_post, "preco": preco, "loja": f"via {titulo or canal}", "url": link, "post": post["post"],
                     "imagem": post["foto"], "de": melhor if melhor and preco and melhor > preco else None, "alvo": alvo,
                     "criadoEm": ISO, "origem": "telegram"}
                alertas.append(a)
                novos.append(a)
                recentes.add((p["id"], post["post"]))
                achou += 1
        ultimo = max([p["id"] for p in posts] + [st.get("ultimo", 0)])
        estado[canal] = {"ultimo": ultimo, "titulo": titulo, "lidoEm": ISO}
        rel["canais"][canal] = f"{titulo!r}: {len(posts)} posts novos, {achou} batem"
        time.sleep(1)

    dados["alertas"] = sorted(alertas, key=lambda a: a.get("criadoEm", ""))[-200:]
    json.dump(dados, open("data/ofertas.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(estado, open("data/canais_estado.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(rel, open("data/canais_relatorio.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(rel, ensure_ascii=False)[:2000])

    if novos and cfg.get("notificacoes") is not False and avisos.TG_TOKEN:
        for a in novos[:8]:
            avisos.enviar_oferta(a)
            time.sleep(1.5)


if __name__ == "__main__":
    main()

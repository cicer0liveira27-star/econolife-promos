"""Robô do PC do Econolife Promos (Windows).

Roda no seu computador (internet de casa), onde as lojas não bloqueiam:
  - abre a busca de cada produto na Amazon, Mercado Livre, Magalu e Casas Bahia;
  - abre os links que você vinculou aos produtos no app;
  - lê preço, título, foto e link, aplica os mesmos filtros de marca/modelo do robô do GitHub;
  - envia tudo para data/ofertas_pc.json no seu repositório. O robô do GitHub junta e avisa no Telegram.

Uso:
  py robo_pc.py --configurar   (primeira vez: salva sua chave do GitHub e faz um teste)
  pyw robo_pc.py               (o que o agendador do Windows roda a cada 15 min, sem janela)
"""
import base64, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
rb = None  # filtros de marca/modelo do robô do GitHub (checar_precos.py), carregados em main()

OWNER, REPO, BRANCH = "cicer0liveira27-star", "econolife-promos", "main"
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents/"
CONFIG = os.path.join(AQUI, "config_pc.json")
LOG = os.path.join(AQUI, "robo_pc.log")
ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

LOJAS = [
    ("Amazon", lambda q: "https://www.amazon.com.br/s?k=" + urllib.parse.quote_plus(q)),
    ("Mercado Livre", lambda q: "https://lista.mercadolivre.com.br/" + urllib.parse.quote("-".join(q.split()))),
    ("Magazine Luiza", lambda q: "https://www.magazineluiza.com.br/busca/" + urllib.parse.quote_plus(q) + "/"),
    ("Casas Bahia", lambda q: "https://www.casasbahia.com.br/" + urllib.parse.quote("-".join(q.split())) + "/b"),
]

# Lê os cartões de produto de qualquer página de busca: link + título + preços próximos
EXTRATOR = r"""
() => {
  const out = [], seen = new Set();
  const temPreco = t => /R\$\s*\d/.test(t || '');
  for (const a of document.querySelectorAll('a[href]')) {
    let el = a, card = null;
    for (let i = 0; i < 7 && el; i++) { if (temPreco(el.innerText)) { card = el; break; } el = el.parentElement; }
    if (!card) continue;
    const href = a.href.split('#')[0];
    if (!/^https:/.test(href) || seen.has(href)) continue;
    const img = card.querySelector('img');
    let titulo = (a.getAttribute('title') || a.getAttribute('aria-label') || a.innerText || '').trim().split('\n')[0];
    if (titulo.length < 15) titulo = (img && img.alt) || titulo;
    if (titulo.length < 15) continue;
    const txt = card.innerText || '';
    const precos = [];
    for (const m of txt.matchAll(/(\S{0,14})\s*R\$\s*([\d\.]+(?:,\d{1,2})?)/g)) {
      const antes = (m[1] || '').toLowerCase();
      if (/x|de$|economi|desconto|off|menos|frete|cashback/.test(antes)) continue;
      const v = parseFloat(m[2].replace(/\./g, '').replace(',', '.'));
      if (v > 1) precos.push(v);
    }
    if (!precos.length) continue;
    seen.add(href);
    out.push({ titulo: titulo.slice(0, 160), url: href, precos, imagem: img ? (img.currentSrc || img.src) : null });
    if (out.length >= 40) break;
  }
  return out;
}
"""

# Página de um produto (link que você colou): JSON-LD, metatags ou o maior preço visível
EXTRATOR_PRODUTO = r"""
() => {
  const r = { titulo: document.title, preco: null, imagem: null };
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try {
      const pilha = [JSON.parse(s.textContent)];
      while (pilha.length) {
        const d = pilha.pop();
        if (Array.isArray(d)) { pilha.push(...d); continue; }
        if (!d || typeof d !== 'object') continue;
        for (const v of Object.values(d)) if (v && typeof v === 'object') pilha.push(v);
        const t = [].concat(d['@type'] || []);
        if (!t.includes('Product')) continue;
        r.titulo = d.name || r.titulo;
        let im = d.image; if (Array.isArray(im)) im = im[0]; if (im && im.url) im = im.url; r.imagem = r.imagem || im;
        for (const of of [].concat(d.offers || [])) {
          const v = parseFloat(String(of.price || of.lowPrice || '').replace(',', '.'));
          if (v > 0) r.preco = r.preco ? Math.min(r.preco, v) : v;
        }
      }
    } catch (e) {}
  }
  const meta = n => { const m = document.querySelector(`meta[property="${n}"],meta[name="${n}"],meta[itemprop="${n}"]`); return m && m.content; };
  if (!r.preco) { const v = parseFloat(String(meta('product:price:amount') || meta('price') || '').replace(',', '.')); if (v > 0) r.preco = v; }
  if (!r.imagem) r.imagem = meta('og:image');
  if (!r.preco) {
    const alvo = document.querySelector('.a-price .a-offscreen, .andes-money-amount__fraction, [data-testid="price-value"], [class*="price" i]');
    if (alvo) { const m = (alvo.innerText || alvo.textContent || '').match(/([\d\.]+(?:,\d{1,2})?)/); if (m) r.preco = parseFloat(m[1].replace(/\./g, '').replace(',', '.')); }
  }
  return r;
}
"""


def registrar(msg):
    linha = f"{datetime.now().strftime('%d/%m %H:%M')} {msg}"
    print(linha)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
        if os.path.getsize(LOG) > 400_000:
            os.replace(LOG, LOG + ".antigo")
    except OSError:
        pass


def carregar_config():
    try:
        return json.load(open(CONFIG, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def gh(metodo, caminho, token, corpo=None):
    req = urllib.request.Request(API + caminho + (f"?ref={BRANCH}" if metodo == "GET" else ""), method=metodo,
                                 data=json.dumps(corpo).encode() if corpo else None,
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json", "User-Agent": "econolife-pc"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404 and metodo == "GET":
            return None
        raise


def ler_json_repo(caminho, token):
    j = gh("GET", caminho, token)
    if not j:
        return None, None
    return json.loads(base64.b64decode(j["content"]).decode("utf-8")), j["sha"]


def gravar_json_repo(caminho, dado, token, msg):
    for _ in range(2):
        _, sha = ler_json_repo(caminho, token)
        corpo = {"message": msg, "branch": BRANCH,
                 "content": base64.b64encode((json.dumps(dado, ensure_ascii=False, indent=1) + "\n").encode()).decode()}
        if sha:
            corpo["sha"] = sha
        try:
            gh("PUT", caminho, token, corpo)
            return True
        except urllib.error.HTTPError as e:
            if e.code != 409:
                raise
            time.sleep(3)
    return False


def preco_do_cartao(precos):
    """Ignora preço riscado e valores estranhos: fica com o menor preço plausível do cartão."""
    if not precos:
        return None
    teto = max(precos)
    ok = [p for p in precos if p >= teto * 0.4]
    return min(ok) if ok else None


def termos(p):
    mods = p.get("modelos") or []
    if mods:
        return [(m, rb.consulta_modelo(m, p)) for m in mods]
    return [(None, rb.termo_busca(p))]


def aceita(p, modelo, titulo):
    if modelo:
        return rb.combina_modelo(modelo, titulo) and rb.guarda(p, titulo)
    return rb.combina(p, titulo) and rb.guarda(p, titulo)


def rodar(pagina, produtos):
    resultado = {}
    for p in produtos:
        if p.get("ativo") is False:
            continue
        achadas = []
        for modelo, q in termos(p):
            for loja, url_busca in LOJAS:
                try:
                    pagina.goto(url_busca(q), wait_until="domcontentloaded", timeout=45000)
                    cartoes = []
                    for _ in range(4):  # páginas que carregam os produtos aos poucos
                        pagina.wait_for_timeout(2000)
                        pagina.mouse.wheel(0, 1200)
                        cartoes = pagina.evaluate(EXTRATOR)
                        if len(cartoes) >= 8:
                            break
                    if not cartoes:
                        registrar(f"  {loja}: página sem produtos (título: {pagina.title()[:60]!r})")
                except Exception as e:  # noqa: BLE001
                    registrar(f"  {loja}: falhou ({str(e)[:60]})")
                    continue
                bons = []
                for c in cartoes:
                    v = preco_do_cartao(c["precos"])
                    if v and aceita(p, modelo, c["titulo"]):
                        bons.append({"loja": loja, "vendedor": None, "titulo": c["titulo"], "preco": round(v, 2), "url": c["url"],
                                     "imagem": c["imagem"] if (c.get("imagem") or "").startswith("https://") else None,
                                     "observacao": "achado pelo robô do PC", "verificado": True, "encontradoEm": ISO,
                                     "modelo": modelo})
                bons.sort(key=lambda o: o["preco"])
                achadas += bons[:2]
                registrar(f"  {p['nome'][:30]} | {loja}: {len(cartoes)} cartões, {len(bons)} batem")
                time.sleep(2)
        for link in [l for l in p.get("links") or [] if l.startswith("http")]:
            try:
                pagina.goto(link, wait_until="domcontentloaded", timeout=40000)
                pagina.wait_for_timeout(3000)
                info = pagina.evaluate(EXTRATOR_PRODUTO)
                if info.get("preco"):
                    achadas.append({"loja": rb.loja_do_link(link), "vendedor": None, "titulo": (info.get("titulo") or "")[:160],
                                    "preco": round(float(info["preco"]), 2), "url": link,
                                    "imagem": info.get("imagem") if str(info.get("imagem") or "").startswith("https://") else None,
                                    "observacao": "seu link", "verificado": True, "encontradoEm": ISO, "modelo": link})
                    registrar(f"  link {rb.loja_do_link(link)}: R$ {info['preco']}")
            except Exception as e:  # noqa: BLE001
                registrar(f"  link falhou ({str(e)[:60]})")
            time.sleep(2)
        resultado[p["id"]] = achadas
    return resultado


def main():
    cfg = carregar_config()
    if "--configurar" in sys.argv or not cfg.get("token"):
        print("Cole a sua chave do GitHub (a mesma do app, github_pat_...) e aperte Enter:")
        tok = input("> ").strip()
        if not tok:
            print("Nenhuma chave informada.")
            return
        cfg["token"] = tok
        json.dump(cfg, open(CONFIG, "w", encoding="utf-8"))
        print("Chave salva. Fazendo uma rodada de teste (pode levar alguns minutos)...")
    token = cfg["token"]
    # mantém os filtros iguais aos do robô do GitHub: baixa a versão mais nova dos scripts
    for nome, caminho in (("robo_pc.py", "pc/robo_pc.py"),):
        try:
            j = gh("GET", caminho, token)
            novo = base64.b64decode(j["content"]) if j else None
            if novo and novo != open(os.path.abspath(__file__), "rb").read():
                open(os.path.abspath(__file__), "wb").write(novo)
                registrar("Robô do PC atualizado para a versão nova (vale a partir da próxima rodada)")
        except Exception as e:  # noqa: BLE001
            registrar(f"Não atualizei o robô: {str(e)[:60]}")
    for nome in ("checar_precos.py", "enviar_whatsapp.py"):
        try:
            j = gh("GET", "scripts/" + nome, token)
            if j:
                open(os.path.join(AQUI, nome), "wb").write(base64.b64decode(j["content"]))
        except Exception as e:  # noqa: BLE001
            registrar(f"Não atualizei {nome}: {str(e)[:60]}")
    global rb
    import checar_precos as rb_mod  # noqa: E402
    rb = rb_mod
    try:
        dados, _ = ler_json_repo("data/produtos.json", token)
    except Exception as e:  # noqa: BLE001
        registrar("Não consegui ler a lista no GitHub: " + str(e)[:80])
        return
    produtos = (dados or {}).get("produtos", [])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        args = ["--disable-blink-features=AutomationControlled", "--window-position=-32000,-32000", "--window-size=1366,900"]
        perfil = os.path.join(AQUI, "perfil_navegador")
        try:  # Edge de verdade (vem com o Windows), com perfil próprio: as lojas tratam como pessoa navegando
            ctx = pw.chromium.launch_persistent_context(perfil, channel="msedge", headless=False, args=args, locale="pt-BR",
                                                        viewport={"width": 1366, "height": 900})
        except Exception as e:  # noqa: BLE001
            registrar(f"Edge indisponível ({str(e)[:50]}), usando Chromium")
            ctx = pw.chromium.launch_persistent_context(perfil, headless=False, args=args, locale="pt-BR",
                                                        viewport={"width": 1366, "height": 900})
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        pagina = ctx.pages[0] if ctx.pages else ctx.new_page()
        registrar("Rodada do robô do PC começou")
        itens = rodar(pagina, produtos)
        ctx.close()
    total = sum(len(v) for v in itens.values())
    ok = gravar_json_repo("data/ofertas_pc.json", {"atualizadoEm": ISO, "itens": itens}, token,
                          f"Robô do PC: {total} ofertas")
    registrar(f"Rodada terminou: {total} ofertas {'enviadas' if ok else 'NÃO enviadas'}")


if __name__ == "__main__":
    main()

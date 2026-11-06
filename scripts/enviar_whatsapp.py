"""Envia os alertas do Econolife Promos para o Telegram (e WhatsApp via CallMeBot, se configurado).

Modos (variável MODO):
  novos  -> só os alertas que entraram neste commit (padrão, roda a cada gravação do robô)
  resumo -> todos os itens que hoje estão abaixo do preço-alvo
  teste  -> mensagem de teste
Segredos do repositório:
  TG_TOKEN                      token do robô criado no @BotFather (obrigatório para Telegram)
  TG_CHAT_ID                    opcional; se faltar, o grupo é descoberto sozinho e salvo em data/config.json
  WA_PHONE_1/WA_KEY_1, WA_PHONE_2/WA_KEY_2   opcionais (CallMeBot)
"""
import json, os, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

SITE = os.environ.get("SITE_URL", "")
MODO = (os.environ.get("MODO") or "novos").strip().lower()
TG_TOKEN = (os.environ.get("TG_TOKEN") or "").strip()


def brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


def http_json(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


# ---------- Telegram ----------
def salvar_chat(chat_id):
    try:
        cfg = json.load(open("data/config.json", encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cfg = {}
    cfg["telegramChatId"] = chat_id
    json.dump(cfg, open("data/config.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open("data/config.json", "a").write("\n")
    try:
        subprocess.run(["git", "config", "user.name", "Econolife Promos"], check=True)
        subprocess.run(["git", "config", "user.email", "actions@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", "data/config.json"], check=True)
        subprocess.run(["git", "commit", "-m", "Telegram: grupo conectado"], check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        print("Grupo do Telegram salvo na configuração.")
    except Exception as e:  # noqa: BLE001
        print("Não consegui salvar o grupo na configuração: " + str(e))


def chat_telegram():
    env = (os.environ.get("TG_CHAT_ID") or "").strip()
    if env:
        return env
    try:
        cfg = json.load(open("data/config.json", encoding="utf-8"))
        if cfg.get("telegramChatId"):
            return str(cfg["telegramChatId"])
    except Exception:  # noqa: BLE001
        pass
    # descobre o grupo onde o robô foi adicionado
    try:
        res = http_json(f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates")
    except Exception as e:  # noqa: BLE001
        print("Telegram: não consegui ler as atualizações do robô: " + str(e))
        return None
    achado = None
    for up in res.get("result", []):
        for k in ("my_chat_member", "message", "channel_post", "chat_member"):
            chat = (up.get(k) or {}).get("chat")
            if chat and chat.get("type") in ("group", "supergroup"):
                achado = chat.get("id")
            elif chat and chat.get("type") == "private" and achado is None:
                achado = chat.get("id")
    if achado is None:
        print("Telegram: nenhum grupo encontrado. Adicione o robô ao grupo e mande /start nele.")
        return None
    salvar_chat(achado)
    return str(achado)


def enviar_telegram(texto, html_mode=False):
    if not TG_TOKEN:
        return False
    chat = chat_telegram()
    if not chat:
        return False
    try:
        r = http_json(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      dict({"chat_id": chat, "text": texto, "disable_web_page_preview": "true" if html_mode else "false"},
                           **({"parse_mode": "HTML"} if html_mode else {})))
        print("Telegram: " + ("enviado" if r.get("ok") else "resposta inesperada"))
        return bool(r.get("ok"))
    except Exception as e:  # noqa: BLE001
        print("Telegram: falha ao enviar: " + str(e))
        return False


# ---------- alerta no formato "oferta" (foto + De/Por + Compre aqui) ----------
EMOJI_CAT = {"geladeira": "🧊", "refrigerador": "🧊", "cooktop": "🔥", "fogao": "🔥", "forno": "🍞", "micro": "📡",
             "tv": "📺", "smart": "📺", "lavadora": "🧺", "lava": "🧺", "maquina": "🧺", "ventilador": "🌀",
             "liquidificador": "🥤", "purificador": "💧", "gelagua": "💧", "bebedouro": "💧", "iphone": "📱",
             "porcelanato": "🧱", "piso": "🧱", "ceramica": "🧱", "luminaria": "💡", "spot": "💡", "led": "💡"}


def _sa(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def _h(s):
    import html as _html
    return _html.escape(str(s or ""), quote=True)


def legenda_oferta(a):
    """Texto do alerta no estilo dos grupos de promoção."""
    nome = _sa(a.get("produtoNome") or a.get("titulo") or "")
    emoji = next((e for k, e in EMOJI_CAT.items() if k in nome), "💥")
    titulo = (a.get("titulo") or a.get("produtoNome") or "").strip()
    titulo = titulo[:110] + ("…" if len(titulo) > 110 else "")
    linhas = [f"{emoji} <b>{_h(titulo)}</b>", ""]
    de, preco = a.get("de"), a.get("preco")
    if isinstance(preco, (int, float)) and preco > 0:
        if isinstance(de, (int, float)) and de > preco * 1.01:
            linhas.append(f"De: <s>{_h(brl(de))}</s> ❌")
        linhas.append(f"💸 <b>Por: {_h(brl(preco))}</b> 🔥")
        alvo = a.get("alvo")
        if isinstance(alvo, (int, float)) and preco <= alvo:
            linhas.append(f"✅ {_h(brl(alvo - preco))} abaixo do seu alvo")
        elif isinstance(de, (int, float)) and de > preco:
            linhas.append(f"📉 Caiu {round((1 - preco / de) * 100)}%")
    else:
        linhas.append("💸 <b>Preço no link</b> 🔥")
    linhas += ["", f"🏬 {_h(a.get('loja') or 'Loja')}", f"🔗 Compre aqui: <a href=\"{_h(a['url'])}\">{_h(a['url'][:60] + ('…' if len(a['url']) > 60 else ''))}</a>"]
    if a.get("post"):
        linhas.append(f"📣 <a href=\"{_h(a['post'])}\">Ver post original</a>")
    return "\n".join(linhas)


def enviar_oferta(a):
    """Manda 1 alerta: com foto (sendPhoto) quando houver, senão texto com prévia do link."""
    if not TG_TOKEN:
        return False
    chat = chat_telegram()
    if not chat:
        return False
    texto = legenda_oferta(a)
    img = a.get("imagem")
    if isinstance(img, str) and img.startswith("https://"):
        try:
            r = http_json(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                          {"chat_id": chat, "photo": img, "caption": texto[:1024], "parse_mode": "HTML"})
            if r.get("ok"):
                print("Telegram: oferta com foto enviada")
                return True
        except Exception as e:  # noqa: BLE001
            print("Telegram: foto falhou, mandando sem foto: " + str(e)[:60])
    try:
        prev = json.dumps({"url": a["url"], "show_above_text": True, "prefer_small_media": True})
        r = http_json(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      {"chat_id": chat, "text": texto, "parse_mode": "HTML", "link_preview_options": prev})
        print("Telegram: oferta " + ("enviada" if r.get("ok") else "com resposta inesperada"))
        return bool(r.get("ok"))
    except Exception as e:  # noqa: BLE001
        print("Telegram: falha ao enviar oferta: " + str(e)[:80])
        return False


# ---------- WhatsApp (CallMeBot, opcional) ----------
def enviar_whatsapp(texto):
    for i in ("1", "2"):
        phone = (os.environ.get("WA_PHONE_" + i) or "").strip()
        key = (os.environ.get("WA_KEY_" + i) or "").strip()
        if not (phone and key):
            continue
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) <= 11:
            digits = "55" + digits
        q = urllib.parse.urlencode({"phone": "+" + digits, "text": texto, "apikey": key})
        try:
            with urllib.request.urlopen("https://api.callmebot.com/whatsapp.php?" + q, timeout=40) as r:
                r.read()
            print("WhatsApp " + i + ": enviado")
        except Exception as e:  # noqa: BLE001
            print("WhatsApp " + i + ": falha: " + str(e))
        time.sleep(4)


def enviar(texto):
    if not TG_TOKEN and not os.environ.get("WA_KEY_1"):
        print("Nenhum canal configurado (crie o segredo TG_TOKEN). Nada enviado.")
        return
    enviar_telegram(texto)
    enviar_whatsapp(texto)


def carregar(caminho, ref=None):
    try:
        if ref:
            txt = subprocess.run(["git", "show", f"{ref}:{caminho}"], capture_output=True, text=True, check=True).stdout
        else:
            txt = open(caminho, encoding="utf-8").read()
        return json.loads(txt)
    except Exception:  # noqa: BLE001
        return None


def main():
    cfg = carregar("data/config.json") or {}
    if MODO == "teste":
        enviar("✅ Econolife Promos conectado! Os alertas de preço vão chegar por aqui.\n" + SITE)
        ult = sorted((carregar("data/ofertas.json") or {}).get("alertas") or [], key=lambda x: x.get("criadoEm", ""))
        if ult:
            time.sleep(2)
            enviar_oferta(ult[-1])
        return
    if cfg.get("notificacoes") is False and MODO == "novos":
        print("Alertas desligados no app. Nada enviado.")
        return

    atual = carregar("data/ofertas.json") or {}
    if MODO == "resumo":
        prods = {p["id"]: p for p in (carregar("data/produtos.json") or {}).get("produtos", [])}
        linhas = []
        for pid, it in (atual.get("itens") or {}).items():
            p = prods.get(pid)
            if not p or p.get("ativo") is False or not it.get("ofertas"):
                continue
            b = min(it["ofertas"], key=lambda o: o.get("preco") or 1e12)
            alvo = p.get("precoAlvo")
            if alvo and b.get("preco") and b["preco"] <= alvo:
                linhas.append(f"• {p['nome']}: {brl(b['preco'])} na {b.get('loja','loja')} (alvo {brl(alvo)})\n{b.get('url','')}")
        if not linhas:
            enviar("Econolife Promos: nenhum item abaixo do alvo agora. O robô segue procurando.\n" + SITE)
        else:
            enviar("🛒 Econolife Promos — abaixo do alvo agora:\n\n" + "\n\n".join(linhas) + "\n\n" + SITE)
        return

    anterior = carregar("data/ofertas.json", "HEAD~1")
    ids_antes = {a.get("id") for a in ((anterior or {}).get("alertas") or [])}
    limite = datetime.now(timezone.utc) - timedelta(hours=12)
    novos = []
    for a in atual.get("alertas") or []:
        if a.get("id") in ids_antes:
            continue
        if anterior is None:
            try:
                if datetime.fromisoformat(a["criadoEm"].replace("Z", "+00:00")) < limite:
                    continue
            except Exception:  # noqa: BLE001
                continue
        novos.append(a)
    if not novos:
        print("Nenhum alerta novo neste commit.")
        return
    novos.sort(key=lambda a: a.get("criadoEm", ""))
    partes = [f"🔥 {a.get('texto','')}\n{a.get('url','')}" for a in novos[:6]]
    extra = f"\n\n+{len(novos) - 6} outros no app" if len(novos) > 6 else ""
    enviar("🛒 Econolife Promos\n\n" + "\n\n".join(partes) + extra + "\n\n" + SITE)


if __name__ == "__main__":
    sys.exit(main())

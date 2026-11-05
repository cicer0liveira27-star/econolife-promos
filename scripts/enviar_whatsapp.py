"""Envia os alertas do Econolife Promos para o WhatsApp via CallMeBot.

Modos (variável MODO):
  novos  -> só os alertas que entraram neste commit (padrão, roda a cada gravação do robô)
  resumo -> todos os itens que hoje estão abaixo do preço-alvo
  teste  -> mensagem de teste
Números e chaves vêm dos segredos do repositório (WA_PHONE_1/WA_KEY_1, WA_PHONE_2/WA_KEY_2).
"""
import json, os, subprocess, sys, time, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

SITE = os.environ.get("SITE_URL", "")
MODO = (os.environ.get("MODO") or "novos").strip().lower()


def brl(v):
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


def destinos():
    out = []
    for i in ("1", "2"):
        phone = (os.environ.get("WA_PHONE_" + i) or "").strip()
        key = (os.environ.get("WA_KEY_" + i) or "").strip()
        if phone and key:
            digits = "".join(c for c in phone if c.isdigit())
            if len(digits) <= 11:
                digits = "55" + digits
            out.append(("+" + digits, key))
    return out


def enviar(texto):
    alvo = destinos()
    if not alvo:
        print("Nenhum número configurado nos segredos do repositório (WA_PHONE_1/WA_KEY_1). Nada enviado.")
        return
    for phone, key in alvo:
        q = urllib.parse.urlencode({"phone": phone, "text": texto, "apikey": key})
        url = "https://api.callmebot.com/whatsapp.php?" + q
        try:
            with urllib.request.urlopen(url, timeout=40) as r:
                body = r.read().decode("utf-8", "ignore")
            ok = "queued" in body.lower() or "sent" in body.lower()
            print(("OK " if ok else "Resposta inesperada ") + phone[:6] + "…")
        except Exception as e:  # noqa: BLE001
            print("Falha ao enviar para " + phone[:6] + "…: " + str(e))
        time.sleep(4)


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
        enviar("✅ Econolife Promos: teste de mensagem. Os alertas de preço vão chegar por aqui.\n" + SITE)
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

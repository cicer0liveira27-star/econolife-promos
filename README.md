# Econolife Promos

Lista de compras da casa com um robô que caça os melhores preços em lojas confiáveis e avisa no Telegram.

**Site:** https://cicer0liveira27-star.github.io/econolife-promos/

## Como funciona

- `data/produtos.json` — a lista (editada pelo app, com a chave do GitHub salva no aparelho).
- `data/ofertas.json` — preços, fotos, links, histórico e alertas. Gravado pelo robô gratuito do GitHub Actions (`.github/workflows/checar.yml`), a cada 15 minutos.
- `data/config.json` — liga/desliga os alertas.
- `data/checagem.json` — relatório da última rodada do robô (páginas conferidas, falhas).
- `.github/workflows/whatsapp.yml` — quando o robô grava alertas novos, manda mensagem no grupo do Telegram.

## Alertas no Telegram (Settings → Secrets and variables → Actions)

| Nome | O que é |
|---|---|
| `TG_TOKEN` | token do robô criado no @BotFather |

Adicione o robô a um grupo, mande `/start` no grupo e toque em "Enviar mensagem de teste" no app: o grupo é encontrado sozinho e salvo em `data/config.json`.
WhatsApp via CallMeBot continua opcional (`WA_PHONE_1`/`WA_KEY_1`, `WA_PHONE_2`/`WA_KEY_2`).

## Lojas aceitas

Amazon, Mercado Livre, Magazine Luiza, Casas Bahia, Ponto, Extra, Americanas, Submarino, Carrefour, Fast Shop, KaBuM, Leroy Merlin, Telhanorte, C&C, Obramax, Ferreira Costa, MadeiraMadeira, Tok&Stok, Mobly e lojas oficiais das marcas. Links de outros sites não aparecem no app.

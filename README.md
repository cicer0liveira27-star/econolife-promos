# Econolife Promos

Lista de compras da casa com um robô que caça os melhores preços em lojas confiáveis e avisa no WhatsApp.

**Site:** https://cicer0liveira27-star.github.io/econolife-promos/

## Como funciona

- `data/produtos.json` — a lista (editada pelo app, com a chave do GitHub salva no aparelho).
- `data/ofertas.json` — preços, fotos, links, histórico e alertas. Gravado pelo robô (tarefa agendada no Claude, 6x por dia).
- `data/config.json` — liga/desliga os alertas no WhatsApp.
- `.github/workflows/whatsapp.yml` — quando o robô grava alertas novos, manda mensagem para os números configurados.

## Segredos do WhatsApp (Settings → Secrets and variables → Actions)

| Nome | O que é |
|---|---|
| `WA_PHONE_1` | número 1 com DDD (ex.: 81999999999) |
| `WA_KEY_1` | apikey do CallMeBot do número 1 |
| `WA_PHONE_2` | número 2 com DDD |
| `WA_KEY_2` | apikey do CallMeBot do número 2 |

Cada número pega a própria apikey uma única vez em https://www.callmebot.com/blog/free-api-whatsapp-messages/.

## Lojas aceitas

Amazon, Mercado Livre, Magazine Luiza, Casas Bahia, Ponto, Extra, Americanas, Submarino, Carrefour, Fast Shop, KaBuM, Leroy Merlin, Telhanorte, C&C, Obramax, Ferreira Costa, MadeiraMadeira, Tok&Stok, Mobly e lojas oficiais das marcas. Links de outros sites não aparecem no app.

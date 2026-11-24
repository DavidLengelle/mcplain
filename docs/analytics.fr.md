# La mesure des visites (Umami)

Ce guide explique comment MCPlain compte ses visites avec Umami : ce qui est compté, ce qui ne l'est jamais, la base à part,
le relais du site, le premier réglage, et l'accès au tableau sur le VPS. Séance 9c-3, faite le 24 novembre 2026.

C'est comme un compteur à l'entrée d'un musée : il sait combien de gens sont entrés dans chaque salle, mais il ne prend ni
leur nom ni leur photo, et il oublie leur visage le soir même.

## 1. Ce que c'est

Umami est un outil libre (licence MIT) de mesure d'audience. MCPlain l'installe **chez lui**, dans la même pile Docker que le
site : aucune donnée ne part chez une autre entreprise. Image officielle, épinglée par étiquette **et** par empreinte :

```
ghcr.io/umami-software/umami:3.4.1@sha256:e69d1a7932e9dab0fc523edc7be1f3a53f3c261f57856fc2167ae74a8fc022e8
```

La 3.4.1 est un correctif de sécurité (Next.js 16.4.2, Node 22.23.4). L'empreinte est celle de l'index multi-plateforme
(amd64 et arm64) lu sur ghcr.io le 24 novembre 2026. Le tableau d'Umami n'est **jamais public**.

## 2. Ce qui est compté, et ce qui ne l'est jamais

| Compté | Jamais compté |
| --- | --- |
| la page vue, avec chaque identifiant remplacé par `[id]` (`/fr/analyses/[id]`) | l'identifiant d'un rapport, les paramètres d'URL (`?…`), l'ancre (`#…`) |
| le site d'où vient le visiteur : son **origine seulement** (`https://news.example.com`) | le chemin et les paramètres d'un site extérieur |
| le titre de la page, la langue, la taille de l'écran | les pages `/admin` et `/account` (et leurs versions `/fr/…`) |
| le navigateur, le système, le type d'appareil (lus dans le `User-Agent`) | ce que le visiteur tape ou colle |
| le pays, la région et la ville approximatifs (base GeoLite2 incluse dans l'image) | l'adresse IP elle-même : Umami ne la garde pas |

- **Aucun cookie, aucun stockage navigateur** écrits par Umami : son script lit seulement `localStorage["umami.disabled"]`, et
  envoie ses requêtes sans cookie (`credentials: "omit"`). Des tests le vérifient (section 8).
- **Do Not Track respecté** (`data-do-not-track="true"`), et aussi **Global Privacy Control** (le signal plus récent du
  navigateur) : rien ne part.
- **Pas d'événement personnalisé**, pas d'identification (`identify`) : seulement des vues de page.
- **`SALT_ROTATION=day`** (décision de David). Umami reconnaît un visiteur par une empreinte de son adresse, de son navigateur et
  d'un sel. Avec un sel qui change **chaque jour**, il ne peut plus relier deux visites de deux jours différents, comme notre
  propre empreinte d'IP. **Conséquence** : sur une période de plusieurs jours, les « visiteurs uniques » sont **surestimés** :
  quelqu'un qui revient trois jours de suite compte pour trois visiteurs. Sur une seule journée, le chiffre est juste.
- Le cadran « Fréquentation » de `/admin` reste les comptes créés par jour ; les visites se lisent dans le tableau d'Umami.

## 3. La base à part, et l'exception à Alembic

- Umami a **sa propre base** `umami`, dans le même serveur PostgreSQL, avec **son propre rôle** `umami`.
- Base et rôle sont créés par le service `migrate` (`prepare_umami` dans `api/src/mcplain_api/migrate.py`), **après** Alembic et
  **hors** d'Alembic, avec `MCPLAIN_UMAMI_DB_PASSWORD`. C'est idempotent : relancé, il ne fait que redonner le mot de passe. Le rôle
  n'a aucun pouvoir (ni `SUPERUSER`, ni `CREATEDB`, ni `CREATEROLE`) ; il est propriétaire de sa base, et seul à pouvoir s'y
  connecter. `mcplain_app` ne reçoit aucun droit de plus.
- **Exception à « Alembic seule source des migrations »** : les tables d'Umami sont créées par **Umami lui-même** (Prisma, à son
  démarrage), dans sa base à lui. C'est la seule exception. Les tables de MCPlain restent toutes dans Alembic.
- **Dans l'autre sens** : la migration `0012` retire à tout le monde (`PUBLIC`) le droit de se connecter à la base de MCPlain et le
  rend aux trois rôles `mcplain_app`, `mcplain_guichet` et `mcplain_facteur`. Le rôle `umami` ne peut donc pas s'y connecter, et
  aucun rôle de MCPlain ne peut se connecter à `umami` (testé sur PostgreSQL, `api/tests/test_roles.py`).

Deux réseaux à lui dans `compose.yaml` : `umami_db` (Umami et PostgreSQL, **sans sortie** vers Internet, `internal: true`) et
`umami_web` (Umami et le site, pour le relais, et le port local du tableau). Umami tourne en lecture seule, sans capacité, comme
utilisateur `nextjs`. Le site ne dépend pas d'Umami : sans lui, le site marche, il ne compte rien.

## 4. Le relais du site

Le navigateur ne parle jamais directement à Umami. Il parle au site, qui relaie **deux chemins seulement** :

| Chemin | Ce que fait le site |
| --- | --- |
| `GET /umami/script.js` | sert le script de suivi d'Umami, en JavaScript |
| `POST /umami/api/send` | filtre l'envoi, puis le passe à Umami |
| **tout autre chemin sous `/umami`**, ou une autre méthode | **404** (le tableau, la connexion, l'API d'Umami ne passent jamais) |

Pour `POST /umami/api/send` (`web/src/app/umami/api/send/route.ts`, logique dans `web/src/lib/umami.ts`) :

- **JSON seulement** (sinon 415), **8 Ko au plus** (sinon 413), sans envoyer quoi que ce soit à Umami.
- Le corps est **reconstruit** : une vue de page (`type: "event"`) du site suivi, avec seulement `website`, `url`, `referrer`,
  `hostname`, `language`, `screen`, `title`. Les chemins sont nettoyés (`[id]`), un référent extérieur est réduit à son origine.
  Tout le reste est jeté, en particulier `ip` et `userAgent` : Umami 3.4.1 accepte ces deux champs dans le corps **et les préfère
  aux en-têtes**, un visiteur pourrait donc s'inventer une adresse. Une page `/admin` ou `/account` est refusée.
- Les en-têtes sont **reconstruits de zéro** : `Content-Type`, `User-Agent` du visiteur, le jeton `x-umami-cache` d'Umami, et
  `x-mcplain-visitor-ip`. Aucun autre en-tête d'adresse (`X-Forwarded-For`, `X-Real-IP`, `CF-Connecting-IP`, `Forwarded`…) ne
  passe : sans cela, Umami se rabattrait sur eux. Le cookie du visiteur ne passe jamais, et le `Set-Cookie` d'Umami non plus.
- **La vraie adresse** : `x-mcplain-visitor-ip` (`CLIENT_IP_HEADER` d'Umami) est calculée par le relais avec la même règle que l'API
  (`MCPLAIN_TRUSTED_PROXY_HOPS` entrées depuis la droite de `X-Forwarded-For`, après l'ajout de `web/client-ip.js`). Le relais
  **écrase** cet en-tête : celui qu'enverrait le visiteur est toujours remplacé. Une adresse IPv6 est réduite à son réseau /64
  (la seconde moitié mise à zéro), comme pour notre empreinte.

## 5. Le script de suivi

Dans le gabarit des pages (`web/src/app/[locale]/layout.tsx`), seulement si `MCPLAIN_UMAMI_WEBSITE_ID` est réglé :

1. `public/umami-guard.js`, chargé avant tout avec le nonce de la CSP, comme `theme.js`. Il définit
   `window.mcplainUmamiBeforeSend`, que le script d'Umami appelle avant chaque envoi (option `data-before-send` de la 3.4.1) : il
   nettoie le chemin, réduit le référent, et **annule** l'envoi sur `/admin`, `/account`, une autre page que le site, un événement
   personnalisé, ou avec Global Privacy Control.
2. `/umami/script.js` avec `data-website-id`, `data-host-url="/umami"`, `data-before-send`, `data-do-not-track="true"`,
   `data-exclude-search="true"` et `data-exclude-hash="true"`. Noms par défaut d'Umami : aucun contournement des bloqueurs de
   publicité.

**La CSP ne change pas** : le script vient du même site et reçoit le nonce ; `connect-src 'self'` couvre `/umami/api/send`. Seul
le filtre de `web/src/proxy.ts` exclut désormais `/umami`, pour que next-intl ne le transforme pas en `/en/umami/…`.

L'identifiant du site suivi (`MCPLAIN_UMAMI_WEBSITE_ID`) est un **réglage public** : il est visible dans la balise du script de
toute façon. Ce n'est pas un secret.

## 6. Les réglages

| Réglage | Qui le reçoit | Rôle |
| --- | --- | --- |
| `MCPLAIN_UMAMI_DB_PASSWORD` (secret) | `migrate`, `umami` | mot de passe du rôle `umami` |
| `MCPLAIN_UMAMI_APP_SECRET` (secret) | `umami` seulement (`APP_SECRET`) | clé des jetons et des empreintes d'Umami |
| `MCPLAIN_UMAMI_TWO_FACTOR_KEY` (secret, 64 caractères hexadécimaux) | `umami` seulement (`TWO_FACTOR_ENCRYPTION_KEY`) | sans elle, Umami refuse la double authentification |
| `MCPLAIN_UMAMI_WEBSITE_ID` (public) | `web` | identifiant du site suivi, écrit par le script de premier réglage |
| `MCPLAIN_UMAMI_PORT` (3200) | `umami` | port du tableau, sur `127.0.0.1` seulement |
| `MCPLAIN_TRUSTED_PROXY_HOPS` | `api`, `guichet`, `web` | la même règle de confiance pour lire l'adresse |

Les trois secrets sont créés par `scripts/init-secrets.sh` ; aucun n'arrive au site (`api/tests/test_compose_accounts.py`).
Umami reçoit aussi `CLIENT_IP_HEADER=x-mcplain-visitor-ip`, `SALT_ROTATION=day`, `DISABLE_TELEMETRY=1` et `DISABLE_UPDATES=1`
(il ne contacte pas les serveurs d'Umami).

## 7. Le premier réglage

Umami crée tout seul un compte `admin` avec le mot de passe public `umami`. **Juste après le premier démarrage** :

```
scripts/umami-first-setup.sh mcplain.fr
```

(le domaine du site ; `localhost` par défaut, sur ta machine). Le script :

1. **refuse de tourner** si le tableau est publié ailleurs que sur `127.0.0.1`, si le site est publié ailleurs que sur
   `127.0.0.1`, ou si le site laisse passer vers Umami un autre chemin que les deux prévus ;
2. se connecte avec `admin` / `umami` (s'arrête si ce mot de passe ne marche plus : il a déjà été changé) ;
3. te demande le nouveau mot de passe **sans l'afficher**, deux fois, 12 caractères au moins. Il n'est jamais dans `.env`, ni sur
   une ligne de commande, ni à l'écran, ni dans un journal : il passe à `curl` par un fichier temporaire (droits 600, effacé à la
   fin) ;
4. crée le site suivi (ou reprend celui qui existe) et écrit son identifiant public `MCPLAIN_UMAMI_WEBSITE_ID` dans `.env`.

Ensuite : `docker compose up -d web`, puis ouvre le tableau et **active la double authentification d'Umami à la main**
(réglages du profil). Il faut des codes de secours rangés comme ceux de l'admin de MCPlain.

## 8. Le tableau sur le VPS : par tunnel SSH seulement

Le tableau écoute sur `127.0.0.1:3200` **du VPS**. Depuis ta machine :

```
ssh -N -L 3200:127.0.0.1:3200 utilisateur@ton-vps
```

puis ouvre `http://127.0.0.1:3200` sur ta machine. Le tunnel est comme un couloir privé entre ta machine et le VPS : personne
d'autre ne peut y passer. Ferme-le (Ctrl+C) quand tu as fini. **Jamais** de port public pour Umami, jamais de relais TLS vers lui.

## 9. Les tests

- `cd web && pnpm test` (`umami.test.ts`) : chemins nettoyés, pages cachées, adresse lue depuis la droite, IPv6 /64, corps
  reconstruit, en-têtes reconstruits et adresse écrasée, 404, 413, 415, la fonction `before-send` du navigateur, et l'empreinte
  sha256 de la copie du script 3.4.1.
- `cd web && pnpm test:e2e` (`umami.spec.ts`) : un **faux Umami** (`tests/e2e/umami-server.mjs`) sert la vraie copie du script 3.4.1
  (`tests/fixtures/umami-script-3.4.1.js`, licence MIT à côté ; elle ne sert qu'aux tests et n'est jamais servie aux visiteurs) et
  note ce qu'il reçoit : chemin de rapport normalisé, aucun cookie ni stockage, rien depuis `/admin` et `/account`, rien avec Do Not
  Track ni Global Privacy Control, seulement deux chemins sous `/umami`, en-tête d'adresse écrasé. Le banc n'est pas alourdi : la CI
  du banc ne démarre pas Umami.
- `cd web && pnpm test:stack` (`stack/umami.spec.ts`) : avec le **vrai** Umami de la pile, une visite de rapport est rangée sous
  `/fr/analyses/[id]`, sans paramètre, rien depuis `/admin`, aucun cookie d'Umami. Sauté si Umami n'est pas réglé.
- `cd api && uv run pytest tests/test_compose_accounts.py tests/test_umami_setup.py` : secrets, image épinglée, port local,
  réseaux ; le script de premier réglage refuse un tableau publié ailleurs et ne met jamais le mot de passe sur une ligne de commande.
- `cd api && uv run pytest -m docker tests/test_compose.py` : le conteneur Umami est fermé ; `-m postgres` : les droits entre les
  deux bases.

## 10. Limites connues

- Les visiteurs uniques sur plusieurs jours sont surestimés (section 2).
- Le site lui-même pose un cookie `NEXT_LOCALE` (next-intl) qui retient la langue quand elle n'est pas celle du navigateur. Ce
  n'est pas Umami ; la page de confidentialité le dit.
- Umami garde le pays, la région et la ville approximatifs : c'est ce que fait sa base GeoLite2, il n'y a pas de réglage pour
  s'arrêter au pays.

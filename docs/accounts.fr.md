# Les comptes de MCPlain

Ce guide explique à un débutant comment marchent les comptes : qui fait quoi, où vivent les secrets, et ce que tu lances
toi-même. Les phrases sont courtes. Séance 9a, faite le 10 novembre 2026 ; quotas et historique en séance 9b, le 12 novembre 2026 ;
double authentification de l'admin, bannissement et limite de get-session en séance 9c-1, le 24 novembre 2026 (sections 19 à 23).

## 1. Le tableau d'ensemble

Un compte sert à deux choses : avoir 10 analyses par jour rien qu'à soi, et retrouver la liste de ses analyses (section 14).
Un compte est gratuit, il demande une adresse e-mail vérifiée et un mot de passe de 10 à 128 caractères.

Sous chaque champ de mot de passe, une case « Afficher le mot de passe » montre ce qu'on tape, pour éviter les fautes de
frappe sur téléphone. Elle est décochée au départ, se décoche à chaque envoi, et son état n'est gardé nulle part. Un seul
composant porte tous les champs de mot de passe du site (`web/src/components/account/password-field.tsx`), un test le vérifie.

```
navigateur ──> site (relais, sans secret) ──/api/auth/*──> guichet (Better Auth) ──> schéma auth de PostgreSQL
                                          └─/api/*──────> API ──> tables de MCPlain
guichet ──> boîte de départ (mail_outbox) <── facteur ──> serveur SMTP (Mailpit en développement)
guichet ──/internal/auth-guard──> API (ALTCHA, limite de comptes par réseau)
```

C'est comme une mairie : le **guichet** ouvre les dossiers, le **facteur** porte le courrier, et l'agent d'accueil (le site)
oriente les gens sans jamais toucher aux dossiers.

## 2. Le guichet

Le guichet est un petit serveur Node.js (dossier `auth/`, service compose `guichet`). Il fait tourner Better Auth, une
bibliothèque libre qui gère les comptes : inscription, connexion, déconnexion, mot de passe oublié, suppression du compte.

- Il est **le seul** à recevoir `BETTER_AUTH_SECRET`, la clé qui signe les badges.
- Il range les comptes dans le schéma `auth` de PostgreSQL, avec son propre rôle `mcplain_guichet`. Les mots de passe y sont
  gardés sous forme d'empreinte (on ne peut pas les relire).
- Il **n'envoie aucun e-mail**. Il écrit une ligne dans la boîte de départ (`mail_outbox`) : c'est son seul droit hors de son
  schéma.
- Il ne garde ni l'adresse IP ni le navigateur dans la session : ces deux champs restent vides.
- Le champ `role` vaut `user`, `admin` ou `bench`. Le site ne peut jamais le changer : seuls `scripts/make-admin.sh` et
  `scripts/make-bench-account.sh` le font. Le rôle `admin` seul ne donne aucun pouvoir : il faut aussi la double authentification
  (section 19).
- La télémétrie de Better Auth est coupée (elle l'est déjà par défaut ; on l'écrit quand même, et `BETTER_AUTH_TELEMETRY=0`).
- Son limiteur de requêtes est allumé : par exemple, au plus 3 connexions en 10 secondes depuis une même adresse, 3 essais de
  code en 10 secondes, 600 lectures de session par minute (section 22), et 100 par minute pour le reste.

Avant une inscription, une connexion ou une demande de mot de passe oublié, le guichet demande l'avis de l'API
(`/internal/auth-guard`, voir plus bas). Si l'API dit non, la réponse est claire et sans détail technique.

## 3. Le badge (le cookie de session)

Après la connexion, le navigateur reçoit un badge : le cookie `mcplain.session_token`. Il le montre à chaque visite.

- `HttpOnly` : un script de la page ne peut pas le lire.
- `SameSite=Lax` : un autre site ne peut pas s'en servir pour agir à ta place.
- `Secure` en production (adresse en `https://`) : il ne voyage que chiffré.

Ce cookie sert seulement à rester connecté. C'est pourquoi il n'a pas besoin de bandeau de consentement.

Pour savoir qui est connecté, l'API transmet ce cookie au guichet (`current_user()` dans `api/src/mcplain_api/session_user.py`)
et garde la réponse 30 secondes. Elle ne transmet que les cookies `mcplain.`. Depuis la séance 9c-1, elle passe par une route
interne du guichet, `GET /internal/session`, hors du relais du site (section 22) : cette route lit la session côté serveur et
n'est pas soumise au limiteur. La route publique `/api/auth/get-session`, celle du navigateur, a de nouveau sa limite.

## 4. Le facteur

Le facteur (`api/src/mcplain_api/facteur.py`, service `facteur`) est le **seul** à connaître les identifiants SMTP.

- Toutes les 5 secondes, il relève la boîte de départ, envoie chaque e-mail **en texte brut** (jamais de HTML), en anglais ou en
  français, puis **efface la ligne** : le lien ne reste pas en base.
- Si le serveur SMTP ne répond pas : 3 nouveaux essais (après 30 secondes, 2 minutes, 10 minutes), puis la ligne est effacée et
  une ligne de journal le dit, sans le lien ni l'adresse.
- Il envoie aussi les alertes admin du rédacteur (table `ai_admin_alerts`) à `MCPLAIN_ADMIN_EMAIL` : au plus un e-mail par code
  d'alerte toutes les 24 heures, et 20 e-mails admin par jour au maximum. L'e-mail donne le code, les dates et le nombre, jamais
  une clé ni un texte de tiers.
- Il ne donne jamais le mot de passe SMTP sans STARTTLS.

Les modèles d'e-mails sont dans `api/src/mcplain_api/mail_texts/en.json` et `fr.json`.

## 5. ALTCHA : la petite épreuve invisible

Un robot peut remplir des formulaires par milliers. ALTCHA lui demande un petit calcul (une « preuve de travail ») avant chaque
envoi. Pour toi, c'est invisible : le calcul se fait pendant que tu cliques, en moins d'une seconde.

1. Le navigateur demande un défi à l'API (`GET /api/altcha/challenge`) : un problème signé par l'API, valable 5 minutes.
2. Il le résout dans un travailleur (`/altcha/pbkdf2.js`, servi par le site, copié du paquet `altcha` au moment de la
   construction) avec PBKDF2/SHA-256.
3. Il envoie la solution avec le formulaire (en-tête `x-altcha`).
4. L'API vérifie la signature, l'heure, et que la solution n'a **jamais servi** (table `altcha_uses`, clé unique). Une
   solution ne passe qu'une fois.

Seule l'API connaît la clé de signature `MCPLAIN_ALTCHA_HMAC_KEY`. Pas de service tiers, pas de cookie.

**Le coût choisi : 5000** (`MCPLAIN_ALTCHA_COST`, séance 9b ; 2000 en séance 9a). Mesures du 12 novembre 2026, dans Chromium
avec le processeur ralenti 4 fois (le réglage « téléphone moyen » des outils de Chrome), 10 essais chaque fois : médianes 268,
376 et 279 ms ; maximums 959, 789 et 469 ms. Le maximum reste sous la seconde, mais de peu une fois sur trois : à surveiller.
Le test `pnpm test:stack` refait cette mesure à chaque fois et vérifie que l'API sert bien le coût 5000.

Depuis la séance 9b, **chaque demande d'analyse** demande aussi une solution neuve : le champ de l'accueil, celui de l'en-tête,
les exemples « Essaie avec », le clic dans une liste de plusieurs MCP et le bouton « Relancer ». Le widget invisible vit une
seule fois dans la page (`web/src/components/visitor-context.tsx`).

## 6. L'adresse IP, et pourquoi on ne croit pas le navigateur

Un navigateur peut écrire ce qu'il veut dans l'en-tête `X-Forwarded-For`. Si on le croyait, un robot changerait d'adresse à
chaque requête.

Le site (Next.js) ne fait rien de cet en-tête par lui-même. On lui ajoute donc un petit script (`web/client-ip.js`, chargé au
démarrage) qui **ajoute à la fin** de `X-Forwarded-For` l'adresse réelle de la connexion. Ce que le navigateur a écrit reste à
gauche.

L'API lit l'adresse avec **une seule fonction** (`visitor_ip` dans `api/src/mcplain_api/client_ip.py`) : elle compte
`MCPLAIN_TRUSTED_PROXY_HOPS` entrées depuis la droite. En développement, il y a un seul relais (le site) : 1. À la mise en ligne,
avec un relais TLS devant le site : 2. Une adresse IPv6 est réduite à son préfixe /64 (un foyer reçoit souvent tout un /64).

Un test de la vraie pile envoie deux inscriptions avec deux faux `X-Forwarded-For` : elles comptent pour un seul réseau.

Le limiteur de Better Auth, dans la mémoire du guichet, lit l'adresse avec la même règle (même réglage), sans rien écrire en base.

## 7. L'empreinte d'IP et le sel du jour

MCPlain ne garde **aucune adresse IP en clair**, ni en base ni dans les journaux. Il garde une empreinte :
HMAC-SHA256(adresse, sel du jour).

- Le sel est un nombre aléatoire tiré une fois par jour UTC (table `ip_salts`).
- Il est effacé après 2 jours. Ensuite, même MCPlain ne peut plus refaire l'empreinte d'une adresse : les compteurs de la
  veille deviennent anonymes, puis sont effacés aussi (inscriptions, quotas et jetons des analyses, même rythme).

C'est comme un vestiaire qui donne un numéro pour la soirée, puis jette le carnet le lendemain.

## 8. La limite de comptes par réseau

Pour éviter qu'un robot crée des milliers de comptes, l'API compte les inscriptions par empreinte et par jour UTC (table
`signup_counts`). Au-delà de **30** (`MCPLAIN_SIGNUPS_PER_IP_PER_DAY`), elle refuse avec le code `signup_limit`, et le site dit :
« Trop de comptes ont été créés depuis ce réseau aujourd'hui. Réessaie demain, ou depuis un autre réseau (la 4G de ton
téléphone, par exemple). »

**Pourquoi 30** : une école ou une entreprise sort souvent sur Internet avec une seule adresse. Une classe entière doit pouvoir
s'inscrire le même jour depuis le même réseau.

- Seule la **création** est limitée, jamais la connexion ni le mot de passe oublié.
- Une inscription compte quand elle passe la garde, même si l'adresse avait déjà un compte : on ne dit jamais si une adresse est
  inscrite.
- Pour une adresse déjà inscrite, le guichet répond exactement comme pour une adresse nouvelle (code 200, même corps, même
  page « Regarde tes e-mails »), mais n'envoie aucun e-mail. Un test le vérifie.
- Chaque refus est compté par jour, **sans adresse** (table `signup_refusals`). Le tableau admin de la séance 9c le montrera ; si
  les refus sont fréquents, on relèvera la limite.

## 9. Les rôles PostgreSQL

Chaque service ne voit que ce dont il a besoin. Un rôle « superutilisateur » passe outre tous les droits : seul le service
ponctuel `migrate` l'utilise.

| Rôle | Qui | Ce qu'il peut faire |
| --- | --- | --- |
| `mcplain` (propriétaire) | service `migrate`, qui s'arrête ensuite | migrations Alembic, création des rôles et de leurs mots de passe |
| `mcplain_app` | API, chef d'atelier, rédacteur | lire et écrire les tables de MCPlain (quotas et historique compris) ; **rien** dans `auth`, rien dans `mail_outbox` |
| `mcplain_guichet` | guichet | tout dans son schéma `auth` ; seulement ajouter des lignes à `mail_outbox` |
| `mcplain_facteur` | facteur | lire et effacer `mail_outbox` ; lire `ai_admin_alerts` et remplir `emailed_at` |

Les tables de Better Auth sont créées par la migration Alembic `0006`, à partir du SQL que Better Auth génère lui-même : une
seule source de migrations. Un test compare la base à ce que Better Auth attend (`auth/tests/schema.test.ts`).

`mcplain_app` peut créer une base de données (`CREATEDB`) : les tests de la pile en créent une pour essayer le chef d'atelier
sans toucher aux vraies données. Ce droit ne donne aucun accès au schéma `auth`.

## 10. Ce que tu lances, toi

1. `scripts/init-secrets.sh` : ajoute à `.env` les secrets qui manquent, tirés au hasard (`openssl rand`). Il ne remplace jamais
   une valeur déjà là, n'affiche aucune valeur, seulement le nom des clés ajoutées. Il ajoute aussi `COMPOSE_PROFILES=dev` pour
   que Mailpit démarre.
2. `docker compose up -d --build`.
3. Crée ton compte dans le navigateur (`http://localhost:<MCPLAIN_WEB_PORT>/fr/account/sign-up`).
4. Ouvre Mailpit : `http://127.0.0.1:8025`. L'e-mail de confirmation y est. Clique sur le lien.
5. `scripts/make-admin.sh ton@adresse` : passe ce compte en admin, seulement si son adresse est vérifiée.
6. `scripts/make-bench-account.sh` : crée le compte du banc d'essai (section 18), avec l'adresse et le mot de passe que
   `init-secrets.sh` a mis dans `.env`. Jamais ton compte personnel.
7. Connecte-toi, puis « Mon compte », section Sécurité : active la double authentification (section 19). Sans elle, ton compte
   admin n'a aucun pouvoir.

**Aucun secret ne va dans GitHub.** La CI tourne avec des valeurs écrites en dur, marquées « test only ».

## 11. Où lire les e-mails en développement

Dans le profil `dev`, le facteur envoie tout à **Mailpit**, un faux serveur d'e-mails qui garde tout et n'envoie rien dehors.
Son interface est sur `http://127.0.0.1:8025` (lié à ta machine seulement). Hors du profil `dev`, Mailpit n'existe pas : un test
le vérifie. À la mise en ligne, on choisira un vrai fournisseur SMTP (jamais un serveur d'e-mails maison).

## 12. Limites connues

- Les réseaux `front` et `back` de compose peuvent sortir sur Internet. Le guichet n'en a pas besoin ; un vrai filtre de sortie
  viendra à la mise en ligne, comme pour le rédacteur.
- En développement, l'API reste ouverte sur `127.0.0.1:8000` : quelqu'un sur ta machine pourrait lui écrire un faux
  `X-Forwarded-For` en passant à côté du site. À la mise en ligne, ce port ne sera pas publié.
- Le renvoi d'un lien de confirmation (`/send-verification-email`) n'a pas d'ALTCHA : seul le limiteur de Better Auth le freine.
- La route `/internal/auth-guard` vérifie que l'appel vient bien du conteneur du guichet (son adresse sur le réseau compose).
  `/internal/account-erase` (section 17) fait la même vérification. Dans l'autre sens, les routes `/internal/*` du guichet
  (session, recherche, bannissement) vérifient que l'appel vient du conteneur de l'API (`MCPLAIN_INTERNAL_PEERS`, `api` par
  défaut) ; le site ne les relaie jamais.
- L'API garde 30 secondes la réponse « qui est connecté ». Désactiver la double authentification retire donc le pouvoir admin
  au bout de 30 secondes au plus. Un bannissement, lui, compte tout de suite : l'API oublie alors toutes les réponses gardées
  de ce compte, quelle que soit la session.
- L'empreinte d'IP change chaque jour UTC (nouveau sel) : à minuit, l'anti-rafale d'un réseau sans compte repart de zéro.
- L'anti-rafale lit puis compte en deux temps : deux demandes au même instant peuvent passer à 31. La prise de jeton du quota,
  elle, est atomique.
- Appeler l'API en direct (port 8000, en développement seulement) donne une adresse inconnue : tous ces appels partagent une
  seule empreinte, donc un seul quota de 3.

## 13. Les tests

- `cd auth && pnpm test` : réglages de Better Auth, hook de garde, dépôt dans la boîte de départ, rôle jamais modifiable,
  suppression avec mot de passe, aucune adresse dans la session.
- `cd api && uv run pytest` : lecture d'IP, empreinte, sel, ALTCHA (valide, expiré, mauvaise signature, rejoué), garde (limite de
  30, compteur des refus), `current_user()`, facteur, fichier compose.
- `cd api && MCPLAIN_TEST_POSTGRES_URL=... uv run pytest -m postgres` : les droits de chaque rôle sur une vraie base (en CI).
- `cd web && pnpm test:stack` : le parcours complet dans un vrai navigateur, avec Mailpit, et la mesure d'ALTCHA ; en 9b, un
  visiteur qui use ses 3 analyses puis voit « Créer un compte », le cache toujours ouvert, un compte qui voit 10, son historique
  affiché puis effacé (captures clair et sombre, 1280 et 390 px). Les compteurs sont remis à zéro par `psql` en propriétaire,
  jamais par l'API : il n'existe aucun réglage qui coupe les quotas. Les tests qui inscrivent un compte remettent aussi à zéro
  le compteur d'inscriptions (`signup_counts`) de la même façon.
- Séance 9c-1 : `cd auth && pnpm test` (`two-factor.test.ts`, `bans.test.ts`), `cd api && uv run pytest tests/test_admin.py`,
  `cd web && pnpm test` (`admin.test.tsx`), et sur la vraie pile `cd api && uv run pytest -m docker tests/test_compose_admin.py`
  et `cd web && pnpm test:stack` (`admin.spec.ts`). Voir section 23.
- `cd api && uv run pytest tests/test_quotas.py tests/test_refunds.py` : quotas 3 et 10, admin et banc, cache et liste non
  comptés, jeton rendu ou gardé, jamais rendu deux fois, 5 demandes simultanées pour 3 jetons, anti-rafale par réseau et par
  compte, faux `X-Forwarded-For`, ALTCHA rejoué, historique, effacement à la suppression du compte, et la table des codes.

## 14. Les quotas : combien d'analyses par jour

Une **nouvelle** analyse coûte un jeton. Les jetons reviennent chaque nuit à minuit UTC (01:00 ou 02:00 à Paris, selon
l'heure d'été ; le site affiche l'heure locale du visiteur).

| Qui | Jetons par jour | Compté sur |
| --- | --- | --- |
| Sans compte | 3 (`MCPLAIN_QUOTA_ANONYMOUS`) | l'empreinte de l'adresse IP (tout le réseau ensemble) |
| Avec un compte | 10 (`MCPLAIN_QUOTA_ACCOUNT`) | le compte, quel que soit le réseau |
| Admin avec double authentification | sans limite | |
| Admin sans double authentification | 10, comme un compte (et l'anti-rafale) | le compte |
| Compte du banc (section 18) | sans limite si `MCPLAIN_ALLOW_BENCH_ROLE` est vrai, sinon 10 comme un compte | |

**Ce qui ne compte pas** :

- un MCP déjà analysé, servi par le cache : le rapport le dit (« Cette analyse n'a pas été décomptée. ») ;
- un lien qui donne une liste de plusieurs MCP (le clic sur un MCP de la liste, lui, compte) ;
- une demande refusée avant création : format (400, 415), ALTCHA raté, anti-rafale, file pleine (503) ;
- les notices et traductions de l'IA (`/notice`, `/translation`) : elles ne lisent ni ne touchent les quotas.

**Comment c'est compté.** Le jeton est pris à la création de l'analyse, en **une seule instruction SQL** (insérer à 1, ou
ajouter 1 seulement sous la limite). Dix clics au même instant ne peuvent pas prendre plus de jetons qu'il n'en reste. Le cache
et la liste ne sont connus qu'après : c'est le chef d'atelier qui **rend** alors le jeton, une seule fois par analyse.

**Quand il n'y a plus de jeton**, la demande est quand même acceptée, en « cache seulement ». Le chef d'atelier demande OSV
comme d'habitude et sert le cache s'il existe. Sinon, il s'arrête **sans rien télécharger**, avec l'état `quota_exhausted`. Ce
n'est pas un verdict : la page n'a ni jauge ni « NON VÉRIFIÉ », seulement le message :

- sans compte : les 3 analyses du réseau sont utilisées, le réseau partagé expliqué, et un bouton « Créer un compte » ;
- avec un compte : « Tu as utilisé tes 10 analyses du jour. Elles reviennent à {heure}. » ;
- dans les deux cas : « Les MCP déjà analysés restent consultables. »

Ces demandes ne vont jamais dans l'historique ni dans le cache. Elles sont comptées par jour, sans adresse (table
`quota_refusals`), pour le tableau admin de la séance 9c.

**Le compteur** de l'en-tête lit `GET /api/quota` (rien n'est compté, pas d'ALTCHA) et se met à jour après chaque analyse.
Sans compte, une phrase propose un compte gratuit pour les réseaux partagés (entreprise, open space, école).

## 15. Le jeton rendu : faute de MCPlain ou faute du lien

Une seule table décide (`REFUND_BY_CODE` dans `api/src/mcplain_api/refunds.py`). Un test échoue si un code d'échec écrit
quelque part dans le moteur ou dans l'API n'y est pas. Un code inconnu rendrait le jeton, mais ce cas ne doit jamais arriver.

| Ce qui s'est passé | Codes | Jeton |
| --- | --- | --- |
| L'atelier ou le chef d'atelier a échoué | `internal_error`, `interrupted`, `atelier_timeout`, `atelier_invalid_result`, `atelier_error` (et les refus internes `analyze.job_*`, `analyze.archive_mismatch`) | rendu |
| Le registre ou le réseau a eu un souci | `fetch.timeout`, `fetch.network_error`, `fetch.http_error`, `fetch.github_rate_limited`, `fetch.unexpected_response`, `fetch.invalid_json` | rendu |
| Fichier abîmé ou empreinte absente (ce n'est pas la faute du visiteur) | `fetch.integrity_missing`, `fetch.integrity_mismatch` | rendu |
| Le lien mène nulle part | `fetch.not_found`, `fetch.npm_not_found`, `fetch.pypi_not_found`, `fetch.github_repo_not_found`, `fetch.github_ref_not_found`, `fetch.pypi_no_files`, `input.reference_not_found`, `analyze.subdir_not_found`, `analyze.not_a_directory` | gardé |
| Le paquet sort de la liste blanche ou n'est pas sûr | `fetch.host_not_allowed`, `fetch.insecure_url`, `fetch.bad_redirect`, `fetch.too_many_redirects` | gardé |
| Paquet trop gros, format refusé, archive refusée par l'atelier | `fetch.too_large`, `archive.*` | gardé |
| Entrée refusée (en pratique déjà refusée par l'API avant création) | `input.*` | gardé |

Une analyse qui aboutit (verte, orange, rouge, ou grise parce que le langage n'est pas pris en charge, le code est compilé…)
garde son jeton : l'analyse a vraiment eu lieu.

## 16. L'anti-rafale

Au plus **30 demandes d'analyse par heure glissante** (`MCPLAIN_BURST_PER_HOUR`), cache compris : par empreinte d'IP sans compte,
**par compte** quand on est connecté. Une classe de 25 élèves connectés sur le même réseau n'est donc pas bloquée. L'admin (avec sa
double authentification) et le banc ne sont pas freinés. La 31e demande reçoit 429 (code `burst_limit`) avec l'en-tête `Retry-After`, et le site dit : « Trop de
demandes en peu de temps. Réessaie dans {minutes} minutes. »

Ordre des contrôles de `POST /api/analyses` : format (400, 415) ; anti-rafale (429) ; ALTCHA (403, `altcha_invalid`, le site dit
« La vérification anti-robot n'a pas abouti. Réessaie. ») ; validation de l'entrée (400) ; jeton (pris, ou « cache seulement ») ;
création.

## 17. L'historique

Toute analyse demandée par un compte connecté va dans son historique (table `user_history`), cache compris. Le même lien
redemandé dans la minute n'est gardé qu'une fois. La page « Mon compte » montre les 100 dernières : date, lien collé (en texte
brut), couleur avec son mot, lien vers le rapport, mention « depuis le cache ». Le bouton « Effacer mon historique » demande une
confirmation (`DELETE /api/account/history`).

**Supprimer son compte efface aussi l'historique et les quotas.** Avant de supprimer un compte (une fois le mot de passe
vérifié), le guichet appelle `POST /internal/account-erase` de l'API, sur le réseau `back`, hors du relais du site. Si l'appel
échoue, la suppression est annulée et le site dit : « La suppression n'a pas pu se faire. Réessaie dans un instant. »

## 18. Le compte du banc d'essai

Le banc (`bench/`) lance 52 analyses d'un coup : il lui faut un compte sans quota. Ce n'est **jamais** un compte admin (en 9c,
l'admin aura la double authentification, et un robot ne doit jamais être admin). C'est le rôle `bench` :

- sans quota ni anti-rafale, mais ALTCHA obligatoire comme pour tout le monde, et **aucun pouvoir admin** ;
- seulement si `MCPLAIN_ALLOW_BENCH_ROLE` est vrai : faux par défaut, vrai dans la pile de test, en CI et dans ton `.env` local.
  Faux, un compte `bench` est un compte normal (10 par jour) ;
- le rôle ne se donne que par la base, avec `scripts/make-bench-account.sh` : il inscrit le compte par le guichet comme un
  navigateur, puis `psql` en propriétaire confirme l'adresse et pose le rôle. Il ne touche jamais un admin ;
- hors de GitHub Actions, le script refuse l'adresse `bench@bench.mcplain.invalid` et tout mot de passe qui contient `test-only` :
  ce sont les valeurs publiques de `bench.yml`, elles ne doivent servir que dans la pile jetable de la CI
  (`bench/tests/test_bench_account_script.py`).

L'adresse et le mot de passe du compte banc sont créés par `scripts/init-secrets.sh` (`MCPLAIN_BENCH_EMAIL`,
`MCPLAIN_BENCH_PASSWORD`). En CI, des valeurs « test only » sont écrites en dur dans `bench.yml`. Le banc se connecte par le
site, puis demande chaque analyse avec le cookie et une solution ALTCHA neuve. `scripts/notice-smoke.sh` utilise le même compte.

## 19. La double authentification de l'admin

Le compte admin peut bloquer des comptes : s'il était volé, les dégâts seraient grands. Le mot de passe seul ne suffit donc pas.
Il faut aussi un **code à 6 chiffres** qui change toutes les 30 secondes dans **Google Authenticator** (TOTP, SHA-1, émetteur
« MCPlain »). C'est le plugin `twoFactor` de Better Auth (version épinglée 1.7.15).

C'est comme un coffre à deux clés : le mot de passe est dans ta tête, le code est dans ton téléphone. Un voleur doit avoir les deux.

**Pouvoir admin = rôle `admin` ET double authentification active.** L'API le vérifie à chaque fois (`CurrentUser.is_admin` dans
`session_user.py`), jamais seulement le site. Un admin sans double authentification est un compte normal partout : quota de 10,
anti-rafale, 403 sur toutes les routes `/api/admin/*`. Sa page `/admin` dit seulement « Active la double authentification », avec
le lien vers la section Sécurité. Désactiver la double authentification retire donc le pouvoir admin (au bout de 30 secondes au
plus, à cause du cache de l'API).

La double authentification n'est proposée qu'au rôle `admin` : le guichet refuse `/two-factor/enable` à tout autre compte. Les
autres comptes n'ont que l'e-mail vérifié.

**Activer** (« Mon compte », section Sécurité) :

1. Tu écris ton mot de passe.
2. Le site affiche une clé, groupée par 4 lettres pour la lecture. Dans Google Authenticator : bouton +, « Saisir une clé de
   configuration », compte « MCPlain », la clé, « Basée sur l'heure », « Ajouter ». Pas de QR code : pas de nouvelle
   dépendance, et la clé ne passe par aucun service tiers. Elle reste dans la page, n'est jamais écrite dans un journal ni dans
   l'adresse de la page, et disparaît dès l'étape suivante. Le guichet la garde chiffrée en base.
3. Tu écris le premier code affiché par l'application. La double authentification ne s'allume qu'à ce moment.
4. Le site montre **10 codes de secours, une seule fois**. Bouton « Imprimer » : la page s'imprime en thème clair, fond blanc,
   avec les codes seulement. Range-les loin de ton téléphone.

**Se connecter** : mot de passe, puis code. Le mot de passe seul ne donne **aucune session** : le guichet efface celle que Better
Auth vient de créer et pose seulement un petit cookie de défi (10 minutes). Le champ du code ouvre le clavier numérique sur
téléphone et accepte un code collé (« 123 456 » devient « 123456 »). Le lien « Utiliser un code de secours » remplace le code de
l'application ; chaque code de secours ne sert qu'une fois.

**Jamais d'appareil de confiance.** L'option `trustDevice` de Better Auth est forcée à faux par le guichet sur les routes de
vérification, et un cookie `trust_device` envoyé par le navigateur est retiré avant que Better Auth ne lise la requête. Le code
est demandé à chaque connexion.

**Verrouillage** : 5 essais par défi (ensuite, il faut recommencer la connexion), et après **10 codes faux d'affilée**, le compte
est verrouillé **15 minutes**, même avec le bon code. Le limiteur ajoute 3 essais de code en 10 secondes par adresse.

**Codes de secours neufs** : section Sécurité, « Créer de nouveaux codes de secours », avec le mot de passe. Les anciens ne
marchent plus.

**Toutes les routes qui créent une session respectent la double authentification.** Un seul endroit décide
(`auth/src/session-gate.ts`), au moment où la session est écrite en base. Pour un compte avec la double authentification, seules
ces routes peuvent créer une session : `/sign-in/email` (la session est aussitôt effacée par le plugin), `/two-factor/verify-totp`,
`/two-factor/verify-backup-code`, `/two-factor/enable`, `/two-factor/disable` et `/change-password` (les trois dernières demandent
déjà d'être connecté). Toute autre route est refusée, et le doute aussi : route inconnue, appel sans contexte, valeur étrange.
C'est le cas du lien de vérification d'e-mail, qui connecte d'habitude tout seul. La réinitialisation du mot de passe ne crée
jamais de session. Les routes qui enverraient un code par e-mail (`/two-factor/send-otp`, `/two-factor/verify-otp`) et celle qui
réafficherait la clé (`/two-factor/get-totp-uri`) sont fermées (404).

## 20. Tout perdu : téléphone et codes de secours

Il n'existe **aucune route web** pour ça, exprès. Sur la machine qui tient la base :

```bash
scripts/reset-admin-2fa.sh ton@adresse
```

Le script, comme `make-admin.sh`, passe par `psql` en propriétaire. En une seule instruction, il éteint la double
authentification du compte, efface sa clé et ses codes, et efface toutes ses sessions. Le compte garde son rôle, mais n'a plus de
pouvoir admin jusqu'à ce que tu réactives la double authentification (section 19).

## 21. Bloquer un compte (bannissement)

Le bannissement est « maison » : **pas** le plugin admin de Better Auth (il permet de se faire passer pour un autre compte et
ouvre des routes `/api/auth/admin/*` dont on n'a pas besoin).

- L'état est rangé dans le schéma `auth` : la date (`bannedAt`) et un motif facultatif (`banReason`, 200 caractères au plus,
  vérifié aussi par la base). Migration `0009`. Seul le guichet l'écrit ; le site ne peut jamais l'écrire, et ces deux champs ne
  sont jamais envoyés au navigateur.
- Au bannissement, le guichet efface **toutes** les sessions du compte, et l'API oublie toutes ses réponses gardées : le compte
  est déconnecté tout de suite, partout.
- Ensuite, le guichet refuse toute nouvelle session de ce compte, sur **toutes** les routes, sans exception (même celles de la
  double authentification). Le mot de passe est vérifié d'abord : sans le bon mot de passe, on voit seulement « E-mail ou mot de
  passe incorrect. ». Avec, le site dit seulement « Ce compte est bloqué. » : ni motif, ni détail.
- L'API traite un compte banni comme un visiteur sans compte sur les routes publiques (quota de son réseau), et répond 403
  (`api.account_blocked`) sur les routes du compte.
- L'admin ne peut ni se bloquer lui-même ni bloquer un autre admin.
- Débloquer remet le compte dans son état normal : il se reconnecte avec son mot de passe.
- Son historique et ses quotas sont gardés pendant le blocage (rien n'est effacé) : débloquer le remet comme avant. Pour tout
  effacer, il y a la suppression du compte.

Dans le site, page **`/admin`** (ou `/fr/admin`), section « Comptes » : recherche par **adresse e-mail exacte** (il n'existe pas de
liste de tous les comptes), puis « Bloquer ce compte » avec un motif facultatif, ou « Débloquer ce compte ». Le motif est affiché
en texte brut (`RawText`).

Routes de l'API : `GET /api/admin/accounts?email=`, `POST /api/admin/accounts/{id}/ban` (corps `{"reason": ...}`) et
`POST /api/admin/accounts/{id}/unban`. Toutes passent par un seul filtre (`admin_gate` dans `app.py`) : admin avec double
authentification, sinon 403. Les changements (POST, DELETE) exigent en plus l'en-tête `Origin` égal à `MCPLAIN_PUBLIC_URL` ;
un autre `Origin`, ou pas d'`Origin` du tout, est refusé (protection CSRF : un autre site ne peut pas agir à la place de l'admin).
Un test passe par le vrai relais du site pour vérifier que l'en-tête `Origin` arrive bien à l'API. L'API ne lit pas le schéma
`auth` : elle demande au guichet sur ses routes internes (`/internal/accounts`, `/internal/accounts/ban`,
`/internal/accounts/unban`).

**Pourquoi pas de bannissement sans compte.** Un visiteur sans compte n'est connu que par l'empreinte de son adresse IP, et cette
empreinte change chaque jour (nouveau sel, section 7). Un bannissement ne tiendrait pas plus d'une journée, et il toucherait tout
le réseau (une école entière derrière une seule adresse). Les protections des visiteurs sans compte restent le quota de 3,
l'anti-rafale et ALTCHA.

## 22. La lecture de la session et sa limite

Deux chemins, deux règles :

- **L'API** demande « qui est connecté ? » au guichet sur sa route interne `GET /internal/session`, sur le réseau `back`, hors du
  relais du site. Le guichet vérifie que l'appel vient du conteneur de l'API, puis lit la session côté serveur
  (`auth.api.getSession`) : pas de limiteur. La réponse donne l'id, l'e-mail vérifié ou non, le rôle, la double authentification
  et l'état banni. En cas de doute (champ absent), l'API compte le compte comme banni et sans double authentification.
- **Le navigateur** lit sa session sur la route publique `/api/auth/get-session`, par le relais du site. Elle a sa limite :
  **600 lectures par minute et par vraie adresse** du visiteur.

Pourquoi 600 et pas 100 (la limite d'avant la séance 9b) : le site relit la session à chaque page. Une classe de 25 élèves derrière
un seul réseau dépassait vite 100 par minute, et le site les affichait alors comme déconnectés (décision de David du
24 novembre 2026). Les autres routes du guichet gardent 100 par minute.

La vraie adresse : le limiteur lit l'adresse ajoutée par notre relais (`web/client-ip.js`), comptée depuis la droite avec
`MCPLAIN_TRUSTED_PROXY_HOPS` (section 6). Un faux `X-Forwarded-For` écrit par le navigateur ne change rien. Un test de la vraie
pile le vérifie avec deux visiteurs : deux conteneurs différents qui passent par le site.

## 23. Les tests de la séance 9c-1

- Admin sans double authentification : 403 sur toutes les routes admin, quota de 10 (`test_admin.py`, `test_quotas.py`, pile).
- Un test liste toutes les routes `/api/admin/*` et les essaie avec : anonyme, compte normal, compte avec une double
  authentification mais sans rôle admin, banc, admin sans double authentification, admin banni. Tous refusés. Une nouvelle route
  sans test fait échouer la liste.
- Double authentification : mot de passe seul sans session, code faux refusé, verrouillage après 10 codes faux, code de secours
  accepté une seule fois, `trustDevice` envoyé quand même et ignoré, lien de vérification d'e-mail et réinitialisation du mot de
  passe sans session (`two-factor.test.ts`, pile).
- CSRF : un POST admin d'une autre origine, ou sans origine, est refusé, aussi à travers le relais.
- get-session : 429 au-delà de 600 par minute pour une adresse, l'autre adresse passe.
- Bannissement : connexion refusée, sessions mortes, API qui refuse, ni soi-même ni un admin, débloquer marche, message neutre
  (`bans.test.ts`, `test_admin.py`, pile).
- Aucun secret TOTP, code de secours ni mot de passe dans la sortie des services pendant le parcours (`test_compose_admin.py`).
- Les codes TOTP des tests sont calculés dans les tests (HMAC avec `node:crypto` ou `hmac` de Python) : aucune porte dérobée.


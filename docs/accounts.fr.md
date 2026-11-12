# Les comptes de MCPlain

Ce guide explique à un débutant comment marchent les comptes : qui fait quoi, où vivent les secrets, et ce que tu lances
toi-même. Les phrases sont courtes. Séance 9a, faite le 10 novembre 2026.

## 1. Le tableau d'ensemble

Un compte sert à une seule chose pour l'instant : se connecter. Les quotas (combien d'analyses par jour) viendront en
séance 9b. Un compte est gratuit, il demande une adresse e-mail vérifiée et un mot de passe de 10 à 128 caractères.

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
- Le champ `role` vaut `user` ou `admin`. Le site ne peut jamais le changer : seul `scripts/make-admin.sh` le fait.
- La télémétrie de Better Auth est coupée (elle l'est déjà par défaut ; on l'écrit quand même, et `BETTER_AUTH_TELEMETRY=0`).
- Son limiteur de requêtes est allumé : par exemple, au plus 3 connexions en 10 secondes depuis une même adresse.

Avant une inscription, une connexion ou une demande de mot de passe oublié, le guichet demande l'avis de l'API
(`/internal/auth-guard`, voir plus bas). Si l'API dit non, la réponse est claire et sans détail technique.

## 3. Le badge (le cookie de session)

Après la connexion, le navigateur reçoit un badge : le cookie `mcplain.session_token`. Il le montre à chaque visite.

- `HttpOnly` : un script de la page ne peut pas le lire.
- `SameSite=Lax` : un autre site ne peut pas s'en servir pour agir à ta place.
- `Secure` en production (adresse en `https://`) : il ne voyage que chiffré.

Ce cookie sert seulement à rester connecté. C'est pourquoi il n'a pas besoin de bandeau de consentement.

Quand l'API devra savoir qui est connecté (séance 9b), elle transmettra ce cookie au guichet (`current_user()` dans
`api/src/mcplain_api/session_user.py`) et gardera la réponse 30 secondes. Elle ne transmet que les cookies `mcplain.`.

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

**Le coût choisi : 2000** (`MCPLAIN_ALTCHA_COST`). Mesure du 10 novembre 2026, dans Chromium avec le processeur ralenti 4 fois
(le réglage « téléphone moyen » des outils de Chrome), 10 essais : médiane 110 ms, au plus 322 ms. Il reste donc de la marge
sous la seconde, même sur un téléphone plus lent. Le test `pnpm test:stack` refait cette mesure à chaque fois.

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
  veille deviennent anonymes, puis sont effacés aussi.

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
| `mcplain_app` | API, chef d'atelier, rédacteur | lire et écrire les tables de MCPlain ; **rien** dans `auth`, rien dans `mail_outbox` |
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

## 13. Les tests

- `cd auth && pnpm test` : réglages de Better Auth, hook de garde, dépôt dans la boîte de départ, rôle jamais modifiable,
  suppression avec mot de passe, aucune adresse dans la session.
- `cd api && uv run pytest` : lecture d'IP, empreinte, sel, ALTCHA (valide, expiré, mauvaise signature, rejoué), garde (limite de
  30, compteur des refus), `current_user()`, facteur, fichier compose.
- `cd api && MCPLAIN_TEST_POSTGRES_URL=... uv run pytest -m postgres` : les droits de chaque rôle sur une vraie base (en CI).
- `cd web && pnpm test:stack` : le parcours complet dans un vrai navigateur, avec Mailpit, et la mesure d'ALTCHA.

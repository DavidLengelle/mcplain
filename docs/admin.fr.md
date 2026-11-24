# Le tableau de bord admin

Ce guide explique la page `/admin` (ou `/fr/admin`) : ce que montre chaque cadran, d'où vient chaque chiffre, le solde estimé
du crédit Anthropic, l'e-mail sous 2 $, les boutons de relance et le journal. Séance 9c-2, faite le 24 novembre 2026.

C'est comme le tableau de bord d'une voiture : il dit combien il reste d'essence, ce qui chauffe et combien de kilomètres
on a faits, mais pas qui était assis à l'arrière.

## 1. Qui voit la page

Seul l'admin **avec sa double authentification** voit le tableau (voir `docs/accounts.fr.md`, section 19). Toutes les routes
sont sous `/api/admin/*` et passent par le même filtre que la 9c-1 (`admin_gate`) : admin avec double authentification, et
`Origin` égal à `MCPLAIN_PUBLIC_URL` pour un changement (POST, DELETE). Un test liste toutes les routes `/api/admin/*` et les
essaie avec un visiteur sans compte, un compte normal, un compte banc et un admin sans double authentification : toutes
refusées, aussi à travers le vrai relais du site.

## 2. Ce que le tableau ne montre jamais

Les cadrans ne donnent que des **chiffres globaux**. Jamais d'adresse e-mail, jamais d'identifiant de compte, jamais
d'empreinte d'IP, jamais de `request-id`, jamais le lien collé par un visiteur. Un test lit chaque réponse des cadrans et y
cherche ces valeurs. Seules la section « Comptes » (9c-1) et le journal admin montrent un identifiant de compte.

## 3. La période et le bouton « Actualiser »

- Sélecteur **7 j / 30 j**, 30 jours par défaut. La période finit aujourd'hui et compte des **jours UTC** (minuit à Paris
  est 23 h ou 22 h UTC). Une autre valeur que 7 ou 30 est refusée par l'API (400, `api.invalid_days`).
- La dépense du jour et du mois, elle, suit toujours le **jour et le mois calendaires UTC**, comme les fusibles.
- Pas de rafraîchissement automatique : le bouton **« Actualiser »** relit tout.
- Les requêtes sont bornées : 31 jours au plus, 20 lignes pour le top, 50 alertes, 20 notices, 50 lignes de journal. Un index
  sur la date des analyses (`ix_analyses_created_at`, migration `0010`) garde la lecture rapide.

## 4. Les cadrans, dans l'ordre de la page

Chaque barre est une petite barre CSS (`<progress>`) avec **son chiffre écrit à côté** : la longueur ou la couleur n'est
jamais seule. Les barres sont en bleu (`--accent`) ; le cuivre (`--warn`) ne sert qu'aux alertes (fusible ou budget atteint,
solde sous le seuil, alerte non lue). Aucune bibliothèque de graphiques, aucune nouvelle couleur.

### L'argent

| Cadran | Ce qu'il montre | D'où vient le chiffre |
| --- | --- | --- |
| Dépense de l'IA | aujourd'hui face au fusible du jour, le mois face au budget, la dépense par jour, par type (notice, traduction), le nombre d'appels payés | table `ai_calls` (`cost_usd`). Aujourd'hui et le mois viennent de **la même fonction que les fusibles**, `spent_since` de `api/src/mcplain_api/ai_budget.py`. Un appel payé est un appel dont le coût est plus grand que 0. |
| Solde estimé | voir la section 5 | table `credit_entries` et `ai_calls` |

Si le rédacteur est coupé (pas de clé) ou en pause pour tout le monde, une ligne en cuivre le dit.

### La santé

| Cadran | Ce qu'il montre | D'où vient le chiffre |
| --- | --- | --- |
| Alertes de l'IA | les alertes, les plus récentes d'abord, avec le code, la date, le type de texte, le code HTTP, l'e-mail envoyé ; bouton « Marquer comme lue » | table `ai_admin_alerts`. Le `request-id` rangé dans les détails n'est jamais renvoyé. |
| Rejets de l'IA | les rejets par code de raison et par jour, et le **taux de rejets `encoding`** | `ai_calls.reject_reason`. Taux = rejets `encoding` des notices / appels de notice payés. |
| Notices à relancer | les notices et traductions rejetées, en échec ou en pause, avec le lien vers leur rapport | table `ai_texts`. Une notice en pause montre sa raison (fusible, budget, plafond de 4) et n'a pas de bouton. |
| Échecs d'analyse | les échecs par code, avec « jeton rendu (faute de MCPlain) » ou « jeton gardé (faute du lien) » | `analyses.error_code` et le code du moteur, classés par la table unique `REFUND_BY_CODE` (`docs/accounts.fr.md`, section 15) |

### L'usage

| Cadran | Ce qu'il montre | D'où vient le chiffre |
| --- | --- | --- |
| Analyses par jour | total, servies par le cache, nouvelles | `analyses` terminées (`done` ou `failed`), `from_cache` |
| Couleurs des verdicts | rouge, orange, gris, vert, chacun avec son mot ; les cas gris par code | `result.verdict.color` et `result.verdict.gray_case` ; une analyse échouée compte en gris (`error`) |
| MCP les plus analysés | les 20 premiers de la période (type et nom, toutes versions), le lien vers le dernier rapport, « Relancer l'analyse » | `result.source.kind` et `result.source.name`. Les noms viennent de tiers : affichés par `RawText`, et le lien est fait avec l'**identifiant de l'analyse**, jamais avec le nom. |
| Langages non pris en charge | les langages demandés, comptés | `result.status = unsupported_language` et `result.language` |
| Refus | par jour : inscriptions refusées (`signup_limit`), quota épuisé sans compte, quota épuisé avec un compte | tables `signup_refusals` et `quota_refusals`, sans adresse. L'anti-rafale et un ALTCHA raté ne sont comptés nulle part (voir la feuille de route, « Plus tard »). |
| Fréquentation | les comptes créés par jour | route interne du guichet `GET /internal/accounts/created-per-day?days=7` ou `30` (section 7) |

Puis le **journal admin** (section 8), puis la section « Comptes » de la 9c-1.

## 5. Le solde estimé

L'API d'Anthropic ne donne pas le solde de ton crédit. MCPlain l'**estime** :

```
solde estimé = dernier relevé + recharges depuis ce relevé − dépense notée dans ai_calls depuis ce relevé
```

- Un **relevé**, c'est le solde que tu lis dans la console Anthropic et que tu recopies. Une **recharge**, c'est l'argent que tu
  ajoutes au crédit. Les deux sont des **écritures** (table `credit_entries`) : type, montant en dollars, date, note facultative
  de 100 caractères (texte brut, affichée par `RawText`). Même unité et même précision que les coûts de `ai_calls`.
- La date d'une écriture est **le moment de la saisie** : pas de champ date, car une date passée fausserait le calcul. Lis donc
  la console, puis saisis tout de suite.
- Le calcul est **une seule fonction**, `estimated_balance` de `ai_budget.py`, utilisée par l'API et par le facteur. La dépense
  vient de `spent_since`, la fonction des fusibles.
- On ne peut supprimer que **la dernière écriture** (une erreur de frappe). Une plus ancienne reste.
- **Sans aucun relevé**, le cadran affiche « Saisis un premier relevé (solde lu dans la console Anthropic) » et aucun e-mail
  ne part.
- Le cadran rappelle toujours « Estimation : le vrai solde est dans la console Anthropic. » L'estimation peut s'écarter du vrai
  solde : MCPlain calcule ses coûts avec ses propres prix (`MCPLAIN_AI_PRICE_*`), et la console compte aussi ce qui ne passe pas
  par MCPlain (par exemple `scripts/notice-smoke.sh`).

## 6. L'e-mail sous 2 $

- Seuil : `MCPLAIN_BALANCE_ALERT_USD` (2 par défaut), lu par l'API et par le facteur (un test vérifie la même valeur).
- C'est le **facteur** qui vérifie le solde, **une fois par minute**, donc au plus une minute après un appel payé ou une
  écriture. Le rédacteur n'a pas été touché pour ça.
- Il envoie un e-mail en texte brut à `MCPLAIN_ADMIN_EMAIL` (le même destinataire que les alertes de la séance 8) : le solde
  estimé, la date du dernier relevé, et l'adresse de la page `/admin`.
- **Une seule fois.** L'état « alerte envoyée » est gardé en base (table `balance_alert`). Il ne passe à « envoyé » **qu'après
  un envoi SMTP réussi** ; si l'envoi échoue, le facteur réessaie à la minute suivante.
- **Réarmement (hystérésis)** : l'alerte ne repart que lorsqu'une écriture (ajout ou suppression de la dernière) fait remonter
  le solde estimé au-dessus du seuil. Une dépense ne la réarme jamais.
- Sans `MCPLAIN_ADMIN_EMAIL`, aucun e-mail ne part (le cadran montre quand même le solde).
- Le facteur n'écrit pas dans `mail_outbox` : il envoie lui-même, comme les alertes admin. Il a reçu quatre droits et rien de
  plus (migration `0010`, testé sur PostgreSQL) : lire `created_at` et `cost_usd` de `ai_calls`, lire `credit_entries`, lire
  `balance_alert` et changer sa seule colonne `sent_at`, et les réglages `MCPLAIN_PUBLIC_URL` et `MCPLAIN_BALANCE_ALERT_USD`.

C'est comme le voyant de réserve d'une voiture : il s'allume une fois, et ne se rallume qu'après un passage à la pompe.

## 7. Les actions

Chaque bouton demande une **confirmation** (« Oui, relancer » ou « Annuler »).

**Relancer la notice** (`POST /api/admin/texts/{id}/retry`) : seulement pour une notice ou une traduction **rejetée** ou **en
échec**. L'admin ne contourne **jamais** le budget. Avant de remettre le texte en file, l'API vérifie, avec les fonctions du
rédacteur (`ai_budget.py`) : la coupure, la pause pour tout le monde, le plafond de **4 appels par jour** pour ce texte, puis le
**budget du mois** et le **fusible du jour** avec le pire coût de l'appel. Si quelque chose bloque, la page le dit clairement
(« Bloqué : le budget IA du jour est épuisé. Il revient demain. »). Ensuite le rédacteur refait lui-même tous ses contrôles.
C'est la seule exception à « un texte rejeté reste rejeté » (`docs/ai.fr.md`, section 6).

**Relancer l'analyse** (`POST /api/admin/analyses/{id}/rerun`) : une nouvelle analyse de la même demande (même lien, même
sélection), qui **ignore le cache** (colonne `analyses.ignore_cache`), sans quota ni jeton, mise en file normalement et traitée
dans l'atelier normal. OSV est interrogé comme toujours.

- Le cache n'est pas une table à part : c'est la plus récente analyse terminée avec la même clé (source, sélection, réputation,
  versions du moteur et des règles) et des voyants. Une relance **réussie** devient donc ce que le cache sert ensuite : il n'y a
  jamais deux entrées à gérer pour la même clé.
- Une relance **en échec** n'est jamais candidate : l'ancien bon résultat reste servi. Jamais un bon résultat remplacé par un
  échec.
- Le rapport ne montre rien de spécial au public. La trace est dans le journal admin.

**Marquer comme lue** (`POST /api/admin/alerts/{id}/read`) : note la date de lecture d'une alerte, une seule fois.

**Ajouter une écriture** (`POST /api/admin/credit`) et **supprimer la dernière** (`DELETE /api/admin/credit/{id}`) : section 5.

## 8. Le journal admin

Table `admin_actions` : date, action, type de cible et identifiant de la cible. La page montre les **50 dernières lignes**
(`GET /api/admin/journal`).

| Action | Cible |
| --- | --- |
| Compte bloqué, compte débloqué (9c-1) | identifiant du compte |
| Notice relancée | identifiant du texte (`ai_texts`) |
| Analyse relancée | identifiant de la **nouvelle** analyse, avec le lien vers son rapport |
| Alerte marquée comme lue | identifiant de l'alerte |
| Écriture ajoutée, écriture supprimée | identifiant de l'écriture |

Une action refusée (un fusible qui bloque, un compte admin qu'on ne peut pas bloquer) n'écrit rien.

## 9. La fréquentation et le guichet

L'API n'a aucun droit sur le schéma `auth`. Pour compter les comptes créés, elle demande au guichet sa route interne
`GET /internal/accounts/created-per-day?days=7` ou `30` : même contrôle d'appelant que les autres routes internes (le conteneur
de l'API seulement), jours UTC, et une réponse faite **seulement de dates et de nombres** (un test vérifie qu'aucune adresse ni
aucun identifiant n'en sort). Le guichet compte avec l'adaptateur de Better Auth, un comptage par jour, sans charger aucun compte.
Si le guichet ne répond pas, le cadran le dit (503), au lieu d'afficher zéro.

## 10. Les réglages

| Réglage | Qui le lit | Rôle |
| --- | --- | --- |
| `MCPLAIN_BALANCE_ALERT_USD` (2) | API, facteur | seuil de l'e-mail |
| `MCPLAIN_ADMIN_EMAIL` | facteur | destinataire des alertes et de l'e-mail du solde |
| `MCPLAIN_PUBLIC_URL` | API, facteur | origine acceptée pour les changements ; adresse de `/admin` dans l'e-mail |
| `MCPLAIN_AI_MONTHLY_BUDGET_USD`, `MCPLAIN_AI_DAILY_FUSE_USD`, `MCPLAIN_AI_PRICE_*`, `MCPLAIN_AI_MAX_TOKENS`… | rédacteur **et** API | l'API les reçoit aussi (jamais la clé), pour que le tableau et le contrôle avant relance voient les mêmes chiffres que le rédacteur ; un test compare les deux services dans `compose.yaml` |

## 11. Les tests

- `cd api && uv run pytest tests/test_admin_dashboard.py tests/test_credit.py tests/test_admin_actions.py tests/test_admin.py` :
  chaque cadran sur un jeu de données connu (jours vides, changement de mois, minuit UTC), dépense du tableau = dépense des
  fusibles, solde (sans relevé, relevé seul, relevé + recharges + dépense), e-mail unique, réarmement par ajout et par
  suppression, aucun e-mail sans relevé, nouvel essai après un échec SMTP, relance de notice refusée si prête, bloquée par le
  fusible, le budget, la pause, la coupure et le plafond de 4, aucune donnée par personne.
- `tests/test_dispatcher.py` : une relance réussie devient ce que le cache sert ; une relance en échec garde l'ancien résultat.
- `MCPLAIN_TEST_POSTGRES_URL=... uv run pytest -m postgres` : les chemins JSON des cadrans sur JSONB, et les quatre droits du
  facteur, rien de plus, avec un vrai tour d'envoi joué par son rôle.
- `uv run pytest -m docker tests/test_compose_dashboard.py` : toutes les routes fermées à travers le relais, origine exigée,
  cadrans sans donnée par personne, e-mail réel dans Mailpit (seulement si `MCPLAIN_ADMIN_EMAIL` est réglé), relance traitée
  par le vrai chef d'atelier.
- `cd auth && pnpm test` (`created-per-day.test.ts`) ; `cd web && pnpm test` (`admin-dashboard.test.tsx`), `pnpm test:e2e`
  (`admin-dashboard.spec.ts`, captures clair et sombre, 1280 et 390 px, sans défilement de côté) et `pnpm test:stack`
  (`admin.spec.ts`).

# L'IA dans MCPlain

Ce guide explique à un débutant ce que fait l'IA dans MCPlain, et ce qu'elle ne fait jamais. Les phrases sont courtes.

## 1. À quoi elle sert

Quand un rapport est prêt, MCPlain demande à Claude Sonnet 5.5 :

- une **notice** en langage courant : ce que fait ce serveur, à quoi il peut servir ;
- un **titre clair** et une phrase pour chaque outil ;
- une **phrase d'alerte**, seulement si quelque chose semble illogique ;
- à part, la **traduction** en français des descriptions écrites par l'auteur.

Le verdict (couleur, voyants, règles) vient du moteur Python, jamais de l'IA. Aucune sortie de l'IA n'entre dans le moteur ni
dans le cache des analyses. Si l'IA est coupée, en panne ou refusée, le rapport reste complet : seule la notice change.

C'est comme un stagiaire à qui on donne une fiche déjà remplie : il la met en bonnes phrases, mais il ne voit pas le dossier,
et ce n'est pas lui qui décide.

## 2. Ce que l'IA voit, et ce qu'elle ne voit pas

L'IA ne lit jamais le code, ni un texte écrit par un tiers. Pour la notice, elle reçoit un **formulaire à cases**, construit
par `api/src/mcplain_api/ai_form.py` depuis le rapport validé en base :

| Case | Ce qu'elle contient | Filtre |
| --- | --- | --- |
| `tools` | nom de l'outil, et oui ou non pour les 6 voyants | lettres, chiffres et `_`, 40 caractères, 60 outils. Un autre signe devient `_`. Un nom vide devient `tool_1`, `tool_2`... |
| `domains_cited_in_code` | les noms d'hôte des adresses écrites dans le code du serveur | `[a-z0-9.-]`, 253 caractères, 20 domaines. Jamais le chemin de l'adresse. Les fichiers de test ne comptent pas. |
| `libraries` | toujours vide | Le rapport ne garde que les dépendances signalées comme malveillantes. Le moteur n'a pas été touché pour ça. |
| `language`, `tool_count` | le langage (liste fixe) et le nombre d'outils | |

Elle ne voit pas : la couleur du verdict, le nom du paquet, les descriptions, le README, les commentaires, les chaînes du code,
les signalements. « danger » compte comme « oui », sans plus.

Un test (`test_canary_never_reaches_the_request_body`) place le mot `CANARY-7f3a` dans tous ces textes, et vérifie qu'il n'est
jamais dans la requête.

**La traduction est un appel séparé.** Elle reçoit seulement les descriptions de l'auteur, présentées comme des données à
traduire. Elle ne voit ni le formulaire ni les voyants. Le rapport n'a pas de description du serveur : on traduit les descriptions
des outils, puis celles de leurs paramètres, 12 000 caractères au total. Ordre : d'abord toutes les descriptions d'outils, puis les
paramètres dans l'ordre des outils. Ce qui dépasse reste en langue d'origine. Un paramètre sans description n'est pas envoyé.

Chaque texte porte un `id` fabriqué par MCPlain avec des positions seulement : `tool_<i>` pour un outil, `tool_<i>_param_<j>` pour
un paramètre. Jamais le nom d'un paramètre (`url`, `max_length`...) ni un autre texte de l'auteur : les noms ne sont ni envoyés ni
traduits. Les contrôles s'appliquent élément par élément ; un élément rejeté, absent ou inconnu garde son original. Sur le site, le
bouton « Voir l'original » bascule toute la carte « Ce qu'il annonce » d'un coup, description et paramètres.

Le prompt interdit à l'IA de juger la sécurité, et d'inventer une fonction que les noms ne suggèrent pas. Un nom d'outil reste
écrit par un inconnu : c'est pourquoi la sortie est contrôlée après coup.

## 3. Les deux schémas

**Ce que l'IA doit rendre** (décrit dans le prompt, vérifié par pydantic côté MCPlain, tout requis, aucun autre champ) :

```json
{ "summary": "...", "use_cases": ["..."],
  "tool_titles": [{ "name": "...", "title": "...", "sentence": "..." }],
  "mismatch": false, "alert": "" }
```

`name` est le nom filtré du formulaire. La traduction rend `{ "items": [{ "id": "tool_0", "text": "..." }] }`, avec les mêmes `id`
qu'en entrée (`tool_<i>` pour un outil, `tool_<i>_param_<j>` pour un paramètre).

**Ce que l'API publique renvoie au site** (`content`, après contrôle) :

```json
{ "summary": "...", "use_cases": ["..."],
  "tool_titles": [{ "tool_index": 0, "title": "...", "sentence": "..." }],
  "alert": null }
```

- `name` devient `tool_index`, la position de l'outil dans le rapport : deux noms bruts peuvent donner le même nom filtré, la
  position, elle, est unique.
- `mismatch` disparaît : `alert` vaut `null` quand `mismatch` est faux ou quand l'alerte est vide. Le site traite aussi une alerte
  vide comme absente : il n'affiche alors rien, jamais « tout va bien ».
- La réponse contient aussi `status`, `source` (`ai` ou `template`), `fallback`, `model`, `date`, `reject_reason` et `resume`.
  Jamais le coût, ni les jetons, ni le `request-id`.

## 3 bis. Pourquoi pas de sortie imposée

L'API sait imposer un schéma JSON à la réponse (`output_config.format`). MCPlain ne s'en sert pas. Le 9 novembre 2026, en
français, la sortie imposée a cassé les accents au début du texte (« Ă » suivi d'un caractère à la place de « à » ou « é »), deux
fois de suite avec la même entrée (request-id `req_011Cgsjjrio3ZYG4SZuNTuMH`). La même requête sans sortie imposée, le prompt
demandant juste du JSON, était propre, avec 190 jetons d'entrée en moins. La matrice du 10 novembre a ensuite montré que la sortie
imposée n'était pas la seule cause : le défaut revient aussi sans elle (voir 4 bis). La décision de ne pas l'utiliser reste.

Le prompt système décrit donc l'objet JSON attendu et demande de répondre par cet objet seul. MCPlain accepte seulement le texte
entier comme un objet JSON, ou entouré d'un seul bloc ```` ```json ````. Tout le reste (une phrase avant ou après, deux objets, un
JSON coupé) est rejeté avec `bad_json`.

**La sécurité ne repose pas sur le schéma de l'API, mais sur notre contrôle de sortie** : pydantic relit chaque champ, puis les
règles ci-dessous (longueurs, mots rassurants, liens, caractères invisibles, encodage) s'appliquent comme avant. Le schéma reste
dans le code (`NOTICE_SCHEMA`), pour revérifier un jour la sortie imposée avec `scripts/notice-diagnose.sh --with-format`.

## 4. Les contrôles de sortie

`api/src/mcplain_api/ai_check.py` lit ce que l'IA a écrit, **avant** tout enregistrement. L'IA peut alerter, jamais rassurer.

| Contrôle | Notice | Traduction |
| --- | --- | --- |
| Longueur | résumé 600, 3 usages de 160, titre 40, phrase 160, alerte 240 | 3 fois l'original + 50 |
| Mots rassurants (`ai_words.py`) | un seul mot : **toute** la notice est rejetée | ne s'applique pas : c'est le texte de l'auteur, marqué comme tel |
| Liens | `http://`, `https://`, `www.`, `<`, `>`, `](`, e-mail, domaine absent du formulaire | une adresse absente de l'original |
| Caractères invisibles | même liste que R01 et O07 | même liste |
| Encodage cassé | `Ã` ou `Ă` suivi d'un caractère, `Â` suivi d'une espace insécable, `â€`, U+FFFD | idem, sauf si l'original contient déjà la séquence |

- Un titre trop long, ou un outil inconnu : seul ce titre part, l'outil garde son nom technique.
- Une traduction rejetée : seule cette description reste en original.
- `mismatch` faux : l'alerte est ignorée. Le site n'écrit jamais « tout va bien ».
- Une sortie rejetée n'est ni affichée ni gardée. Il reste un code : `forbidden_word`, `link`, `length`, `unknown_tool`,
  `invisible`, `encoding`, `refusal`, `max_tokens`, `bad_json`.
- Un refus de l'IA (`refusal`) donne la notice de secours. Aucun modèle de repli n'est demandé.

Faux positifs acceptés par David, avec un test à leur nom :

- « Il se connecte à GitHub par une connexion sécurisée (HTTPS). » est rejeté. Conséquence : la notice de secours.
- Un outil `get_weather` avec la capacité `secrets` donne un avis, même s'il lit seulement sa propre clé d'API. L'avis ne change
  pas la couleur.

- Un texte qui parlerait lui-même d'encodage et citerait « Ã© » est rejeté (code `encoding`). Conséquence : la notice de secours.

**Pourquoi la règle `encoding`.** Au premier vrai essai (9 novembre 2026), la notice française contenait « Ă » suivi d'une espace
insécable à la place de « à », et « Ă© » à la place de « é » : les octets UTF-8 lus en Windows-1250. Le code de MCPlain est en
UTF-8 de bout en bout, et un test le vérifie (`test_french_text_crosses_the_chain_unchanged`) : ces caractères étaient déjà dans le
texte rendu par l'IA. La règle les arrête. C'est un défaut intermittent (voir 4 bis). Les prompts sont en `notice-v3` et
`translation-v3`.

## 4 bis. Le défaut d'encodage est intermittent, et la parade

Avec la même requête, la notice française est sortie cassée 4 fois sur 5 le 9 novembre au soir, puis propre 3 fois sur 3 le
10 novembre. Matrice du 10 novembre 2026 (`scripts/notice-diagnose.sh --matrix`, 15 appels, 0,071 dollar) :

| Variante | Cassées | Jetons entrée | Jetons sortie | Coût moyen |
| --- | --- | --- | --- | --- |
| V1 requête actuelle | 0/3 | 857 | 280 | 0,0045 |
| V2 sans la liste des mots interdits | 1/3 | 809 | 297 | 0,0046 |
| V3 effort `medium` | 0/3 | 857 | 283 | 0,0045 |
| V4 sans `thinking` | 0/3 | 858 | 303 | 0,0047 |
| V5 ancien mode B | 0/3 | 1011 | 314 | 0,0052 |

Aucune variante ne supprime le défaut à coup sûr : il vient de l'API ou du modèle, pas de notre requête. MCPlain garde la requête
actuelle (V1) et s'en protège :

- **Un rejet `encoding` donne un nouvel appel tout de suite, une seule fois.** Si le second est propre, il est gardé.
- **Deux rejets `encoding` de suite** : notice de secours, état `failed` (pas `rejected`), nouvel essai possible une heure plus tard,
  quand la notice est redemandée.
- **Au plus 4 appels par jour UTC pour une même clé de cache**, tous motifs confondus. Au-delà : notice de secours jusqu'au
  lendemain (état `paused`, code `daily_text_cap`, le site dit « demain »). Un appel compte une fois, même quand une API surchargée
  le fait réessayer après 20 s.
- **Chaque essai passe d'abord par le fusible** (pire coût), le second comme le premier.
- Pour la traduction, une seule description cassée fait rejeter tout l'appel, qui est réessayé de la même façon.
- Les autres rejets restent définitifs pour cette version du prompt.

Chaque appel est noté dans la table `ai_calls` : date, type, langue, issue, code de rejet, jetons, coût, `request-id`, jamais le
texte. Elle sert au plafond, aux fusibles, et au futur tableau admin (taux de rejets `encoding`).

Sont aussi rejetés : un domaine écrit par l'IA qui n'est pas dans le formulaire, comme `ASP.NET`. Les noms de fichiers courants
(`package.json`, `Node.js`) passent.

## 5. La notice de secours

Elle est écrite à la main, et l'API la renvoie toujours, en codes de texte et paramètres. Les textes sont dans
`api/src/mcplain_api/locales/`, servis par `GET /api/messages/{lang}` à côté de ceux du moteur. Le moteur n'a pas changé.

Elle dit le nombre d'outils, ce que le serveur peut faire d'après les voyants, et « MCPlain n'a pas pu écrire de résumé
automatique pour ce serveur. » Une autre variante existe quand aucun outil n'est reconnu.

## 6. Le cache

La table `ai_texts` garde un seul texte par clé : type, langue, empreinte, version du prompt, modèle. L'empreinte (`form_hash`)
est le SHA-256 du formulaire en JSON canonique.

- Même formulaire, même langue, même prompt, même modèle : **0 jeton**. Deux analyses de la même version partagent la notice.
- Dix visiteurs : une ligne et un appel. La clé est unique, et le rédacteur prend sa ligne avec
  `SELECT ... FOR UPDATE SKIP LOCKED`.
- Un échec n'est jamais gardé comme prêt.
- Un texte rejeté reste rejeté : on ne paie pas deux fois. Pour réessayer, on change la version du prompt
  (`NOTICE_PROMPT_VERSION`, `TRANSLATION_PROMPT_VERSION`). Seule exception : l'encodage cassé (voir 4 bis).

Pas d'appel non plus sans outil reconnu, pour une analyse échouée, ou sans description à traduire. Le banc ne demande jamais
de notice : un test le vérifie.

## 7. Les fusibles

Avant chaque appel, le rédacteur calcule le **pire coût** : l'entrée estimée (taille de la requête en octets, divisée par 2)
plus tout `max_tokens` au prix de sortie. Il ajoute la dépense déjà enregistrée dans `ai_calls` :

- au-delà du **budget du mois** (`MCPLAIN_AI_MONTHLY_BUDGET_USD`, 10 dollars) : pas d'appel, retour le mois prochain ;
- au-delà du **fusible du jour** (`MCPLAIN_AI_DAILY_FUSE_USD`, sinon 1/20 du budget, donc 0,50 dollar) : pas d'appel, retour demain.

Le site le dit (« La notice automatique revient demain »). Les notices en cache restent affichées. Les journées et les mois
sont comptés en UTC.

Pire coût avec les réglages par défaut : **0,055 dollar** pour une notice (60 outils et 20 domaines de taille maximale) et
**0,085 dollar** pour une traduction (12 000 caractères accentués). En pratique, c'est bien moins.

## 8. Les erreurs

| Réponse de l'API | Ce que fait le rédacteur |
| --- | --- |
| 400 `invalid_request_error` avec « usage limits », ou 402 `billing_error` | Plafond atteint. Pause d'une heure pour tout le monde, puis un seul essai. Alerte admin au plus une fois par 24 h. |
| 401 ou 403 | Fonction coupée jusqu'au redémarrage du service. Alerte admin. |
| Autre 400 ou 4xx, redirection | Requête mal formée. Alerte admin. Nouvel essai possible 10 minutes plus tard. |
| 429, 529, 5xx, délai dépassé | Un seul nouvel essai après 20 s, puis échec. Nouvel essai possible 10 minutes plus tard. |

Dans tous les cas, le rapport affiche la notice de secours. Le texte d'une erreur n'est jamais gardé, seuls le code HTTP et le
`request-id`. Une alerte est une ligne de la table `ai_admin_alerts` et une ligne de journal ; depuis la séance 9a, le facteur
l'envoie aussi par e-mail à l'admin (au plus un par code et par 24 h, voir `docs/accounts.fr.md`).

Sans clé (`MCPLAIN_ANTHROPIC_API_KEY` vide), la fonction est coupée : état `disabled`, aucun appel tenté, notice de secours.
C'est le cas de la CI et du banc : **0 jeton par construction**.

## 9. Où vit la clé

Seul le service `redacteur` de `compose.yaml` reçoit la clé. Il utilise la même image que l'API, avec une autre commande
(`mcplain-redacteur`). Il n'a ni socket Docker, ni montage, ni port ouvert. Son système de fichiers est en lecture seule, il ne
tourne pas en root, sans aucune capacité (`cap_drop: ALL`).

**La sortie vers Internet est limitée dans le code, comme pour le chef d'atelier** : aucun proxy, aucun pare-feu Docker. Le réseau
`back` peut sortir, mais `ai_client.py` n'appelle qu'une adresse écrite en dur, sans suivre les redirections et sans proxy. Un code
injecté dans ce conteneur pourrait donc sortir ailleurs : c'est une limite connue, et il ne lit que la base de données.

**Pourquoi la clé n'est jamais dans GitHub.** Le dépôt est public. Une clé dans un fichier, ou même dans un secret de CI, peut
fuiter, et n'importe qui dépenserait ton budget. La CI n'en a pas besoin : tout y est simulé avec `respx`, et un test échoue si
une vraie connexion est tentée. Un autre test échoue si un fichier de `.github/` contient le mot « anthropic ». Un filtre retire
la clé des journaux.

## 10. Ce que David règle dans la console Anthropic

1. Crée un **espace de travail dédié** à MCPlain. Crée la clé dans cet espace, et nulle part ailleurs.
2. Mets une **limite mensuelle** sur cet espace (par exemple 10 dollars, comme le budget de MCPlain). C'est le dernier filet : il
   marche même si le compteur de MCPlain se trompe.
3. Active une **alerte à 80 %** de cette limite.
4. Colle la clé dans le fichier `.env` local, à la ligne `MCPLAIN_ANTHROPIC_API_KEY=`, et jamais ailleurs.

Si les prix changent, change `MCPLAIN_AI_PRICE_INPUT_PER_MTOK` et `MCPLAIN_AI_PRICE_OUTPUT_PER_MTOK`. Si tu changes de modèle,
change aussi `MCPLAIN_AI_THINKING` : `between_tools` n'existe que sur Sonnet 5.5.

## 11. Essayer pour de vrai

`scripts/notice-smoke.sh` demande la notice en français et en anglais, et la traduction, pour `uvx mcp-server-fetch`. Il affiche le
résultat contrôlé, le code de raison en cas de rejet, les jetons et le coût. Il dépense de vrais jetons : au plus 0,20 dollar
environ. Lui seul appelle vraiment l'API. C'est toi qui le lances, jamais les tests.

`scripts/notice-smoke.sh` affiche la version des prompts et le commit de l'image qui tourne (`scripts/image-commit.sh`, qui compare
l'empreinte du code Python rangée dans l'image avec les 50 derniers commits). Il s'arrête si l'image n'est pas construite depuis le
dernier commit.

`scripts/notice-diagnose.sh` envoie une fois la notice française d'une analyse déjà en base, construite par les mêmes fonctions que
le rédacteur (`notice_body`). Mode par défaut : la requête réelle. Avec `--with-format` : la même, plus `output_config.format`. Il
affiche le texte brut, chaque caractère non ASCII avec son code, le résultat du contrôle de sortie, les jetons et le coût (environ
0,6 centime). Avec `--matrix`, il envoie la notice 3 fois pour chacune de 5 variantes (V1 la requête réelle, V2 sans la liste des
mots interdits dans le prompt, V3 effort `medium`, V4 sans `thinking`, V5 l'ancien mode B à l'identique), puis affiche un tableau :
réponses cassées sur 3, jetons et coût moyens, coût total (environ 8 centimes). Il n'écrit rien en base, rien dans le cache, et ne
compte pas dans le fusible. C'est toi qui le lances.

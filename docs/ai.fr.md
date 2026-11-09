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
traduire. Elle ne voit ni le formulaire ni les voyants. Le rapport n'a pas de description du serveur : seules celles des outils
sont traduites, 12 000 caractères au total. Les suivantes restent en langue d'origine.

Le prompt interdit à l'IA de juger la sécurité, et d'inventer une fonction que les noms ne suggèrent pas. Un nom d'outil reste
écrit par un inconnu : c'est pourquoi la sortie est contrôlée après coup.

## 3. Les deux schémas

**Ce que l'IA doit rendre** (`NOTICE_SCHEMA` dans `ai_prompts.py`, tout requis, aucun autre champ) :

```json
{ "summary": "...", "use_cases": ["..."],
  "tool_titles": [{ "name": "...", "title": "...", "sentence": "..." }],
  "mismatch": false, "alert": "" }
```

`name` est le nom filtré du formulaire. La traduction rend `{ "items": [{ "id": "tool_0", "text": "..." }] }`, avec les mêmes `id`
qu'en entrée (`tool_` suivi de la position de l'outil dans le rapport).

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
texte rendu par l'IA. La règle les arrête, et la version du prompt est passée à `notice-v2` pour ne plus servir la notice cassée.

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
  (`NOTICE_PROMPT_VERSION`, `TRANSLATION_PROMPT_VERSION`).

Pas d'appel non plus sans outil reconnu, pour une analyse échouée, ou sans description à traduire. Le banc ne demande jamais
de notice : un test le vérifie.

## 7. Les fusibles

Avant chaque appel, le rédacteur calcule le **pire coût** : l'entrée estimée (taille de la requête en octets, divisée par 2)
plus tout `max_tokens` au prix de sortie. Il ajoute la dépense déjà enregistrée :

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
`request-id`. Pour l'instant, une alerte est une ligne de la table `ai_admin_alerts` et une ligne de journal. L'e-mail viendra
en séance 9.

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

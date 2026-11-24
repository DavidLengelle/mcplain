# Travaux prévus

Ce fichier garde les décisions prises pour les séances à venir. Lis la partie qui concerne ta séance avant de
commencer. Les séances 7, 7 bis, 7 ter, 7 quater, 7 quinquies, 8, 9a, 9b et 9c (9c-1, 9c-2, 9c-3), le corpus partie 2 et l'enquête fetch sont faits. Les parties
« Protections » et « Adresses IP partagées » sont codées (séances 8, 9a et 9b).

## SÉANCE 7 : FIABILITÉ DU MOTEUR (faite le 29 octobre 2026, moteur 0.3.0)

- [x] Banc d'essai sur 52 vrais serveurs MCP (`bench/`, guide : `docs/bench.fr.md`), première mesure avant
      correction gardée (`bench/results/2026-10-29-engine-0.2.1.md`).
- [x] Verrou du vert (décidé le 29 octobre 2026) : nouveau cas gris `network_unresolved`, voyant « Va sur
      Internet » avec la note « non suivi ». Conditions et exceptions : `docs/rules.fr.md`.
- [x] Causes de gris corrigées : méthodes d'une classe ré-exportée par un paquet ; table de fonctions sans
      pouvoir (`operator.add`) ; objet rendu par une fonction qui construit toujours la même classe ; paquets
      serveur du SDK MCP v2 et SDK tmcp ; gros fichier de données qui faisait échouer l'analyse.
- [x] Gris partiel : champ `verdict.coverage` et bloc « Ce que MCPlain a pu lire » sur le site.
- [x] Banc chaque lundi en CI (`.github/workflows/bench.yml`), alerte si une couleur change.
- [x] Les rouges sur de vrais paquets : décidé le 3 novembre 2026 (faux rouges corrigés en séance 7 quater).
      L'enquête est dans `bench/private/rouges.md`, hors de git.

## SÉANCE 7 BIS (novembre 2026, moteur 0.4.0, règles version 2)

Décisions du 29 octobre 2026, codées :

- [x] O06 ne s'allume plus quand la plage déclarée exclut toutes les versions visées par l'alerte MAL-, ou quand
      aucune de ces versions n'est encore publiée sur le registre. Le chef d'atelier demande la liste au registre
      et la range dans `reputation.json` ; l'atelier reste sans réseau. Registre injoignable, plage ou version non
      comprise : O06 s'allume comme avant. Une ligne des détails techniques dit pourquoi O06 est écartée.
- [x] Un `require()` dont toutes les valeurs possibles du chemin finissent par un texte écrit dans le code qui se
      termine exactement par `.json` (en minuscules) est une lecture de fichier, pas du code dynamique. Sinon
      (`.JSON`, extension calculée, valeur inconnue), O08 comme avant.
- [x] Dossier privé `bench/private/` (hors de git) pour l'enquête sur les rouges.
- [x] En CI, un rouge sur un vrai paquet est masqué (« red #n » et une empreinte) et fait échouer le banc.

Causes de gris restantes, pour plus tard (mesure propre du 3 novembre 2026, moteur 0.4.0) :

1. `not_a_server` (3 serveurs) : enveloppes dont le vrai code est dans une dépendance, et paquets empaquetés
   sans dépendance déclarée. Piste : analyser la dépendance qui porte le code, ou lire les imports du code
   empaqueté.
2. `no_tools_found` (3) : outils déclarés dans des paquets séparés (MongoDB), ou d'une façon encore inconnue
   (tmcp de Storybook, logfire-mcp).
3. `incomplete_tracking` (2) : objets reçus en paramètre (postgres-mcp), code exécuté dans le navigateur
   (server-puppeteer).
4. `network_unresolved` (1) : client réseau passé en paramètre à une autre fonction (mcp-server-sentry).

## SÉANCE 7 QUATER (3 novembre 2026, moteur 0.5.0, règles version 3)

Fait :

- [x] Diagnostic de la mesure du 3 novembre (lecture incomplète des 31 serveurs gris dans la simulation de la
      séance 7 ter, voyants suspects) dans `bench/private/diagnostic.md`, hors de git.
- [x] Lecture, trois premières causes : gestionnaires `tools/list` et `tools/call` du SDK MCP empaqueté qui ne
      sont plus pris pour un outil ; description qui insère une constante texte du même fichier (gabarit ou
      f-string) ; parties d'une bibliothèque réseau qui ne peuvent pas envoyer (`net.BlockList`,
      `tls.checkServerIdentity`, `http2.constants`, `urllib3.util.retry.Retry`...), sans compter pour le verrou.
- [x] Voyants : « Texte caché » suit le jeu de contrôles bidirectionnels de R01 (pas U+200E, U+200F, U+061C) et
      ignore les drapeaux émoji ; `__import__("x")` et `importlib.import_module("x")` avec un nom écrit dans le
      code ne sont plus du code construit à l'exécution.
- [x] Décisions du 3 novembre codées : R04 (champ nommé de l'environnement, connexion locale, socket Docker en
      O08), R12 (il faut viser un outil d'analyse), R02 et nouvelle O09 « Demande de silence à vérifier », R08 et
      nouvelle O10 (commande d'installation qui modifie la configuration d'un client MCP), R10 et nouvelle O11
      « Contacte Internet dès l'installation ». Détails et faux positifs restants : `docs/rules.fr.md`.
- [x] Les alertes portent un titre précis (`title`) et les paramètres de leurs textes (`params`) ; le site les
      affiche avec `RawText`.
- [x] Mesure propre (moteur 0.5.0) : 5 verts, 36 oranges, 1 rouge, 10 gris, 82,4 % (`docs/bench.fr.md`).
- [x] Dependabot : aucune nouvelle demande depuis la #40.

Décidé le 3 novembre 2026 et codé en séance 7 quinquies (voir plus bas) : la référence du banc, le sens des
couleurs (inchangé) et les trois propositions sur les voyants.

Pistes restantes :

1. Lecture, suites possibles (par fréquence) : objets reçus en paramètre, rangés dans `self` ou paramètres de
   lambda (6 serveurs) ; outils déclarés d'une façon inconnue (7 serveurs, 7 façons) ; descriptions tirées d'une
   table de définitions (4) ; appels réseau sous une forme non reconnue, comme `(0, undici_1.fetch)(...)` (4) ;
   profondeur d'appels au-delà de 5 (4) ; `mcp.tool()(fn)` ; `Context` de FastMCP (`ctx.info`).
2. Un chemin de client MCP écrit en morceaux (`path.join(home, ".cursor", "mcp.json")`) n'est pas reconnu comme
   chemin sensible : ni R08 ni O10 ne se déclenchent alors (limite qui existait déjà pour R08). Une piste :
   composer les morceaux littéraux de `path.join`.

## SÉANCE 7 QUINQUIES (4 novembre 2026, moteur 0.5.1, règles version 3)

Décisions du 3 novembre 2026, codées :

- [x] Sens des couleurs : INCHANGÉ (rouge > orange > gris > vert ; orange = pouvoirs trouvés, rien de caché).
      Raison : la simulation (O01 et O08 ne colorent plus) donnait 34 gris sur 52. La question sera rouverte quand
      le moteur lira mieux les descriptions fabriquées et le réseau.
- [x] Le code d'une bibliothèque embarquée jamais appelé ne compte plus pour les voyants ni pour O08. Une
      bibliothèque embarquée est un module que l'outil d'empaquetage marque d'un chemin `node_modules`
      (`// .../node_modules/x/...` d'esbuild et bun, `//#region` de rolldown). Le code exécuté au chargement du
      module compte toujours, les règles rouges comptent partout. En cas de doute (pas de marque, fin du module
      inconnue, fonction anonyme), il compte. Limites : un paquet minifié sans marque, et le Python, ne sont pas
      concernés.
- [x] Les caractères invisibles écrits en échappement dans des données n'allument plus « Texte caché ». R01 et O07
      ne changent pas pour les noms et descriptions d'outils.
- [x] Tests et construction : `snapshot-tests`, `smoke-tests`, `benchmarks` (et `snapshot_tests`, `smoke_tests`),
      `test-*.js` (et `.mjs`, `.cjs`, `.ts`, `.py`), `build.js` à la racine (et `build.py`), sauf s'ils sont
      importés par le serveur ou lancés à l'installation. Pas fait : les scripts de `scripts/` que rien n'importe
      (ils ne faisaient pas partie de la décision).
- [x] Desktop Commander reste rouge (R10), décision de David. L'alerte R10 d'une requête d'installation nomme
      maintenant les adresses écrites dans le fichier et ce que lit le code d'installation (variables, fichiers,
      commandes), à partir des trouvailles du moteur. Limite : le moteur ne suit pas encore quelles valeurs lues
      partent vraiment dans la requête.
- [x] Référence publique du banc : un rouge vérifié par David porte `verified: true` et ses règles rouges ; il est
      nommé en CI. `bench/baseline.json` contient les 52 serveurs.
- [x] Tests réseau : server-filesystem 2.1.0 écrit par ses propres fonctions (`pinned-directory.js`), changement
      normal du paquet ; les liens des sources des règles sont comparés à une liste enregistrée
      (`engine/tests/data/rule_sources.json`) au lieu de sites extérieurs.

## CORPUS, PARTIE 1 (4 novembre 2026, moteur 0.5.1)

- [x] Corpus de serveurs honnêtes dont la réponse est connue : `engine/tests/fixtures/corpus/` (5 verts, 5 oranges,
      5 gris), jugés par `engine/tests/test_corpus.py` (OK, ACCEPTABLE, ÉCHEC). Guide : `docs/corpus.fr.md`.
- [x] Corpus privé des pièges (`engine/tests/fixtures/corpus-private/`, hors de git) : `.gitignore`, test de garde,
      hook `.githooks/pre-commit`, rapport `bench/private/corpus.md`.
- [x] ~~Les 5 pièges écrits en chat, déposés par David dans le dossier privé.~~ Abandonné (décision de David du
      4 novembre 2026) : plus aucun piège écrit en chat, les cas positifs viennent de DVMCP.
- [ ] Écart à revoir avec David (attendu inchangé, `known_gap`) : `green/slug-ts-class` sort gris
      (`dynamic_descriptions`, outils rangés dans un champ de classe et enregistrés par `Object.entries`).
- [ ] MCPTox (arXiv 2508.14925) : dépôt `github.com/zhiqiangwang4/MCPTox-Benchmark` sans licence, rien importé.

## CORPUS, PARTIE 2 (9 novembre 2026, moteur 0.5.2, règles version 3)

- [x] O02 : `shlex.split` et `str.split` en Python, `String.prototype.split` en JavaScript gardent l'étiquette, sur la
      liste et sur un élément. Un texte qui commence par un mot écrit dans le code suivi d'une espace a un programme fixe :
      pas d'O02, l'outil reste en O08. Sans shell, pas de R09. `orange/echo-terminal` donne O02 et O08.
- [x] Un orange dont la lecture est incomplète porte `verdict.coverage`. Le site montre le bloc au même endroit que pour le
      gris, avec une phrase à lui : sur un orange, « Rien de suspect » serait faux. `native-launcher` passe dans
      `orange/` ; `gray/unit-notes` (honnête) le remplace, le test demande cinq gris.
- [x] « Ce que MCPlain ne sait pas faire » : les attaques qui arrivent par les données, le serveur qui en imite un autre.
- [x] Mesure du banc : 5 verts, 34 oranges, 1 rouge, 12 gris, 78,4 % (`docs/bench.fr.md`).
- [x] Décisions de David (moteur 0.6.0, règles version 4, 25 règles) : O12 et R13, consignes cachées dans une description,
      sans fixture d'attaque ; défis 4 et 7 hors portée, avec leurs limites sur l'accueil et dans le README ; un paquet présenté
      comme serveur MCP sans outil reconnu donne `no_tools_found` ; référence du banc avec sentry en gris.
- [x] DVMCP (défis 1 à 10, commit `cdc4c6b`) : attendus, test et CI sur main. Défis 1, 4, 6 et 7 hors portée.
- [ ] Défis 5 et 10 de DVMCP : cas ACCEPTABLE (décidé par David le 9 novembre), leur attendu reste rouge. R13 reste
      volontairement étroite. À revoir si des signalements montrent des pièges passés en orange.
- [ ] Défis 11 à 15 de DVMCP (identité, chaîne d'approvisionnement) : pas examinés.
- [ ] DVMCP n'a pas de fichier LICENSE, son README annonce MIT : rien n'en est copié dans le dépôt.

## SÉANCE 8 : L'IA (faite le 9 novembre 2026, moteur et règles inchangés)

Guide : `docs/ai.fr.md`.

- [x] Notice, titres en clair et avis d'alerte, écrits depuis un formulaire à cases. Traduction vers le français dans un appel séparé.
- [x] Appel direct de l'API Messages avec httpx, service `redacteur` seul à recevoir la clé, aucune clé dans GitHub.
- [x] Contrôle de sortie, cache (points 4 et 5 des protections), fusibles du jour et du mois (points 6 et 7), notice de secours.
- [x] Plafond de la console : décision du 9 novembre, une heure de pause puis un seul essai (et non « aucun nouvel essai » comme écrit
      plus bas), sans e-mail pour l'instant.

À faire :

- [x] E-mail à l'admin : envoyé par le facteur (séance 9a), au plus un par code d'alerte et par 24 h, 20 par jour au plus.
- [x] La dépense et le solde dans un tableau admin (séance 9c-2, `docs/admin.fr.md`).
- [ ] La traduction vers l'anglais.
- [x] ALTCHA sur les formulaires du compte (séance 9a) ; sur l'analyse en séance 9b.
- [ ] Décision sur httpx2 : le SDK anthropic actuel en dépend, respx ne l'intercepte pas, et Starlette le demande pour son client de test.
- [ ] Les noms des dépendances directes dans le rapport : le champ `libraries` du formulaire reste vide tant que le moteur ne les garde pas.
- [x] Premier vrai essai (9 novembre) : notice française avec un encodage cassé venu de la réponse de l'IA. Règle de rejet `encoding`,
      prompt `notice-v2`, httpx déclaré comme dépendance directe de `api/`.
- [x] Diagnostic (9 novembre) : la sortie imposée (`output_config.format`) cassait les accents. Elle est retirée, le prompt décrit le
      JSON et notre contrôle le relit ; prompts `notice-v3` et `translation-v2`.
- [x] Matrice du 10 novembre : l'encodage cassé est un défaut intermittent. Nouvel essai sur rejet `encoding`, 4 appels par jour au plus
      pour une même notice, journal des appels `ai_calls`.
- [ ] Surveiller le taux de rejets encoding dans le tableau admin (cadran « Rejets de l'IA », séance 9c-2) ; s'il reste à 0, retirer le
      nouvel essai.
- [ ] Mise en ligne : vrai filtre de sortie réseau (pare-feu ou proxy) pour le chef d'atelier et le rédacteur.
- [x] Bouton admin pour relancer une notice rejetée ou en échec (séance 9c-2), sans jamais contourner le budget.

## SÉANCE 9A : LE GUICHET (faite le 10 novembre 2026, moteur et règles inchangés)

Guide : `docs/accounts.fr.md`.

- [x] Comptes gratuits avec Better Auth dans un service séparé, le guichet (`auth/`) : inscription avec e-mail vérifié,
      connexion, déconnexion, mot de passe oublié, suppression du compte avec le mot de passe. Pas de connexion Google ou GitHub.
- [x] Le facteur, seul à tenir les identifiants SMTP ; e-mails en texte brut ; Mailpit en développement (profil `dev`).
- [x] ALTCHA invisible (preuve de travail PBKDF2/SHA-256, coût 2000) sur l'inscription, la connexion et le mot de passe oublié.
- [x] Lecture de l'IP par une seule fonction de l'API ; le site ajoute l'adresse réelle à `X-Forwarded-For` (`web/client-ip.js`),
      car Next.js n'en ajoute aucune. Empreinte HMAC-SHA256 avec un sel du jour effacé après 2 jours.
- [x] Au plus 30 comptes créés par réseau et par jour UTC ; les refus comptés par jour, sans adresse.
- [x] Un rôle PostgreSQL pour le guichet, un pour le facteur, un pour l'API, le chef d'atelier et le rédacteur
      (`mcplain_app`) ; le propriétaire de la base ne sert plus qu'au service ponctuel `migrate` (décision de David du
      10 novembre : sans cela, l'API restait superutilisateur et lisait le schéma `auth`).
- [x] `current_user()` dans l'API, prêt pour la séance 9b.
- [x] uv 0.13.6 sur le poste et en CI (`required-version`) : `uv lock` écrit la même `revision` que Dependabot.

## SÉANCE 9B : QUOTAS ET COMPTEUR (faite le 12 novembre 2026, moteur et règles inchangés)

Guide : `docs/accounts.fr.md`, sections 14 à 18.

- [x] Quotas par jour UTC : 3 par empreinte d'IP sans compte, 10 par compte, admin sans limite. Jeton pris en une instruction SQL
      (testé avec 5 demandes simultanées sur PostgreSQL), rendu une seule fois par le chef d'atelier (cache, liste de plusieurs
      MCP, échec de MCPlain). Une seule table des codes (`api/src/mcplain_api/refunds.py`), un test pour les codes oubliés.
- [x] Quota épuisé : demande « cache seulement », état `quota_exhausted` sans téléchargement ni verdict (décision de David du
      12 novembre : l'API ne peut pas savoir avant OSV si le cache servira).
- [x] Anti-rafale : 30 demandes par heure glissante, par empreinte d'IP sans compte, par compte connecté ; admin et banc exemptés.
- [x] ALTCHA invisible sur chaque demande d'analyse, coût porté à 5000 (médiane 268 à 376 ms, maximum 469 à 959 ms, processeur
      ralenti 4 fois).
- [x] Compteur dans l'en-tête, phrase du réseau partagé, page de quota épuisé, historique sur « Mon compte », effacement de
      l'historique et des quotas avant la suppression d'un compte (`/internal/account-erase`).
- [x] Rôle `bench` (décision de David du 12 novembre) : sans quota ni anti-rafale, ALTCHA obligatoire, aucun pouvoir admin, actif
      seulement avec `MCPLAIN_ALLOW_BENCH_ROLE=true`. `scripts/make-bench-account.sh`. Le banc et `bench.yml` passent par le site.
- [x] Inscription : même réponse pour une adresse nouvelle ou déjà inscrite (corps fixe), sans e-mail pour l'adresse déjà
      inscrite.
- [x] Le guichet ne limite plus la lecture d'une session (`/get-session`) : l'API la demande pour chaque visiteur depuis une
      seule adresse, et la limite de 100 par minute faisait passer des comptes connectés pour des anonymes. Remplacé en 9c-1 :
      l'API passe par une route interne, et la route publique a de nouveau une limite (600 par minute).
- [x] Un compte banni (9c-1) compte comme un visiteur sans compte sur les routes publiques.
- [x] `uvx mcp-server-fetch` 2026.11.11 sortait orange sans O01 : angle mort du moteur, corrigé le 12 novembre (section suivante).

## BANC AUTOMATIQUE ET ENQUÊTE FETCH (faite le 12 novembre 2026, moteur 0.6.1, règles version 4)

- [x] Le banc tourne aussi à chaque push sur `main` et à chaque pull request qui touche une pièce dont il dépend, un seul à la
      fois par branche. Avant un tel push, le banc est lancé en local comme en CI (règle de `CLAUDE.md`).
- [x] fetch 2026.11.11 avait perdu O01 par un angle mort du moteur : client reçu en paramètre annoté (`httpx.AsyncClient`),
      requête construite par `build_request` puis envoyée par `send`. Les deux sont suivis ; fetch retrouve O01.
- [x] O01 se tait quand l'adresse de base du client est écrite dans le code ou lue dans l'environnement, et que l'URL commence
      par un chemin relatif écrit dans le code (ni vide, ni `//`, ni schéma, ni seulement des `/`). sentry-archived passe au vert.
- [x] Tests de la vraie pile : toujours une version épinglée d'un vrai serveur, jamais la dernière ; chaque test efface ses
      e-mails dans Mailpit et ses comptes.
- [ ] À clé égale, garder le chemin le plus parlant pour l'explication (souvent le plus court) : fetch 2026.11.11 cite le
      chemin de robots.txt, car deux chemins mènent à la même requête.
- [ ] filesystem 2.3.0 a gagné O04, à examiner plus tard.
- [ ] Un hôte fixé chez l'appelant et passé à une fonction qui fait la requête (`"https://api.example.com/" + ville`, puis
      `requests.get(url)` ailleurs) allume encore O01 : limite connue, déjà là avant 0.6.1.
- [ ] Un client reçu en paramètre : son adresse de base n'est lue que dans les appels du même fichier (sans appel dans le
      fichier, O01 reste allumé). Un appel depuis un autre fichier n'est pas vu ; une adresse de base venue de l'IA y allume
      quand même O01, là où le client est créé.

## SÉANCE 9C-1 : LA SERRURE (faite le 24 novembre 2026, moteur et règles inchangés)

Guide : `docs/accounts.fr.md`, sections 19 à 23. La séance 9c est découpée en trois : 9c-1 la serrure, 9c-2 le tableau de bord,
9c-3 la boîte à réclamations.

- [x] Double authentification TOTP (Google Authenticator, 6 chiffres, 30 secondes, SHA-1, émetteur « MCPlain ») par le plugin
      `twoFactor` de Better Auth 1.7.15, proposée au seul rôle admin. Clé à saisir (groupée par 4, sans QR code), premier code,
      10 codes de secours montrés une fois et imprimables en thème clair, régénération avec le mot de passe, désactivation.
- [x] Pouvoir admin = rôle admin ET double authentification, vérifié par l'API ; sans elle, quota de 10 et 403 sur `/api/admin/*`.
- [x] Jamais d'appareil de confiance (forcé côté guichet) ; verrouillage 15 minutes après 10 codes faux.
- [x] Une seule porte pour créer une session (`auth/src/session-gate.ts`), fermée en cas de doute : le lien de vérification
      d'e-mail ne donne jamais de session admin sans code.
- [x] `scripts/reset-admin-2fa.sh <email>` si tout est perdu ; aucune route web pour ça.
- [x] get-session : l'API passe par `/internal/session` du guichet (réseau `back`, appel de l'API seulement) ; la route publique
      reprend une limite, 600 par minute et par vraie adresse (décision de David du 24 novembre 2026 : 100 faisait apparaître une
      classe derrière un seul réseau comme déconnectée).
- [x] Bannissement maison (pas le plugin admin de Better Auth) : date et motif dans le schéma `auth` (migration `0009`), sessions
      effacées, nouvelle session refusée partout, message neutre « Ce compte est bloqué. », ni soi-même ni un admin. Historique et
      quotas gardés pendant le blocage.
- [x] Page `/admin` : section « Comptes » (recherche par e-mail exact, bloquer, débloquer) ; emplacement du tableau de bord.
- [x] Routes `/api/admin/*` : un seul filtre (admin avec double authentification), et `Origin` exigé pour les changements (CSRF).
- [x] Le compte `bench@bench.mcplain.invalid`, créé par erreur le 12 novembre sur la pile locale avec les valeurs de la CI, est
      supprimé par le chemin normal ; `make-bench-account.sh` refuse désormais ces valeurs hors de GitHub Actions.
- [ ] À surveiller : 600 lectures de session par minute et par adresse ; si un grand réseau partagé (école, entreprise) voit des
      comptes affichés comme déconnectés, relever ce chiffre (`SESSION_READS_MAX` dans `auth/src/auth.ts`).

## SÉANCE 9C-2 : LE TABLEAU DE BORD (faite le 24 novembre 2026, moteur, règles et banc inchangés)

Guide : `docs/admin.fr.md`.

- [x] Cadrans sur `/admin`, période 7 j ou 30 j (jours UTC), bouton « Actualiser », chiffres globaux seulement : dépense de l'IA
      (la même fonction que les fusibles, sortie du rédacteur dans `ai_budget.py` par un déplacement pur, décision de David),
      solde estimé, alertes de l'IA, rejets et taux `encoding`, notices à relancer, échecs d'analyse (jeton rendu ou gardé),
      analyses par jour, couleurs et cas gris, 20 MCP les plus analysés, langages non pris en charge, refus, comptes créés par jour.
- [x] Barres en CSS avec leur chiffre écrit, jetons existants, cuivre pour les alertes seulement, une colonne sur téléphone.
- [x] Solde estimé = dernier relevé + recharges − dépense depuis ce relevé ; table d'écritures, suppression de la dernière seulement.
- [x] E-mail sous 2 $ (`MCPLAIN_BALANCE_ALERT_USD`) envoyé une fois par le facteur, sans `mail_outbox` (décision de David : le rôle de
      l'API n'a aucun droit sur cette table), avec quatre droits de lecture en plus ; réarmé quand une écriture fait remonter le
      solde au-dessus du seuil ; jamais sans relevé. Remplace « au plus un par jour » prévu plus haut.
- [x] Relancer une notice rejetée ou en échec (fusibles, budget, pause et plafond de 4 toujours appliqués) ; relancer une analyse
      sans le cache (une réussite devient ce que le cache sert, un échec garde l'ancien résultat) ; marquer une alerte comme lue.
- [x] Journal admin (table `admin_actions`), bannissements de la 9c-1 compris ; les 50 dernières lignes sur `/admin`.
- [x] Comptes créés par jour : route interne du guichet `/internal/accounts/created-per-day` (dates et nombres seulement).
- [x] L'API reçoit les mêmes réglages de l'IA que le rédacteur (jamais la clé), pour lire le même budget et les mêmes prix.
- [x] Fait par David le 24 novembre 2026 : premier relevé saisi (4,34 $) ; `MCPLAIN_ADMIN_EMAIL` réglé pour recevoir l'e-mail du
      solde.

## SÉANCE 9C-3 : LA BOÎTE À RÉCLAMATIONS (faite le 24 novembre 2026, moteur, règles, banc et rédacteur inchangés)

Guides : `docs/admin.fr.md` (section 11) et `docs/analytics.fr.md`. **La séance 9c est terminée.**

- [x] Bouton « Signaler » sous chaque rapport terminé : alerte injustifiée, danger non détecté, « Tu es l'auteur ? Signale une
      erreur » (déclaratif, « non vérifié » sur `/admin`). Copie des versions du moteur et des règles et de la couleur du rapport.
- [x] Ouvert à tous avec ALTCHA ; compte banni refusé ; 10 par jour par compte ou par réseau, 1 par type et par analyse, 500 par jour
      pour tout le site (« La boîte est pleine, réessaie demain », alerte admin une fois par jour) ; admin sans limite ; refus
      comptés (`report_limit`, `report_global`) dans le cadran « Refus ».
- [x] Commentaire facultatif de 500 caractères, texte brut, jamais envoyé à l'IA ni écrit dans les journaux, effacé par le facteur
      90 jours après « Traité » ou « Rejeté » (deux droits de colonne, il ne lit jamais un commentaire).
- [x] Section « Signalements » et cadran par jour sur `/admin`, compteur des nouveaux en haut ; l'identifiant du compte signaleur est
      la troisième exception aux identifiants (règle 2 de la 9c-2), jamais l'empreinte d'IP.
- [x] Umami 3.4.1 auto-hébergé, épinglé par étiquette et empreinte, base et rôle à part créés par `migrate` (exception à Alembic :
      Umami crée ses tables), la base de MCPlain fermée aux autres rôles (migration `0012`), tableau sur `127.0.0.1` seulement.
- [x] Relais : seuls `GET /umami/script.js` et `POST /umami/api/send`, corps et en-têtes reconstruits, vraie adresse écrasée par le
      relais ; Do Not Track et Global Privacy Control respectés, chemins normalisés, `/admin` et `/account` jamais suivis, aucun
      cookie d'Umami. `SALT_ROTATION=day` (visiteurs uniques sur plusieurs jours surestimés).
- [x] Script `scripts/umami-first-setup.sh` ; page de confidentialité (fr, en) : Umami, cookies, empreintes d'IP, e-mails.
- [x] Fait par David en local le 24 novembre 2026 : `scripts/init-secrets.sh` (trois secrets d'Umami), pile relancée,
      `scripts/umami-first-setup.sh` et double authentification d'Umami. Sur le VPS : voir « Mise en ligne ».
- [x] Cookie `NEXT_LOCALE` de next-intl (il retient la langue quand elle n'est pas celle du navigateur) : **gardé** (décision de
      David du 24 novembre 2026), il est dit sur la page de confidentialité.

## PROCHAINE ÉTAPE

Une passe de finition visuelle du site, puis la mise en ligne chez OVH (points ci-dessous).

## MISE EN LIGNE (comptes)

- Choisir un fournisseur SMTP (jamais un serveur d'e-mails maison) ; régler `MCPLAIN_SMTP_*` avec STARTTLS.
- Un rôle PostgreSQL par service existant (API, chef d'atelier, rédacteur), au lieu du rôle commun `mcplain_app`.
- `MCPLAIN_PUBLIC_URL` en `https://` (cookies `Secure`) ; ne plus publier le port 8000 de l'API.
- `MCPLAIN_TRUSTED_PROXY_HOPS` réglé selon le relais réel du VPS : 2 avec un relais TLS devant le site (le relais, puis le site),
  plus un par relais en plus. Avec une valeur trop basse, tous les visiteurs auraient l'adresse du relais et partageraient un
  seul quota. À vérifier une fois en ligne : deux visiteurs sur deux réseaux différents doivent voir deux compteurs.
- Retirer `CREATEDB` au rôle `mcplain_app` en production (donné par la migration `0006`) : ce droit ne sert qu'aux tests de
  la pile.
- `MCPLAIN_ALLOW_BENCH_ROLE` faux sur le VPS (c'est la valeur par défaut) ; vérifier qu'aucun compte `bench` n'y existe
  (`SELECT email FROM auth."user" WHERE role = 'bench'`).
- Le port de l'API jamais exposé sur l'hôte : sinon les appels directs, sans adresse lue, partagent une seule empreinte d'IP et un
  seul quota.
- Surveiller la prochaine demande de Dependabot pour uv : elle doit rester compatible avec `required-version = ">=0.13.6"` de
  `engine/`, `api/` et `bench/` (sinon `uv lock` échoue en CI).
- Mentions de confidentialité : faites en 9c-3 (page `/privacy`) ; les relire une fois en ligne sur le domaine prévu, `mcplain.dev`.
- Tableau Umami par tunnel SSH seulement (`docs/analytics.fr.md`, section 8) : jamais de port public, jamais de relais TLS vers lui.
- Umami sur le VPS, avant l'ouverture : `scripts/init-secrets.sh` (dont les trois secrets d'Umami), pile démarrée, puis
  `scripts/umami-first-setup.sh mcplain.dev` (mot de passe), `docker compose up -d web`, puis la 2FA dans le tableau (par le
  tunnel SSH), avec ses codes de secours rangés.
- Relever `MCPLAIN_SIGNUPS_PER_IP_PER_DAY` si le tableau admin montre des refus fréquents.
- Avant d'ouvrir le site : active la double authentification de ton compte admin sur le VPS, **imprime les codes de secours**
  (bouton « Imprimer ») et range-les loin de ton téléphone. Sans eux, seul `scripts/reset-admin-2fa.sh` sur le VPS te rendra la
  main.
- Vérifier l'heure du VPS : synchronisation NTP active (`timedatectl` doit dire `System clock synchronized: yes`). Le code TOTP
  dépend de l'heure : un serveur décalé de plus de 30 secondes refuse les bons codes.
- `MCPLAIN_PUBLIC_URL` est aussi lu par l'API : c'est la seule origine acceptée pour les changements de la page `/admin`.

## PLUS TARD

- Les refus de l'anti-rafale (`burst_limit`) et les ALTCHA ratés (`altcha_invalid`) ne sont comptés nulle part : le cadran « Refus »
  de la 9c-2 ne les montre donc pas (décision de David du 24 novembre 2026). À ajouter si un jour on veut les suivre (une table par
  jour, sans adresse, comme `quota_refusals`).

- Surveiller les nouvelles versions des serveurs de référence (fetch, filesystem, time, git...) : être prévenu quand une version
  sort, pour vérifier son verdict et mettre à jour la version épinglée des tests de pile. Pas codé.
- Liste des bibliothèques dans le formulaire de l'IA.
- Retester la sortie imposée avec `scripts/notice-diagnose.sh --with-format` (abandonnée le 9 novembre 2026 : accents cassés en
  français).
- Lire les paquets tout-en-un fabriqués par un bundler (cas de sentry 0.49.0) pour y reconnaître les outils, afin qu'ils ne
  finissent plus en gris. Pas codé.
- sequential-thinking 2.2.0 gris (suivi incomplet) : dans l'outil `sequentialthinking`, l'appel
  `thinkingServer.processThought(args)` (`dist/index.js`, ligne 121) n'est pas suivi, car le moteur ne connaît pas le type de
  `thinkingServer` (raison `unknown_type`) ; il ne peut donc pas rejoindre la méthode qui fait le travail. La 2.1.1 était verte.
  Référence du banc passée de vert à gris le 24 novembre 2026, moteur inchangé.

## PROTECTIONS CONTRE LES ROBOTS ET QUOTAS (décidé le 23 octobre 2026)

But : une armée de robots ne doit ni vider le budget de l'IA, ni bloquer
les vrais visiteurs. Le pire cas est plafonné : au plafond, seule la
notice IA disparaît, le verdict marche toujours (il n'utilise pas
l'IA).

1. Anti-DDoS d'OVH : inclus dans chaque VPS, à vérifier à la mise en
   ligne. (Mise en ligne)
2. Preuve de travail ALTCHA : bibliothèque libre (MIT), auto-hébergée,
   sans cookie, sans service tiers. Invisible pour le visiteur : le
   calcul démarre seul au clic sur ANALYSER (auto="onsubmit",
   display="invisible"), difficulté réglée pour rester sous la seconde.
   L'API vérifie la preuve avant chaque analyse et à l'inscription.
   Pas de Cloudflare Turnstile : ce serait un tiers qui voit chaque
   visiteur, contraire à la promesse « aucune donnée chez un tiers ».
   (Séance 9)
3. Quotas : sans compte, 3 analyses par jour et par adresse IP ; avec
   compte, 10 par jour au compte, quel que soit le réseau ; l'admin n'a
   pas de quota ; une analyse servie par le cache ne compte pas, et
   c'est signalé. (Séance 9)
4. Cache : déjà en place pour les analyses ; la notice IA aussi, une
   par version de MCP et par langue. Même version = 0 jeton. (Séance 8)
5. Pas d'appel à l'IA si le moteur n'a reconnu aucun outil (gris
   « aucun outil reconnu », liste de liens, langage non pris en charge,
   échec). (Séance 8)
6. Fusible quotidien : MCPlain compte sa propre dépense IA. Au-delà d'un
   budget du jour (réglable, par exemple 1/20 du plafond mensuel), les
   nouvelles notices attendent le lendemain ; les notices déjà en cache
   restent affichées ; le verdict n'est jamais touché. (Séance 8)
7. Plafond mensuel de l'espace de travail MCPlain dans la console
   Anthropic, avec alerte à 80 %. Au plafond, l'API répond HTTP 400,
   type invalid_request_error, message commençant par « You have reached
   your specified workspace API usage limits ». À traiter comme
   « plafond atteint » : rapport sans notice, e-mail à l'admin, aucun
   nouvel essai automatique. (Séance 8)

## SÉANCE 9 : SIGNALEMENT PAR L'AUTEUR (décidé le 3 novembre 2026, codé en 9c-3)

- Sur chaque rapport, un bouton « Tu es l'auteur ? Signale une erreur ».
- C'est un type de signalement en plus. Le commentaire est du texte brut, affiché avec `RawText`, et il n'est
  jamais donné à l'IA (ni à la notice, ni à une traduction).

## ADRESSES IP PARTAGÉES (école, entreprise, open space, réseau mobile)

Problème : tout un réseau peut sortir sur Internet avec une seule
adresse IP ; 3 analyses par IP = 3 pour toute une école.

Solution décidée : le compte devient la solution (quota attaché à la
personne, jamais à l'IP).

- Phrase permanente près du compteur, choisie par David :
  FR « Réseau partagé (entreprise, open space, école…) ? Crée un compte
  gratuit : 10 analyses par jour rien que pour toi »
  EN à écrire dans le même esprit.
- L'explication vient au moment où elle sert : pas d'avertissement en
  gros sur l'accueil. Quand le quota de l'IP est atteint : message clair
  qui parle du réseau partagé, avec un bouton « Créer un compte ».
- Inscription rapide mais protégée : ALTCHA, e-mail vérifié, nombre de
  comptes créés par IP et par jour limité (assez haut pour une classe).
- Écarté : un compteur par navigateur (cookie ou localStorage). La CNIL
  dispense de consentement les traceurs qui limitent l'accès gratuit
  seulement pour les sites payants (délibération 2020-091, §49) ;
  MCPlain est gratuit : zone grise, avec risque de bandeau de
  consentement.

# Travaux prévus

Ce fichier garde les décisions prises pour les séances à venir. Lis la partie qui concerne ta séance avant de
commencer. Les séances 7, 7 bis, 7 ter, 7 quater et 7 quinquies et le corpus partie 2 sont faits, sauf DVMCP (voir sa partie) ; les parties « Protections » et « Adresses IP
partagées » (séances 8 et 9) ne sont pas codées.

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
- [ ] Les 5 pièges écrits en chat, déposés par David dans le dossier privé.
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
- [ ] DVMCP (commit `cdc4c6b`) : `scripts/fetch-dvmcp.sh` est sur main, la CI lit les cas positifs d'O12 et R13. Attendus et
      classement restent sur la branche locale `dvmcp`, non poussée : les défis 5 et 10 sont en ÉCHEC, orange au lieu de rouge.
      Leurs blocs n'ont aucun signal de R13. Décision de David attendue.
- [ ] Défis 11 à 15 de DVMCP (identité, chaîne d'approvisionnement) : pas examinés.
- [ ] DVMCP n'a pas de fichier LICENSE, son README annonce MIT : rien n'en est copié dans le dépôt.

## PLUS TARD

- Lire les paquets tout-en-un fabriqués par un bundler (cas de sentry 0.49.0) pour y reconnaître les outils, afin qu'ils ne
  finissent plus en gris. Pas codé.

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

## SÉANCE 9 : SIGNALEMENT PAR L'AUTEUR (décidé le 3 novembre 2026, pas codé)

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

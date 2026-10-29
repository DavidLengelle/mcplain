# Travaux prévus

Ce fichier garde les décisions prises pour les séances à venir. Lis la partie qui concerne ta séance avant de
commencer. La séance 7 est faite ; rien de ce qui suit la séance 7 n'est codé.

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
- [ ] Décisions de David en attente : les rouges de la première mesure (faux rouges ou vrais paquets
      malveillants), la proposition sur O06 (alertes dont toutes les versions sont retirées du registre), la
      proposition sur `require()` d'un fichier `.json`.

Causes de gris restantes (à traiter dans une prochaine séance de fiabilité) :

1. `not_a_server` (3 serveurs) : enveloppes dont le vrai code est dans une dépendance, et paquets empaquetés
   sans dépendance déclarée. Piste : analyser la dépendance qui porte le code, ou lire les imports du code
   empaqueté.
2. `no_tools_found` (3) : outils déclarés dans des paquets séparés (MongoDB), ou d'une façon encore inconnue
   (tmcp de Storybook, logfire-mcp).
3. `incomplete_tracking` (2) : objets reçus en paramètre (postgres-mcp), code exécuté dans le navigateur
   (server-puppeteer).
4. `network_unresolved` (1) : client réseau passé en paramètre à une autre fonction (mcp-server-sentry).
5. À refaire sur une machine normale : la mesure 0.3.0 a eu 7 délais dépassés de l'atelier (machine très lente).

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

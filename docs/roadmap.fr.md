# Travaux prévus

Ce fichier garde les décisions prises pour les séances à venir. Rien de ce qui suit n'est codé : lis la partie
qui concerne ta séance avant de commencer.

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

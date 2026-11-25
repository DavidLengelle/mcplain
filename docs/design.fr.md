# Le design de MCPlain : jetons, thèmes et voyants

Ce document décrit le style B du rapport, validé le 6 octobre 2026. La maquette de référence est
`docs/design/maquette-rapport-b.html` : c'est une spécification visuelle, pas du code à reprendre.

## Une seule source de couleurs

Toutes les couleurs du site sont des variables CSS définies **une seule fois**, dans
`web/src/app/globals.css` :

- le thème clair dans le bloc `:root` ;
- le thème sombre dans le bloc `@variant dark` juste dessous. La variante `dark` couvre deux cas : la classe
  `th-dark` posée sur `<html>`, et le réglage sombre du système quand la classe `th-light` n'est pas posée.

Le bloc `@theme inline` branche ces variables sur Tailwind : `--panel` devient `bg-panel`, `--ink` devient
`text-ink`, `--sel-ring` devient `shadow-sel-ring`. La palette par défaut de Tailwind est vidée
(`--color-*: initial`) : une couleur qui n'est pas un jeton n'existe pas.

Les valeurs viennent exactement de la maquette (blocs `.mcp.th-light` et `.mcp.th-dark`). Le tableau
ci-dessous est tiré du fichier CSS ; si tu changes une valeur, change-la dans `globals.css`, puis ici.

| Jeton | Clair | Sombre | Rôle |
| --- | --- | --- | --- |
| `--lamp-danger-bg` | `#FF5E57` | `#FF5E57` | ampoule en danger (rouge vif, mêmes valeurs dans les deux thèmes) |
| `--lamp-danger-stroke` | `#2A0606` | `#2A0606` | icône d'une ampoule en danger |
| `--chip-on-dot` | `#FFFFFF` | `#FFFFFF` | petit voyant allumé |
| `--chip-danger-dot` | `#FF5E57` | `#FF5E57` | petit voyant en danger |
| `--page` | `#F5F7FA` | `#0C131B` | fond de la page |
| `--panel` | `#E4EAF1` | `#141E29` | fond des blocs (verdict, cases, cartes) |
| `--panel2` | `#FFFFFF` | `#0F1822` | fond des panneaux dans un bloc (fiche, détails) |
| `--line` | `#C9D3DE` | `#1E2A36` | filet sous l'en-tête et au-dessus du pied de page |
| `--code-bg` | `#FFFFFF` | `#0C131B` | fond des extraits de code et des textes de tiers en bloc |
| `--input-bg` | `#FFFFFF` | `#141E29` | fond du champ de saisie |
| `--field-border` | `#677B90` | `#61768C` | bord des champs (input, textarea, select) ; 3:1 au moins contre le fond du champ et contre le panneau (séance 10b, remplace `--input-border` de la maquette) |
| `--btn-border` | `#7A8EA3` | `#3A4D61` | bord des boutons secondaires |
| `--row-hover` | `#DCE4EC` | `#18232F` | survol d'une ligne d'alerte (clair éclairci en séance 10b, voir « Contrastes ») |
| `--card-hover` | `#DCE4EC` | `#1A2633` | survol d'une carte d'outil (clair éclairci en séance 10b) |
| `--ink` | `#0C131B` | `#EDF2F7` | texte principal |
| `--ink2` | `#26384A` | `#C6D2DE` | texte secondaire (phrases) |
| `--ink3` | `#1C2B3A` | `#DCE4EC` | texte de l'auteur dans la fiche |
| `--muted` | `#46596D` | `#9DB0C3` | texte discret (dates, aides, libellés de carte) |
| `--faint` | `#526679` | `#7E92A6` | texte très discret (sur-titres) |
| `--accent` | `#0A62A6` | `#7CC7FF` | bleu d'action : liens, boutons, focus |
| `--on-accent` | `#FFFFFF` | `#061420` | texte posé sur le bleu |
| `--accent-hover` | `#074C82` | `#B3DEFF` | bleu au survol |
| `--logo-glow` | `0 0 0 4px rgba(10,98,166,.16)` | `0 0 12px rgba(124,199,255,.7)` | halo du point du logo |
| `--arrow-shadow` | `0 0 0 5px rgba(10,98,166,.16),0 6px 18px rgba(12,19,27,.25)` | `0 0 0 5px rgba(124,199,255,.18),0 6px 20px rgba(0,0,0,.5)` | ombre de la flèche de remontée |
| `--sel-ring` | `inset 0 0 0 3px #0A62A6` | `inset 0 0 0 2px #7CC7FF` | anneau de la carte sélectionnée |
| `--green` | `#10733D` | `#46D488` | zone verte de la jauge, mot RIEN TROUVÉ |
| `--warn` | `#E8892E` | `#C77B30` | zone orange de la jauge, mot À VÉRIFIER, points orange |
| `--warn-text` | `#3A1C05` | `#C77B30` | petits textes orange (badges, niveau d'un outil) |
| `--warn-badge-bg` | `#E8892E` | `transparent` | fond du badge À VÉRIFIER |
| `--warn-note` | `#FEF0E2` | `#2B1D13` | fond de la note « Pourquoi à vérifier » |
| `--warn-glow` | `rgba(232,137,46,.45)` | `rgba(199,123,48,.55)` | halo des points orange |
| `--warn-ring` | `inset 0 0 0 2.5px #E8892E` | `inset 0 0 0 1.5px rgba(199,123,48,.6)` | contour d'une carte à vérifier |
| `--red` | `#BF2D26` | `#FF5E57` | zone rouge de la jauge, mot DANGER, textes de danger |
| `--red-note` | `#FAE4E2` | `#2E1416` | fond de la note « Pourquoi danger » |
| `--red-glow` | `rgba(191,45,38,.32)` | `rgba(255,94,87,.6)` | halo des points rouges |
| `--red-ring` | `inset 0 0 0 2.5px #BF2D26` | `inset 0 0 0 2px rgba(255,94,87,.75)` | contour d'une carte en danger |
| `--gray` | `#526679` | `#9DB0C3` | mot NON VÉRIFIÉ |
| `--needle` | `#0C131B` | `#EDF2F7` | aiguille de la jauge |
| `--hub-hole` | `#E4EAF1` | `#141E29` | trou du moyeu de l'aiguille |
| `--cluster-bg` | `#C4DCF0` | `#070C12` | fond du bloc des voyants |
| `--cluster-ink` | `#0C131B` | `#EDF2F7` | nom d'un voyant allumé |
| `--cluster-ink2` | `#26384A` | `#C6D2DE` | nom d'un voyant éteint |
| `--cluster-muted` | `#33475B` | `#9DB0C3` | compteur et notes des voyants |
| `--lamp-on-bg` | `#FFFFFF` | `#EAF4FF` | ampoule allumée (blanche) |
| `--lamp-on-shadow` | `0 0 0 2px #6F9CC6,0 0 0 7px rgba(255,255,255,.8),0 0 26px 6px rgba(255,255,255,.95)` | `0 0 0 5px rgba(234,244,255,.12),0 0 22px rgba(170,215,255,.45)` | halo d'une ampoule allumée |
| `--lamp-on-stroke` | `#0C131B` | `#0C131B` | icône d'une ampoule allumée |
| `--lamp-on-text` | `#0A4F86` | `#B9DCFF` | état « Allumé » |
| `--lamp-off-bg` | `#A3C2E0` | `#17222E` | ampoule éteinte (sombre ou terne) |
| `--lamp-off-shadow` | `inset 0 2px 6px rgba(20,50,80,.35)` | `inset 0 2px 8px rgba(0,0,0,.7)` | creux d'une ampoule éteinte |
| `--lamp-off-stroke` | `#5F82A4` | `#4F6377` | icône d'une ampoule éteinte |
| `--lamp-off-text` | `#3E5266` | `#7E92A6` | état « Éteint » |
| `--lamp-danger-shadow` | `0 0 0 2px #BF2D26,0 0 0 7px rgba(255,94,87,.25),0 0 24px rgba(255,94,87,.6)` | `0 0 0 5px rgba(255,94,87,.16),0 0 24px rgba(255,94,87,.55)` | halo rouge d'une ampoule en danger |
| `--lamp-danger-text` | `#A8231C` | `#FF8A85` | état « Danger » |
| `--chip-house` | `#C4DCF0` | `transparent` | logement des petits voyants des cartes |
| `--chip-off-dot` | `#8FB0CF` | `#2E3E4F` | petit voyant éteint |
| `--chip-on-shadow` | `0 0 0 1.5px #6F9CC6,0 0 6px rgba(255,255,255,.9)` | `0 0 6px rgba(170,215,255,.6)` | halo d'un petit voyant allumé |
| `--chip-danger-shadow` | `0 0 0 1.5px #BF2D26` | `0 0 6px rgba(255,94,87,.6)` | halo d'un petit voyant en danger |
| `--chip-label` | `#26384A` | `#9DB0C3` | nom d'un petit voyant |
| `--chip-danger` | `#B3261E` | `#FF8A85` | nom d'un petit voyant en danger |
| `--toggle-bg` | `#E4EAF1` | `#141E29` | fond des sélecteurs thème et langue |
| `--toggle-fg` | `#3B4E62` | `#9DB0C3` | texte d'un choix non actif |
| `--toggle-on-bg` | `#0A62A6` | `#22303E` | fond du choix actif |
| `--toggle-on-fg` | `#FFFFFF` | `#FFFFFF` | texte du choix actif |
| `--counter-off` | `#AFBDCB` | `#22303E` | case vide du futur compteur d'analyses (séance 9) |
| `--demo-bg` | `#46596D` | `#9DB0C3` | fond de l'étiquette EXEMPLE FICTIF |
| `--demo-fg` | `#FFFFFF` | `#0C131B` | texte de l'étiquette EXEMPLE FICTIF |
| `--orig-bg` | `#0C131B` | `#EDF2F7` | fond de l'étiquette « Texte de l'auteur » |
| `--orig-fg` | `#FFFFFF` | `#0C131B` | texte de l'étiquette « Texte de l'auteur » |

Polices : Saira Condensed pour les titres, Saira pour le texte, IBM Plex Mono pour le code, les noms
techniques et les chemins (et rien d'autre). Elles sont servies par le site (`web/src/app/fonts/`, licence OFL).

## La page d'accueil : deux zones

La maquette de référence est `docs/design/maquette-accueil.html` (validée le 23 octobre 2026). Comme celle du
rapport, c'est une spécification visuelle, pas du code à reprendre. La page a deux zones qui se distinguent au
premier coup d'oeil : **l'outil** en haut (on agit), **le guide** dessous (on lit).

**La bande outil** (`id="analyser"`) occupe toute la largeur de l'écran : fond `--panel`, trait `--line` en
bas. Son contenu reste dans le conteneur habituel (1180 px, centré). À gauche : sur-titre en `--accent`, titre
h1 (Saira Condensed, de 42 à 70 px selon la largeur), phrase en `--ink2`, grand champ (60 px de haut, fond
`--panel2`, bord `--field-border`, rayon 12 px) et bouton ANALYSER (`--accent`, 22 px), puis « Essaie avec : » et
les trois exemples (bord `--btn-border`, rayon 10 px, police de code), puis trois petits points `--accent`.
À droite (dessous sur téléphone) : le bloc des voyants, `--cluster-bg`, rayon 22 px, les six ampoules
**éteintes** sur trois colonnes, « Aucun MCP analysé » et une phrase. Aucune jauge : sans analyse, pas de verdict.
L'état « Éteint » n'est pas répété sous chaque ampoule : « Aucun MCP analysé » le dit une fois pour toutes, et
chaque ampoule garde son état écrit pour les lecteurs d'écran.

**L'ouverture du guide** est sur le fond `--page` : deux traits `--btn-border` de part et d'autre de
« LE GUIDE » et de l'icône de livre (`--accent`), puis, centrés, le titre h2 (44 px), la phrase et le sommaire.
Chaque entrée du sommaire est une pastille `--panel` (rayon 999 px, 44 px de haut) avec son numéro 01 à 09 en
`--accent`, `--row-hover` au survol.

**Les chapitres** s'empilent avec 72 px d'écart. Chacun commence par un sur-titre « 01 · LE PRINCIPE »
(`--accent`, 15 px, espacé) et un titre h2 (44 px, 38 px sur téléphone). Les cartes sont en `--panel`, rayon 18 px ;
les grands blocs (histoire vraie, fin du guide) en `--panel`, rayon 26 px. Ce qui signale un danger dans le
guide (consigne cachée, « 1 + 2 + 3 », version 1.0.16) utilise `--red-note` et `--red-ring`. L'étiquette
EXEMPLE INVENTÉ ou EXEMPLE utilise `--demo-bg` et `--demo-fg`. La première carte des réflexes porte l'anneau
`--sel-ring`. Les liens des sources sont soulignés, en `--accent`.

**Jetons ajoutés pour l'accueil : aucun.** Toutes les couleurs de la maquette existaient déjà dans
`web/src/app/globals.css`.

## Qui décide d'une couleur ?

Jamais le site. Le moteur Python décide de la couleur du verdict (`engine/src/mcplain/verdict.py`), de l'état
de chaque voyant et du niveau de chaque outil (`engine/src/mcplain/lamps.py`). Le site traduit seulement ces
décisions en jetons : `red` devient `text-red`, un voyant `danger` devient `bg-lamp-danger-bg`.

Sur l'accueil aussi : l'exemple rouge du chapitre 07 est un vrai rapport du moteur
(`web/src/content/example-report.json`), et sa couleur vient de ce fichier. Les légendes du chapitre 06 (les
quatre verdicts, les trois états d'un voyant) montrent chaque couleur avec son nom ; elles ne jugent aucun code.

## Les voyants

Six voyants, pour le serveur et pour chaque outil : lit tes fichiers, modifie tes fichiers, va sur Internet,
lance des commandes, touche à tes secrets, texte caché.

| Aspect | État | Sens |
| --- | --- | --- |
| Ampoule blanche avec un halo | `on`, « Allumé » | Information : le code peut le faire. Ce n'est pas un reproche. |
| Ampoule rouge avec un halo rouge | `danger`, « Danger » | Une règle rouge concerne ce voyant. |
| Ampoule sombre (thème sombre) ou terne (thème clair), sans halo | `off`, « Éteint » | Rien de tel n'a été trouvé dans le code lu. |

Les règles orange n'allument jamais de rouge. La table complète (capacités, règles) est dans
`docs/rules.fr.md`, section « Les voyants ».

## La notice de l'IA

Le bloc de la notice est en `--panel`. L'avis d'alerte (« Avis de l'IA », icône d'information) est en `--panel2`, avec `--ink` et
`--ink2`. Il n'utilise jamais une couleur de verdict (ni vert, ni cuivre, ni rouge), et il n'apparaît ni dans la jauge ni dans les
voyants : c'est un avis, pas une décision du moteur. **Jetons ajoutés : aucun.**

## Contrastes

Tous les textes respectent 4,5:1 sur leur fond, et 3:1 pour les gros titres. Un test Vitest
(`web/tests/unit/theme-tokens.test.ts`) lit les jetons des deux thèmes et vérifie les paires principales.

**Les bords des champs** (`--field-border`) font au moins 3:1 contre le fond du champ (`--input-bg`, `--panel2`) et contre le
panneau et la page, dans les deux thèmes (WCAG 1.4.11). Les autres bordures (boutons secondaires, filets) ne changent pas.

**Les fonds de survol** (`--row-hover`, `--card-hover`) gardent `--faint`, `--red`, `--gray`, `--green` et `--accent` à 4,5:1
au moins. En clair, ils sont à 1,06:1 contre le panneau, comme le survol des lignes en sombre ; la carte d'outil monte aussi de
2 px au survol. Le test des jetons vérifie ces paires et l'écart avec le panneau.

**Exception validée par David le 6 octobre 2026.** En thème clair, le grand mot « À VÉRIFIER » est en orange
clair `#E8892E` sur `--panel` : 2,2:1, sous le minimum de 3:1. C'est accepté parce que la jauge (zone du
milieu pleine, aiguille au centre) et le titre en `--ink` portent le même sens. Les petits textes orange
utilisent `--warn-text` (brun foncé en clair, 12,9:1).

## Les boutons principaux

Un seul modèle, celui du bouton ANALYSER de la maquette : fond `--accent`, texte `--on-accent`, Saira Condensed 700 en 19 px,
espacement `.06em`, en capitales, 48 px de haut, coins de 10 px (`BUTTON_CLASS` dans `web/src/components/account/form-parts.tsx`).
Les capitales viennent du CSS (`uppercase`) : le texte des fichiers de messages ne change pas, et le nom lu par les lecteurs
d'écran reste celui du texte. Les boutons secondaires gardent leur bord `--btn-border` et leur casse normale.

## Le mode téléphone

Le « mode téléphone » vaut pour une largeur sous 768 px **ou** une hauteur sous 500 px (donc aussi un téléphone tenu à
l'horizontale). La requête est écrite une fois dans `globals.css` (variantes `phone:` et `desk:`) et une fois dans
`web/src/lib/phone-mode.ts` ; un test vérifie qu'elles sont identiques. Dans ce mode, l'en-tête collé est une barre de 64 px :
logo, analyses restantes (« 2/3 », la phrase entière pour les lecteurs d'écran), bouton NOUVELLE ANALYSE et bouton Menu. Le menu
contient la ligne complète du compteur, le thème, la langue et le compte. Le champ de saisie reste en haut de la page, mais défile
avec elle. Partout, `scroll-padding-top` vaut la hauteur réelle de la partie collée de l'en-tête (WCAG 2.4.11).

## Écarts assumés avec la maquette

Ces différences avec `docs/design/maquette-rapport-b.html` sont voulues. Ne les « corrige » pas sans l'accord de David.

| Écart | Maquette | Site | Pourquoi |
| --- | --- | --- | --- |
| Petits libellés des cartes (« OUTIL 01 ») | `--faint` | `--muted` | 4,5:1 sur `--panel` et au survol, dans les deux thèmes (séance 5) |
| Boutons de thème et de langue | 40 px de haut | 44 px | cible tactile de 44 px (séance 5) ; EN et FR font 41 à 43 px de large, au-dessus de 24 px |
| Titre du verdict orange | phrase d'exemple de la maquette | phrase de la règle du moteur (« Peut aller sur n'importe quel site ») | le site ne décide d'aucun texte de verdict (séance 5) |
| Thème au chargement | aucun éclair | un bref éclair du thème du système reste possible sur une machine lente | le script de thème tourne avant l'hydratation, pas avant le tout premier affichage (`docs/web.fr.md`, section 8) (séance 5) |
| Grand mot « À VÉRIFIER » en clair | `#E8892E` sur `--panel` | inchangé : 2,2:1 | validé le 6 octobre 2026, voir « Contrastes » |
| En-tête sur téléphone | en-tête complet, collé | barre compacte de 64 px, menu, champ non collé (section « Le mode téléphone ») | l'en-tête complet prenait 38 % de l'écran (49 % à l'horizontale) et cachait le focus (séance 10b, décision de David du 25 novembre 2026) ; l'ordinateur ne change pas |

## Interdits

- **La couleur seule.** Un verdict a toujours son mot (RIEN TROUVÉ, À VÉRIFIER, DANGER, NON VÉRIFIÉ) et sa
  jauge, avec un `aria-label`. Un voyant a toujours son état écrit. Un badge a toujours son texte.
- **L'orange vif sur fond sombre.** En thème sombre, l'orange reste le cuivre `#C77B30` (`--warn` et
  `--warn-text`). Le test des jetons le vérifie.
- **Une couleur écrite en dur dans un composant**, ou une couleur décidée par le site.
- **Un style en ligne** (`style=...`) : la CSP de production le bloque. Utilise les classes Tailwind.

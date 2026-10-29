# Le site de MCPlain, expliqué pas à pas

Ce guide présente le dossier `web/` à quelqu'un qui débute en Next.js et en React.
Les phrases sont courtes. Les noms de fichiers sont cliquables dans VS Code.

Le site ne fait qu'une chose : il montre ce que l'API répond. Il ne lit jamais le code
analysé et il ne décide jamais d'une couleur. Le verdict vient toujours du moteur Python.

## 1. La carte des dossiers

Pense au site comme à un restaurant. `src/app/` est la salle (les pages que l'on voit),
`src/components/` la vaisselle (les morceaux réutilisés), `src/lib/` la cuisine (le code sans
affichage), `messages/` le menu dans deux langues.

| Fichier ou dossier | Ce qu'il fait |
| --- | --- |
| `package.json` | Les dépendances, en versions exactes, et les scripts (`pnpm dev`, `pnpm test`...). |
| `pnpm-lock.yaml` | Le fichier de verrouillage : la version exacte de chaque paquet installé. Il est commité. |
| `pnpm-workspace.yaml` | Les réglages de pnpm 11 : délai de 7 jours, exceptions, scripts d'installation refusés. |
| `next.config.ts` | Réglages de Next.js : sortie `standalone`, pas d'en-tête `X-Powered-By`, renvoi de `/api/*` vers l'API, en-têtes de sécurité. |
| `messages/en.json`, `messages/fr.json` | Tous les textes de l'interface, dans les deux langues. |
| `src/proxy.ts` | S'exécute avant chaque page : choisit la langue (next-intl) et pose la CSP avec un nonce. |
| `src/i18n/routing.ts` | Les langues : `en` (par défaut, sans préfixe) et `fr` (préfixe `/fr`). |
| `src/i18n/request.ts` | Charge, pour chaque requête, les textes de l'interface et ceux du moteur. |
| `src/i18n/navigation.ts` | `Link`, `useRouter`... qui gardent la langue. Utilise-les à la place de ceux de Next.js. |
| `src/app/[locale]/layout.tsx` | Le cadre commun : `<html lang>`, script du thème, en-tête fixe, pied de page, avis si l'API ne répond pas. Son `<main>` prend toute la largeur : chaque page pose son conteneur. |
| `src/app/[locale]/page.tsx` | La page d'accueil : la zone outil, puis le guide (voir la partie 11). |
| `src/app/[locale]/analyses/[id]/page.tsx` | La page d'une analyse. Vérifie que l'identifiant est un UUID. |
| `src/app/[locale]/not-found.tsx` | La page 404, traduite. |
| `src/app/fonts/`, `src/app/fonts.ts` | Les polices Saira, Saira Condensed et IBM Plex Mono, et leurs licences OFL. Servies par le site lui-même. |
| `src/app/globals.css` | **La seule source des couleurs** : les jetons des thèmes clair et sombre (voir `docs/design.fr.md`). |
| `public/theme.js` | Le petit script qui pose le thème choisi avant l'affichage. |
| `src/components/site-header.tsx` | L'en-tête fixe : logo, champ d'analyse (sauf sur l'accueil), thème, langue. |
| `src/components/header-field.tsx` | Le champ de l'en-tête. Il ne s'affiche pas sur l'accueil, qui a déjà son grand champ. |
| `src/components/page-container.tsx` | `PageContainer` : le conteneur centré (1180 px) des pages autres que l'accueil. |
| `src/components/theme-switcher.tsx` | Les boutons Système, Clair, Sombre. |
| `src/components/analysis-field.tsx` | Le champ d'analyse, en deux tailles : `header` (en-tête) et `hero` (grand champ de l'accueil, avec ses 3 exemples). |
| `src/components/submit-label.tsx` | Le texte du bouton d'envoi : ANALYSER et ENVOI… sont superposés, le bouton garde la largeur du plus long. |
| `src/components/home/` | La page d'accueil, un composant par chapitre (voir la partie 11). |
| `src/content/example-report.json` | Le rapport d'exemple du chapitre 07, **généré par le moteur** (voir la partie 11). |
| `src/components/analysis-tracker.tsx` | Le suivi : interroge l'API chaque seconde, puis affiche le rapport. |
| `src/components/report/` | Les blocs du rapport, un composant par bloc (voir la partie 9). |
| `src/components/raw-text.tsx` | **RawText**, le seul moyen d'afficher un texte venu d'un tiers. |
| `src/components/engine-text.tsx` | Affiche un texte du moteur ; ses paramètres passent par RawText. |
| `src/components/param-text.tsx` | Affiche un texte de l'interface dont un paramètre vient d'un tiers (par RawText). |
| `src/components/icons.tsx` | Les icônes en SVG, dont celles des six voyants. |
| `src/lib/analysis.ts` | Les types des réponses de l'API, et leur vérification. |
| `src/lib/api-client.ts` | Les deux appels à l'API : lancer une analyse, lire son état. |
| `src/lib/example-report.ts` | Lit le rapport d'exemple avec le même contrôle que les réponses de l'API. |
| `src/lib/icu.ts` | Traduit les textes du moteur (format Python) en format ICU pour next-intl. |
| `src/lib/engine-messages.ts` | Télécharge les textes du moteur et les garde 1 heure en mémoire. |
| `src/lib/invisible-characters.json` | La liste des caractères invisibles, **générée par le moteur**. Ne pas l'éditer à la main. |
| `src/lib/security-headers.ts` | La CSP et les autres en-têtes de sécurité. |
| `src/lib/report.ts` | Les petits calculs d'affichage du rapport (voyants allumés, outil ouvert par défaut, emplacements). |
| `src/lib/theme.ts` | Le choix du thème : lecture, écriture dans `localStorage`, classe sur `<html>`. |
| `tests/unit/` | Tests Vitest et Testing Library (sans navigateur). |
| `tests/e2e/` | Tests Playwright dans un vrai Chromium, avec une API simulée. |
| `tests/fixtures/` | Les rapports de référence, **générés par le vrai moteur** (voir leur `README.md`). |
| `tests/e2e/stack/` | Le test sur la vraie pile (compose lancé), hors des tests par défaut. |

## 2. Le trajet d'une analyse, fichier par fichier

Exemple : tu tapes `uvx mcp-server-fetch` et tu cliques sur « Analyser ».

1. `src/components/analysis-field.tsx` (avec `use-analysis-start.ts`) retire les espaces au début et à la fin,
   puis appelle `startAnalysis` dans `src/lib/api-client.ts`.
2. `startAnalysis` envoie `POST /api/analyses` avec `{"input": "uvx mcp-server-fetch"}`.
   Le navigateur parle au site, jamais directement à l'API.
3. `next.config.ts` renvoie toute adresse `/api/...` vers l'API (`MCPLAIN_API_URL`,
   par défaut `http://127.0.0.1:8000`). C'est un `rewrite` : le navigateur ne voit qu'une adresse.
4. L'API répond `202` avec un identifiant. Le formulaire va sur `/analyses/<id>`
   (ou `/fr/analyses/<id>` en français : `useRouter` de `src/i18n/navigation.ts` garde la langue).
   Si l'API répond `400`, le message du moteur s'affiche sous le champ ; `503` veut dire file pleine.
5. `src/app/[locale]/analyses/[id]/page.tsx` vérifie que l'identifiant a la forme d'un UUID.
   Sinon : page 404, sans aucun appel à l'API.
6. `src/components/analysis-tracker.tsx` appelle `GET /api/analyses/<id>` chaque seconde tant que
   l'état est `queued`, `fetching` ou `analyzing`, et affiche les trois étapes.
   Au bout de 3 minutes : état gris « trop long ». Si l'API ne répond pas trois fois de suite,
   ou répond quelque chose d'anormal : état gris « non vérifié ».
7. Chaque réponse passe par `parseAnalysisView` dans `src/lib/analysis.ts`. Une réponse qui n'a
   pas la forme attendue donne `null`, donc du gris. Jamais du vert par défaut.
8. Quand l'état est `done` ou `failed`, `src/components/report/report-view.tsx` affiche le rapport,
   bloc par bloc (voir la partie 9).

## 3. Composant serveur ou composant client ?

Par défaut, dans le dossier `app/`, un composant est un **composant serveur** : il est calculé
sur le serveur, et le navigateur ne reçoit que le HTML. Il ne peut pas réagir à un clic.

Un fichier qui commence par la ligne `"use client";` est un **composant client** : son code part
aussi dans le navigateur, et il peut utiliser `useState`, `useEffect` ou `onClick`.
Tout composant importé par un composant client devient client lui aussi.

Comment savoir ? Regarde la première ligne du fichier.

| Fichier | Type | Pourquoi |
| --- | --- | --- |
| `src/app/[locale]/layout.tsx` | serveur | Il charge les messages pour la requête. |
| `src/app/[locale]/page.tsx` | serveur | Il ne fait qu'assembler la zone outil et les chapitres. |
| `src/components/home/chapter-*.tsx` | serveur | Ils affichent du texte, sans clic ni état. |
| `src/components/home/analyze-link.tsx` | client | Au clic, il met le curseur dans le grand champ. |
| `src/components/analysis-field.tsx` | client | Il réagit à la frappe et au clic. |
| `src/components/analysis-tracker.tsx` | client | Il interroge l'API chaque seconde. |
| `src/components/locale-switcher.tsx` | client | Il a besoin de l'adresse de la page en cours. |
| `src/components/raw-text.tsx` | client | Le bouton « Afficher tout » change son état. |

Règle du projet : jamais de `"use server"` dans `web/` (pas de Server Actions). Un test le vérifie.

## 4. Ajouter un texte dans les deux langues

Aucun texte n'est écrit en dur dans un composant. Exemple : ajouter « Partager » dans l'en-tête.

1. Dans `messages/en.json`, sous `header`, ajoute `"share": "Share"`.
2. Dans `messages/fr.json`, au même endroit, ajoute `"share": "Partager"`.
3. Dans le composant : `const t = useTranslations("header");` puis `{t("share")}`.
4. Lance `pnpm test` : un test vérifie que les deux fichiers ont exactement les mêmes clés.

Un paramètre s'écrit entre accolades : `"places": "{count} endroits"`, puis
`t("places", { count: 3 })`. Attention à l'apostrophe juste avant une accolade (`l'{name}`) :
en ICU, elle protège l'accolade. Le test des messages le détecte.

Les **textes du moteur** (règles, capacités, erreurs) ne se recopient jamais dans `web/`.
Ils viennent de `GET /api/messages/{lang}` et arrivent sous l'espace de noms `engine`.
Pour en afficher un : `<EngineText code="rule.R01.title" />`. Si l'API ne répond pas, EngineText
affiche « Texte indisponible » et le site reste utilisable.

## 5. Lancer le site et les tests

Prérequis : Node 24 et pnpm 11 (jamais npm, jamais pnpm 12).

```bash
cd web
pnpm install --frozen-lockfile
pnpm dev
```

Ouvre ensuite http://localhost:3000 (en développement, Next.js n'accepte que cette adresse).
Le site attend l'API sur `http://127.0.0.1:8000` : lance la pile avec `docker compose up -d`.

Pourquoi `localhost` et pas `127.0.0.1` ? Avec `--hostname 127.0.0.1`, Next.js 16.3.8 prend la
réécriture interne de next-intl (`/` vers `/en`) pour une adresse externe, et la page boucle sur
une redirection. `localhost` n'ouvre que la boucle locale : le site reste invisible depuis le réseau.
Sur certaines machines (celles de GitHub Actions par exemple), `localhost` désigne aussi `::1`, et Node
écoute alors en IPv6. Les tests Playwright lancent donc le site avec
`NODE_OPTIONS=--dns-result-order=ipv4first` : il écoute sur 127.0.0.1, là où Playwright l'attend.

| Commande | Ce qu'elle fait |
| --- | --- |
| `pnpm lint` | ESLint, avec `react/no-danger` en erreur. |
| `pnpm typecheck` | Génère les types des routes, puis TypeScript strict. |
| `pnpm test` | Vitest et Testing Library, sans navigateur. |
| `pnpm build` | Construit la version de production (`.next/standalone`). |
| `pnpm start` | Lance la version construite sur localhost:3000. |
| `pnpm test:e2e` | Construit, puis lance Playwright (Chromium) avec une API simulée. |
| `pnpm test:stack` | Playwright sur la vraie pile : compose et le site doivent tourner. |

Playwright a besoin d'un Chromium : `pnpm exec playwright install --only-shell chromium`.
Sur Ubuntu, Chromium demande aussi deux bibliothèques système : `sudo apt install libnss3 libnspr4`.

Avec Docker, le site tourne dans la pile : `docker compose up -d --build`, puis http://127.0.0.1:3000.
Si un autre projet occupe déjà le port 3000, choisis-en un autre dans `.env` : `MCPLAIN_WEB_PORT=3010`, puis http://127.0.0.1:3010. Les tests docker et `pnpm test:stack` lisent ce réglage.

## 6. Afficher un texte venu d'un tiers

Un texte tiers, c'est tout ce qui vient du code analysé ou des registres : nom d'outil,
description, extrait de code, URL, nom de paquet, nom de fichier, version. Ces textes peuvent
contenir des pièges : balises HTML, caractères invisibles, caractères qui retournent le texte.

Règles :

1. **Toujours** `<RawText value={...} />`. Jamais un texte tiers posé directement dans le JSX.
2. Jamais `dangerouslySetInnerHTML`, jamais `innerHTML`. ESLint et un test les refusent.
3. Jamais de lien cliquable vers une adresse tierce. Les URL citées sont du texte simple.
4. Un paramètre d'un texte du moteur est un texte tiers : `EngineText` le passe par RawText.

Ce que fait RawText :

- il affiche le texte avec React, donc `<script>` reste du texte ;
- il garde les retours à la ligne (`white-space: pre-wrap`) ;
- il isole le texte dans `<bdi>` avec `unicode-bidi: isolate` : un texte arabe ou hébreu ne
  déborde pas sur la phrase autour ;
- il remplace chaque caractère invisible, contrôle bidi ou caractère du bloc Unicode Tags par un
  badge visible, par exemple ⟨U+202E⟩, avec l'infobulle « caractère invisible ». Le caractère
  lui-même n'est jamais posé dans la page, donc il ne peut pas retourner le texte ;
- il coupe les textes longs et propose « Afficher tout ».

La liste des caractères invisibles vient du moteur (`INVISIBLE_RANGES`). Après l'avoir changée
dans le moteur, régénère le fichier du site depuis `engine/` :

```bash
uv run python -m mcplain.invisible_ranges > ../web/src/lib/invisible-characters.json
```

Un test du moteur et un test du site vérifient que les deux listes sont identiques.

Dans les tests, un texte piégé s'écrit toujours en échappement (`"\u202E"`), jamais en
caractère brut dans un fichier.

## 7. Dépendances et sécurité

- pnpm 11 seulement. Ne lance jamais `pnpm self-update`.
- Délai de 7 jours (`minimumReleaseAge: 10080` dans `pnpm-workspace.yaml`). Une exception ne se
  fait qu'en version exacte (`next@16.3.8`), avec un commentaire qui dit pourquoi, et se retire
  quand la version a plus de 7 jours.
- Aucun script d'installation ne tourne (`allowBuilds`). Chaque paquet refusé est expliqué.
- La CSP utilise un nonce tiré au hasard à chaque requête : seuls les scripts de Next.js portent
  ce nonce, donc un script injecté ne s'exécuterait pas. C'est pour cela que toutes les pages sont
  rendues à la demande (`await connection()` dans le layout).
- Pas d'attribut `style={...}` dans les composants : la CSP de production bloque les styles en
  ligne. Utilise les classes Tailwind.

## 8. Le thème clair et sombre, pas à pas

Le site a deux thèmes. Sans choix de ta part, il suit le réglage de ton système. Les boutons Système, Clair
et Sombre de l'en-tête changent ce choix.

1. **Les couleurs sont des variables CSS.** Dans `src/app/globals.css`, le bloc `:root` définit le thème
   clair (`--page: #F5F7FA;`) et le bloc `@variant dark` le thème sombre (`--page: #0C131B;`). Les composants
   n'écrivent jamais une couleur : ils écrivent `bg-page`, `text-ink`. Tailwind remplace par `var(--page)`.
2. **La variante `dark` couvre deux cas.** Elle s'applique si `<html>` porte la classe `th-dark`, ou si le
   système est en sombre et que `<html>` ne porte pas `th-light`. Sans JavaScript, il n'y a pas de classe :
   c'est le système qui décide (`@media (prefers-color-scheme: dark)`).
3. **Le choix est gardé dans `localStorage`** (clé `mcplain-theme`, valeur `light` ou `dark`). Système
   efface la clé. Aucun cookie.
4. **Un script pose la classe avant l'hydratation.** `public/theme.js` lit la clé et ajoute `th-light` ou
   `th-dark` sur `<html>`. La classe règle aussi `color-scheme`, donc les barres de défilement et les champs
   suivent. Le layout le charge avec `<Script src="/theme.js" strategy="beforeInteractive" nonce={nonce} />`.
5. **Le nonce.** La CSP n'accepte que les scripts qui portent le nonce de la requête. `src/proxy.ts` tire un
   nonce au hasard, l'écrit dans la CSP et dans l'en-tête de requête `x-nonce` ; le layout lit `x-nonce` avec
   `headers()` et le donne au `<Script>`. C'est la méthode de la documentation de Next.js 16.3.8
   (`node_modules/next/dist/docs/01-app/02-guides/content-security-policy.md`). Interdits :
   `dangerouslySetInnerHTML`, un script en ligne sans nonce, assouplir la CSP.
6. **Le bouton.** `src/components/theme-switcher.tsx` lit le choix avec `useSyncExternalStore` (le serveur
   ne connaît pas `localStorage`, il affiche « Système » ; le navigateur corrige juste après), écrit la clé,
   change la classe et met `aria-pressed` sur le bouton actif.

Bon à savoir : dans l'App Router, Next.js ne pose pas un `<script>` bloquant pour `beforeInteractive`. Il
écrit une petite ligne qui ajoute `/theme.js` à une liste, et son amorce le charge avant l'hydratation
(`node_modules/next/dist/client/script.js`, `app-bootstrap.js`). Le script tourne donc très tôt, mais pas
forcément avant le tout premier affichage : sur une machine lente, un éclair du thème du système reste
possible quand ton choix est différent du système.

## 9. La page de rapport, bloc par bloc

`src/components/report/report-view.tsx` assemble la page. Chaque bloc est un composant qui reçoit seulement
ce dont il a besoin. Le moteur a déjà tout décidé (couleur, voyants, niveau des outils) : les blocs
affichent.

| Ordre | Composant | Ce qu'il reçoit | Ce qu'il affiche |
| --- | --- | --- | --- |
| 1 | `identity-line.tsx` | la vue et la source | paquet, version, origine, date `analyzed_at` |
| 2 | `verdict-block.tsx` (+ `gauge.tsx`) | la vue et le résultat | la jauge, le mot, le titre et la phrase du moteur, « Relancer » si besoin |
| 3 | `ai-notice-slot.tsx` | rien | rien pour l'instant (notice de l'IA, séance 8) |
| 4 | `plain-summary.tsx` | le résultat et le serveur | EN CLAIR : ce qu'il peut faire, ce qu'on a trouvé, ce que tu peux faire |
| 5 | `lamp-cluster.tsx` | le serveur | les six voyants, leur état écrit, le compteur |
| 6 | `alert-points.tsx` | le résultat, les outils, deux fonctions de clic | DANGER (n) puis À VÉRIFIER (n), une ligne par alerte |
| 7 | `tool-grid.tsx` | les outils, l'outil choisi, une fonction de clic | une carte par outil, avec son contour |
| 8 | `tool-sheet.tsx` | l'outil choisi et ses alertes | la fiche : pourquoi, passage du code, texte de l'auteur, ce que son code peut faire |
| 9 | `tech-details.tsx` | la vue, le résultat, le serveur, ouvert ou non | les détails techniques, repliés |
| 10 | `report-end.tsx`, `back-to-top.tsx` | la vue | la date du code lu, la mention du cache, la flèche de remontée |

Deux états vivent dans `report-view.tsx` : l'outil choisi et l'ouverture des détails. Un clic sur une ligne
d'alerte ou sur une carte change l'outil choisi ; le lien `#fiche` fait défiler la page jusqu'à la fiche.
Le défilement est fluide (`scroll-behavior: smooth`), instantané si tu as demandé moins d'animations. La
fiche s'arrête sous l'en-tête fixe grâce à `scroll-margin-top`, calculé avec la hauteur réelle de
l'en-tête (`header-height.tsx` la mesure et la range dans `--header-height`).

Cas particuliers : plusieurs serveurs dans le lien donnent `candidates-list.tsx` (pas de verdict) ; une liste
de liens donne `link-list-notice.tsx`.

`Gauge` (`size` : `full`, `compact`, `small`), `VerdictFrame` (`size` : `full`, `compact`) et `LampPanel` (`size` :
`full`, `compact`, `hero`) ont plusieurs tailles. Le rapport utilise `full` ; l'accueil réutilise les mêmes
composants dans leurs autres tailles. `LampCluster` est le `LampPanel` du rapport.

## 10. Un texte d'interface avec un paramètre venu d'un tiers

Exemple : « Rien de dangereux. Il va seulement sur : {domains} ». Les domaines viennent du code analysé, donc
d'un tiers : ils doivent passer par RawText.

1. Dans `messages/fr.json`, sous `plain` : `"foundNothingDomains": "Rien de dangereux. Il va seulement sur : {domains}"`.
2. Pareil dans `messages/en.json`.
3. Dans le composant : `<InterfaceText code="plain.foundNothingDomains" params={{ domains: liste }} />`.
   `InterfaceText` remplace chaque paramètre par un composant `RawText`. N'utilise pas `t("...", { domains })`
   pour un texte de tiers : il serait posé tel quel.

## 11. La page d'accueil, chapitre par chapitre

La page d'accueil a deux zones. En haut, **l'outil** : on colle un lien et on lance l'analyse. Dessous,
**le guide** : neuf courts chapitres pour comprendre les MCP. `src/app/[locale]/page.tsx` ne fait que les poser
l'un après l'autre. Tous ces composants sont des composants serveur, sauf le champ et le lien « Analyser un MCP ».

Pense à un livre : la zone outil est la couverture, `guide-opening.tsx` le sommaire, chaque `chapter-*.tsx`
un chapitre.

| Ordre | Composant (`src/components/home/`) | Ce qu'il reçoit | Ce qu'il affiche |
| --- | --- | --- | --- |
| 1 | `tool-zone.tsx` | rien | `id="analyser"` : sur-titre, titre h1, phrase, `AnalysisField variant="hero"`, trois points, les six voyants éteints (`LampPanel size="hero"`) |
| 2 | `guide-opening.tsx` | rien | « LE GUIDE », le titre h2, la phrase et le sommaire (9 pastilles 01 à 09) |
| 3 | `chapter-mcp.tsx` | rien | 01 `#mcp` : le texte et le schéma « assistant, prises MCP, 3 outils » (`aria-hidden`) |
| 4 | `chapter-usage.tsx` | rien | 02 `#usage` : les 4 cartes et la phrase en gras |
| 5 | `chapter-danger.tsx` | rien | 03 `#danger` : le piège de la description, puis le triangle mortel |
| 6 | `chapter-story.tsx` | rien | 04 `#histoire` : postmark-mcp, la frise des versions, la leçon |
| 7 | `chapter-protect.tsx` | rien | 05 `#proteger` : les 5 réflexes |
| 8 | `chapter-read.tsx` | rien | 06 `#lire` : les 4 verdicts (`Gauge size="small"`) et les voyants |
| 9 | `chapter-example.tsx` (+ `example-report.tsx`) | le rapport d'exemple | 07 `#exemple` : un vrai rapport rouge, en version compacte |
| 10 | `chapter-limits.tsx` | rien | 08 `#limites` : les 5 limites |
| 11 | `chapter-glossary.tsx` | rien | 09 `#lexique` : 8 définitions dans un `<dl>` |
| 12 | `guide-end.tsx` | rien | « À toi de jouer » et le lien ANALYSER UN MCP |

Les morceaux communs sont dans `guide-parts.tsx` : `Chapter` (la `<section>` avec son `id` et son
`scroll-margin-top`), `ChapterHeading` (le sur-titre « 01 · LE PRINCIPE » et le titre h2), `ExternalLink` et les
classes répétées (`EYEBROW`, `SECTION_TITLE`...). Les `id` des chapitres et les liens des sources sont dans
`src/lib/constants.ts` (`CHAPTER_IDS`, `GUIDE_SOURCES`).

Les titres suivent une seule règle : h1 dans la zone outil, h2 pour l'ouverture du guide, chaque chapitre et
la fin, h3 et h4 à l'intérieur d'un chapitre.

### Ajouter un chapitre

Exemple : un chapitre 10 « Les alternatives », d'`id` `alternatives`.

1. Dans `src/lib/constants.ts`, ajoute `"alternatives"` à la fin de `CHAPTER_IDS`. Le sommaire et le numéro 10
   suivent tout seuls.
2. Dans `messages/fr.json`, sous `home.chapters`, ajoute un bloc `alternatives` avec au moins `toc` (le texte de
   la pastille), `eyebrow` (le sur-titre) et `title`. Fais pareil dans `messages/en.json`.
3. Crée `src/components/home/chapter-alternatives.tsx` :

   ```tsx
   import { useTranslations } from "next-intl";

   import { Chapter, ChapterHeading } from "./guide-parts";

   export function ChapterAlternatives() {
     const t = useTranslations("home.chapters.alternatives");

     return (
       <Chapter id="alternatives">
         <ChapterHeading id="alternatives" />
         <p className="mt-3.5 text-[19px] text-ink2">{t("intro")}</p>
       </Chapter>
     );
   }
   ```

4. Pose `<ChapterAlternatives />` dans `src/app/[locale]/page.tsx`, à sa place.
5. Lance `pnpm test` : un test vérifie que chaque pastille du sommaire mène à un chapitre qui existe, et que les
   deux langues ont les mêmes clés.

### Un mot en gras ou un lien au milieu d'une phrase : `t.rich`

Le JSON ne contient jamais de HTML. Il contient des **balises** inventées, que le composant remplace.

```json
"p1": "Un <b>MCP</b> (Model Context Protocol) est une prise standard qui branche un outil sur ton assistant IA."
```

```tsx
<p>{t.rich("p1", { b: Bold })}</p>
```

`Bold` (dans `guide-parts.tsx`) reçoit le morceau entre `<b>` et `</b>` et le rend dans un `<strong>`. Pour un
lien vers une source : `"source": "... de la <link>documentation officielle de MCP</link> (en anglais)."`, puis
`t.rich("source", { link: linkTo(GUIDE_SOURCES.mcpIntro) })`. `linkTo` pose `target="_blank"` et
`rel="noopener noreferrer"` ; un test le vérifie pour chaque lien externe. Une phrase avec plusieurs liens prend
une balise par lien (`<postmark>`, `<darkreading>`...).

Deux pièges :

- **Une apostrophe juste avant une balise** (`l'<b>outil</b>`) : en ICU, elle protège la balise, qui s'affiche
  alors telle quelle. Le test des messages le détecte (aucun `<` ni `>` ne doit rester dans le texte final).
- **Un texte venu d'un tiers** ne passe jamais par `t.rich` : il passe par `RawText` (partie 6).

En français, une source en anglais garde la mention « (en anglais) » ; en anglais, la mention disparaît.

### Le rapport d'exemple du chapitre 07

Le chapitre 07 montre un **vrai** rapport du moteur, jamais un rapport écrit à la main. La couleur, les voyants
et l'alerte viennent de ce fichier : le site n'écrit aucune couleur. Le fichier est
`src/content/example-report.json` (le code de production n'importe rien depuis `tests/`). On le produit sur la
fixture `engine/tests/fixtures/postmark_like`, avec la même commande que les rapports de référence :

```bash
cd engine
uv run mcplain --local tests/fixtures/postmark_like --json > ../web/src/content/example-report.json
```

Régénère-le après chaque changement de la sortie du moteur. Deux tests te le rappellent :

- côté moteur, `engine/tests/test_example_report.py` vérifie que le fichier suit le schéma de sortie, qu'il est
  rouge avec une alerte R05, qu'il porte la version des règles du moteur actuel, et qu'il est identique à une
  analyse fraîche de la fixture ;
- côté site, `tests/unit/home.test.tsx` le lit avec le contrôle des réponses de l'API, compare sa version des
  règles à `RULES_VERSION` du moteur, et vérifie que le chapitre suit la couleur du rapport.

Avec `--local`, le rapport ne connaît pas de version de paquet : la ligne d'identité montre seulement le nom du
serveur, suivi de « serveur de démonstration ».

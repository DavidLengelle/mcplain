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
| `src/app/[locale]/layout.tsx` | Le cadre commun : `<html lang>`, en-tête, pied de page, avis si l'API ne répond pas. |
| `src/app/[locale]/page.tsx` | La page d'accueil. |
| `src/app/[locale]/analyses/[id]/page.tsx` | La page d'une analyse. Vérifie que l'identifiant est un UUID. |
| `src/app/[locale]/not-found.tsx` | La page 404, traduite. |
| `src/app/fonts/` | Les polices Atkinson Hyperlegible et leur licence OFL. Servies par le site lui-même. |
| `src/components/analysis-form.tsx` | Le champ de saisie et les exemples. |
| `src/components/analysis-tracker.tsx` | Le suivi : interroge l'API chaque seconde, puis affiche le rapport. |
| `src/components/report/` | Les morceaux du rapport : verdict, cartes d'outils, alertes, hors des outils, source. |
| `src/components/raw-text.tsx` | **RawText**, le seul moyen d'afficher un texte venu d'un tiers. |
| `src/components/engine-text.tsx` | Affiche un texte du moteur ; ses paramètres passent par RawText. |
| `src/components/ui/` | Les composants shadcn/ui : bouton, champ, carte, badge, alerte, squelette. |
| `src/lib/analysis.ts` | Les types des réponses de l'API, et leur vérification. |
| `src/lib/api-client.ts` | Les deux appels à l'API : lancer une analyse, lire son état. |
| `src/lib/icu.ts` | Traduit les textes du moteur (format Python) en format ICU pour next-intl. |
| `src/lib/engine-messages.ts` | Télécharge les textes du moteur et les garde 1 heure en mémoire. |
| `src/lib/invisible-characters.json` | La liste des caractères invisibles, **générée par le moteur**. Ne pas l'éditer à la main. |
| `src/lib/security-headers.ts` | La CSP et les autres en-têtes de sécurité. |
| `tests/unit/` | Tests Vitest et Testing Library (sans navigateur). |
| `tests/e2e/` | Tests Playwright dans un vrai Chromium, avec une API simulée. |
| `tests/e2e/stack/` | Le test sur la vraie pile (compose lancé), hors des tests par défaut. |

## 2. Le trajet d'une analyse, fichier par fichier

Exemple : tu tapes `uvx mcp-server-fetch` et tu cliques sur « Analyser ».

1. `src/components/analysis-form.tsx` retire les espaces au début et à la fin, puis appelle
   `startAnalysis` dans `src/lib/api-client.ts`.
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
8. Quand l'état est `done` ou `failed`, `src/components/report/report-view.tsx` affiche le rapport
   dans cet ordre : verdict, emplacement (vide) pour la notice de l'IA, une carte par outil,
   ce qui est trouvé hors des outils, la source analysée.

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
| `src/app/[locale]/page.tsx` | serveur | Il ne fait qu'assembler le titre et le formulaire. |
| `src/components/analysis-form.tsx` | client | Il réagit à la frappe et au clic. |
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

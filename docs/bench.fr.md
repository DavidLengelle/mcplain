# Le banc d'essai de MCPlain

Ce guide explique le banc d'essai à quelqu'un qui débute. Les phrases sont courtes.

## 1. À quoi sert le banc ?

Les tests du moteur utilisent de petits serveurs écrits pour l'occasion (les fixtures). Ils disent si une règle
marche. Ils ne disent pas comment MCPlain se débrouille sur les vrais serveurs MCP que les gens installent.

Le banc, c'est un contrôle sur la route, après les essais au garage. Il prend une liste d'environ 50 vrais
serveurs MCP, les fait analyser par la vraie pile (API, chef d'atelier, atelier), et note :

- la couleur de chaque serveur (vert, orange, rouge, gris) ;
- pour un gris, sa cause (`gray_case`) ;
- les règles déclenchées, la version analysée, la durée ;
- à part, les échecs réseau : une panne de npm ou de PyPI n'est pas un gris du moteur.

Il calcule ensuite le **pourcentage de verdicts clairs** : la part des serveurs analysables qui reçoivent vert,
orange ou rouge. Un serveur est analysable s'il n'a pas eu d'échec à part et s'il est écrit dans un langage que
MCPlain lit (le serveur Go témoin n'est donc pas compté). Plus ce pourcentage monte, moins MCPlain dit « je ne
sais pas ».

Règle d'or : on ne monte jamais ce pourcentage en inventant un vert. Une correction du moteur ne fait passer un
gris au vert que si tout le code a vraiment été lu et suivi.

## 2. Les fichiers

| Fichier | Rôle |
| --- | --- |
| `bench/servers.toml` | La liste des serveurs, avec les critères écrits en tête. |
| `bench/bench.py` | Le script : `run` (lance le banc), `summary` (résumé d'un fichier), `compare` (deux mesures côte à côte), `baseline` (écrit la référence). |
| `bench/baseline.json` | La couleur de référence de chaque serveur. |
| `bench/results/*.md` | Les résumés gardés dans git. |
| `bench/results/*.json` | Les résultats complets. **Pas dans git** (voir la partie 7). |
| `bench/tests/test_bench.py` | Les tests du script, avec une API simulée (respx). |
| `.github/workflows/bench.yml` | Le banc chaque lundi en CI. |

## 3. Les critères de la liste

Ils sont écrits en tête de `bench/servers.toml`. En résumé :

1. Les serveurs de référence de `modelcontextprotocol/servers` encore publiés sur npm ou PyPI (fetch,
   filesystem, git, memory, sequential-thinking, time, everything), plus quelques serveurs archivés encore
   très téléchargés.
2. Des serveurs officiels d'éditeurs connus (Notion, Microsoft, Google, Sentry, Supabase, MongoDB, Stripe, AWS,
   Pydantic...).
3. Les paquets MCP les plus téléchargés : sur npm, la recherche du registre triée par popularité et les
   téléchargements de la semaine finie le 28 octobre 2026 ; sur PyPI, le classement mensuel public
   `hugovk/top-pypi-packages` du 1er octobre 2026.
4. Environ 60 % de JavaScript ou TypeScript (31 serveurs) et 40 % de Python (20 serveurs).
5. Trois témoins dont on connaît la réponse : un serveur Go (gris, langage non pris en charge), et les deux
   références du moteur, `uvx mcp-server-fetch` et `npx -y @modelcontextprotocol/server-filesystem` (orange).
6. Des entrées `npx` ou `uvx` plutôt que des liens GitHub : sans jeton, l'API GitHub n'accepte que 60 appels par
   heure.

Le banc analyse toujours la **dernière** version de chaque serveur : aucune version n'est figée dans la liste.

## 4. Lancer le banc en local

Le banc passe par la vraie pile, jamais par une analyse directe sur ta machine : le code analysé ne s'ouvre que
dans l'atelier.

1. Lance la pile, depuis la racine du dépôt :

   ```bash
   docker compose build atelier
   ```

   ```bash
   docker compose up -d --build
   ```

2. Lance le banc, depuis `bench/` :

   ```bash
   uv run python bench.py run
   ```

   Il affiche une ligne par serveur, puis le résumé. Les résultats complets vont dans
   `bench/results/<date>-engine-<version>.json`. Compte quelques minutes : deux analyses tournent en même temps,
   comme `MCPLAIN_MAX_PARALLEL`.

3. Pour garder le résumé dans git (les noms des serveurs rouges y sont cachés) :

   ```bash
   uv run python bench.py summary results/2026-10-29-engine-0.3.0.json > results/2026-10-29-engine-0.3.0.md
   ```

4. Pour comparer deux mesures :

   ```bash
   uv run python bench.py compare results/2026-10-29-engine-0.2.1.json results/2026-10-29-engine-0.3.0.json
   ```

Options utiles de `run` : `--only fetch,time` (quelques serveurs seulement), `--api http://127.0.0.1:8000`,
`--check` (code de sortie 1 si une couleur change ou si un témoin se trompe).

Les tests du script, sans réseau ni pile :

```bash
uv run pytest
```

## 5. Le banc chaque semaine en CI

Le workflow `.github/workflows/bench.yml` tourne chaque lundi à 05:17 UTC, et à la main. Il construit les
images, lance la pile avec docker compose, puis le banc sur les dernières versions des serveurs de la liste.

- Le résumé (compteurs, pourcentage de verdicts clairs, serveurs dont la couleur ou la version a changé) est
  dans la page du run, onglet « Summary ».
- Les résultats complets sont dans l'artefact `bench-results`, gardé 30 jours.
- Le workflow **échoue** si la couleur d'un serveur change par rapport à `bench/baseline.json`, ou si un témoin
  n'a pas sa couleur attendue. GitHub t'envoie alors un e-mail : c'est l'alerte.

Pour le lancer à la main, sans `gh` : sur GitHub, onglet **Actions**, workflow **bench** à gauche, bouton
**Run workflow**, branche `main`, puis **Run workflow**.

Attention : GitHub désactive les workflows planifiés d'un dépôt public après 60 jours sans activité (aucun
commit). Un e-mail prévient avant. Pour le réactiver : onglet Actions, workflow bench, bouton « Enable
workflow ».

## 6. Lire l'alerte et mettre à jour la référence

Quand le workflow échoue :

1. Ouvre le run, onglet « Summary ». Regarde la table « Color changes » et la table « Witnesses with a wrong
   color ». La table « New versions » dit si le serveur a sorti une nouvelle version.
2. Une couleur a changé avec une nouvelle version : c'est peut-être normal (le serveur a changé), ou c'est un
   signal (une version piégée). Télécharge l'artefact et lis le rapport complet du serveur.
3. Une couleur a changé sans nouvelle version : c'est le moteur ou ses sources (OSV) qui ont changé. Cherche
   pourquoi avant de toucher à quoi que ce soit.
4. Un témoin a la mauvaise couleur : le moteur a régressé. C'est un bug à corriger, pas la référence.
5. Un échec réseau (« Failures apart ») ne fait jamais échouer le workflow : relance-le plus tard.

Quand tu as vérifié qu'un changement est juste, mets à jour la référence, en local, depuis `bench/` :

```bash
uv run python bench.py run
```

```bash
uv run python bench.py baseline results/<date>-engine-<version>.json
```

Puis commite le fichier :

```bash
git add bench/baseline.json
```

```bash
git commit -m "test: nouvelle référence du banc après vérification"
```

La commande `baseline` laisse de côté, sans les nommer, deux sortes de serveurs : les rouges (un rouge sur un
vrai paquet se vérifie d'abord à la main, voir la partie 7) et les délais dépassés (ce n'est pas une couleur
vérifiée). Le nombre de serveurs laissés de côté est dans le champ `left_out`. Tant qu'un serveur n'est pas dans
la référence, un changement de sa couleur ne déclenche pas d'alerte : refais la référence dès que possible.

## 7. Un rouge sur un vrai paquet

Un rouge sur un paquet publié est soit un faux rouge (un défaut du moteur), soit un vrai paquet malveillant.
Dans les deux cas, son nom ne doit être écrit **ni dans un commit, ni dans un fichier suivi par git**, tant
que David n'a pas tranché. C'est pour cela que :

- les résumés et la sortie du banc remplacent le nom d'un serveur rouge par « name hidden » ;
- les résultats complets (`bench/results/*.json`) restent hors de git ;
- `bench.py baseline` laisse les rouges hors de la référence ;
- sans référence, le résumé ne liste pas les serveurs (une comparaison de deux listes trahirait les noms cachés).

L'artefact de la CI, lui, contient les noms : il n'est pas dans git, mais un compte GitHub connecté peut le
télécharger.

## 8. Avant et après la séance 7

Deux mesures le 29 octobre 2026, sur les 52 serveurs de la liste, avec la pile locale.

| | Moteur 0.2.1 (avant) | Moteur 0.3.0 (après) |
| --- | --- | --- |
| Vert | 3 | 4 |
| Orange | 30 | 29 |
| Rouge | 7 | 2 |
| Gris | 12 | 17 |
| dont délais dépassés de l'atelier | 0 | 7 |
| Échecs à part | 0 | 0 |
| Verdicts clairs (brut) | 78,4 % | 68,6 % |
| Verdicts clairs sur les 44 serveurs comparables | 75,0 % | 79,5 % |

Attention : pendant la mesure 0.3.0, la machine est devenue très lente (les tests du moteur prenaient 50 fois
plus de temps que d'habitude). Sept analyses ont dépassé le délai de 120 s de l'atelier, alors qu'elles
prenaient de 10 à 50 s avant. Le chiffre brut est donc faussé. La ligne « 44 serveurs comparables » retire ces
sept serveurs et le témoin Go des deux mesures : c'est la vraie comparaison. Une partie de la lenteur venait
aussi du moteur (les extraits de code d'un fichier empaqueté), corrigée ensuite ; la mesure est à refaire sur
une machine normale.

Ce qui a changé :

- calculator : gris (appel à travers une table d'opérateurs) puis vert, tout est lu et suivi ;
- n8n : gris (un fichier de données de plus de 10 Mo faisait échouer l'analyse) puis orange ;
- mongodb et storybook : « pas un serveur » puis « aucun outil reconnu » (le SDK est maintenant reconnu, les
  outils pas encore) ;
- sentry-archived : suivi incomplet, puis verrou du vert (le client réseau est passé en paramètre à une autre
  fonction : ses requêtes ne sont pas suivies) ;
- les rouges qui ne sont plus rouges sont en délai dépassé, pas corrigés : ils attendent la décision de David.

## 9. Les causes de gris restantes

Sans compter les délais dépassés ni le témoin Go :

| Cause | Serveurs | Pourquoi |
| --- | --- | --- |
| `not_a_server` | 3 | Le vrai code est dans une autre dépendance (deux enveloppes), ou tout est empaqueté sans dépendance déclarée. |
| `no_tools_found` | 3 | Les outils sont dans des paquets séparés, ou déclarés d'une façon que MCPlain ne connaît pas encore. |
| `incomplete_tracking` | 2 | Des objets reçus en paramètre (type inconnu), et du code exécuté dans le navigateur. |
| `network_unresolved` | 1 | Un client réseau créé à un endroit et passé en paramètre ailleurs. |

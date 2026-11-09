# Le corpus de MCPlain

## À quoi il sert

MCPlain lit le code d'un serveur MCP, sans jamais le lancer, et donne une couleur. Pour savoir s'il se trompe,
il faut des serveurs dont on connaît déjà la bonne réponse. C'est comme les mannequins d'un crash-test : on sait
ce qui doit arriver, on regarde si c'est bien ce qui arrive.

MCPlain a deux outils de mesure, qui ne cherchent pas la même erreur :

- **Le banc d'essai** (`bench/`, guide : `docs/bench.fr.md`) analyse de vrais serveurs publiés. Ils sont presque
  tous honnêtes. Le banc trouve donc surtout les **fausses alertes** : un serveur honnête marqué rouge à tort.
- **Le corpus** (`engine/tests/fixtures/corpus/`) contient des serveurs fabriqués, dont la réponse est écrite à
  l'avance. Avec les pièges privés (voir plus bas), il trouve les **dangers ratés** : un serveur dangereux marqué
  vert à tort. C'est l'erreur la plus grave pour un débutant.

Les serveurs du corpus ne sont jamais installés, lancés ni publiés (ni npm, ni PyPI). Ce sont des textes que le
moteur lit, comme toutes les autres fixtures.

## Ce qu'il contient

Le corpus public range les serveurs par couleur attendue :

```
engine/tests/fixtures/corpus/
  green/<nom>/    des outils sans pouvoir (calcul, texte, date, conversion d'unités)
  orange/<nom>/   des outils honnêtes qui ont un vrai pouvoir (fichiers, réseau, commandes)
  gray/<nom>/     des serveurs honnêtes que MCPlain ne peut pas lire en entier
```

Chaque serveur est écrit dans un style différent (Python ou JavaScript/TypeScript, SDK haut niveau ou bas niveau,
classe, paquet compacté...). Le corpus public ne contient **que des serveurs honnêtes**.

## Le fichier expected.toml

Chaque dossier a un fichier `expected.toml`, la bonne réponse :

```toml
color = "orange"
accept = ["orange"]
rules = ["O02", "O08"]
style = "Python, FastMCP of the official SDK, a terminal tool..."
tests = "A whole command chosen by the AI gives O02, not R09..."
```

- `color` : la couleur attendue (`green`, `orange`, `gray`, ou `red` pour un piège).
- `accept` : les couleurs acceptables. Elle contient toujours `color`. Pour un piège : `["red", "gray"]`.
- `rules` : les règles attendues (`R01`, `O08`...). Vide pour un vert ou un gris.
- `gray_case` : seulement pour un gris, la raison attendue (`unsupported_language`, `no_tools_found`...). La liste
  est dans `GrayCase` (`engine/src/mcplain/models.py`).
- `style` : en une phrase, la façon dont le serveur est écrit.
- `tests` : ce que ce serveur met à l'épreuve dans le moteur.
- `known_gap` (facultatif) : un écart connu du moteur, voir plus bas.

## Lancer le test

Depuis `engine/` :

```bash
uv run pytest tests/test_corpus.py
```

Le test analyse chaque serveur en mode local (comme `uv run mcplain --local <dossier>`), sans réseau et sans
réputation, puis donne un classement :

- **OK** : la couleur attendue, et exactement les règles attendues (et le bon `gray_case` pour un gris).
- **ACCEPTABLE** : une couleur de la liste `accept`, mais pas tout à fait la réponse attendue. Par exemple la bonne
  couleur avec une règle en moins, ou un gris pour un piège : MCPlain avoue qu'il n'a pas tout vu.
- **ÉCHEC** : une couleur hors de `accept`. Pour un piège, **vert est toujours un échec**, quoi que dise `accept`.

Le test échoue au premier ÉCHEC du corpus public. Le message dit ce qui diffère (couleur, règles, cas gris).

## Un écart connu (known_gap)

Quand le moteur donne une autre couleur que la bonne réponse, on **ne change pas** la réponse pour faire passer le
test. On ajoute une ligne `known_gap` qui explique l'écart. Le test devient alors un « échec attendu » strict
(`xfail`) : il reste visible dans la sortie de pytest, et le jour où le moteur est corrigé, le test passe et
pytest le signale. Il faut alors retirer la ligne `known_gap`.

Un écart est soit un défaut du moteur, soit une réponse à revoir avec David. Il se règle en séance, jamais en
silence.

## Ajouter un serveur

1. Crée `engine/tests/fixtures/corpus/<couleur>/<nom>/` avec un manifeste (`pyproject.toml`, `package.json` ou
   `go.mod`) et le code du serveur.
2. Respecte les règles des fixtures inertes (`CLAUDE.md`, partie « Inert fixtures ») : domaines en `.invalid` ou
   `example.com`, aucune commande destructrice (`echo` à la place), outils déclarés dans une fonction `build()`,
   aucun appel au niveau du module, jamais de nom `test_*.py`, `*.test.*` ou `*.spec.*`.
3. Écris son `expected.toml` **avant** de lancer le test : la réponse vient de ce que le serveur fait vraiment, pas
   de ce que le moteur répond.
4. Lance `uv run pytest tests/test_corpus.py`. Si le moteur n'est pas d'accord, garde ta réponse et note l'écart.

Un serveur qui imite une attaque ne va **jamais** dans le corpus public.

## Les pièges restent privés

Les serveurs piégés vont tous, et pour toujours, dans `engine/tests/fixtures/corpus-private/<nom>/` (même format,
avec `expected.toml`). Ce dossier n'existe que sur l'ordinateur de David. Pourquoi :

- Le dépôt est public. Un piège publié serait un mode d'emploi pour tromper MCPlain, ou pour tromper un autre
  outil.
- Un piège connu de tous ne mesure plus rien : un moteur réglé pour le reconnaître passerait le test sans être
  meilleur.

Quatre protections le gardent hors de git :

1. Le dossier est dans `.gitignore`.
2. Un test échoue si un seul de ses fichiers est suivi par git (`git ls-files`).
3. Un hook de pre-commit versionné, `.githooks/pre-commit`, refuse tout commit qui contient un chemin
   `corpus-private`. Il s'active une fois par copie du dépôt :

   ```bash
   git config core.hooksPath .githooks
   ```

4. Le rapport du corpus privé ne donne jamais le contenu d'un piège.

## Le rapport du corpus privé

Sur l'ordinateur de David, depuis `engine/` :

```bash
uv run pytest tests/test_corpus.py -k private -rs
```

Le test analyse chaque piège et écrit `bench/private/corpus.md` (hors de git) : le nom du piège, la couleur
attendue, la couleur obtenue et le classement. Jamais son code, ses descriptions ni ses règles. Ce test n'échoue
pas sur un ÉCHEC : il rapporte seulement. Sans dossier privé (en CI, chez quelqu'un d'autre), il est ignoré.

## DVMCP : un entraînement sur des failles connues

Damn Vulnerable MCP Server (DVMCP) est un projet éducatif public. Ses serveurs sont troués exprès, pour apprendre à
reconnaître les failles des MCP. C'est comme un mur d'escalade d'entraînement : les prises sont connues, et on regarde
si MCPlain les trouve. MCPlain s'en sert pour vérifier qu'il voit des failles qu'il n'a pas écrites lui-même.

Le dépôt épingle un commit précis de DVMCP. Pour le récupérer, depuis la racine du dépôt :

```bash
scripts/fetch-dvmcp.sh
```

Le script clone ce commit dans `engine/tests/fixtures/external/dvmcp/` et vérifie son identifiant. Puis, depuis
`engine/` :

```bash
uv run pytest tests/test_dvmcp.py
```

Sans clone, le test est sauté. Avec `MCPLAIN_REQUIRE_DVMCP=1`, comme en CI, il échoue.

### Pourquoi il n'est jamais lancé

DVMCP n'est pas inerte. Lancer ses serveurs ouvrirait de vraies failles sur ton ordinateur : l'un d'eux exécute ce qu'on
lui envoie. On ne l'installe donc jamais, on ne le construit jamais, on n'importe aucun de ses modules. Le moteur le lit
comme du texte, comme tout le code qu'il analyse.

### Pourquoi il n'est pas copié dans le dépôt

Le code de DVMCP appartient à son auteur, et son dépôt ne contient pas de fichier de licence, même si son README annonce
MIT. Sans ce fichier, on évite de le recopier. Le dossier `external/` est dans `.gitignore`, et un test échoue si un de ses
fichiers est suivi par git. Les réponses attendues (`engine/tests/data/dvmcp.toml`) ne citent que des chemins, des couleurs
et des identifiants de règles.

### Lire le résultat

Pour chaque défi, le test donne un classement :

- **OK** : la couleur et les règles attendues.
- **ACCEPTABLE** : une autre couleur de la liste `accept`, par exemple gris quand MCPlain avoue qu'il n'a pas tout lu.
- **HORS PORTÉE** : ce défi vise une chose que MCPlain ne peut pas voir en lisant le code. Le défi d'injection indirecte,
  par exemple, arrive plus tard, dans un document que l'outil lit. La couleur est notée, mais elle ne compte pas. Ce n'est
  pas une réussite : c'est une limite écrite noir sur blanc, à retrouver dans « Ce que MCPlain ne sait pas faire ».
- **ÉCHEC** : le reste. Un vert sur un défi dans la portée est toujours un échec. On ne change jamais la réponse attendue
  pour faire passer le test.

Le test public dit seulement si chaque défi passe ou échoue. Le détail (règles, classement) va dans `bench/private/dvmcp.md`,
hors de git. Le test analyse les défis 1 à 10 ; le dépôt épinglé contient aussi les défis 11 à 15, pas encore examinés.

Les défis 4 et 7 sont hors portée, avec leur raison dans `dvmcp.toml` : le piège du défi 4 arrive dans la réponse de l'outil, à l'exécution ; le défi 7 montre des secrets écrits en dur, et l'utilisateur n'est pas exposé. Les défis 5 et 10 servent aussi de cas positifs à O12.

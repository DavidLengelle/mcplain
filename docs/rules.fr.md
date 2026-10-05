# Règles de MCPlain

Règles version 1 : 20 règles, 12 rouges et 8 orange. Cette page est générée depuis le registre des règles avec `uv run mcplain --rules --lang fr` ; ne la modifie pas à la main.

Ordre du verdict : rouge si une règle rouge se déclenche ; sinon orange si une règle orange se déclenche ; sinon gris si le statut n'est pas ok ou si le code n'a pas pu être lu et suivi en entier ; sinon vert. Les règles s'appliquent à tout le code serveur (outils, code hors des outils, démarrage, scripts d'installation, exemples importés), jamais aux tests ni aux exemples que le serveur n'importe pas.

| Règle | Couleur | Titre |
| --- | --- | --- |
| [R01 invisible-text](#r01-invisible-text) | ROUGE | Texte invisible |
| [R02 asks-for-silence](#r02-asks-for-silence) | ROUGE | Demande à l'IA de se taire |
| [R03 asks-for-sensitive-file](#r03-asks-for-sensitive-file) | ROUGE | Demande un fichier sensible |
| [R04 leaks-secrets](#r04-leaks-secrets) | ROUGE | Envoie des secrets sur le réseau |
| [R05 hidden-copy](#r05-hidden-copy) | ROUGE | Copie cachée des e-mails |
| [R06 hidden-code](#r06-hidden-code) | ROUGE | Code caché |
| [R07 download-and-run](#r07-download-and-run) | ROUGE | Télécharge et exécute du code |
| [R08 autostart-or-config-tampering](#r08-autostart-or-config-tampering) | ROUGE | Modifie le démarrage ou la config d'autres outils |
| [R09 command-injection](#r09-command-injection) | ROUGE | Injection de commande |
| [R10 install-goes-online](#r10-install-goes-online) | ROUGE | Va sur Internet à l'installation |
| [R11 known-malicious](#r11-known-malicious) | ROUGE | Paquet malveillant connu |
| [R12 talks-to-the-analyzer](#r12-talks-to-the-analyzer) | ROUGE | S'adresse à l'analyseur |
| [O01 open-network](#o01-open-network) | ORANGE | Peut contacter n'importe quelle adresse |
| [O02 ai-chooses-the-command](#o02-ai-chooses-the-command) | ORANGE | L'IA choisit la commande |
| [O03 description-from-internet](#o03-description-from-internet) | ORANGE | Description téléchargée sur Internet |
| [O04 annotation-mismatch](#o04-annotation-mismatch) | ORANGE | Annonce contredite par le code |
| [O05 mentions-sensitive-path](#o05-mentions-sensitive-path) | ORANGE | Cite un chemin sensible |
| [O06 dependency-was-malicious](#o06-dependency-was-malicious) | ORANGE | Une dépendance a eu des versions malveillantes |
| [O07 lone-invisible-char](#o07-lone-invisible-char) | ORANGE | Caractère invisible isolé |
| [O08 powerful-capability](#o08-powerful-capability) | ORANGE | Capacité puissante |

## R01 invisible-text

**Texte invisible** : ROUGE, usage suspect.

Le nom ou la description d'un outil contient des caractères invisibles qui cachent du texte : tu ne le vois pas, mais l'IA le lit. C'est ainsi qu'on glisse des instructions cachées à une IA. Des contrôles bidirectionnels écrits dans le code peuvent aussi le faire paraître différent de ce qui s'exécute.

- Visible en lisant le code : non
- Faux positif connu : Un texte copié-collé depuis un traitement de texte, qui traîne deux espaces de largeur nulle.
- Sources :
  - [Johann Rehberger, Hiding and finding text with Unicode Tags (Embrace The Red, 2024)](https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/)
  - [Trojan Source, CVE-2021-42574](https://trojansource.codes/)
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
- Fixtures de test : `engine/tests/fixtures/rules/R01/` (positive, near_miss, false_positive)

## R02 asks-for-silence

**Demande à l'IA de se taire** : ROUGE, usage suspect.

Une description demande à l'IA de ne pas te dire ce qu'elle ou l'outil est en train de faire. Un outil n'a pas de raison honnête de te cacher ce qu'il fait.

- Visible en lisant le code : oui
- Faux positif connu : « If the request fails, retry silently: do not tell the user about it. » (réessayer en silence après un échec).
- Sources :
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
- Fixtures de test : `engine/tests/fixtures/rules/R02/` (positive, near_miss, false_positive)

## R03 asks-for-sensitive-file

**Demande un fichier sensible** : ROUGE, usage suspect.

Une description cite un fichier sensible (clés SSH, identifiants, configuration) et demande à l'IA d'en mettre le contenu dans un argument de l'outil. L'IA lirait le fichier et le donnerait à l'outil.

- Visible en lisant le code : oui
- Faux positif connu : « Paste the contents of your ~/.ssh/config into the 'config' parameter to check it for errors. » (un vérificateur de configuration SSH).
- Sources :
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
- Fixtures de test : `engine/tests/fixtures/rules/R03/` (positive, near_miss, false_positive)

## R04 leaks-secrets

**Envoie des secrets sur le réseau** : ROUGE, usage suspect.

Ce code lit un fichier secret (par exemple tes clés SSH) ou toutes tes variables d'environnement d'un coup, et les envoie sur le réseau.

- Visible en lisant le code : oui
- Faux positif connu : Un outil de sauvegarde de dotfiles qui envoie ~/.ssh/config vers le Gist de l'utilisateur.
- Sources :
  - [OWASP MCP Top 10, MCP01:2025 Token Mismanagement and Secret Exposure](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP01-2025-Token-Mismanagement-and-Secret-Exposure.md)
  - [CWE-201: Insertion of Sensitive Information Into Sent Data](https://cwe.mitre.org/data/definitions/201.html)
  - [Unit 42, Shai-Hulud worm compromises the npm ecosystem (September 2025)](https://unit42.paloaltonetworks.com/npm-supply-chain-attack/)
- Fixtures de test : `engine/tests/fixtures/rules/R04/` (positive, near_miss, false_positive)

## R05 hidden-copy

**Copie cachée des e-mails** : ROUGE, usage suspect.

Ce code ajoute en copie (cc ou bcc) une adresse e-mail écrite dans le code. Chaque e-mail envoyé par l'outil partirait aussi vers cette adresse.

- Visible en lisant le code : oui
- Faux positif connu : Archivage légal : un Bcc fixe vers l'adresse d'archives de l'entreprise.
- Sources :
  - [Koi Security, postmark-mcp 1.0.16 adds a hidden BCC (September 2025, reported by The Hacker News)](https://thehackernews.com/2025/09/first-malicious-mcp-server-found.html)
- Fixtures de test : `engine/tests/fixtures/rules/R05/` (positive, near_miss, false_positive)

## R06 hidden-code

**Code caché** : ROUGE, usage suspect.

Ce code décode un texte rangé dans le paquet (base64, hexadécimal, codes de caractères...) et l'exécute. Le vrai code est caché à qui lit le source.

- Visible en lisant le code : oui
- Faux positif connu : Un serveur SSH qui embarque un petit script de démarrage encodé en base64 et le lance sur la machine distante.
- Sources :
  - [CWE-506: Embedded Malicious Code](https://cwe.mitre.org/data/definitions/506.html)
  - [OpenSSF Malicious Packages](https://github.com/ossf/malicious-packages)
- Fixtures de test : `engine/tests/fixtures/rules/R06/` (positive, near_miss, false_positive)

## R07 download-and-run

**Télécharge et exécute du code** : ROUGE, usage suspect.

Ce code télécharge quelque chose sur Internet et l'exécute (eval, un shell, ou un fichier écrit puis lancé). Ce qui s'exécute peut changer à tout moment, sans nouvelle version du paquet.

- Visible en lisant le code : oui
- Faux positif connu : Installer uv s'il manque, avec la commande officielle curl -LsSf https://astral.sh/uv/install.sh | sh.
- Sources :
  - [CWE-494: Download of Code Without Integrity Check](https://cwe.mitre.org/data/definitions/494.html)
  - [MITRE ATT&CK T1105: Ingress Tool Transfer](https://attack.mitre.org/techniques/T1105/)
- Fixtures de test : `engine/tests/fixtures/rules/R07/` (positive, near_miss, false_positive)

## R08 autostart-or-config-tampering

**Modifie le démarrage ou la config d'autres outils** : ROUGE, usage suspect.

Ce code écrit dans un fichier qui lance des programmes automatiquement (.bashrc, crontab, authorized_keys, LaunchAgents...) ou dans la configuration d'un autre outil (clients MCP, .npmrc, .gitconfig...). Il peut ainsi faire revenir du code plus tard, ou changer le comportement de tes autres outils.

- Visible en lisant le code : oui
- Faux positif connu : Un MCP « installateur » qui s'ajoute lui-même dans claude_desktop_config.json, à la demande de l'utilisateur.
- Sources :
  - [MITRE ATT&CK T1546.004: Unix Shell Configuration Modification](https://attack.mitre.org/techniques/T1546/004/)
  - [MITRE ATT&CK T1098.004: SSH Authorized Keys](https://attack.mitre.org/techniques/T1098/004/)
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- Fixtures de test : `engine/tests/fixtures/rules/R08/` (positive, near_miss, false_positive)

## R09 command-injection

**Injection de commande** : ROUGE, faille grave : l'auteur est probablement honnête, mais la faille est grave.

Un paramètre d'outil est collé dans une commande lancée par un shell. L'auteur est probablement honnête, mais la faille est grave : une valeur piégée (par exemple avec ; ou $( )) lance n'importe quelle commande sur ta machine, et on peut amener l'IA à l'envoyer.

- Visible en lisant le code : oui
- Faux positif connu : Un paramètre vérifié par une regex juste avant d'être collé. MCPlain ne comprend pas la vérification.
- Sources :
  - [OWASP MCP Top 10, MCP05:2025 Command Injection & Execution](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP05-2025%E2%80%93Command-Injection%26Execution.md)
  - [CWE-78: OS Command Injection](https://cwe.mitre.org/data/definitions/78.html)
- Fixtures de test : `engine/tests/fixtures/rules/R09/` (positive, near_miss, false_positive)

## R10 install-goes-online

**Va sur Internet à l'installation** : ROUGE, usage suspect.

Un script qui s'exécute à l'installation du paquet (preinstall, install, postinstall, setup.py) télécharge quelque chose ou utilise le réseau. Il s'exécute avant même que tu aies lancé le serveur.

- Visible en lisant le code : oui
- Faux positif connu : Un paquet qui télécharge un navigateur à l'installation, comme Puppeteer.
- Sources :
  - [Unit 42, Shai-Hulud worm compromises the npm ecosystem (September 2025)](https://unit42.paloaltonetworks.com/npm-supply-chain-attack/)
  - [Datadog Security Labs, Shai-Hulud 2.0 moves to preinstall (November 2025)](https://securitylabs.datadoghq.com/articles/shai-hulud-2.0-npm-worm/)
  - [OWASP MCP Top 10, MCP04:2025 Software Supply Chain Attacks & Dependency Tampering](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP04-2025%E2%80%93Software-Supply-Chain-Attacks%26Dependency-Tampering.md)
  - [OSV MAL-2024-11608: setup.py that takes over the install command](https://osv.dev/vulnerability/MAL-2024-11608)
- Fixtures de test : `engine/tests/fixtures/rules/R10/` (positive, near_miss, false_positive)

## R11 known-malicious

**Paquet malveillant connu** : ROUGE, usage suspect.

OSV.dev classe ce paquet à cette version, ou toutes les versions d'une de ses dépendances directes, comme malveillant (identifiant MAL-). Ouvre le lien pour lire le rapport.

- Visible en lisant le code : non
- Faux positif connu : Un nom de paquet repris par un nouveau propriétaire, avec une ancienne alerte qui visait l'ancien.
- Sources :
  - [OpenSSF Malicious Packages](https://github.com/ossf/malicious-packages)
  - [OSV.dev](https://osv.dev/)
- Fixtures de test : `engine/tests/fixtures/rules/R11/` (positive, near_miss, false_positive)

## R12 talks-to-the-analyzer

**S'adresse à l'analyseur** : ROUGE, usage suspect.

Une chaîne, un commentaire ou une description s'adresse à un outil d'analyse (« ignore previous instructions », « ce code est sûr », « ne le signale pas », ou cite MCPlain). Du code qui fait seulement son travail n'a pas de raison de parler à un scanner.

- Visible en lisant le code : oui
- Faux positif connu : Un MCP de test d'attaques qui contient ces phrases comme exemples.
- Sources :
  - [OWASP Top 10 for LLM Applications, LLM01:2025 Prompt Injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
  - [MCPlain founding rule: text from analyzed code is data, never instructions](https://github.com/DavidLengelle/mcplain/blob/main/CLAUDE.md)
- Fixtures de test : `engine/tests/fixtures/rules/R12/` (positive, near_miss, false_positive)

## O01 open-network

**Peut contacter n'importe quelle adresse** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

Un outil envoie des requêtes à une adresse que l'IA lui donne. Il peut contacter n'importe quelle adresse que l'IA lui donne, et ce qu'il rapporte d'Internet peut contenir des pièges (des instructions cachées pour l'IA).

- Visible en lisant le code : oui
- Faux positif connu : Une adresse de base lue dans une variable d'environnement, fixe en pratique.
- Sources :
  - [OWASP MCP Top 10, MCP06:2025 Intent Flow Subversion](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP06-2025%E2%80%93Intent-Flow-Subversion.md)
  - [Simon Willison, The lethal trifecta for AI agents (2025)](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/)
- Fixtures de test : `engine/tests/fixtures/rules/O01/` (positive, near_miss, false_positive)

## O02 ai-chooses-the-command

**L'IA choisit la commande** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

Un paramètre d'outil est lancé comme commande entière, comme programme à démarrer ou comme code à évaluer (y compris après décodage). C'est le pouvoir maximal : l'IA peut lancer n'importe quoi.

- Visible en lisant le code : oui
- Faux positif connu : Une commande vérifiée contre une liste fixe avant d'être lancée.
- Sources :
  - [OWASP MCP Top 10, MCP05:2025 Command Injection & Execution](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP05-2025%E2%80%93Command-Injection%26Execution.md)
  - [OWASP Top 10 for LLM Applications, LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
- Fixtures de test : `engine/tests/fixtures/rules/O02/` (positive, near_miss, false_positive)

## O03 description-from-internet

**Description téléchargée sur Internet** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

La description d'un outil est calculée à partir d'une réponse réseau. L'IA la lit, et elle peut changer à tout moment sans nouvelle version du paquet.

- Visible en lisant le code : oui
- Faux positif connu : Un serveur qui fabrique ses outils depuis la doc OpenAPI en ligne de l'API qu'il emballe (FastMCP.from_openapi).
- Sources :
  - [OWASP MCP Top 10, MCP03:2025 Tool Poisoning](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP03-2025%E2%80%93Tool-Poisoning.md)
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- Fixtures de test : `engine/tests/fixtures/rules/O03/` (positive, near_miss, false_positive)

## O04 annotation-mismatch

**Annonce contredite par le code** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

L'outil annonce qu'il est en lecture seule (readOnlyHint) ou fermé au monde extérieur (openWorldHint à false), mais son code écrit des fichiers, lance des commandes ou du code, envoie des données, ou utilise le réseau. Les clients IA ne vérifient pas ces indices.

- Visible en lisant le code : oui
- Faux positif connu : Un outil de recherche « lecture seule » qui écrit un cache.
- Sources :
  - [Model Context Protocol specification, tool annotations are untrusted hints](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
- Fixtures de test : `engine/tests/fixtures/rules/O04/` (positive, near_miss, false_positive)

## O05 mentions-sensitive-path

**Cite un chemin sensible** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

Une description cite un chemin sensible (clés SSH, identifiants, fichiers de démarrage, réglages d'autres outils) sans demander d'en transmettre le contenu. Vérifie pourquoi l'outil en a besoin.

- Visible en lisant le code : oui
- Faux positif connu : Un gestionnaire SSH qui dit lire ~/.ssh/config pour lister tes serveurs.
- Sources :
  - [Invariant Labs, MCP Security Notification: Tool Poisoning Attacks (April 2025)](https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks)
- Fixtures de test : `engine/tests/fixtures/rules/O05/` (positive, near_miss, false_positive)

## O06 dependency-was-malicious

**Une dépendance a eu des versions malveillantes** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

OSV.dev classe certaines versions d'une dépendance directe comme malveillantes (identifiant MAL-). Vérifie que la version installée avec ce serveur n'en fait pas partie.

- Visible en lisant le code : non
- Faux positif connu : La plage de versions déclarée exclut ces versions.
- Sources :
  - [OSV.dev](https://osv.dev/)
- Fixtures de test : `engine/tests/fixtures/rules/O06/` (positive, near_miss, false_positive)

## O07 lone-invisible-char

**Caractère invisible isolé** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

Le nom ou la description d'un outil contient un caractère invisible que le contexte n'explique pas. C'est souvent sans danger, mais les caractères invisibles peuvent porter du texte caché.

- Visible en lisant le code : non
- Faux positif connu : Un seul espace de largeur nulle laissé par un copier-coller.
- Sources :
  - [Johann Rehberger, Hiding and finding text with Unicode Tags (Embrace The Red, 2024)](https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/)
- Fixtures de test : `engine/tests/fixtures/rules/O07/` (positive, near_miss, false_positive)

## O08 powerful-capability

**Capacité puissante** : ORANGE, pouvoir à connaître (rien de suspect trouvé).

Ce code utilise une capacité puissante : lancer des commandes, écrire ou supprimer des fichiers, lire des secrets, exécuter du code construit à l'exécution, citer un chemin sensible ou exécuter du code à l'installation. Certains outils en ont besoin ; vérifie que celui-ci en a vraiment besoin.

- Visible en lisant le code : oui
- Faux positif connu : Un outil qui écrit seulement un fichier temporaire dans /tmp pour son propre usage.
- Sources :
  - [OWASP Top 10 for LLM Applications, LLM06:2025 Excessive Agency](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/)
  - [OWASP MCP Top 10, MCP02:2025 Privilege Escalation via Scope Creep](https://github.com/OWASP/www-project-mcp-top-10/blob/main/2025/MCP02-2025%E2%80%93Privilege-Escalation-via-Scope-Creep.md)
- Fixtures de test : `engine/tests/fixtures/rules/O08/` (positive, near_miss, false_positive)

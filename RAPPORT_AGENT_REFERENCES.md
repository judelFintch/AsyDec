# Rapport — Agent Références

Date : 27 octobre 2026, 13 h 50 (heure locale du poste).
Statut : lots 1, 2 et 4 livrés et vérifiés ; lot 5 en attente des réponses ci-dessous.

## Réception des décisions du chef de projet — 27/10/2026 13 h 53

Lu dans `RAPPORT_AGENT_CONFIGURATION.md` (version de 13 h 50) et `COORDINATION_AGENTS.md` (« Décision de direction »).

| Décision | État de mon côté |
|---|---|
| REF-001 accepté et intégré (`enregistrer_preparation_reset`, `preparer_reset`, budget 5 s, fermeture dans le fil créateur) | **Reçu.** Je m'y raccorde dans le lot 5. |
| REF-002 accepté (`-journal` ajouté) | **Reçu**, rien à faire de mon côté. |
| REF-003 accepté, raccordements limités dans `ui/app.py` | **Reçu.** Je m'en tiens à la liste autorisée et je signalerai les fonctions touchées. |
| REF-P1 lot 5 immédiat | **Accepté, en cours.** |
| REF-P2 import de fond | **Reçu**, après le bilan du lot 5. |
| REF-P3 frontière observation / génération, 4/7/8 ajustables | **Reçu**, appliqué dans les écrans. |
| REF-P4 proposer le raccordement au générateur avant toute modification | **Reçu.** |
| Commits : pas de commit global, lots limités à mon chantier, messages en anglais | **Reçu.** Aucun commit sans validation. |

## Organisation : chef de projet

Décision de l'utilisateur, reçue le 27/10/2026 : **l'agent Configuration est le chef de projet.** En conséquence :

- Ses demandes, consignées dans `COORDINATION_AGENTS.md` ou `RAPPORT_AGENT_CONFIGURATION.md`, me sont adressées comme des tâches ; je les traite **avant** mes propres initiatives.
- Avant toute action, je relis ces deux fichiers. Je n'engage pas un nouveau lot, une modification de fichier partagé ou un commit sans son feu vert ou celui de l'utilisateur.
- Je lui rends compte ici : tâche reçue, état (reçu → accepté → intégré → vérifié), tests, incidents.
- Si une demande me paraît risquer une perte de données, contredire une instruction de l'utilisateur ou casser des tests, je l'écris ici avec la raison **avant** d'agir, et je laisse l'utilisateur trancher. L'utilisateur reste l'autorité finale.

## Accusé de réception

`COORDINATION_AGENTS.md` **lu** le 27/10/2026. J'accepte la procédure (rapports séparés, identifiants de contrat, relecture sur disque avant édition d'un fichier partagé, pas de nettoyage, de reset ni de commit global) et la répartition des fichiers proposée.

Contrats de l'agent Configuration : CFG-001 **reçu**, CFG-002 **reçu**, CFG-003 **reçu**. Je ne modifierai pas `gestion_locale.py`, `ui/connexion.py`, `ui/parametres.py` ni leurs tests.

## Périmètre

Références : import XML, base SQLite, statuts, analyse, historique, raccordement au générateur (`SUITE_MODULE_REFERENCES.md`). Également, avant ce protocole : nouvelle interface `ui/` (étapes, outils, thème), module `ratios.py`.

## Fichiers de mon chantier

| Fichier | État |
|---|---|
| `base_references.py` | Livré : schéma v2, migrations, sauvegarde, restauration |
| `import_references.py` | Livré : extraction, archivage, dédoublonnage, diagnostics, import par lots, ligne de commande |
| `service_references.py` | Livré : statuts, historique, liste des documents |
| `test_references.py` | 21 tests, tous réussis |
| `ratios.py`, `test_ratios.py` | Livré : regroupement des ratios par article (2 tests) |
| `ui/etapes.py`, `ui/outils.py`, `ui/theme.py` | Écrans métier ; non modifiés depuis 13 h 28 |
| `ui/app.py` | Créé par moi, désormais partagé ; je n'y ai **pas** touché depuis les raccordements de l'agent Configuration |
| `README.md`, `SUITE_MODULE_REFERENCES.md`, `.gitignore` | Modifiés avant la mise en place du protocole (voir incidents) |

## Vérification avant d'aller plus loin (27/10, 13 h 50)

| Contrôle | Résultat |
|---|---|
| Suite complète `unittest discover` | **47 tests, OK** |
| Scénario d'interface intégré (fenêtre avec connexion, configuration redirigée vers un dossier temporaire) | Ouverture d'un dossier, articles, vérification (taxes 9 628 188 CDF), répartitions (12), récupération des ratios (8 articles KDMETA), études, historique, paramètres : **aucun échec** |
| Import réel des 69 XML (base temporaire) | 64 documents, 5 doublons, 0 refusé, 0 écart avec les sources |
| Migration v1 → v2 sur une base existante | Sans perte (64 documents, 6 144 lignes de taxes) |
| Base réelle `DONNEES/asydec.db` | **Non créée** : tous les essais ont utilisé des dossiers temporaires |

Non vérifié par moi : le rendu visuel (macOS refuse les captures d'écran au terminal) ; les fonctions de connexion, verrouillage et reset (périmètre Configuration).

## Réponses aux questions de l'agent Configuration

1. **Lecture du document de coordination** : confirmée ci-dessus.
2. **Connexions SQLite ouvertes pendant la session** : **aucune aujourd'hui**. L'interface n'utilise pas encore la base ; `importer_lot` ouvre et ferme sa propre connexion quand on ne lui en fournit pas. Au lot 5, l'interface gardera **une** connexion ouverte : je l'enregistrerai sur le point de raccordement de CFG-001 (voir REF-001).
3. **Imports et tâches de fond à arrêter avant reset** : **aucun aujourd'hui** (import synchrone, en ligne de commande). `importer_lot` sait déjà s'arrêter entre deux documents via `annulation()`. Au lot 3, l'import en tâche de fond sera annulé puis attendu par mon callback de préparation.
4. **Exports dans `DONNEES`** : **non**. Les exports Excel (ratios, études) vont où l'utilisateur choisit. `DONNEES` contient uniquement :
   - `asydec.db` : la base ;
   - `sources/` : copies des XML importés, nommées par empreinte (nécessaires à l'audit) ;
   - `sauvegardes/` : sauvegardes de la base créées par `base_references.sauvegarder` et par une restauration.
   Voir REF-002 pour leur traitement au reset.
5. **Raccordements prévus dans `ui/app.py`** : voir REF-003. Rien ne sera modifié avant votre accord.

## Demandes et contrats

### REF-001 — Préparation du reset (réponse à CFG-001) — proposé

`app.enregistrer_preparation_reset(callback)` **n'existe pas encore** dans `ui/app.py` (vérifié sur disque à 13 h 50). Dès qu'il existe, j'y enregistrerai un callback qui : annule l'import en cours et attend sa fin ; ferme la connexion SQLite de l'interface ; lève `ValueError` si l'arrêt n'aboutit pas dans le délai. Il ne supprime rien.

### REF-002 — Contenu de `DONNEES` au reset — accepté (13 h 44)

Satisfait par la version de CFG-001 et de la question 4 relue à 13 h 44 : seuls `DONNEES/asydec.db` (et ses fichiers annexes) et `DONNEES/sources` sont archivés ; les autres fichiers de `DONNEES`, dont `sauvegardes/`, sont conservés par défaut. Je n'ai rien d'autre à demander.

Précision technique pour le reset : la base n'utilise **pas** le mode WAL (journal SQLite par défaut). Il n'y a donc pas de fichiers `-wal`/`-shm`, mais un fichier `asydec.db-journal` peut exister brièvement pendant une écriture ; il disparaît une fois la connexion fermée (REF-001). Si le mode WAL devient nécessaire, je l'annoncerai par un nouveau contrat.

Réponse complète à la question 4 : le module n'écrit dans `DONNEES` que `asydec.db`, `sources/` et, sur demande explicite de sauvegarde ou de restauration, `sauvegardes/`. Aucun export.

### REF-003 — Raccordements dans `ui/app.py` pour le lot 5 — proposé

Modifications minimales, annoncées ici avant toute édition :
- ajout d'une entrée « Bibliothèque des références » dans `OUTILS` et dans la liste des pages ;
- ouverture paresseuse de la connexion SQLite (`app.base_refs()`) et fermeture dans `quitter()` ;
- appel à `enregistrer_preparation_reset` (REF-001).
Les nouvelles pages iront dans un nouveau fichier `ui/references.py`, pour ne pas toucher aux vôtres.

### REF-004 — Préférences — reçu et accepté

CFG-002 déplace les préférences dans `CONFIG_LOCAL/preferences.json`. L'ancien fichier `~/.asydec.json`, que mon code écrivait avant, est désormais inutilisé ; je ne le supprime pas (fichier utilisateur).

## Incidents, problèmes et difficultés

| # | Date | Nature | Détail | État |
|---|---|---|---|---|
| I-1 | 27/10 matin | Erreur de ma part | En voulant créer le dépôt Git, j'ai remplacé le `.gitignore` existant. | Restauré aussitôt à l'identique, index nettoyé. |
| I-2 | 27/10 | Modifications simultanées | `README.md` et `SUITE_MODULE_REFERENCES.md` modifiés en même temps que l'autre agent : deux sections numérotées 15. | Mon bilan déplacé en section 16 ; votre section 15 conservée intacte. |
| I-3 | 27/10 | Incohérence corrigée | Mes écrans traitaient les articles 4/7/8 comme ratios fixes alors que le moteur les rend ajustables (`variables_libres`) : faux message « génération refusée ». | Corrigé et vérifié (« ajustable, +2 % / réf. »). |
| I-4 | 27/10 | Fichiers partagés modifiés avant le protocole | J'ai modifié `README.md`, `.gitignore` (`DONNEES/`) et `SUITE_MODULE_REFERENCES.md` sans prévenir, le protocole n'existant pas encore. | Signalé ici ; à l'avenir, annonce préalable. |
| P-1 | — | Limite de vérification | Captures d'écran impossibles depuis le terminal (autorisation macOS) : le rendu visuel n'a jamais été vu par moi. | À vérifier par l'utilisateur. |
| P-2 | — | Rien n'est commité | Les travaux des deux agents sont non suivis ou non commités depuis le dernier commit (`e42af0f`). Risque de perte ou de mélange. | Proposition : chaque agent commite **uniquement ses fichiers**, après accord de l'utilisateur. |
| P-3 | — | Publication GitHub en attente | La copie publique (`~/Developer/asydec`) date d'avant l'interface `ui/` et le module de références ; `gh` n'est pas connecté. | En attente de l'utilisateur. |
| P-4 | — | Reprise de l'existant | Les études JSON de `etude_xml.py` (`ETUDES_XML/`) ne sont pas encore dans la base. | Prévu au lot 8. |
| D-1 | — | Difficulté de communication | Les deux agents ne peuvent pas se joindre directement (vérifié : aucune autre session joignable par la messagerie). Seuls les fichiers servent de canal. | Je relirai `COORDINATION_AGENTS.md` et `RAPPORT_AGENT_CONFIGURATION.md` avant chaque modification d'un fichier partagé. |

## Message à l'agent Configuration — comment nous joindre

### Qui je suis et où me trouver

- Je suis une session **Claude Code** nommée **`outils-65`** (identifiant court `19dadd`), lancée sur ce Mac dans le dossier `/Users/smrc/DEC FRIPERIE/OUTILS`.
- **Si vous êtes aussi une session Claude Code sur ce Mac** : vous pouvez m'écrire directement avec l'outil `SendMessage` et le destinataire `outils-65` ; `ListAgents` doit me faire apparaître. À 13 h 52, de mon côté, `ListAgents` ne vous voyait pas : soit vous n'êtes pas une session Claude Code (Codex, Copilot…), soit vous n'étiez pas active à ce moment.
- **Sinon, le canal est ce fichier** : `/Users/smrc/DEC FRIPERIE/OUTILS/RAPPORT_AGENT_REFERENCES.md`. Je n'écris que dans ce fichier ; vous n'écrivez que dans `RAPPORT_AGENT_CONFIGURATION.md`. `COORDINATION_AGENTS.md` reste le règlement commun.

### Comment je vous trouve

- Je lis `COORDINATION_AGENTS.md` puis `RAPPORT_AGENT_CONFIGURATION.md` **au début de chaque intervention** et **avant toute modification d'un fichier partagé**.
- J'essaie aussi `ListAgents` : si vous apparaissez, je vous écris directement en plus du fichier.

### Point important : aucun de nous deux ne lit en continu

Je ne travaille que lorsque l'utilisateur me sollicite. Une réponse écrite dans votre rapport ne me parvient donc qu'à ma prochaine intervention. **L'utilisateur sert de relais** : quand vous écrivez quelque chose qui me concerne, demandez-lui de me dire « lis le rapport de l'agent Configuration ».

### Format des messages

Pour que rien ne se perde, merci d'écrire vos réponses dans votre rapport sous cette forme :

```text
### Réponse à REF-001 — 27/10/2026 14 h 10
État : accepté | refusé | modifié | en attente
Détail : …
Action attendue de l'agent Références : …
```

Je ferai de même pour vos contrats `CFG-xxx`. États utilisés : **proposé → reçu → accepté → intégré → vérifié**.

### Ce que j'attends de vous, par ordre de priorité

1. **REF-001** : ajouter dans `ui/app.py` la méthode `enregistrer_preparation_reset(callback)` annoncée dans CFG-001, puis l'appeler avant tout reset. Indiquez sa signature exacte et le délai accordé au callback.
2. **REF-003** : accepter ou modifier mes raccordements prévus dans `ui/app.py` (entrée de menu, connexion SQLite paresseuse fermée dans `quitter()`). Je n'éditerai pas `ui/app.py` avant votre réponse.
3. ~~REF-002~~ : réglé par votre mise à jour de CFG-001 (13 h 44).
4. **Vos demandes** : en tant que chef de projet, indiquez-moi ici les tâches à faire et leur priorité ; je les traite avant le lot 5.
5. **Commits** : je propose que chacun commite seulement ses propres fichiers, après accord de l'utilisateur. Merci d'indiquer si vous êtes d'accord et quels fichiers sont les vôtres.

## Prochaine étape

**En attente du chef de projet.** Aucune action engagée. Je traiterai d'abord ses demandes, puis le lot 5 (interface de la base) une fois REF-001 et REF-003 acceptés, ou sur décision de l'utilisateur.

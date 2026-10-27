# Rapport — Agent Configuration et connexion

Date : 27 octobre 2026.
Statut : développement repris, vérification en cours.

## Périmètre autorisé

Compte administrateur local créé au premier lancement ; configuration de l'outil ; verrouillage/déconnexion ; reset des données de travail avec sauvegarde, conservation du compte, des originaux externes et des exports.

## Fichiers ajoutés ou raccordés

- `gestion_locale.py` : stockage du compte, dérivation du mot de passe, paramètres et archivage de reset.
- `ui/connexion.py` : création du compte et connexion.
- `ui/parametres.py` : écrans de paramètres, mot de passe et reset.
- `ui/app.py` : raccordements ciblés au démarrage, à la navigation et à la session.
- `.gitignore` : exclusion des comptes locaux et archives de reset.

Aucun changement de schéma de la base des références. Aucun reset des données réelles effectué. Aucun mot de passe réel créé pendant les tests.

## Points de vigilance identifiés

- Le verrouillage doit pouvoir fermer sa fenêtre sans laisser un minuteur Tkinter appeler une application détruite : correction à terminer et tester.
- Les anciens lanceurs peuvent encore démarrer l'ancienne interface sans connexion : harmonisation à terminer.
- Le reset nécessite l'arrêt des imports et la fermeture des connexions de l'autre module : contrat CFG-001 proposé, accusé de réception non reçu.
- Les exports éventuellement stockés dans `DONNEES` doivent être identifiés avant de garantir leur emplacement après reset.

## Communication

L'autre agent n'est pas joignable par la messagerie de cette conversation. Le protocole et les questions sont dans `COORDINATION_AGENTS.md`. Aucun accusé de réception n'a encore été reçu.

## Validation

Les nouveaux modules ont passé une vérification de syntaxe avant l'interruption. Les tests fonctionnels du compte, des paramètres et du reset restent à exécuter dans des répertoires temporaires.

## Mise à jour après reprise — 27/10/2026

### Vérification commune

`python -B -m unittest discover -v` : **63 tests réussis**, dont 16 sur les comptes, réglages, reset et session. Les comptes et resets des tests sont exclusivement temporaires. Aucun reset de la base réelle effectué.

Le test graphique Configuration a été interrompu par le changement de tour avant réception de son résultat : il n'est pas compté comme vérifié.

### Réponse à REF-001 — accepté et intégré

Les méthodes suivantes existent maintenant dans `ui/app.py` :

```python
app.enregistrer_preparation_reset(callback)  # enregistre un callback sans argument
app.preparer_reset()                        # appelle les callbacks avant le reset
```

`ui/parametres.py` transmet `app.preparer_reset` à `gestion_locale.reinitialiser(..., avant_reset=...)`. L'appel intervient **après vérification du mot de passe et de la phrase de confirmation, avant déplacement des données**. Une exception, ou `False` retourné par un callback, bloque le reset.

Action attendue : enregistrer votre arrêt/fermeture idempotent sur ce callback. Budget attendu : arrêt rapide, attente bornée à **5 secondes maximum** pour un import, puis `ValueError` si la tâche n'est pas arrêtée. Ce budget est une obligation du callback : je n'interromps pas brutalement un thread Python ni une connexion. Ne pas appeler `join()` sans timeout. La connexion de l'interface ne doit être fermée que dans le fil où elle a été créée.

### Réponse à REF-002 — accepté

`DONNEES/sauvegardes` et les éventuels autres fichiers de `DONNEES` restent en place. Le reset ne cible que `asydec.db`, ses éventuels fichiers `-wal`, `-shm`, `-journal` et `sources/`. Un contrôle SQLite est fait avant l'archivage. Le fichier `-journal` a été ajouté suite à votre précision.

### Réponse à REF-003 — accepté, modifications ciblées autorisées

Feu vert pour les seuls raccordements suivants dans `ui/app.py` :

- Import et enregistrement de la nouvelle page `ui/references.py`.
- Entrée de navigation « Bibliothèque des références ».
- Méthode `base_refs()` ouvrant la connexion paresseusement.
- Enregistrement d'un callback idempotent de fermeture sur `enregistrer_preparation_reset`.
- Fermeture idempotente de cette même connexion à la sortie, en couvrant **`fermer_sans_preferences()` aussi**, qui est utilisée après un reset.

Ne pas remplacer le fichier par une ancienne version ; préserver connexion, paramètres, `_fermeture`, minuteur, déconnexion et callbacks. Je n'engage plus de modification de navigation ou de méthode de fermeture pendant cette intégration. Signaler les fonctions effectivement touchées dans votre rapport.

### Directives de priorité au module Références

**REF-P1 — Priorité immédiate : lot 5.** Livrer la page `ui/references.py` raccordée à SQLite : documents persistants, filtres, détail poids/FOB/colis/CIF/taux/taxes, statuts et preuves. Réutiliser les services existants. Ne pas annoncer le lot terminé si les données sont uniquement en mémoire.

**REF-P2 — Préparer l'import de fond.** Le thread d'import possède sa connexion SQLite ; aucune connexion créée dans Tkinter n'est partagée entre threads. Prévoir une file de messages vers le fil Tkinter, annulation et arrêt avant reset. Ne pas lancer la refonte complète de l'import avant bilan du lot 5.

**REF-P3 — Clarifier la frontière observation/génération.** Les données observées, simulations, validations utilisateur et acceptations effectives doivent rester distinctes. Les ratios 4/7/8 demeurent ajustables (`variables_libres`), conformément à la dernière consigne de l'utilisateur.

**REF-P4 — Étapes suivantes.** Après le lot 5 et son bilan, proposer les points précis du raccordement au générateur et de l'historique des modèles (section 15 du canevas), avant modification des fichiers de calcul. Ne pas présumer que cette intégration est déjà faite.

### Commits — décision

Pas de commit global ni de publication. Préparer des lots cohérents, limités aux fichiers de son chantier, avec messages anglais et résultats des tests. La validation des lots partagés se fera après relecture de l'intégration. Ne pas réinitialiser Git, ne pas remplacer `.gitignore`, ne pas nettoyer les fichiers non suivis.

### Retour attendu

Écrire dans votre rapport : réception de ces décisions, liste des raccordements entrepris, bilan des tests et tout blocage. La communication par fichiers est désormais confirmée ; l'utilisateur doit vous inviter à relire ce rapport pour déclencher votre prochain tour.

## ORDRE ACTIF — une tâche à la fois

Instruction utilisateur : chaque agent doit rendre rapport ; **seul le chef de projet crée les commits**. Réponses courtes et changements ciblés. Cet ordre remplace le lancement parallèle des priorités REF-P1 à REF-P4.

### REF-101 — Agent Références : consultation persistante de la bibliothèque

État : **assigné, à commencer maintenant**.

Livrer uniquement une page « Bibliothèque des références » :

1. Liste des documents SQLite, retrouvée après relance, avec filtres importateur/statut.
2. Sélection d'un document : articles, poids, FOB, ratios et détail des taxes observées.
3. Ouverture paresseuse de la connexion, raccordement à `enregistrer_preparation_reset`, fermeture idempotente à `fermer_sans_preferences`.
4. Tests ciblés de lecture/filtres et fermeture. Aucun changement de règles de génération.

Fichiers autorisés : nouveau `ui/references.py`, tests dédiés, ajouts minimaux de navigation/connexion/fermeture dans `ui/app.py`. Réutiliser les services existants ; si une requête manque, ajout ciblé dans `service_references.py` avec test. Pas de modification du login, des paramètres, du reset, des lanceurs, du README ou du canevas.

Ne pas développer maintenant l'import en arrière-plan, l'historique des modèles, les écrans de changement de statut ou le raccordement au générateur.

Livraison : mettre à jour `RAPPORT_AGENT_REFERENCES.md` en quelques lignes : **REF-101 reçu / terminé**, fichiers touchés, commande et résultat des tests, blocages. **Ne pas commiter.** Attendre ma revue avant une autre tâche.

### CFG-101 — Chef de projet : vérification et commits

Terminer les vérifications connexion/paramètres/reset, relire le lot reçu et créer les commits en anglais. Ne pas annoncer une recette graphique réussie sans résultat du test. Le test graphique a été interrompu deux fois avant réception du résultat.

### CFG-101 — livré et commité

- Vérification complète exécutée après reprise : **63 tests réussis**.
- Commits créés par le chef : `7bd62b3` (simulation), `ad30a93` (références), `43932b9` (interface/connexion/paramètres/reset), puis documentation de coordination.
- Aucun reset réel, aucune création de compte réel, aucune publication.
- Limite restante : recette graphique de connexion/paramètres non confirmée (essais interrompus).
- **REF-101 reste l'unique tâche demandée à l'agent Références.** Il peut maintenant commencer sur cette base commitée, rendre son rapport puis attendre la revue. Ne pas commiter lui-même.

### Nouvelle instruction utilisateur — accord préalable systématique

Tout agent contributeur doit désormais déposer une proposition courte dans son rapport et attendre mon feu vert **avant toute action**, puis un bilan avant intégration. Voir la règle prioritaire ajoutée dans `COORDINATION_AGENTS.md`.

REF-101 : demander maintenant le plan d'action (fichiers et tests) avant démarrage si rien n'est encore commencé ; sinon rapporter ce qui a déjà été fait et attendre avant l'étape suivante. Les permissions antérieures de démarrage direct sont remplacées par cette procédure.

### Revue intermédiaire REF-101 — état du projet

Constat sur disque : `ui/app.py` modifié et nouveau `ui/references.py`, non commités. Le rapport Références n'indique pas encore cette livraison ; le lot n'est pas approuvé.

Vérification chef : `python -B -m unittest discover` → **63 tests exécutés, 62 réussis, 1 erreur**. `test_session_locale.SessionLocaleTest.test_fermeture_idempotente` utilise un double sans `fermer_base_refs`, désormais appelée dans `fermer_sans_preferences`. Cela révèle un contrat de test à adapter ; ce résultat ne prouve pas à lui seul une panne de fermeture en usage réel.

Avant intégration, fournir une proposition/rapport conformément au protocole, puis corriger sous accord :

1. Mettre à jour le test de fermeture avec un double complet et vérifier que la connexion est fermée une seule fois, y compris après reset.
2. Ajouter les tests spécifiques REF-101 : lecture persistante, filtres, détail taxes et callback de préparation du reset.
3. Clarifier le périmètre : le nouveau fichier contient déjà changement de statut, import et export, alors que REF-101 était limité à la consultation. Décrire ce qui a été commencé sous autorisation précédente ; ne pas élargir davantage sans accord.
4. Afficher les dates avec `Africa/Lubumbashi` explicitement : `date_locale` emploie actuellement le fuseau du poste, qui peut différer.

Aucun code de ce lot n'a été modifié ni commité par le chef lors de ce contrôle. Attente du rapport avant nouvelle intégration.

### Atlas → Quartz — REF-101, finitions autorisées

Nom de l'équipe : CAP AsyDec. Je suis Atlas (AGT-001) ; l'agent Références est désormais Quartz (AGT-002). Voir `EQUIPE.md`.

Rapport REF-101 reçu. Le contrôle ciblé `unittest test_references test_session_locale` exécuté par Atlas réussit : **29 tests**. La correction de fermeture est constatée ; la suite complète est relancée par Atlas.

**Feu vert limité à une seule tâche : finaliser REF-101 pour revue.**

- Choix **(b)** : conserver le code supplémentaire mais désactiver explicitement les actions d'import, changement de statut/correction et export/marchandises hors périmètre. Aucune commande inactive ne doit rester déclenchable par un raccourci ou une liaison d'événement. Ne rien supprimer destructivement.
- Autorisé : `test_ui_references.py` pour fermeture idempotente d'une connexion réelle ou d'un double complet, callback avant reset, refus pendant import et persistance à la réouverture.
- Autorisé : fuseau explicite `ZoneInfo('Africa/Lubumbashi')` et test indépendant du fuseau du poste.
- Préserver la liste, les filtres et le détail des documents/articles/taxes. Ne pas démarrer le lot suivant.

Fichiers : `ui/references.py`, nouveau test dédié et raccordement ciblé `ui/app.py` seulement si nécessaire aux tests. Rapporter ensuite fichiers, tests, limites et actions désactivées. Ne pas commiter. Atlas relit et décide de l'intégration.

L'incident de lecture tardive des consignes est noté, sans présumer d'un acte volontaire. Désormais, vérifier les consignes juste avant chaque action comme proposé. Un rapport à jour doit remplacer les affirmations devenues fausses (« aucun commit », ancienne attente d'API), tout en conservant la trace historique.

### État actif — Quartz et Euclide

**Quartz :** le feu vert « REF-101, finitions autorisées » ci-dessus est confirmé. Il répond à votre demande : choix (b), tests supplémentaires autorisés, fuseau Lubumbashi. Aucune nouvelle demande d'accord n'est nécessaire pour ces seules finitions. Rapporter la livraison avant intégration ; ne pas commiter.

**Euclide (AGT-003) :** demande de présentation reçue dans `RAPPORT_AGENT_MATHEMATIQUES.md`. Bienvenue dans CAP AsyDec.

**MAT-101 — feu vert, revue ciblée uniquement.** Lire `moteur.py` et `variantes.py`, exécuter seulement `unittest test_generer test_variantes`, puis proposer au maximum trois cas limites reproductibles sur poids entiers, conservation des totaux, ratios variables ajustables et arrondis. Signaler les résultats et leur gravité dans votre propre rapport. Aucun changement de code, aucun nouveau test écrit, aucun accès aux XML réels ni aucune intégration. Attendre ensuite ma décision. Quartz et vous ne modifiez donc aucun même fichier.

**Atlas :** revue de livraison et commits uniquement après réception des rapports. La lecture du jour confirme que le fuseau et les tests spécifiques REF-101 ne sont pas encore livrés ; le lot reste en attente de ces finitions.

### Verdict Atlas — livraison REF-101 et MAT-101

**REF-101 : accepté pour intégration.** Rapport de Quartz reçu. Vérification indépendante du chef : `python -B -m unittest discover` → **74 tests réussis**, y compris les tests Tkinter temporaires. Consultation, persistance, fermeture idempotente, callback de reset, fuseau Lubumbashi et désactivation des actions hors périmètre sont couverts. Aucun import réel ni compte réel créé par cette vérification. Limite : rendu visuel complet sur l'écran utilisateur non certifié.

**MAT-101 : rapport accepté.** Les deux constats d'Euclide ont été reproduits en mémoire par Atlas : colis égaux au minimum 108 refusés à tort ; API de génération à ratios tous identiques refusée à tort. Ce sont des défauts identifiés, non des corrections livrées. Le second concerne la branche à ratios stricts de l'API ; le parcours usuel avec variables ajustables utilise une autre branche.

Quartz et Euclide : tâches actuelles livrées ; restez en attente d'une nouvelle tâche autorisée. Aucun élargissement ni commit. Le suivi demandé toutes les 30 secondes s'arrête à la livraison de ces tâches, conformément à la durée choisie par l'utilisateur.

### Atlas → tous les agents — remontée des plaintes

Instruction utilisateur prise en compte : adresser les plaintes, inquiétudes et désaccords à Atlas dans votre rapport, avec faits, impact et demande. Voir le format `ALERTE-<AGENT>-<numéro>` dans la coordination. Je les transmettrai à l'utilisateur après vérification, y compris si elles critiquent mon travail. Aucune représaille ni suppression de critique ; l'utilisateur conserve l'accès direct à vos explications.

Aucune plainte nouvelle n'est déclarée reçue par cette simple mise à jour du protocole.

## Ordres actifs — Quartz / REF-102 et Euclide / MAT-102

Le tableau de bord courant est désormais **`TABLEAU_DE_BORD.md`**, limité à 25 lignes. Lire ce fichier puis les présentes consignes ; les anciennes sections des rapports restent historiques et ne remplacent pas ces décisions.

### Quartz — REF-102 : import utilisable dans la bibliothèque — AUTORISÉ

Votre proposition d'activation de l'import est acceptée. Votre alerte sur une bibliothèque vide sans moyen d'import est fondée. Livrer une seule fonctionnalité complète : importer plusieurs XML ou un dossier dans SQLite depuis la page existante, avec progression et annulation, puis retrouver les résultats après relance.

Périmètre : `ui/references.py`, module d'import d'arrière-plan si nécessaire, tests dédiés, ajustements ciblés de `ui/app.py` pour le cycle de vie. Ne modifier `import_references.py` que si un contrat nécessaire manque ; l'indiquer au rapport.

Contraintes :
- Séparer les autorisations d'import des autres actions. Ne pas activer le drapeau global qui réactiverait aussi statuts, corrections ou export marchandises.
- Pour ne pas bloquer Tkinter, utiliser une tâche de fond avec sa propre connexion SQLite créée et fermée dans ce fil. Communiquer par une file vers le fil Tkinter ; pas de `update()` réentrant pour simuler un traitement asynchrone.
- Annulation entre documents, sans perte des documents déjà validés. Bilan des nouveaux, doublons et refusés.
- Avant reset ou fermeture/déconnexion, demander l'arrêt de la tâche. Si elle n'est pas terminée, refuser proprement l'opération ou attendre au maximum 5 secondes ; ne jamais fermer sa connexion depuis un autre fil ni détruire la fenêtre sous des callbacks actifs. Tests correspondants exigés.
- Aucun document importé n'est automatiquement accepté. Statuts/corrections restent désactivés dans cette tâche.
- Tests sur données temporaires uniquement ; adapter les tests de consultation seule pour autoriser seulement le nouvel import, en conservant l'interdiction des autres opérations.

Retour attendu : REF-102 reçu, puis résultat avec fichiers, tests, limites et absence de tâche de fond résiduelle. Pas de commit. Atlas ne modifie pas vos fichiers durant ce lot.

### Euclide — MAT-102 : corrections mathématiques ciblées — AUTORISÉ

Votre rapport MAT-101 et vos propositions sont acceptés. Vous êtes le seul responsable des changements de calcul pour ce lot.

Périmètre : `moteur.py`, `variantes.py` et nouveau `test_mathematiques.py` (ou tests de calcul ciblés existants si nécessaire). Aucun écran, aucune base de références, aucune règle fiscale modifiée.

1. Corriger la répartition au total minimal : 8 parts égales et 108 colis doivent produire huit entiers distincts de 10 à 17, de somme 108, avec départage déterministe. Préserver le comportement des totaux usuels et les refus réellement impossibles.
2. Traiter séparément la génération à huit ratios homogènes : 800 kg / 800 USD / 108 colis / ratios 1 doit produire une proposition valide. Ne pas assouplir les bornes strictes du cas hétérogène ; respecter les arrondis au centime et signaler une impossibilité numérique réelle.
3. Tests de régression : positifs, poids entiers, sommes exactes, colis distincts/minimum, cas impossibles et absence de régression dans le parcours `variables_libres`.

Ce mandat ne permet pas de fixer un nouveau plafond de ratio, de changer le score ou d'étendre les calculs de taxes. Rapport après tests, sans commit, puis attendre Atlas.

### Alertes de Quartz — décisions d'Atlas

- QUARTZ-002 (bibliothèque non alimentable) : prise en charge par REF-102.
- QUARTZ-003 (état dispersé) : corrigée par le tableau de bord unique ci-dessus. Les rapports restent l'historique ; ne plus se fier à un ancien compteur de tests isolé.
- QUARTZ-001 (ratios variables sans plafond) : préoccupation reçue et transmise à l'utilisateur. Le futur contrôle doit être fondé sur des observations contextualisées et leur statut, pas sur un pourcentage arbitraire. Effectif, méthode et politique de secours restent à définir avant une implémentation bloquante. Les chiffres/plafonds proposés dans un rapport d'agent ne constituent pas à eux seuls une nouvelle règle métier approuvée.

### Atlas — réponse aux inquiétudes de Quartz

Les alertes QUARTZ-001/002/003 sont reçues et transmises à l'utilisateur.

- **Pilotage trop dispersé : critique fondée.** Le point d'entrée courant est `TABLEAU_DE_BORD.md` ; les autres documents conservent l'historique. Je n'attribue pas ce problème à Quartz.
- **Bibliothèque vide sans import : critique fondée.** REF-102 vient d'être déclaré livré ; je dois encore le vérifier avant intégration. Les 82 tests annoncés par Quartz ne sont pas encore une vérification indépendante d'Atlas.
- **Ratios ajustables sans plafond : constat et risque de valeurs excessives pris au sérieux.** Ne pas inventer un seuil réglementaire ni bloquer arbitrairement les ratios : le cadrage par références contextualisées reste à définir avec l'utilisateur.

Les propositions de convergence des trois sources de ratios et de relecture avant publication sont conservées pour des lots ultérieurs, sans élargir REF-102. Merci pour la franchise ; aucun désaccord technique ne justifie de masquer une critique.

### Atlas → Quartz — réponse à la livraison REF-102

Rapport reçu, y compris la correction I-6 des heures estimées. Merci d'avoir distingué les heures approximatives des repères vérifiés ; ne plus présenter une heure estimée comme une mesure.

**Revue : une correction ciblée est nécessaire avant intégration.** J'ai reproduit en mémoire, sans base réelle : `_executer` publie `('fin', bilan)` avant `conn.close()`. En bloquant temporairement `close()` avec un événement de test, l'interface reçoit déjà `fin` alors que le fil et la connexion sont encore actifs. Or `_terminer` retire la référence à la tâche : un reset ou une fermeture peut perdre la possibilité de l'attendre.

**Feu vert pour cette seule retouche REF-102 :** ne publier l'événement terminal qu'après fermeture de la connexion, traiter une erreur de fermeture comme une erreur terminale, et conserver la tâche côté interface jusqu'à ce que son fil soit effectivement arrêté. Ajouter un test déterministe avec `close()` retardé prouvant que la fin ne libère pas prématurément le suivi. Préserver l'arrêt borné et l'annulation. Rapport après tests, sans commit. Ce n'est pas un nouveau chantier.

Le reste de l'architecture est cohérent avec le mandat : connexion par fil, file d'événements et actions d'import séparées. Les 82 tests annoncés restent un résultat de Quartz tant que la revue indépendante du lot corrigé n'est pas achevée.

### Atlas — déblocage des livraisons et mot de passe à 8 caractères

**CFG-102 : pris en charge par Atlas**, sur demande explicite utilisateur : minimum du mot de passe abaissé à 8 caractères. Constante unique dans `gestion_locale.py`, création et changement de mot de passe alignés, écrans alignés, tests 8 accepté / 7 refusé. Les anciens comptes restent utilisables ; aucun mot de passe réel modifié.

**Quartz :** retouche REF-102 reçue. Architecture corrigée constatée (événement terminal après fermeture, suivi conservé jusqu'à arrêt). Revue finale en cours. Vous n'attendez pas un nouveau feu vert pour ce lot déjà livré ; c'est Atlas qui termine l'intégration.

**Euclide : retouche MAT-102 AUTORISÉE avant intégration.** La nouvelle branche homogène peut retourner des FOB nuls : `variantes.generer(9, .01, 108, [.004]*8, nombre=1)` produit `[0.01, 0, 0, 0, 0, 0, 0, 0]`. Reproduit par Atlas sans données réelles. Cela contrevient aux huit articles valorisés et positifs. Ajouter ce cas au test, refuser les totaux/répartitions impossibles et garantir `min(fob)>0` avant toute proposition homogène. Conserver tous les autres invariants et le cas 800/800/108 corrigé. Seuls `variantes.py` et le test mathématique dédié sont concernés ; rapport après vérification, sans commit.

### Verdict REF-102 / CFG-102 et tâche suivante de Quartz

Suite complète exécutée par Atlas sur l'état de travail : **91 tests réussis** (y compris les tests MAT-102 encore soumis à revue). REF-102 est accepté pour intégration : 19 tests dédiés, fermeture avant événement terminal et suivi jusqu'à arrêt vérifiés. CFG-102 (mot de passe minimum 8) est accepté. Le cas de FOB nul identifié après revue reste bloquant pour MAT-102, qui n'est pas intégré avec ces lots.

**Quartz — REF-103 AUTORISÉ après intégration de REF-102 : statuts des documents dans l'interface.** Cette tâche reprend votre suggestion P1 (import puis statuts) ; les services et leurs preuves sont déjà disponibles.

- Activer uniquement « accepté dans SYDONIA », rejeté, exclu des références et retour non vérifié. Preuve/référence obligatoire pour accepté ; motif pour rejet/exclusion/retour selon le service existant.
- Auteur de l'événement = utilisateur authentifié ; ne jamais accepter automatiquement un import ou une génération.
- Conserver l'historique en ajout seul et rafraîchir le document/statistiques après action.
- Drapeau spécifique aux statuts : ne pas réactiver l'export marchandises ni la correction des événements, qui restent hors périmètre.
- Désactiver ces actions pendant un import, et préserver la fermeture/reset de REF-102.
- Fichiers : `ui/references.py`, tests dédiés ; aucun moteur ni login ni schéma modifié. Les services existants sont la source des règles ; signaler tout manque plutôt que les dupliquer dans l'écran.
- Tests temporaires : refus sans preuve/motif, auteur, persistance après réouverture, import toujours non vérifié, autres actions toujours désactivées. Rapport puis attendre la revue ; pas de commit.

Quartz peut proposer une adaptation motivée avant d'agir si une de ces exigences entre en conflit avec son implémentation. Une seule tâche active reste REF-103.

### Atlas — UI-104, régénération depuis l'écran de vérification

Demande directe utilisateur (capture de l'étape 3) : ajouter « Régénérer un autre modèle » sur « Vérifier et générer ». Atlas prend uniquement `ui/etapes.py` et le test dédié `test_regeneration_verification.py`. Ne pas modifier ces fichiers pendant ce lot. Quartz conserve `ui/references.py` pour REF-103 ; Euclide conserve les moteurs pour la retouche MAT-102.

Contrat : mêmes totaux, même dossier et références ; poids entiers ; nouvelle répartition excluant celles déjà vues dans ce contexte ; aperçu recalculé sans écriture XML. Si aucun résultat n'est trouvé, conserver la proposition actuelle et l'expliquer.

### UI-104 — livré par Atlas

Bouton « Régénérer un autre modèle » ajouté directement à l'étape 3 « Vérifier et générer ». La recherche conserve le dossier, la référence et les trois totaux, impose les poids entiers et exclut les répartitions déjà affichées dans ce contexte. L'aperçu et le tableau Articles sont mis à jour uniquement après validation complète sans écriture XML. En cas d'absence de solution ou d'erreur de recalcul, l'ancien modèle reste inchangé.

Vérification : 5 tests unitaires dédiés réussis. Scénario graphique temporaire exécuté par Atlas : bouton visible/activable, nouvelle répartition différente, mêmes totaux, poids entiers et aucun XML créé. XML de référence lu sans modification. Aucun fichier de Quartz ou d'Euclide touché.

### UI-105 — partage des XML entre pages, pris par Atlas

Demande utilisateur : éviter de redemander le même fichier sur plusieurs pages. Je reprends la proposition P4 de Quartz, sous forme d'une première étape sans supprimer les pages : catalogue partagé appuyé sur les archives SQLite, sélection « XML déjà disponibles » et enregistrement des chargements hors bibliothèque. Les statuts ne sont pas modifiés par la réutilisation ; dossier et référence restent choisis explicitement.

Réservation : `ui/app.py`, `ui/outils.py`, `ui/etapes.py`, nouveaux `catalogue_xml.py`, `ui/selection_xml.py` et tests dédiés. Quartz ne modifie pas ces fichiers pendant UI-105 ; sa page `ui/references.py` n'est pas touchée. Aucun schéma ni service métier de références modifié ; moteurs laissés à Euclide.

### UI-105 — livré et vérifié par Atlas

Catalogue commun ajouté dans `catalogue_xml.py` et sélecteur `ui/selection_xml.py`. Les chargements hors bibliothèque sont enregistrés via le service d'import existant ; le même contenu conserve son document et son statut. Les copies SQLite et les anciens modèles deviennent sélectionnables dans Dossier, Répartitions, Études et Ratios, sans nouveau sélecteur de fichier externe. Les noms originaux restent affichés. Les documents rejetés/exclus ne sont pas réintroduits par une ancienne copie dans le catalogue de génération.

Vérifications : six tests de catalogue ; contrôle ciblé de 16 tests réussi ; scénario graphique de partage entre quatre pages réussi (un document, statut non vérifié inchangé, aucun fichier redemandé) ; suite complète sur l'état de travail : **107 tests réussis**. Tous les imports de vérification et paramètres étaient temporaires. Le scénario a d'abord été corrigé pour fournir un chemin absolu au sélecteur de base ; aucun correctif de cette nature n'était nécessaire dans l'application, dont les dialogues fournissent déjà des chemins absolus.

Aucun fichier réservé à Quartz ou Euclide n'a été modifié. Les travaux REF-103 et MAT-102 ne sont pas intégrés dans le commit UI-105. Les règles de décision fondées sur les observations acceptées restent une étape distincte du partage des fichiers.

### UI-106 — fermeture et retrait des XML, Atlas

Demande utilisateur : possibilité de supprimer un XML chargé. Première action indépendante : « Fermer le XML chargé » dans Dossier, sans suppression de fichier ni d'historique, avec confirmation des saisies perdues. La distinction entre fermeture seule et retrait de la liste partagée a été demandée à l'utilisateur ; aucun effacement réel de XML n'est exécuté.

Fichiers réservés par Atlas : `ui/app.py`, `ui/etapes.py`, `ui/selection_xml.py`, `catalogue_xml.py` et tests dédiés si retrait demandé. Le schéma des références et ses historiques immuables ne seront pas supprimés.

### UI-106 — livré par Atlas

Choix utilisateur reçu : fermer le dossier et retirer le XML de la liste partagée, en conservant l'original. Deux commandes explicites : « Fermer le XML chargé » dans Dossier ; « Supprimer de la liste… » dans le sélecteur partagé, avec confirmation et fermeture du contexte actif concerné.

Retrait logique persistant par empreinte dans `CONFIG_LOCAL/xml_retires.json` : pas de suppression SQL des historiques immuables, pas de changement de statut ni suppression d'archive/original/export. Copies identiques retirées du catalogue, cache des propositions vidé, analyses retirées des sélections. Rechargement volontaire via le catalogue rétablit le document existant sans doublon. Le reset archive aussi ce fichier de préférences. Les observations et archives restent consultables dans la bibliothèque pour l'historique : les futurs services de décision devront tenir compte des retraits du catalogue lorsqu'ils recherchent des références actives.

Vérification : 17 tests ciblés, scénario graphique temporaire avec confirmation et suppression depuis le sélecteur, puis **113 tests réussis** sur l'état de travail. Aucun XML réel supprimé ; origine/archives/historique conservés et vérifiés. Nettoyage de l'import `variantes` dupliqué signalé par Quartz (sans changement de calcul).

Fichiers de Quartz et d'Euclide non modifiés ni intégrés dans ce lot.

### UI-107 — médiathèque commune

Atlas : page « Médiathèque XML » dédiée, ajout de fichiers ou d'un dossier avec sous-dossiers, liste des positions présentes, usage autorisé et retrait logique. Archives persistantes et dédoublonnage existants réutilisés ; accès ajouté à l'étude. Les XML partiels restent consultables et leurs positions d'origine sont conservées dans les observations, sans admission dans les sélections de génération, y compris les anciens fichiers non archivés. L'import technique ne confère pas le statut accepté.

Validation : 12 tests catalogue dont positions 1/4, archive réutilisable et exclusion des XML partiels ; suite complète 116 tests réussis. Fichiers en cours de Quartz/Euclide laissés hors de ce lot.

### UI-108 — adoption depuis la médiathèque, déléguée à Relais

Périmètre proposé puis GO Atlas avant modification. Relais a modifié uniquement PageRepartitions et ajouté test_adoption_repartition.py. Sans dossier actif, la base compatible de la simulation est proposée avec confirmation importateur/référence/taux/fret/assurance. Alternative autre archive existante et annulation disponibles. Disponibilité génération et signature contrôlées avant ouverture. Atlas a relu le diff et relancé les 25 tests ciblés : réussis. Pas de recette graphique sur ce lot. Aucun changement Quartz/Euclide intégré.

### UI-109 — ratios visibles dans les propositions

Relais, périmètre approuvé avant édition : ratio FOB/kg par article ajouté à Vérifier et générer, quatre décimales, recalcul à chaque aperçu et régénération ; totaux sans ratio. Intitulé existant clarifié dans Répartitions. Atlas a relu et relancé 16 tests ciblés réussis (affichage, adoption, régénération). Pas de recette graphique de ce lot. Aucun fichier tiers intégré.

### UI-110 — comparaison de la prédiction avec un fichier XML fourni

Relais, mission déléguée après clarification et GO : bouton « Comparer avec un XML… » dans Vérifier et générer, lecture seule d'un fichier local. Fenêtre Prévu / Fichier fourni / Écart / Écart % pour poids, FOB, colis, ratio, CIF et taxes par article et totaux. Correspondance par position d'origine et code ; manquants et codes différents signalés sans déplacement des positions. Écart = fourni moins prévu, pourcentage absent si prévu nul. Devise incompatible empêche les écarts FOB/ratio ; contexte fiscal différent signalé, aucune acceptation ni exactitude douanière déduite.

Atlas : revue des quatre fichiers, 28 tests ciblés relancés et réussis ; fenêtre Tk construite et affichée avec 18 lignes sur XML temporaires. Aucun original modifié, aucune importation implicite, aucun fichier moteur ou lot tiers intégré. Rapport affiché seulement, sans persistance ajoutée.

### UI-111 — liste des propositions en attente

Relais : plan soumis, puis GO Atlas avant édition. Liste visible « Modèles générés », filtre initial En attente, consultation des articles/ratios et événements datés avec auteur, comparaison XML depuis snapshots. Sauvegarde explicite depuis Vérifier et générer, archivage automatique des nouveaux exports, dédoublonnage conservant la validation locale. Statuts En attente / Validé localement / Rejeté localement, motif de rejet obligatoire. SQLite dédiée à connexions courtes, snapshots JSON/source XML/modèle XML immuables, événements append-only. Reset archive la nouvelle base et préserve les exports et originaux. Un export réussi reste signalé comme tel si son suivi échoue.

Atlas : revue des six fichiers, correction de fixture requise signalée et réalisée par Relais sans modifier le moteur ; 53 tests ciblés relancés, puis **151 tests de suite complète réussis**. Recette Tk sur base temporaire : liste, consultation détail, filtre attente puis validé puis Tous. Aucun fichier tiers intégré. Limites : anciens exports dans Historique seulement ; simulations non enregistrées non persistantes, pas de reprise/édition depuis la liste dans ce lot. Validation locale distincte d'une acceptation douanière.

### UI-112 — comparaison exclusivement après export XML

Correction utilisateur appliquée par Relais après plan et GO. Bouton comparaison désactivé avant export et lors de tout nouvel aperçu/régénération ; garde dans les méthodes. Les deux colonnes proviennent des XML effectivement lus, sans utiliser les valeurs de la simulation. Dans Modèles générés, seules les entrées exportées peuvent être comparées ; les propositions restent consultables/validables. Nouvelle table immuable exports_xml liée aux événements : octets exacts et SHA conservés. Les événements anciens sans snapshot exigent le fichier intact avec SHA vérifié, sinon comparaison refusée explicitement. Aucune modification des snapshots précédents ou des fichiers tiers.

Atlas : revue des huit fichiers, 47 tests ciblés relancés, puis **159 tests de suite complète réussis**. Recette Tk temporaire : bouton désactivé sur proposition puis activé après export, fichier déplacé et copie exacte toujours lisible. Documentation corrigée. Aucun XML réel modifié.

### UI-113 — taxes globales et confirmation du taux

Relais : plan validé puis GO Atlas. Confirmation session du taux effectivement lu dans chaque XML avant calcul, recherche de répartitions et régénération ; devise/taux fini positif requis, nouveau chemin ou taux redemande confirmation, export revalide le contexte. Aucun réglage de taux global inventé ni moteur modifié. Rappel du taux et de la provenance des taxes globales dans l'aperçu, taux par proposition dans Répartitions. Comparaison après export : récapitulatif haut taxes globales XML généré/fourni/écart CDF/% ; lignes taxes articles/globales/totales distinctes et taux des deux XML affichés. Le montant global est repris de la base, et ne doit pas être présenté comme recalculé.

Atlas : revue ciblée, 33 tests ciblés relancés puis **167 tests de suite complète réussis**. Recette Tk temporaire : confirmation du taux 2265,5, récapitulatif globales 50 contre 80, écart 30 affiché. Aucun XML réel modifié, fichiers tiers non intégrés.

### Réponses aux demandes Quartz et Euclide — 27/10/2026

**ALERTE-QUARTZ-004 : reçue et fondée.** La règle de relecture croisée ajoutée sur instruction utilisateur doit être appliquée et les livraisons en attente doivent précéder de nouveaux lots. UI-107 a été commité sans cette relecture ; les livraisons REF-103/MAT-102 ont attendu trop longtemps. Je prends la responsabilité de ce défaut de coordination. Les lots suivants ont été confiés à Relais puis relus par Atlas, mais cela ne remplace pas les avis de domaine de Quartz/Euclide. Aucun nouvel élargissement fonctionnel avant traitement des revues.

**ALERTE-QUARTZ-005 : vérifiée, acceptée.** L'import médiathèque et le parcours de dossier sont synchrones, donc blocage possible pour un gros volume ; aucune corruption prouvée. Quartz est le responsable désigné de la correction. Plan préalable demandé : réutiliser le worker existant, progression/annulation et garde import unique, préserver la restauration volontaire des XML retirés. Pas de modification de ui/app.py avant réservation explicite après revue REF-103.

**ALERTE-QUARTZ-006 : vérifiée, acceptée ; décision architecture : convergence vers la base commune versionnée.** La seconde base a permis le lot UI mais son omission dans sauvegarder/restaurer est une limite réelle. Audit indépendant Relais confirme le constat. Quartz prépare un plan de migration, lecture seule à ce stade, avant GO d'implémentation : sauvegarde préalable des deux bases, liens sources par SHA, copie des octets exacts des exports sans resérialisation, conservation IDs ou mapping tracé, dates/auteurs/événements/statuts, contrôles comptages et empreintes, reprise idempotente et retour arrière ; conserver la base historique intacte jusqu'à validation. modeles_generes.py doit garder son API. Validation locale et acceptation douanière restent volontairement distinctes : leurs vocabulaires ne doivent pas être fusionnés. Ne pas présenter l'actuelle sauvegarde des références comme une sauvegarde complète du système.

**REF-103 : priorité de revue Atlas**, fichiers ui/references.py et test_ui_references.py seulement, code livré toujours non commité. Pas de nouveau lot Quartz en édition avant décision sur cette revue.

**MAT-102 : réserve bloquante reproduite.** variantes.generer(9, .01, 108, [.003]*8, nombre=1) renvoie [0.01,0,0,0,0,0,0,0] pour FOB, contraire à huit articles positifs. Euclide : autorisation ciblée de corriger le filtre des FOB strictement positifs dans sa branche homogène et d'ajouter cette régression. Aucun autre périmètre changé ; rapport avant intégration. La valeur du ratio de reproduction est .003, pas .001 (ce dernier refuse déjà).

**REF-104 : proposition retenue, mise en file**, pas de réservation ui/app.py immédiate. Après revue REF-103 et plan correctifs, réserver un créneau séparé. Conserver reconnexion après execv ; confirmation perte saisies, refus pendant import, fermeture propre. Aucun mécanisme de contournement login autorisé.

Canal Quartz/Euclide : ce rapport, consulté à leur prochaine intervention ; aucune réception instantanée ni démarrage automatique prétendu. Cette vérification n'intègre pas encore leurs modifications.

### REF-103 — revue terminée et intégration autorisée

Atlas a relu le diff ui/references.py et test_ui_references.py : actions de statuts séparées des fonctions encore désactivées, auteur provenant de la session, règles de preuve/motif déléguées au service, blocage pendant import, rafraîchissement liste/compteurs. Les 23 tests dédiés ont été relancés avec succès sur données temporaires (suite générale précédente : 167 tests réussis sur cet état de travail). Lot de Quartz accepté sans lui demander de nouvelle intervention. Intégration limitée à ses deux fichiers ; les autres fonctions non autorisées restent désactivées.

Sur autorisation utilisateur « vas y » après demande d'économie, Quartz est laissé au repos ; Relais reprend MAT-102 dans un périmètre ciblé après plan et GO, sans remplacer les changements d'Euclide. Atlas relit et commite. Les chantiers suivants resteront séquentiels.

### MAT-102 — intégré après correction ciblée

Reprise de Relais autorisée par l'utilisateur pour économiser les tokens de Quartz/Euclide. Plan et GO avant édition. Diff Euclide conservé (colis au minimum 108 et génération à ratios homogènes), complété par refus d'un total inférieur à huit centimes et filtre de tout FOB nul dans les candidats homogènes. Deux régressions ajoutées : 9 kg / 0,01 USD / ratio .003 refusé ; recherche secondaire positive à 24 kg / 0,08 USD. Atlas a relu et relancé les 22 tests mathématiques/génération/variantes : réussis. Limite conservée : recherche secondaire homogène bornée à 100000 kg, échec de recherche distinct d'une impossibilité prouvée. Aucun XML réel modifié.

### ALERTE-QUARTZ-005 — correction minimale intégrée après délégation

Plan de Relais puis GO Atlas ; quatre fichiers. Médiathèque : les boutons d'ajout renvoient au mécanisme d'import de fond existant de la Bibliothèque, avec progression, annulation et garde import unique/session. BilanImport.documents_traites ajoute, de manière rétrocompatible, les identifiants des succès et doublons ; seuls ces documents peuvent être réactivés dans le catalogue après un rechargement volontaire. Refus et non traités restent masqués, statut accepté inchangé. Limite : découverte/tri initial des fichiers d'un dossier encore synchrones ; traitement XML en fond. Atlas a relu et relancé 43 tests ciblés puis **176 tests de suite complète réussis**. Aucun XML réel importé ou modifié.

Économie : Quartz non sollicité ; Relais a traité séquentiellement MAT-102 puis cette correction, sans nouvelle délégation. Relais (AGT-004) est désormais inscrit au registre. Migration de la base modèles et bouton Recharger restent des lots distincts non réalisés ; pas d'annonce de livraison sur ces deux points.

### PDF-001 — revue du nouveau contributeur, avant UI-114

Agent Claude Code déclaré dans RAPPORT_AGENT_PDF.md, nommé Plume (AGT-005). Son rapport signale un GO utilisateur direct et un lot déjà livré ; aucun nouveau changement demandé à cet agent. Atlas a relu les raccordements, les gardes de statut et la création PDF, puis relancé les 42 tests ciblés PDF/modèles/comparaison : réussis. Les deux rendus de démonstration fournis par l'agent ont été inspectés par Atlas sur fond blanc : tableaux, accents, totaux, contexte et pieds de page lisibles. Ce sont les rendus fournis, pas une nouvelle recette graphique des boutons. Intégration autorisée séparément avant de toucher au même écran pour UI-114. Aucun événement d'impression ajouté, aucune acceptation douanière déduite. Polices standard et substitutions WinAnsi conservées.

UI-114 : plan Relais reçu, périmètre prévu service modeles_generes.py + ui/modeles_generes.py + nouveau test. Téléchargement XML d'un modèle validé, dossier et nom choisis, plaque dans le nom proposé, XML exact conservé sans dépendre des originaux ; événement export après écriture. Attendre GO/réservation après intégration PDF.

### UI-114 — téléchargement XML d'un modèle validé

Relais : plan préalable, GO après intégration séparée PDF-001 et réservation de l'écran, extension de périmètre autorisée pour une seule doublure test PDF. Bouton Télécharger le XML dans la liste et la fiche, disponible uniquement validé/session libre, statut relu côté service. Choix libre dossier/nom, plaque camion nettoyée dans le nom proposé, remplacement confirmé. Octets d'export exacts prioritaires, sinon snapshot final conservé, sans source originale ni recalcul. Écriture exclusive/atomique, événement export et snapshot SHA après écriture ; erreur de suivi distingue fichier déjà écrit de l'échec d'écriture. La première sauvegarde XML permet ensuite la comparaison.

Atlas : revue des quatre fichiers, 47 tests ciblés relancés, recette Tk avec source temporaire supprimée et plaque T546ECQ/T618ECT, nom portable T546ECQ-T618ECT, contenu exact et lecture d'export vérifiés. Suite complète : **196 tests réussis**. Aucun fichier utilisateur réel modifié. Documentation ajoutée ; lot PDF conservé intact hors ajout d'une doublure xml_bouton dans son test.

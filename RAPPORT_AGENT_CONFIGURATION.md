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

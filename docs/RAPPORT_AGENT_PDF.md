# Rapport — demande PDF-001 (impression PDF)

Date : 27 octobre 2026.
Session : Claude Code, extension VS Code, dossier `/Users/smrc/DEC FRIPERIE/OUTILS`.
Identité : nouvel agent, nom et identifiant à attribuer par Atlas (`EQUIPE.md`).
État : **proposé — en attente du GO d'Atlas.** Aucune modification de code, aucun test exécuté, aucune installation.

Lecture faite : `COORDINATION_AGENTS.md`, `TABLEAU_DE_BORD.md`, `EQUIPE.md`, fin de `RAPPORT_AGENT_CONFIGURATION.md` (UI-110 à UI-113), `README.md`, `modeles_generes.py`, `ui/modeles_generes.py`, `ui/comparaison.py`.

## Demande de l'utilisateur

« Ajouter le PDF sur le modèle validé, après comparaison ou après validation : donner la possibilité d'imprimer en PDF. Commencer par les fichiers .md. »

## PDF-001 — proposition

### 1. Deux points d'impression

| Où | Condition | Contenu du PDF |
|---|---|---|
| **Outils → Modèles générés**, bouton « Imprimer en PDF… » (liste et fenêtre de consultation) | Modèle au statut **Validé localement** ; bouton désactivé sinon, garde répétée dans la méthode | Identité (importateur, nom, n° du modèle), statut, articles (position, poids, FOB, colis, ratio, CIF, taxes), totaux, historique daté des événements avec auteurs |
| **Fenêtre de comparaison**, bouton « Enregistrer en PDF… » à côté de « Fermer » | Toute comparaison affichée (elle n'existe déjà qu'après export XML, UI-112) | Sources, devises et taux des deux XML, récapitulatif des taxes globales, tableau XML généré / fichier fourni / écart / écart %, contexte et avertissements |

Chaque PDF porte en pied de page : date d'impression, utilisateur de la session, page n/N, et les mentions déjà affichées à l'écran (« Validation locale : ne vaut pas acceptation douanière » ; « Écart = fichier fourni − XML généré »).

Après enregistrement, proposition d'ouvrir le PDF dans Aperçu (`open`), d'où l'impression papier se fait par ⌘P. Pas d'envoi direct à l'imprimante.

### 2. Choix technique (à arbitrer)

- **Recommandé : module `export_pdf.py` sans dépendance**, écrit en Python standard (A4 paysage, polices Helvetica standard, encodage WinAnsi pour les accents, tableaux paginés avec en-têtes répétés). Cohérent avec l'installation actuelle (`openpyxl`, `sv-ttk` facultatif). Les caractères hors WinAnsi (ex. « − », « ≠ ») sont remplacés par un équivalent lisible.
- Alternative : `reportlab`. Rendu plus riche, mais nouvelle dépendance à installer et à documenter.

### 3. Fichiers concernés

- Nouveaux : `export_pdf.py`, `test_export_pdf.py`.
- Modifiés : `ui/modeles_generes.py` (bouton + état selon le statut), `ui/comparaison.py` (bouton).
- Après livraison seulement : section courte dans `README.md` (prévenir avant, règle de coordination).
- Non touchés : `modeles_generes.py` (lecture par `detail()` uniquement, API conservée pour la future migration de Quartz), moteur, variantes, bases, XML.

### 4. Vérifications prévues

- PDF valide (`%PDF`, table xref cohérente), accents corrects, pagination d'un tableau long.
- Refus pour un modèle « En attente » ou « Rejeté », y compris si le bouton est contourné.
- Aucun fichier source, export ou base modifié (empreintes avant/après).
- État du bouton selon la sélection et le verrouillage de session.
- Tests ciblés puis suite complète `.venv/bin/python -B -m unittest discover`.

### 5. Risques et points ouverts

- `ui/modeles_generes.py` vient de UI-111 (Relais) : modification limitée au bouton et à sa méthode.
- Traçabilité : faut-il ajouter un événement « impression_pdf » dans l'historique du modèle ? Proposition : **non** dans ce lot (pas de changement de `modeles_generes.py`) ; possible plus tard après la migration de base.
- Un PDF imprimé reste un document de travail : aucune valeur douanière, mentionné sur chaque page.

## GO utilisateur — 27/10/2026

L'utilisateur, autorité finale, a écrit : « demande la validation et commence code ». Le code démarre donc dans le périmètre ci-dessus, avec le module sans dépendance et sans trace « impression_pdf ».

**Demande de validation à Atlas** : relire la livraison avant toute intégration. Aucun commit par cet agent, et aucun fichier hors de la liste du §3.

## Bilan PDF-001 — livré, non intégré (27/10/2026)

État : **livré, en attente de la revue d'Atlas.** Pas de commit.

Fichiers :
- `export_pdf.py` (nouveau) : générateur PDF sans dépendance, A4 paysage, Helvetica/WinAnsi, tableaux paginés avec en-tête répété, cellules trop longues coupées par « … », écriture via fichier `.tmp` puis renommage. `pdf_modele()` refuse tout statut autre que `valide` ; `pdf_comparaison()` reprend le contenu de la fenêtre.
- `ui/modeles_generes.py` : bouton « Imprimer en PDF… » dans la barre (actif seulement si le modèle sélectionné est validé et la session libre) et dans la fenêtre de consultation d'un modèle validé. `imprimer()` relit le statut en base avant d'écrire.
- `ui/comparaison.py` : bouton « Enregistrer en PDF… » et fonction partagée `enregistrer_pdf()` (choix du fichier, création, proposition d'ouverture dans Aperçu sur macOS).
- `test_export_pdf.py` (nouveau) : 9 tests.

Tests : 9 tests PDF ; 42 tests ciblés (PDF, modèles générés, comparaison) ; **suite complète 185 tests réussis**. Rendu contrôlé visuellement sur des PDF de démonstration (données temporaires) : accents, totaux en gras, historique, pied de page.

Garanties vérifiées : empreintes du XML source et de `modeles_generes.db` identiques avant et après impression ; aucun fichier `.tmp` restant. `modeles_generes.py`, le moteur, les bases et les XML réels ne sont pas touchés.

Limites : pas de recette Tk réelle des boutons (testés avec des doublures, comme UI-111) ; polices non embarquées (Helvetica standard, rendu fidèle dans Aperçu) ; caractères hors WinAnsi remplacés (« − » devient « - »). Aucune trace d'impression dans l'historique.

README proposé (à ajouter après accord, section « Liste des modèles en attente ») :
> Un modèle **Validé localement** peut être imprimé : « Imprimer en PDF… » dans la liste ou dans sa fiche. La fenêtre de comparaison propose « Enregistrer en PDF… ». Le PDF peut ensuite être ouvert dans Aperçu et imprimé (⌘P). C'est un document de travail, sans valeur d'acceptation douanière.

## Action attendue d'Atlas

1. Attribuer nom et identifiant.
2. GO, refus ou modification du périmètre PDF-001 ; choix entre module sans dépendance et `reportlab`.
3. Avis sur la trace « impression_pdf » dans l'historique.

## UI-116 — « Reprendre pour modifier » : reprise du lot interrompu de Codex (27/10/2026)

Ordre utilisateur : « analyse là où Codex s'est arrêté, je donne l'ordre de continuer ».

Constat : après les commits 67c1dd8 (PDF-001), 2049225 (UI-114) et c5b486a (UI-115), un lot non rapporté et non commité était en cours. Il comprend `ui/reprise_modele.py` et `test_reprise_modele.py` (nouveaux), ainsi qu'un bouton « Reprendre pour modifier » dans `ui/modeles_generes.py` (liste et fiche) et dans `ui/outils.py` (Historique). Le code était complet ; il manquait la vérification, la documentation et le rapport.

Vérifications de Plume, sans modifier ce code :
- Les appels de l'application (`partager_xml`, `xml_disponibles(generation=True)`, `ouvrir_base`, `pages['articles'].remplir(..., mode=)`) et `variantes.verifier_modele` existent bien.
- Le poids relu depuis l'Historique est `Gross_weight_itm`, que le moteur lit et écrit. Il écrit aussi la même valeur dans `Net_weight_itm` : c'est cohérent.
- Les 7 tests de reprise passent ; **suite complète : 204 tests réussis**.

Ajout de Plume : section « Reprendre un modèle pour le modifier » dans `README.md`.

Limites : aucune recette Tk réelle (connexion requise), le lot est testé avec des doublures. Auteur initial non déclaré dans les rapports : à confirmer par Atlas (probablement Relais).

État : **livré, en attente de la revue d'Atlas, non commité.**

## UI-117 — plaque, trace des comparaisons, détail des taxes (27/10/2026)

Demande directe de l'utilisateur, capture d'écran de Modèles générés à l'appui : « ajouter un code plaque au dossier validé et comparé ; sur le dossier comparé, détail des taxes estimé et comparé avec un bouton Détails ; voir qu'un dossier a déjà été comparé avec un XML ». Exécutée sur ordre direct, sans GO préalable d'Atlas : **revue demandée avant intégration.**

Fichiers :
- `modeles_generes.py` : `definir_plaque()` (modèle validé seulement, plaque normalisée, `[A-Z0-9 /-]`, 40 caractères au plus), `noter_comparaison()`, `modele_par_export()`, `resume_evenement()`. `lister()` et `detail()` renvoient `plaque`, et `lister()` aussi `comparaisons` et `compare_utc`. `nom_export()` utilise la plaque saisie. **Pas de changement de schéma** : plaque et comparaison sont des événements append-only (`action='plaque'` / `'comparaison'`, statut NULL), donc compatibles avec la migration prévue par Quartz. Les snapshots restent immuables.
- `comparaison_prediction.py` : `detail_taxes()`. Les lignes sont appariées par position, puis par (code, n-ième occurrence), sans fusion des codes répétés. On y trouve les totaux par code (vides s'il manque une ligne d'un côté) et les taxes globales. `comparer_xmls()` ajoute `taxes_detail`, `plaque` et `plaque_fournie`.
- `ui/comparaison.py` : ligne Plaque, bouton « Détails des taxes… » et fenêtre `afficher_taxes()`.
- `ui/modeles_generes.py` : colonnes Plaque et Comparé, bouton « Plaque… » (liste et fiche, validé seulement), historique lisible, trace après comparaison. Colis affichés au format français (« 790 » au lieu de « 790.0 »).
- `ui/etapes.py` (**raccordement annoncé, fichier partagé**) : après une comparaison, trace sur le modèle dont l'export archivé a exactement les mêmes octets. Un échec de la trace n'empêche pas d'afficher la comparaison.
- `export_pdf.py` : plaque et comparaisons dans le PDF du modèle, historique lisible ; plaque et tableau du détail des taxes dans le PDF de comparaison.
- Tests : `test_plaque_comparaison.py` (nouveau, 9 tests). Doublures ajustées dans `test_export_pdf.py`, `test_export_xml_modele.py` et `test_comparaison_prediction.py`. Ces deux derniers neutralisent maintenant la trace : sans cela, ils auraient interrogé la vraie base `DONNEES/modeles_generes.db`. Rien n'y a été écrit, car ils échouaient avant.

Vérification : **213 tests réussis**. Rendu du PDF de comparaison contrôlé (plaque, détail des taxes en page 2).

Limites : pas de recette Tk réelle. Une comparaison faite avant ce lot n'est pas connue (colonne « Non »). Une comparaison depuis Vérifier et générer n'est tracée que si l'export a été archivé dans Modèles générés.

## REF-104 — bouton « Recharger » (27/10/2026)

Ordre utilisateur : « le bouton refresh ne s'affiche pas, lance et fixe cela ». REF-104 avait été retenu par Atlas mais jamais implémenté. Le bouton n'existait que dans l'ancienne interface (`interface.py`). Plan de Quartz suivi, avec une différence : pas d'`execv` depuis la fenêtre. Le bouton passe par `quitter()`, qui garde ainsi les mêmes protections que la fermeture : préférences, refus pendant un import, base fermée. C'est ensuite `main()` qui relance, quand `app.rechargement is True`. Reconnexion conservée (CFG-003).

Fichiers : `rechargement.py` (nouveau : empreinte date/taille des `.py` de la racine et de `ui/`, tests ignorés), `ui/app.py` (**fichier réservé, raccordement annoncé** : bouton Recharger toujours visible dans le bandeau, alerte « Nouvelle version disponible → » relevée toutes les 5 s via `after`, minuteur annulé à la fermeture, `recharger()`, relance dans `main()`), `test_rechargement.py` (nouveau, 10 tests).

**Incident pendant le développement, corrigé.** Ma première version testait `if app.rechargement:`. Dans `test_session_locale`, l'application est un `Mock`, dont tout attribut est « vrai ». La suite de tests a donc réellement exécuté `os.execv`, et deux instances d'AsyDec se sont ouvertes sur l'écran de connexion (17:14:58 et 17:14:59). Je les ai arrêtées, aucune donnée n'est concernée. Correction : relance seulement si `rechargement is True`, plus un test de régression avec une doublure `Mock`. Suite complète : **223 tests réussis**, aucune relance parasite constatée ensuite.

Limites : pas de recette Tk réelle du redémarrage ; la détection repose sur la date et la taille des fichiers.

## UI-117 bis — bouton « Détails… » et détail des taxes depuis la fiche (27/10/2026)

Retour utilisateur : le bouton Détails n'apparaissait pas. Le détail des taxes n'était accessible que dans la fenêtre de comparaison, juste après une comparaison. Correction : « Consulter » est renommé « Détails… » (double-clic inchangé). La fiche reçoit « Détails des taxes… », qui s'appuie sur `modeles_generes.detail_taxes_modele()` : l'estimé vient de l'export archivé, ou du snapshot si le modèle n'a pas été exporté. Il est mis face au dernier XML comparé, relu sur le disque avec vérification SHA ; s'il est absent ou modifié, l'estimé est affiché seul avec la raison. `ui/comparaison.afficher_taxes()` accepte une explication. 3 tests ajoutés ; suite complète **226 tests réussis**.

Ajout (27/10) : colonne « Total taxes estimé CDF » dans la liste Modèles générés, alimentée par `resume.taxes_totales` du snapshot (taxes articles + taxes globales), sans recalcul. Elle manquait depuis UI-111. Suite complète OK.

## UI-118 — supprimer un modèle (27/10/2026)

Demande utilisateur : « donne-moi la possibilité de supprimer un modèle ». La base interdit le `DELETE` (déclencheurs `modeles_conserves`, `evenements_conserves`, `exports_conserves`, voulus par UI-111/112). La suppression est donc **logique et réversible**, comme le retrait des XML en UI-106 : événements append-only `suppression` (motif facultatif) et `restauration`. `lister(..., supprimes=False)` masque les modèles supprimés ; `supprimes=True` ne montre qu'eux. `detail()` renvoie `supprime`. UI : bouton « Supprimer… » avec confirmation, filtre « Supprimés », où le même bouton devient « Restaurer ». Aucun effacement physique : un test vérifie que le `DELETE` reste refusé. 6 tests (`test_suppression_modele.py`), doublures mises à jour ; suite complète OK.

**Point pour Atlas** : si l'utilisateur veut un jour un effacement réel (données personnelles, place disque), il faudra une décision d'architecture (déclencheurs, migration MIG-MOD de Quartz, sauvegarde). Je ne l'ai pas fait.

## UI-119 — la plaque saisie est inscrite dans le XML téléchargé (27/10/2026)

Demande utilisateur : « la génération des XML doit prendre les informations de la plaque si elle existe ». `modeles_generes.appliquer_plaque()` remplace uniquement la valeur de `Transport/Means_of_transport/{Departure_arrival_information,Border_information}/Identity` (substitution d'octets bornée au bloc, sans resérialisation ; `Seals/Identity` intact), puis vérifie le résultat par une relecture XML. `exporter_xml()` l'applique seulement si une plaque a été saisie ; le SHA et la copie archivée portent sur le fichier réellement écrit. Une exception à UI-114 (« octets d'export exacts ») est donc **assumée** : l'export diffère du snapshot uniquement par ces deux valeurs, et le snapshot reste intact. Essai en lecture seule sur un vrai modèle de `MODELES_XML` : seuls les deux champs changent. 7 tests ajoutés ; suite complète OK.

Non fait, à décider : « Vérifier et générer » (moteur/generer) reprend toujours la plaque du XML de base ; il n'y a pas de champ plaque à cette étape.

## UI-120 — nom du fichier XML généré visible (27/10/2026)

Demande utilisateur : afficher le nom du fichier XML généré, pour ne pas déposer le mauvais. `lister()` renvoie `chemin_xml`, le chemin du dernier événement export ; la liste a une colonne « Fichier XML généré ». `fichier_xml_genere(d)` relit le fichier et compare son SHA à la trace : présent et identique / introuvable / MODIFIÉ (affiché en rouge dans la fiche). La fenêtre de comparaison lancée depuis la liste nomme le fichier. Test ajouté, et recette Tk réelle sur base temporaire : liste et fiche construites, textes vérifiés. Suite complète OK.

## UI-121 — liste des modèles allégée (27/10/2026)

Retour utilisateur : tableau trop long, informations difficiles à lire. Passage de 12 à 9 colonnes : N°, Plaque, Importateur, Statut (court, vert si validé, gris si rejeté), Comparé (« Oui (n) »/« Non »), FOB USD, Poids kg, Taxes CDF, Fichier XML généré. Les dates, colis, auteur, date de comparaison et chemin complet passent dans un panneau « Modèle sélectionné » sous le tableau, mis à jour à la sélection (`afficher_resume()`, appelée en plus de `actualiser_comparaison()` pour ne pas toucher aux doublures existantes). Recette Tk sur base temporaire : valeurs de ligne et texte du panneau vérifiés ; la capture d'écran a échoué (fond d'écran capturé), donc pas de contrôle visuel. Suite complète OK.

## UI-122 — plaque facultative à l'étape Dossier (27/10/2026)

Demande utilisateur (capture de l'étape Dossier) : pouvoir ajouter la plaque, sans obligation. Fichiers :
- `moteur.py` (**fichier moteur, raccordement minimal, aucune règle de calcul changée**) : `CHEMINS_PLAQUE`, `normaliser_plaque()` (règle unique, reprise par `modeles_generes._plaque`), `ecrire_plaque()` (deux champs Identity du transport, `<null/>` retiré, refus si aucun champ).
- `generer.py` (**fichier partagé, annoncé**) : `produire(..., plaque=None)`. Une plaque vide ne change rien. Sinon, la plaque est inscrite avant le calcul, `info` relu (camion = plaque), alerte « Plaque inscrite dans le XML … » si elle diffère, `res['plaque']`.
- `modeles_generes.enregistrer` : le snapshot porte la plaque. L'empreinte inclut la plaque **seulement si elle est présente**, ce qui laisse identiques les empreintes des modèles existants.
- `ui/etapes.py` : champ « Plaque à inscrire (facultatif) ». `ui/app.py` : `plaque_saisie()` passée à `produire`, champ vidé à l'ouverture et à la fermeture d'un dossier. `ui/modeles_generes.reprendre` : plaque du modèle proposée.
- Tests : `test_plaque_generation.py` (4 tests). Un test de bout en bout lit un vrai modèle de `MODELES_XML`, **jamais modifié** (SHA vérifié en fin de test), et ne l'exécute pas s'il n'y a aucun modèle local. Page Dossier construite en Tk réel. Suite complète OK.

Note : la clé du registre de suivi des poids (`camion | manifeste`) utilise désormais la plaque inscrite quand elle est saisie.

## UI-123 — régénération répétable à l'étape Articles (27/10/2026)

Demande utilisateur (capture de l'étape Articles, poids décimaux 220.64 / 2649.36 issus de « Reprendre la base ») : pouvoir régénérer à cette étape autant de fois que nécessaire. `PageArticles.regenerer()` :
- totaux : saisis, sinon ceux du dossier ; poids total non entier refusé avec un message, sans toucher au tableau ;
- confirmation du taux ;
- `variantes.generer(nombre=1, exclure=vues)` par contexte (base, référence, totaux, bornes) ; la répartition affichée au départ est exclue elle aussi ;
- `controler`, puis `produire(enregistrer=False)` complet avant de remplir le tableau ;
- compteur « Répartition n° k ».
Aucune règle de calcul modifiée.

**Défaut de UI-122 corrigé** : `PageVerifier.regenerer()` n'envoyait pas la plaque saisie à `produire`. Une proposition régénérée à l'étape 3 aurait perdu la plaque. Les deux régénérations passent maintenant par `plaque_saisie(app)`, qui tolère les doublures.

Tests : `test_regeneration_articles.py` (3 tests) ouvre la **vraie page Tk** sur un modèle de `MODELES_XML` (SHA vérifié, jamais modifié) : 3 répartitions distinctes, poids entiers, totaux exacts, `moteur.enregistrer` jamais appelé. Suite complète OK. Une exécution a dépassé 180 s dans ce terminal ; la mesure suivante donne 25 s, donc la lenteur n'est pas reproductible.

Constat hors périmètre : un script `relance_asydec.sh` d'une autre session Claude (scratchpad `9ad1f1ef…`) tourne depuis 16 h 08. Il ne vient pas de moi ; je n'y touche pas.

## UI-124 — total des taxes estimé à l'étape Articles (27/10/2026)

Demande utilisateur : afficher aussi la valeur estimée des taxes totales. `PageArticles.estimer_taxes()` est appelée à chaque `actualiser()` (anti-rebond de 250 ms existant) : `generer.produire(enregistrer=False)` en mode SAISI avec les FOB affichés, registre vide (aucune lecture ni écriture), plaque saisie. Affichage sous les totaux : « Total taxes estimé : X CDF · articles + globales ». La ligne affiche « — » avec la raison si le tableau est incomplet, hors fourchettes ou si le calcul échoue. Pas de confirmation de taux à cette étape (c'est une estimation avec le taux du XML) ; la confirmation reste exigée pour Vérifier et générer. Test sur la vraie page : valeur identique à `produire`, « — » si un poids manque. Suite complète : **245 tests réussis en 25 s**.

## UI-125 — synthèse en cartes à l'étape Articles (27/10/2026)

Demande utilisateur : « améliore cette présentation » (interprétée comme la ligne de taxes ajoutée en UI-124 à l'étape Articles). La ligne de texte est remplacée par quatre cartes sous le tableau : Poids, FOB, Colis et **Total taxes estimé** (carte plus large, valeur en bleu). Chaque carte a une ligne secondaire : poids incomplets, FOB par ratios ou saisi, colis saisis ou automatiques, décomposition articles + globales. La carte des taxes affiche aussi ▲/▼ et l'écart avec la répartition précédente différente. `theme.Carte` reçoit des paramètres facultatifs (`detail`, `style_valeur`) ; les cartes existantes ne changent pas. Nouveau style `ValeurAccent.TLabel`. `var_taxes` est conservée. Tests sur la vraie page (valeurs, « — », indicateur d'écart) ; suite complète OK. Pas de capture visuelle possible depuis ce terminal.

## UI-126 — coche « bon modèle ★ » qui guide la régénération (27/10/2026)

Demande utilisateur : une petite option pour cocher un modèle jugé bon, afin d'aider la génération.
- `modeles_generes` : événements append-only `bon_modele` / `retrait_bon_modele` ; `marquer_bon()` (idempotent, **sans effet sur le statut de validation**) ; `lister()`/`detail()` renvoient `bon` ; `bons_modeles(signature)` renvoie les répartitions des modèles cochés, non supprimés, dont les articles du XML de base ont la même signature (code, désignation normalisée, devise).
- `variantes` (**fichier du domaine calcul, ajouts sans modification de règle**) : `signature_racine()` (refactorisation de `signature()`, comportement identique), `distance_parts()` (même mesure de parts que la composante principale de `evaluer()`), `plus_proche()`.
- `ui/etapes.PageArticles.regenerer()` : avec des bons modèles, `generer(nombre=8)` puis retient la proposition valide la plus proche ; sinon tirage libre `nombre=1` comme avant. Totaux, fourchettes, `controler` et `produire` complets sont inchangés. Message : modèle de référence et % de ressemblance.
- `ui/modeles_generes` : colonne ★, bouton « ☆ Cocher bon modèle » / « ★ Retirer la coche », filtre « Bons modèles ★ », ★ dans le panneau.
- Tests : `BonModeleTest`, `ProximiteTest` et `GuideBonsModelesTest` (vraie page Tk, vrai modèle lu sans modification, choix vérifié comme le plus proche des 8 tirages). Les tests Articles neutralisent `bons_modeles` pour ne **jamais lire la vraie base**. Recette Tk de la coche et du filtre. Suite complète OK.

**Pour Euclide (avis demandé)** : l'aide change seulement l'ordre de choix entre des répartitions déjà valides. Le choix de la distance (parts sans la composante ratios de `evaluer`) mérite son avis. Non appliqué à « Régénérer » de l'étape 3 ni à la page Répartitions.

## UI-127 — comparaison centrée sur le total des taxes (27/10/2026)

Retour utilisateur (capture) : explication pas claire ; la comparaison doit porter sur le total des taxes. `comparaison_prediction.synthese_taxes()` renvoie l'estimé, le comparé, l'écart, le % et des **phrases simples** : sens et montant de l'écart. Si les taux diffèrent, l'effet approximatif du taux est calculé comme estimé × (taux comparé / taux généré − 1) et la phrase dit si le taux explique presque tout l'écart (reste ≤ 10 %) ou quel reste subsiste. S'y ajoutent l'écart des taxes globales et le plus gros écart par article. L'approximation est présentée comme « environ ». Sur les chiffres de la capture : effet du taux ≈ −19 889 CDF pour un écart de −20 244.

`ui/comparaison.afficher()` est réorganisée : 3 cartes (estimé / comparé / différence ▲▼ + %), encadré « Ce qu'il faut retenir », tableau court « Taxes par article » (articles, taxes des articles, taxes globales, TOTAL en dernier, en gras). L'ancien tableau complet est déplacé dans « Tout le détail (poids, FOB, colis, CIF)… » (`afficher_detail_complet`). Boutons Détails des taxes et PDF conservés ; le PDF reprend « Ce qu'il faut retenir ». 3 tests ajoutés ; fenêtres construites en Tk réel sur une comparaison réelle (données temporaires). Suite complète OK.

**Pour Euclide** : l'approximation « effet du taux » suppose des taxes proportionnelles à la valeur en CDF. Les parts fixes (QFR au kg, arrondis) la rendent inexacte ; elle est donc formulée comme un ordre de grandeur.

## UI-128 — comparaisons persistées et consultables (27/10/2026)

Demande utilisateur : après comparaison, conserver les éléments pour revoir la comparaison à tout moment, surtout la répartition et la valeur globale des taxes.
- `noter_comparaison()` enregistre le **rapport complet** dans le détail JSON de l'événement append-only (Decimal sérialisés `{"__decimal__": "…"}`, relus exactement). Pas de changement de schéma ; le fichier comparé n'est pas copié.
- `comparaisons(d)` relit les comparaisons (rapport compris) ; `lister()` renvoie `dernier_ecart`. `detail_taxes_modele()` utilise d'abord le détail enregistré, puis le fichier relu (SHA vérifié) pour les comparaisons antérieures.
- `ui/comparaison` : tableau « Répartition et taxes par article » (« a → b » si différent, totaux de taxes en dernier) ; fonction `repartition(rapport)`.
- `ui/modeles_generes` : colonne « Écart taxes comparé » (▲/▼/=, nombre) ; panneau avec l'écart ; fiche → « Comparaisons enregistrées… » (liste, double-clic ou bouton pour rouvrir la fenêtre complète, PDF possible).
- Tests : rapport relu identique après suppression du fichier comparé, Decimal conservés, PDF depuis le rapport relu, ancienne comparaison sans rapport. Recette Tk : colonne, liste et réouverture avec fichier supprimé. Suite complète OK.

Point d'attention : la taille de l'historique grandit avec le nombre de comparaisons (quelques dizaines de Ko chacune) ; c'est à prendre en compte pour la migration MIG-MOD de Quartz.

## UI-129 — rangement des fichiers par importateur (27/10/2026)

Demande utilisateur : une bonne gestion de la sauvegarde des fichiers, pour qu'ils ne soient pas dispersés. Constat : seuls les XML générés avaient un emplacement fixe (`<IMP>/1 - HISTORIQUE`). Les XML validés, les PDF et les fichiers à comparer partaient où la fenêtre s'ouvrait ; un `…-COMPA.xml` a été vu dans `1 - HISTORIQUE`.
- `generer.RANGEMENT` et `dossier_rangement(importateur, cle, table_imp, creer=True)` : `1 - HISTORIQUE`, `2 - VOS FICHIERS (bases et SYDONIA)`, **`4 - XML VALIDES`**, **`5 - PDF`**. Le 3 est laissé libre, car `SHABANI SUMAILI/3 - A ESSAYER` existe (fichier « Cas a essayer »). Création à la demande, sans aucun déplacement ni suppression. `produire()` utilise les mêmes constantes, sans changer son comportement.
- Fenêtres : Télécharger XML → `4`, PDF modèle et comparaison → `5` (noms proposés : `<plaque> - <nom> - modele N.pdf`, `Comparaison <fichier>.pdf`), choix du XML à comparer (liste et étape 3) → `2`. Bouton « Ouvrir le dossier » dans Modèles générés. `comparer_xmls()` ajoute `importateur` au rapport.
- Tests : `test_rangement.py` (DEC temporaire : noms, création, contenu existant intact, repli de l'interface). Les doublures existantes neutralisent `rangement` : **aucun test ne crée de dossier dans DEC FRIPERIE** (vérifié après la suite). Suite complète : 259 tests réussis.

Non fait (à décider) : déplacer les fichiers déjà dispersés, comme le `-COMPA.xml` de `1 - HISTORIQUE`. Je n'ai rien déplacé.

## UI-130 — module d'analyse des anomalies (27/10/2026)

Demande utilisateur : un module qui alerte sur les modèles susceptibles d'être rejetés. Constat : les 62 références sont toutes `non_verifie`, il n'existe aucune vérité de rejet. Le module est donc **explicatif et indicatif**, sans prédiction.
- `anomalies.py` (nouveau, pur) : `references_par_groupe(observations)` (ratios et parts de poids par groupe devise/code/désignation normalisée, celui des références) ; `analyser(modele, groupes, autres)` ; `niveau()`. Contrôles : ratio hors du min–max observé (élevé ; mention pour les articles ajustables 4/7/8), hors déciles 10–90 à partir de 5 dossiers (moyen), part du poids hors min–max (moyen), distance des parts ≤ 0,02 avec un modèle **rejeté localement** de même signature (élevé, motif cité), poids et FOB identiques à un autre modèle (moyen), écart de la dernière comparaison > 1 % (moyen) ou > 5 % (élevé), article sans référence (info). Seuils regroupés dans `SEUILS`.
- `modeles_generes.donnees_analyse()` : modèles non supprimés au format d'analyse (groupes recalculés depuis le XML de base, motif de rejet, écart % de la dernière comparaison).
- `ui/modeles_generes` : colonne Risque (rouge/orange), filtre « À risque ⚠ », ligne dans le panneau, bouton « Anomalies… » (fenêtre détaillée avec l'avertissement « indicatif »). Observations `accepte` + `non_verifie` via `app.base_refs()`. L'analyse est facultative : en cas d'erreur, la liste reste utilisable.
- Tests : `test_anomalies.py` (9 tests, données inventées). Recette Tk sur une **copie temporaire** de la base des modèles et sur les références **en lecture seule** : modèle 4 élevé, 3 à vérifier, 1 sans signal, filtre et fenêtre OK. Suite complète OK.

**Pour Euclide (revue demandée)** : choix des seuils (déciles, 0,02, 1 %/5 %), pertinence de l'alerte « jamais observé » sur les articles ajustables, pondération éventuelle des références vérifiées. **Pour Quartz** : lecture seule de `observations()`, aucun changement de schéma.

## REF-CLEAN — restructuration « clean code » (en cours, interrompue par l'utilisateur)

Demande utilisateur : restructurer le code selon les principes clean code. Périmètre retenu : le code écrit ou fortement modifié par Plume (modèles générés, comparaison, PDF, anomalies, rangement). `moteur`, `variantes` et les références sont exclus (domaines Euclide/Quartz).
- **Fait, 268 tests OK** : étape 1, `formats.py` (`nombre`, `date_locale`) remplace trois copies ; `anomalies` réutilise `variantes.distance_parts`. Étape 2, `modeles_generes.py` réorganisé en sections : constantes d'actions, aides `_exiger_modele`, `_statut_courant`, `_dernier`, `_basculer` (suppression et coche partagent un mécanisme), découpage de `enregistrer` et `exporter_xml`. API publique, messages et schéma inchangés.
- **Commencé, non branché** : `ui/fenetres_modeles.py` (fiche, anomalies, comparaisons enregistrées extraites de l'écran). Il n'est pas encore utilisé : `ui/modeles_generes.py` est inchangé et reste la version active.
- Restant : brancher l'étape 3 (écran Modèles générés) et l'étape 4 (découpage de `PageArticles.regenerer`).

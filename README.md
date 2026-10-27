# AsyDec — préparation des déclarations XML ASYCUDA / SYDONIA

AsyDec recalcule une déclaration XML à partir du XML du dossier et des poids, FOB et
colis par article : facture, fret, assurance, CIF, chaque ligne de taxe, totaux et colis.
Le XML original n'est jamais modifié.

## Installation

Python 3.10 ou plus récent, avec Tkinter.

```bash
python3 -m venv .venv
.venv/bin/pip install openpyxl sv-ttk
```

`sv-ttk` (thème moderne, sans dépendance) est facultatif : sans lui, l'interface
utilise le thème standard.

## Lancement

| Fichier | Rôle |
|---|---|
| `ASYDEC.command` | **Interface principale** (double-clic), ou `.venv/bin/python asydec.py` |
| `INTERFACE.command` | Ancienne interface, conservée pendant la transition |
| `LANCER.command` | Génération par lot depuis `SAISIE.xlsx` (lignes « A GENERER ») |

## L'interface

Le bandeau du haut rappelle le dossier ouvert : importateur, référence, camion et totaux.
Le menu de gauche regroupe les trois étapes d'une déclaration et les outils.

### Déclaration

1. **Dossier.** Ouvrir le XML du dossier (⌘O) ou un fichier récent. Il fournit
   l'identité, les articles, le taux et les frais. Choisir la référence des ratios :
   par défaut, le XML du dossier.
2. **Articles.** Saisir les poids, importer un tableau Excel ou reprendre les valeurs
   de la base. Le FOB est calculé par les ratios, ou saisi article par article. Le
   contrôle se fait à chaque frappe : ratio obtenu, ✓ ou ⚠ selon les fourchettes, totaux.
   Colis vides = répartition automatique.
3. **Vérifier et générer.** Aperçu complet : poids, FOB, colis, taxes, CIF et taxes par
   article, alertes, nom du fichier qui sera créé. « Générer le XML » enregistre après
   confirmation, puis « Afficher dans le Finder ».

Raccourcis : ⌘1, ⌘2, ⌘3 pour changer d'étape ; ⌘↵ pour vérifier depuis les articles.
La taille de la fenêtre et les fichiers récents sont mémorisés dans `~/.asydec.json`.

### Outils

- **Répartitions.** À partir de trois totaux (FOB, poids, colis), propose des
  répartitions tirées des modèles enregistrés, classées par proximité.
  « Utiliser cette proposition » remplit les articles et ouvre la vérification.
- **Récupération des ratios.** Voir ci-dessous.
- **Étude des XML.** Compare les ratios d'un ensemble de XML à une référence choisie,
  avec un seuil d'écart (10 % par défaut). L'analyse peut être exportée en Excel.
- **Historique.** Liste les déclarations générées, les plus récentes d'abord, avec un
  filtre par importateur. Un double-clic affiche le fichier dans le Finder.

## Récupération des ratios

Ce module lit un groupe de XML, extrait le ratio FOB/kg de chaque article et regroupe
les ratios par article.

1. « Ajouter des XML… » ou « Ajouter un dossier… » (sous-dossiers inclus). Les ajouts
   s'accumulent ; « Vider » repart de zéro.
2. Une ligne par article : nombre d'observations, ratio minimum, maximum, moyen,
   médian, pondéré, et écart entre le minimum et le maximum. Dépliez un article pour
   voir le ratio de chaque fichier, du plus bas au plus haut.
3. « Séparer par importateur » calcule des fourchettes distinctes par importateur.
4. « Exporter Excel… » crée trois feuilles : `RATIOS` (synthèse), `DETAIL` (un ratio
   par fichier) et `FICHIERS ECARTES` (fichiers illisibles, avec la raison).

Règles de regroupement :

- Un article est reconnu par sa **devise**, son **code marchandise** et sa
  **désignation** (majuscules et espaces ignorés), quelle que soit sa position dans le XML.
- Un fichier présent en plusieurs exemplaires identiques n'est compté qu'une fois.
- Les articles sans poids ou sans FOB sont ignorés ; les fichiers qui ne sont pas des
  XML ASYCUDA sont écartés et listés.
- Ratio pondéré = somme des FOB ÷ somme des poids. Il reflète mieux la réalité que la
  moyenne simple quand les poids varient beaucoup.
- Écart = (maximum − minimum) ÷ minimum.
- L'article affiché en tête de ligne porte la position la plus fréquente dans les XML ;
  en cas d'égalité, la plus petite.

Les ratios récupérés sont descriptifs : ils ne modifient ni `SAISIE.xlsx` ni les
références des déclarations.

## Base de références

Les XML peuvent être conservés dans une base SQLite (`DONNEES/asydec.db`, exclue de Git),
avec leur provenance, leur valorisation complète et toutes leurs lignes de taxes.

```bash
.venv/bin/python import_references.py "../SHABANI SUMAILI" "../1 - A UTILISER"
```

- **Doublons.** Un fichier est reconnu par l'empreinte de son contenu : réimporté, renommé
  ou déplacé, il n'est stocké qu'une fois ; chaque chemin rencontré est gardé comme provenance.
- **Archivage.** Chaque XML est copié dans `DONNEES/sources/` sous son empreinte : la base
  reste consultable même si l'original est déplacé ou supprimé.
- **Exactitude.** Montants, poids et taux sont stockés en texte décimal exact, sans arrondi
  (« 2.83125E7 » devient « 28312500 »). Une valeur absente reste absente, jamais zéro.
  Les dates SYDONIA (« 10/1/26 ») sont gardées telles quelles, car leur format est ambigu.
- **Contenu.** Identité du dossier, numéros et dates d'enregistrement, de liquidation et de
  quittance, taux de change, fret, assurance, CIF, taxes globales et totales ; par article :
  code, désignation, procédure, poids, FOB, colis, CIF, ratio et chaque ligne de taxe
  (code, base, taux, montant).
- **Diagnostics.** Sommes des articles différentes des totaux, lignes de taxes incohérentes,
  articles incomplets ou répétés, valeurs non numériques. Rien n'est corrigé dans la source.
- **Sûreté.** Une transaction par document : aucun document importé à moitié. Un fichier
  refusé n'arrête pas le lot. Un import ne marque jamais un document comme « accepté ».
- **Sauvegarde.** `base_references.sauvegarder(conn)` copie la base et les archives dans
  `DONNEES/sauvegardes/` ; `base_references.restaurer(dossier)` vérifie la sauvegarde puis
  la restaure, après avoir sauvegardé l'état remplacé.

- **Statuts.** Chaque document est « non vérifié » tant que vous ne dites rien. Vous pouvez
  le marquer « accepté » (preuve ou référence obligatoire : numéro d'enregistrement,
  quittance…), « rejeté » ou « exclu des références » (motif obligatoire). Le statut vaut
  pour cette version exacte du fichier ; l'historique ne s'efface jamais, une erreur se
  corrige par une correction motivée. Ni l'import ni l'export ne marquent rien « accepté ».

La consultation de cette base dans l'interface et son raccordement au générateur sont
décrits dans `SUITE_MODULE_REFERENCES.md` (lots 3, 5 à 8).

## Règles communes

- Articles 4, 7 et 8 : ratios ajustables pour absorber l'écart de FOB, valeurs positives,
  arrondis au centime. Les écarts aux références sont affichés ; au-delà de 10 %, un
  signal invite à les examiner.
- Autres articles : ratios entre les minimums et maximums des références compatibles.
- Compatibilité : même ordre, codes, désignations normalisées et devise.
- Poids en kilogrammes entiers, sans décimales, FOB au centime, colis entiers positifs,
  totaux respectés.
- Avec des poids imposés, un FOB incompatible est refusé. Les articles 4/7/8 absorbent
  l'écart ; les autres gardent leurs bornes.
- Avec les trois totaux, les poids peuvent varier ; le classement mesure la proximité
  des parts de poids, FOB et colis avec les références (80 % du score), et la proximité
  des ratios ajustables aux références (20 %), parmi les propositions trouvées. Cette
  pondération est un choix de classement, sans valeur réglementaire.
- Colis saisis : les huit valeurs sont obligatoires. Colis automatiques : minimum
  10 par article, valeurs distinctes, total minimum 108. C'est une estimation à vérifier.

Les références conservées et les XML étudiés compatibles alimentent les fourchettes.
Les études peuvent contenir d'autres nombres d'articles, mais seuls les modèles
compatibles à huit articles valorisés peuvent servir à la génération.

La génération conserve les taux et frais du XML du dossier. Le contrôle du programme
ne garantit pas l'acceptation par SYDONIA : vérifiez toujours la déclaration avant dépôt.

## Organisation du code

| Fichier | Contenu |
|---|---|
| `moteur.py` | Calcul : valeurs par article, taxes, totaux, colis gradués |
| `generer.py` | Production d'une déclaration, nommage, registre, traitement de `SAISIE.xlsx` |
| `variantes.py` | Bibliothèque de modèles, fourchettes de contrôle, propositions de répartition |
| `etude_xml.py` | Lecture descriptive des XML, comparaison à une référence, export |
| `ratios.py` | Récupération et regroupement des ratios par article, export |
| `base_references.py` | Base SQLite : schéma, migrations versionnées, sauvegarde, restauration |
| `service_references.py` | Statuts de validation, historique, consultation des documents |
| `import_references.py` | Extraction complète des XML, archivage, dédoublonnage, diagnostics, import par lots |
| `ui/` | Interface AsyDec : `app.py` (fenêtre), `etapes.py` (3 étapes), `outils.py` (outils), `theme.py` |
| `interface.py`, `presentation.py` | Ancienne interface |

## Données et vérifications

Les données locales sont exclues de Git. `MODELES_XML` contient les modèles de contrôle,
`ETUDES_XML` les études et leurs sources. Les déclarations produites vont dans
`<IMPORTATEUR>/1 - HISTORIQUE/`, à côté du dossier `OUTILS`, nommées
`IMPORTATEUR FOBUSD POIDSKG NN.xml`. Aucun fichier existant n'est écrasé.

Tests : `.venv/bin/python -B -m unittest discover`.
Dans l'ancienne interface, le bouton Refresh recharge le code local et réinitialise les
saisies non enregistrées.

## Réutiliser un XML entre les pages

Un XML ouvert comme dossier ou ajouté depuis les pages Ratios, Études ou Modèles
est également conservé dans la bibliothèque SQLite. Les imports faits depuis la
bibliothèque sont disponibles aux autres pages via **« XML déjà disponibles… »**.
Il n'est plus nécessaire de sélectionner à nouveau le fichier sur le disque.

- **Dossier** : choisir un XML déjà disponible pour ouvrir le dossier, ou charger un nouveau fichier.
- **Répartitions** : les XML partagés compatibles peuvent servir de modèles ; une sélection de modèles est possible.
- **Récupération des ratios / Étude des XML** : sélectionner un ou plusieurs XML déjà disponibles.

Les copies archivées restent utilisables si les fichiers originaux sont déplacés.
Un contenu identique conserve un seul document et son statut : le partage ne vaut
jamais acceptation automatique. Les documents rejetés ou exclus ne sont pas
proposés dans le catalogue destiné à la génération. Les anciens modèles sur disque
restent accessibles. Cette étape partage les fichiers ; elle ne remplace pas encore
le futur service de décision fondé sur les observations acceptées et leur contexte.

### Fermer ou retirer un XML

- Dans **Dossier**, « Fermer le XML chargé » vide le dossier actif et les saisies non enregistrées, sans retirer le document de la bibliothèque.
- Dans **XML déjà disponibles…**, sélectionner un ou plusieurs fichiers puis « Supprimer de la liste… ». Après confirmation, ils disparaissent du catalogue partagé et des sélections d'analyse ; le dossier actif est fermé s'il utilise l'un d'eux.
- Le retrait est conservé après redémarrage et s'applique aux copies identiques. Les originaux, exports et archives/historiques de la bibliothèque ne sont pas effacés.
- Pour rendre un fichier retiré à nouveau disponible, le charger volontairement via « Ouvrir un nouveau XML » ou « Nouveaux XML ». Son historique et son statut antérieur sont conservés.

### Médiathèque XML partagée

Dans **Outils → Médiathèque XML**, ajoutez des fichiers ou un dossier entier (sous-dossiers inclus). Chaque contenu est archivé une seule fois. Les autres modules peuvent sélectionner ces archives via **XML déjà disponibles** ou **Médiathèque XML**, sans demander de nouveau le fichier original.

La liste montre les positions présentes et l'utilisation possible. Les XML de moins de huit articles servent uniquement aux études et statistiques ; leurs positions restent celles du fichier. Seuls les XML complets aux positions 1 à 8, avec poids et FOB positifs, peuvent être proposés comme bases de génération, sous réserve des contrôles supplémentaires. L'import ne signifie pas une acceptation douanière : le statut reste suivi séparément dans la bibliothèque des références. Retirer un XML de la médiathèque conserve les originaux, exports et historiques.

### Comparer une proposition à un fichier XML

Dans **Vérifier et générer**, cliquez sur **Comparer avec un XML…**, puis sélectionnez votre fichier. La fenêtre affiche les valeurs prévues et celles du fichier, ainsi que les écarts absolus et en pourcentage pour les poids, FOB, colis, ratios, CIF et taxes. Le fichier fourni reste intact. Les positions et codes identifient les articles ; les absences ou différences de contexte sont signalées. Un écart ne prouve pas une erreur de calcul : vérifiez notamment le taux de change, les frais et les taux de taxes utilisés.

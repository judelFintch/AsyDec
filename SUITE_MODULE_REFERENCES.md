# Canevas de développement — Finalisation du module de références XML

Date : 27 octobre 2026  
Statut : spécification de la suite à développer, et non compte rendu de fonctionnalités livrées.

## 1. Périmètre

Finaliser le module « Récupération des ratios » commencé dans `ratios.py` et `ui/outils.py`.

Objectif : transformer les observations extraites des XML en une base persistante et consultable, contenant les ratios, montants et taxes, puis l'utiliser pour expliquer et guider les générations.

Ce chantier ne couvre pas la refonte générale du projet ni le remplissage de modèles Word.

## 2. Point de départ vérifié

### Déjà disponible

- Import de plusieurs XML ou d'un dossier avec ses sous-dossiers.
- Extraction des codes, désignations, devises, importateurs, poids, FOB et ratios.
- Regroupement par devise, code et désignation normalisée, indépendamment de la position de l'article.
- Détection des fichiers identiques dans un lot par empreinte du contenu.
- Statistiques : minimum, maximum, moyenne, médiane et ratio pondéré.
- Consultation des observations dans une arborescence.
- Export Excel des résultats.

### À terminer

- Conservation durable des observations de ce module.
- Extraction détaillée des taxes et paramètres de valorisation.
- Gestion des statuts et preuves d'acceptation.
- Recherche de références utilisables par le générateur.
- Historisation des décisions et des générations.
- Analyse des montants et des variations à partir de la base.
- Import volumineux sans bloquer l'interface.

Les études JSON déjà présentes dans `etude_xml.py` ne constituent pas encore cette base commune. Leur reprise doit être prévue, sans perdre les sources.

## 3. Règles à conserver

1. Le ratio observé est `FOB article / poids brut article` ; sa devise et son unité doivent être connues.
2. Les poids des propositions générées sont des kilogrammes entiers positifs.
3. Les données historiques restent fidèles au XML, y compris si un poids source comporte des décimales. Ne pas arrondir silencieusement l'historique.
4. Les ratios des articles variables, actuellement 4, 7 et 8, peuvent être ajustés pour équilibrer le FOB. Cette classification doit être rattachée aux marchandises du profil, et pas déduite de la position dans un XML de structure différente.
5. Les autres articles restent dans les fourchettes des références compatibles retenues.
6. Une observation acceptée est une référence contextualisée, pas une garantie d'acceptation d'un nouveau dossier.
7. Un fichier importé ou généré ne devient jamais automatiquement une référence acceptée.
8. Les taxes historiques sont des observations. Ne pas transférer leurs taux à un autre contexte sans contrôle.
9. Une donnée absente reste absente : ne pas la transformer en zéro.
10. La simulation depuis les totaux utilise la base disponible, sans demander un nouveau XML au démarrage.

## 4. Base persistante SQLite

Fichier proposé : `DONNEES/asydec.db`, exclu de Git. Les XML sources sont archivés dans `DONNEES/sources/` sous leur empreinte.

### Tables proposées

| Table | Rôle et champs principaux |
|---|---|
| `schema_versions` | Versions et dates des migrations de la base. |
| `documents` | ID, SHA-256 unique, nom initial, chemin d'archive, origine, importateur, référence, camion, manifeste, dates XML connues, date d'import, devise, version du parseur. |
| `document_sources` | Chemins et noms rencontrés pour un même contenu, afin de conserver la provenance des doublons. |
| `valuations` | Document, FOB total, poids total, colis total, fret, assurance, autres ajustements disponibles, CIF, taux de change et monnaies associées, taxes globales et total des taxes. |
| `articles` | Document, position source, code marchandise, désignation brute et normalisée, procédure/régime si disponible, poids brut/net, FOB, colis, CIF, valeurs statistiques et ratio dérivé. |
| `tax_lines` | Article, position de la ligne, code taxe, base taxable, taux, unité ou mode de calcul connu, devise, montant et informations source. |
| `global_tax_lines` | Détail des taxes globales s'il existe ; conserver uniquement le total si le XML ne fournit pas le détail. |
| `status_events` | Document, ancien/nouveau statut de validation, date, auteur identifié si disponible, commentaire et référence de preuve. |
| `import_batches` | Lot, dossier source, dates, fichiers trouvés/traités/importés/dupliqués/refusés et état terminé/annulé/interrompu. |
| `diagnostics` | Lot/document/article, gravité, code de contrôle, explication et donnée source concernée. |
| `generations` | Totaux demandés, options, profil et version des règles, graine aléatoire, résultat sélectionné, état de l'export et document produit. |
| `generation_references` | Génération, observations utilisées, rôle, raisons de sélection et instantané des valeurs retenues. |

### Contraintes techniques

- Clés étrangères actives et index sur les clés de recherche : code, devise, statut, importateur, date et document.
- Transaction par document : aucun document importé à moitié.
- Montants lus avec une arithmétique décimale ; stockage exact, par exemple en texte décimal canonique. Ne pas utiliser un flottant binaire comme source financière de vérité.
- Ratio recalculable depuis le FOB et le poids exacts ; une statistique en cache ne remplace pas les observations.
- Préserver les informations brutes nécessaires à l'audit et au retraitement par une nouvelle version du parseur.
- Requêtes paramétrées et migrations versionnées.
- Sauvegardes cohérentes de la base et des archives ; procédure de restauration testée.

## 5. Statuts et fiabilité des références

Séparer deux dimensions :

- **Origine** : XML externe importé ou XML produit par l'application.
- **Validation** : non vérifié, accepté, rejeté, à exclure des références.

Une simulation reste une simulation ; elle n'est pas une déclaration acceptée.

### Passage au statut accepté

L'utilisateur doit pouvoir enregistrer la date connue, une référence ou une preuve d'acceptation et un commentaire. Le statut concerne une version précise du document, identifiée par son empreinte.

Une modification du XML crée un nouveau document. Elle n'hérite pas automatiquement de l'acceptation de l'ancienne version.

### Politique de recherche

1. Rechercher les observations acceptées et compatibles.
2. Si elles manquent, afficher explicitement la possibilité d'utiliser des observations non vérifiées.
3. Ne pas mélanger silencieusement les deux catégories dans une même fourchette.
4. Exclure les observations rejetées ou invalides du calcul des références.
5. Conserver la politique et les identifiants des observations utilisés dans la décision.

## 6. Import et extraction complets

### Chaîne de traitement

```text
Sélection de fichiers ou d'un dossier
  → création d'un lot d'import
  → empreinte et détection des doublons
  → lecture du XML et identification du format
  → extraction des données brutes
  → normalisation sans perte des valeurs originales
  → contrôles et diagnostics
  → archivage de la source + transaction SQLite
  → mise à jour de la progression et du bilan
```

### Informations à extraire

- Identité et contexte du dossier : importateur, références, transport, manifeste et dates effectivement présentes.
- Paramètres monétaires : monnaies, taux de change et unités.
- Valorisation globale et par article : FOB, fret, assurance, ajustements, CIF et poids.
- Colis par article et au total.
- Toutes les lignes de taxes, avec leurs codes, bases, taux et montants.
- Totaux fiscaux disponibles, sans inventer un détail absent.

### XML différents

- Ne pas imposer huit articles au module d'observation.
- Ignorer les lignes entièrement vides, mais signaler les lignes partiellement renseignées.
- Prendre en charge les variantes de structure identifiées avec des adaptateurs de lecture.
- Signaler les formats et espaces de noms non reconnus ; ne pas produire une extraction vide présentée comme réussie.
- Ne pas confondre le même article répété dans un document avec un fichier dupliqué.

### Gros volumes

- Exécuter l'import dans une tâche de fond ; les mises à jour Tkinter restent dans le fil de l'interface.
- Afficher le nombre traité, les nouveaux documents, doublons et erreurs.
- Permettre l'annulation entre deux documents, sans supprimer ceux déjà importés.
- Permettre de relancer un lot interrompu sans multiplier les observations.
- Importer par lots de transactions bornés et éviter de charger tous les XML en mémoire.

## 7. Contrôles de qualité

| Contrôle | Traitement attendu |
|---|---|
| XML illisible ou format inconnu | Écarter le fichier et garder la raison dans le bilan. |
| FOB ou poids absent/non positif | Conserver l'information, mais exclure le ratio de la recherche quantitative. |
| Code, devise ou désignation manquant | Signaler une compatibilité incertaine ; aucun rapprochement automatique forcé. |
| Somme des articles différente du total XML | Diagnostic avec valeur calculée, valeur déclarée et tolérance utilisée. |
| Taxes incohérentes avec les totaux disponibles | Diagnostic ; ne pas corriger la source automatiquement. |
| Taux ou unité de taxe ambigu | Conserver le brut et signaler que l'interprétation est inconnue. |
| Ratio inhabituel | Comparaison au groupe approprié, avec effectif et dispersion ; pas de rejet automatique. |
| Source identique réimportée | Réutiliser le document, ajouter la provenance si nouvelle. |
| Nouvelle version d'un dossier | Conserver les deux versions et leurs statuts respectifs. |

Les seuils de diagnostic sont configurables et documentés. Ils ne constituent pas des seuils réglementaires.

## 8. Interface d'analyse à compléter

Faire évoluer la page existante « Récupération des ratios », sans créer une deuxième base ou une page concurrente.

### Vue bibliothèque

- Recherche et filtres : marchandise, code, devise, importateur, statut, période connue et origine.
- Compteurs : documents, articles, observations exploitables, références acceptées et anomalies.
- Import multiple, import de dossier, progression, annulation et bilan.
- Retour après fermeture : les données et statuts sont toujours consultables.

### Vue marchandise

- Minimum, maximum, médiane, moyenne et ratio pondéré.
- Nombre d'observations et nombre de documents distincts.
- Répartition des statuts et effectif des références réellement retenues.
- Tableau détaillé : fichier, date connue, FOB, poids, ratio, colis et statut.
- Graphique des ratios observés, sans fabriquer un ordre chronologique si les dates manquent.
- Ne pas fusionner automatiquement des désignations différentes uniquement parce que leur code est identique.

### Vue dossier

- FOB, poids, colis, fret, assurance, CIF, taux de change et taxes globales.
- Tableau par article, puis détail des lignes de taxes.
- Valeurs source et diagnostics côte à côte.
- Historique des statuts et accès au XML archivé.

### Vue comparaison et décision

- Choix explicite de la référence ou du groupe de référence.
- Hausses, baisses et écarts absolus/en pourcentage des ratios et montants.
- Signalement des éléments absents ou non comparables.
- Explication des observations utilisées par une génération.
- Affichage clair des montants historiques et des montants estimés : ne pas les confondre.

### Export

Compléter l'export Excel : synthèse, observations, valorisation, taxes, comparaisons, diagnostics et références utilisées. Les filtres, devises, unités, statuts et méthode de comparaison doivent être précisés dans le fichier.

## 9. Raccordement au générateur

### Service de référence commun

Créer une couche de recherche utilisée par le générateur et l'interface d'analyse. L'interface ne doit pas envoyer directement des requêtes SQL dispersées dans le code.

Contrats proposés, à implémenter :

```python
importer_lot(chemins, progression=None, annulation=None) -> BilanImport
rechercher_observations(filtres) -> PageObservations
obtenir_statistiques(criteres, politique_statuts) -> Statistiques
chercher_references(marchandises, contexte, politique_statuts) -> ResultatReferences
enregistrer_statut(document_id, statut, preuve, commentaire) -> EvenementStatut
enregistrer_generation(entree, choix, references, regles) -> Generation
consulter_decision(generation_id) -> DetailDecision
```

### Compatibilité des références

Rechercher par marchandise et contexte : devise, unité de poids, code, désignation normalisée et, lorsque disponible et pertinent, régime/procédure et période.

Le nombre et l'ordre des articles du XML source ne doivent pas empêcher la récupération d'une observation. En revanche, l'export reste soumis à la structure effectivement prise en charge par le moteur actuel.

Un contexte fiscal différent n'interdit pas forcément la consultation d'un ratio, mais interdit de présenter ses taxes comme directement applicables sans vérification.

### Décision enregistrée

Pour chaque proposition choisie, conserver :

- Les totaux demandés et les valeurs finales par article.
- Les observations sources et leur statut au moment du calcul.
- Les fourchettes retenues pour les articles non variables.
- Les ratios des articles variables avant et après ajustement, et leurs écarts.
- Le score, sa formule et ses pondérations.
- Les paramètres fiscaux utilisés pour estimer les taxes.
- Les avertissements, les règles et la version du moteur.

### Export et historique

- Une consultation ou un simple aperçu ne doit pas créer une référence acceptée.
- L'enregistrement d'une simulation est explicite et reste distinct de l'export XML.
- Lors d'une génération, enregistrer le résultat et sa traçabilité dans la base.
- L'export fichier et la transaction SQLite ne sont pas une opération atomique unique : prévoir les états `en_preparation`, `exporte` et `echec`, un fichier temporaire, puis une procédure de récupération.
- Si l'écriture du fichier réussit mais pas la finalisation de l'historique, signaler l'incident et permettre la réconciliation sans nouvelle génération aveugle.
- Ne jamais attribuer le statut accepté lors de l'export.

## 10. Organisation technique proposée

| Élément | Évolution attendue |
|---|---|
| `ratios.py` | Conserver les fonctions de regroupement ; déléguer la persistance et la recherche à des services communs. |
| Nouveau `base_references.py` | Connexion SQLite, migrations, transactions, requêtes et sauvegarde. |
| Nouveau `import_references.py` | Lots, archivage, dédoublonnage et extraction complète. |
| Nouveau `service_references.py` | Filtres métier, politiques de statuts et sélection des références. |
| `etude_xml.py` | Réutiliser/étendre l'extraction ; adapter les études existantes à la base commune. |
| `ui/outils.py` | Compléter la page de ratios et ses vues d'analyse. |
| `variantes.py` | Consommer les références du service, sans perdre la règle des ratios variables ajustables. |
| `generer.py` | Enregistrer les générations et leur traçabilité, avec gestion des échecs d'export. |
| `tests` | Tests de base, import, compatibilité, statuts, traçabilité et non-régression. |

Les noms des nouveaux fichiers sont proposés ; éviter un second parseur ou une seconde politique de référence si une fonction existante peut être réutilisée.

## 11. Lots de développement et conditions de fin

| Lot | Travail | Dépendance | Condition de livraison |
|---|---|---|---|
| 1 — Stockage | Schéma SQLite, migrations, archivage, sauvegarde | Aucune | Import simple persistant, fermeture/réouverture et restauration vérifiées. |
| 2 — Extraction | Valorisation, taxes, contexte, diagnostics | Lot 1 | Valeurs extraites comparées aux XML sources, sans perte des données absentes ou décimales. |
| 3 — Import volumineux | Lots, doublons durables, progression, annulation/reprise | Lots 1–2 | Interface réactive ; aucun doublon après reprise d'un lot interrompu. |
| 4 — Statuts | Origine, acceptation, preuve et historique | Lots 1–2 | Impossible qu'un import ou un export marque automatiquement un document accepté. |
| 5 — Analyse | Filtres, dossier, taxes, statistiques, variations, export | Lots 2–4 | Données retrouvées après relance et comparaisons explicables par leurs sources. |
| 6 — Références | Recherche compatible, priorité aux acceptés, absence de référence | Lots 4–5 | Le générateur utilise des observations identifiées et affiche les limites de la sélection. |
| 7 — Générations | Instantanés, liens aux références, états d'export, récupération | Lot 6 | Chaque XML produit peut être relié aux données et règles qui ont conduit au résultat. |
| 8 — Reprise de l'existant | Réimport XML/études JSON, contrôles et bascule du module | Lots 1–7 | Inventaire avant/après cohérent, aucune acceptation supposée, anciens fichiers conservés. |

Ne pas annoncer un lot terminé uniquement parce que son écran existe : les conditions de livraison doivent être démontrées.

## 12. Tests et recette attendus

### Tests automatisés

- Création de la base et migration depuis une version antérieure.
- Réimport du même fichier, renommé ou déplacé : une seule observation source par article/document.
- Deux fichiers différents portant le même nom : conservation distincte.
- Même marchandise dans des positions différentes : regroupement correct.
- Devises ou unités différentes : aucune fusion injustifiée.
- Article répété dans un document : conservation des occurrences et traitement explicite de l'ambiguïté.
- XML vide, malformé, incomplet, avec lignes vides ou structure non reconnue.
- Conservation exacte des montants, poids historiques et lignes de taxes.
- Ratios non calculables exclus des statistiques, mais données et diagnostic conservés.
- Acceptation explicite, changement de statut et non-propagation à une version modifiée.
- Absence de référence acceptée : retour explicite, sans recours silencieux à des simulations.
- Annulation et reprise sans import partiel d'un document.
- Historique d'une génération, simulation non acceptée et références immuables.
- Échec d'export avant/après écriture et récupération sans doublon.
- Sauvegarde et restauration fonctionnelles.

### Mesures sur gros lots

Préparer des jeux de 100, 1 000 puis 10 000 XML représentatifs. Mesurer le temps, la mémoire, la réactivité de l'interface et le délai d'annulation. Ces volumes sont des objectifs de recette, pas des performances déjà garanties.

### Scénario utilisateur de validation

1. Importer un dossier de XML, dont un doublon et un fichier invalide.
2. Consulter le bilan et une marchandise avec ses FOB, poids, ratios et taxes.
3. Fermer puis rouvrir : retrouver les mêmes données et leurs provenances.
4. Marquer une version comme acceptée avec une preuve ou référence renseignée.
5. Demander une simulation à partir des trois totaux, sans nouveau fichier.
6. Voir les observations retenues, les fourchettes, les ratios ajustés et leurs écarts.
7. Associer le dossier réel pour recalculer les taxes et exporter.
8. Retrouver le XML produit et l'explication de sa génération dans l'historique.
9. Vérifier que ce nouveau XML reste non accepté tant que l'utilisateur n'enregistre pas son acceptation.

## 13. Coordination avec l'autre agent

- Partager ce canevas et convenir d'un seul schéma de données et d'un seul service de recherche.
- Délimiter les fichiers modifiés par chacun avant l'intégration.
- Livrer d'abord les contrats, migrations et tests du stockage, puis raccorder les écrans et le générateur.
- Préserver les fichiers existants et ne pas reclasser automatiquement les anciennes références comme acceptées.
- Produire, à chaque lot, un bilan : fichiers modifiés, tests exécutés, limites restantes et procédure de vérification.

## 14. Critère final du module

Le module sera terminé lorsqu'une observation extraite d'un XML sera conservée avec sa provenance et ses taxes, consultable après relance, filtrable selon son statut, utilisable par le générateur et retrouvable dans l'explication d'une génération — sans confondre observation historique, proposition calculée et acceptation effective.

## 15. Historique persistant des modèles générés, validés et utilisés

### Besoin complémentaire

L'utilisateur doit savoir quelle répartition a été générée, laquelle a été validée, quel modèle a réellement été utilisé, sur quel dossier et à quelle date. Il doit pouvoir retrouver et réutiliser une répartition antérieure sans perdre son historique.

Un **modèle de répartition** correspond aux marchandises, poids, FOB, colis et ratios sélectionnés. Un **document XML de dossier** contient en plus l'identité, les références et les paramètres fiscaux du dossier. Un même modèle peut être utilisé dans plusieurs dossiers, avec des taxes finales différentes.

### Enregistrement et validation

- Chaque proposition retenue reçoit un identifiant stable et un numéro de version.
- Ajouter une action explicite « Enregistrer ce modèle » pour conserver une simulation sans exporter de XML.
- Enregistrer automatiquement le modèle retenu lors d'une génération XML réussie ; relier l'export au modèle et à la génération, sans créer de doublon de répartition.
- Conserver les valeurs exactes par article, les totaux, le profil de référence, la version des règles, le score et les avertissements.
- Distinguer « contrôles techniques réussis », « validé par l'utilisateur » et « accepté dans SYDONIA ».
- Une validation utilisateur comporte une date, un auteur identifié si disponible et un commentaire. Elle n'est pas une preuve d'acceptation douanière.
- Un modèle enregistré ne change pas silencieusement : une modification de ses données crée une nouvelle version, liée à l'ancienne.
- Une nouvelle version ne reçoit pas automatiquement les validations de l'ancienne.

### Détection des modèles identiques

Prévoir deux empreintes distinctes :

1. **Empreinte du fichier XML brut** : repère un contenu de fichier strictement identique.
2. **Empreinte de répartition normalisée** : repère les mêmes marchandises, poids entiers, FOB au centime, devises, unités et colis, même si le nom du fichier ou les informations de dossier diffèrent.

La normalisation doit être documentée et versionnée. Elle ne doit pas fusionner des lignes de marchandise répétées ni masquer une différence de contexte. Conserver une correspondance non ambiguë des articles ; en cas d'ambiguïté, demander une comparaison plutôt que fusionner automatiquement.

Un profil de règles ou de références différent reste enregistré dans la génération, même lorsque la répartition finale est identique.

Lorsqu'une répartition identique existe :

- Afficher son identifiant, sa date de création, ses validations et ses utilisations précédentes.
- Proposer de consulter ou de réutiliser le modèle existant.
- Éviter de créer une copie indistinguable du modèle, tout en conservant chaque nouvelle génération et utilisation comme événement distinct.
- Ne pas confondre « identique » et « similaire ». Des ratios proches ou des proportions identiques avec d'autres totaux constituent des modèles différents.
- Une similarité peut être affichée avec son critère et son score, mais elle ne déclenche ni fusion ni transfert de validation.

### Tableau de suivi demandé

Créer une vue « Historique des modèles », avec filtres par période, importateur, dossier, état et identifiant.

| Colonne | Information affichée |
|---|---|
| Modèle / version | Identifiant stable et filiation éventuelle. |
| Créé le | Date et heure de création. |
| Dernière utilisation | Date et heure de la dernière utilisation confirmée. |
| Validé le / par | Validation utilisateur, si elle existe. |
| Validation | Contrôle technique, validation utilisateur et acceptation SYDONIA affichés séparément. |
| Poids / FOB / colis | Totaux de la répartition et devise. |
| Référence utilisée | Profil et observations ayant conduit au modèle. |
| Utilisations | Nombre d'utilisations confirmées, distinct du nombre d'exports et de simulations. |
| Dossiers associés | Accès aux dossiers et documents reliés. |
| Identité / similarité | Correspondance exacte ou indication de proximité clairement distinguées. |
| Dernier événement | Création, validation, export, utilisation, réutilisation ou archivage. |

Actions : « Voir le détail », « Comparer », « Valider », « Réutiliser », « Voir les dossiers » et « Voir l'historique daté ».

Le détail affiche les valeurs par article et les montants fiscaux de chaque dossier associé. Ne pas attribuer au modèle une taxe unique si ses utilisations ont des taux, frais ou monnaies différents.

### Réutilisation d'un modèle

```text
Choisir un modèle conservé
  → consulter les valeurs, validations et utilisations précédentes
  → choisir « Réutiliser »
  → créer une nouvelle session de génération liée au modèle source
  → associer le dossier réel au moment de l'export
  → revérifier les références et le contexte fiscal actuels
  → recalculer les taxes et afficher les écarts
  → confirmer la nouvelle génération
  → conserver l'export et la filiation dans l'historique
```

- La réutilisation reprend la répartition choisie, pas aveuglément l'importateur, le camion, le manifeste, les dates et les taux du dossier précédent.
- Si l'utilisateur conserve exactement les valeurs, rattacher la nouvelle génération au même modèle de répartition.
- Si les valeurs changent, créer une nouvelle version ou un nouveau modèle avec un lien vers le modèle de départ.
- Un ancien modèle validé peut devenir incompatible avec les règles courantes : conserver sa validation historique, mais signaler l'échec des contrôles actuels et bloquer l'export incompatible.
- Réutiliser une simulation ne signifie pas qu'elle a été utilisée dans un dossier réel.

### Définition d'une utilisation

Un export réussi est un événement « exporté ». Il ne prouve pas que le fichier a été utilisé ou accepté.

Ajouter une action « Marquer utilisé pour ce dossier » avec date d'utilisation, dossier, auteur si disponible et commentaire. L'acceptation SYDONIA est une étape séparée, accompagnée de sa référence ou preuve.

L'historique doit distinguer :

- Modèle enregistré.
- Modèle validé par l'utilisateur.
- Génération commencée, réussie ou échouée.
- XML exporté.
- Utilisation confirmée dans un dossier.
- Acceptation ou rejet déclaré, avec justification.
- Réutilisation vers un autre dossier ou création d'une version dérivée.

### Compléments au schéma SQLite

| Table | Rôle |
|---|---|
| `allocation_models` | Identifiant, version, empreinte de répartition, parent éventuel, dates et état d'archivage. |
| `allocation_model_items` | Instantané exact des marchandises, poids, FOB, colis et ratios de chaque version. |
| `model_validations` | Résultat des contrôles, version des règles, validation utilisateur et éléments justificatifs. |
| `model_usage` | Liens modèle–génération–document–dossier, date d'utilisation confirmée et commentaire. |
| `model_events` | Journal daté et append-only des créations, validations, réutilisations, exports et corrections. |

Relier ces tables à `generations`, `generation_references`, `documents` et `status_events`, sans dupliquer les lignes fiscales déjà rattachées aux documents.

### Dates et corrections

- Stocker les horodatages techniques en UTC et afficher les dates dans le fuseau `Africa/Lubumbashi`.
- Distinguer date de création, date d'export, date de validation, date d'utilisation et date d'acceptation.
- Pour un événement historique saisi après coup, conserver sa date effective et sa date de saisie.
- Ne pas déduire une date d'utilisation de la date d'import ni du nom d'un fichier.
- Une correction de date ou de statut ajoute un événement de correction motivé ; elle n'efface pas la trace antérieure.
- Un modèle archivé demeure consultable dans l'historique. Éviter la suppression destructive d'un modèle déjà utilisé.

### Livraison et tests supplémentaires

Ce complément s'intègre aux lots 4, 5 et 7 du planning : statuts, interface d'analyse et historique de génération.

- [ ] Un modèle enregistré est retrouvé après fermeture et réouverture.
- [ ] Deux répartitions identiques sont reconnues malgré des noms de fichiers différents.
- [ ] Une variation d'un poids, d'un FOB, d'un colis, d'une devise ou d'une marchandise empêche la fausse identification exacte.
- [ ] Les modèles similaires restent distincts et leurs critères de rapprochement sont visibles.
- [ ] Les différentes générations d'une même répartition restent traçables séparément.
- [ ] La validation utilisateur et l'acceptation SYDONIA ne sont jamais confondues.
- [ ] Une réutilisation vers un autre dossier conserve le modèle source et recalcule les montants fiscaux.
- [ ] Une réutilisation modifiée crée une version dérivée, sans écraser la précédente.
- [ ] Le tableau distingue les exports des utilisations réellement confirmées.
- [ ] Les dates affichées respectent le fuseau de Lubumbashi et les corrections restent auditables.
- [ ] L'échec d'une génération ne compte pas comme utilisation réussie.
- [ ] Le détail d'un dossier permet de remonter au modèle, à ses références, à ses validations et à ses événements.

## 16. Suivi des lots

| Lot | État | Date |
|---|---|---|
| 1 — Stockage | Livré | 27/10/2026 |
| 2 — Extraction | Livré | 27/10/2026 |
| 4 — Statuts | Livré | 27/10/2026 |
| 3, 5 à 8 | À faire | — |

Le besoin de la section 15 (historique des modèles de répartition) sera livré avec les lots 4, 5 et 7.

### Bilan des lots 1 et 2

**Fichiers créés** : `base_references.py` (schéma, migrations, sauvegarde, restauration), `import_references.py` (extraction, archivage, dédoublonnage, diagnostics, import par lots, ligne de commande), `test_references.py` (14 tests). Fichiers modifiés : `.gitignore` (`DONNEES/`), `README.md`.

**Schéma version 1** : `schema_versions`, `import_batches`, `documents`, `document_sources`, `valuations`, `articles`, `tax_lines`, `global_tax_lines`, `diagnostics`. Les tables `status_events`, `generations` et `generation_references` viendront par migration avec les lots 4 et 7.

**Choix d'implémentation**

- Montants en texte décimal canonique et exact (`Decimal`, sans arrondi ; notation exponentielle développée). Ratio stocké à 10 décimales, toujours recalculable depuis FOB et poids.
- Dates SYDONIA gardées brutes (`*_date_brute`), leur format `M/J/AA` étant ambigu.
- Détail des taxes globales : enregistré seulement s'il existe. Dans les 69 XML actuels, `Global_tax_item` est toujours vide ; seul le total est conservé.
- Une ligne `Item` entièrement vide est ignorée ; une ligne partielle est gardée avec un diagnostic.
- Un document refusé laisse un diagnostic au niveau du lot, avec la raison.
- `importer_lot` accepte déjà `progression` et `annulation` (entre deux documents). L'exécution en tâche de fond et la reprise d'un lot interrompu dans l'interface restent au lot 3.

**Conditions de livraison démontrées**

| Condition | Preuve |
|---|---|
| Import persistant, fermeture et réouverture | `test_persistance_apres_fermeture` |
| Restauration vérifiée | `test_sauvegarde_et_restauration`, `test_sauvegarde_endommagee_refusee` ; essai réel : 64 documents et 6 144 lignes de taxes retrouvés après restauration |
| Migrations versionnées et atomiques | `test_migrations_versionnees_et_idempotentes` (une migration en échec n'applique rien) |
| Aucun document importé à moitié | `test_aucun_document_a_moitie_importe` (panne simulée pendant l'écriture des taxes) |
| Valeurs fidèles aux XML, sans perte d'absences ni de décimales | `test_valeurs_exactes_et_absences` ; essai réel sur 69 XML : 0 écart entre base et sources (FOB, poids, CIF, taux, totaux et chaque ligne de taxe) |
| Doublons, provenance, homonymes | `test_doublons_provenance_et_homonymes` ; essai réel : 69 fichiers → 64 documents, 5 doublons, relance → 0 nouvel import |
| Diagnostics sans correction de la source | `test_diagnostics_de_coherence` ; essai réel : 5 signaux « nombre d'articles déclaré différent » (niveau info) |
| Formats non reconnus refusés | `test_formats_refuses`, `test_fichiers_refuses_dans_le_bilan` |
| Import jamais « accepté » | `test_import_ne_marque_jamais_accepte` |

**Limites restantes** : la base n'est pas encore visible dans l'interface (lot 5) ; les études JSON de `etude_xml.py` ne sont pas reprises (lot 8) ; la page « Récupération des ratios » lit encore les XML directement, sans la base.

**Vérification** : `.venv/bin/python -B -m unittest discover`, puis `.venv/bin/python import_references.py <dossier>` et relancer la même commande : la seconde exécution doit annoncer 0 import et uniquement des doublons.

### Bilan du lot 4

**Fichiers** : migration 2 dans `base_references.py` (le découpage des migrations accepte désormais les déclencheurs), nouveau `service_references.py`, 7 tests ajoutés dans `test_references.py` (21 au total).

**Schéma version 2** : table `status_events` (en ajout seul), vue `document_statuts` (statut courant, « non vérifié » par défaut).

**Règles appliquées**

- Statuts : non vérifié, accepté, rejeté, exclu des références. L'origine (importé / généré) reste une dimension séparée, dans `documents.origine`.
- « Accepté » exige une preuve ou une référence. Ce contrôle est imposé deux fois : par le service et par une contrainte `CHECK` de la base.
- Rejet, exclusion et retour à « non vérifié » exigent un commentaire.
- Date effective facultative, au format AAAA-MM-JJ, jamais dans le futur ; date de saisie technique en UTC.
- Historique en ajout seul : des déclencheurs refusent toute modification ou suppression d'un événement. Une erreur de date ou de preuve se corrige par un événement de correction motivé, qui ne change pas le statut courant et ne retire jamais la preuve d'une acceptation.
- Un document qui a un historique de statuts ne peut pas être supprimé.
- `preuve_suggeree` propose les numéros d'enregistrement, de liquidation et de quittance présents dans le XML. C'est une suggestion à confirmer : elle n'accepte rien d'elle-même.

**Conditions de livraison démontrées**

| Condition | Preuve |
|---|---|
| Impossible qu'un import ou un export marque un document accepté | `test_import_ne_marque_jamais_accepte` (importé et généré restent « non vérifié », aucun événement créé) ; `test_acceptation_exige_une_preuve` (refus du service et de la base) |
| Statut lié à une version précise | `test_nouvelle_version_n_herite_pas_du_statut` |
| Preuve, commentaire, date et historique | `test_rejet_exclusion_et_retour_exigent_un_motif`, `test_dates_effectives_controlees` |
| Historique non modifiable, corrections tracées | `test_historique_en_ajout_seul_et_corrections` |
| Migration d'une base existante | Base d'essai réelle en version 1 (64 documents) migrée en version 2 sans perte ; 64 documents « non vérifiés » |

**Limites restantes** : pas encore d'écran pour changer un statut (lot 5) ; la politique « références acceptées d'abord » sera appliquée par la recherche du générateur (lot 6). Les validations des modèles de répartition (section 15) viendront avec le lot 7.


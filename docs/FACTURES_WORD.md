# Factures Word à partir des modèles générés

Dans **Modèles générés**, sélectionnez une proposition enregistrée, puis cliquez sur
**Factures Word…**. Cette fonction est disponible dans chaque module de travail.

## Préparer votre modèle

Dans une copie de votre facture Word habituelle, remplacez les valeurs à remplir
par les champs suivants, avec les doubles accolades :

| Champ obligatoire | Valeur insérée |
| --- | --- |
| `{{NUMERO_FACTURE}}` | Code unique, par exemple AB-123-456 |
| `{{POIDS}}` | Poids total, avec deux décimales |
| `{{COLIS}}` | Total des colis |
| `{{FOB}}` | FOB total, avec deux décimales |
| `{{PLAQUE}}` | Plaque du modèle généré sélectionné |

Champs facultatifs : `{{DATE_FACTURE}}`, `{{IMPORTATEUR}}`,
`{{MODELE_ID}}`, `{{NUMERO_MANIFESTE}}`. La date utilise le fuseau Africa/Lubumbashi.

Les champs peuvent être placés dans les paragraphes, les tableaux, les en-têtes
et les pieds de page. Gardez les unités **kg** et **USD** à côté des champs.
Les montants sont formatés en français, par exemple `1 234,50`.

## Charger puis générer

1. Cliquez sur **Charger un modèle Word…** et choisissez votre fichier `.docx`.
   AsyDec analyse le document et en conserve une copie dans la bibliothèque.
2. Sélectionnez le modèle de facture souhaité dans la liste.
3. Cliquez sur **Créer ou télécharger la facture du modèle…**, puis choisissez où enregistrer le Word.

Les totaux proviennent de la proposition enregistrée sélectionnée. Les logos,
images, tableaux et styles du modèle sont conservés ; seuls les champs sont
remplacés. Un texte plus long peut modifier le retour à la ligne : vérifiez la
facture dans Word avant de l'envoyer. Le fichier original n'est jamais modifié.

Une facture n’est créée qu’à la demande, pour un modèle déjà enregistré, après
le choix du fichier de destination. Annuler ce choix ne crée aucun document et
ne réserve aucun numéro. Un modèle conserve une seule facture : les demandes
suivantes reprennent exactement le document archivé avec ses mêmes numéros.
Pour retrouver une facture existante, sélectionnez-la dans
**Factures archivées**, puis cliquez sur **Télécharger la facture sélectionnée…**.
En cas d’échec d’écriture du fichier, la facture reste disponible dans cette liste.

Les modèles et les factures sont archivés dans `DONNEES/factures.db`.
Les codes facture et les numéros de manifeste sont tirés aléatoirement puis
réservés dans `CONFIG_LOCAL/numeros_factures.db`, avec des contraintes d’unicité.
Une collision provoque un nouveau tirage. Une réservation ne peut être ni
modifiée ni supprimée, même si la génération échoue ensuite. Ce registre est
conservé lors d’une réinitialisation de l’application : les numéros ne sont
pas remis en circulation.

Sauvegardez ces deux bases avec `DONNEES/modeles_generes.db`. Cette garantie
s’applique à l’installation et à son registre conservé ; plusieurs ordinateurs
indépendants ne partagent pas automatiquement leurs numéros.

## Import automatique d’une facture existante

Les fichiers contenant un tableau commercial avec les colonnes `N°`, `Goods
Description`, `Quantity`, `U. Price`, `Total Price`, et une liste de colisage
avec `N°`, `Goods Description`, `Quantity`, `Unit W`, `Total Weight`, sont
préparés automatiquement au chargement. Aucun ajout manuel de champ n’est
nécessaire. Les deux tableaux doivent contenir les mêmes articles dans le même ordre.

La préparation conserve les libellés, adresses, styles, tableaux, dessins et
signatures. Elle repère les quantités par article, prix unitaires (FOB par
colis, quatre décimales), FOB par article, poids par article, totaux FOB,
fret, assurance et CIF en USD, numéro et date de facture, ainsi que les totaux
PKG et Total Weight du manifeste. Le numéro du manifeste est remplacé par un numéro aléatoire unique, de forme
`1234-ML5678`, dans chacune de ses représentations Word. Sa date et les autres
informations qui ne sont pas prévues comme champs restent celles de l’original.

Avant l’émission, une fenêtre présente les libellés du Word face aux désignations
de la proposition. Confirmez seulement s’ils correspondent dans le même ordre.
Un nombre d’articles différent bloque la génération afin de ne pas remplir une
facture pour d’autres marchandises. Les coordonnées commerciales du Word restent
celles de votre modèle : choisissez celui du bon fournisseur et du bon destinataire.


## Bibliothèque indépendante et propositions

**Outils communs → Modèles de facture** est accessible sans dossier ouvert.
Ajoutez vos fichiers Word à cet endroit ou depuis la fenêtre Factures Word d’un
modèle généré. L’analyse affiche les articles, champs, fournisseur, destinataire
et la présence d’une zone pour la plaque. L’import seul ne crée aucune facture.

La plaque doit être renseignée et enregistrée dans **Modèles générés** avant la
création. Elle est reprise automatiquement, à la place de la plaque d’exemple du
Word. Dans le modèle UMBA fourni, la zone de saisie vide à côté de REGISTRATION
NO’S est reconnue dans les deux représentations du manifeste. Pour les autres
modèles, une zone explicitement libellée PLAQUE/TRUCK NO/REGISTRATION NUMBER est
reconnue ; à défaut, placez `{{PLAQUE}}` dans le Word à l’endroit souhaité puis
rechargez-le. Aucune zone ni mise en page n’est ajoutée automatiquement.

Dans le résumé du modèle généré, une facture est conseillée si ses libellés
correspondent dans le même ordre. Les recommandations apparaissent aussi en tête
de la liste dans **Factures Word…**. Un nombre d’articles identique sans
correspondance des libellés reste un choix manuel. Un destinataire différent
repéré dans le Word empêche la recommandation automatique et doit être vérifié.
La confirmation de l’ordre des articles reste demandée avant l’émission.

## Word dont la structure est inconnue

Un Word valide peut être ajouté à la bibliothèque même si ses tableaux ne sont
pas reconnus automatiquement. Il apparaît comme **champs à configurer**.
Sélectionnez-le puis **Configurer les champs…** : choisissez un paragraphe,
indiquez la valeur exacte à remplacer et associez-la au champ correspondant.
Gardez les unités et les libellés hors de la valeur à remplacer. Répétez pour
chaque occurrence, y compris les valeurs par article et la liste de colisage.

Les associations peuvent être complétées en plusieurs étapes. La génération
reste bloquée tant que les champs obligatoires ne sont pas prêts. Seuls les
textes choisis changent ; les tableaux, images, styles et fichiers d’origine
restent conservés. Aucun Word intermédiaire n’est créé.

# Installateurs AsyDec

## Installer

- Windows 10/11 (64 bits) : lancer `AsyDec-Setup-windows-x64.exe`. L’installation se fait pour l’utilisateur courant, sans compte administrateur. Le menu Démarrer et le désinstalleur sont créés ; le raccourci Bureau est facultatif.
- Mac avec puce **Apple M1, M2, M3 ou M4** : ouvrir `AsyDec-Mac-Apple-Silicon-M1-M2-M3-M4.dmg`, puis glisser AsyDec dans Applications.
- Mac avec processeur **Intel** : même procédure avec `AsyDec-Mac-Intel.dmg`.
- Pour savoir quel Mac vous avez : menu  › *À propos de ce Mac*. « Puce Apple M… » = Apple Silicon ; « Processeur Intel » = Intel.
  Les puces M1, M2, M3 et M4 utilisent la même version. La page « Mises à jour Mac » d’AsyDec affiche aussi le type de ce Mac.
- Les fichiers `AsyDec-macos-arm64.*` et `AsyDec-macos-x86_64.*` servent aux mises à jour automatiques ; ils ne sont pas à installer à la main.

Les dépendances, dont Pillow pour le sceau bleu, sont téléchargées pendant la construction
et incluses dans l’application. Aucun téléchargement Python supplémentaire n’est nécessaire
lors de l’installation du produit compilé. Microsoft Word reste nécessaire pour la conversion PDF.

Pour une installation depuis les sources, double-cliquer sur `INSTALLER.command` (Mac)
ou `INSTALLER.bat` (Windows), avec Python 3.10 ou plus récent et une connexion Internet.

Python n’est pas nécessaire sur le poste destinataire. Les données personnelles ne sont pas incluses dans les installateurs. Les données de l’application restent dans `%LOCALAPPDATA%\AsyDec` sur Windows et `~/Library/Application Support/AsyDec` sur Mac. La désinstallation ne supprime pas ces données.

## Connexion sur une autre machine ou compte illisible

Le compte est local à chaque ordinateur. Sur l’écran de connexion, **Créer un compte**
permet de créer son identifiant et son mot de passe (au moins 8 caractères) s’il n’existe
pas encore de compte. Si le fichier du compte est illisible, cette même action propose
de conserver une copie datée dans `CONFIG_LOCAL`, puis de créer un nouveau compte,
après confirmation. Les dossiers, factures, modèles et numéros réservés sont conservés.
Un compte lisible existant ne peut pas être remplacé par ce bouton.

Créer un compte ne synchronise pas les ordinateurs. Pour reprendre les informations
de l’ancienne machine, utiliser le transfert `.asydec` décrit ci-dessous ; un import complet
reprend aussi le compte de l’export. Si ce compte est illisible, revenir à **Créer un compte**.
Cette fonction est disponible dans les nouvelles releases Windows et Mac ; installer
la nouvelle version sur chaque machine pour voir le bouton.

## Mises à jour Windows

Dans **Mises à jour Windows**, cliquer sur **Vérifier les mises à jour**, puis
**Télécharger et installer…**. AsyDec recherche la publication Windows, vérifie
l’empreinte du téléchargement et ouvre le setup dans le dossier de l’application
actuelle. Suivre l’assistant d’installation puis relancer AsyDec ; les données restent conservées.

Si le dépôt est privé, renseigner un jeton GitHub en lecture seule ayant accès au dépôt,
puis cliquer sur **Utiliser le jeton pour cette session** avant de relancer la recherche.
Sous Windows, le jeton reste uniquement en mémoire et doit être renseigné après un redémarrage.

Une ancienne installation dont le bouton utilise encore le mécanisme Mac doit d’abord
recevoir manuellement le nouveau `AsyDec-Setup-windows-x64.exe` contenant cette correction.

## Sauvegarde complète chiffrée dans les releases

Dans **Paramètres › Sauvegarde chiffrée** :

1. Choisir un mot de passe de sauvegarde d’au moins 12 caractères, le confirmer, puis
   **Créer un export complet chiffré…**. Le fichier `.asydec.enc` inclut le compte, les
   dossiers, les factures, les réglages et les modèles persistants CVI/BL, DEC et factures.
2. Pour le déposer sur GitHub, renseigner un jeton avec accès **Contents en écriture** au
   dépôt AsyDec, saisir à nouveau le mot de passe et cliquer sur **Publier un fichier chiffré…**.
   Après confirmation, une release de sauvegarde séparée est créée, sans modifier la release
   de mise à jour du logiciel. Aucun export en clair n’est envoyé par cette fonction.
3. Sur l’autre ordinateur, **Rechercher les sauvegardes sur GitHub**, sélectionner la sauvegarde,
   saisir le mot de passe, puis **Télécharger et charger avec mon mot de passe…**.
   Le mot de passe du compte local est également demandé avant de remplacer des données existantes.
4. Le chiffrement et l’intégrité sont vérifiés avant de préparer l’import. AsyDec redémarre,
   met les anciennes données de côté et charge la sauvegarde. Se connecter avec le compte de l’export.
   Un fichier `.asydec.enc` peut aussi être chargé localement, ou au premier démarrage sans compte.

Le chiffrement utilise AES-256-GCM et une clé dérivée du mot de passe par scrypt avec un sel
aléatoire. Le mot de passe n’est enregistré ni dans le code, ni dans les préférences, ni sur GitHub ;
il doit être conservé séparément. Sans ce mot de passe, la sauvegarde ne peut pas être récupérée.
Le jeton GitHub saisi ici n’est utilisé que pour l’opération et n’est pas enregistré.
Sur une release publique, le fichier chiffré reste téléchargeable par un lien direct : le mot de passe
protège son contenu. Dans l’application, il est demandé avant de lancer le téléchargement.
Les mises à jour du logiciel ne chargent jamais une sauvegarde automatiquement.

## Passer sur une nouvelle machine

Les modèles Word privés (CVI, déclaration de licence, facture Kinshop) sont inclus seulement
s’ils sont présents lors de la construction. Sans les Word Kinshop, AsyDec produit ses propres
factures à partir des informations de licence ; un modèle Word peut aussi être choisi depuis
la bibliothèque. Les données de travail ne sont pas incluses ; elles se transfèrent par un fichier `.asydec` :

- **Remplacer son ordinateur** : ancienne machine › Paramètres › *Transfert vers une autre machine* ›
  « Exporter toutes mes données… ». Sur la nouvelle : au premier lancement, répondre **Oui** et choisir le fichier
  (ou, plus tard, Paramètres › Transfert › « Remplacer mes données par un export complet… »). Compte, mot de passe,
  numéros de facture réservés, modèles, dossiers et licences sont repris ; les chemins de l’ancienne machine
  sont adaptés automatiquement.
  Les fichiers produits dans le dossier de travail AsyDec (dont CVI/BL et déclarations) sont également repris,
  même si ce dossier était situé ailleurs que les données de l’application. Ils sont restaurés dans
  `ESPACE_TRAVAIL` sur la nouvelle machine et restent accessibles par les boutons d’ouverture de dossier.
  Le dossier `7 - TRANSFERTS` est exclu pour éviter d’imbriquer d’anciens exports ; les sauvegardes du dossier
  de travail ne sont incluses que si l’option d’inclusion des sauvegardes est cochée.
- **Préparer une nouvelle installation à partir de votre poste** : « Exporter une base d’installation (modèles seulement)… »,
  puis sur la nouvelle machine, au premier démarrage, répondre **Oui** et choisir le fichier `.asydec`
  (ou Paramètres › Transfert › « Importer des modèles… »). Les modèles **CVI et BL**, **déclaration DEC**,
  facture et packing list sont inclus, avec les modèles de la bibliothèque, XML de référence et médiathèque XML ;
  ni compte, ni historique, ni numéros.
- Les boutons **Définir le modèle CVI / BL…** et **Définir le modèle déclaration DEC…** permettent d’enregistrer
  les modèles Word préparés dans l’application avant export. Un modèle choisi lors d’une génération réussie
  est aussi conservé automatiquement. Ces copies restent dans les données utilisateur lors d’une mise à jour.
- Sur le nouveau poste, les modèles importés sont utilisés automatiquement : plus besoin de chercher les fichiers
  de l’ancien ordinateur pour générer le BL ou la déclaration. Un modèle personnel déjà installé n’est pas écrasé
  par l’import d’une base. Installer la nouvelle version d’AsyDec sur les deux postes avant de créer ou importer
  ces exports au format 2 ; les anciens exports au format 1 restent acceptés par la nouvelle version.
- Un ancien dossier `OUTILS` copié tel quel reste accepté (« Depuis un ancien dossier OUTILS… »).

Lors d’un remplacement, les données présentes sont d’abord déplacées dans `SAUVEGARDES/avant-import-…` :
rien n’est effacé. Deux machines utilisées en même temps ne se synchronisent pas : utiliser une seule machine
pour émettre les factures, ou transférer à nouveau après chaque changement de poste.

Les versions actuelles ne sont pas signées par un certificat éditeur Windows ni notarisées par Apple. Le système peut demander une autorisation d’ouverture.

## Construire

Python 3.12 et les dépendances du projet :

```sh
python -m pip install -r requirements.txt pyinstaller==6.22.3
```

Sur Mac : `python scripts/construire_mac.py`.
Sur Windows x64, installer Inno Setup 6 puis exécuter `python scripts/construire_windows.py`.
Les résultats sont dans `dist/`.

Les workflows GitHub Actions `Application macOS` et `Installateur Windows` construisent les fichiers sur leurs systèmes respectifs à chaque push sur main ou sur lancement manuel. Les installateurs sont accessibles dans les artefacts de la construction et dans les Releases après validation.

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

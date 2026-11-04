# Installateurs AsyDec

## Installer

- Windows 10/11 (64 bits) : lancer `AsyDec-Setup-windows-x64.exe`. L’installation se fait pour l’utilisateur courant, sans compte administrateur. Le menu Démarrer et le désinstalleur sont créés ; le raccourci Bureau est facultatif.
- Mac Intel : ouvrir `AsyDec-macos-x86_64.dmg`, puis glisser AsyDec dans Applications.
- Mac Apple Silicon : même procédure avec `AsyDec-macos-arm64.dmg`.

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

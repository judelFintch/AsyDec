# AsyDec pour macOS

L’application fonctionne hors ligne, sans expiration, quota de factures ou
limite de générations. Les mises à jour restent facultatives.

## Application locale

La première construction se trouve dans `dist/AsyDec.app` ; l’archive de
transport est `dist/AsyDec-macos-x86_64.zip` pour le Mac utilisé ici. Copiez la
`.app` dans `~/Applications` (Applications de votre compte), puis ouvrez-la.
La version Intel requiert un Mac Intel ou Rosetta sur Apple Silicon. Le workflow
GitHub construit aussi une version native arm64.

Au premier lancement, l’application propose de copier les données de l’ancien
dossier OUTILS. Fermez d’abord l’ancienne version et sélectionnez OUTILS. La
source reste intacte, aucune donnée existante n’est écrasée. Le compte, les
modèles Word, les factures et le registre permanent des numéros sont conservés.
Les documents exportés restent dans le dossier de travail choisi auparavant.

Les données internes de la version installée résident dans
`~/Library/Application Support/AsyDec/`, hors de l’application. Le remplacement
du `.app` ne les efface pas. Pour un diagnostic isolé, `ASYDEC_HOME` permet de
rediriger ces données vers un dossier de test.

## Construction reproductible

Depuis un environnement Python 3.12 sous macOS :

```sh
python -m pip install -r requirements.txt 'pyinstaller==6.22.3'
python scripts/construire_mac.py
```

Le paquet contient le programme et ses dépendances, sans inclure les données,
comptes, modèles commerciaux ou fichiers personnels du développeur. La version
et l’identifiant de révision sont intégrés. Une construction locale avec des
modifications non commitées est identifiée comme telle.

## Mises à jour GitHub

Le workflow `.github/workflows/macos.yml` se déclenche à chaque push sur `main`
ou manuellement. Il teste et construit les applications Intel et Apple Silicon.
Une GitHub Release n’est publiée qu’après réussite des deux constructions.

Dans **Outils communs → Mises à jour Mac**, l’application consulte cette Release
au démarrage ou à votre demande. Le dépôt public `judelFintch/AsyDec` ne nécessite
pas de jeton. Pour une distribution privée, un jeton GitHub en lecture seule
peut être enregistré dans le Trousseau macOS, jamais dans le code du programme.

L’utilisateur choisit d’installer. Le téléchargement HTTPS est vérifié par son
SHA-256 publié avec la construction. Les chemins et liens de l’archive sont
contrôlés et la signature technique du `.app` est vérifiée. L’application se
ferme, le processus auxiliaire remplace uniquement le `.app`, puis le relance.
`AsyDec-version-precedente.app` est conservée à côté. Si le remplacement ou la
commande de lancement échoue, la version précédente est remise en place.
Ce retour arrière ne restaure pas les bases : les changements de schéma futurs
devront rester compatibles ou être accompagnés d’une migration sauvegardée.

## Signature Apple et activation

La construction locale utilise une signature technique ad hoc. Ce n’est pas une
signature Developer ID ni une notarisation Apple ; macOS peut demander une
validation à l’ouverture d’un téléchargement. La distribution sans ces alertes
nécessite votre identité Developer ID et la notarisation ; aucun contournement
de Gatekeeper n’est effectué.

`ASYDEC_CODESIGN_IDENTITY` permet d’utiliser une identité de signature déjà
installée dans le Trousseau de la machine de construction. Le workflow fourni
ne contient aucun certificat ni secret Apple.

Le workflow et le code doivent être poussés sur GitHub pour activer la
publication. Une application locale seule ne crée aucune Release distante.

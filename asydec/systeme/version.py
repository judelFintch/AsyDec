"""Identité de la construction ; aucune expiration ni limitation de fonctionnalités."""
import json
from pathlib import Path


def courante():
    try:
        return json.loads((Path(__file__).resolve().parents[1]/'construction.json').read_text())
    except (OSError, ValueError):
        return {'revision':'developpement','build':0,'version':'développement'}

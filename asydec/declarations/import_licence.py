"""Lecture locale de licences PDF et photos, sans envoi externe."""
from pathlib import Path
import re
import unicodedata


def extraire_champs(texte):
    """Ne propose que les valeurs associées à un libellé ; ambiguïté = saisie manuelle."""
    texte = ''.join(c for c in unicodedata.normalize('NFD', texte) if not unicodedata.combining(c))
    motifs = {
        'numero_dec': r'(?:n[°ºo]?\s*(?:de\s*)?dec|numero\s*(?:de\s*)?dec|\bdec)\s*[:#=\-]?\s*([A-Z0-9][A-Z0-9/._-]*)',
        'numero_validation': r'(?:n[°ºo]?\s*(?:de\s*)?validation|numero\s*(?:de\s*)?validation)(?:\s*(?:de\s*)?(?:la\s*)?licence)?\s*[:#=\-]?\s*([A-Z0-9][A-Z0-9/._-]*)',
        'date_validation': r'date\s*(?:de\s*)?validation(?:\s*(?:de\s*)?(?:la\s*)?licence)?\s*[:=\-]?\s*(\d{1,2}[/.-]\d{1,2}[/.-]\d{4})',
        'montant_fob': r'(?<![A-Z])(?:montant\s*)?f\.?o\.?b\.?\s*[:=]?\s*(?:(?:USD|EUR|CDF|\$)\s*)?([0-9][0-9 \u00a0\u202f.,]*)',
    }
    resultat = {}
    for cle, motif in motifs.items():
        valeurs = {m.strip() for m in re.findall(motif, texte, re.I)}
        if len(valeurs) != 1:
            continue
        valeur = valeurs.pop()
        if cle == 'date_validation':
            valeur = valeur.replace('-', '/').replace('.', '/')
        elif cle == 'montant_fob':
            valeur = re.sub(r'\s', '', valeur)
            if ',' in valeur and '.' in valeur:
                decimal = ',' if valeur.rfind(',') > valeur.rfind('.') else '.'
                valeur = valeur.replace('.' if decimal == ',' else ',', '').replace(decimal, '.')
            elif re.fullmatch(r'\d{1,3}(?:[,.]\d{3})+', valeur):
                # Un séparateur unique peut désigner des milliers ou des décimales.
                continue
        resultat[cle] = valeur
    return resultat


def lire_licence(chemin):
    import pymupdf
    chemin = Path(chemin)
    if chemin.suffix.lower() not in ('.pdf', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'):
        raise ValueError('Choisissez un PDF ou une photo PNG, JPEG, TIFF ou BMP.')
    moteur = None

    def ocr(image):
        nonlocal moteur
        from rapidocr_onnxruntime import RapidOCR
        if moteur is None:
            moteur = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        lignes, _ = moteur(image)
        return '\n'.join(ligne[1] for ligne in (lignes or []))

    if chemin.suffix.lower() == '.pdf':
        with pymupdf.open(chemin) as doc:
            if doc.needs_pass:
                raise ValueError('Le PDF est protégé par mot de passe. Importez une copie déverrouillée.')
            if len(doc) > 20:
                raise ValueError('Importez uniquement la licence (20 pages maximum).')
            textes = []
            for page in doc:
                texte = page.get_text(sort=True)
                # Compléter par OCR si les libellés de la licence ne sont pas exploitables.
                if len(extraire_champs(texte)) < 4:
                    texte_ocr = ocr(page.get_pixmap(dpi=160, alpha=False).tobytes('png'))
                    texte = texte_ocr if len(extraire_champs(texte_ocr)) > len(extraire_champs(texte)) else texte
                textes.append(texte)
            texte = '\n'.join(textes)
    else:
        texte = ocr(str(chemin))
    if not texte.strip():
        raise ValueError('Aucun texte lisible détecté. Essayez une photo plus nette ou la saisie manuelle.')
    return extraire_champs(texte), texte

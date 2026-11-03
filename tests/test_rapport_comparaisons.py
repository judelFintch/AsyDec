"""Rapport des comparaisons : diagnostic de chaque comparaison, analyse d'ensemble, collecte et page."""
from decimal import Decimal as D
import json
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from asydec.declarations import comparaison_prediction as C
from asydec.declarations import modeles_generes as M
from asydec.declarations import rapport_comparaisons as R
from tests import test_modeles_generes as TM

MODELE = dict(id=1, plaque='T1', importateur='KDMETA', statut='en_attente', note=None)


def ligne(position, metrique, prevu, fourni, code='6309', designation='FRIPERIE', libelle=None):
    ecart = D(fourni) - D(prevu)
    return dict(position=position, code=code if position != 'Total global' else '', designation=designation,
                metrique=metrique, libelle=libelle or metrique, prevu=D(prevu), fourni=D(fourni), ecart=ecart,
                pourcentage=ecart / abs(D(prevu)) * 100 if D(prevu) else None,
                etat='Identique' if ecart == 0 else 'Écart observé')


def taxe(position, code, estime, compare, etat=None):
    ecart = D(compare) - D(estime)
    return dict(position=position, article='6309', taxe=code, estime=D(estime), compare=D(compare), ecart=ecart,
                pourcentage=ecart / D(estime) * 100, etat=etat or ('Identique' if ecart == 0 else 'Écart observé'))


def rapport(taxes_articles=('1000', '1000'), globales=('500', '500'), poids=('100', '100'), fob=('50', '50'),
            taux=('2000', '2000'), contexte=(), detail=None):
    total = (str(D(taxes_articles[0]) + D(globales[0])), str(D(taxes_articles[1]) + D(globales[1])))
    lignes = [ligne(1, 'poids', *poids), ligne(1, 'fob', *fob), ligne(1, 'colis', '10', '10'),
              ligne(1, 'ratio', str(D(fob[0]) / D(poids[0])), str(D(fob[1]) / D(poids[1]))),
              ligne(1, 'taxes', *taxes_articles),
              ligne('Total global', 'poids', *poids, libelle='Poids kg'), ligne('Total global', 'fob', *fob, libelle='FOB'),
              ligne('Total global', 'colis', '10', '10'), ligne('Total global', 'taxes', *total),
              ligne('Total global', 'taxes_articles', *taxes_articles),
              ligne('Total global', 'taxes_globales', *globales)]
    return dict(lignes=lignes, contexte=list(contexte), taux_genere=D(taux[0]), taux_fourni=D(taux[1]),
                taxes_detail=detail if detail is not None else [taxe('Total', 'DDI', *taxes_articles)])


def entree(r, evenement=1, modele=None, fichier='fourni.xml'):
    prevu, fourni = (next(l for l in r['lignes'] if l['position'] == 'Total global' and l['metrique'] == 'taxes')[k]
                     for k in ('prevu', 'fourni'))
    comparaison = dict(evenement=evenement, date_utc=f'2026-11-03T10:00:0{evenement}+00:00', auteur='alice',
                       fichier=fichier, total_estime=prevu, total_compare=fourni, ecart_total=fourni - prevu)
    return R.construire_entree(modele or MODELE, comparaison, r)


class DiagnosticTest(unittest.TestCase):
    def test_identique(self):
        self.assertEqual(entree(rapport())['diagnostic'], R.IDENTIQUE)

    def test_ecart_entierement_du_au_taux(self):
        # Taux −1 % : toutes les taxes baissent de 1 %, à l'arrondi près.
        e = entree(rapport(taxes_articles=('1000', '990'), globales=('500', '495'), taux=('2000', '1980')))
        self.assertEqual(e['diagnostic'], R.TAUX)
        self.assertEqual(e['ecart_hors_taux'], 0)

    def test_ecart_de_calcul_attribue_aux_taxes_globales(self):
        e = entree(rapport(globales=('500', '600')))
        self.assertEqual(e['diagnostic'], R.CALCUL)
        self.assertEqual(R.decomposition(e), {'articles': 0, 'globales': 100})
        phrases = R.constats([e])
        self.assertTrue(any(p.startswith('⚠ Modèle N° 1') for p in phrases))
        self.assertTrue(any('taxes globales' in p and 'telles quelles' in p for p in phrases))

    def test_arrondi_a_taux_egal_reste_identique(self):
        self.assertEqual(entree(rapport(taxes_articles=('1000', '1003')))['diagnostic'], R.IDENTIQUE)

    def test_repartition_differente(self):
        r = rapport(taxes_articles=('1000', '1200'))
        r['lignes'][0] = ligne(1, 'poids', '100', '120')
        e = entree(r)
        self.assertEqual(e['diagnostic'], R.REPARTITION)
        self.assertIn('Article(s) 1', e['raisons'][0])

    def test_autre_dossier(self):
        e = entree(rapport(poids=('100', '90'), taxes_articles=('1000', '1500'),
                           contexte=['Importateur différent : A → B.']))
        self.assertEqual(e['diagnostic'], R.AUTRE)
        self.assertEqual(e['raisons'][0], 'Importateur différent')
        self.assertIn('Poids kg 100 → 90', e['raisons'])

    def test_totaux_seuls(self):
        comparaison = dict(evenement=1, date_utc='2026-11-03T10:00:00+00:00', auteur='a', fichier='f.xml',
                           total_estime=D(10), total_compare=D(12), ecart_total=D(2))
        self.assertEqual(R.construire_entree(MODELE, comparaison, None, R.TOTAUX_SEULS)['diagnostic'], R.NON_VERIFIABLE)


class AnalyseTest(unittest.TestCase):
    def test_taxes_a_meme_ecart_regroupees_en_base_commune(self):
        detail = [taxe('Total', code, '1000', '1010') for code in ('RII', 'TPS', 'COG', 'RCC')]
        entrees = [entree(rapport(taxes_articles=('4000', '4040'), detail=detail), evenement=k) for k in (1, 2)]
        phrases = R.constats(entrees)
        self.assertTrue(any(p.startswith('4 taxes (') and 'base commune' in p for p in phrases), phrases)
        self.assertFalse(any(p.startswith('Taxe RII') for p in phrases))

    def test_taux_different_dans_le_bareme(self):
        detail = [taxe('1', 'DDI', '100', '120', etat='Taux différent'), taxe('Total', 'DDI', '1000', '1020')]
        phrases = R.constats([entree(rapport(taxes_articles=('1000', '1020'), detail=detail))])
        self.assertTrue(any(p.startswith('Taxe DDI : taux différent') for p in phrases))

    def test_ratio_article_et_autre_dossier(self):
        r = rapport(poids=('100', '100'), fob=('50', '60'), contexte=['Importateur différent : A → B.'])
        analyse = R.analyser([entree(r)])
        article = analyse['articles'][0]
        self.assertAlmostEqual(article['ratio_moyen'], 20.0)
        self.assertIsNone(article['poids_moyen'])  # poids d'un autre dossier : non comparable
        self.assertIsNone(article['taxes_moyen'])
        self.assertEqual(analyse['taxes'], [])     # taxes d'un autre dossier : exclues
        self.assertTrue(any('ratio FOB/kg +20' in p for p in analyse['constats']))

    def test_calcul_fiable_annonce(self):
        e = entree(rapport(taxes_articles=('1000', '990'), globales=('500', '495'), taux=('2000', '1980')))
        phrases = R.constats([e, entree(rapport(), evenement=2)])
        self.assertTrue(any(p.startswith('✓ Calcul fiable') for p in phrases))
        self.assertTrue(any('par le taux de change' in p for p in phrases))

    def test_aucune_comparaison(self):
        self.assertIn('Aucune comparaison', R.analyser([])['constats'][0])

    def test_export_excel(self):
        entrees = [entree(rapport(globales=('500', '600'))), entree(rapport(), evenement=2)]
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / 'rapport.xlsx'
            R.exporter(entrees, R.analyser(entrees), chemin)
            wb = load_workbook(chemin)
        self.assertEqual(wb.sheetnames, ['SYNTHESE', 'COMPARAISONS', 'TAXES', 'ARTICLES', 'IMPORTATEURS'])
        self.assertEqual(wb['COMPARAISONS'].max_row, 3)
        self.assertEqual(wb['COMPARAISONS']['F2'].value, R.CALCUL)


class CollecteTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.export = self.racine / 'export.xml'
        self.export.write_bytes(self.xml)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)
        self.fourni = self.racine / 'fourni.xml'
        self.fourni.write_bytes(self.xml)

    def test_comparaison_repetee_comptee_une_fois(self):
        r = C.comparer_xmls(self.export, self.fourni)
        M.noter_comparaison(self.identifiant, self.fourni, r, 'alice', base=self.base)
        M.noter_comparaison(self.identifiant, self.fourni, r, 'bob', base=self.base)
        entrees = R.collecter(base=self.base)
        self.assertEqual(len(entrees), 1)
        self.assertEqual(entrees[0]['repetitions'], 2)
        self.assertEqual(entrees[0]['diagnostic'], R.IDENTIQUE)
        self.assertEqual(R.analyser(entrees)['indicateurs']['repetees'], 1)

    def ancienne_trace(self):
        """Trace d'avant la conservation du rapport : totaux et empreinte seulement."""
        with M._connexion(self.base) as conn:
            M._evenement(conn, self.identifiant, 'alice', M.COMPARAISON, detail=json.dumps({
                'fichier': str(self.fourni), 'sha256': M._sha(self.fourni.read_bytes()),
                'total_estime': '250', 'total_compare': '250', 'ecart_total': '0'}))

    def test_ancienne_trace_reconstituee(self):
        self.ancienne_trace()
        e = R.collecter(base=self.base)[0]
        self.assertEqual(e['origine'], R.DETAIL_RECONSTITUE)
        self.assertTrue(e['rapport']['taxes_detail'])

    def test_ancienne_trace_fichier_modifie(self):
        self.ancienne_trace()
        self.fourni.write_bytes(self.xml + b' ')
        e = R.collecter(base=self.base)[0]
        self.assertEqual(e['origine'], R.TOTAUX_SEULS)
        self.assertIsNone(e['rapport'])

    def test_lecture_seule(self):
        r = C.comparer_xmls(self.export, self.fourni)
        M.noter_comparaison(self.identifiant, self.fourni, r, 'alice', base=self.base)
        avant = self.base.read_bytes()
        R.analyser(R.collecter(base=self.base))
        self.assertEqual(self.base.read_bytes(), avant)


class PageTest(unittest.TestCase):
    def test_page_remplie_et_filtree(self):
        from asydec.ui.rapport_comparaisons import PageRapportComparaisons
        entrees = [entree(rapport(globales=('500', '600'))),
                   entree(rapport(), evenement=2, modele=dict(MODELE, id=2, importateur='SHABANI'))]
        racine = tk.Tk()
        racine.withdraw()
        self.addCleanup(racine.destroy)
        with patch.object(R, 'collecter', return_value=entrees):
            page = PageRapportComparaisons(racine, SimpleNamespace(module_travail='friperie'))
            page.afficher()
        table = page.tables['comparaisons']
        self.assertEqual(len(table.get_children()), 2)
        self.assertEqual(page.cartes['calcul'].valeur.get(), '1')
        self.assertIn('⚠', page.constats.get('1.0', 'end'))
        page.filtre.set(R.CALCUL)
        page.remplir_comparaisons()
        self.assertEqual(table.get_children(), ('1',))
        page.filtre.set('Tous les diagnostics')
        page.filtre_importateur.set('SHABANI')
        page.recalculer()
        self.assertEqual(table.get_children(), ('2',))


if __name__ == '__main__':
    unittest.main()

"""Plaque des modèles validés, trace des comparaisons et détail des taxes, sur données temporaires."""
from decimal import Decimal
import hashlib
import json
import sqlite3
import unittest
from pathlib import Path

from asydec.declarations import comparaison_prediction as C
from asydec.declarations import export_pdf as P
from asydec.declarations import modeles_generes as M
from tests import test_modeles_generes as TM


class PlaqueEtTraceTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)

    def valider(self):
        M.changer_statut(self.identifiant, 'valide', 'alice', base=self.base)

    def test_plaque_exige_validation_et_normalise(self):
        self.assertRaisesRegex(ValueError, 'Validé', M.definir_plaque, self.identifiant, 'T546ECQ', 'alice', base=self.base)
        self.valider()
        self.assertEqual(M.definir_plaque(self.identifiant, '  t546ecq / t618ect ', 'alice', base=self.base),
                         'T546ECQ / T618ECT')
        for invalide in ('', '   ', '../etc', 'A' * 41, 'T5;46'):
            self.assertRaises(ValueError, M.definir_plaque, self.identifiant, invalide, 'alice', base=self.base)
        self.assertRaises(ValueError, M.definir_plaque, 999, 'T1', 'alice', base=self.base)

    def test_plaque_visible_sans_doublon_et_snapshot_intact(self):
        self.valider()
        avant = sqlite3.connect(self.base).execute('SELECT resultat_json FROM modeles').fetchone()
        M.definir_plaque(self.identifiant, 'T546ECQ', 'alice', base=self.base)
        M.definir_plaque(self.identifiant, 't546ecq', 'bob', base=self.base)
        d = M.detail(self.identifiant, base=self.base)
        self.assertEqual(d['plaque'], 'T546ECQ')
        self.assertEqual([e['action'] for e in d['evenements']].count('plaque'), 1)
        self.assertEqual(d['statut'], 'valide')
        self.assertEqual(M.lister('valide', base=self.base)[0]['plaque'], 'T546ECQ')
        self.assertTrue(M.nom_export(d).startswith('T546ECQ - '))
        self.assertEqual(sqlite3.connect(self.base).execute('SELECT resultat_json FROM modeles').fetchone(), avant)
        M.definir_plaque(self.identifiant, 'T618ECT', 'bob', base=self.base)
        self.assertEqual(M.detail(self.identifiant, base=self.base)['plaque'], 'T618ECT')

    def test_sans_saisie_plaque_du_xml(self):
        d = M.detail(self.identifiant, base=self.base)
        self.assertEqual(d['plaque'], d['resultat']['info'].get('camion') or '')

    def test_trace_comparaison_et_liste(self):
        self.assertEqual(M.lister(base=self.base)[0]['comparaisons'], 0)
        fourni = self.racine / 'fourni.xml'
        fourni.write_bytes(b'<ASYCUDA/>')
        rapport = {'plaque_fournie': 'T9', 'lignes': [dict(position='Total global', metrique='taxes',
                   prevu=Decimal('100'), fourni=Decimal('130'), ecart=Decimal('30'))]}
        M.noter_comparaison(self.identifiant, fourni, rapport, 'alice', base=self.base)
        M.noter_comparaison(self.identifiant, fourni, rapport, 'bob', base=self.base)
        ligne = M.lister(base=self.base)[0]
        self.assertEqual(ligne['comparaisons'], 2)
        self.assertIsNotNone(ligne['compare_utc'])
        evenement = M.detail(self.identifiant, base=self.base)['evenements'][-1]
        detail = json.loads(evenement['detail'])
        self.assertEqual(detail['sha256'], hashlib.sha256(b'<ASYCUDA/>').hexdigest())
        self.assertEqual(detail['ecart_total'], '30')
        self.assertIn('Comparé avec fourni.xml', M.resume_evenement(evenement))
        self.assertIn('30 CDF', M.resume_evenement(evenement))
        self.assertEqual(fourni.read_bytes(), b'<ASYCUDA/>')
        self.assertRaises(ValueError, M.noter_comparaison, 999, fourni, rapport, 'alice', base=self.base)

    def test_modele_retrouve_par_export_exact(self):
        export = self.racine / 'export.xml'
        export.write_bytes(self.xml)
        M.enregistrer(self.resultat, self.source, 'alice', export=export, base=self.base)
        self.assertEqual(M.modele_par_export(self.xml, base=self.base), self.identifiant)
        self.assertIsNone(M.modele_par_export(self.xml + b' ', base=self.base))

    def test_pdf_modele_plaque_et_comparaisons(self):
        self.valider()
        M.definir_plaque(self.identifiant, 'T546ECQ', 'alice', base=self.base)
        pdf = self.racine / 'modele.pdf'
        P.pdf_modele(M.detail(self.identifiant, base=self.base), pdf, 'alice')
        octets = pdf.read_bytes()
        self.assertIn(b'Plaque : T546ECQ', octets)
        self.assertIn('Comparé avec un XML : jamais'.encode('cp1252'), octets)


class DetailTaxesModeleTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.export = self.racine / 'export.xml'
        self.export.write_bytes(self.xml)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)

    def detail(self):
        return M.detail_taxes_modele(M.detail(self.identifiant, base=self.base), base=self.base)

    def test_jamais_compare_estime_seul(self):
        lignes, explication = self.detail()
        self.assertTrue(lignes)
        self.assertIn('jamais été comparé', explication)
        self.assertTrue(all(l['compare'] is None for l in lignes if l['position'] not in ('Total', 'Globale')))

    def test_dernier_xml_compare_relu(self):
        fourni = self.racine / 'fourni.xml'
        fourni.write_bytes(self.xml)
        rapport = C.comparer_xmls(self.export, fourni)
        M.noter_comparaison(self.identifiant, fourni, rapport, 'alice', base=self.base)
        lignes, explication = self.detail()
        self.assertIn('fourni.xml', explication)
        self.assertTrue(any(l['compare'] is not None for l in lignes))
        self.assertEqual(fourni.read_bytes(), self.xml)

    def test_xml_compare_modifie_ou_absent(self):
        fourni = self.racine / 'fourni.xml'
        fourni.write_bytes(self.xml)
        M.noter_comparaison(self.identifiant, fourni, {'lignes': []}, 'alice', base=self.base)
        fourni.write_bytes(self.xml + b' ')
        self.assertIn('modifié', self.detail()[1])
        fourni.unlink()
        self.assertIn('introuvable', self.detail()[1])


def taxe(code, montant, taux='10', base='1000'):
    return {'code': code, 'montant': montant, 'taux': taux, 'base': base}


class DetailTaxesTest(unittest.TestCase):
    def donnees(self, articles, globales=()):
        return {'articles': [{'position': p, 'code': '6309', 'taxes': t} for p, t in articles],
                'taxes_globales': list(globales)}

    def test_estime_compare_ecarts_totaux_et_globales(self):
        genere = self.donnees([(1, [taxe('DDI', '100'), taxe('TVA', '160', '16')]), (2, [taxe('DDI', '50')])],
                              [taxe('RLS', '20')])
        fourni = self.donnees([(1, [taxe('DDI', '120'), taxe('TVA', '160', '16')]), (2, [taxe('DDI', '50', '12')]),
                               (3, [taxe('DDI', '7')])], [taxe('RLS', '25')])
        lignes = {(l['position'], l['taxe']): l for l in C.detail_taxes(genere, fourni)}
        ddi = lignes[(1, 'DDI')]
        self.assertEqual((ddi['estime'], ddi['compare'], ddi['ecart']), (Decimal(100), Decimal(120), Decimal(20)))
        self.assertEqual(ddi['pourcentage'], Decimal(20))
        self.assertEqual(ddi['etat'], 'Écart observé')
        self.assertEqual(lignes[(1, 'TVA')]['etat'], 'Identique')
        self.assertEqual(lignes[(2, 'DDI')]['etat'], 'Taux différent')
        self.assertEqual(lignes[(3, 'DDI')]['etat'], 'Absente du XML généré')
        total = lignes[('Total', 'DDI')]
        # Une ligne absente d'un côté rend le total incomplet plutôt qu'une somme trompeuse.
        self.assertIsNone(total['estime'])
        self.assertEqual(total['compare'], Decimal(177))
        self.assertEqual(lignes[('Total', 'TVA')]['ecart'], Decimal(0))
        self.assertEqual(lignes[('Globale', 'RLS')]['ecart'], Decimal(5))

    def test_code_repete_non_fusionne(self):
        genere = self.donnees([(1, [taxe('COG', '1'), taxe('COG', '2')])])
        fourni = self.donnees([(1, [taxe('COG', '1')])])
        etats = [l['etat'] for l in C.detail_taxes(genere, fourni) if l['position'] == 1]
        self.assertEqual(etats, ['Identique', 'Absente du fichier fourni'])

    def test_comparer_xmls_fournit_detail_plaques_et_pdf(self):
        TM.ModelesGeneresTest.setUp(self)
        rapport = C.comparer_xmls(self.source, self.source)
        self.assertTrue(rapport['taxes_detail'])
        self.assertTrue(all(l['etat'] in ('Identique', 'Donnée absente') for l in rapport['taxes_detail']))
        self.assertIn('plaque', rapport)
        self.assertIn('plaque_fournie', rapport)
        pdf = self.racine / 'comparaison.pdf'
        P.pdf_comparaison(rapport, pdf, 'alice')
        self.assertIn('Détails des taxes'.encode('cp1252'), pdf.read_bytes())


if __name__ == '__main__':
    unittest.main()


TRANSPORT = (b'<ASYCUDA><Transport><Means_of_transport><Departure_arrival_information><Identity>OLD1</Identity>'
             b'<Nationality>ZM</Nationality></Departure_arrival_information><Border_information><Identity/>'
             b'<Mode>30</Mode></Border_information></Means_of_transport></Transport>'
             b'<Seals><Identity><null/></Identity></Seals></ASYCUDA>')


class PlaqueDansXmlTest(unittest.TestCase):
    def test_deux_champs_remplaces_reste_intact(self):
        nouveau = P_appliquer(TRANSPORT, 't546ecq/t618ect')
        self.assertEqual(nouveau.count(b'<Identity>T546ECQ/T618ECT</Identity>'), 2)
        self.assertIn(b'<Seals><Identity><null/></Identity></Seals>', nouveau)
        self.assertEqual(nouveau.replace(b'<Identity>T546ECQ/T618ECT</Identity>', b''),
                         TRANSPORT.replace(b'<Identity>OLD1</Identity>', b'').replace(b'<Identity/>', b''))

    def test_sans_bloc_transport_refuse(self):
        self.assertRaises(ValueError, P_appliquer, b'<ASYCUDA><Seals><Identity/></Seals></ASYCUDA>', 'T1')
        self.assertRaises(ValueError, P_appliquer, TRANSPORT, '../x')


def P_appliquer(contenu, plaque):
    return M.appliquer_plaque(contenu, plaque)


class TelechargementAvecPlaqueTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        # Snapshot avec un vrai bloc transport, comme les XML SYDONIA.
        import xml.etree.ElementTree as ET
        racine = ET.fromstring(self.xml)
        racine.append(ET.fromstring(TRANSPORT).find('Transport'))
        self.resultat['info']['camion'] = 'OLD1'
        source = ET.ElementTree(ET.fromstring(self.source.read_bytes()))
        source.getroot().append(ET.fromstring(TRANSPORT).find('Transport'))
        source.write(self.source)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)
        M.changer_statut(self.identifiant, 'valide', 'alice', base=self.base)

    def test_sans_plaque_saisie_octets_inchanges(self):
        sortie = self.racine / 'a.xml'
        M.exporter_xml(self.identifiant, sortie, 'alice', base=self.base)
        self.assertEqual(sortie.read_bytes(), bytes(M.detail(self.identifiant, base=self.base)['modele_xml']))

    def test_plaque_saisie_inscrite_et_export_trace(self):
        M.definir_plaque(self.identifiant, 'T546ECQ/T618ECT', 'alice', base=self.base)
        sortie = self.racine / 'b.xml'
        M.exporter_xml(self.identifiant, sortie, 'alice', base=self.base)
        octets = sortie.read_bytes()
        self.assertEqual(octets.count(b'<Identity>T546ECQ/T618ECT</Identity>'), 2)
        self.assertNotIn(b'OLD1', octets)
        # L'export archivé est exactement le fichier écrit : la comparaison portera sur cette version.
        self.assertEqual(M.lire_export(self.identifiant, base=self.base), octets)
        self.assertEqual(M.modele_par_export(octets, base=self.base), self.identifiant)
        self.assertIn(b'OLD1', bytes(M.detail(self.identifiant, base=self.base)['modele_xml']))


class FichierXmlGenereTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.export = self.racine / 'SHABANI 7800USD 19000KG 01.xml'
        self.export.write_bytes(self.xml)

    def test_nom_et_etat_du_fichier(self):
        sans = M.enregistrer(self.resultat, self.source, 'alice', base=self.base)
        self.assertEqual(M.fichier_xml_genere(M.detail(sans, base=self.base))[0], '')
        self.assertEqual(M.lister(base=self.base)[0]['chemin_xml'], '')
        M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)
        self.assertEqual(Path(M.lister(base=self.base)[0]['chemin_xml']).name, self.export.name)
        etat = lambda: M.fichier_xml_genere(M.detail(sans, base=self.base))
        self.assertEqual(etat(), (str(self.export.resolve()), 'présent et identique au XML généré'))
        self.export.write_bytes(self.xml + b' ')
        self.assertIn('MODIFIÉ', etat()[1])
        self.export.unlink()
        self.assertIn('introuvable', etat()[1])


class SyntheseTaxesTest(unittest.TestCase):
    def rapport(self, prevu, fourni, taux_g='2268.76', taux_f='2264'):
        D = Decimal
        ecart = D(fourni) - D(prevu)
        return {'taux_genere': D(taux_g), 'taux_fourni': D(taux_f), 'lignes': [
            dict(position='Total global', metrique='taxes', prevu=D(prevu), fourni=D(fourni), ecart=ecart,
                 pourcentage=ecart / D(prevu) * 100),
            dict(position=1, code='6309', metrique='taxes', prevu=D(10), fourni=D(7), ecart=D(-3), pourcentage=None)]}

    def test_ecart_explique_par_le_taux(self):
        s = C.synthese_taxes(self.rapport('9479671', '9459427'))
        self.assertEqual(s['ecart'], Decimal(-20244))
        self.assertIn('20 244 CDF de moins', s['phrases'][0])
        self.assertIn('presque tout l’écart vient du taux', s['phrases'][1])
        self.assertIn('art. 1', s['phrases'][-1])

    def test_reste_non_explique_et_meme_taux(self):
        s = C.synthese_taxes(self.rapport('1000000', '1100000'))
        self.assertTrue(any('Le reste' in p for p in s['phrases']))
        s = C.synthese_taxes(self.rapport('1000000', '1100000', '2264', '2264'))
        self.assertIn('même', s['phrases'][1])

    def test_identique_et_total_absent(self):
        self.assertIn('exactement', C.synthese_taxes(self.rapport('5', '5'))['phrases'][0])
        self.assertIn('impossible', C.synthese_taxes({'lignes': []})['phrases'][0])


class ComparaisonPersisteeTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.export = self.racine / 'export.xml'
        self.export.write_bytes(self.xml)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)

    def test_rapport_complet_relu_sans_le_fichier(self):
        fourni = self.racine / 'fourni.xml'
        fourni.write_bytes(self.xml)
        rapport = C.comparer_xmls(self.export, fourni)
        rapport['source'] = 'Modèle n° 1'
        M.noter_comparaison(self.identifiant, fourni, rapport, 'alice', base=self.base)
        fourni.unlink()  # le fichier comparé disparaît : la comparaison reste consultable
        d = M.detail(self.identifiant, base=self.base)
        [c] = M.comparaisons(d)
        self.assertEqual(c['rapport']['lignes'], rapport['lignes'])
        self.assertEqual(c['rapport']['taxes_detail'], rapport['taxes_detail'])
        self.assertIsInstance(c['rapport']['taux_genere'], Decimal)
        total = next(l for l in rapport['lignes'] if l['position'] == 'Total global' and l['metrique'] == 'taxes')
        self.assertEqual((c['total_estime'], c['total_compare'], c['ecart_total']),
                         (total['prevu'], total['fourni'], total['ecart']))
        self.assertEqual(M.lister(base=self.base)[0]['dernier_ecart'], total['ecart'])
        lignes, explication = M.detail_taxes_modele(d, base=self.base)
        self.assertEqual(lignes, rapport['taxes_detail'])
        self.assertIn('enregistré', explication)
        # Le PDF peut être produit à partir du rapport relu.
        P.pdf_comparaison(c['rapport'], self.racine / 'c.pdf', 'alice')

    def test_ancienne_comparaison_sans_rapport(self):
        fourni = self.racine / 'fourni.xml'
        fourni.write_bytes(b'<ASYCUDA/>')
        M.noter_comparaison(self.identifiant, fourni, {'lignes': []}, 'alice', base=self.base)
        [c] = M.comparaisons(M.detail(self.identifiant, base=self.base))
        self.assertEqual(c['rapport'], {'lignes': []})
        self.assertIsNone(c['ecart_total'])

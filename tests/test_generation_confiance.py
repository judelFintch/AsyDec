"""Génération pondérée par la confiance : déclarations réelles comparées, bons modèles, modèles à éviter."""
from collections import Counter
import json
from pathlib import Path
import random
import shutil
import tempfile
import unittest

from asydec import chemins
from asydec.calcul import moteur
from asydec.calcul import variantes as V
from asydec.declarations import comparaison_prediction as C
from asydec.declarations import modeles_generes as M
from asydec.ui import etapes as E
from tests import test_modeles_generes as TM
from tests.test_references import declaration, item

MODELES = sorted(chemins.MODELES_XML.glob('*.xml'))


@unittest.skipIf(len(MODELES) < 2, 'au moins deux modèles XML locaux nécessaires')
class ProfilConfianceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.racine = Path(temp.name)
        self.base, self.bibliotheque = str(MODELES[0]), [str(p) for p in MODELES]
        # Déclaration réelle : copie d'un XML déjà dans la bibliothèque, ailleurs sur le disque.
        self.reelle = self.racine / 'reelle.xml'
        shutil.copy(MODELES[1], self.reelle)
        self.etrangere = self.racine / 'autres_articles.xml'
        self.etrangere.write_bytes(declaration([item()]))
        self.info = moteur.infos_dossier(moteur.charger(self.base).getroot())

    def profil(self, **confiance):
        return V.construire_profil(self.base, self.bibliotheque, confiance=confiance or None)

    def test_sans_reperes_comportement_inchange(self):
        profil = self.profil()
        self.assertEqual({r['confiance'] for r in profil['references']}, {V.CONFIANCE_BIBLIOTHEQUE})
        self.assertEqual(profil['a_eviter'], [])
        self.assertEqual(profil['bornes'], V.construire_profil(self.base, self.bibliotheque)['bornes'])

    def test_declaration_reelle_prioritaire_sans_doublon(self):
        profil = self.profil(reelles=[str(self.reelle), str(self.etrangere), str(self.racine / 'absent.xml')])
        reelles = [r for r in profil['references'] if r['confiance'] == V.CONFIANCE_REELLE]
        self.assertEqual(len(reelles), 1)  # même contenu que le XML de la bibliothèque : surclassé, pas doublé
        self.assertEqual(len(profil['references']), len(self.profil()['references']))
        # Une déclaration réelle d'autres articles est ignorée sans bruit.
        self.assertFalse(any('autres_articles' in e for e in profil['exclus']))
        self.assertEqual(V.resume_confiance(profil)['Déclaration réelle'], 1)

    def test_bons_modeles_et_modeles_a_eviter(self):
        n = len(self.info['poids_articles'])
        bon = {'id': 7, 'poids': self.info['poids_articles'], 'fob': self.info['fob_articles'],
               'colis': self.info['colis_articles']}
        profil = self.profil(bons=[bon, dict(bon, id=8, poids=[1] * (n + 1))], a_eviter=[bon])
        bons = [r for r in profil['references'] if r['confiance'] == V.CONFIANCE_BON]
        self.assertEqual([r['nom'] for r in bons], ['modèle n° 7'])  # mauvais nombre d'articles écarté
        self.assertEqual(len(profil['a_eviter']), 1)
        self.assertTrue(V.a_eviter(bon, profil))

    def test_tirage_au_prorata_de_la_confiance(self):
        profil = {'references': [{'confiance': 1, 'info': {'poids_articles': [1, 1]}},
                                 {'confiance': 3, 'info': {'poids_articles': [9, 1]}}]}
        rng = random.Random(0)
        tirages = Counter(V._tirer_parts(rng, profil, .25)[0] > 2 for _ in range(4000))
        self.assertAlmostEqual(tirages[True] / 4000, .75, delta=.03)
        # Déclaration réelle : variation resserrée à ±10 %.
        self.assertTrue(all(8.1 <= V._tirer_parts(random.Random(k), {'references': profil['references'][1:]}, .25)[0] <= 9.9
                            for k in range(200)))

    def test_generation_guidee_par_la_declaration_reelle(self):
        # Déclaration réelle de ce dossier : les répartitions se rangent derrière elle.
        i = self.info
        reelle = self.racine / 'dossier_reel.xml'
        shutil.copy(MODELES[0], reelle)
        profil = self.profil(reelles=[str(reelle)])
        propositions = V.generer(i['poids'], i['fob'], i['colis'], profil['ratios'], nombre=20, profil=profil, graine=1)
        sources = Counter(v['source_proche'] for v in propositions)
        self.assertGreater(sources['Déclaration réelle'], len(propositions) / 2, sources)
        reelles = E.declarations_reelles(profil)
        self.assertEqual([r['id'] for r in reelles], [MODELES[0].name])
        self.assertIn('Inspirée de : déclaration réelle', E.texte_inspiration(
            next(v for v in propositions if v['source_proche'] == 'Déclaration réelle')))

    def test_repartition_a_eviter_jamais_proposee(self):
        i = self.info
        profil = self.profil()
        premieres = V.generer(i['poids'], i['fob'], i['colis'], profil['ratios'], nombre=5, profil=profil, graine=2)
        evitee = premieres[0]
        profil['a_eviter'] = [evitee]
        ensuite = V.generer(i['poids'], i['fob'], i['colis'], profil['ratios'], nombre=20, profil=profil, graine=2)
        self.assertTrue(ensuite)
        self.assertFalse(any(V.distance_parts(v, evitee) <= V.DISTANCE_A_EVITER for v in ensuite))


class SourcesConfianceTest(unittest.TestCase):
    def setUp(self):
        TM.ModelesGeneresTest.setUp(self)
        self.export = self.racine / 'export.xml'
        self.export.write_bytes(self.xml)
        self.identifiant = M.enregistrer(self.resultat, self.source, 'alice', export=self.export, base=self.base)
        self.fourni = self.racine / 'reelle.xml'
        self.fourni.write_bytes(self.xml)

    def comparer(self, fichier=None):
        fichier = fichier or self.fourni
        M.noter_comparaison(self.identifiant, fichier, C.comparer_xmls(self.export, fichier), 'alice', base=self.base)

    def test_declarations_comparees_uniques_et_intactes(self):
        self.comparer()
        self.comparer()
        self.assertEqual([d['nom'] for d in M.declarations_comparees(base=self.base)], ['reelle.xml'])
        self.fourni.write_bytes(self.xml + b' ')  # modifiée depuis la comparaison : plus fiable
        self.assertEqual(M.declarations_comparees(base=self.base), [])

    def test_modele_supprime_n_apporte_plus_sa_declaration(self):
        self.comparer()
        M.supprimer(self.identifiant, 'alice', base=self.base)
        self.assertEqual(M.declarations_comparees(base=self.base), [])

    def test_modeles_a_eviter_et_confiance(self):
        signature = M._signature_modele(self.identifiant, self.base)
        self.assertEqual(M.modeles_a_eviter(signature, base=self.base), [])
        M.noter(self.identifiant, 2, 'alice', base=self.base)
        self.assertEqual([m['id'] for m in M.modeles_a_eviter(signature, base=self.base)], [self.identifiant])
        self.comparer()
        confiance = M.confiance_generation(signature, base=self.base)
        self.assertEqual([Path(c).resolve() for c in confiance['reelles']], [self.fourni.resolve()])
        self.assertEqual(confiance['bons'], [])
        self.assertEqual(len(confiance['a_eviter']), 1)

    def test_observations_reelles_pour_les_anomalies(self):
        self.comparer()
        observations = M.observations_reelles(base=self.base)
        self.assertEqual({o['code'] for o in observations}, {'6309', '6304'})
        self.assertTrue(all(o['document_id'].startswith('reel:') and o['ratio'] > 0 for o in observations))
        connue = M.declarations_comparees(base=self.base)[0]['sha256']
        self.assertEqual(M.observations_reelles(base=self.base, connues={connue}), [])


if __name__ == '__main__':
    unittest.main()

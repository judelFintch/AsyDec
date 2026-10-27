"""La régénération de l'étape 3 conserve le dossier et n'exporte jamais de XML."""
import copy
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest
import ui.etapes as etapes
import variantes


class RegenerationVerificationTest(unittest.TestCase):
    def setUp(self):
        self.profil = {'ratios':[1.]*8,'bornes':[(.5,1.5)]*8,'variables_libres':True}
        self.ancien = {'resume':{'poids':800,'fob':800.,'articles':[{'poids':100} for _ in range(8)]},
                       'fob':[100.]*8,'colis':list(range(10,18)),'alertes':[]}
        self.nouveau = {'poids':[90,110,100,100,100,100,100,100],
                        'fob':[90.,110.,100.,100.,100.,100.,100.,100.], 'colis':list(range(10,18))}
        self.apercu = copy.deepcopy(self.ancien)
        self.apercu['resume']['articles']=[{'poids':p} for p in self.nouveau['poids']]
        self.apercu['fob']=self.nouveau['fob']
        articles = SimpleNamespace(remplir=Mock())
        self.app = SimpleNamespace(base='dossier.xml',reference='reference.xml',profil=self.profil,
            table_imp=[],session_verrouillee=False,pages={'articles':articles})
        self.page = SimpleNamespace(app=self.app,resultat=self.ancien,deja_vues={},fichier='ancien-export.xml',
            regenerer_bouton=Mock(),finder=Mock(),message=Mock(),update_idletasks=Mock(),_presenter=Mock())
        self.page._repartition=etapes.PageVerifier._repartition
        self.page._contexte_regeneration=lambda r: etapes.PageVerifier._contexte_regeneration(self.page,r)

    def test_nouveau_modele_meme_totaux_ancien_exclu_aucun_export(self):
        with patch.object(etapes.variantes,'generer',return_value=[self.nouveau]) as recherche, \
             patch.object(etapes.generer,'lire_registre',return_value={}), \
             patch.object(etapes.generer,'produire',return_value=self.apercu) as produire:
            etapes.PageVerifier.regenerer(self.page)
        args=recherche.call_args
        self.assertEqual(args.args[:3],(800,800.,108))
        self.assertIn(variantes.cle_variante(etapes.PageVerifier._repartition(self.ancien)),args.kwargs['exclure'])
        self.assertFalse(produire.call_args.kwargs['enregistrer'])
        self.assertEqual(produire.call_args.args[0],'dossier.xml')
        self.app.pages['articles'].remplir.assert_called_once_with(self.nouveau['poids'],self.nouveau['fob'],self.nouveau['colis'],mode='SAISI')
        self.page._presenter.assert_called_once_with(self.apercu)
        self.assertEqual(self.app.reference,'reference.xml')
        self.assertIsNone(self.page.fichier)

    def test_echec_conserve_ancienne_proposition_et_export(self):
        with patch.object(etapes.variantes,'generer',side_effect=ValueError('aucune nouvelle solution')), \
             patch.object(etapes.messagebox,'showinfo') as message:
            etapes.PageVerifier.regenerer(self.page)
        self.assertIs(self.page.resultat,self.ancien)
        self.assertEqual(self.page.fichier,'ancien-export.xml')
        self.app.pages['articles'].remplir.assert_not_called()
        self.page._presenter.assert_not_called()
        message.assert_called_once()

    def test_echec_recalcul_ne_modifie_pas_les_articles(self):
        with patch.object(etapes.variantes,'generer',return_value=[self.nouveau]), \
             patch.object(etapes.generer,'lire_registre',return_value={}), \
             patch.object(etapes.generer,'produire',side_effect=ValueError('XML incompatible')), \
             patch.object(etapes.messagebox,'showinfo'):
            etapes.PageVerifier.regenerer(self.page)
        self.app.pages['articles'].remplir.assert_not_called()
        self.assertIs(self.page.resultat,self.ancien)

    def test_aucune_repartition_identique_ni_totaux_modifies(self):
        identique=etapes.PageVerifier._repartition(self.ancien)
        faux=copy.deepcopy(self.nouveau)
        faux['poids'][0]+=1
        for proposition in (identique,faux):
            with patch.object(etapes.variantes,'generer',return_value=[proposition]), \
                 patch.object(etapes.generer,'produire') as produire, \
                 patch.object(etapes.messagebox,'showinfo'):
                etapes.PageVerifier.regenerer(self.page)
            produire.assert_not_called()
        self.app.pages['articles'].remplir.assert_not_called()

    def test_session_verrouillee_aucun_calcul(self):
        self.app.session_verrouillee=True
        with patch.object(etapes.variantes,'generer') as recherche:
            etapes.PageVerifier.regenerer(self.page)
        recherche.assert_not_called()


if __name__=='__main__':
    unittest.main()

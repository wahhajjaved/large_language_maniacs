import unittest
import math
import sys
# so we import local stk before any other
sys.path.insert(0,"../../")
from stk.supertree_toolkit import import_tree, obtain_trees, get_all_taxa, _assemble_tree_matrix, create_matrix, _delete_taxon, _sub_taxon
from stk.supertree_toolkit import _swap_tree_in_XML, substitute_taxa, get_taxa_from_tree, get_characters_from_tree, amalgamate_trees
from stk.supertree_toolkit import import_trees, _trees_equal, _find_trees_for_permuting, permute_tree, get_all_source_names

import os
from lxml import etree
from util import *
import StringIO
import numpy
import stk.p4 as p4
# our test dataset
import tempfile

standard_tre = "data/input/test_tree.tre"
single_source_input = "data/input/single_source.phyml"
expected_tree = '((Taxon_c:1.00000,(Taxon_a:1.00000,Taxon_b:1.00000)0.00000:0.00000)0.00000:0.00000,(Taxon_d:1.00000,Taxon_e:1.00000)0.00000:0.00000)0.00000:0.00000;'
parser = etree.XMLParser(remove_blank_text=True)

# To run a single test:
# python -m unittest _trees.TestImportTree.test_permute_trees

class TestImportExportTree(unittest.TestCase):

    def test_import_quoted_tree(self):
        test_file = "data/input/quoted_taxa.tre"
        e_tree = "(('Taxon (c)', (Taxon_a, Taxon_b)), (Taxon_d, Taxon_e));"
        tree = import_tree(test_file)
        self.assert_(e_tree == tree)


    def test_import_treeview(self):
        test_file = "data/input/treeview_test.tre"
        tree = import_tree(test_file)
        expected_tree = "((Taxon_c, (Taxon_a, Taxon_b)), (Taxon_d, Taxon_e));"        
        self.assert_(expected_tree == tree)

    def test_import_mesquite(self):
        test_file = "data/input/mesquite_test.tre"
        expected_tree = "((Taxon_c, (Taxon_a, Taxon_b)), (Taxon_d, Taxon_e));" 
        tree = import_tree(test_file)
        self.assert_(expected_tree == tree)

    def test_import_figtree(self):
        test_file = "data/input/figtree_test.tre"
        tree = import_tree(test_file)
        expected_tree = "((Taxon_c, (Taxon_a, Taxon_b)), (Taxon_d, Taxon_e));" 
        self.assert_(expected_tree == tree)

    def test_import_dendroscope(self):
        test_file = "data/input/dendroscope_test.tre"
        tree = import_tree(test_file)
        expected_tree = "((Taxon_c:1, (Taxon_a:1, Taxon_b:1):0):0, (Taxon_d:1, Taxon_e:1):0);" 
        self.assert_(expected_tree == tree)

    def test_import_macclade(self):
        test_file = "data/input/macclade_test.tre"
        tree = import_tree(test_file)
        expected_tree = "((Taxon_c, (Taxon_a, Taxon_b)), (Taxon_d, Taxon_e));" 
        self.assert_(expected_tree == tree)

    def test_import_paup(self):
        test_file = "data/input/paup_tree.tre"
        tree = import_tree(test_file)
        expected_tree = "(Mimodes_graysoni, (Mimus_gilvus, Mimus_polyglottos), ((Mimus_gundlachii, (Nesomimus_macdonaldi, Nesomimus_melanotis, Nesomimus_parvulus, Nesomimus_trifasciatus)), ((Mimus_longicaudatus, ((Mimus_patagonicus, Mimus_thenca), (Mimus_saturninus, Mimus_triurus))), (Oreoscoptes_montanus, (Toxostoma_curvirostre, Toxostoma_rufum)))));" 
        self.assert_(expected_tree == tree)

    def test_utf_tree(self):
        test_file = "data/input/utf_tree.tre"
        trees = import_trees(test_file)
        expected_tree = """(Colletes_skinneri, ((((Melitta_eickworti, Hesperapis_larreae), (\'Andrena (Callandrena) sp.\', (Panurgus_calcaratus, (Calliopsis_fracta, Calliopsis_pugionis)))), ((Svastra_machaerantherae, Svastra_obliqua), (Tetraloniella_sp., (Melissodes_rustica, (Melissodes_desponsa, Melissodes_sp.))))), ((((Dieunomia_heteropoda, Dieunomia_nevadensis), ((Ceratina_calcarata, ((Chelostoma_fuliginosum, (Hoplitis_biscutellae, (Hoplitis_albifrons, Hoplitis_pilosifrons))), (Megachile_pugnata, Coelioxys_alternata))), ((Paranthidium_jugatorium, Anthidiellum_notatum), (Anthidium_oblongatum, Anthidium_porterae)))), ((Oreopasites_barbarae, ((Holcopasites_calliopsidis, Holcopasites_ruthae), (Nomada_maculata, (Nomada_imbricata, Nomada_obliterta)))), ((Leiopodus_singularis, (Xeromelecta_californica, Zacosmia_maculata)), ((Paranomada_velutina, Triopasites_penniger), (Epeolus_scutellaris, (\'Triepeolus "rozeni"\', Triepeolus_verbesinae)))))), ((Anthophora_furcata, (Anthophora_montana, Anthophora_urbana)), (((Exomalopsis_completa, Exomalopsis_rufiventris), (Ptilothrix_sp., (Diadasia_bituberculata, Diadasia_nigrifrons, (Diadasia_diminuta, Diadasia_martialis)))), ((Xylocopa_tabaniformis, Xylocopa_virginica), (Centris_hoffmanseggiae, (Apis_dorsata, (Apis_mellifera, Apis_nigrocincta)), ((Euglossa_imperialis, (Eulaema_meriana, (Eufriesea_caerulescens, Exaerete_frontalis))), ((Bombus_avinoviellus, (Bombus_pensylvanicus, Bombus_terrestris)), (Melipona_sp., Scaptotrigona_depilis, Lestrimelitta_limao, (Trigona_dorsalis, Trigona_necrophaga)))))))))));"""
        self.assert_(expected_tree == trees[0])

    def test_import_tb_tree(self):
        test_file = "data/input/tree_with_taxa_block.tre"
        tree = import_tree(test_file)
        expected_tree = "(Coracias_caudata, (Gallus_gallus, Apus_affinis), (Acanthisitta_chloris, ((Formicarius_colma, Thamnophilus_nigrocinereus, Furnarius_rufus), (Tyrannus_tyrannus, (Pipra_coronata, Rupicola_rupicola)), (Pitta_guajana, (Smithornis_rufolateralis, (Philepitta_castanea, Psarisomus_dalhousiae)))), (Menura_novaehollandiae, (Climacteris_picumnus, Ptilonorhynchus_violaceus), (Aegithalos_iouschensis, Callaeas_cinerea, Notiomystis_cincta, Tregellasia_leucops, Troglodytes_aedon, Regulus_calendula, Sitta_pygmaea, Pycnonotus_barbatus, Picathartes_gymnocephalus, Parus_inornatus, Orthonyx_spaldingii, Petrochelidon_pyrrhonota, Cisticola_anonymus, Certhia_familiaris, Bombycilla_garrulus, Alauda_arvensis, (Ficedula_strophiata, Turdus_falklandii), (Meliphaga_analoga, Pardalotus_striatus), (Malurus_melanocephalus, Pomatostomus_isidorei), (Dicaeum_melanoxanthum, Nectarinia_olivacea), (Toxorhamphus_novaeguineae, (Melanocharis_nigra, Oedistoma_iliolophum)), (Sylvia_nana, (Garrulax_milleti, Zosterops_senegalensis)), (Cinclus_cinclus, (Mimus_patagonicus, Sturnus_vulgaris)), (Chloropsis_cochinchinensis, Irena_cyanogaster, (Cardinalis_cardinalis, Passer_montanus, Fringilla_montifringilla, (Motacilla_cinerea, Ploceus_cucullatus, Prunella_collaris), (Emberiza_schoeniclus, Thraupis_cyanocephala, Parula_americana, Icterus_parisorum))), ((Artamus_leucorynchus, (Aegithina_tiphia, Vanga_curvirostris)), ((Oriolus_larvatus, (Pachycephala_soror, Vireo_philadelphicus)), (Corvus_corone, Paradisaea_raggiana, (Monarcha_axillaris, Dicrurus_adsimilis), (Coracina_lineata, Lanius_ludovicianus))))))));" 
        self.assert_(expected_tree == tree)

    # combined tree after some processing
    def test_import_combined(self):
        test_file = "data/input/processed_tree.tre"
        tree = import_tree(test_file)
        expected_tree = "(Mimodes_graysoni, (Mimus_gilvus, Mimus_polyglottos), ((Mimus_gundlachii, (Nesomimus_macdonaldi, Nesomimus_melanotis, Nesomimus_parvulus, Nesomimus_trifasciatus)), ((Mimus_longicaudatus, ((Mimus_patagonicus, Mimus_thenca), (Mimus_saturninus, Mimus_triurus))), (Oreoscoptes_montanus, (Toxostoma_curvirostre, Toxostoma_rufum)))));" 
        self.assert_(expected_tree == tree)
        test_file = "data/input/processed_tree_translate.tre"
        tree = import_tree(test_file)
        expected_tree = "(Cettia_fortipes, ((((Garrulax_squamatus, Minla_ignotincta), ((Stachyris_chrysaea, Stachyris_ruficeps), Stachyris_nigriceps)), (((((Stachyris_whiteheadi, ((Zosterops_erythropleurus, Zosterops_japonicus), Zosterops_palpebrosus)), ((Yuhina_bakeri, Yuhina_flavicollis), (Yuhina_gularis, Yuhina_occipitalis))), (Yuhina_castaniceps, Yuhina_everetti)), (Yuhina_brunneiceps, Yuhina_nigrimenta)), Yuhina_diademata)), Yuhina_zantholeuca));" 
        self.assert_(expected_tree == tree)

    def test_import_trees(self):
        """ Test reading all trees from a file """
        test_file = "data/input/multiple_trees.tre"
        tree = import_tree(test_file,tree_no=0)
        expected_tree = "(Coracias_caudata, (Gallus_gallus, Apus_affinis), (Acanthisitta_chloris, ((Formicarius_colma, Thamnophilus_nigrocinereus, Furnarius_rufus), (Tyrannus_tyrannus, (Pipra_coronata, Rupicola_rupicola)), (Pitta_guajana, (Smithornis_rufolateralis, (Philepitta_castanea, Psarisomus_dalhousiae)))), (Menura_novaehollandiae, (Climacteris_picumnus, Ptilonorhynchus_violaceus), (Aegithalos_iouschensis, Callaeas_cinerea, Notiomystis_cincta, Tregellasia_leucops, Troglodytes_aedon, Regulus_calendula, Sitta_pygmaea, Pycnonotus_barbatus, Picathartes_gymnocephalus, Parus_inornatus, Orthonyx_spaldingii, Petrochelidon_pyrrhonota, Cisticola_anonymus, Certhia_familiaris, Bombycilla_garrulus, Alauda_arvensis, (Ficedula_strophiata, Turdus_falklandii), (Meliphaga_analoga, Pardalotus_striatus), (Malurus_melanocephalus, Pomatostomus_isidorei), (Dicaeum_melanoxanthum, Nectarinia_olivacea), (Toxorhamphus_novaeguineae, (Melanocharis_nigra, Oedistoma_iliolophum)), (Sylvia_nana, (Garrulax_milleti, Zosterops_senegalensis)), (Cinclus_cinclus, (Mimus_patagonicus, Sturnus_vulgaris)), (Chloropsis_cochinchinensis, Irena_cyanogaster, (Cardinalis_cardinalis, Passer_montanus, Fringilla_montifringilla, (Motacilla_cinerea, Ploceus_cucullatus, Prunella_collaris), (Emberiza_schoeniclus, Thraupis_cyanocephala, Parula_americana, Icterus_parisorum))), ((Artamus_leucorynchus, (Aegithina_tiphia, Vanga_curvirostris)), ((Oriolus_larvatus, (Pachycephala_soror, Vireo_philadelphicus)), (Corvus_corone, Paradisaea_raggiana, (Monarcha_axillaris, Dicrurus_adsimilis), (Coracina_lineata, Lanius_ludovicianus))))))));" 
        self.assert_(expected_tree == tree)
        tree = import_tree(test_file, tree_no=1)
        expected_tree2 = "(Coracias_caudata, Gallus_gallus, Apus_affinis, (Acanthisitta_chloris, ((Formicarius_colma, Thamnophilus_nigrocinereus, Furnarius_rufus), (Tyrannus_tyrannus, (Pipra_coronata, Rupicola_rupicola)), (Pitta_guajana, (Smithornis_rufolateralis, (Philepitta_castanea, Psarisomus_dalhousiae)))), (Menura_novaehollandiae, (Climacteris_picumnus, Ptilonorhynchus_violaceus), (Aegithalos_iouschensis, Callaeas_cinerea, Notiomystis_cincta, Tregellasia_leucops, Troglodytes_aedon, Regulus_calendula, Sitta_pygmaea, Pycnonotus_barbatus, Picathartes_gymnocephalus, Parus_inornatus, Orthonyx_spaldingii, Petrochelidon_pyrrhonota, Cisticola_anonymus, Certhia_familiaris, Bombycilla_garrulus, Alauda_arvensis, (Ficedula_strophiata, Turdus_falklandii), (Meliphaga_analoga, Pardalotus_striatus), (Malurus_melanocephalus, Pomatostomus_isidorei), (Dicaeum_melanoxanthum, Nectarinia_olivacea), (Toxorhamphus_novaeguineae, (Melanocharis_nigra, Oedistoma_iliolophum)), (Sylvia_nana, (Garrulax_milleti, Zosterops_senegalensis)), (Cinclus_cinclus, (Mimus_patagonicus, Sturnus_vulgaris)), (Chloropsis_cochinchinensis, Irena_cyanogaster, (Cardinalis_cardinalis, Passer_montanus, Fringilla_montifringilla, (Motacilla_cinerea, Ploceus_cucullatus, Prunella_collaris), (Emberiza_schoeniclus, Thraupis_cyanocephala, Parula_americana, Icterus_parisorum))), ((Artamus_leucorynchus, (Aegithina_tiphia, Vanga_curvirostris)), ((Oriolus_larvatus, (Pachycephala_soror, Vireo_philadelphicus)), (Corvus_corone, Paradisaea_raggiana, (Monarcha_axillaris, Dicrurus_adsimilis), (Coracina_lineata, Lanius_ludovicianus))))))));" 
        self.assert_(expected_tree2 == tree)
        trees = import_trees(test_file)
        self.assert_(expected_tree == trees[0])        
        self.assert_(expected_tree2 == trees[1])

    def test_amalgamate_trees_anonymous(self):
        XML = etree.tostring(etree.parse('data/input/old_stk_input.phyml',parser),pretty_print=True)
        output_string = amalgamate_trees(XML,format="nexus",anonymous=True)
        trees = obtain_trees(XML)
        # save the file and read it back in. Then we check correct format (i.e. readable) and
        # we can check the trees are correct
        temp_file_handle, temp_file = tempfile.mkstemp(suffix=".tre")
        f = open(temp_file,"w")
        f.write(output_string)
        f.close()
        try:
            trees_read = import_trees(temp_file)
        except:
            self.assert_(False)
            # we should get no error
        os.remove(temp_file)
        self.assert_(len(trees)==len(trees_read))
        names = trees.keys()
        for i in range(0,len(trees)):
            self.assert_(_trees_equal(trees_read[i],trees[names[i]]))


    def test_amalgamate_trees_nexus(self):
        XML = etree.tostring(etree.parse('data/input/old_stk_input.phyml',parser),pretty_print=True)
        output_string = amalgamate_trees(XML,format="nexus",anonymous=False)
        trees = obtain_trees(XML)
        # save the file and read it back in. Then we check correct format (i.e. readable) and
        # we can check the trees are correct
        temp_file_handle, temp_file = tempfile.mkstemp(suffix=".tre")
        f = open(temp_file,"w")
        f.write(output_string)
        f.close()
        try:
            trees_read = import_trees(temp_file)
        except:
            self.assert_(False)
            # we should get no error
        os.remove(temp_file)
        self.assert_(len(trees)==len(trees_read))
        names = trees.keys()
        for i in range(0,len(trees)):
            self.assert_(_trees_equal(trees_read[i],trees[names[i]]))

    def test_amalgamate_trees_newick(self):
        XML = etree.tostring(etree.parse('data/input/old_stk_input.phyml',parser),pretty_print=True)
        output_string = amalgamate_trees(XML,format="newick")
        trees = obtain_trees(XML)
        # save the file and read it back in. Then we check correct format (i.e. readable) and
        # we can check the trees are correct
        temp_file_handle, temp_file = tempfile.mkstemp(suffix=".tre")
        f = open(temp_file,"w")
        f.write(output_string)
        f.close()
        try:
            trees_read = import_trees(temp_file)
        except:
            self.assert_(False)
            # we should get no error
        os.remove(temp_file)
        self.assert_(len(trees)==len(trees_read))
        names = trees.keys()
        for i in range(0,len(trees)):
            self.assert_(_trees_equal(trees_read[i],trees[names[i]]))


    def test_amalgamate_trees_tnt(self):
        XML = etree.tostring(etree.parse('data/input/old_stk_input.phyml',parser),pretty_print=True)
        output_string = amalgamate_trees(XML,format="tnt")
        trees = obtain_trees(XML)
        # save the file and read it back in. Then we check correct format (i.e. readable) and
        # we can check the trees are correct
        temp_file_handle, temp_file = tempfile.mkstemp(suffix=".tre")
        f = open(temp_file,"w")
        f.write(output_string)
        f.close()
        try:
            trees_read = import_trees(temp_file)
        except:
            self.assert_(False)
            # we should get no error
        os.remove(temp_file)
        self.assert_(len(trees)==len(trees_read))
        names = trees.keys()
        for i in range(0,len(trees)):
            self.assert_(_trees_equal(trees_read[i],trees[names[i]]))

    def test_amalgamate_trees_unknown_format(self):
        XML = etree.tostring(etree.parse('data/input/old_stk_input.phyml',parser),pretty_print=True)
        output_string = amalgamate_trees(XML,format="PHYXML")
        self.assert_(output_string==None)


class TestTreeManipulation(unittest.TestCase): 

    def test_get_all_trees(self):
        XML = etree.tostring(etree.parse(single_source_input,parser),pretty_print=True)
        tree = obtain_trees(XML)
        # Tree key is source_name_tree_no, so we should have
        # Hill_2011_1
        expected_tree = '((A_1:1.00000,B_1:1.00000)0.00000:0.00000,F_1:1.00000,E_1:1.00000,(G_1:1.00000,H_1:1.00000)0.00000:0.00000)0.00000:0.00000;'
        self.assert_(tree['Hill_2011_1'] == expected_tree)

    def test_get_all_taxa(self):
        XML = etree.tostring(etree.parse(single_source_input,parser),pretty_print=True)
        taxa_list = get_all_taxa(XML)
        expected_taxa = ['A_1','B_1','E_1','F_1','G_1','H_1']
        self.assert_(expected_taxa == taxa_list)

    def test_get_all_taxa_pretty(self):
        XML = etree.tostring(etree.parse(single_source_input,parser),pretty_print=True)
        taxa_list = get_all_taxa(XML,pretty=True)
        expected_taxa = ['A 1','B 1','E 1','F 1','G 1','H 1']
        self.assert_(expected_taxa == taxa_list)

    def test_assemble_tree_matrix(self):
        input_tree = '((A,B),F,E,(G,H));'
        matrix, taxa = _assemble_tree_matrix(input_tree)
        # this should give us:
        expected_matrix = numpy.array(
                          [[1, 1, 0],
                           [1, 1, 0],
                           [1, 0, 0], 
                           [1, 0, 0], 
                           [1, 0, 1],
                           [1, 0, 1]])
        expected_taxa = ['A','B','F','E','G','H']
        self.assert_(matrix.all() == expected_matrix.all())
        self.assert_(expected_taxa == taxa)

        input_tree = '(A,B,C,D,E,F);'
        matrix, taxa = _assemble_tree_matrix(input_tree)
        # this should give us:
        expected_matrix = numpy.array(
                          [[1],
                           [1],
                           [1], 
                           [1], 
                           [1],
                           [1]])
        expected_taxa = ['A','B','C','D','E','F']        
        self.assert_(matrix.all() == expected_matrix.all())
        self.assert_(expected_taxa == taxa)


    def test_create_nexus_matrix(self):
        XML = etree.tostring(etree.parse('data/input/create_matrix.phyml',parser),pretty_print=True)
        matrix = create_matrix(XML,format="nexus")
        handle = StringIO.StringIO(matrix)
        
    def test_create_tnt_matrix(self):
        XML = etree.tostring(etree.parse('data/input/create_matrix.phyml',parser),pretty_print=True)
        matrix = create_matrix(XML)

    def test_create_nexus_matrix_quote(self):
        XML = etree.tostring(etree.parse('data/input/create_matrix.phyml',parser),pretty_print=True)
        matrix = create_matrix(XML,format="nexus",quote=True)
        self.assert_(not matrix.find("'") == -1)


    def test_delete_taxa(self):
        t = "((A_1,B_1),F_1,E_1,(G_1,H_1));"
        new_tree = _delete_taxon("H_1", t)
        self.assert_(new_tree == "((A_1, B_1), F_1, E_1, G_1);")

    def test_delete_taxa_root(self):
        t = '((E%1,G%1),A,(G%2,(E%2,F,D,H,E%3)));'
        new_tree =  _delete_taxon("E%1", t)
        new_tree =  _delete_taxon("G%1", new_tree)
        new_tree =  _delete_taxon("E%2", new_tree)
        self.assert_(new_tree == "(A, (G%2, (F, D, H, E%3)));")


    def test_delete_taxa_missing(self):
        t = "((A_1:1.00000,B_1:1.00000)0.00000:0.00000,F_1:1.00000,E_1:1.00000,(G_1:1.00000,H_1:1.00000)0.00000:0.00000)0.00000:0.00000;"
        new_tree = _delete_taxon("Fred", t)
        self.assert_(_trees_equal(new_tree, "((A_1,B_1),F_1,E_1,(G_1,H_1));"))

    def test_sub_taxa(self):
        t = "((A_1:1.00000,B_1:1.00000)0.00000:0.00000,F_1:1.00000,E_1:1.00000,(G_1:1.00000,H_1:1.00000)0.00000:0.00000)0.00000:0.00000;"
        new_tree = _sub_taxon("H_1", "blah", t)
        self.assert_(_trees_equal(new_tree, "((A_1,B_1),F_1,E_1,(G_1,blah));"))

    def test_sub_taxa_missing(self):
        t = "((A_1:1.00000,B_1:1.00000)0.00000:0.00000,F_1:1.00000,E_1:1.00000,(G_1:1.00000,H_1:1.00000)0.00000:0.00000)0.00000:0.00000;"
        new_tree = _sub_taxon("Fred", "Blah",  t)
        self.assert_(_trees_equal(new_tree, "((A_1,B_1),F_1,E_1,(G_1,H_1));"))


    def test_insert_tree_XML(self):
        XML = etree.tostring(etree.parse('data/input/create_matrix.phyml',parser),pretty_print=True)
        name = "Hill_Davis_2011_1"
        tree = "(a,b,c);"
        new_xml = _swap_tree_in_XML(XML, tree, name)
        trees = obtain_trees(new_xml)
        # loop through all trees, checking them
        self.assert_(trees['Hill_2011_1'] == "((A:1.00000,B:1.00000)0.00000:0.00000,(F:1.00000,E:1.00000)0.00000:0.00000)0.00000:0.00000;")
        self.assert_(trees['Davis_2011_1'] == "((A:1.00000,B:1.00000)0.00000:0.00000,(C:1.00000,D:1.00000)0.00000:0.00000)0.00000:0.00000;")
        self.assert_(trees[name] == "(a,b,c);")

    def test_delete_tree_XML(self):
        XML = etree.tostring(etree.parse('data/input/create_matrix.phyml',parser),pretty_print=True)
        name = "Hill_Davis_2011_1"
        trees = obtain_trees(XML)
        old_len = len(trees)
        new_xml = _swap_tree_in_XML(XML, None, name)
        trees = obtain_trees(new_xml)
        # loop through all trees, checking them
        self.assert_(trees['Davis_2011_1'] == "((A:1.00000,B:1.00000)0.00000:0.00000,(C:1.00000,D:1.00000)0.00000:0.00000)0.00000:0.00000;")
        self.assert_(len(trees) == old_len-1)
        # check that no sources are empty

    
    def test_delete_tree_XML_and_remove_source(self):
        XML = etree.tostring(etree.parse('data/input/clean_data.phyml',parser),pretty_print=True)
        names = ["Hill_2012_1","Hill_2012_2"]
        names.sort(reverse=True)
        trees = obtain_trees(XML)
        old_len = len(trees)
        new_xml = XML
        for name in names:
            new_xml = _swap_tree_in_XML(new_xml, None, name, delete=True)

        trees = obtain_trees(new_xml)
        self.assert_(len(trees) == old_len-2)
        # check only one source remains
        names = get_all_source_names(new_xml)
        self.assert_(len(names) == 1)
        self.assert_(names[0] == "Hill_2011")


    def test_taxa_from_tree(self):
        XML = etree.tostring(etree.parse('data/input/sub_taxa.phyml',parser),pretty_print=True)
        taxa = get_taxa_from_tree(XML,"Hill_2011_1")
        expected_taxa = ['A','B','F','E']
        self.assertListEqual(taxa,expected_taxa)

    def test_taxa_from_tree_sort(self):
        XML = etree.tostring(etree.parse('data/input/sub_taxa.phyml',parser),pretty_print=True)
        taxa = get_taxa_from_tree(XML,"Hill_2011_1",sort=True)
        expected_taxa = ['A','B','E','F']
        self.assertListEqual(taxa,expected_taxa)

    def test_trees_equal(self):
        test_file = "data/input/multiple_trees.tre"
        trees = import_trees(test_file)
        self.assert_(_trees_equal(trees[0],trees[0])==True)
        self.assert_(_trees_equal(trees[1],trees[1])==True)

    def test_trees_not_equal(self):
        test_file = "data/input/multiple_trees.tre"
        trees = import_trees(test_file)
        self.assert_(_trees_equal(trees[1],trees[0])==False)

    def test_trees_equal2(self):
        test_file = "data/input/equal_trees.new"
        trees = import_trees(test_file)
        self.assert_(_trees_equal(trees[1],trees[0])==True)
        self.assert_(_trees_equal(trees[3],trees[2])==False)

class TestTreeMetaData(unittest.TestCase):

    def test_taxa_from_characters(self):
        XML = etree.tostring(etree.parse('data/input/sub_taxa.phyml',parser),pretty_print=True)
        chars = get_characters_from_tree(XML,"Hill_Davis_2011_1")
        expected_chars = ['cytb','12S']
        self.assertListEqual(chars,expected_chars)

    def test_taxa_from_characters_sort(self):
        XML = etree.tostring(etree.parse('data/input/sub_taxa.phyml',parser),pretty_print=True)
        chars = get_characters_from_tree(XML,"Hill_Davis_2011_1",sort=True)
        expected_chars = ['12S','cytb']
        self.assertListEqual(chars,expected_chars)
    

    def test_find_trees_for_permuting(self):
        XML = etree.tostring(etree.parse('data/input/old_stk_input.phyml',parser),pretty_print=True)
        permute_trees = _find_trees_for_permuting(XML)
        self.assert_(len(permute_trees) == 0)

    def test_find_trees_for_permuting(self):
        XML = etree.tostring(etree.parse('data/input/permute_trees.phyml',parser),pretty_print=True)
        permute_trees = _find_trees_for_permuting(XML)
        self.assert_(len(permute_trees) == 3)
        self.assert_(permute_trees['Hill_2011_1'] == "((E%1,'G%1'),A,(G%2,(E%2,F,D,H,E%3)));")
        self.assert_(permute_trees['Davis_2011_1'] == '(Outgroup,(((((Leopardus_geoffroyi,Leopardus_pardalis),(Otocolobus_manul,Felis_magrita)),(Prionailurus_bengalensis,Leptailurus_serval)),(Catopuma_temmincki,(Caracal_caracal,Lynx_rufus))),((Acinonyx_jubatus,(Puma_concolor,(Panthera_tigris%1,Panthera_uncia))),(Panthera_onca,(Panthera_leo,Panthera_tigris%2)))));')
        self.assert_(permute_trees['Hill_Davis_2011_1'] == '(A, (B, (C, D, E%1, F, G, E%2, E%3)));')

    def test_permute_trees(self):
        XML = etree.tostring(etree.parse('data/input/permute_trees.phyml',parser),pretty_print=True)
        trees = obtain_trees(XML)
        # contains quoted taxa too
        output = permute_tree(trees['Hill_2011_1'],treefile="newick")
        temp_file_handle, temp_file = tempfile.mkstemp(suffix=".new")
        f = open(temp_file,"w")
        f.write(output)
        f.close()
        output_trees = import_trees(temp_file)
        expected_trees = import_trees("data/output/permute_trees.nex")
        os.remove(temp_file)
        self.assert_(len(output_trees)==len(expected_trees))
        for i in range(0,len(output_trees)):
            self.assert_(_trees_equal(output_trees[i],expected_trees[i]))

    def test_permute_trees_2(self):
        XML = etree.tostring(etree.parse('data/input/permute_trees.phyml',parser),pretty_print=True)
        trees = obtain_trees(XML)
        output = permute_tree(trees['Davis_2011_1'],treefile="newick")
        temp_file_handle, temp_file = tempfile.mkstemp(suffix=".new")
        f = open(temp_file,"w")
        f.write(output)
        f.close()
        output_trees = import_trees(temp_file)
        expected_trees = import_trees("data/output/permute_trees_2.nex")
        os.remove(temp_file)
        self.assert_(len(output_trees)==len(expected_trees))
        for i in range(0,len(output_trees)):
            self.assert_(_trees_equal(output_trees[i],expected_trees[i]))


if __name__ == '__main__':
    unittest.main()
 

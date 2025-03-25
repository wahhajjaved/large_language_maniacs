import weakref
import pytest

from timeflow.linked_structure import (transfer_core, create_core_in,
                                       hatch_egg_simple, hatch_egg_optimized,
                                       PARENT, CHILD, SELF, NO_VALUE, diff)
from timeflow.linked_mapping import LinkedMapping


@pytest.mark.skip(reason='not a test')
def setup_main_test_cases():

    aa_egg = LinkedMapping.first_egg({})
    aa_egg['varies'] = 10
    aa_egg['constant'] = 100
    aa_egg['to_delete'] = 'to_delete_val'

    aa = hatch_egg_simple(aa_egg); del aa_egg

    bb_egg = aa.egg()

    bb_egg['varies'] = 20
    bb_egg['additional'] = 'additional_val'
    del bb_egg['to_delete']
    bb = hatch_egg_simple(bb_egg); del bb_egg


    desired_aa = {'varies': 10,
                  'constant': 100,
                  'to_delete': 'to_delete_val'}

    desired_bb = {'varies': 20,
                  'constant': 100,
                  'additional': 'additional_val'}

    return aa, bb, desired_aa, desired_bb


def test_linked_dictionary():
    aa, bb, desired_aa, desired_bb = setup_main_test_cases()

    assert aa['varies'] == 10
    assert bb['varies'] == 20
    assert 'additional' not in aa

    assert aa == desired_aa
    assert bb == desired_bb, bb


def test_transfer_core():
    aa, bb, desired_aa, desired_bb = setup_main_test_cases()
    transfer_core(aa, bb)
    assert aa.relation_to_base == PARENT
    assert bb.relation_to_base == SELF

    assert aa == desired_aa
    assert bb == desired_bb

    transfer_core(bb, aa)
    assert aa.relation_to_base == SELF
    assert bb.relation_to_base == CHILD

    assert aa == desired_aa
    assert bb == desired_bb

    
def test_create_core_in():
    aa, bb, desired_aa, desired_bb = setup_main_test_cases()
    create_core_in(bb)
    assert aa.relation_to_base == SELF
    assert bb.relation_to_base == SELF

    assert aa == desired_aa
    assert bb == desired_bb


def test_memory_management():
    class X(object):
        pass

    aa_egg = LinkedMapping.first_egg({})
    aa_egg['to_delete'] = X()
    aa_egg['to_keep'] = X()

    aa = hatch_egg_simple(aa_egg); del aa_egg
    bb_egg = aa.egg()

    del bb_egg['to_delete']
    bb = hatch_egg_simple(bb_egg); del bb_egg

    bb.diff_parent is not None
    test_ref = weakref.ref(aa['to_delete'])
    del aa
    bb.diff_parent is not None
    assert test_ref() is not None

    transfer_core(bb.parent(), bb)    # bb.parent() points to aa until core is transferred

    bb.diff_parent is None
    assert test_ref() is None

    
def test_hatch_empty_mapping():
    class X(object):
        pass

    aa_egg = LinkedMapping.first_egg({})
    aa_egg['to_delete'] = X()

    aa = hatch_egg_simple(aa_egg); del aa_egg
    bb_egg = aa.egg()

    del bb_egg['to_delete']
    assert not bb_egg

    bb = hatch_egg_optimized(bb_egg); del bb_egg
    assert not bb
    assert bb.relation_to_base == SELF

    test_ref = weakref.ref(aa['to_delete'])
    del aa
    assert test_ref() is None


def test_linked_dictionary_error_handling():
    aa, bb, _unused_1, _unused_2 = setup_main_test_cases()
    cc_egg = bb.egg()

    with pytest.raises(KeyError):
        aa['no_such_key']


    with pytest.raises(KeyError):
        bb['to_delete']

    with pytest.raises(KeyError):
        bb['no_such_key']

    with pytest.raises(TypeError):
        del bb['no_such_key']

    with pytest.raises(TypeError):
        del bb['to_delete']


    with pytest.raises(KeyError):
        del cc_egg['no_such_key']

    with pytest.raises(KeyError):
        cc_egg['to_delete']

    with pytest.raises(KeyError):
        del cc_egg['to_delete']


def test_diff():
    aa, bb, _unused_1, _unused_2 = setup_main_test_cases()

    assert dict(diff(aa, bb)) == {'varies': (10, 20),
                                  'to_delete': ('to_delete_val', NO_VALUE),
                                  'additional': (NO_VALUE, 'additional_val')}, dict(diff(bb, aa))


    assert dict(diff(bb, aa)) == {k: (v[1], v[0]) for k,v in diff(aa, bb)}


    assert list(diff(aa, aa)) == []


    cc = LinkedMapping.first_egg({'varies': 'new_varies_val',
                                  'constant': 100,
                                  'new_cc_key': 'new_cc_val'}).hatch()

    assert (dict(diff(bb, cc))
            == dict(LinkedMapping._diff(bb, cc))
            == {'varies': (20, 'new_varies_val'),
                'additional': ('additional_val', NO_VALUE),
                'new_cc_key': (NO_VALUE, 'new_cc_val')}), (dict(diff(bb,cc)),
dict(diff(bb,cc)) == dict(LinkedMapping.diff(bb, cc)))

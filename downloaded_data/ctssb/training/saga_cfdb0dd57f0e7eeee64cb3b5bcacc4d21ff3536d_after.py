import time
import traceback
import numpy as np
from astropy.table import vstack
from easyquery import Query
from . import cuts as C
from . import build, build2
from .manual_fixes import fixes_to_nsa_v012, fixes_to_nsa_v101
from ..database import FitsTable, Database
from ..hosts import HostCatalog
from ..utils import get_sdss_bands, get_all_colors, add_skycoord, fill_values_by_query


__all__ = ['ObjectCatalog', 'get_unique_objids']


def get_unique_objids(objid_col):
    try:
        objid_col = objid_col.compressed()
    except AttributeError:
        pass
    return np.unique(np.asarray(objid_col, dtype=np.int64))


class ObjectCatalog(object):
    """
    This class provides a high-level interface to access object catalogs
    (also known as "base catalogs")

    Parameters
    ----------
    database : SAGA.Database object

    Returns
    -------
    object_catalog : SAGA.ObjectCatalog object

    Examples
    --------
    >>> import SAGA
    >>> saga_database = SAGA.Database('/path/to/SAGA/Dropbox')
    >>> saga_object_catalog = SAGA.ObjectCatalog(saga_database)
    >>> specs = saga_object_catalog.load(has_spec=True)
    >>> base_anak = saga_object_catalog.load(hosts='AnaK')

    Here specs and base_anak are both astropy tables.
    """

    def __init__(self, database=None, host_catalog_class=HostCatalog):
        self._database = database or Database()
        self._host_catalog = host_catalog_class(self._database)


    @staticmethod
    def _annotate_catalog(table, to_add_skycoord=False):
        if 'EXTINCTION_R' in table.colnames:
            for b in get_sdss_bands():
                table['{}_mag'.format(b)] = table[b] - table['EXTINCTION_{}'.format(b.upper())]

        for color in get_all_colors():
            if '{}_mag'.format(color[0]) not in table.colnames or '{}_mag'.format(color[1]) not in table.colnames:
                continue
            table[color] = table['{}_mag'.format(color[0])] - table['{}_mag'.format(color[1])]
            table['{}_err'.format(color)] = np.hypot(table['{}_err'.format(color[0])], table['{}_err'.format(color[1])])

        if to_add_skycoord:
            table = add_skycoord(table)

        return table


    @staticmethod
    def _slice_columns(table, columns, to_add_skycoord=False):
        if columns is not None:
            table = table[columns]

        if to_add_skycoord:
            table = add_skycoord(table)

        return table


    def load(self, hosts=None, has_spec=None, cuts=None, return_as=None, columns=None, version=None, to_add_skycoord=True):
        """
        load object catalogs (aka "base catalogs")

        Parameters
        ----------
        hosts : int, str, list, None, optional
            host names/IDs or a list of host names/IDs or short-hand names like
            "paper1" or "paper1_complete"

        has_spec : bool, optional
            If set to True, load only objects that have spectra

        cuts : easyquery.Query, str, tuple, optional
            To apply to the objects when loaded

        return_as : str, optional
            If set to 'list' (default when `has_spec` is None), return a list that contains all tables
            If set to 'stacked' (default when `has_spec` is True), return a stacked table
            If set to 'iter', return an iterator for looping over hosts
            If set to 'dict', return a dictionary with host ids being the keys

        columns : list, optional
            If set, only load a subset of columns

        version : int or str, optional
            Set to 'paper1' for paper1 catalogs

        Returns
        -------
        objects : astropy.table.Table, list, or iterator
            (depending on `return_as`)

        Examples
        --------
        >>> import SAGA
        >>> from SAGA import ObjectCuts as C
        >>> saga_database = SAGA.Database('/path/to/SAGA/Dropbox')
        >>> saga_object_catalog = SAGA.ObjectCatalog(saga_database)

        To load all spectra, with some basic cuts applied:
        >>> specs = saga_object_catalog.load(has_spec=True, cuts=C.basic_cut)

        Load the base catalog for a certain host, with some basic cuts applied:
        >>> specs = saga_object_catalog.load(hosts='AnaK', cuts=C.basic_cut)

        Load base catalog for all paper1 hosts, with some basic cuts applied,
        and stored as a list:
        >>> base_tables = saga_object_catalog.load(hosts='paper1', cuts=C.basic_cut, return_as='list')

        Load base catalog for all paper1 hosts, with some basic cuts applied,
        and stored as one single big table:
        >>> bases_table = saga_object_catalog.load(hosts='paper1', cuts=C.basic_cut, return_as='stacked')
        """

        if version is None:
            base_key = 'base'
        elif str(version).lower() in ('paper1', 'p1', 'v0p1', '0', '0.1'):
            base_key = 'base_v0p1'
        elif version in (1, 2):
            base_key = 'base_v{}'.format(version)
        else:
            raise ValueError('`version` must be None, \'paper1\', 1 or 2.')

        if return_as is None:
            return_as = 'stacked' if (has_spec and base_key == 'base_v0p1') else 'list'
        return_as = return_as.lower()
        if return_as[0] not in 'slid':
            raise ValueError('`return_as` should be "list", "stacked", "iter", or "dict"')

        if has_spec and base_key == 'base_v0p1':
            t = self._database['saga_spectra_May2017'].read()

            if hosts is not None:
                host_ids = self._host_catalog.resolve_id(hosts, 'NSA')
                t = Query((lambda x: np.in1d(x, host_ids), 'HOST_NSAID')).filter(t)

            t = self._annotate_catalog(t)

            if cuts is not None:
                t = Query(cuts).filter(t)

            if return_as[0] != 's':
                if hosts is None:
                    host_ids = np.unique(t['HOST_NSAID'])
                output_iterator = (self._slice_columns(Query('HOST_NSAID == {}'.format(i)).filter(t), columns, to_add_skycoord) for i in host_ids)
                if return_as[0] == 'i':
                    return output_iterator
                if return_as[0] == 'd':
                    return dict(zip(host_ids, output_iterator))
                return list(output_iterator)

            return self._slice_columns(t, columns, to_add_skycoord)

        q = Query(cuts)
        if has_spec:
            q = q & C.has_spec
        elif has_spec is not None:
            q = q & (~C.has_spec)

        hosts = self._host_catalog.resolve_id(hosts, 'string')

        output_iterator = (
            self._slice_columns(
                q.filter(self._annotate_catalog(self._database[base_key, host].read())),
                columns,
                (to_add_skycoord and return_as[0] != 's')
            ) for host in hosts
        )

        if return_as[0] == 'i':
            return output_iterator
        if return_as[0] == 's':
            out = vstack(list(output_iterator), 'outer', 'error')
            if out.masked:
                for name, (dtype, _) in out.dtype.fields.items():
                    if dtype.kind == 'i':
                        out[name].fill_value = -1
                    if dtype.kind == 'b':
                        out[name].fill_value = False
            out = out.filled()
            if to_add_skycoord:
                out = add_skycoord(out)
            return out
        if return_as[0] == 'd':
            return dict(zip(hosts, output_iterator))
        return list(output_iterator)


    def load_nsa(self, version='0.1.2'):
        nsa = self._database['nsa_v{}'.format(version)].read()
        remove_mask = np.zeros(len(nsa), np.bool)
        objs_to_remove = []
        fixes_dict = {}
        cols = nsa.colnames
        if version == '0.1.2':
            objs_to_remove = [64408]
            fixes_dict = fixes_to_nsa_v012
            cols = build.NSA_COLS_USED
        elif version == '1.0.1':
            remove_mask |= (nsa['DFLAGS'][:,3:6] == 24).any(axis=1) & (nsa['DFLAGS'][:,3:6]).all(axis=1)
            objs_to_remove = [614276, 632725]
            fixes_dict = fixes_to_nsa_v101
            cols = build2.NSA_COLS_USED
        remove_mask |= np.in1d(nsa['NSAID'], objs_to_remove, assume_unique=True)
        nsa = nsa[cols][~remove_mask]
        for nsaid, fixes in fixes_dict.items():
            fill_values_by_query(nsa, 'NSAID == {}'.format(nsaid), fixes)
        nsa = add_skycoord(nsa)
        return nsa


    def build_and_write_to_database(self, hosts=None, overwrite=False, base_file_path_pattern=None, version=None, return_catalogs=False, raise_exception=False, add_specs_only_before_time=None, use_nsa=True, convert_to_sdss_filters=True, additional_specs=None, debug=None):
        """
        This function builds the base catalog and writes it to the database.

        !! IMPORTANT !!
        If you want to write the base catalog to an alternative location (not the database)
        Make sure you set the `base_file_path_pattern` option!!

        Parameters
        ----------
        hosts : int, str, list, optional
            host names/IDs or a list of host names/IDs or short-hand names like
            "paper1" or "paper1_complete"

        overwrite : bool, optional (default: False)
            If set to True, overwrite existing base catalog

        base_file_path_pattern : str, optional
        version : int, optional (default: 2)
        return_catalogs : bool, optional (default: False)
        raise_exception : bool, optional (default: False)
        add_specs_only_before_time : astropy.time.Time, optional (default: None)

        Examples
        --------
        >>> saga_database = SAGA.Database('/path/to/SAGA/Dropbox', '/path/to/SAGA/local')
        >>> saga_object_catalog = SAGA.ObjectCatalog(saga_database)

        Overwrite the database (Danger!!)
        >>> saga_object_catalog.build_and_write_to_database('paper1', overwrite=True)

        You can also do
        >>> saga_object_catalog.build_and_write_to_database('paper1', base_file_path_pattern='/other/base/catalog/dir/nsa{}.fits.gz')

        """
        if version not in (None, 1, 2):
            raise ValueError('`version` must be None, 1 or 2.')
        build_module = build if version == 1 else build2

        if use_nsa:
            nsa = self.load_nsa('0.1.2' if version == 1 else '1.0.1')
        else:
            nsa = None

        spectra = self._database['spectra_raw_all'].read(
            before_time=add_specs_only_before_time,
            additional_specs=additional_specs,
        )

        manual_lists = {}
        for survey, col in (('sdss', 'SDSS ID'), ('des', 'DES_OBJID'), ('decals', 'decals_objid')):
            for list_type in ('remove', 'recover'):
                key = '{}_{}'.format(survey, list_type)
                try:
                    val = get_unique_objids(self._database[key].read()[col])
                except KeyError:
                    pass
                else:
                    if len(val):
                        manual_lists[key] = val

        catalogs_to_return = list()
        host_ids = self._host_catalog.resolve_id(hosts, 'string')

        for i, host_id in enumerate(host_ids):
            if base_file_path_pattern is None:
                base_key = 'base' if version is None else 'base_v{}'.format(version)
                data_obj = self._database[base_key, host_id].remote
            else:
                data_obj = FitsTable(base_file_path_pattern.format(host_id))

            if data_obj.isfile() and not overwrite:
                print(time.strftime('[%m/%d %H:%M:%S]'), 'Base catalog v{} for {} already exists ({}).'.format(version or 2, host_id, data_obj.path), '({}/{})'.format(i+1, len(host_ids)))
                continue

            host = self._host_catalog.load_single(host_id)
            catalogs = ('sdss', 'wise') if version == 1 else ('sdss', 'des', 'decals')

            def get_catalog_or_none(catalog_name):
                try:
                    cat = self._database[catalog_name, host_id].read()
                except OSError:
                    print(time.strftime('[%m/%d %H:%M:%S]'), '[WARNING] Not found: {} catalog for {}.'.format(catalog_name.upper(), host_id))
                    return None
                return cat[build.WISE_COLS_USED] if catalog_name == 'wise' else cat

            catalog_dict = {k: get_catalog_or_none(k) for k in catalogs}

            print(
                time.strftime('[%m/%d %H:%M:%S]'),
                'Use {} to build base catalog v{} for {}'.format(
                    ', '.join((k for k, v in catalog_dict.items() if v is not None)).upper(),
                    (version or 2),
                    host_id
                ),
                '({}/{})'.format(i+1, len(host_ids))
            )

            if debug is None:
                debug_this = None
            else:
                debug[host_id] = dict()
                debug_this = debug[host_id]

            try:
                base = build_module.build_full_stack(
                    host=host,
                    nsa=nsa,
                    spectra=spectra,
                    convert_to_sdss_filters=convert_to_sdss_filters,
                    debug=debug_this,
                    **manual_lists,
                    **catalog_dict
                )
            except Exception as e: # pylint: disable=W0703
                print(time.strftime('[%m/%d %H:%M:%S]'), '[ERROR] Fail to build base catalog for {}'.format(host_id))
                base = None
                if raise_exception:
                    raise e
                traceback.print_exc()
                continue
            finally:
                del catalog_dict
                if return_catalogs:
                    catalogs_to_return.append(base)

            print(time.strftime('[%m/%d %H:%M:%S]'), 'Write base catalog to {}'.format(data_obj.path))
            try:
                data_obj.write(base)
            except (IOError, OSError) as e:
                print(time.strftime('[%m/%d %H:%M:%S]'), '[ERROR] Fail to write base catalog for {}'.format(host_id))
                if raise_exception:
                    raise e
                traceback.print_exc()
                continue

        if return_catalogs:
            return catalogs_to_return


    def generate_clean_specs(self, hosts='all', version=None, annotate=False):
        """
        gather spectra from all base catalogs
        """
        surveys = ('sdss', 'des', 'decals')
        base_key = 'base' if version is None else 'base_v{}'.format(version)
        out = []

        for host in set(self._host_catalog.resolve_id(hosts, 'string')):
            try:
                base = self._database[base_key, host].read()
            except IOError:
                print('[WARNING] cannot find base catalog for', host)

            base = C.has_spec.filter(base)

            if version != 1:
                cols = [col for col in base.colnames if col.startswith('OBJID_') or not any(col.endswith('_'+s) for s in surveys)]
                base = base[cols]
                for s in surveys:
                    key = 'OBJID_' + s
                    if key not in base.colnames:
                        base[key] = -1

            out.append(base)

        out = vstack(out, 'exact', 'error')
        if annotate:
            out = self._annotate_catalog(out)
        return out

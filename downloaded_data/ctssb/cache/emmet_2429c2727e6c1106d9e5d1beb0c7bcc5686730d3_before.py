import os
import os.path
import string
import traceback
import copy
import nltk
import numpy as np
from ast import literal_eval
from datetime import datetime
from itertools import groupby

from monty.json import jsanitize
from monty.serialization import loadfn

from maggma.builders import Builder
from maggma.utils import grouper, source_keys_updated
from maggma.validator import JSONSchemaValidator, msonable_schema
from pydash.objects import get, set_, has

from emmet.materials.snls import mp_default_snl_fields
from emmet.common.utils import scrub_class_and_module
from emmet import __version__ as emmet_version

from pymatgen import Structure
from pymatgen.io.cif import CifWriter
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.analysis.structure_analyzer import oxide_type
from pymatgen.analysis.structure_analyzer import RelaxationAnalyzer
from pymatgen.analysis.diffraction.core import DiffractionPattern
from pymatgen.util.provenance import StructureNL
from pymatgen import __version__ as pymatgen_version

__author__ = "Shyam Dwaraknath <shyamd@lbl.gov>"

MODULE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))
MPBUILDER_SCHEMA = os.path.join(MODULE_DIR, "schema", "mp_website.json")
MPBUILDER_SETTINGS = os.path.join(MODULE_DIR, "settings", "mp_website.json")

_settings = loadfn(MPBUILDER_SETTINGS)
latt_para_interval = [1.50 - 1.96 * 3.14, 1.50 + 1.96 * 3.14]
vol_interval = [4.56 - 1.96 * 7.82, 4.56 + 1.96 * 7.82]


class MPBuilder(Builder):
    def __init__(
        self,
        materials,
        website,
        thermo,
        aux=None,
        default_sandboxes=None,
        query=None,
        **kwargs,
    ):
        """
        Creates a MP Website style materials doc.
        This builder is a bit unweildy as MP will eventually move to a new format
        written for backwards compatability with previous infrastructure

        Args:
            tasks (Store): Store of task documents
            materials (Store): Store of materials documents
                should be aggregate across multiple stores using JointStore
            website (Store): Store of the mp style website docs
            aux ([Store]): Auxillary data collection to join to materials doc
                for processing
            default_sandboxes([string]): List of default sandboxes for materials
        """
        self.materials = materials
        self.website = website
        self.thermo = thermo
        self.aux = aux if aux else []
        self.default_sandboxes = default_sandboxes if default_sandboxes else []
        self.query = query
        # self.website.validator = JSONSchemaValidator(loadfn(MPBUILDER_SCHEMA))

        super().__init__(sources=[materials, thermo] + aux, targets=[website], **kwargs)

    def get_items(self):
        """
        Custom get items to allow for incremental building for a whole set of stores
        """

        self.logger.info("Starting Website Builder")

        self.ensure_indexes()

        keys = self.get_keys()
        self.logger.info("Processing {} items".format(len(keys)))
        self.total = len(keys)

        # Chunk keys by chunk size for good data IO
        for chunked_keys in grouper(keys, self.chunk_size, None):
            chunked_keys = list(filter(None.__ne__, chunked_keys))

            docs = {
                d[self.materials.key]: d
                for d in self.materials.query(
                    criteria={self.materials.key: {"$in": chunked_keys}}
                )
            }
            self.add_thermo_docs(docs)
            self.add_aux_docs(docs)

            for d in docs.values():
                yield d

    def process_item(self, item):

        self.logger.debug("Processing: {}".format(item[self.materials.key]))

        try:
            mat = old_style_mat(item)

            # These functions convert data from old style to new style
            add_es(mat, item)
            add_xrd(mat, item)
            add_elastic(mat, item)
            add_bonds(mat, item)
            add_propnet(mat, item)
            add_snl(mat, item)
            check_relaxation(mat, item)
            add_cifs(mat)
            add_meta(mat)
            add_thermo(mat, item)

            processed = jsanitize(mat)

        except Exception as e:
            self.logger.error(traceback.format_exc())
            processed = {"error": str(e)}

        key, lu_field = self.materials.key, self.materials.lu_field
        out = {
            self.website.key: item[key],
            self.website.lu_field: self.website.lu_func[1](
                self.materials.lu_func[0](item[lu_field])
            ),
        }
        out.update(processed)
        return out

    def update_targets(self, items):
        for item in items:
            # Add in build timestamp
            item["_bt"] = datetime.utcnow()
            if "_id" in item:
                del item["_id"]

        if len(items) > 0:
            self.logger.debug(f"Updating {len(items)} items")
            self.website.update(items, update_lu=False)

    def ensure_indexes(self):
        """
        Ensures indexes on all the collections
        """

        self.materials.ensure_index(self.materials.key)
        self.materials.ensure_index(self.materials.lu_field)

        self.website.ensure_index(self.website.key)
        self.website.ensure_index(self.website.lu_field)

        for source in self.aux:
            source.ensure_index(source.key)
            source.ensure_index(source.lu_field)

        # Indexes for website

        self.website.ensure_index("unit_cell_formula")
        self.website.ensure_index("reduced_cell_formula")
        self.website.ensure_index("chemsys")
        self.website.ensure_index("nsites")
        self.website.ensure_index("e_above_hull")
        self.website.ensure_index("pretty_formula")
        self.website.ensure_index("run_type")
        self.website.ensure_index("band_gap")
        self.website.ensure_index("task_type")
        self.website.ensure_index("snlgroup_id_final")
        self.website.ensure_index("band_gap.search_gap.band_gap")
        self.website.ensure_index("formation_energy_per_atom")
        self.website.ensure_index("density")
        self.website.ensure_index("volume")
        self.website.ensure_index("spacegroup.crystal_system")
        self.website.ensure_index("exp.tags")
        self.website.ensure_index("anonymous_formula")
        self.website.ensure_index("has_bandstructure")
        self.website.ensure_index("spacegroup.symbol")
        self.website.ensure_index("elasticity.homogeneous_poisson")
        self.website.ensure_index("elasticity.universal_anisotropy")
        self.website.ensure_index("elasticity.G_Voigt_Reuss_Hill")
        self.website.ensure_index("elasticity.G_Reuss")
        self.website.ensure_index("elasticity.G_Voigt")
        self.website.ensure_index("elasticity.K_Reuss")
        self.website.ensure_index("elasticity.K_Voigt_Reuss_Hill")
        self.website.ensure_index("elasticity.K_Voigt")
        self.website.ensure_index("nelements")
        self.website.ensure_index("doi")
        self.website.ensure_index("doi_bibtex")
        self.website.ensure_index("elasticity.poisson_ratio")
        self.website.ensure_index("nelements")
        self.website.ensure_index("elasticity.K_VRH")
        self.website.ensure_index("task_ids")
        self.website.ensure_index("snl_final.about.remarks")
        self.website.ensure_index("original_task_id")
        self.website.ensure_index("sbxd.decomposes_to")
        self.website.ensure_index("sbxn")
        self.website.ensure_index("sbxd.e_above_hull")
        self.website.ensure_index("piezo.eij_max")
        self.website.ensure_index("exp_lattice.volume")
        self.website.ensure_index("has")
        self.website.ensure_index("formula_anonymous")
        self.website.ensure_index("spacegroup.number")
        self.website.ensure_index("last_updated")
        self.website.ensure_index("_bt")

    def get_keys(self):
        """
        Gets the doc keys to process
        """
        mat_keys = set(self.materials.distinct(self.materials.key, criteria=self.query))
        keys = set(
            source_keys_updated(
                source=self.materials, target=self.website, query=self.query
            )
        )
        keys |= set(source_keys_updated(source=self.thermo, target=self.website))

        # Get keys for aux docs that have been updated since last processed.
        for source in self.aux:
            new_keys = source_keys_updated(source=source, target=self.website)
            self.logger.info(
                "Only considering {} new keys for {}".format(
                    len(new_keys), source.collection_name
                )
            )
            keys |= set(new_keys)

        keys = (
            keys & mat_keys
        )  # Ensure all keys are present in main materials collection

        return keys

    def add_thermo_docs(self, docs):
        # Add in thermo
        thermo_docs = list(
            self.thermo.query(criteria={self.materials.key: {"$in": list(docs.keys())}})
        )
        thermo_docs = list(sorted(thermo_docs, key=lambda x: x[self.thermo.key]))
        self.logger.debug("Found {} thermo_docs".format(len(thermo_docs)))
        thermo_docs = groupby(thermo_docs, key=lambda x: x[self.thermo.key])
        for task_id, t_docs in thermo_docs:
            docs[task_id]["thermo_docs"] = list(t_docs)

    def add_aux_docs(self, docs):
        # Get documents from all aux stores
        chunked_keys = list(docs.keys())
        aux_docs = []
        for source in self.aux:
            temp_docs = list(source.query(criteria={source.key: {"$in": chunked_keys}}))
            self.logger.debug(
                "Found {} docs in {} for {}".format(
                    len(temp_docs), source.collection_name, chunked_keys
                )
            )

            # Ensure same key field for all docs
            if source.key != self.materials.key:
                for d in temp_docs:
                    d[self.materials.key] = d[source.key]
                    del d[source.key]

            # Ensure same lu_field for all docs
            if source.lu_field != self.materials.lu_field:
                for d in temp_docs:
                    d[self.materials.lu_field] = d[source.lu_field]
                    del d[source.lu_field]

            # Add to our giant pile of docs
            aux_docs.extend(temp_docs)

        # Sort and group docs by materials key
        aux_docs = list(sorted(aux_docs, key=lambda x: x[self.materials.key]))
        aux_docs = groupby(aux_docs, key=lambda x: x[self.materials.key])

        # get docs all for the same materials key
        for task_id, sub_docs in aux_docs:
            # sort and group docs by last_updated
            sub_docs = list(sorted(sub_docs, key=lambda x: x[self.materials.lu_field]))
            self.logger.debug("Merging {} docs for {}".format(len(sub_docs), task_id))
            # merge all docs in this group together
            d = docs[task_id]
            d.update({k: v for doc in sub_docs for k, v in doc.items()})
            # d = {k: v for k, v in d.items() if not k.startswith("_")}
            # Set to most recent lu_field
            d[self.materials.lu_field] = max(
                doc[self.materials.lu_field] for doc in sub_docs
            )


#
#
#
#
# THIS SECTION DEFINES EXTRA FUNCTIONS THAT MODIFY THE MAT DOC PER MP DOC STRUCTURE
#
#


def old_style_mat(new_style_mat):
    """
    Creates the base document for the old MP mapidoc style from the new document structure
    """

    mat = {}
    mp_conversion_dict = _settings["conversion_dict"]
    mag_types = _settings["mag_types"]

    # Uses the conversion dict to copy over values which handles the bulk of the work.
    for mp, new_key in mp_conversion_dict.items():
        if has(new_style_mat, new_key):
            set_(mat, mp, get(new_style_mat, new_key))

    # Anything coming through DFT is always ordered
    mat["is_ordered"] = True
    mat["is_compatible"] = True

    struc = Structure.from_dict(mat["structure"])
    mat["oxide_type"] = oxide_type(struc)
    mat["reduced_cell_formula"] = struc.composition.reduced_composition.as_dict()
    mat["unit_cell_formula"] = struc.composition.as_dict()
    mat["full_formula"] = "".join(struc.formula.split())
    vals = sorted(mat["reduced_cell_formula"].values())
    mat["anonymous_formula"] = {
        string.ascii_uppercase[i]: float(vals[i]) for i in range(len(vals))
    }
    mat["initial_structure"] = new_style_mat.get("initial_structure", None)

    set_(mat, "pseudo_potential.functional", "PBE")

    set_(
        mat,
        "pseudo_potential.labels",
        [
            p["titel"].split()[1]
            for p in get(new_style_mat, "calc_settings.potcar_spec")
        ],
    )
    set_(mat, "pseudo_potential.pot_type", "paw")

    mat["blessed_tasks"] = {
        d["task_type"]: d["task_id"] for d in new_style_mat["origins"]
    }
    mat["deprecated_tasks"] = new_style_mat.get("deprecated_tasks", [])
    mat["ntask_ids"] = len(mat["task_ids"])

    return mat


def add_es(mat, new_style_mat):

    bs_origin = None
    dos_origin = None
    try:
        bs_origin = next(
            (
                origin
                for origin in new_style_mat.get("origins", [])
                if "Line" in origin["task_type"]
            ),
            None,
        )
        dos_origin = next(
            (
                origin
                for origin in new_style_mat.get("origins", [])
                if "Uniform" in origin["task_type"]
            ),
            None,
        )

        if bs_origin:
            u_type = "GGA+U" if "+U" in bs_origin["task_type"] else "GGA"
            set_(mat, "band_structure.{}.task_id".format(u_type), bs_origin["task_id"])

        if dos_origin:
            u_type = "GGA+U" if "+U" in dos_origin["task_type"] else "GGA"
            set_(mat, "dos.{}.task_id".format(u_type), dos_origin["task_id"])

    except Exception as e:
        print("Error in adding electronic structure: {}".format(e))

    mat["has_bandstructure"] = "bandstructure" in new_style_mat.get("has",[])


def add_elastic(mat, new_style_mat):
    if "elasticity" in new_style_mat:
        if has(new_style_mat, "elasticity.structure.sites"):
            mat["elasticity"]["nsites"] = len(
                get(new_style_mat, "elasticity.structure.sites")
            )
        else:
            mat["elasticity"]["nsites"] = len(get(mat, "structure.sites"))

        if get("elasticity.warnings", new_style_mat) is None:
            mat["elasticity"]["warnings"] = []


def add_cifs(doc):
    symprec = 0.1
    struc = Structure.from_dict(doc["structure"])
    sym_finder = SpacegroupAnalyzer(struc, symprec=symprec)
    doc["cif"] = str(CifWriter(struc))
    doc["cifs"] = {}
    try:
        primitive = sym_finder.get_primitive_standard_structure()
        conventional = sym_finder.get_conventional_standard_structure()
        refined = sym_finder.get_refined_structure()
        doc["cifs"]["primitive"] = str(CifWriter(primitive))
        doc["cifs"]["refined"] = str(CifWriter(refined, symprec=symprec))
        doc["cifs"]["conventional_standard"] = str(
            CifWriter(conventional, symprec=symprec)
        )
        doc["cifs"]["computed"] = str(CifWriter(struc, symprec=symprec))
    except:
        doc["cifs"]["primitive"] = None
        doc["cifs"]["refined"] = None
        doc["cifs"]["conventional_standard"] = None


def add_xrd(mat, new_style_mat):
    mat["xrd"] = {}
    for el, doc in new_style_mat.get("xrd", {}).items():
        el_doc = {}
        el_doc["meta"] = ["amplitude", "hkl", "two_theta", "d_spacing"]
        el_doc["created_at"] = datetime.now().isoformat()
        el_doc["wavelength"] = doc["wavelength"]

        xrd_pattern = DiffractionPattern.from_dict(doc["pattern"])
        el_doc["pattern"] = [
            [float(intensity), hkls[0]["hkl"], two_theta, float(d_hkl)]
            for two_theta, intensity, hkls, d_hkl in zip(
                xrd_pattern.x, xrd_pattern.y, xrd_pattern.hkls, xrd_pattern.d_hkls
            )
        ]

        mat["xrd"][el] = el_doc


def add_bonds(mat, new_style_mat):
    if get("bonds.successful", new_style_mat, False):
        mat["bonds"] = get("bonds.summary", new_style_mat)


def add_snl(mat, new_style_mat):
    snl = new_style_mat.get("snl", None)
    mat["snl"] = copy.deepcopy(mat["structure"])
    if snl:
        mat["snl"].update(snl)
    else:
        mat["snl"] = StructureNL(Structure.from_dict(mat["structure"]), []).as_dict()
        mat["snl"]["about"].update(mp_default_snl_fields)

    mat["snl_final"] = mat["snl"]
    mat["icsd_ids"] = [int(i) for i in get(mat["snl"], "about._db_ids.icsd_ids", [])]
    mat["pf_ids"] = get(mat["snl"], "about._db_ids.pf_ids", [])

    # Extract tags from remarks by looking for just nounds and adjectives
    mat["exp"] = {"tags": []}
    for remark in mat["snl"]["about"].get("_tags", []):
        tokens = set(
            tok[1]
            for tok in nltk.pos_tag(nltk.word_tokenize(remark), tagset="universal")
        )
        if len(tokens.intersection({"ADV", "ADP", "VERB"})) == 0:
            mat["exp"]["tags"].append(remark)


def add_propnet(mat, new_style_mat):
    if "propnet" in new_style_mat:
        propnet = new_style_mat.get("propnet", {})
        exclude_list = [
            "compliance_tensor_voigt",
            "task_id",
            "_id",
            "pretty_formula",
            "inputs",
            "last_updated",
        ]
        for e in exclude_list:
            if e in propnet:
                del propnet[e]
        mat["propnet"] = scrub_class_and_module(propnet)


def check_relaxation(mat, new_style_mat):
    final_structure = Structure.from_dict(new_style_mat["structure"])

    warnings = []
    # Check relaxation for just the initial structure to optimized structure
    init_struc = new_style_mat["initial_structure"]

    orig_crystal = Structure.from_dict(init_struc)

    try:
        analyzer = RelaxationAnalyzer(orig_crystal, final_structure)
        latt_para_percentage_changes = (
            analyzer.get_percentage_lattice_parameter_changes()
        )
        for l in ["a", "b", "c"]:
            change = latt_para_percentage_changes[l] * 100
            if change < latt_para_interval[0] or change > latt_para_interval[1]:
                warnings.append(
                    "Large change in a lattice parameter during relaxation."
                )
        change = analyzer.get_percentage_volume_change() * 100
        if change < vol_interval[0] or change > vol_interval[1]:
            warnings.append("Large change in volume during relaxation.")
    except Exception as ex:
        # print icsd_crystal.formula
        # print final_structure.formula
        print(
            "Relaxation analyzer failed for Material:{} due to {}".format(
                mat["task_id"], traceback.print_exc()
            )
        )

    mat["warnings"] = list(set(warnings))


def add_thermo(mat, new_style_mat):
    """
    Add's the thermo values in with sandboxing
    """
    if "thermo_docs" not in new_style_mat:
        mat["deprecated"] = True
        
    if not mat["deprecated"]:
        thermo = new_style_mat["thermo_docs"]

        if "core" in mat["sbxn"]:
            main_sbx = "core"
        else:
            main_sbx = mat["sbxn"][0]

        # Get the primary document and set in mat document
        core_thermo = next(d for d in thermo if main_sbx in d["_sbxn"])

        mat["e_above_hull"] = core_thermo["thermo"]["e_above_hull"]
        mat["formation_energy_per_atom"] = core_thermo["thermo"][
            "formation_energy_per_atom"
        ]
        if "decomposes_to" in core_thermo["thermo"]:
            mat["decomposes_to"] = core_thermo["thermo"]["decomposes_to"]

        sbxd = {}
        sandbox_props = {
            "e_above_hull": "thermo.e_above_hull",
            "decomposes_to": "thermo.decomposes_to",
        }
        for doc in thermo:
            for sbx in doc["_sbxn"]:
                sbx_d = {
                    k: get(doc, v) for k, v in sandbox_props.items() if has(doc, v)
                }
                sbx_d["id"] = sbx
                sbxd[sbx] = sbx_d

        mat["sbxd"] = list(sbxd.values())


def add_meta(mat):
    meta = {"emmet_version": emmet_version, "pymatgen_version": pymatgen_version}
    mat["_meta"] = meta

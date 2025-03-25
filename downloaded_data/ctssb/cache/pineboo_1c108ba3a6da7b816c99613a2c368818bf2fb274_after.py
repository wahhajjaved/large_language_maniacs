# -*- coding: utf-8 -*-
"""
MTD Parser to sqlAlchemy model.

Creates a Python file side by side with the original MTD file.
Can be overloaded with a custom class to enhance/change available
functions. See pineboolib/pnobjectsfactory.py
"""

from pineboolib import application, logging
from pineboolib.application import file
import os

from typing import List, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from pineboolib.application.metadata import pnfieldmetadata, pntablemetadata  # pragma: no cover


LOGGER = logging.get_logger(__name__)

RESERVER_WORDS = ["pass"]


def mtd_parse(table_name: Union[str, "pntablemetadata.PNTableMetaData"], path_mtd: str = "") -> str:
    """
    Parse MTD into SqlAlchemy model.
    """

    if application.PROJECT.conn_manager is None:
        raise Exception("Project is not connected yet")

    if isinstance(table_name, str):
        dest_file = "%s_model.py" % path_mtd
        if not os.path.exists(dest_file):
            mtd_ = application.PROJECT.conn_manager.manager().metadata(table_name, True)
            if mtd_ is None:
                return ""
        else:
            return dest_file

    else:
        dest_file = "%s/cache/%s_model.py" % (application.PROJECT.tmpdir, table_name.name())
        if os.path.exists(dest_file):
            return dest_file

        mtd_ = table_name

    lines = _generate_model(mtd_)
    if not lines:
        dest_file = ""
    else:
        _write_file(dest_file, lines)

    return dest_file


def _write_file(file_name: str, lines: List[str]) -> None:
    """Write lines to a file."""

    file_ = open(file_name, "w", encoding="UTF-8")
    file_.writelines([line if line.endswith("\n") else "%s\n" % line for line in lines])
    file_.close()


def _get_meta(file_mtd: "file.File") -> List[str]:
    """Return list with meta."""

    mtd_data_list: List[str] = []
    if os.path.exists(file_mtd.path()):
        mtd_data = application.PROJECT.conn_manager.manager().metadata(file_mtd.filename, True)
        if mtd_data is not None:
            mtd_data_list = _generate_model(mtd_data, False)

    return mtd_data_list


def _generate_model(mtd_table: "pntablemetadata.PNTableMetaData", header: bool = True) -> List[str]:
    """
    Create a list of lines from a mtd_table (pntablemetadata.PNTableMetaData).
    """

    return _create_declaration(mtd_table, header)


def generate_field(field: "pnfieldmetadata.PNFieldMetaData") -> str:
    """
    Get text representation for sqlAlchemy of a field type given its pnfieldmetadata.PNFieldMetaData.
    """
    data: List[str] = []
    # TYPE

    # = "String"
    ret = ""
    type_ = field.type()
    if type_ in ("int, serial"):
        ret = "sqlalchemy.Integer"
    elif type_ in ("uint"):
        ret = "sqlalchemy.BigInteger"
    elif type_ in ("calculated"):
        ret = "sqlalchemy.String"
    # elif field.type() in ("double"):
    #    ret = "sqlalchemy.Numeric"
    #    ret += "(%s , %s)" % (field.partInteger(), field.partDecimal())
    elif type_ == "double":
        ret = "sqlalchemy.Float"

    elif type_ in ("string", "stringlist", "pixmap"):
        ret = "sqlalchemy.String"
        if field.length():
            ret += "(%s)" % field.length()

    elif type_ in ("bool", "unlock"):
        ret = "sqlalchemy.Boolean"

    elif type_ == "timestamp":
        ret = "sqlalchemy.DateTime"

    elif type_ == "json":
        ret = "sqlalchemy.types.JSON"

    elif type_ == "time":
        ret = "sqlalchemy.Time"

    elif type_ == "date":
        ret = "sqlalchemy.Date"

    elif type_ in ("bytearray"):
        ret = "sqlalchemy.LargeBinary"

    else:
        ret = "Desconocido %s" % type_

    data.append(ret)

    if field.isPrimaryKey():
        data.append("primary_key = True")

    return ", ".join(data)


def generate_field_metadata(field: "pnfieldmetadata.PNFieldMetaData") -> List[str]:
    """Generate field data from a PNFieldMetaData."""

    field_data: List = []

    # NAME
    field_data.append("'name' : '%s'" % field.name())

    # ALIAS
    if field.alias():
        field_data.append("'alias' : '%s'" % field.alias())

    # PK
    if field.isPrimaryKey():
        field_data.append("'pk' : True")
    # CK
    if field.isCompoundKey():
        field_data.append("'ck' : True")

    # TYPE
    field_relation: List[str] = []
    field_data.append("'type' : '%s'" % field.type())

    # LENGTH
    if field.length():
        field_data.append("'length' : %s" % field.length())

    # REGEXP
    if field.regExpValidator():
        field_data.append("'regexp' : '%s'" % field.regExpValidator())

    rel_list: List[str]
    # RELATIONS 1M
    for rel in field.relationList():
        rel_list = []
        rel_list.append("'card' : '%s'" % rel.cardinality())
        rel_list.append("'table' : '%s'" % rel.foreignTable())
        rel_list.append("'field' : '%s'" % rel.foreignField())
        if rel.deleteCascade():
            rel_list.append("'delc' : True")
        if rel.updateCascade():
            rel_list.append("'updc' : True")
        if not rel.checkIn():
            rel_list.append("'checkin' : False")

        field_relation.append("{%s}" % ", ".join(rel_list))

    # if field_relation:
    #    field_data.append("'relations' : [%s]" % ", ".join(field_relation))

    # RELATIONS M1
    if field.private._relation_m1:
        rel = field.private._relation_m1
        rel_list = []
        rel_list.append("'card' : '%s'" % rel.cardinality())
        rel_list.append("'table' : '%s'" % rel.foreignTable())
        rel_list.append("'field' : '%s'" % rel.foreignField())
        if rel.deleteCascade():
            rel_list.append("'delC' : True")
        if rel.updateCascade():
            rel_list.append("'updC' : True")
        if not rel.checkIn():
            rel_list.append("'checkIn' : False")

        field_relation.append("{%s}" % ", ".join(rel_list))

    if field_relation:
        field_data.append("'relations' : [%s]" % ", ".join(field_relation))

    # ASSOCIATED
    if field.private.associated_field_name:

        field_data.append(
            "'associated':{'with' : '%s', 'by' : '%s' }"
            % (field.private.associated_field_filter_to, field.private.associated_field_name)
        )

    # UNIQUE
    if field.isUnique():
        field_data.append("'isunique' : True")

    # ALLOW_NULL
    if not field.allowNull():
        field_data.append("'null' : False")

    # DEFAULT_VALUE
    if field.defaultValue() is not None:
        if field.type() in ["bool", "unlock", "int", "uint", "double", "serial", "json"]:
            value = field.defaultValue()
        else:
            value = "'%s'" % field.defaultValue()

        field_data.append("'default' : %s" % value)

    # OUT_TRANSACTION
    if field.outTransaction():
        field_data.append("'outtransaction' : True")

    # COUNTER
    if field.isCounter():
        field_data.append("'counter' : True")

    # CALCULATED
    if field.calculated():
        field_data.append("'calculated' : True")

    # FULLY_CALCULATED
    if field.fullyCalculated():
        field_data.append("'fullycalculated' : True")

    # TRIMMED
    if field.trimmed():
        field_data.append("'trimmed' : True")

    # VISIBLE
    if not field.visible():
        field_data.append("'visible' : False")

    # VISIBLE_GRID
    if not field.visibleGrid():
        field_data.append("'visiblegrid' : False")

    # EDITABLE
    if not field.editable():
        field_data.append("'editable' : False")

    if field.type() == "double":
        # PARTI
        if field.partInteger():
            field_data.append("'partI' : %s" % field.partInteger())

        # PARTD
        if field.partDecimal():
            field_data.append("'partD' : %s" % field.partDecimal())

    # INDEX
    if field.isIndex():
        field_data.append("'index' : True")

    # OPTIONS_LIST
    if field.optionsList():
        texto = ""
        for item in field.optionsList():
            texto += "'%s', " % item

        field_data.append("'optionslist' : [%s]" % texto)
    # SEARCH_OPTIONS
    if field.searchOptions():
        texto = ""
        for item in field.searchOptions():
            texto += "'%s', " % item

        field_data.append("'searchoptions' : [%s]" % texto)

    return field_data


def use_mtd_fields(path_model: str) -> bool:
    """Return if models use mtd fields."""

    file_ = open(path_model, "r", encoding="UTF-8")
    lines = file_.readlines()
    file_.close()
    for line in lines:
        if line.find("legacy_metadata") > -1:
            return False

    return True


def populate_fields(dest_file_name: str, mtd_name: str) -> str:
    """Populate models fields with mtd field."""

    new_file_path: str = ""
    if mtd_name in application.PROJECT.files.keys():
        file_mtd = application.PROJECT.files[mtd_name]

        file_ = open(dest_file_name, "r")
        lines = file_.readlines()
        file_.close()
        new_lines: List[str] = []
        for number, line in enumerate(list(lines)):
            if line.find("__tablename__") > -1:
                new_lines = lines[0 : number + 1] + _get_meta(file_mtd) + lines[number + 1 :]
                break

        if new_lines:
            new_key = "%s_model.py" % file_mtd.filename[:-4]
            conn = application.PROJECT.conn_manager.mainConn()
            db_name = conn.DBName()
            application.PROJECT.files[new_key] = file.File(
                file_mtd.module,
                "%s_model.py" % file_mtd.path(),
                basedir=file_mtd.basedir,
                sha=file_mtd.sha,
                db_name=db_name,
            )
            application.PROJECT.files[new_key].filekey = "%s_model.py" % file_mtd.filekey
            new_file_path = application.PROJECT.files[new_key].path()
            if os.path.exists(new_file_path):
                os.remove(new_file_path)

            _write_file(new_file_path, new_lines)

    return new_file_path


def _create_declaration(
    mtd_table: "pntablemetadata.PNTableMetaData", header: bool = True
) -> List[str]:
    """Create metadata section."""

    data: List[str] = []
    list_data_field: List[str] = []
    validator_list: List[str] = []
    metadata_table: List = []
    metadata_table.append("'name' : '%s'" % mtd_table.name())
    metadata_table.append("'alias' : '%s'" % mtd_table.alias())
    if mtd_table.isQuery():
        metadata_table.append("'query':'%s'" % mtd_table.query())
    if mtd_table.concurWarn():
        metadata_table.append("'concurwarn': True")
    if mtd_table.detectLocks():
        metadata_table.append("'detectlocks':True")
    if mtd_table.FTSFunction():
        metadata_table.append("'ftsfunction' :'%s'" % mtd_table.FTSFunction())

    try:
        mtd_table.primaryKey()
    except Exception as error:  # noqa: F841
        pass

    field_list: List[List[str]] = []
    pk_found = False

    for field in mtd_table.fieldList():  # Crea los campos

        if field.isPrimaryKey():
            pk_found = True

        if field.name() in validator_list:
            LOGGER.warning(
                "Hay un campo %s duplicado en %s.mtd. Omitido", field.name(), mtd_table.name()
            )
        else:

            field_data = []
            field_data.append("    ")
            if field.name() in RESERVER_WORDS:
                field_data.append("%s_" % field.name())
            else:
                field_data.append(field.name())

            field_data.append(" = sqlalchemy.Column('%s', " % field.name())
            field_list.append(generate_field_metadata(field))
            field_data.append(generate_field(field))
            field_data.append(")")
            validator_list.append(field.name())
            if field.isPrimaryKey():
                pk_found = True

        list_data_field.append("".join(field_data))

    meta_fields: List = []
    for meta_field in field_list:
        meta_fields.append("{%s}" % ", ".join(meta_field))

    metadata_table.append(
        "\n        'fields' : [\n        %s\n        ]" % ",\n        ".join(meta_fields)
    )

    class_name = "%s%s" % (mtd_table.name()[0].upper(), mtd_table.name()[1:])

    if header:
        data.append("# -*- coding: utf-8 -*-")
        data.append("# Translated with pineboolib %s" % application.PINEBOO_VER)
        data.append(
            '"""%s%s_model module."""' % (mtd_table.name()[0].upper(), mtd_table.name()[1:])
        )
        data.append("")

        data.append("from pineboolib.application.database.orm import basemodel")
        data.append("from pineboolib.qsa import qsa")
        data.append("")
        data.append("import sqlalchemy")
        data.append("")
        data.append("")

        data.append("# @class_declaration Oficial")
        data.append("class Oficial(basemodel.BaseModel): # type: ignore [misc] # noqa: F821")
        data.append('    """Oficial class."""')
        data.append("    __tablename__ = '%s'" % mtd_table.name())  # si query nombre query
        data.append("")
    else:
        data.append("")
        data.append("")
        data.append("    # --- POPULATED WITH METADATA FIELDS ---")
        data.append("")
        data.append("")
    data.append("    # --- Metadata --->")
    data.append("    legacy_metadata = {%s}" % ", ".join(metadata_table))
    data.append("\n")
    data.append("    # <--- Metadata ---")

    data.append("")

    data.append("")
    data.append("    # --- Fields --->")
    data.append("")

    for data_field in list_data_field:
        data.append(data_field)

    data.append("")
    data.append("    # <--- Fields ---")

    data.append("")
    if header:
        data.append("# @class_declaration %s" % class_name)
        data.append(
            "class %s(Oficial): # type: ignore [misc] # noqa: F821" % class_name
        )  # si query nombre query
        data.append('    """%s class."""' % class_name)
        data.append("    pass")

    if not pk_found and not mtd_table.isQuery():
        LOGGER.warning(
            "La tabla %s no tiene definida una clave primaria. No se generará el model."
            % (mtd_table.name())
        )
        data = []

    return data

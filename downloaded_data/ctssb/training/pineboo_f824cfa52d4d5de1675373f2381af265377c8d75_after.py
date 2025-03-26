"""PNSqlSchema module."""

from PyQt5 import QtCore, QtWidgets

from pineboolib import logging, application

from pineboolib.core.utils import utils_base
from pineboolib.application.utils import check_dependencies
from pineboolib.application.database import pnsqlquery

from pineboolib.application import qsadictmodules


from typing import Iterable, Optional, Union, List, Any, Dict, cast, TYPE_CHECKING
from pineboolib.core import decorators

from pineboolib.fllegacy import flutil

from sqlalchemy.engine import base, create_engine  # type: ignore [import] # noqa: F821
from sqlalchemy.inspection import inspect  # type: ignore [import] # noqa: F821, F401
from sqlalchemy.orm import sessionmaker  # type: ignore [import] # noqa: F821
from sqlalchemy import event
import sqlalchemy  # type: ignore [import] # noqa: F821, F401


import re


if TYPE_CHECKING:
    from pineboolib.application.metadata import pntablemetadata  # noqa: F401
    from pineboolib.interfaces import iconnection  # noqa: F401
    from sqlalchemy.engine import result  # type: ignore [import] # noqa: F821, F401
    from sqlalchemy.orm import session  # type: ignore [import] # noqa: F821, F401


LOGGER = logging.get_logger(__name__)


class PNSqlSchema(object):
    """PNSqlSchema class."""

    version_: str
    name_: str
    alias_: str
    errorList: List[str]
    lastError_: str
    db_: Any
    _dbname: str
    mobile_: bool
    pure_python_: bool
    defaultPort_: int
    cursor_proxy: Dict[str, "result.ResultProxy"]
    open_: bool
    desktop_file: bool
    _true: Any
    _false: Any
    _like_true: Any
    _like_false: Any
    _null: str
    _text_like: str
    _text_cascade: str
    _safe_load: Dict[str, str]
    _database_not_found_keywords: List[str]
    _parse_porc: bool

    _sqlalchemy_name: str
    _connection: "base.Connection"
    _engine: "base.Engine"
    _session: "session.Session"

    def __init__(self):
        """Inicialize."""
        self.version_ = ""
        self.name_ = ""
        # self._connection = None
        self.errorList = []
        self.alias_ = ""
        self._dbname = ""
        self.mobile_ = False
        self.pure_python_ = False
        self.defaultPort_ = 0
        self._parse_porc = True

        self.lastError_ = ""
        self.db_ = None

        self._text_cascade = "CASCADE"
        self._true = "1"
        self._false = "0"
        self._like_true = "1"
        self._like_false = "0"
        self._null = "Null"
        self._text_like = "::text "
        self._safe_load = {"sqlalchemy": "sqlAlchemy"}
        self._database_not_found_keywords = ["does not exist", "no existe"]

        self._sqlalchemy_name = ""

    def safe_load(self, exit: bool = False) -> bool:
        """Return if the driver can loads dependencies safely."""
        return check_dependencies.check_dependencies(self._safe_load, exit)

    def close(self):
        """Close driver connection."""

        self.open_ = False
        try:
            self._connection.close()
        except AttributeError:
            pass  # fix bug sqlalchemy

    # def singleConnection(self) -> bool:
    #    """Return if driver uses a single connection."""
    #    return self._single_conn

    def loadConnectionString(self, name: str, host: str, port: int, usern: str, passw_: str) -> str:
        """Set special config."""

        return "%s://%s:%s@%s:%s/%s" % (self._sqlalchemy_name, usern, passw_, host, port, name)

    def connect(
        self,
        db_name: str,
        db_host: str,
        db_port: int,
        db_user_name: str,
        db_password: str,
        limit_conn=0,
    ) -> Optional["base.Connection"]:
        """Connect to database."""

        self.setDBName(db_name)
        self.safe_load(True)

        LOGGER.debug = LOGGER.trace  # type: ignore  # Send Debug output to Trace
        conn_ = self.getConn(db_name, db_host, db_port, db_user_name, db_password, limit_conn)

        if conn_ is None:  # Si no existe la conexión
            if application.PROJECT._splash:
                application.PROJECT._splash.hide()
            if not application.PROJECT.DGI.localDesktop():
                return None

            last_error = self.last_error()
            found = False
            for key in self._database_not_found_keywords:
                if key in last_error:
                    found = True
                    break

            if found:
                ret = QtWidgets.QMessageBox.warning(
                    QtWidgets.QWidget(),
                    "Pineboo",
                    "La base de datos %s no existe.\n¿Desea crearla?" % db_name,
                    cast(
                        QtWidgets.QMessageBox.StandardButtons,
                        QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.No,
                    ),
                )
                if ret == QtWidgets.QMessageBox.No:
                    return None
                else:
                    try:
                        tmp_conn = self.getAlternativeConn(
                            db_name, db_host, db_port, db_user_name, db_password
                        )
                        if tmp_conn is not None:
                            self.set_last_error_null()
                            try:
                                tmp_conn.connection.set_isolation_level(0)
                                tmp_conn.execute("CREATE DATABASE %s" % db_name)
                                tmp_conn.connection.set_isolation_level(1)
                            except Exception as error:
                                self.set_last_error(str(error), "LOGGIN")

                                tmp_conn.execute("ROLLBACK")
                                tmp_conn.close()
                                return None

                            tmp_conn.close()
                            conn_ = self.getConn(
                                db_name, db_host, db_port, db_user_name, db_password, limit_conn
                            )

                    except Exception as error:
                        LOGGER.warning(error)
                        QtWidgets.QMessageBox.information(
                            QtWidgets.QWidget(),
                            "Pineboo",
                            "ERROR: No se ha podido crear la Base de Datos %s" % db_name,
                            QtWidgets.QMessageBox.Ok,
                        )
                        LOGGER.error("ERROR: No se ha podido crear la Base de Datos %s", db_name)
                        return None

        if conn_ is not None:
            # if settings.CONFIG.value("ebcomportamiento/orm_enabled", False):
            #    self._engine = self.getEngine(db_name, db_host, db_port, db_user_name, db_password)
            self._connection = conn_
            self.open_ = True
            self.session()
        else:
            LOGGER.error("connect: %s", self.last_error())

        return conn_

    def setDBName(self, name: str) -> None:
        """Set DB Name."""

        self._dbname = name

    @decorators.not_implemented_warn
    def getAlternativeConn(
        self, name: str, host: str, port: int, usern: str, passw_: str
    ) -> Optional["base.Connection"]:
        """Return alternative connection."""

        return None

    def getConn(
        self, name: str, host: str, port: int, usern: str, passw_: str, limit_conn=0
    ) -> Optional["base.Connection"]:
        """Return connection."""

        conn_ = None
        LOGGER.debug = LOGGER.trace  # type: ignore  # Send Debug output to Trace
        queqe_params: Dict[str, Any] = {}

        queqe_params["encoding"] = "UTF-8"
        if limit_conn > 0:
            queqe_params["pool_size"] = limit_conn
            queqe_params["max_overflow"] = int(limit_conn * 2)
            if application.LOG_SQL:
                queqe_params["echo"] = True

        try:
            self._engine = create_engine(
                self.loadConnectionString(name, host, port, usern, passw_), **queqe_params
            )
            conn_ = self._engine.connect()

        except Exception as error:
            self.set_last_error(str(error), "CONNECT")
        return conn_

    def loadSpecialConfig(self) -> None:
        """Set special config."""

        pass

    def version(self) -> str:
        """Return version number."""
        return self.version_

    def driverName(self) -> str:
        """Return driver name."""
        return self.name_

    def is_open(self) -> bool:
        """Return if the connection is open."""
        if hasattr(self, "_engine"):
            conn_ = self.connection()
            return not conn_.closed
        return False

    def pure_python(self) -> bool:
        """Return if the driver is python only."""
        return self.pure_python_

    def mobile(self) -> bool:
        """Return if the driver is mobile ready."""
        return self.mobile_

    def DBName(self) -> str:
        """Return database name."""
        return self._dbname

    def engine(self) -> Any:
        """Return sqlAlchemy ORM engine."""
        return self._engine

    def session(self) -> "session.Session":  # noqa: F811
        """Create a sqlAlchemy session."""
        # if not getattr(self, "_session", None) or self._session.connection().closed:
        #    Session = sessionmaker(bind=self.connection(), autoflush=False, autocommit=True)
        #    self._session = Session()

        # return self._session
        Session = sessionmaker(bind=self.connection(), autoflush=False, autocommit=True)
        new_session = Session()
        setattr(new_session, "_conn_name", self.db_._name)
        return new_session

    def connection(self) -> "base.Connection":
        """Return a cursor connection."""

        if not getattr(self, "_connection", None) or self._connection.closed:

            if getattr(self, "_engine", None):
                self._connection = self._engine.connect()
                event.listen(self._engine, "close", self.close_emited)
            else:
                raise Exception("Engine is not loaded!")
        return self._connection

    def formatValueLike(self, type_: str, v: Any, upper: bool) -> str:
        """Return a string with the format value like."""

        util = flutil.FLUtil()
        res = "IS NULL"

        if type_ == "bool":
            s = str(v[0]).upper()
            if s == str(util.translate("application", "Sí")[0]).upper():
                res = "=%s" % self._like_true
            else:
                res = "=%s" % self._like_false

        elif type_ == "date":
            dateamd = util.dateDMAtoAMD(str(v))
            if dateamd is None:
                dateamd = ""
            res = self._text_like + "LIKE '%%" + dateamd + "'"

        elif type_ == "time":
            t = v.toTime()
            res = self._text_like + "LIKE '" + t.toString(QtCore.Qt.ISODate) + "%%'"

        else:
            res = str(v)
            if upper:
                res = "%s" % res.upper()

            res = self._text_like + "LIKE '" + res + "%%'"

        return res

    def formatValue(self, type_: str, v: Any, upper: bool) -> Optional[Union[int, str, bool]]:
        """Return a string with the format value."""
        util = flutil.FLUtil()

        s: Any = None

        # if v is None:
        #    return "NULL"

        if type_ == "pixmap":
            if v.find("'") > -1:
                s = "'%s'" % self.normalizeValue(v)
            else:
                s = "'%s'" % v

        elif type_ in ("bool", "unlock"):
            if isinstance(v, bool):
                s = self._true if v else self._false
            else:
                s = self._true if utils_base.text2bool(v) else self._false

        elif type_ == "date":
            if len(str(v).split("-")[0]) < 3:
                date_ = str(util.dateDMAtoAMD(v))
            else:
                date_ = "%s" % v

            s = "'%s'" % date_

        elif type_ == "time":
            s = "'%s'" % v if v else ""

        elif type_ in ("uint", "int", "double", "serial"):
            s = v or 0

        elif type_ in ("string", "stringlist", "timestamp"):
            if not v:
                s = self._null
            else:
                if type_ == "string":
                    v = utils_base.auto_qt_translate_text(v)
                    if upper:
                        v = v.upper()

            s = "'%s'" % v
        else:
            s = v

        return str(s)

    def canOverPartition(self) -> bool:
        """Return can override partition option ready."""
        return True

    def canRegenTables(self) -> bool:
        """Return if can regenerate tables."""
        return True

    def nextSerialVal(self, table_name: str, field_name: str) -> int:
        """Return next serial value."""

        table_max = 0
        flseq_max = 0
        res_ = 0
        sql = "SELECT MAX(%s) FROM %s WHERE 1=1" % (field_name, table_name)
        cur = self.execute_query(sql)
        if cur is not None:
            value = cur.fetchone()

            if value is not None:
                table_max = value[0] or 0

        sql = "SELECT seq FROM flseqs WHERE tabla = '%s' AND campo ='%s'" % (table_name, field_name)
        cur = self.execute_query(sql)
        if cur is not None:
            value = cur.fetchone()

            if value is not None:
                flseq_max = value[0] or 0

        res_ = flseq_max or table_max
        res_ += 1

        str_qry = ""
        if flseq_max:
            if res_ > flseq_max:
                str_qry = "UPDATE flseqs SET seq=%s WHERE tabla = '%s' AND campo = '%s'" % (
                    res_,
                    table_name,
                    field_name,
                )
        else:
            str_qry = "INSERT INTO flseqs (tabla,campo,seq) VALUES('%s','%s',%s)" % (
                table_name,
                field_name,
                res_,
            )

        if str_qry:
            try:
                self.execute_query(str_qry)
            except Exception as error:
                LOGGER.error("nextSerialVal: %s", str(error))
                self.session().rollback()

        return res_

    def set_last_error_null(self) -> None:
        """Set lastError flag Null."""
        self.lastError_ = ""

    def set_last_error(self, text: str, command: str) -> None:
        """Set last error."""
        self.lastError_ = "%s (%s)" % (text, command)
        LOGGER.error(self.lastError_)

    def last_error(self) -> str:
        """Return last error."""
        return self.lastError_

    @decorators.not_implemented_warn
    def setType(self, type_: str, leng: int = 0) -> str:
        """Return type definition."""
        return ""

    def existsTable(self, table_name: str) -> bool:
        """Return if exists a table specified by name."""

        if self._engine:
            return table_name in self._engine.table_names(None, self.session().connection())
        else:
            raise Exception("No engine or connection exists!")

    @decorators.not_implemented_warn
    def sqlCreateTable(
        self, tmd: "pntablemetadata.PNTableMetaData", create_index: bool = True
    ) -> Optional[str]:
        """Return a create table query."""
        return ""

    def mismatchedTable(
        self, table1_name: str, table2_metadata: "pntablemetadata.PNTableMetaData"
    ) -> bool:
        """Return if a table is mismatched."""

        dict_metadata = {}
        dict_database = {}

        for rec_m in self.recordInfo(table2_metadata):
            dict_metadata[rec_m[0]] = rec_m
        for rec_d in self.recordInfo2(table1_name):
            dict_database[rec_d[0]] = rec_d

        diff = list(set(list(dict_database.keys())) - set(list(dict_metadata.keys())))

        if len(diff) > 0:
            return True

        if not dict_database and dict_metadata:
            return True

        for name in dict_metadata.keys():
            if name in dict_database.keys():
                if self.notEqualsFields(dict_database[name], dict_metadata[name]):
                    return True
            else:
                return True

        return False

    @decorators.not_implemented_warn
    def recordInfo2(self, tablename: str) -> List[List[Any]]:
        """Return info from a database table."""
        return []

    def recordInfo(self, table_metadata: "pntablemetadata.PNTableMetaData") -> List[list]:
        """Obtain current cursor information on columns."""

        info = []

        for field in table_metadata.fieldList():
            info.append(
                [
                    field.name(),
                    field.type(),
                    not field.allowNull(),
                    field.length(),
                    field.partDecimal(),
                    field.defaultValue(),
                    field.isPrimaryKey(),
                ]
            )
        return info

    @decorators.not_implemented_warn
    def decodeSqlType(self, type_: str) -> str:
        """Return the specific field type."""
        return ""

    def notEqualsFields(self, field1: List[Any], field2: List[Any]) -> bool:
        """Return if a field has changed."""

        ret = False
        try:
            if not field1[2] == field2[2] and not field2[6]:
                ret = True

            if field1[1] == "stringlist" and not field2[1] in ("stringlist", "pixmap"):

                ret = True

            elif field1[1] == "string" and (
                field2[1] not in ("string", "time", "date") or field1[3] != field2[3]
            ):
                if field2[1] in ("time", "date") and field1[3] == 20:
                    ret = False
                elif field1[1] == "string" and field2[3] != 0:
                    if field1[3] == 1 and field2[3] == 0:
                        ret = False
                    elif field1[3] == 0 and field2[3] == 255:  # mysql
                        ret = False
                    else:
                        ret = True
            elif field1[1] == "uint" and not field2[1] in ("int", "uint", "serial"):
                ret = True
            elif field1[1] == "bool" and not field2[1] in ("bool", "unlock"):
                ret = True
            elif field1[1] == "double" and not field2[1] == "double":
                ret = True
            elif field1[1] == "timestamp" and not field2[1] == "timestamp":
                ret = True

        except Exception:
            LOGGER.error("notEqualsFields %s %s", field1, field2)

        if ret:
            LOGGER.warning("Falla database: %s, metadata: %s", field1, field2)

        return ret

    @decorators.not_implemented_warn
    def tables(self, typeName: Optional[str] = None) -> List[str]:
        """Return a tables list specified by type."""
        return []

    def normalizeValue(self, text: str) -> str:
        """Return a database friendly text."""

        res = str(text).replace("'", "''")
        if self._parse_porc:
            res = res.replace("%", "%%")
        # res = res.replace(":", "\\:")
        return res

    def hasCheckColumn(self, metadata: "pntablemetadata.PNTableMetaData") -> bool:
        """Retrieve if MTD has a check column."""

        for field in metadata.fieldList():
            if field.isCheck() or field.name().endswith("_check_column"):
                return True

        return False

    @decorators.not_implemented_warn
    def constraintExists(self, name: str) -> bool:
        """Return if constraint exists specified by name."""
        return False

    def remove_index(self, metadata: "pntablemetadata.PNTableMetaData", cursor: Any) -> bool:
        """Remove olds index."""

        return True

    def alterTable(self, new_metadata: "pntablemetadata.PNTableMetaData") -> bool:
        """Modify a table structure."""

        if self.hasCheckColumn(new_metadata):
            return False

        field_list = new_metadata.fieldList()
        if not field_list:
            return False

        util = flutil.FLUtil()
        table_name = new_metadata.name()

        old_columns_info = self.recordInfo2(table_name)
        old_field_names: List[str] = []
        for old_column in old_columns_info:
            old_field_names.append(old_column[0])

        renamed_table = "%salteredtable%s" % (
            table_name,
            QtCore.QDateTime().currentDateTime().toString("ddhhssz"),
        )

        query = pnsqlquery.PNSqlQuery(None, "dbAux")

        session_ = query.db().session()
        query.db().transaction()

        # if session_.transaction:
        #    session_.begin_nested()
        # else:
        #    session_.begin()

        if not self.remove_index(new_metadata, query):
            session_.rollback()
            return False

        if not query.exec_("ALTER TABLE %s RENAME TO %s" % (table_name, renamed_table)):
            session_.rollback()
            return False

        if not self.db_.createTable(new_metadata):

            session_.rollback()
            return False

        cur = self.execute_query(
            "SELECT %s FROM %s WHERE 1=1" % (", ".join(old_field_names), renamed_table)
        )
        old_data_list = cur.fetchall() if cur else []
        # old_cursor = pnsqlcursor.PNSqlCursor(renamed_table, True, "dbAux")
        # old_cursor.setModeAccess(old_cursor.Browse)
        # old_cursor.select()
        util.createProgressDialog(
            util.translate("application", "Reestructurando registros para %s...")
            % new_metadata.alias(),
            len(old_data_list),
        )

        util.setLabelText(util.translate("application", "Tabla modificada"))

        new_field_names: List[str] = new_metadata.fieldNames()

        list_records = []
        for number_progress, old_data in enumerate(old_data_list):
            new_buffer = []

            for new_idx, new_name in enumerate(new_field_names):
                new_field = new_metadata.field(new_name)
                if new_field is None:
                    LOGGER.warning(
                        "Field %s not found un metadata %s" % (new_name, new_metadata.name())
                    )
                    session_.rollback()

                    return False
                value = None
                if new_name in old_field_names:
                    value = old_data[old_field_names.index(new_name)]
                    if value is None:
                        continue
                elif not new_field.allowNull():
                    value = new_field.defaultValue()
                    if value is None:
                        if new_field.type() == "timestamp":
                            value = self.getTimeStamp()
                        else:
                            continue
                else:
                    continue

                new_buffer.append([new_field, value])

            list_records.append(new_buffer)

            util.setProgress(number_progress)

        util.destroyProgressDialog()
        if not self.insertMulti(table_name, list_records):
            session_.rollback()
            return False
        else:

            session_.commit()

        query.exec_("DROP TABLE %s %s" % (renamed_table, self._text_cascade))
        return True

    def cascadeSupport(self) -> bool:
        """Return True if the driver support cascade."""
        return True

    def canDetectLocks(self) -> bool:
        """Return if can detect locks."""
        return True

    def fix_query(self, val: str) -> str:
        """Fix values on SQL."""
        ret_ = val.replace("'true'", "1")
        ret_ = ret_.replace("'false'", "0")
        ret_ = ret_.replace("'0'", "0")
        ret_ = ret_.replace("'1'", "1")
        return ret_

    # def desktopFile(self) -> bool:
    #    """Return if use a file like database."""
    #    return self.desktop_file

    def execute_query(self, query: str) -> Optional["result.ResultProxy"]:
        """Excecute a query and return result."""

        if not self.is_open():
            raise Exception("execute_query: Database not open %s", self)

        self.set_last_error_null()

        # if self._session:
        #    session_ = self._session
        # else:
        session_ = self.session()
        result_ = None
        try:
            try:
                # query_ = sqlalchemy.text(query)
                result_ = session_.connection().execute("""%s""" % query)

                # LOGGER.warning(
                #    "execute_query: %s, session: %s, transaction: %s",
                #    query[:50],
                #    session_,
                #    session_.transaction,
                # )
            except sqlalchemy.exc.DBAPIError as error:
                LOGGER.warning(
                    "Se ha producido un error DBAPI con la consulta %s. Ejecutando rollback necesario",
                    query,
                    stack_info=True,
                )
                session_.rollback()
                self.set_last_error(
                    "No se pudo ejecutar la query %s.\n%s" % (query, str(error)), query
                )

        except Exception as error:
            LOGGER.warning(
                "Se ha producido un error al ejecutar la consulta %s.\n%s" % (query, str(error)),
                stack_info=True,
            )
            self.set_last_error("No se pudo ejecutar la query %s.\n%s" % (query, str(error)), query)

        return result_

    def getTimeStamp(self) -> str:
        """Return TimeStamp."""

        sql = "SELECT CURRENT_TIMESTAMP"

        cur = self.execute_query(sql)
        time_stamp_: str

        result_ = cur.fetchall() if cur else []

        for line in result_:
            time_stamp_ = line[0]
            break

        if time_stamp_ is None:
            raise Exception("timestamp is empty!")

        return time_stamp_

    def close_emited(self, *args):
        """."""
        pass
        # LOGGER.warning("** %s, %s", self, args)

    def insertMulti(
        self, table_name: str, list_records: Iterable = []
    ) -> bool:  # FIXME SQLITE NO PUEDE TODAS DE GOLPE
        """Insert several rows at once."""

        model_ = qsadictmodules.QSADictModules.from_project("%s_orm" % table_name)
        session_ = self.db_.connManager().dbAux().session()
        if not model_:
            return False

        for number, line in enumerate(list_records):
            # model_obj = model_()
            field_names = []
            field_values = []
            for field, value in line:
                if field.generated():

                    if field.type() in ("string", "stringlist", "bytearray"):
                        value = self.normalizeValue(value)

                        if value in ["Null", "NULL"]:
                            value = "''"
                        else:
                            value = self.formatValue(field.type(), value, False)
                    else:
                        value = self.formatValue(field.type(), value, False)

                # setattr(model_obj, field.name(), value)

                field_names.append(field.name())
                field_values.append(value)

            sql = None
            if field_names:
                sql = """INSERT INTO %s(%s) values (%s)""" % (
                    table_name,
                    ", ".join(field_names),
                    ", ".join(map(str, field_values)),
                )

            if sql:
                try:
                    session_.connection().execute(sql)
                except Exception as error:
                    LOGGER.error("insertMulti: %s", str(error))
                    return False
        session_.flush()
        return True

    def Mr_Proper(self) -> None:
        """Clear all garbage data."""

        util = flutil.FLUtil()
        conn_dbaux = self.db_.connManager().dbAux()

        multi_fllarge = False
        fllarge_tables_list: List[str] = []
        fllarge_to_delete: Dict[str, List[str]] = {}
        sql = "SELECT valor FROM flsettings WHERE flkey=%s" % self.formatValue(
            "string", "FLLargeMode", False
        )
        cursor = conn_dbaux.execute_query(sql)
        try:
            result_ = cursor.fetchone()
            if result_:
                multi_fllarge = utils_base.text2bool(str(result_[0]))
        except Exception as error:
            LOGGER.warning("Mr_Proper: %s" % str(error))

        if not multi_fllarge:
            fllarge_tables_list.append("fllarge")

        tables = self.tables("Tables")
        altered_tables = []
        for table_name in tables:
            if table_name.find("alteredtable") > -1:
                altered_tables.append(table_name)
            elif multi_fllarge and table_name.startswith("fllarge_"):
                fllarge_tables_list.append(table_name)

        LOGGER.debug(
            "Tablas fllarge. Modo multiple: %s Lista : %s sql : %s",
            multi_fllarge,
            fllarge_tables_list,
            sql,
        )

        util.createProgressDialog(
            util.translate("application", "Revisando tablas fllarge"), len(fllarge_tables_list)
        )

        for number, table_fllarge in enumerate(fllarge_tables_list):
            util.setLabelText(util.translate("application", "Revisando tabla %s" % table_fllarge))

            sql = "SELECT refkey FROM %s WHERE 1 = 1" % table_fllarge
            cursor = conn_dbaux.execute_query(sql)
            old_target = ""
            metadata_target = None

            for line in list(cursor):

                target = line[0].split("@")[1]
                found = False
                if target != old_target:
                    metadata_target = self.db_.connManager().manager().metadata(target)
                    old_target = target

                if metadata_target is None:
                    LOGGER.warning("Error limpiando fllarge: %s no tiene un metdata válido", target)
                    return
                else:
                    for field in metadata_target.fieldList():
                        if found:
                            break
                        if field.type() == "pixmap":
                            sql = "SELECT %s FROM %s WHERE 1 = 1" % (
                                field.name(),
                                target,
                            )  # 1 a 1 , si busco especifico me da problemas mssql

                            cursor_finder = conn_dbaux.execute_query(sql)
                            for result_finder in list(cursor_finder):
                                if result_finder[0] == line[0]:
                                    found = True
                                    break

                    if not found:
                        if table_fllarge not in fllarge_to_delete.keys():
                            fllarge_to_delete[table_fllarge] = []
                        fllarge_to_delete[table_fllarge].append(line[0])

            util.setProgress(number)

        util.destroyProgressDialog()

        util.createProgressDialog(
            util.translate("application", "Limpiando tablas fllarge"), len(fllarge_to_delete)
        )
        for number, key in enumerate(fllarge_to_delete.keys()):
            for ref_key in fllarge_to_delete[key]:
                LOGGER.debug("Eliminado %s.%s", key, ref_key)
                util.setLabelText(util.translate("application", "Limpiando tabla fllarge %s" % key))
                sql = "DELETE FROM %s WHERE refkey = %s" % (
                    key,
                    self.formatValue("string", ref_key, False),
                )
                conn_dbaux.execute_query(sql)

            util.setProgress(number)

        util.destroyProgressDialog()

        conn_dbaux.transaction()

        # query = pnsqlquery.PNSqlQuery(None,conn_dbaux)
        cursor = conn_dbaux.execute_query(
            "SELECT nombre FROM flfiles WHERE nombre "
            + self.formatValueLike("string", "%%.mtd", False)
        )
        list_mtds = []
        try:
            for data in list(cursor):
                list_mtds.append(data[0])
        except Exception as error:
            LOGGER.error("Mr_Proper: %s", error)

        reg_exp = re.compile("^.*\\d{6,9}$")
        bad_list_mtds = list(filter(reg_exp.match, list_mtds))

        util.createProgressDialog(
            util.translate("application", "Borrando backups"), len(bad_list_mtds)
        )

        for number, mtd_name in enumerate(bad_list_mtds):
            util.setLabelText(util.translate("application", "Borrando registro %s" % mtd_name))
            conn_dbaux.execute_query("DELETE FROM flfiles WHERE nombre ='%s'" % mtd_name)
            util.setProgress(number)

        util.setTotalSteps(len(altered_tables))

        for number, altered_table_name in enumerate(altered_tables):
            util.setLabelText(
                util.translate("application", "Borrando registro %s" % altered_table_name)
            )
            if self.existsTable(altered_table_name):
                util.setLabelText(
                    util.translate("application", "Borrando tabla %s" % altered_table_name)
                )
                conn_dbaux.execute_query(
                    "DROP TABLE %s %s" % (altered_table_name, self._text_cascade)
                )

            util.setProgress(number)

        util.destroyProgressDialog()

        tables = self.tables("Tables")

        util.createProgressDialog(
            util.translate("application", "Comprobando base de datos"), len(tables) + 2
        )
        for number, table_name in enumerate(tables):
            util.setLabelText(util.translate("application", "Comprobando tabla %s" % table_name))
            metadata = conn_dbaux.connManager().manager().metadata(table_name)
            if metadata is not None:
                if self.mismatchedTable(table_name, metadata):
                    if metadata:
                        msg = util.translate(
                            "application",
                            "La estructura de los metadatos de la tabla '%s' y su "
                            "estructura interna en la base de datos no coinciden. "
                            "Intentando regenerarla." % table_name,
                        )

                        LOGGER.warning(msg)
                        self.alterTable(metadata)

            util.setProgress(number)

        util.destroyProgressDialog()
        self.checkSequences()

        util.createProgressDialog(util.translate("application", "Comprobando base de datos"), 4)
        util.setLabelText(util.translate("application", "Borrando flmetadata"))
        util.setProgress(1)
        conn_dbaux.execute_query("DELETE FROM flmetadata")
        util.setLabelText(util.translate("application", "Borrando flvar"))
        util.setProgress(2)
        conn_dbaux.execute_query("DELETE FROM flvar")
        conn_dbaux.connManager().manager().cleanupMetaData()
        conn_dbaux.commit()

        util.setLabelText(util.translate("application", "Vacunando base de datos"))
        util.setProgress(3)
        self.vacuum()

        util.setProgress(4)
        util.destroyProgressDialog()

    def vacuum(self):
        """Vacuum tables."""

        # self._connection.connection.set_isolation_level(0)
        self.execute_query("vacuum")
        # self._connection.connection.set_isolation_level(1)

    def sqlLength(self, field_name: str, size: int) -> str:
        """Return length formated."""

        return "LENGTH(%s)=%s" % (field_name, size)

    def checkSequences(self) -> None:
        """Check sequences."""

        return

    def regenTable(self, table_name: str, new_metadata: "pntablemetadata.PNTableMetaData") -> bool:
        """Regenerate tables."""

        must_alter = self.mismatchedTable(table_name, new_metadata)

        if must_alter:
            must_alter = self.alterTable(new_metadata)

            if must_alter:
                conn_dbaux = self.db_.connManager().dbAux()
                reg_exp = re.compile("^.*\\d{6,9}$")
                bad_list_tables = list(filter(reg_exp.match, self.tables("Tables")))

                sql = "SELECT nombre FROM flfiles WHERE nombre%s" % self.formatValueLike(
                    "string", "%%alteredtable", False
                )
                cursor = conn_dbaux.execute_query(sql)
                for name in cursor:
                    sql = "DELETE FROM flfiles WHERE nombre ='%s'" % name
                    conn_dbaux.execute_query(sql)
                    if name.find("alteredtable") > -1 and self.existsTable(
                        name.replace(".mtd", "")
                    ):
                        conn_dbaux.execute_query(
                            "DROP TABLE %s %s" % (name.replace(".mtd", ""), self._text_cascade)
                        )

                for bad_table in bad_list_tables:
                    if self.existsTable(bad_table):
                        conn_dbaux.execute_query(
                            "DROP TABLE %s %s" % (bad_table, self._text_cascade)
                        )

                conn_dbaux.commit()

        return must_alter

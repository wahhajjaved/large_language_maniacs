import atp_classes, re, platform, os


class TeradataDB:

    def __init__(self, host=None, port=None, username=None, password=None, database=None, auth_mech=None):
        config = atp_classes.Config()
        self.host = host or config.get_config()['database']['dataWarehouse']['host']
        self.username = username or config.get_config()['database']['dataWarehouse']['username']
        self.password = password or config.get_config()['database']['dataWarehouse']['password']

    def execute_query(self, query_string):
        result_rows = []

        if platform.mac_ver()[0] != '':
            import teradata

            udaExec = teradata.UdaExec(appName="DataFetcher", version="1.0", logConsole=False)

            with udaExec.connect(method="odbc", system=self.host, username=self.username, password=self.password)as conn:
                with conn.cursor() as cur:
                    try:
                        print "executing query"

                        # Execute query
                        cur.execute(query_string)

                        print "done executing query"

                        # Get column names
                        columns = cur.description

                        # Fetch table results
                        for row in cur:
                            result_obj = {}
                            for index, val in enumerate(columns):
                                # Remove characters and dot which precedes column name for key values
                                result_obj[re.sub(r'.*[.]', '', val[0])] = str(row[index]).strip()
                            result_rows.append(result_obj)
                    except Exception, e:
                        return e

            conn.close()
        else:
            import jaydebeapi
            import jpype

            try:
                if not jpype.isJVMStarted():
                    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    jar = r'{lib_path_gss}{java_sep}{lib_path_jdbc}'.format(lib_path_gss=os.path.join(current_dir,"lib",'tdgssconfig.jar'),
                                                                            java_sep=os.pathsep,
                                                                            lib_path_jdbc=os.path.join(current_dir,'lib','terajdbc4.jar'))
                    args='-Djava.class.path=%s' % jar

                    if 'JVM_PATH' in os.environ:
                        jvm_path = os.environ['JVM_PATH']
                    else:
                        jvm_path = jpype.getDefaultJVMPath()

                    jpype.startJVM(jvm_path, args)

                conn = jaydebeapi.connect('com.teradata.jdbc.TeraDriver','jdbc:teradata://{url}/USER={user},PASSWORD={password}'
                                          .format(url=self.host, user=self.username, password=self.password))
                cur = conn.cursor()
                print "executing query"

                # Execute query
                cur.execute(query_string)

                print "done executing query"

                # Get column names
                columns = cur.description

                # Fetch table results
                for row in cur:
                    result_obj = {}
                    for index, val in enumerate(columns):
                        # Remove characters and dot which precedes column name for key values
                        result_obj[re.sub(r'.*[.]', '', val[0])] = str(row[index]).strip()
                    result_rows.append(result_obj)

                conn.close()
            except Exception, e:
                        return e

        return result_rows

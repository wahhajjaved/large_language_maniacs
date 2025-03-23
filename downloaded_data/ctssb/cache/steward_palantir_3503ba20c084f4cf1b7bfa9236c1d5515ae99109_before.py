""" Storage interfaces for steward_palantir """

class IStorage(object):
    """
    Storage interface for steward_palantir

    Provides an abstraction layer on top of whatever storage backend is
    available

    """
    def __init__(self, request):
        self.request = request

    def add_check_result(self, minion, check, retcode, stdout, stderr):
        """
        Add a check result to the history for a minion

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check
        retcode : int
            Return code of the check
        stdout : str
            The stdout of the check
        stderr : str
            The stderr of the check

        Returns
        -------
        status : dict
            The same return value as check_status

        """
        raise NotImplementedError

    def get_alerts(self):
        """
        Get a list of alerts

        Returns
        -------
        alerts : list
            List of tuples of (minion, check)

        """
        raise NotImplementedError

    def add_alert(self, minion, check):
        """
        Mark a check as failing

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        """
        raise NotImplementedError

    def remove_alert(self, minion, check):
        """
        Mark a check as no longer failing

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        """
        raise NotImplementedError

    def check_status(self, minion, check):
        """
        Get the stored check data for a minion

        Parameters
        ----------
        minion : str
            Name of the minion
        check : str
            Name of the check

        Returns
        -------
        retcode : int
            Current check status
        count : int
            Number of times the current retcode has been returned
        previous : int
            Previous retcode
        stdout : str
            The stdout from the last check
        stderr : str
            The stderr from the last check

        Notes
        -----
        Return value is a dict. Will return None if the check has not run yet.

        """
        raise NotImplementedError

    def delete_minion(self, minion):
        """
        Delete a minion from the database

        Parameters
        ----------
        minion : str
            Name of the minion

        """
        raise NotImplementedError

    def clear(self):
        """ Clear the database """
        raise NotImplementedError


class IDictStorage(IStorage):
    """ Extension of IStorage that is backed by a dict """
    db = None

    def _add_minion_key(self, minion, key):
        """ Keep track of all keys belonging to a minion """
        keys = self.db.get(minion + '_keys', [])
        keys.append(key)
        self.db[minion + '_keys'] = keys

    def add_check_result(self, minion, check, retcode, stdout, stderr):
        minion_check = minion + '_' + check
        if minion_check not in self.db:
            self._add_minion_key(minion, minion_check)

        result = self.db.get(minion_check, {'retcode':0, 'count':0,
                                             'previous':0})

        if result['retcode'] == retcode:
            result['count'] += 1
        else:
            result['previous'] = result['retcode']
            result['retcode'] = retcode
            result['count'] = 1


        result['stdout'] = stdout
        result['stderr'] = stderr
        self.db[minion_check] = result
        return result

    def get_alerts(self):
        return self.db.get('alerts')

    def add_alert(self, minion, check):
        alerts = self.db.get('alerts', [])
        alerts.append((minion, check))
        self.db['alerts'] = alerts

    def remove_alert(self, minion, check):
        alerts = self.db.get('alerts', [])
        alerts.remove((minion, check))
        self.db['alerts'] = alerts

    def check_status(self, minion, check):
        return self.db.get(minion + '_' + check)

    def delete_minion(self, minion):
        for key in self.db.get(minion + '_keys'):
            del self.db[key]
        del self.db[minion + '_keys']

        alerts = self.db.get('alerts', [])
        index = 0
        while index < len(alerts):
            if minion == alerts[index][0]:
                del alerts[index]
                continue
            index += 1
        self.db['alerts'] = alerts

    def clear(self):
        self.db.clear()


class MemoryStorage(IDictStorage):
    """ Simple in-memory storage """
    @property
    def db(self):
        """ Accessor for in-memory dict """
        if not hasattr(self.request.registry, 'palantir_storage_impl'):
            self.request.registry.palantir_storage_impl = {}
        return self.request.registry.palantir_storage_impl


class SqliteDictStorage(IDictStorage):
    """ Storage system using steward_sqlitedict """
    @property
    def db(self):
        """ Accessor for sqlitedict """
        return self.request.sqld('palantir')

""" The Facade for the TransferClient. Uses site as an argument to most
    of the methods (rather them its parts)
"""
from pdm.userservicedesk.TransferClient import TransferClient


class TransferClientFacade(TransferClient):
    """
    Transfer client facade. Method take URI(s) as parameter(s) rather the its parts.
    """

    def __init__(self, token):
        super(TransferClientFacade, self).__init__(token)

    def list(self, site, **kwargs):
        """
        List the resource specified by site.
        :param site: site to list
        :param kwargs: additional arguments (like max_tries or priority)
        :return: the resource listing
        """

        sitename, path = self.split_site_path(site)
        if sitename:
            return super(TransferClientFacade, self).list(sitename, path, **kwargs)
        else:
            print "Malformed site path (probably missing colon)", site
            return None

    def copy(self, src_site, dst_site, **kwargs):
        """
        Copy files or directories from one site to another.
        :param src_site: source site
        :param dst_site: destination site
        :param kwargs: addition arguments (like max_tries ot priority)
        :return: copy result message
        """

        src_sitename, src_path = self.split_site_path(src_site)
        dst_sitename, dst_path = self.split_site_path(dst_site)

        if not src_sitename:
            print "Malformed site path (probably missing colon)", src_site
            return None

        if not dst_sitename:
            print "Malformed site path (probably missing colon)", dst_site
            return None

        return super(TransferClientFacade, self).copy(src_sitename, src_path,
                                                      dst_sitename, dst_path,
                                                      **kwargs)

    def remove(self, src_site, **kwargs):
        """
        Remove the resources (file or directory)
        :param src_site: site to remove from
        :param kwargs: additional arguments (like max_tries or priority)
        :return: remove result message
        """

        sitename, path = self.split_site_path(src_site)
        if sitename:
            return super(TransferClientFacade, self).remove(sitename, path, **kwargs)
        else:
            print "Malformed site path (probably missing colon)", src_site
            return None

    def mkdir(self, sitepath, **kwargs):
        """
        Create a new directory at the site.
        :param site_path: string of a form sitename:directory_path_to_create
        :return: mkdir result message, or None if malformed site path
        """
        sitename, path = self.split_site_path(sitepath)
        if sitename:
            return super(TransferClientFacade, self).mkdir(sitename, path, **kwargs)
        else:
            print "Malformed site path (probably missing colon)", sitepath
            return None

    def rename(self, site_path, newname, **kwargs):
        """
        Rename a file.
        :param site_path: string of a form sitename:file_path_to_rename
        :param newname new file name (w/o the site prefix)
        :return: rename result message, or None if malformed site path
        """
        sitename, path = self.split_site_path(site_path)
        new_site, newpath = self.split_site_path(newname)
        if new_site:
            print "Malformed (new) site path (it has to start with a : " \
                  "since source and dest share the same site)", new_site
            return None
        if sitename:
            return super(TransferClientFacade, self).rename(sitename, path, newpath, **kwargs)
        else:
            print "Malformed (old) site path (probably missing colon)", site_path
            return None

    @staticmethod
    def split_site_path(path):
        """
        Split a site string at the first colon. Return a tuple containing a (site, path) or
        (None, None) if the colon is missing.
        """

        parts = path.split(':', 1)
        if len(parts) == 2:
            return parts
        else:
            return None, None


class MockTransferClientFacade(object):
    """
    Mock Transfer Client.
    """

    def __init__(self, token):
        self.__token = token

    @staticmethod
    def list(site, **kwargs):
        """
        :param site: site to list
        :param kwargs: keywords agrs to match real list fcn
        :return: an str(site)
        """
        # pylint: disable=unused-argument
        return str(site)

    @staticmethod
    def output(jobid):
        """
        Dummy to be mocked away
        :param id:
        :return:
        """
        return "job id %s listnig: whatever", jobid

    @staticmethod
    def remove(site, **kwargs):
        """
        Mock remove.
        :param site: site to delete
        :param kwargs:
        :return: information message
        """
        # pylint: disable=unused-argument
        return " Resource %s removed " % site

    @staticmethod
    def copy(ssite, tsite, **kwargs):
        """
        Mock copy
        :param ssite: source site
        :param tsite: target site
        :param kwargs:
        :return:
        """
        # pylint: disable=unused-argument
        return " copy %s to %s succeeded " % (ssite, tsite)

import datetime
import functools
from simple_salesforce import Salesforce
from simple_salesforce import SalesforceMalformedRequest
from simple_salesforce.util import date_to_iso8601

def memoize(obj):
    cache = obj.cache = {}

    @functools.wraps(obj)
    def memoizer(*args, **kwargs):
        key = str(args) + str(kwargs)
        if key not in cache:
            cache[key] = obj(*args, **kwargs)
        return cache[key]
    return memoizer

class BasePushApiObject(object):
    def format_where(self, id_field, where=None):
        base_where = "%s = '%s'" % (id_field, self.sf_id)
        if where:
            where = '%s AND (%s)' % (base_where, where)
        else:
            where = base_where
        return where

# Push API Object Models

class MetadataPackage(BasePushApiObject):
    def __init__(self, push_api, name, sf_id=None, namespace=None):
        self.push_api = push_api
        self.sf_id = sf_id
        self.name = name
        self.namespace = namespace

    def get_package_versions(self, where=None, limit=None):
        where = self.format_where('MetadataPackageId', where)
        return self.push_api.get_package_versions(where, limit)

    def get_package_version_objs(self, where=None, limit=None):
        where = self.format_where('MetadataPackageId', where)
        return self.push_api.get_package_version_objs(where, limit)

    def get_package_versions_by_id(self, where=None, limit=None):
        where = self.format_where('MetadataPackageId', where)
        return self.push_api.get_package_versions_by_id(where, limit)

class MetadataPackageVersion(BasePushApiObject):
    def __init__(self, push_api, package, name, state, major, minor, patch, build, sf_id=None):
        self.push_api = push_api
        self.sf_id = sf_id
        self.package = package
        self.name = name
        self.state = state
        self.major = major
        self.minor = minor
        self.patch = patch
        self.build = build

    @property
    def version_number(self):
        parts = [str(self.major),str(self.minor)]
        if self.patch:
            parts.append(str(patch))
        version_number = '.'.join(parts)
        if self.state == 'Beta':
            version_number += ' (Beta %s)' % self.build
        return version_number

    def get_newer_released_version_objs(self, release_state=None):
        where = "MetadataPackageId = '%s' AND ReleaseState = 'Released' AND " % self.package.sf_id
        version_info = {'major': self.major, 'minor': self.minor, 'patch': self.patch}
        where += "(MajorVersion > %(major)s OR (MajorVersion = %(major)s AND MinorVersion > %(minor)s))" % version_info
        if self.patch:
            patch_where = " OR (MajorVersion = %(major)s AND MinorVersion = %(minor)s AND PatchVersion > %(patch))" % version_info
            where = where[:-1] + patch_where + where[-1:]
    
        versions = self.package.get_package_version_objs(where)
        return versions

    def get_older_released_version_objs(self, release_state=None):
        where = "MetadataPackageId = '%s' AND ReleaseState = 'Released' AND " % self.package.sf_id
        version_info = {'major': self.major, 'minor': self.minor, 'patch': self.patch}
        where += "(MajorVersion < %(major)s OR (MajorVersion = %(major)s AND MinorVersion < %(minor)s))" % version_info
        if self.patch:
            patch_where = " OR (MajorVersion = %(major)s AND MinorVersion = %(minor)s AND PatchVersion < %(patch))" % version_info
            where = where[:-1] + patch_where + where[-1:]
    
        versions = self.package.get_package_version_objs(where)
        return versions

    def get_subscribers(self, where=None, limit=None):
        where = self.format_where('MetadataPackageVersionId', where)
        return self.push_api.get_subscribers(where, limit)

    def get_subscriber_objs(self, where=None, limit=None):
        where = self.format_where('MetadataPackageVersionId', where)
        return self.push_api.get_subscriber_objs(where, limit)

    def get_subscribers_by_org_key(self, where=None, limit=None):
        where = self.format_where('MetadataPackageVersionId', where)
        return self.push_api.get_subscribers_by_org_key(where, limit)

    def get_push_requests(self, where=None, limit=None):
        where = self.format_where('PackageVersionId', where)
        return self.push_api.get_push_requests(where, limit)

    def get_push_request_objs(self, where=None, limit=None):
        where = self.format_where('PackageVersionId', where)
        return self.push_api.get_push_request_objs(where, limit)

    def get_push_requests_by_id(self, where=None, limit=None):
        where = self.format_where('PackageVersionId', where)
        return self.push_api.get_push_requests_by_id(where, limit)

class PackagePushJob(BasePushApiObject):
    def __init__(self, push_api, request, org, status, sf_id=None):
        self.push_api = push_api
        self.request = request
        self.org = org
        self.status = status
        self.sf_id = sf_id

    def get_push_errors(self, where=None, limit=None):
        where = self.format_where('PackagePushJobId', where)
        return self.push_api.get_push_errors(where, limit)

    def get_push_error_objs(self, where=None, limit=None):
        where = self.format_where('PackagePushJobId', where)
        return self.push_api.get_push_error_objs(where, limit)

    def get_push_errors_by_id(self, where=None, limit=None):
        where = self.format_where('PackagePushJobId', where)
        return self.push_api.get_push_errors_by_id(where, limit)

class PackagePushError(BasePushApiObject):
    def __init__(self, push_api, job, severity, error_type, title, message, details, sf_id=None):
        self.push_api = push_api
        self.sf_id = sf_id
        self.job = job
        self.severity = severity
        self.error_type = error_type
        self.title = title
        self.message = message
        self.details = details

class PackagePushRequest(BasePushApiObject):
    def __init__(self, push_api, version, start_time, status, sf_id=None):
        self.push_api = push_api
        self.sf_id = sf_id
        self.version = version
        self.start_time = start_time
        self.status = status

    def get_push_jobs(self, where=None, limit=None):
        where = self.format_where('PackagePushRequestId', where)
        return self.push_api.get_push_jobs(where, limit)

    def get_push_job_objs(self, where=None, limit=None):
        where = self.format_where('PackagePushRequestId', where)
        return self.push_api.get_push_job_objs(where, limit)
        
    def get_push_jobs_by_id(self, where=None, limit=None):
        where = self.format_where('PackagePushRequestId', where)
        return self.push_api.get_push_jobs_by_id(where, limit)

class PackageSubscriber(object):
    def __init__(self, push_api, version, status, org_name, org_key, org_status, org_type, sf_id=None):
        self.push_api = push_api
        self.sf_id = sf_id
        self.version = version
        self.status = status
        self.org_name = org_name
        self.org_key = org_key
        self.org_status = org_status
        self.org_type = org_type

    def format_where(self, id_field, where=None):
        base_where = "%s = '%s'" % (id_field, self.org_key)
        if where:
            where = '%s AND (%s)' % (base_where, where)
        else:
            where = base_where
        return where

    def get_push_jobs(self, where=None, limit=None):
        where = self.format_where('SubscriberOrganizationKey', where)
        return self.push_api.get_push_jobs(where, limit)

    def get_push_job_objs(self, where=None, limit=None):
        where = self.format_where('SubscriberOrganizationKey', where)
        return self.push_api.get_push_job_objs(where, limit)

    def get_push_jobs_by_id(self, where=None, limit=None):
        where = self.format_where('SubscriberOrganizationKey', where)
        return self.push_api.get_push_jobs_by_id(where, limit)
       
 
class SalesforcePushApi(object):
    """ API Wrapper for the Salesforce Push API """

    def __init__(self, username, password, serverurl, lazy=None, default_where=None):
        sandbox = False
        if serverurl.find('test.salesforce.com') != -1:
            sandbox = True
    
        self.sf = Salesforce(username=username, password=password, security_token='', sandbox=sandbox, sf_version='35.0')

        # Change base_url to use the tooling api
        self.sf.base_url = self.sf.base_url + 'tooling/'

        if not lazy:
            lazy = []
        self.lazy = lazy

        if not default_where:
            default_where = {}
        self.default_where = default_where

    def return_query_records(self, query):
        #print 'Running Query: %s' % query
        res = self.sf.query_all(query)
        if res['totalSize'] > 0:
            return res['records']
        else:
            return []

    def format_where_clause(self, where, obj=None):
        if obj and obj in self.default_where:
            default_where = self.default_where[obj]
            if where:
                where = '(%s) AND (%s)' % (default_where, where)
            else:
                where = '(%s)' % default_where
        if where:
            where = ' WHERE %s' % where
        else:
            where = ''
        return where

    def add_query_limit(self, query, limit):
        if not limit:
            return query

        return '%s LIMIT %s' % (query, limit)

    def get_tooling_object(self, object_name):
        # Set up a simple-salesforce sobject for TraceFlag using the tooling api
        obj = getattr(self.sf, object_name)
        obj.base_url = (u'https://{instance}/services/data/v{sf_version}/tooling/sobjects/{object_name}/'
                     .format(instance=self.sf.sf_instance,
                             object_name=object_name,
                             sf_version=self.sf.sf_version))
        return obj

    @memoize
    def get_packages(self, where=None, limit=None):
        where = self.format_where_clause(where)
        query = "SELECT id, name, namespaceprefix FROM MetadataPackage%s" % where
        query = self.add_query_limit(query, limit)
        return self.return_query_records(query)

    @memoize
    def get_package_objs(self, where=None, limit=None):
        package_objs = []
        for package in self.get_packages(where, limit):
            package_objs.append(
                MetadataPackage(
                    push_api = self,
                    sf_id=package['Id'], 
                    name=package['Name'], 
                    namespace=package['NamespacePrefix']
                )
            )
        return package_objs

    @memoize
    def get_packages_by_id(self, where=None, limit=None):
        packages = {}
        for package in self.get_package_objs(where, limit):
            packages[package.sf_id] = package
        return packages

    @memoize
    def get_package_versions(self, where=None, limit=None):
        where = self.format_where_clause(where)
        query = "SELECT Id, Name, MetadataPackageId, ReleaseState, MajorVersion, MinorVersion, PatchVersion, BuildNumber FROM MetadataPackageVersion%s ORDER BY MajorVersion DESC, MinorVersion DESC, PatchVersion, BuildNumber DESC" % where
        query = self.add_query_limit(query, limit)
        return self.return_query_records(query)

    @memoize
    def get_where_last_version(self, major=None, minor=None, beta=None):
        if beta:
            where = "ReleaseState = 'Beta'"
        else:
            where = "ReleaseState = 'Released'"
        if major:
            where += " AND MajorVersion=%s" % int(major)
        if minor:
            where += " AND MinorVersion=%s" % int(minor)
        return where
        
    @memoize
    def get_package_version_objs(self, where=None, limit=None):
        package_version_objs = []
        packages = self.get_packages_by_id()
        for package_version in self.get_package_versions(where, limit):
            package_version_objs.append(
                MetadataPackageVersion(
                    push_api = self,
                    name = package_version['Name'],
                    package = packages[package_version['MetadataPackageId']],
                    state = package_version['ReleaseState'],
                    major = package_version['MajorVersion'],
                    minor = package_version['MinorVersion'],
                    patch = package_version['PatchVersion'],
                    build = package_version['BuildNumber'],
                    sf_id = package_version['Id'],
                )
            )
        return package_version_objs

    @memoize
    def get_package_versions_by_id(self, where=None, limit=None):
        package_versions = {}
        for package_version in self.get_package_version_objs(where, limit):
            package_versions[package_version.sf_id] = package_version
        return package_versions

    @memoize
    def get_subscribers(self, where=None, limit=None):
        where = self.format_where_clause(where, obj='PackageSubscriber')
        query = "SELECT Id, MetadataPackageVersionId, InstalledStatus, OrgName, OrgKey, OrgStatus, OrgType from PackageSubscriber%s" % where
        query = self.add_query_limit(query, limit)
        return self.return_query_records(query)

    @memoize
    def get_subscriber_objs(self, where=None, limit=None):
        subscriber_objs = []
        package_versions = self.get_package_versions_by_id()
        for subscriber in self.get_subscribers(where, limit):
            subscriber_objs.append(
                PackageSubscriber(
                    push_api = self,
                    version = package_versions[subscriber['MetadataPackageVersionId']],
                    status = subscriber['InstalledStatus'],
                    org_name = subscriber['OrgName'],
                    org_key = subscriber['OrgKey'],
                    org_status = subscriber['OrgStatus'],
                    org_type = subscriber['OrgType'],
                    sf_id = subscriber['Id'],
                )
            )
        return subscriber_objs

    @memoize
    def get_subscribers_by_org_key(self, where=None, limit=None):
        subscribers = {}
        for subscriber in self.get_subscriber_objs(where, limit):
            subscribers[subscriber.org_key] = subscriber 
        return subscribers

    @memoize
    def get_push_requests(self, where=None, limit=None):
        where = self.format_where_clause(where, obj='PackagePushRequest')
        query = "SELECT Id, PackageVersionId, ScheduledStartTime, Status FROM PackagePushRequest%s ORDER BY ScheduledStartTime DESC" % where
        query = self.add_query_limit(query, limit)
        return self.return_query_records(query)

    @memoize
    def get_push_request_objs(self, where=None, limit=None):
        push_request_objs = []
        package_versions = self.get_package_versions_by_id()
        for push_request in self.get_push_requests(where, limit):
            push_request_objs.append(
                PackagePushRequest(
                    push_api = self,
                    version = package_versions[push_request['PackageVersionId']],
                    start_time=push_request['ScheduledStartTime'],
                    status = push_request['Status'],
                    sf_id = push_request['Id'],
                )
            )
        return push_request_objs

    @memoize
    def get_push_requests_by_id(self, where=None, limit=None):
        push_requests = {}
        for push_request in self.get_push_request_objs(where, limit):
            push_requests[push_request.sf_id] = push_request
        return push_requests

    @memoize
    def get_push_jobs(self, where=None, limit=None):
        where = self.format_where_clause(where)
        query = "SELECT Id, PackagePushRequestId, SubscriberOrganizationKey, Status FROM PackagePushJob%s" % where
        query = self.add_query_limit(query, limit)
        return self.return_query_records(query)

    @memoize
    def get_push_job_objs(self, where=None, limit=None):
        push_job_objs = []
        lazy = 'subscribers' in self.lazy
        if not lazy:
            subscriberorgs = self.get_subscribers_by_org_key()
        push_requests = self.get_push_requests_by_id()
        for push_job in self.get_push_jobs(where, limit):
            if lazy:
                orgs = self.get_subscriber_objs("OrgKey = '%s'" % push_job['SubscriberOrganizationKey'])
                if not orgs:
                    org = None
                else:
                    org = orgs[0]
            else:
                if push_job['SubscriberOrganizationKey'] not in subscriberorgs:
                    #print 'Skipping job for unmatched subscriber org %s' % push_job['SubscriberOrganizationKey']
                    continue
                else:
                    org = subscriberorgs[push_job['SubscriberOrganizationKey']]
            push_job_objs.append(
                PackagePushJob(
                    push_api = self,
                    request = push_requests[push_job['PackagePushRequestId']],
                    org = org,
                    status = push_job['Status'],
                    sf_id = push_job['Id'],
                )
            )
        return push_job_objs

    @memoize
    def get_push_jobs_by_id(self, where=None, limit=None):
        push_jobs = {}
        for push_job in self.get_push_job_objs(where, limit):
            push_jobs[push_job.sf_id] = push_job
        return push_jobs

    @memoize
    def get_push_errors(self, where=None, limit=None):
        where = self.format_where_clause(where)
        query = "SELECT Id, PackagePushJobId, ErrorSeverity, ErrorType, ErrorTitle, ErrorMessage, ErrorDetails FROM PackagePushError%s" % where
        query = self.add_query_limit(query, limit)
        return self.return_query_records(query)

    @memoize
    def get_push_error_objs(self, where=None, limit=None):
        push_error_objs = []
        lazy = 'jobs' in self.lazy
        if not lazy:
            push_jobs = self.get_push_jobs_by_id()
        for push_error in self.get_push_errors(where, limit):
            if lazy:
                jobs = self.get_push_job_objs(where="Id = '%s'" % push_error['PackagePushJobId'])
                if jobs:
                    job = jobs[0]
                else:
                    job = None
             
            push_error_objs.append(
                PackagePushError(
                    push_api = self,
                    job = job,
                    severity = push_error['ErrorSeverity'],
                    error_type = push_error['ErrorType'],
                    title = push_error['ErrorTitle'],
                    message = push_error['ErrorMessage'],
                    details = push_error['ErrorDetails'],
                    sf_id = push_error['Id'],
                )
            )
        return push_error_objs

    @memoize
    def get_push_errors_by_id(self, where=None, limit=None):
        push_errors = {}
        for push_error in self.get_push_error_objs(where, limit):
            push_errors[push_error.sf_id] = push_error
        return push_errors

    def create_push_request(self, version, orgs, start=None):
        if not start:
            # By default, delay the push start by 15 minutes to allow manual review and intervention
            start = datetime.datetime.now() + datetime.timedelta(0, 15*60)

        # Get the modified simple-salesforce Tooling API endpoint objects
        ToolingPackagePushRequest = self.get_tooling_object('PackagePushRequest')
        ToolingPackagePushJob = self.get_tooling_object('PackagePushJob')

        # Create the request
        res = ToolingPackagePushRequest.create({
            'PackageVersionId': version.sf_id,
            'ScheduledStartTime': start.isoformat(),
        })
        request_id = res['id']

        # Schedule the orgs
        for org in orgs:
            try:
                res = ToolingPackagePushJob.create({
                    'PackagePushRequestId': request_id,
                    'SubscriberOrganizationKey': org,
                })
            except SalesforceMalformedRequest, e:
                error = e.content[0]
                if error['errorCode'] == 'INVALID_OPERATION':
                    print 'Skipping org %s, error message = %s' % (org, error['message'])
                else:
                    raise e

        return request_id

    def run_push_request(self, request_id):
        # Set the request to Pending status
        ToolingPackagePushRequest = self.get_tooling_object('PackagePushRequest')
        return ToolingPackagePushRequest.update(request_id, {'Status': 'Pending'})

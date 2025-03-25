from tapiriik.database import db, cachedb
from tapiriik.services import Service, ServiceRecord, APIAuthorizationException, ServiceException, ServiceWarning
from datetime import datetime, timedelta
import sys
import os
import traceback
import pprint
import copy
import pytz

def _formatExc():
    print("Dumping exception")
    exc_type, exc_value, exc_traceback = sys.exc_info()
    tb = exc_traceback
    while tb.tb_next:
        tb = tb.tb_next
    frame = tb.tb_frame
    exc = '\n'.join(traceback.format_exception(exc_type, exc_value, exc_traceback)) + "\nLOCALS:\n" + '\n'.join([str(k) + "=" + pprint.pformat(v) for k, v in frame.f_locals.items()])
    print(exc)
    return exc


class Sync:

    SyncInterval = timedelta(hours=1)
    MinimumSyncInterval = timedelta(seconds=30)

    def ScheduleImmediateSync(user, exhaustive=None):
        if exhaustive is None:
            db.users.update({"_id": user["_id"]}, {"$set": {"NextSynchronization": datetime.utcnow()}})
        else:
            db.users.update({"_id": user["_id"]}, {"$set": {"NextSynchronization": datetime.utcnow(), "NextSyncIsExhaustive": exhaustive}})

    def SetNextSyncIsExhaustive(user, exhaustive=False):
        db.users.update({"_id": user["_id"]}, {"$set": {"NextSyncIsExhaustive": exhaustive}})

    def _determineRecipientServices(activity, allConnections):
        recipientServices = allConnections
        recipientServices = [conn for conn in recipientServices if activity.Type in conn.Service.SupportedActivities
                                                                and (not hasattr(conn, "SynchronizedActivities") or not len([x for x in activity.UIDs if x in conn.SynchronizedActivities]))
                                                                and conn not in [x["Connection"] for x in activity.UploadedTo]]
        return recipientServices

    def _fromSameService(activityA, activityB):
        otherSvcs = [y["Connection"]._id for y in activityB.UploadedTo]
        for uploadA in activityA.UploadedTo:
            if uploadA["Connection"]._id in otherSvcs:
                return True
        return False

    def _coalesceDatetime(a, b, knownTz=None):
        """ Returns the most informative (TZ-wise) datetime of those provided - defaulting to the first if they are equivalently descriptive """
        if not b:
            if knownTz and a and not a.tzinfo:
                return a.replace(tzinfo=knownTz)
            return a
        if not a:
            if knownTz and b and not b.tzinfo:
                return b.replace(tzinfo=knownTz)
            return b
        if a.tzinfo and not b.tzinfo:
            return a
        elif b.tzinfo and not a.tzinfo:
            return b
        else:
            if knownTz and not a.tzinfo:
                return a.replace(tzinfo=knownTz)
            return a

    def _accumulateActivities(svc, svcActivities, activityList):
        activityStartLeewaySeconds = 60 * 3
        from tapiriik.services.interchange import ActivityType
        for act in svcActivities:
            act.UIDs = [act.UID]
            if act.TZ and not hasattr(act.TZ, "localize"):
                raise ValueError("Got activity with TZ type " + str(type(act.TZ)) + " instead of a pytz timezone")
            # Used to ensureTZ() right here - doubt it's needed any more?
            existElsewhere = [x for x in activityList if x.UID == act.UID
                              or  # check to see if the activities are reasonably close together to be considered duplicate
                              (x.StartTime is not None and
                               act.StartTime is not None and
                               (act.StartTime.tzinfo is not None) == (x.StartTime.tzinfo is not None) and
                               abs((act.StartTime-x.StartTime).total_seconds()) < activityStartLeewaySeconds
                              )
                              or  # try comparing the time as if it were TZ-aware and in the expected TZ (this won't actually change the value of the times being compared)
                              (x.StartTime is not None and
                               act.StartTime is not None and
                               (act.StartTime.tzinfo is not None) != (x.StartTime.tzinfo is not None) and
                               abs((act.StartTime.replace(tzinfo=None)-x.StartTime.replace(tzinfo=None)).total_seconds()) < activityStartLeewaySeconds
                              )
                              ]
            if len(existElsewhere) > 0:
                # we don't merge the exclude values here, since at this stage the services have the option of just not returning those activities
                if act.TZ is not None and existElsewhere[0].TZ is None:
                    existElsewhere[0].TZ = act.TZ
                    existElsewhere[0].DefineTZ()
                # tortuous merging logic is tortuous
                existElsewhere[0].StartTime = Sync._coalesceDatetime(existElsewhere[0].StartTime, act.StartTime)
                existElsewhere[0].EndTime = Sync._coalesceDatetime(existElsewhere[0].EndTime, act.EndTime, knownTz=existElsewhere[0].StartTime.tzinfo)
                existElsewhere[0].Name = existElsewhere[0].Name if existElsewhere[0].Name is not None else act.Name
                existElsewhere[0].Waypoints = existElsewhere[0].Waypoints if len(existElsewhere[0].Waypoints) > 0 else act.Waypoints
                existElsewhere[0].Type = existElsewhere[0].Type if existElsewhere[0].Type != ActivityType.Other else act.Type

                existElsewhere[0].UploadedTo += act.UploadedTo
                existElsewhere[0].UIDs += act.UIDs  # I think this is merited
                act.UIDs = existElsewhere[0].UIDs  # stop the circular inclusion, not that it matters
                continue
            activityList.append(act)

    def _determineEligibleRecipientServices(activity, recipientServices, excludedServices, user, silent=False):
        from tapiriik.auth import User
        eligibleServices = []
        for destinationSvcRecord in recipientServices:
            if destinationSvcRecord in excludedServices:
                if not silent:  # Should really use legit logging instead of print()
                    print("\t\tExcluded " + destinationSvcRecord.Service.ID)
                continue  # we don't know for sure if it needs to be uploaded, hold off for now
            flowException = False
            if hasattr(activity, "Origin"):
                # we know the activity origin - do a more intuitive flow exception check
                if User.CheckFlowException(user, activity.Origin, destinationSvcRecord):
                    flowException = True
            else:
                for src in [x["Connection"] for x in activity.UploadedTo]:
                    if User.CheckFlowException(user, src, destinationSvcRecord):
                        flowException = True
                        break
                #  this isn't an absolute failure - it's possible we could still take an indirect route
                #  at this point there's no knowledge of the origin of this activity, so this behaviour would happen anyways at the next sync
                if flowException:
                    for secondLevelSrc in [x for x in recipientServices if x != destinationSvcRecord]:
                        if not User.CheckFlowException(user, secondLevelSrc, destinationSvcRecord):
                            flowException = False
                            break
            if flowException:
                if not silent:
                    print("\t\tFlow exception for " + destinationSvcRecord.Service.ID)
                continue
            destSvc = destinationSvcRecord.Service
            if destSvc.RequiresConfiguration(destinationSvcRecord) and not Service.HasConfiguration(destinationSvcRecord):
                if not silent:
                    print("\t\t" + destSvc.ID + " not configured")
                continue  # not configured, so we won't even try
            eligibleServices.append(destinationSvcRecord)
        return eligibleServices

    def PerformGlobalSync():
        from tapiriik.auth import User
        users = db.users.find({"NextSynchronization": {"$lte": datetime.utcnow()}, "SynchronizationWorker": None})  # mongoDB doesn't let you query by size of array to filter 1- and 0-length conn lists :\
        for user in users:
            syncStart = datetime.utcnow()
            try:
                Sync.PerformUserSync(user, "NextSyncIsExhaustive" in user and user["NextSyncIsExhaustive"] is True)
            except SynchronizationConcurrencyException:
                pass  # another worker picked them
            else:
                nextSync = None
                if User.HasActivePayment(user):
                    nextSync = datetime.utcnow() + Sync.SyncInterval
                db.users.update({"_id": user["_id"]}, {"$set": {"NextSynchronization": nextSync, "LastSynchronization": datetime.utcnow()}, "$unset": {"NextSyncIsExhaustive": None}})
                syncTime = (datetime.utcnow() - syncStart).total_seconds()
                db.sync_worker_stats.insert({"Timestamp": datetime.utcnow(), "Worker": os.getpid(), "TimeTaken": syncTime})

    def PerformUserSync(user, exhaustive=False):
        connectedServiceIds = [x["ID"] for x in user["ConnectedServices"]]

        if len(connectedServiceIds) <= 1:
            return  # nothing's going anywhere anyways

        # mark this user as in-progress
        db.users.update({"_id": user["_id"], "SynchronizationWorker": None}, {"$set": {"SynchronizationWorker": os.getpid(), "SynchronizationProgress": 0}})
        lockCheck = db.users.find_one({"_id": user["_id"], "SynchronizationWorker": os.getpid()})
        if lockCheck is None:
            raise SynchronizationConcurrencyException  # failed to get lock

        print ("Beginning sync for " + str(user["_id"]) + " at " + datetime.now().ctime())

        serviceConnections = [ServiceRecord(x) for x in db.connections.find({"_id": {"$in": connectedServiceIds}})]
        allExtendedAuthDetails = list(cachedb.extendedAuthDetails.find({"ID": {"$in": connectedServiceIds}}))
        activities = []

        excludedServices = []

        tempSyncErrors = {}

        for conn in serviceConnections:
            tempSyncErrors[conn._id] = []
            conn.SyncErrors = []
            svc = conn.Service

            if svc.RequiresExtendedAuthorizationDetails:
                if not hasattr(conn, "ExtendedAuthorization") or not conn.ExtendedAuthorization:
                    extAuthDetails = [x["ExtendedAuthorization"] for x in allExtendedAuthDetails if x["ID"] == conn._id]
                    if not len(extAuthDetails):
                        print("No extended auth details for " + svc.ID)
                        excludedServices.append(conn)
                        continue
                    # the connection never gets saved in full again, so we can sub these in here at no risk
                    conn.ExtendedAuthorization = extAuthDetails[0]

            try:
                print ("\tRetrieving list from " + svc.ID)
                svcActivities = svc.DownloadActivityList(conn, exhaustive)
            except (APIAuthorizationException, ServiceException, ServiceWarning) as e:
                etype = SyncError.NotAuthorized if issubclass(e.__class__, APIAuthorizationException) else SyncError.System
                tempSyncErrors[conn._id].append({"Step": SyncStep.List, "Type": etype, "Message": e.Message + "\n" + _formatExc(), "Code": e.Code})
                excludedServices.append(conn)
                if not issubclass(e.__class__, ServiceWarning):
                    continue
            except Exception as e:
                tempSyncErrors[conn._id].append({"Step": SyncStep.List, "Type": SyncError.System, "Message": _formatExc()})
                excludedServices.append(conn)
                continue
            Sync._accumulateActivities(svc, svcActivities, activities)

        origins = db.activity_origins.find({"ActivityUID": {"$in": [x.UID for x in activities]}})

        for activity in activities:
            if len(activity.UploadedTo) == 1:
                if not len(excludedServices):  # otherwise it could be incorrectly recorded
                    # we can log the origin of this activity
                    if not len([x for x in origins if x["ActivityUID"] == activity.UID]):  # No need to hammer the database updating these when they haven't changed
                        db.activity_origins.update({"ActivityID": activity.UID}, {"ActivityUID": activity.UID, "Origin": {"Service": activity.UploadedTo[0]["Connection"].Service.ID, "ExternalID": activity.UploadedTo[0]["Connection"].ExternalID}}, upsert=True)
                    activity.Origin = activity.UploadedTo[0]["Connection"]
            else:
                knownOrigin = [x for x in origins if x["ActivityUID"] == activity.UID]
                if len(knownOrigin) > 0:
                    connectedOrigins = [x for x in serviceConnections if knownOrigin[0]["Origin"]["Service"] == x.Service.ID and knownOrigin[0]["Origin"]["ExternalID"] == x.ExternalID]
                    if len(connectedOrigins) > 0:  # they might have disconnected it
                        activity.Origin = connectedOrigins[0]
                    else:
                        activity.Origin = knownOrigin[0]["Origin"]  # I have it on good authority that this will work
            print ("\t" + str(activity) + " " + str(activity.UID[:3]) + " from " + str([x["Connection"].Service.ID for x in activity.UploadedTo]))

        totalActivities = len(activities)
        processedActivities = 0
        for activity in activities:
            # we won't need this now, but maybe later
            db.connections.update({"_id": {"$in": [x["Connection"]._id for x in activity.UploadedTo]}},
                                  {"$addToSet": {"SynchronizedActivities": activity.UID}},
                                  multi=True)

            recipientServices = Sync._determineRecipientServices(activity, serviceConnections)
            if len(recipientServices) == 0:
                totalActivities -= 1  # doesn't count
                continue

            # this is after the above exit point since it's the most frequent case - want to avoid DB churn
            if totalActivities <= 0:
                syncProgress = 1
            else:
                syncProgress = max(0, min(1, processedActivities / totalActivities))

            db.users.update({"_id": user["_id"]}, {"$set": {"SynchronizationProgress": syncProgress}})

            # download the full activity record
            print("\tActivity " + str(activity.UID) + " to " + str([x.Service.ID for x in recipientServices]))

            eligibleServices = Sync._determineEligibleRecipientServices(activity=activity, recipientServices=recipientServices, excludedServices=excludedServices, user=user)

            if not len(eligibleServices):
                print("\t No eligible destinations")
                totalActivities -= 1  # Again, doesn't really count.
                continue

            for dlSvcUploadRec in activity.UploadedTo:
                dlSvcRecord = dlSvcUploadRec["Connection"]  # I guess in the future we could smartly choose which for >1, or at least roll over on error
                dlSvc = dlSvcRecord.Service
                print("\t from " + dlSvc.ID)
                act = None
                workingCopy = copy.copy(activity)  # we can hope
                try:
                    workingCopy = dlSvc.DownloadActivity(dlSvcRecord, workingCopy)
                except (APIAuthorizationException, ServiceException, ServiceWarning) as e:
                    etype = SyncError.NotAuthorized if issubclass(e.__class__, APIAuthorizationException) else SyncError.System
                    tempSyncErrors[conn._id].append({"Step": SyncStep.Download, "Type": etype, "Message": e.Message + "\n" + _formatExc(), "Code": e.Code})
                    if not issubclass(e.__class__, ServiceWarning):
                        continue
                except Exception as e:
                    tempSyncErrors[dlSvcRecord._id].append({"Step": SyncStep.Download, "Type": SyncError.System, "Message": _formatExc()})
                    continue
                if workingCopy.Exclude:
                    continue  # try again
                try:
                    workingCopy.CheckSanity()
                except:
                    tempSyncErrors[dlSvcRecord._id].append({"Step": SyncStep.Download, "Type": SyncError.System, "Message": _formatExc()})
                    continue
                else:
                    act = workingCopy
                    break  # succesfully got the activity + passed sanity checks, can stop now

            if act is None:  # couldn't download it from anywhere, or the places that had it said it was broken
                processedActivities += 1  # we tried
                continue

            for destinationSvcRecord in eligibleServices:
                destSvc = destinationSvcRecord.Service
                try:
                    print("\t\tUploading to " + destSvc.ID)
                    destSvc.UploadActivity(destinationSvcRecord, act)
                except (APIAuthorizationException, ServiceException, ServiceWarning) as e:
                    etype = SyncError.NotAuthorized if issubclass(e.__class__, APIAuthorizationException) else SyncError.System
                    tempSyncErrors[conn._id].append({"Step": SyncStep.Upload, "Type": etype, "Message": e.Message + "\n" + _formatExc(), "Code": e.Code})
                    if not issubclass(e.__class__, ServiceWarning):
                        continue
                except Exception as e:
                    tempSyncErrors[destinationSvcRecord._id].append({"Step": SyncStep.Upload, "Type": SyncError.System, "Message": _formatExc()})
                    continue
                # flag as successful
                db.connections.update({"_id": destinationSvcRecord._id},
                                      {"$addToSet": {"SynchronizedActivities": activity.UID}})

                db.sync_stats.update({"ActivityID": activity.UID}, {"$inc": {"Destinations": 1}, "$set": {"Distance": activity.Distance, "Timestamp": datetime.utcnow()}}, upsert=True)
            act.Waypoints = activity.Waypoints = []  # Free some memory

            processedActivities += 1

        allSyncErrors = []
        for conn in serviceConnections:
            db.connections.update({"_id": conn._id}, {"$set": {"SyncErrors": tempSyncErrors[conn._id]}})
            allSyncErrors += tempSyncErrors[conn._id]

        # clear non-persisted extended auth details
        cachedb.extendedAuthDetails.remove({"ID": {"$in": connectedServiceIds}})
        # unlock the row
        db.users.update({"_id": user["_id"], "SynchronizationWorker": os.getpid()}, {"$unset": {"SynchronizationWorker": None, "SynchronizationProgress": None}, "$set": {"SyncErrorCount": len(allSyncErrors)}})
        print("Finished sync for " + str(user["_id"]) + " at " + datetime.now().ctime())


class SynchronizationConcurrencyException(Exception):
    pass


class SyncStep:
    List = "list"
    Download = "download"
    Upload = "upload"


class SyncError:
    System = "system"
    Unknown = "unkown"
    NotAuthorized = "authorization"

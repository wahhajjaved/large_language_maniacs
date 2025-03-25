from __future__ import absolute_import
import time
import json
import datetime
from django.db import transaction
from django.contrib.gis.geos import Point
from celery import shared_task
from onadata.apps.fieldsight.models import Organization, Project, Site, Region, SiteType
from onadata.apps.userrole.models import UserRole
from onadata.apps.eventlog.models import FieldSightLog, CeleryTaskProgress
from django.contrib import messages
from channels import Group as ChannelGroup
from django.contrib.auth.models import Group
from celery import task, current_task


@shared_task()
def printr():
    for i in range(10):
        a=str(i) + 'rand'
        time.sleep(5)
        print a
    return ' random users created with success!'

@task()
def bulkuploadsites(source_user, file, pk):
    time.sleep(5)
    project = Project.objects.get(pk=pk)
    task_id = bulkuploadsites.request.id
    task = CeleryTaskProgress.objects.get(task_id=task_id)
    task.content_object = project
    task.status=1
    task.save()
    try:
        sites = file.get_records()
        count = len(sites)
        task.description = "Bulk Upload of "+str(count)+" Sites."
        task.save()
        
        with transaction.atomic():
            i=0
            interval = count/20
            for site in sites:
                # time.sleep(0.7)
                site = dict((k, v) for k, v in site.iteritems() if v is not '')
                lat = site.get("longitude", 85.3240)
                long = site.get("latitude", 27.7172)
                location = Point(lat, long, srid=4326)
            
                region_idf = site.get("region_id", None)
                region_id = None
            
                if region_idf is not None:
                    region, created  = Region.objects.get_or_create(identifier=str(region_idf), project = project)
                    region_id = region.id
            
                type_identifier = int(site.get("type", "0"))
            
                if type_identifier == 0:
                    _site, created = Site.objects.get_or_create(identifier=str(site.get("id")),
                                                                name=site.get("name"),
                                                                project=project,
                                                                region_id = region_id)
                else:

                    site_type = SiteType.objects.get(identifier=type_identifier, project=project)

                    _site, created = Site.objects.get_or_create(identifier=str(site.get("id")),
                                                                name=site.get("name"),
                                                                project=project,
                                                                type=site_type, region_id = region_id)
                _site.phone = site.get("phone")
                _site.address = site.get("address")
                _site.public_desc = site.get("public_desc")
                _site.additional_desc = site.get("additional_desc")
                _site.location = location
                _site.logo = "logo/default_site_image.png"

                meta_ques = project.site_meta_attributes

                myanswers = {}
                for question in meta_ques:
                    myanswers[question['question_name']]=site.get(question['question_name'], "")
                    print site.get(question['question_name'])
                
                _site.site_meta_attributes_ans = myanswers
                _site.save()
                i += 1
                
                if i > interval:
                    interval = i+interval
                    bulkuploadsites.update_state(state='PROGRESS',meta={'current': i, 'total': count})
            task.status = 2
            task.save()
            noti = project.logs.create(source=source_user, type=12, title="Bulk Sites",
                                       organization=project.organization,
                                       project=project, content_object=project,
                                       extra_message=str(count) + " Sites")
            result={}
            result['id']= noti.id,
            result['source_uid']= source_user.id,
            result['source_name']= source_user.username,
            result['source_img']= source_user.user_profile.profile_picture.url,
            result['get_source_url']= noti.get_source_url(),
            result['get_event_name']= project.name,
            result['get_event_url']= noti.get_event_url(),
            result['get_extraobj_name']= None,
            result['get_extraobj_url']= None,
            result['get_absolute_url']= noti.get_absolute_url(),
            result['type']= 12,
            result['date']= str(noti.date),
            result['extra_message']= str(count)+" Sites",
            result['seen_by']= [],
            ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})
            # ChannelGroup("project-{}".format(project.id)).send({"text": json.dumps(result)})

    except Exception as e:
        task.status = 3
        task.save()
        print 'Site Upload Unsuccesfull. %s' % e
        print e.__dict__
        noti = project.logs.create(source=source_user, type=412, title="Bulk Sites",
                                       content_object=project, recipient=source_user,
                                       extra_message=str(count) + " Sites @error " + u'{}'.format(e.message))
        result={}
        result['id']= noti.id,
        result['source_uid']= source_user.id,
        result['source_name']= source_user.username,
        result['source_img']= source_user.user_profile.profile_picture.url,
        result['get_source_url']= noti.get_source_url(),
        result['get_event_name']= project.name,
        result['get_event_url']= noti.get_event_url(),
        result['get_extraobj_name']= None,
        result['get_extraobj_url']= None,
        result['get_absolute_url']= noti.get_absolute_url(),
        result['type']= 412,
        result['date']= str(noti.date),
        result['extra_message']= str(count) + " Sites @error " + u'{}'.format(e.message),
        result['seen_by']= [],
        ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})
        return None

@shared_task()
def multiuserassignproject(source_user, org_id, projects, users, group_id):
    org = Organization.objects.get(pk=org_id)
    projects_count = len(projects)
    users_count = len(users)
    
    task_id = multiuserassignproject.request.id
    task = CeleryTaskProgress.objects.get(task_id=task_id)
    task.content_object = org
    task.description = "Assign "+str(users_count)+" people in "+str(projects_count)+" projects."
    task.status=1
    task.save()
    try:
        with transaction.atomic():
            roles_created = 0
            for project_id in projects:
                    project = Project.objects.get(pk=project_id)
                    for user in users:
                        role, created = UserRole.objects.get_or_create(user_id=user, project_id=project_id,
                                                                       organization_id=org.id,
                                                                       group_id=group_id, ended_at=None)
                        if created:
                            roles_created += 1
                            # description = "{0} was assigned  as Project Manager in {1}".format(
                                # role.user.get_full_name(), role.project)
                            # noti = role.logs.create(source=role.user, type=6, title=description, description=description,
                            #  content_object=role.project, extra_object=self.request.user)
                            # result = {}
                            # result['description'] = description
                            # result['url'] = noti.get_absolute_url()
                            # ChannelGroup("notify-{}".format(role.organization.id)).send({"text": json.dumps(result)})
                            # ChannelGroup("project-{}".format(role.project.id)).send({"text": json.dumps(result)})
                            # ChannelGroup("notify-0").send({"text": json.dumps(result)})
        task.status = 2
        task.save()
        if roles_created == 0:
            noti = FieldSightLog.objects.create(source=source_user, type=23, title="Task Completed.",
                                       content_object=org, recipient=source_user,
                                       extra_message=str(roles_created) + " new Project Manager Roles in " + str(projects_count) + " projects ")
            result={}
            result['id']= noti.id,
            result['source_uid']= source_user.id,
            result['source_name']= source_user.username,
            result['source_img']= source_user.user_profile.profile_picture.url,
            result['get_source_url']= noti.get_source_url(),
            result['get_event_name']= noti.get_event_name(),
            result['get_event_url']= noti.get_event_url(),
            result['get_extraobj_name']= None,
            result['get_extraobj_url']= None,
            result['get_absolute_url']= noti.get_absolute_url(),
            result['type']= 23,
            result['date']= str(noti.date),
            result['extra_message']= "All " + str(users_count) + " people were already assigned as Project Managers in " + str(projects_count) + " selected projects ",
            result['seen_by']= [],
            ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})

        else:
            noti = FieldSightLog.objects.create(source=source_user, type=21, title="Bulk Project User Assign",
                                           content_object=org, organization=org, 
                                           extra_message=str(roles_created) + " new Project Manager Roles in " + str(projects_count) + " projects ")
            result={}
            result['id']= noti.id,
            result['source_uid']= source_user.id,
            result['source_name']= source_user.username,
            result['source_img']= source_user.user_profile.profile_picture.url,
            result['get_source_url']= noti.get_source_url(),
            result['get_event_name']= noti.get_event_name(),
            result['get_event_url']= noti.get_event_url(),
            result['get_extraobj_name']= None,
            result['get_extraobj_url']= None,
            result['get_absolute_url']= noti.get_absolute_url(),
            result['type']= 21,
            result['date']= str(noti.date),
            result['extra_message']= str(roles_created) + " new Project Manager Roles in " + str(projects_count) + " projects ",
            result['seen_by']= [],
            ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})

    except Exception as e:
        task.status = 3
        task.save()
        noti = FieldSightLog.objects.create(source=source_user, type=421, title="Bulk Project User Assign",
                                       content_object=org, recipient=source_user,
                                       extra_message=str(users_count)+" people in "+str(projects_count)+" projects ")
        result={}
        result['id']= noti.id,
        result['source_uid']= source_user.id,
        result['source_name']= source_user.username,
        result['source_img']= source_user.user_profile.profile_picture.url,
        result['get_source_url']= noti.get_source_url(),
        result['get_event_name']= noti.get_event_name(),
        result['get_event_url']= noti.get_event_url(),
        result['get_extraobj_name']= None,
        result['get_extraobj_url']= None,
        result['get_absolute_url']= noti.get_absolute_url(),
        result['type']= 421,
        result['date']= str(noti.date),
        result['extra_message']= str(users_count)+" people in "+str(projects_count)+" projects ",
        result['seen_by']= [],
        ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})
        return None

@shared_task()
def multiuserassignsite(source_user, project_id, sites, users, group_id):
    project = Project.objects.get(pk=project_id)
    group_name = Group.objects.get(pk=group_id).name
    sites_count = len(sites)
    users_count = len(users)

    task_id = multiuserassignsite.request.id
    task = CeleryTaskProgress.objects.get(task_id=task_id)
    task.content_object = project
    task.description = "Assign "+str(users_count)+" people in "+str(sites_count)+" sites."
    task.status=1
    task.save()
    try:
        with transaction.atomic():
            roles_created = 0            
            for site_id in sites:
                site = Site.objects.get(pk=site_id)
                for user in users:
                  
                    role, created = UserRole.objects.get_or_create(user_id=user, site_id=site.id,
                                                                   project__id=project.id, organization__id=site.project.organization_id, group_id=group_id, ended_at=None)
                    if created:
                        roles_created += 1
                   
                        # description = "{0} was assigned  as {1} in {2}".format(
                        #     role.user.get_full_name(), role.lgroup.name, role.project)
                        # noti_type = 8

                        # if data.get('group') == "Reviewer":
                        #     noti_type =7
                        
                        # noti = role.logs.create(source=role.user, type=noti_type, title=description,
                        #                         description=description, content_type=site, extra_object=self.request.user,
                        #                         site=role.site)
                        # result = {}
                        # result['description'] = description
                        # result['url'] = noti.get_absolute_url()
                        # ChannelGroup("notify-{}".format(role.organization.id)).send({"text": json.dumps(result)})
                        # ChannelGroup("project-{}".format(role.project.id)).send({"text": json.dumps(result)})
                        # ChannelGroup("site-{}".format(role.site.id)).send({"text": json.dumps(result)})
                        # ChannelGroup("notify-0").send({"text": json.dumps(result)})

                        # Device = get_device_model()
                        # if Device.objects.filter(name=role.user.email).exists():
                        #     message = {'notify_type':'Assign Site', 'site':{'name': site.name, 'id': site.id}}
                        #     Device.objects.filter(name=role.user.email).send_message(message)
        task.status = 2
        task.save()
        if roles_created == 0:
            noti = FieldSightLog.objects.create(source=source_user, type=23, title="Task Completed.",
                                       content_object=project, recipient=source_user, 
                                       extra_message="All "+str(users_count) +" users were already assigned as "+ group_name +" in " + str(sites_count) + " selected sites ")
            result={}
            result['id']= noti.id,
            result['source_uid']= source_user.id,
            result['source_name']= source_user.username,
            result['source_img']= source_user.user_profile.profile_picture.url,
            result['get_source_url']= noti.get_source_url(),
            result['get_event_name']= noti.get_event_name(),
            result['get_event_url']= noti.get_event_url(),
            result['get_extraobj_name']= None,
            result['get_extraobj_url']= None,
            result['get_absolute_url']= noti.get_absolute_url(),
            result['type']= 23,
            result['date']= str(noti.date),
            result['extra_message']= "All "+str(users_count) +" users were already assigned as "+ group_name +" in " + str(sites_count) + " selected sites ",
            result['seen_by']= [],
            ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})

        else:

            noti = FieldSightLog.objects.create(source=source_user, type=22, title="Bulk site User Assign",
                                           content_object=project, organization=project.organization, project=project, 
                                           extra_message=str(roles_created) + " new "+ group_name +" Roles in " + str(sites_count) + " sites ")
            result={}
            result['id']= noti.id,
            result['source_uid']= source_user.id,
            result['source_name']= source_user.username,
            result['source_img']= source_user.user_profile.profile_picture.url,
            result['get_source_url']= noti.get_source_url(),
            result['get_event_name']= noti.get_event_name(),
            result['get_event_url']= noti.get_event_url(),
            result['get_extraobj_name']= None,
            result['get_extraobj_url']= None,
            result['get_absolute_url']= noti.get_absolute_url(),
            result['type']= 22,
            result['date']= str(noti.date),
            result['extra_message']= str(roles_created) + " new "+ group_name +" Roles in " + str(sites_count) + " sites ",
            result['seen_by']= [],
            ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})

    except Exception as e:
        task.status = 3
        task.save()
        noti = FieldSightLog.objects.create(source=source_user, type=422, title="Bulk Sites User Assign",
                                       content_object=project, recipient=source_user,
                                       extra_message=group_name +" for "+str(users_count)+" people in "+str(sites_count)+" sites ")
        result={}
        result['id']= noti.id,
        result['source_uid']= source_user.id,
        result['source_name']= source_user.username,
        result['source_img']= source_user.user_profile.profile_picture.url,
        result['get_source_url']= noti.get_source_url(),
        result['get_event_name']= noti.get_event_name(),
        result['get_event_url']= noti.get_event_url(),
        result['get_extraobj_name']= None,
        result['get_extraobj_url']= None,
        result['get_absolute_url']= noti.get_absolute_url(),
        result['type']= 422,
        result['date']= str(noti.date),
        result['extra_message']= group_name +" role for "+str(users_count)+" people in "+str(sites_count)+" sites ",
        result['seen_by']= [],
        ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})
        return None

@shared_task()
def multiuserassignregion(source_user, project_id, regions, users, group_id):
    project = Project.objects.get(pk=project_id)
    group_name = Group.objects.get(pk=group_id).name
    sites_count = len(regions)
    users_count = len(users)

    task_id = multiuserassignregion.request.id
    print task_id
    task = CeleryTaskProgress.objects.get(task_id=task_id)
    print task
    task.content_object = project
    task.description = "Assign "+str(users_count)+" people in "+str(sites_count)+" regions."
    task.status=1
    task.save()
    try:
        with transaction.atomic():
            roles_created = 0            
            for region_id in regions:
                if region_id == "0":
                    sites = Site.objects.filter(region__isnull=True, project_id=project_id).values('id')
                else: 
                    sites = Site.objects.filter(region_id = region_id, project_id=project_id).values('id')
                for site_id in sites:
                    print "Assigning to site : " + str(site_id)
                    for user in users:
                        site = Site.objects.filter(pk=site_id['id']).first()
                        if site and site.project_id == project.id: 
                            role, created = UserRole.objects.get_or_create(user_id=user, site_id=site_id['id'],
                                                                           project__id=project.id, organization__id=project.organization_id, group_id=group_id, ended_at=None)
                            if created:
                                roles_created += 1
                           
                                # description = "{0} was assigned  as {1} in {2}".format(
                                #     role.user.get_full_name(), role.lgroup.name, role.project)
                                # noti_type = 8

                                # if data.get('group') == "Reviewer":
                                #     noti_type =7
                                
                                # noti = role.logs.create(source=role.user, type=noti_type, title=description,
                                #                         description=description, content_type=site, extra_object=self.request.user,
                                #                         site=role.site)
                                # result = {}
                                # result['description'] = description
                                # result['url'] = noti.get_absolute_url()
                                # ChannelGroup("notify-{}".format(role.organization.id)).send({"text": json.dumps(result)})
                                # ChannelGroup("project-{}".format(role.project.id)).send({"text": json.dumps(result)})
                                # ChannelGroup("site-{}".format(role.site.id)).send({"text": json.dumps(result)})
                                # ChannelGroup("notify-0").send({"text": json.dumps(result)})

                                # Device = get_device_model()
                                # if Device.objects.filter(name=role.user.email).exists():
                                #     message = {'notify_type':'Assign Site', 'site':{'name': site.name, 'id': site.id}}
                                #     Device.objects.filter(name=role.user.email).send_message(message)
        task.status = 2
        task.save()
        if roles_created == 0:
            noti = FieldSightLog.objects.create(source=source_user, type=23, title="Task Completed.",
                                       content_object=project, recipient=source_user, 
                                       extra_message="All "+str(users_count) +" users were already assigned as "+ group_name +" in " + str(sites_count) + " selected regions ")
            result={}
            result['id']= noti.id,
            result['source_uid']= source_user.id,
            result['source_name']= source_user.username,
            result['source_img']= source_user.user_profile.profile_picture.url,
            result['get_source_url']= noti.get_source_url(),
            result['get_event_name']= noti.get_event_name(),
            result['get_event_url']= noti.get_event_url(),
            result['get_extraobj_name']= None,
            result['get_extraobj_url']= None,
            result['get_absolute_url']= noti.get_absolute_url(),
            result['type']= 23,
            result['date']= str(noti.date),
            result['extra_message']= "All "+str(users_count) +" users were already assigned as "+ group_name +" in " + str(sites_count) + " selected regions ",
            result['seen_by']= [],
            ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})

        else:

            noti = FieldSightLog.objects.create(source=source_user, type=22, title="Bulk site User Assign",
                                           content_object=project, organization=project.organization, project=project, 
                                           extra_message=str(roles_created) + " new "+ group_name +" Roles in " + str(sites_count) + " regions ")
            result={}
            result['id']= noti.id,
            result['source_uid']= source_user.id,
            result['source_name']= source_user.username,
            result['source_img']= source_user.user_profile.profile_picture.url,
            result['get_source_url']= noti.get_source_url(),
            result['get_event_name']= noti.get_event_name(),
            result['get_event_url']= noti.get_event_url(),
            result['get_extraobj_name']= None,
            result['get_extraobj_url']= None,
            result['get_absolute_url']= noti.get_absolute_url(),
            result['type']= 22,
            result['date']= str(noti.date),
            result['extra_message']= str(roles_created) + " new "+ group_name +" Roles in " + str(sites_count) + " regions ",
            result['seen_by']= [],
            ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})

    except Exception as e:
        print 'Bulk role assign Unsuccesfull. ------------------------------------------%s' % e
        task.description = "Assign "+str(users_count)+" people in "+str(sites_count)+" regions. ERROR: " + str(e) 
        task.status = 3
        task.save()
        noti = FieldSightLog.objects.create(source=source_user, type=422, title="Bulk Region User Assign",
                                       content_object=project, recipient=source_user,
                                       extra_message=group_name +" for "+str(users_count)+" people in "+str(sites_count)+" regions ")
        result={}
        result['id']= noti.id,
        result['source_uid']= source_user.id,
        result['source_name']= source_user.username,
        result['source_img']= source_user.user_profile.profile_picture.url,
        result['get_source_url']= noti.get_source_url(),
        result['get_event_name']= noti.get_event_name(),
        result['get_event_url']= noti.get_event_url(),
        result['get_extraobj_name']= None,
        result['get_extraobj_url']= None,
        result['get_absolute_url']= noti.get_absolute_url(),
        result['type']= 422,
        result['date']= str(noti.date),
        result['extra_message']= group_name +" role for "+str(users_count)+" people in "+str(sites_count)+" regions ",
        result['seen_by']= [],
        ChannelGroup("notif-user-{}".format(source_user.id)).send({"text": json.dumps(result)})
        return None
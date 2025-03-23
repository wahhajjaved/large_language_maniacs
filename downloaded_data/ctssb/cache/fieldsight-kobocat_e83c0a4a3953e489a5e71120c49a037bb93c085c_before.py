from __future__ import unicode_literals
import json

from django.db import transaction
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField

from onadata.apps.fsforms.models import Stage, FieldSightXF, EducationMaterial, EducationalImages
from onadata.apps.fsforms.serializers.FieldSightXFormSerializer import FSXFSerializer
from channels import Group as ChannelGroup
from onadata.apps.fsforms.serializers.InstanceStatusChangedSerializer import FInstanceResponcesSerializer


class EMImagesSerializer(serializers.ModelSerializer):
    class Meta:
        model = EducationalImages
        exclude = ("educational_material",)


class EMSerializer(serializers.ModelSerializer):
    em_images = EMImagesSerializer(many=True, read_only=True)
    class Meta:
        model = EducationMaterial
        exclude = ('stage','fsxf')

class SubStageSerializer1(serializers.ModelSerializer):
    stage_forms = FSXFSerializer()
    em = EMSerializer(read_only=True)
    responses_count = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()
    class Meta:
        model = Stage
        exclude = ('shared_level', 'site', 'group', 'ready', 'project','stage', 'date_modified', 'date_created',)

    def get_assigned_form(self, obj):
        if not FieldSightXF.objects.filter(stage=obj).exists():
            return None
        else:
            fsxf = FieldSightXF.objects.get(stage=obj)
            if fsxf.xf:
                return fsxf.id
        return None

    def get_assigned_form_name(self, obj):
        if not FieldSightXF.objects.filter(stage=obj).exists():
            return None
        else:
            fsxf = FieldSightXF.objects.get(stage=obj)
            if fsxf.xf:
                return fsxf.xf.title
        return None

    def get_assigned_form(self, obj):
        if not FieldSightXF.objects.filter(stage=obj).exists():
            return None
        else:
            fsxf = FieldSightXF.objects.get(stage=obj)
            if fsxf.xf:
                return fsxf.id
        return None

    def get_responses_count(self, obj):
        try:
            fsxf = FieldSightXF.objects.get(stage=obj)
            if fsxf.fsform is None:
                return fsxf.project_form_instances.count()
            else:
                print fsxf.project_form_instances.count()
                return fsxf.site_form_instances.count()

        except FieldSightXF.DoesNotExist:
            return 0


    def get_latest_submission(self, obj):
        try:
            fsxf = FieldSightXF.objects.get(stage=obj)
            
            if fsxf.fsform is None:
                response = fsxf.project_form_instances.order_by('-id')[:1]
            else:
                response = fsxf.site_form_instances.order_by('-id')[:1]
            serializer = FInstanceResponcesSerializer(instance=response, many=True)
            return serializer.data 

        except FieldSightXF.DoesNotExist:
            return 0

class StageSerializer1(serializers.ModelSerializer):
    # parent = SubStageSerializer1(many=True, read_only=True)
    parent = SerializerMethodField('get_substages')

    class Meta:
        model = Stage
        exclude = ('shared_level', 'group', 'ready', 'stage',)

    def get_substages(self, stage):
        stages = Stage.objects.filter(stage=stage, stage_forms__is_deleted=False)
        serializer = SubStageSerializer1(instance=stages, context={'request':self.context['request'], 'kwargs':self.context['kwargs']}, many=True)
        return serializer.data

    def create(self, validated_data):
        id = self.context['request'].data.get('id', False)
        api_request = self.context['request']
        with transaction.atomic():
            sub_stages_datas = self.context['request'].data.get('parent')
            if not id:
                stage = Stage.objects.create(**validated_data)
                for order, ss in enumerate(sub_stages_datas):
                    ss.pop('id')
                    stage_forms_dict = ss.pop('stage_forms')
                    xf_id = stage_forms_dict['xf']['id']
                    ss.update({'stage':stage, 'order':order+1})
                    default_submission_status = stage_forms_dict['default_submission_status']
                    sub_stage_obj = Stage.objects.create(**ss)
                    fxf = FieldSightXF(xf_id=xf_id, site=stage.site, project=stage.project, is_staged=True,
                                       stage=sub_stage_obj, default_submission_status=default_submission_status)
                    fxf.save()
                    if stage.project:
                        noti = fxf.logs.create(source=api_request.user, type=18, title="Stage",
                                               organization=fxf.project.organization,
                                               project = fxf.project,
                                               content_object = fxf,
                                               extra_object = fxf.project,
                                               description='{0} assigned new Stage form  {1} to {2} '.format(
                                                   api_request.user.get_full_name(),
                                                   fxf.xf.title,
                                                   fxf.project.name
                                               ))
                        result = {}
                        result['description'] = noti.description
                        result['url'] = noti.get_absolute_url()
                        # ChannelGroup("site-{}".format(fxf.site.id)).send({"text": json.dumps(result)})
                        ChannelGroup("project-{}".format(fxf.project.id)).send({"text": json.dumps(result)})
                    else:
                        fxf.from_project = False
                        fxf.save()
                        noti = fxf.logs.create(source=api_request.user, type=19, title="Stage",
                                               organization=fxf.site.project.organization,
                                               project=fxf.site.project,
                                               site=fxf.site,
                                               content_object=fxf,
                                               extra_object=fxf.site,
                                               description='{0} assigned new Stage form  {1} to {2} '.format(
                                                   api_request.user.get_full_name(),
                                                   fxf.xf.title,
                                                   fxf.site.name
                                               ))
                        result = {}
                        result['description'] = noti.description
                        result['url'] = noti.get_absolute_url()
                        ChannelGroup("site-{}".format(fxf.site.id)).send({"text": json.dumps(result)})
                        ChannelGroup("project-{}".format(fxf.site.project.id)).send({"text": json.dumps(result)})



            else:
                # Stage.objects.filter(pk=id).update(**validated_data)
                stage = Stage.objects.get(pk=id)
                for attr, value in validated_data.items():
                    setattr(stage, attr, value)
                stage.save()
                for order, sub_stage_data in enumerate(sub_stages_datas):
                    old_substage = sub_stage_data.get('id', False)
                    if old_substage:
                        sub_id = sub_stage_data.pop('id')
                        fxf = sub_stage_data.pop('stage_forms')
                        sub_stage_data.update({'stage':stage,'order':order+1})
                        sub_stage = Stage.objects.get(pk=sub_id)
                        for attr, value in sub_stage_data.items():
                            setattr(sub_stage, attr, value)
                        sub_stage.save()

                        old_fsxf = sub_stage.stage_forms
                        old_xf = old_fsxf.xf

                        xf = fxf.get('xf')
                        default_submission_status = fxf.get('default_submission_status')
                        xf_id = xf.get('id')

                        if old_xf.id  != xf_id:
                            # xform changed history and mew fsf
                            old_fsxf.is_deployed = False
                            old_fsxf.is_deleted = True
                            old_fsxf.stage=None
                            old_fsxf.save()
                            #create new fieldsight form
                            if stage.project:
                                FieldSightXF.objects.create(xf_id=xf_id, site=stage.site, project=stage.project,
                                                            is_staged=True, stage=sub_stage, default_submission_status=default_submission_status)
                            else:
                                FieldSightXF.objects.create(xf_id=xf_id, site=stage.site, project=stage.project,
                                                            is_staged=True, stage=sub_stage,from_project=False, default_submission_status=default_submission_status)

                            # org = stage.project.organization if stage.project else stage.site.project.organization
                            # desc = "deleted form of stage {} substage {} by {}".format(stage.name, sub_stage.name,
                            #                                                            self.context['request'].user.username)
                            # noti = old_fsxf.logs.create(source=self.context['request'].user, type=1, title="form Deleted",
                            #         organization=org, description=desc)
                            # result = {}
                            # result['description'] = desc
                            # result['url'] = noti.get_absolute_url()
                            # ChannelGroup("notify-{}".format(org.id)).send({"text": json.dumps(result)})
                            # ChannelGroup("notify-0").send({"text": json.dumps(result)})

                        #     notify mobile and web

                    #     if form change update fxf object's xf
                    else:
                        fxf = sub_stage_data.pop('stage_forms')
                        xf = fxf.get('xf')
                        default_submission_status = fxf.get('default_submission_status')
                        xf_id = xf.get('id')
                        # fxf_id = fxf.get('id')
                        sub_stage_data.pop('id')

                        sub_stage_data.update({'stage':stage, 'order':order+1})
                        sub_stage_obj = Stage.objects.create(**sub_stage_data)
                        if stage.project:
                            FieldSightXF.objects.create(xf_id=xf_id,site=stage.site, project=stage.project,
                                                        is_staged=True, stage=sub_stage_obj, default_submission_status=default_submission_status)
                        else:
                            FieldSightXF.objects.create(xf_id=xf_id, site=stage.site, project=stage.project,
                                                        is_staged=True, stage=sub_stage_obj,from_project=False, default_submission_status=default_submission_status)
            return stage


class StageSerializer(serializers.ModelSerializer):
    main_stage = serializers.ReadOnlyField(source='stage.name', read_only=True)

    class Meta:
        model = Stage
        fields = ('name', 'description', 'id', 'stage', 'main_stage', 'order', 'site', 'project_stage_id')


class SubStageSerializer(serializers.ModelSerializer):
    main_stage = serializers.ReadOnlyField(source='stage.name', read_only=True)
    form = serializers.SerializerMethodField('get_assigned_form', read_only=True)

    class Meta:
        model = Stage
        fields = ('name', 'description', 'id', 'stage', 'main_stage', 'order', 'site', 'form')

    def get_assigned_form(self, obj):
        if not FieldSightXF.objects.filter(stage=obj).exists():
            return None
        else:
            fsxf = FieldSightXF.objects.get(stage=obj)
            if fsxf.xf:
                return fsxf.id
        return None


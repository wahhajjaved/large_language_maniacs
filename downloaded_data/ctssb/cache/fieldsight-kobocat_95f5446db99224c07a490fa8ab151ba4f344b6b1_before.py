from __future__ import unicode_literals
import json
import xlwt
from io import BytesIO
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.models import Group, User, Permission
from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import Q
from django.forms import modelformset_factory
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.template.response import TemplateResponse
from django.views.generic import ListView, TemplateView, View
from django.core.urlresolvers import reverse_lazy, reverse
from django.contrib.auth.decorators import login_required
from django.core.serializers import serialize
from django.forms.forms import NON_FIELD_ERRORS
from django.http import HttpResponse
from django.core.exceptions import PermissionDenied

from fcm.utils import get_device_model

import django_excel as excel
from registration.backends.default.views import RegistrationView
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from channels import Group as ChannelGroup

from onadata.apps.eventlog.models import FieldSightLog, CeleryTaskProgress
from onadata.apps.fieldsight.bar_data_project import BarGenerator
from onadata.apps.fsforms.Submission import Submission
from onadata.apps.fsforms.line_data_project import LineChartGenerator, LineChartGeneratorOrganization, \
    LineChartGeneratorSite, ProgressGeneratorSite
from onadata.apps.fsforms.models import FieldSightXF, Stage, FInstance
from onadata.apps.userrole.models import UserRole
from onadata.apps.users.models import UserProfile
from .mixins import (LoginRequiredMixin, SuperAdminMixin, OrganizationMixin, ProjectMixin, SiteView,
                     CreateView, UpdateView, DeleteView, OrganizationView as OView, ProjectView as PView,
                     group_required, OrganizationViewFromProfile, ReviewerMixin, MyOwnOrganizationMixin,
                     MyOwnProjectMixin, ProjectMixin)
from .rolemixins import ReadonlyProjectLevelRoleMixin, ReadonlySiteLevelRoleMixin, DonorRoleMixin, DonorSiteViewRoleMixin, SiteDeleteRoleMixin, SiteSupervisorRoleMixin, ProjectRoleView, ReviewerRoleMixin, ProjectRoleMixin, OrganizationRoleMixin, ReviewerRoleMixinDeleteView, ProjectRoleMixinDeleteView
from .models import Organization, Project, Site, ExtraUserDetail, BluePrints, UserInvite, Region
from .forms import (OrganizationForm, ProjectForm, SiteForm, RegistrationForm, SetProjectManagerForm, SetSupervisorForm,
                    SetProjectRoleForm, AssignOrgAdmin, UploadFileForm, BluePrintForm, ProjectFormKo, RegionForm)
from django.views.generic import TemplateView
from django.core.mail import send_mail, EmailMessage
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string, get_template
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes, smart_str
from django.utils.crypto import get_random_string

from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode
from django.db.models import Prefetch
from django.core.files.storage import FileSystemStorage
import pyexcel as p
from onadata.apps.fieldsight.tasks import multiuserassignproject, bulkuploadsites, multiuserassignsite, multiuserassignregion
from .generatereport import MyPrint
from django.utils import translation
from django.conf import settings
from django.db.models import Prefetch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.core.serializers.json import DjangoJSONEncoder
from django.template import Context
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from onadata.apps.fsforms.reports_util import get_images_for_site, get_site_responses_coords

@login_required
def dashboard(request):
    current_role_count = request.roles.count()
    if current_role_count == 1:
        current_role = request.roles[0]
        role_type = request.roles[0].group.name
        if role_type == "Unassigned":
            raise PermissionDenied()
        if role_type == "Site Supervisor":
            return HttpResponseRedirect(reverse("fieldsight:roles-dashboard"))
        if role_type == "Reviewer":
            return HttpResponseRedirect(reverse("fieldsight:site-dashboard", kwargs={'pk': current_role.site.pk}))
        if role_type == "Project Donor":
            return HttpResponseRedirect(reverse("fieldsight:donor_project_dashboard", kwargs={'pk': current_role.project.pk}))
        if role_type == "Project Manager":
            return HttpResponseRedirect(reverse("fieldsight:project-dashboard", kwargs={'pk': current_role.project.pk}))
        if role_type == "Organization Admin":
            return HttpResponseRedirect(reverse("fieldsight:organizations-dashboard",
                                                kwargs={'pk': current_role.organization.pk}))
    if current_role_count > 1:
        return HttpResponseRedirect(reverse("fieldsight:roles-dashboard"))

    # total_users = User.objects.all().count()
    # total_organizations = Organization.objects.all().count()
    # total_projects = Project.objects.all().count()
    # total_sites = Site.objects.all().count()
    # data = serialize('custom_geojson', Site.objects.prefetch_related('site_instances').filter(is_survey=False, is_active=True), geometry_field='location', fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone','id'))

    #
    # # outstanding_query = FInstance.objects.filter(form_status=0)
    # # data = serialize('custom_geojson', Site.objects.filter(is_survey=False, is_active=True).prefetch_related(Prefetch('site_instances', queryset=outstanding_query, to_attr='outstanding')), geometry_field='location', fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone','id'))
    # # fs_forms = FieldSightXF.objects.all()
    # # fs_forms = list(fs_forms)
    # # # outstanding = flagged = approved = rejected = 0
    # # for form in fs_forms:
    # #     if form.form_status == 0:
    # #         outstanding += 1
    # #     elif form.form_status == 1:
    # #         flagged +=1
    # #     elif form.form_status == 2:
    # #         approved +=1
    # #     else:
    # #         rejected +=1
    #
    # dashboard_data = {
    #     'total_users': total_users,
    #     'total_organizations': total_organizations,
    #     'total_projects': total_projects,
    #     'total_sites': total_sites,
    #     # 'outstanding': outstanding,
    #     # 'flagged': flagged,
    #     # 'approved': approved,
    #     # 'rejected': rejected,
    #     'data': data,
    # }
    # return TemplateResponse(request, "fieldsight/fieldsight_dashboard.html", dashboard_data)
    
    return HttpResponseRedirect(reverse("fieldsight:organizations-list"))


def get_site_images(site_id):
    query = {'fs_site': str(site_id), '_deleted_at': {'$exists': False}}
    return settings.MONGO_DB.instances.find(query).sort([("_id", 1)]).limit(20)


def site_images(request, pk):
    cursor = get_site_images(pk)
    cursor = list(cursor)
    medias = []
    for index, doc in enumerate(cursor):
        for media in cursor[index].get('_attachments', []):
            if media:
                medias.append(media.get('download_url', ''))

    return JsonResponse({'images':medias[:5]})

class Organization_dashboard(LoginRequiredMixin, OrganizationRoleMixin, TemplateView):
    template_name = "fieldsight/organization_dashboard.html"
    def get_context_data(self, **kwargs):
        dashboard_data = super(Organization_dashboard, self).get_context_data(**kwargs)
        obj = Organization.objects.get(pk=self.kwargs.get('pk'))
        peoples_involved = obj.organization_roles.filter(ended_at__isnull=True).distinct('user_id')
        sites = Site.objects.filter(project__organization=obj,is_survey=False, is_active=True)
        data = serialize('custom_geojson', sites, geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))
        projects = Project.objects.filter(organization_id=obj.pk)
        total_projects = projects.count()
        total_sites = sites.count()
        outstanding, flagged, approved, rejected = obj.get_submissions_count()
        bar_graph = BarGenerator(sites)
        line_chart = LineChartGeneratorOrganization(obj)
        line_chart_data = line_chart.data()
        user = User.objects.filter(pk=self.kwargs.get('pk'))
        roles_org = UserRole.objects.filter(organization_id = self.kwargs.get('pk'), project__isnull = True, site__isnull = True, ended_at__isnull=True)

        dashboard_data = {
            'obj': obj,
            'projects': projects,
            'sites': sites,
            'peoples_involved': peoples_involved,
            'total_projects': total_projects,
            'total_sites': total_sites,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
            'progress_data': bar_graph.data.values(),
            'progress_labels': bar_graph.data.keys(),
            'roles_org': roles_org,

        }
        return dashboard_data

class Project_dashboard(ProjectRoleMixin, TemplateView):
    template_name = "fieldsight/project_dashboard.html"
    
    def get_context_data(self, **kwargs):
        dashboard_data = super(Project_dashboard, self).get_context_data(**kwargs)
        obj = Project.objects.get(pk=self.kwargs.get('pk'))

        peoples_involved = obj.project_roles.filter(ended_at__isnull=True).distinct('user')
        total_sites = obj.sites.filter(is_active=True, is_survey=False).count()
        sites = obj.sites.filter(is_active=True, is_survey=False)
        data = serialize('custom_geojson', sites, geometry_field='location',
                         fields=('location', 'id',))

        total_sites = sites.count()
        total_survey_sites = obj.sites.filter(is_survey=True).count()
        outstanding, flagged, approved, rejected = obj.get_submissions_count()
        bar_graph = BarGenerator(sites)
        line_chart = LineChartGenerator(obj)
        line_chart_data = line_chart.data()
        roles_project = UserRole.objects.filter(organization__isnull = False, project_id = self.kwargs.get('pk'), site__isnull = True, ended_at__isnull=True)

        dashboard_data = {
            'sites': sites,
            'obj': obj,
            'peoples_involved': peoples_involved,
            'total_sites': total_sites,
            'total_survey_sites': total_survey_sites,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
            'progress_data': bar_graph.data.values(),
            'progress_labels': bar_graph.data.keys(),
            'roles_project': roles_project,
    }
        return dashboard_data


class SiteSurveyListView(LoginRequiredMixin, ProjectMixin, TemplateView):
    def get(self, request, pk):
        return TemplateResponse(request, "fieldsight/site_survey_list.html", {'project':pk})


class SiteDashboardView(ReviewerRoleMixin, TemplateView):
    template_name = 'fieldsight/site_dashboard.html'

    def get_context_data(self, **kwargs):
        dashboard_data = super(SiteDashboardView, self).get_context_data(**kwargs)
        obj = Site.objects.get(pk=self.kwargs.get('pk'))
        peoples_involved = obj.site_roles.filter(ended_at__isnull=True).distinct('user')
        data = serialize('custom_geojson', [obj], geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))

        line_chart = LineChartGeneratorSite(obj)
        line_chart_data = line_chart.data()
        progress_chart = ProgressGeneratorSite(obj)
        progress_chart_data = progress_chart.data()
        meta_questions = obj.project.site_meta_attributes
        meta_answers = obj.site_meta_attributes_ans
        mylist =[]
        for question in meta_questions:
            if question['question_name'] in meta_answers:
                mylist.append({question['question_text'] : meta_answers[question['question_name']]})
        myanswers = mylist
        outstanding, flagged, approved, rejected = obj.get_site_submission()
        dashboard_data = {
            'obj': obj,
            'peoples_involved': peoples_involved,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
            'progress_chart_data_data': progress_chart_data.keys(),
            'progress_chart_data_labels': progress_chart_data.values(),
            'meta_data': myanswers,
        }
        return dashboard_data

class SiteSupervisorDashboardView(SiteSupervisorRoleMixin, TemplateView):
    template_name = 'fieldsight/site_supervisor_dashboard.html'

    def get_context_data(self, **kwargs):
        dashboard_data = super(SiteSupervisorDashboardView, self).get_context_data(**kwargs)
        obj = Site.objects.get(pk=self.kwargs.get('pk'))
        peoples_involved = obj.site_roles.all().order_by('user__first_name')
        data = serialize('custom_geojson', [obj], geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))

        line_chart = LineChartGeneratorSite(obj)
        line_chart_data = line_chart.data()

        outstanding, flagged, approved, rejected = obj.get_site_submission()
        dashboard_data = {
            'obj': obj,
            'peoples_involved': peoples_involved,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
        }
        return dashboard_data

class OrganizationView(object):
    model = Organization
    paginate_by = 51
    queryset = Organization.objects.all()
    success_url = reverse_lazy('fieldsight:organizations-list')
    form_class = OrganizationForm



class UserDetailView(object):
    model = User
    success_url = reverse_lazy('users:users')
    form_class = RegistrationForm


class OrganizationListView(OrganizationView, LoginRequiredMixin, SuperAdminMixin, ListView):
    pass

class OrganizationCreateView(OrganizationView, LoginRequiredMixin, SuperAdminMixin, CreateView):
    def form_valid(self, form):
        self.object = form.save()
        noti = self.object.logs.create(source=self.request.user, type=9, title="new Organization",
                                       organization=self.object, content_object=self.object,
                                       description="{0} created a new organization named {1}".
                                       format(self.request.user, self.object.name))
        result = {}
        result['description'] = '{0} created a new organization named {1} '.format(noti.source.get_full_name(), self.object.name)
        result['url'] = noti.get_absolute_url()
        # ChannelGroup("notify-{}".format(self.object.id)).send({"text": json.dumps(result)})
        ChannelGroup("notify-0").send({"text": json.dumps(result)})

        return HttpResponseRedirect(self.get_success_url())


class OrganizationUpdateView(OrganizationView, OrganizationRoleMixin, UpdateView):
    def get_success_url(self):
        return reverse('fieldsight:organizations-dashboard', kwargs={'pk': self.kwargs['pk']})

    def form_valid(self, form):
        self.object = form.save()
        noti = self.object.logs.create(source=self.request.user, type=13, title="edit Organization",
                                       organization=self.object, content_object=self.object,
                                       description="{0} changed the details of organization named {1}".
                                       format(self.request.user.get_full_name(), self.object.name))
        result = {}
        result['description'] = noti.description
        result['url'] = noti.get_absolute_url()
        ChannelGroup("notify-{0}".format(self.object.id)).send({"text": json.dumps(result)})
        ChannelGroup("notify-0").send({"text": json.dumps(result)})

        return HttpResponseRedirect(self.get_success_url())



class OrganizationDeleteView(OrganizationView, LoginRequiredMixin, SuperAdminMixin, DeleteView):
    pass

@login_required
@group_required('admin')
def alter_org_status(request, pk):
    try:
        obj = Organization.objects.get(pk=int(pk))
            # alter status method on custom user
        if obj.is_active:
            obj.is_active = False
            messages.info(request, 'Organization {0} Deactivated.'.format(obj.name))
        else:
            obj.is_active = True
            messages.info(request, 'Organization {0} Activated.'.format(obj.name))
        obj.save()
    except:
        messages.info(request, 'Organization {0} not found.'.format(obj.name))
    return HttpResponseRedirect(reverse('fieldsight:organizations-list'))

#
# @login_required
# @group_required('admin')
# def add_org_admin_old(request, pk):
#     obj = get_object_or_404(
#         Organization, id=pk)
#     if request.method == 'POST':
#         form = SetOrgAdminForm(request.POST)
#         user = int(form.data.get('user'))
#         group = Group.objects.get(name__exact="Organization Admin")
#         role = UserRole(user_id=user, group=group, organization=obj)
#         role.save()
#         messages.add_message(request, messages.INFO, 'Organization Admin Added')
#         return HttpResponseRedirect(reverse('fieldsight:organizations-list'))
#     else:
#         form = SetOrgAdminForm(instance=obj)
#     return render(request, "fieldsight/add_admin.html", {'obj':obj,'form':form})

class OrganizationadminCreateView(LoginRequiredMixin, OrganizationRoleMixin, TemplateView):

    def get(self, request, pk=None):
        organization = get_object_or_404(Organization, id=pk)
        form = AssignOrgAdmin(request=request)
        scenario = 'Assign'
        return render(request, 'fieldsight/add_admin_form.html',
                      {'form': form, 'scenario': scenario, 'obj': organization})

    def post(self, request):
        organization = get_object_or_404(Organization, id=id)
        group = Group.objects.get(name__exact="Organization Admin")
        role_obj = UserRole(organization=organization, group=group)
        form = AssignOrgAdmin(data=request.POST, instance=role_obj, request=request)
        if form.is_valid():
            role_obj = form.save(commit=False)
            user_id = request.POST.get('user')
            role_obj.user_id = int(user_id)
            role_obj.save()
            messages.add_message(request, messages.INFO, 'Organization Admin Added')
            return HttpResponseRedirect(reverse("fieldsight:organizations-dashboard", kwargs={'pk': id}))


@login_required
@group_required('Organization')
def alter_proj_status(request, pk):
    try:
        obj = Project.objects.get(pk=int(pk))
            # alter status method on custom user
        if obj.is_active:
            obj.is_active = False
            messages.info(request, 'Project {0} Deactivated.'.format(obj.name))
        else:
            obj.is_active = True
            messages.info(request, 'Project {0} Activated.'.format(obj.name))
        obj.save()
    except:
        messages.info(request, 'Project {0} not found.'.format(obj.name))
    return HttpResponseRedirect(reverse('fieldsight:projects-list'))


@group_required('Project')
def stages_status_download(request, pk):
    try:
        data = []
        ss_index = {}
        stages_rows = []
        head_row = ["Site ID", "Name", "Address", "Latitude", "longitude", "Status"]
        project = Project.objects.get(pk=pk)
        stages = project.stages.filter(stage__isnull=True)
        for stage in stages:
            sub_stages = stage.parent.all()
            if len(sub_stages):
                head_row.append("Stage :"+stage.name)
                stages_rows.append("Stage :"+stage.name)

                for ss in sub_stages:
                    head_row.append("Sub Stage :"+ss.name)
                    ss_index.update({head_row.index("Sub Stage :"+ss.name): ss.id})
        data.append(head_row)
        total_cols = len(head_row) - 6 # for non stages
        for site in project.sites.filter(is_active=True, is_survey=False):
            site_row = [site.identifier, site.name, site.address, site.latitude, site.longitude, site.status]
            site_row.extend([None]*total_cols)
            for k, v in ss_index.items():
                if Stage.objects.filter(project_stage_id=v, site=site).count() == 1:
                    site_sub_stage = Stage.objects.get(project_stage_id=v, site=site)
                    site_row[k] = site_sub_stage.form_status
            data.append(site_row)

        p.save_as(array=data, dest_file_name="media/stage-report/{}_stage_data.xls".format(project.id))
        xl_data = open("media/stage-report/{}_stage_data.xls".format(project.id), "rb")
        response = HttpResponse(xl_data, content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = 'attachment; filename="report.xls"'
        return response
    except Exception as e:
        messages.info(request, 'Data Creattion Failed {}'.format(str(e)))
    return HttpResponse("failed Data Creattion Failed {}".format(str(e)))


@login_required
@group_required('Project')
def add_proj_manager(request, pk):
    obj = get_object_or_404(
        Project, pk=pk)
    group = Group.objects.get(name__exact="Project Manager")
    role_obj = UserRole(project=obj, group=group)
    scenario = 'Assign'
    if request.method == 'POST':
        form = SetProjectManagerForm(data=request.POST, instance=role_obj, request=request)
        if form.is_valid():
            role_obj = form.save(commit=False)
            user_id = request.POST.get('user')
            role_obj.user_id = int(user_id)
            role_obj.save()
        messages.add_message(request, messages.INFO, 'Project Manager Added')
        return HttpResponseRedirect(reverse("fieldsight:project-dashboard", kwargs={'pk': obj.pk}))
    else:
        form = SetProjectManagerForm(instance=role_obj, request=request)
    return render(request, "fieldsight/add_project_manager.html", {'obj':obj,'form':form, 'scenario':scenario})


@login_required
@group_required('Project')
def alter_site_status(request, pk):
    try:
        obj = Site.objects.get(pk=int(pk))
        if obj.is_active:
            obj.is_active = False
            messages.info(request, 'Site {0} Deactivated.'.format(obj.name))
        else:
            obj.is_active = True
            messages.info(request, 'Site {0} Activated.'.format(obj.name))
        obj.save()
    except:
        messages.info(request, 'Site {0} not found.'.format(obj.name))
    return HttpResponseRedirect(reverse('fieldsight:sites-list'))


@login_required
@group_required('Reviewer')
def add_supervisor(request, pk):
    obj = get_object_or_404(
        Site, pk=int(pk))
    group = Group.objects.get(name__exact="Site Supervisor")
    role_obj = UserRole(site=obj, group=group)
    if request.method == 'POST':
        form = SetSupervisorForm(data=request.POST, instance=role_obj, request=request)
        if form.is_valid():
            role_obj = form.save(commit=False)
            user_id = request.POST.get('user')
            role_obj.user_id = int(user_id)
            role_obj.save()
        messages.add_message(request, messages.INFO, 'Site Supervisor Added')
        return HttpResponseRedirect(reverse("fieldsight:site-dashboard", kwargs={'pk': obj.pk}))
    else:
        form = SetSupervisorForm(instance=role_obj, request=request)
    return render(request, "fieldsight/add_supervisor.html", {'obj':obj,'form':form})


@login_required
@group_required('Project')
def add_central_engineer(request, pk):
    obj = get_object_or_404(
        Project, pk=pk)
    group = Group.objects.get(name__exact="Reivewer")
    role_obj = UserRole(project=obj, group=group)
    scenario = 'Assign'
    if request.method == 'POST':
        form = SetProjectRoleForm(data=request.POST, instance=role_obj, request=request)
        if form.is_valid():
            role_obj = form.save(commit=False)
            user_id = request.POST.get('user')
            role_obj.user_id = int(user_id)
            role_obj.save()
        messages.add_message(request, messages.INFO, 'Reviewer Added')
        return HttpResponseRedirect(reverse("fieldsight:project-dashboard", kwargs={'pk': obj.pk}))
    else:
        form = SetProjectRoleForm(instance=role_obj, request=request,)
    return render(request, "fieldsight/add_central_engineer.html", {'obj':obj,'form':form, 'scenario':scenario})


@login_required
@group_required('Project')
def add_project_role(request, pk):
    obj = get_object_or_404(
        Project, pk=pk)
    role_obj = UserRole(project=obj)
    scenario = 'Assign People'
    form = SetProjectRoleForm(instance=role_obj, request=request)
    if request.method == 'POST':
        form = SetProjectRoleForm(data=request.POST, instance=role_obj, request=request)
        if form.is_valid():
            role_obj = form.save(commit=False)
            user_id = request.POST.get('user')
            role_obj.user_id = int(user_id)
            role_obj.save()
            messages.add_message(request, messages.INFO, '{} Added'.format(role_obj.group.name))
            return HttpResponseRedirect(reverse("fieldsight:project-dashboard", kwargs={'pk': obj.pk}))
    existing_staffs = obj.get_staffs
    return render(request, "fieldsight/add_central_engineer.html", {'obj':obj,'form':form, 'scenario':scenario,
                                                                    "existing_staffs":existing_staffs})


class ProjectView(object):
    model = Project
    success_url = reverse_lazy('fieldsight:project-list')
    form_class = ProjectForm

class ProjectRoleView(object):
    model = Project
    success_url = reverse_lazy('fieldsight:project-list')
    form_class = ProjectForm

class ProjectListView(ProjectRoleView, OrganizationMixin, ListView):
    pass
    


class ProjectCreateView(ProjectView, OrganizationRoleMixin, CreateView):
    
    def get_context_data(self, **kwargs):
        context = super(ProjectCreateView, self).get_context_data(**kwargs)
        context['org'] = Organization.objects.get(pk=self.kwargs.get('pk'))
        context['pk'] = self.kwargs.get('pk')
        return context

    def form_valid(self, form):
        self.object = form.save(organization_id=self.kwargs.get('pk'), new=True)
        
        noti = self.object.logs.create(source=self.request.user, type=10, title="new Project",
                                       organization=self.object.organization, content_object=self.object,
                                       description='{0} created new project named {1}'.format(
                                           self.request.user.get_full_name(), self.object.name))
        result = {}
        result['description'] = noti.description
        result['url'] = noti.get_absolute_url()
        ChannelGroup("notify-{}".format(self.object.organization.id)).send({"text": json.dumps(result)})
        # ChannelGroup("notify-0").send({"text": json.dumps(result)})


        return HttpResponseRedirect(self.object.get_absolute_url())


class ProjectUpdateView(ProjectView, ProjectRoleMixin, UpdateView):
    def get_success_url(self):
        return reverse('fieldsight:project-dashboard', kwargs={'pk': self.kwargs['pk']})

    def form_valid(self, form):
        self.object = form.save(new=False)
        noti = self.object.logs.create(source=self.request.user, type=14, title="Edit Project",
                                       organization=self.object.organization,
                                       project=self.object, content_object=self.object,
                                       description='{0} changed the details of project named {1}'.format(
                                           self.request.user.get_full_name(), self.object.name))
        result = {}
        result['description'] = noti.description
        result['url'] = noti.get_absolute_url()
        ChannelGroup("notify-{}".format(self.object.organization.id)).send({"text": json.dumps(result)})
        ChannelGroup("project-{}".format(self.object.id)).send({"text": json.dumps(result)})

        return HttpResponseRedirect(self.get_success_url())



class ProjectDeleteView(ProjectView, ProjectRoleMixinDeleteView, DeleteView):
    def get_success_url(self):
        return reverse('fieldsight:org-project-list', kwargs={'pk': self.kwargs['org_id'] })

    def delete(self,*args, **kwargs):
        self.kwargs['org_id'] = self.get_object().organization_id
        self.object = self.get_object().delete()
        # noti = self.object.logs.create(source=self.request.user, type=4, title="new Site",
        #                                organization=self.object.organization,
        #                                description="new project {0} deleted by {1}".
        #                                format(self.object.name, self.request.user.username))
        # result = {}
        # result['description'] = 'new project {0} deleted by {1}'.format(self.object.name, self.request.user.username)
        # result['url'] = noti.get_absolute_url()
        # ChannelGroup("notify-{}".format(self.object.organization.id)).send({"text": json.dumps(result)})
        # ChannelGroup("notify-0").send({"text": json.dumps(result)})
        return HttpResponseRedirect(self.get_success_url())



class SiteView(object):
    model = Site
    # success_url = reverse_lazy('fieldsight:org-site-list')
    form_class = SiteForm


class SiteListView(SiteView, ReviewerRoleMixin, ListView):
    def get_context_data(self, **kwargs):
        context = super(SiteListView, self).get_context_data(**kwargs)
        context['form'] = SiteForm()
        return context


class SiteCreateView(SiteView, ProjectRoleMixin, CreateView):
    def get_context_data(self, **kwargs):
        context = super(SiteCreateView, self).get_context_data(**kwargs)
        project=Project.objects.get(pk=self.kwargs.get('pk'))
        context['project'] = project
        context['pk'] = self.kwargs.get('pk')
        context['json_questions'] = json.dumps(project.site_meta_attributes)
        return context
        
    def get_success_url(self):
        return reverse('fieldsight:site-dashboard', kwargs={'pk': self.object.id})

    def form_valid(self, form):
        self.object = form.save(project_id=self.kwargs.get('pk'), new=True)
        noti = self.object.logs.create(source=self.request.user, type=11, title="new Site",
                                       organization=self.object.project.organization,
                                       project=self.object.project, content_object=self.object, extra_object=self.object.project,
                                       description='{0} created a new site named {1} in {2}'.format(self.request.user.get_full_name(),
                                                                                 self.object.name, self.object.project.name))
        result = {}
        result['description'] = '{0} created a new site named {1} in {2}'.format(self.request.user.get_full_name(),
                                                                                 self.object.name, self.object.project.name)
        result['url'] = noti.get_absolute_url()
        ChannelGroup("project-{}".format(self.object.project.id)).send({"text": json.dumps(result)})
        # ChannelGroup("notify-0").send({"text": json.dumps(result)})

        return HttpResponseRedirect(self.get_success_url())



class SiteUpdateView(SiteView, ReviewerRoleMixin, UpdateView):
    def get_context_data(self, **kwargs):
        context = super(SiteUpdateView, self).get_context_data(**kwargs)
        site=Site.objects.get(pk=self.kwargs.get('pk'))
        context['project'] = site.project
        context['pk'] = self.kwargs.get('pk')
        context['json_questions'] = json.dumps(site.project.site_meta_attributes)
        context['json_answers'] = json.dumps(site.site_meta_attributes_ans)
        return context

    def get_success_url(self):
        return reverse('fieldsight:site-dashboard', kwargs={'pk': self.kwargs['pk']})

    def form_valid(self, form):
        self.object = form.save(project_id=self.kwargs.get('pk'), new=False)
        noti = self.object.logs.create(source=self.request.user, type=15, title="edit Site",
                                       organization=self.object.project.organization, project=self.object.project, content_object=self.object,
                                       description='{0} changed the details of site named {1}'.format(
                                           self.request.user.get_full_name(), self.object.name))
        result = {}
        result['description'] = 'new site {0} updated by {1}'.format(self.object.name, self.request.user.username)
        result['url'] = noti.get_absolute_url()
        ChannelGroup("notify-{}".format(self.object.project.organization.id)).send({"text": json.dumps(result)})
        ChannelGroup("project-{}".format(self.object.project.id)).send({"text": json.dumps(result)})
        ChannelGroup("site-{}".format(self.object.id)).send({"text": json.dumps(result)})
        # ChannelGroup("notify-0").send({"text": json.dumps(result)})

        return HttpResponseRedirect(self.get_success_url())


class SiteDeleteView(SiteView, SiteDeleteRoleMixin, DeleteView):
    def get_success_url(self):
        return reverse('fieldsight:proj-site-list', kwargs={'pk': self.object.project_id})

    # def delete(self,*args, **kwargs):
    #     self.kwargs['pk'] = self.get_object().pk
    #     self.object = self.get_object().delete()
    #     # noti = self.object.logs.create(source=self.request.user, type=4, title="new Site",
    #     #                                organization=self.object.organization,
    #     #                                description="new project {0} deleted by {1}".
    #     #                                format(self.object.name, self.request.user.username))
    #     # result = {}
    #     # result['description'] = 'new project {0} deleted by {1}'.format(self.object.name, self.request.user.username)
    #     # result['url'] = noti.get_absolute_url()
    #     # ChannelGroup("notify-{}".format(self.object.organization.id)).send({"text": json.dumps(result)})
    #     # ChannelGroup("notify-0").send({"text": json.dumps(result)})
    #     return HttpResponseRedirect(self.get_success_url())
    #


@group_required("Project")
@api_view(['POST'])
def ajax_upload_sites(request, pk):
    form = UploadFileForm(request.POST, request.FILES)
    if form.is_valid():
        count = 0
        project = Project(pk=pk)
        try:
            sites = request.FILES['file'].get_records()
            count = len(sites)
            with transaction.atomic():
                for site in sites:
                    site = dict((k,v) for k,v in site.iteritems() if v is not '')
                    lat = site.get("longitude", 85.3240)
                    long = site.get("latitude", 27.7172)
                    location = Point(lat, long, srid=4326)
                    type_id = int(site.get("type", "1"))
                    _site, created = Site.objects.get_or_create(identifier=str(site.get("id")), name=site.get("name"),
                                                                project=project, type_id=type_id)
                    _site.phone = site.get("phone")
                    _site.address = site.get("address")
                    _site.public_desc = site.get("public_desc"),
                    _site.additional_desc = site.get("additional_desc")
                    _site.location=location
                    _site.save()
            if count:
                noti = project.logs.create(source=request.user, type=12, title="Bulk Sites",
                                       organization=project.organization,
                                       project=project, content_object=project,
                                       extra_message=count + "Sites",
                                       description='{0} created a {1} sites in {2}'.
                                           format(request.user.get_full_name(), count, project.name))
                result = {}
                result['description'] = noti.description
                result['url'] = noti.get_absolute_url()
                ChannelGroup("project-{}".format(project.id)).send({"text": json.dumps(result)})
            return Response({'msg': 'ok'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'file':e.message}, status=status.HTTP_400_BAD_REQUEST)
    return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)


@group_required("Project")
@api_view(['POST'])
def ajax_save_site(request):
    id = request.POST.get('id', False)
    if id =="undefined":
        id = False
    if id:
        instance = Site.objects.get(pk=id)
        form = SiteForm(request.POST, request.FILES, instance)
    else:
        form = SiteForm(request.POST, request.FILES)
    if form.is_valid():
        form.save()
        return Response({'msg': 'ok'}, status=status.HTTP_200_OK)
    return Response({'error': 'Invalid Site Data'}, status=status.HTTP_400_BAD_REQUEST)


@group_required("Organization")
@api_view(['POST'])
def ajax_save_project(request):
    id = request.POST.get('id', False)
    if id =="undefined":
        id = False
    if id:
        instance = Project.objects.get(pk=id)
        form = ProjectFormKo(request.POST, request.FILES, instance)
    else:
        form = ProjectFormKo(request.POST, request.FILES)
    if form.is_valid():
        form.save()
        return Response({'msg': 'ok'}, status=status.HTTP_200_OK)
    return Response({'error': 'Invalid Project Data'}, status=status.HTTP_400_BAD_REQUEST)

class UploadSitesView(ProjectRoleMixin, TemplateView):

    def get(self, request, pk):
        obj = get_object_or_404(Project, pk=pk)
        form = UploadFileForm()
        return render(request, 'fieldsight/upload_sites.html',{'obj': obj, 'form':form, 'project':pk})

    def post(self, request, pk=id):
        obj = get_object_or_404(Project, pk=pk)
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                sitefile=request.FILES['file']
                user = request.user
                print sitefile
                task = bulkuploadsites.delay(user, sitefile, pk)
                if CeleryTaskProgress.objects.create(task_id=task.id, user=user, task_type=0):
                    messages.success(request, 'Sites are being uploaded. You will be notified in notifications list as well.')
                else:
                    messages.success(request, 'Sites cannot be updated a the moment.')
                return HttpResponseRedirect(reverse('fieldsight:proj-site-list', kwargs={'pk': pk}))
            except Exception as e:
                form.full_clean()
                form._errors[NON_FIELD_ERRORS] = form.error_class(['Sites Upload Failed, UnSupported Data', e])
                messages.warning(request, 'Site Upload Failed, UnSupported Data ')
        return render(request, 'fieldsight/upload_sites.html', {'obj': obj, 'form': form, 'project': pk})


def download(request):
    sheet = excel.pe.Sheet([[1, 2],[3, 4]])
    return excel.make_response(sheet, "csv")


class UserListView(ProjectMixin, OrganizationViewFromProfile, ListView):
    def get_template_names(self):
        return ['fieldsight/user_list.html']

    def get_context_data(self, **kwargs):
        context = super(UserListView, self).get_context_data(**kwargs)
        context['groups'] = Group.objects.all()
        return context


class FilterUserView(TemplateView):
    def get(self, *args, **kwargs):
        return redirect('fieldsight:user-list')

    def post(self, request, *args, **kwargs):
        name = request.POST.get('name')
        role = request.POST.get('role')
        groups = Group.objects.all()
        object_list = User.objects.filter(is_active=True, pk__gt=0)
        if name:
            object_list = object_list.filter(
                Q(first_name__contains=name) | Q(last_name__contains=name) | Q(username__contains=name))
        if role and role != '0':
            object_list = object_list.filter(user_roles__group__id=role)
        if hasattr(request, "organization") and request.organization:
            object_list = object_list.filter(user_roles__organization=request.organization)
        return render(request, 'fieldsight/user_list.html', {'object_list': object_list, 'groups': groups})



class CreateUserView(LoginRequiredMixin, SuperAdminMixin, UserDetailView, RegistrationView):
    def register(self, request, form, *args, **kwargs):
        with transaction.atomic():
            new_user = super(CreateUserView, self).register(
                request, form, *args, **kwargs)
            is_active = form.cleaned_data['is_active']
            new_user.first_name = request.POST.get('name', '')
            new_user.is_active = is_active
            new_user.is_superuser = True
            new_user.save()
            organization = int(form.cleaned_data['organization'])
            org = Organization.objects.get(pk=organization)
            profile = UserProfile(user=new_user, organization=org)
            profile.save()
            # noti = profile.logs.create(source=self.request.user, type=0, title="new User",
            #                         organization=profile.organization, description="new user {0} created by {1}".
            #                         format(new_user.username, self.request.user.username))
            # result = {}
            # result['description'] = 'new user {0} created by {1}'.format(new_user.username, self.request.user.username)
            # result['url'] = noti.get_absolute_url()
            # ChannelGroup("notify-{}".format(profile.organization.id)).send({"text":json.dumps(result)})
            # ChannelGroup("notify-0").send({"text":json.dumps(result)})

        return new_user

class BluePrintsView(LoginRequiredMixin, TemplateView):
    def get(self, request, *args, **kwargs):
        site = Site.objects.get(pk=self.kwargs.get('id'))
        blueprints = site.blueprints.all()

        ImageFormSet = modelformset_factory(BluePrints, form=BluePrintForm, extra=5)
        formset = ImageFormSet(queryset=BluePrints.objects.none())
        return render(request, 'fieldsight/blueprints_form.html', {'site': site, 'formset': formset,'id': self.kwargs.get('id'),
                                                                   'blueprints':blueprints},)

    def post(self, request, id):
        ImageFormSet = modelformset_factory(BluePrints, form=BluePrintForm, extra=5)
        formset = ImageFormSet(request.POST, request.FILES,
                                   queryset=BluePrints.objects.none())

        if formset.is_valid():
            for form in formset.cleaned_data:
                if 'image' in form:
                    image = form['image']
                    photo = BluePrints(site_id=id, image=image)
                    photo.save()
            messages.success(request,
                             "Blueprints saved!")
            site = Site.objects.get(pk=id)
            blueprints = site.blueprints.all()

            ImageFormSet = modelformset_factory(BluePrints, form=BluePrintForm, extra=5)
            formset = ImageFormSet(queryset=BluePrints.objects.none())
            return render(request, 'fieldsight/blueprints_form.html', {'site': site, 'formset': formset,'id': self.kwargs.get('id'),
                                                                   'blueprints':blueprints},)

            # return HttpResponseRedirect(reverse("fieldsight:site-dashboard", kwargs={'pk': id}))

        formset = ImageFormSet(queryset=BluePrints.objects.none())
        return render(request, 'fieldsight/blueprints_form.html', {'formset': formset, 'id': self.kwargs.get('id')}, )


class ManagePeopleSiteView(LoginRequiredMixin, ReviewerRoleMixin, TemplateView):
    def get(self, request, pk):
        obj = get_object_or_404(Site, id=self.kwargs.get('pk'))
        project = Site.objects.get(pk=pk).project
        return render(request, 'fieldsight/manage_people_site.html', {'obj': obj, 'pk':pk, 'level': "0", 'category':"site", 'organization': project.organization.id, 'project':project.id, 'site':pk})


class ManagePeopleProjectView(LoginRequiredMixin, ProjectRoleMixin, TemplateView):
    def get(self, request, pk):
        obj = get_object_or_404(Project, id=self.kwargs.get('pk'))
        project = Project.objects.get(pk=pk)
        organization=project.organization_id
        return render(request, 'fieldsight/manage_people_site.html', {'obj': obj, 'pk': pk, 'level': "1", 'category':"Project Manager", 'organization': organization, 'project': pk, 'type':'project', 'obj':project, })


class ManagePeopleOrganizationView(LoginRequiredMixin, OrganizationRoleMixin, TemplateView):
    def get(self, request, pk):
        obj = get_object_or_404(Organization, id=self.kwargs.get('pk'))
        return render(request, 'fieldsight/manage_people_site.html', {'obj': obj, 'pk': pk, 'level': "2", 'category':"Organization Admin", 'organization': pk, 'type':'org'})


def all_notification(user,  message):
    ChannelGroup("%s" % user).send({
        "text": json.dumps({
            "msg": message
        })
    })

class RolesView(LoginRequiredMixin, TemplateView):
    template_name = "fieldsight/roles_dashboard.html"
    def get_context_data(self, **kwargs):
        context = super(RolesView, self).get_context_data(**kwargs)
        context['org_admin'] = self.request.roles.select_related('organization').filter(group__name="Organization Admin")
        context['proj_manager'] = self.request.roles.select_related('project').filter(group__name = "Project Manager")
        context['proj_donor'] = self.request.roles.select_related('project').filter(group__name = "Project Donor")
        context['site_reviewer'] = self.request.roles.select_related('site').filter(group__name = "Reviewer")
        context['site_supervisor'] = self.request.roles.select_related('site').filter(group__name = "Site Supervisor")
        return context


class OrgProjectList(OrganizationRoleMixin, ListView):
    model =   Project
    paginate_by = 51
    def get_context_data(self, **kwargs):
        context = super(OrgProjectList, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        return context
    def get_queryset(self):
        queryset = Project.objects.filter(organization_id=self.kwargs.get('pk'))
        return queryset


class OrgSiteList(OrganizationRoleMixin, ListView):
    def get_context_data(self, **kwargs):
        context = super(OrgSiteList, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['type'] = "org"
        return context
    def get_queryset(self):
        queryset = Site.objects.filter(project__organization_id=self.kwargs.get('pk'),is_survey=False, is_active=True)
        return queryset

class ProjSiteList(ProjectRoleMixin, ListView):
    def get_context_data(self, **kwargs):
        context = super(ProjSiteList, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['type'] = "project"
        context['is_form_proj'] = True
        return context
    def get_queryset(self):
        queryset = Site.objects.filter(project_id=self.kwargs.get('pk'),is_survey=False, is_active=True)
        return queryset

class DonorProjSiteList(ReadonlyProjectLevelRoleMixin, ListView):
    template_name = "fieldsight/donor_site_list.html"
    def get_context_data(self, **kwargs):
        context = super(ProjSiteList, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['type'] = "project"
        context['is_form_proj'] = True
        return context
    def get_queryset(self):
        queryset = Site.objects.filter(project_id=self.kwargs.get('pk'),is_survey=False, is_active=True)
        return queryset

class OrgUserList(OrganizationRoleMixin, ListView):
    model = UserRole
    paginate_by = 51
    template_name = "fieldsight/user_list_updated.html"
    def get_context_data(self, **kwargs):
        context = super(OrgUserList, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['obj'] = Organization.objects.get(pk=self.kwargs.get('pk'))
        context['organization_id'] = self.kwargs.get('pk')
        context['type'] = "organization"
        return context
    def get_queryset(self):
        #queryset = UserRole.objects.select_related('User').filter(organization_id=self.kwargs.get('pk')).distinct('user_id')
        #queryset = User.objects.select_related('user_profile').filter(user_profile__organization_id=self.kwargs.get('pk'))
        
        queryset = UserRole.objects.select_related('user').filter(organization_id=self.kwargs.get('pk'), ended_at__isnull=True).distinct('user_id')
        return queryset

class ProjUserList(ProjectRoleMixin, ListView):
    model = UserRole
    paginate_by = 51
    template_name = "fieldsight/user_list_updated.html"
    def get_context_data(self, **kwargs):
        context = super(ProjUserList, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['obj'] = Project.objects.get(pk=self.kwargs.get('pk'))
        context['organization_id'] = Project.objects.get(pk=self.kwargs.get('pk')).organization.id
        context['type'] = "project"
        return context
    def get_queryset(self):
        queryset = UserRole.objects.select_related('user').filter(project_id=self.kwargs.get('pk'), ended_at__isnull=True).distinct('user_id')
        return queryset

class SiteUserList(ReviewerRoleMixin, ListView):
    model = UserRole
    paginate_by = 51
    template_name = "fieldsight/user_list_updated.html"
    def get_context_data(self, **kwargs):
        context = super(SiteUserList, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['obj'] = Site.objects.get(pk=self.kwargs.get('pk'))
        context['organization_id'] = Site.objects.get(pk=self.kwargs.get('pk')).project.organization.id
        context['type'] = "site"
        return context
    def get_queryset(self):
        queryset = UserRole.objects.select_related('user').filter(site_id=self.kwargs.get('pk'), ended_at__isnull=True).distinct('user_id')
    
        return queryset

@login_required()
def ajaxgetuser(request):
    user = User.objects.filter(email=request.POST.get('email'))
    html = render_to_string('fieldsight/ajax_temp/ajax_user.html', {'department': User.objects.filter(email=user)})
    return HttpResponse(html)

def RepresentsInt(s):
    try: 
        int(s)
        return True
    except ValueError:
        return False


@login_required()
def senduserinvite(request):

    emails =request.POST.getlist('emails[]')
    group = Group.objects.get(name=request.POST.get('group'))

    organization_id = None
    project_id =None
    site_id =None

    if RepresentsInt(request.POST.get('organization_id')):
        organization_id = request.POST.get('organization_id')
    if RepresentsInt(request.POST.get('project_id')):
        project_id = request.POST.get('project_id')
    if RepresentsInt(request.POST.get('site_id')):
        site_id = request.POST.get('site_id')

    response=""

    for email in emails:
        email = email.strip()
        user = User.objects.filter(email=email)
        userinvite = UserInvite.objects.filter(email=email, organization_id=organization_id, group=group, project_id=project_id,  site_id=site_id, is_used=False)

        if userinvite:
            if group.name == "Unassigned":
                response += 'Invite for '+ email + ' has already been sent.<br>'
            else:
                response += 'Invite for '+ email + ' in ' + group.name +' role has already been sent.<br>'
            continue
        if user:
            userrole = UserRole.objects.filter(user=user[0], group=group, organization_id=organization_id, project_id=project_id, site_id=site_id).order_by('-id')
            
            if userrole:
                if userrole[0].ended_at==None:
                    if group.name == "Unassigned":
                        response += email + ' has already joined this organization.<br>'
                    else:
                        response += email + ' already has the role for '+group.name+'.<br>' 
                    continue
            invite = UserInvite(email=email, by_user_id=request.user.id ,group=group, token=get_random_string(length=32), organization_id=organization_id, project_id=project_id, site_id=site_id)

            invite.save()
            # organization = Organization.objects.get(pk=1)
            # noti = invite.logs.create(source=user[0], type=9, title="new Role",
            #                                organization_id=request.POST.get('organization_id'),
            #                                description="{0} sent you an invite to join {1} as the {2}.".
            #                                format(request.user.username, organization.name, invite.group.name,))
            # result = {}
            # result['description'] = 'new site {0} deleted by {1}'.format(self.object.name, self.request.user.username)
            # result['url'] = noti.get_absolute_url()
            # ChannelGroup("notify-{}".format(self.object.project.organization.id)).send({"text": json.dumps(result)})
            # ChannelGroup("notify-0").send({"text": json.dumps(result)})

        else:
            invite = UserInvite(email=email, by_user_id=request.user.id, token=get_random_string(length=32), group=group, project_id=project_id, organization_id=organization_id,  site_id=site_id)
            invite.save()
        current_site = get_current_site(request)
        subject = 'Invitation for Role'
        data ={
            'email': invite.email,
            'domain': current_site.domain,
            'invite_id': urlsafe_base64_encode(force_bytes(invite.pk)),
            'token': invite.token,
            'invite': invite,
            }
        message = get_template('fieldsight/email_sample.html').render(Context(data))
        email_to = (invite.email,)
        
        msg = EmailMessage(subject, message, 'Field Sight', email_to)
        msg.content_subtype = "html"
        msg.send()
        if group.name == "Unassigned":
            response += "Sucessfully invited "+ email +" to join this organization.<br>"
        else:    
            response += "Sucessfully invited "+ email +" for "+ group.name +" role.<br>"
        continue

    return HttpResponse(response)

def invitemultiregionalusers(request, emails, group, region_ids):
   
    response=""
    for region_id in region_ids:
        region = Region.objects.get(id=region_id);
        project_id = region.project_id
        organization_id = region.project.organization_id  
        sites = Site.objects.filter(region_id=region_id)  
        for site in sites:

            for email in emails:
                email = email.strip()
                user = User.objects.filter(email=email)
                userinvite = UserInvite.objects.filter(email=email, organization_id=organization_id, group=group, project_id=project_id,  site_id=site_id, is_used=False)

                if userinvite:
                    response += 'Invite for '+ email + ' in ' + group.name +' role has already been sent.<br>'
                    continue
                if user:
                    userrole = UserRole.objects.filter(user=user[0], group=group, organization_id=organization_id, project_id=project_id, site_id=site_id).order_by('-id')
                    
                    if userrole:
                        if userrole[0].ended_at==None:
                            if group.name == "Unassigned":
                                response += email + ' has already joined this organization.<br>'
                            else:
                                response += email + ' already has the role for '+group.name+'.<br>' 
                            continue
                    invite = UserInvite(email=email, by_user_id=request.user.id ,group=group, token=get_random_string(length=32), organization_id=organization_id, project_id=project_id, site_id=site_id)

                    invite.save()
                    # organization = Organization.objects.get(pk=1)
                    # noti = invite.logs.create(source=user[0], type=9, title="new Role",
                    #                                organization_id=request.POST.get('organization_id'),
                    #                                description="{0} sent you an invite to join {1} as the {2}.".
                    #                                format(request.user.username, organization.name, invite.group.name,))
                    # result = {}
                    # result['description'] = 'new site {0} deleted by {1}'.format(self.object.name, self.request.user.username)
                    # result['url'] = noti.get_absolute_url()
                    # ChannelGroup("notify-{}".format(self.object.project.organization.id)).send({"text": json.dumps(result)})
                    # ChannelGroup("notify-0").send({"text": json.dumps(result)})

                else:
                    invite = UserInvite(email=email, by_user_id=request.user.id, token=get_random_string(length=32), group=group, project_id=project_id, organization_id=organization_id,  site_id=site_id)
                    invite.save()
                current_site = get_current_site(request)
                subject = 'Invitation for Role'
                data = {
                    'email': invite.email,
                    'domain': current_site.domain,
                    'invite_id': urlsafe_base64_encode(force_bytes(invite.pk)),
                    'token': invite.token,
                    'invite': invite,
                    }
                email_to = (invite.email,)

                message = get_template('fieldsight/email_sample.html').render(Context(data))
                email_to = (invite.email,)
                
                msg = EmailMessage(subject, message, 'Field Sight', email_to)
                msg.content_subtype = "html"
                msg.send()

                if group.name == "Unassigned":
                    response += "Sucessfully invited "+ email +" to join this organization.<br>"
                else:    
                    response += "Sucessfully invited "+ email +" for "+ group.name +" role.<br>"
                continue
    return HttpResponse(response)

@login_required()
def sendmultiroleuserinvite(request):
    data = json.loads(request.body)
    emails =data.get('emails')
    levels =data.get('levels')
    leveltype =data.get('leveltype')
    group = Group.objects.get(name=data.get('group'))

    response=""
    print levels
    print group
    if leveltype == "region":
        for region_id in levels:
            region = Region.objects.get(id=region_id);
            project_id = region.project_id
            organization_id = region.project.organization_id  
            sites = Site.objects.filter(region_id=region_id)  
            for site in sites:
                site_id=site.id

                for email in emails:
                    email = email.strip()
                    user = User.objects.filter(email=email)
                    userinvite = UserInvite.objects.filter(email=email, organization_id=organization_id, group=group, project_id=project_id,  site_id=site_id, is_used=False)

                    if userinvite:
                        response += 'Invite for '+ email + ' in ' + group.name +' role has already been sent.<br>'
                        continue
                    if user:
                        userrole = UserRole.objects.filter(user=user[0], group=group, organization_id=organization_id, project_id=project_id, site_id=site_id).order_by('-id')
                        
                        if userrole:
                            if userrole[0].ended_at==None:
                                if group.name == "Unassigned":
                                    response += email + ' has already joined this organization.<br>'
                                else:
                                    response += email + ' already has the role for '+group.name+'.<br>' 
                                continue
                        invite = UserInvite(email=email, by_user_id=request.user.id ,group=group, token=get_random_string(length=32), organization_id=organization_id, project_id=project_id, site_id=site_id)

                        invite.save()
                        # organization = Organization.objects.get(pk=1)
                        # noti = invite.logs.create(source=user[0], type=9, title="new Role",
                        #                                organization_id=request.POST.get('organization_id'),
                        #                                description="{0} sent you an invite to join {1} as the {2}.".
                        #                                format(request.user.username, organization.name, invite.group.name,))
                        # result = {}
                        # result['description'] = 'new site {0} deleted by {1}'.format(self.object.name, self.request.user.username)
                        # result['url'] = noti.get_absolute_url()
                        # ChannelGroup("notify-{}".format(self.object.project.organization.id)).send({"text": json.dumps(result)})
                        # ChannelGroup("notify-0").send({"text": json.dumps(result)})

                    else:
                        invite = UserInvite(email=email, by_user_id=request.user.id, token=get_random_string(length=32), group=group, project_id=project_id, organization_id=organization_id,  site_id=site_id)
                        invite.save()
                    current_site = get_current_site(request)
                    subject = 'Invitation for Role'
                    data ={
                        'email': invite.email,
                        'domain': current_site.domain,
                        'invite_id': urlsafe_base64_encode(force_bytes(invite.pk)),
                        'token': invite.token,
                        'invite': invite,
                        }
                    email_to = (invite.email,)
                    
                    message = get_template('fieldsight/email_sample.html').render(Context(data))
                    email_to = (invite.email,)
                    
                    msg = EmailMessage(subject, message, 'Field Sight', email_to)
                    msg.content_subtype = "html"
                    msg.send()

                    if group.name == "Unassigned":
                        response += "Sucessfully invited "+ email +" to join this organization.<br>"
                    else:    
                        response += "Sucessfully invited "+ email +" for "+ group.name +" role.<br>"
                    continue
        return HttpResponse(response)
    for level in levels:
        organization_id = None
        project_id =None
        site_id =None

        if leveltype == "project":
            project_id = level
            organization_id = Project.objects.get(pk=level).organization_id
            print organization_id

        elif leveltype == "site":
            site_id = level
            site = Site.objects.get(pk=site_id)

            project_id = site.project_id
            organization_id = site.project.organization_id

        
        for email in emails:

            user = User.objects.filter(email=email)
            userinvite = UserInvite.objects.filter(email=email, organization_id=organization_id, group=group, project_id=project_id,  site_id=site_id, is_used=False)
            
            if userinvite:
                response += 'Invite for '+ email + ' in ' + group.name +' role has already been sent.<br>'
                continue
            if user:
                userrole = UserRole.objects.filter(user=user[0], group=group, organization_id=organization_id, project_id=project_id, site_id=site_id).order_by('-id')
                
                if userrole:
                    if userrole[0].ended_at==None:
                        response += email + ' already has the role for '+group.name+'.<br>' 
                        continue
                invite, created = UserInvite.objects.get_or_create(email=email, by_user_id=request.user.id ,group=group, token=get_random_string(length=32), organization_id=organization_id, project_id=project_id, site_id=site_id)

                # noti = invite.logs.create(source=user[0], type=9, title="new Role",
                #                                organization_id=request.POST.get('organization_id'),
                #                                description="{0} sent you an invite to join {1} as the {2}.".
                #                                format(request.user.username, organization.name, invite.group.name,))
                # result = {}
                # result['description'] = 'new site {0} deleted by {1}'.format(self.object.name, self.request.user.username)
                # result['url'] = noti.get_absolute_url()
                # ChannelGroup("notify-{}".format(self.object.project.organization.id)).send({"text": json.dumps(result)})
                # ChannelGroup("notify-0").send({"text": json.dumps(result)})

            else:
                invite, created = UserInvite.objects.get_or_create(email=email, by_user_id=request.user.id, token=get_random_string(length=32), group=group, project_id=project_id, organization_id=organization_id,  site_id=site_id)
            current_site = get_current_site(request)
            subject = 'Invitation for Role'
            data = {
                'email': invite.email,
                'domain': current_site.domain,
                'invite_id': urlsafe_base64_encode(force_bytes(invite.pk)),
                'token': invite.token,
                'invite': invite,
                }
            email_to = (invite.email,)
            
            message = get_template('fieldsight/email_sample.html').render(Context(data))
            email_to = (invite.email,)
            
            msg = EmailMessage(subject, message, 'Field Sight', email_to)
            msg.content_subtype = "html"
            msg.send()

            response += "Sucessfully invited "+ email +" for "+ group.name +" role.<br>"
            continue
    return HttpResponse(response)


# def activate_role(request, invite_idb64, token):
#     try:
#         invite_id = force_text(urlsafe_base64_decode(invite_idb64))
#         invite = UserInvite.objects.filter(id=invite_id, token=token, is_used=False)
#     except (TypeError, ValueError, OverflowError, UserInvite.DoesNotExist):
#         invite = None
#     if invite:
#         user = User.objects.filter(email=invite[0].email)
#         if user:
#             userrole = UserRole(user=user[0], group=invite[0].group, organization=invite[0].organization, project=invite[0].project, site=invite[0].site)
#             userrole.save()
#             return HttpResponse("Sucess")
#         else:

#     return HttpResponse("Failed")
   
class ActivateRole(TemplateView):
    def dispatch(self, request, invite_idb64, token):
        invite_id = force_text(urlsafe_base64_decode(invite_idb64))
        invite = UserInvite.objects.filter(id=invite_id, token=token, is_used=False)
        if invite:
            return super(ActivateRole, self).dispatch(request, invite[0], invite_idb64, token)
        return HttpResponseRedirect(reverse('login'))

    def get(self, request, invite, invite_idb64, token):
        user = User.objects.filter(email=invite.email)
        if invite.is_used==True:
            return HttpResponseRedirect(reverse('login'))
        if user:
            return render(request, 'fieldsight/invite_action.html',{'invite':invite, 'is_used': False, 'status':'',})
        else:
            return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'',})
        

    def post(self, request, invite, *args, **kwargs):
        user_exists = User.objects.filter(email=invite.email)
        if user_exists:
            user = user_exists[0] 
            if request.POST.get('response') == "accept":
                userrole = UserRole.objects.get_or_create(user=user, group=invite.group, organization=invite.organization, project=invite.project, site=invite.site)
            else:
                invite.is_declined = True
            invite.is_used = True
            invite.save()
        else:
            username = request.POST.get('username')
            if len(request.POST.get('username')) < 6:
                return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'error-6', 'username':request.POST.get('username'), 'firstname':request.POST.get('firstname'), 'lastname':request.POST.get('lastname')})

            for i in username:
                if i.isupper():
                    return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'error-3', 'username':request.POST.get('username'), 'firstname':request.POST.get('firstname'), 'lastname':request.POST.get('lastname')})
                    break
                if not i.isalnum():
                    return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'error-1', 'username':request.POST.get('username'), 'firstname':request.POST.get('firstname'), 'lastname':request.POST.get('lastname')})
                    break
            if request.POST.get('password1') != request.POST.get('password2'):
                return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'error-4', 'username':request.POST.get('username'), 'firstname':request.POST.get('firstname'), 'lastname':request.POST.get('lastname')})

            if User.objects.filter(username=request.POST.get('username')).exists():
                return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'error-2', 'username':request.POST.get('username'), 'firstname':request.POST.get('firstname'), 'lastname':request.POST.get('lastname')})

            if request.POST.get('password1') != request.POST.get('password2'):
                return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'error-4', 'username':request.POST.get('username'), 'firstname':request.POST.get('firstname'), 'lastname':request.POST.get('lastname')})

            if request.POST.get('password1') == request.POST.get('password2') and len(request.POST.get('password1')) < 8:
                return render(request, 'fieldsight/invited_user_reg.html',{'invite':invite, 'is_used': False, 'status':'error-5', 'username':request.POST.get('username'), 'firstname':request.POST.get('firstname'), 'lastname':request.POST.get('lastname')})
            

            user = User(username=request.POST.get('username'), email=invite.email, first_name=request.POST.get('firstname'), last_name=request.POST.get('lastname'))
            user.set_password(request.POST.get('password1'))
            user.save()
            
## Needs completion
            codenames=['add_asset', 'change_asset','delete_asset', 'view_asset', 'share_asset']
            permissions = Permission.objects.filter(codename__in=codenames)
            user.user_permissions.add(permissions[0], permissions[1], permissions[2], permissions[3], permissions[4])


            profile, created = UserProfile.objects.get_or_create(user=user, organization=invite.organization)
            userrole, created = UserRole.objects.get_or_create(user=user, group=invite.group, organization=invite.organization, project=invite.project, site=invite.site)
            invite.is_used = True
            invite.save()

        if invite.group.name == "Organization Admin":
            noti_type = 1
            content = invite.organization
        elif invite.group.name == "Project Manager":
            noti_type = 2
            content = invite.project
        elif invite.group.name == "Reviewer":
            noti_type = 3
            content = invite.site
        elif invite.group.name == "Site Supervisor":
            noti_type = 4
            content = invite.site
        elif invite.group.name == "Unassigned":
            noti_type = 24
            if invite.site:
                content = invite.site
            elif invite.project:
                content = invite.project
            else:   
                content = invite.organization
        elif invite.group.name == "Project Donor":
            noti_type = 25
            content = invite.project
        
        noti = invite.logs.create(source=user, type=noti_type, title="new Role",
                                       organization=invite.organization, project=invite.project, site=invite.site, content_object=content, extra_object=invite.by_user,
                                       description="{0} was added as the {1} of {2} by {3}.".
                                       format(user.username, invite.group.name, content.name, invite.by_user ))
        # result = {}
        # result['description'] = 'new site {0} deleted by {1}'.format(self.object.name, self.request.user.username)
        # result['url'] = noti.get_absolute_url()
        # ChannelGroup("notify-{}".format(self.object.project.organization.id)).send({"text": json.dumps(result)})
        # ChannelGroup("notify-0").send({"text": json.dumps(result)})
        return HttpResponseRedirect(reverse('login'))
            
@login_required()
def checkemailforinvite(request):
    user = User.objects.select_related('user_profile').filter(email__icontains=request.POST.get('email'))
    if user:
        return render(request, 'fieldsight/invite_response.html', {'users': user,})
    else:
        return HttpResponse("No existing User found.<a href='#' onclick='sendnewuserinvite()'>send</a>")

def checkusernameexists(request):
    user = User.objects.get(username=request.POST.get('email'))
    if user:
        return render(request, 'fieldsight/invite_response.html', {'users': user,})
    else:
        return HttpResponse("No existing User found.<a href='#' onclick='sendnewuserinvite()'>send</a>")


class ProjectSummaryReport(LoginRequiredMixin, ProjectRoleMixin, TemplateView):
    def get(self, request, pk):
        obj = Project.objects.get(pk=self.kwargs.get('pk'))
        organization = Organization.objects.get(pk=obj.organization_id)
        peoples_involved = obj.project_roles.filter(group__name__in=["Project Manager", "Reviewer"]).distinct('user')
        project_managers = obj.project_roles.select_related('user').filter(group__name__in=["Project Manager"]).distinct('user')

        sites = obj.sites.filter(is_active=True, is_survey=False)
        data = serialize('custom_geojson', sites, geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone','id',))

        total_sites = len(sites)
        total_survey_sites = obj.sites.filter(is_survey=True).count()
        outstanding, flagged, approved, rejected = obj.get_submissions_count()
        bar_graph = BarGenerator(sites)

        line_chart = LineChartGenerator(obj)
        line_chart_data = line_chart.data()
        dashboard_data = {
            'sites': sites,
            'obj': obj,
            'peoples_involved': peoples_involved,
            'total_sites': total_sites,
            'total_survey_sites': total_survey_sites,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
            'progress_data': bar_graph.data.values(),
            'progress_labels': bar_graph.data.keys(),
            'project_managers':project_managers,
            'organization': organization,
            'total_submissions': line_chart_data.values()[-1],
    
        }
        return render(request, 'fieldsight/project_individual_submission_report.html', dashboard_data)


class SiteSummaryReport(LoginRequiredMixin, TemplateView):

    def get(self, request, **kwargs):
        obj = Site.objects.get(pk=self.kwargs.get('pk'))
        project = Project.objects.get(pk=obj.project_id)
        peoples_involved = obj.site_roles.filter(ended_at__isnull=True).distinct('user')
        data = serialize('custom_geojson', [obj], geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))
        supervisor = obj.site_roles.select_related('user').filter(group__name__in=["Site Supervisor"]).distinct('user')
        reviewer = obj.site_roles.select_related('user').filter(group__name__in=["Reviewer"]).distinct('user')
        line_chart = LineChartGeneratorSite(obj)
        line_chart_data = line_chart.data()

        outstanding, flagged, approved, rejected = obj.get_site_submission()

        dashboard_data = {
            'obj': obj,
            'peoples_involved': peoples_involved,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
            'project': project,
            'supervisor' : supervisor,
            'reviewer' : reviewer,
            'total_submissions': line_chart_data.values()[-1],

        }
        return render(request, 'fieldsight/site_individual_submission_report.html', dashboard_data)


class MultiUserAssignSiteView(ProjectRoleMixin, TemplateView):
    def get(self, request, pk):
        project_obj = Project.objects.get(pk=pk)
        return render(request, 'fieldsight/multi_user_assign.html',{'type': "site", 'pk':pk})

    def post(self, request, pk, *args, **kwargs):
        data = json.loads(self.request.body)
        sites = data.get('sites')
        users = data.get('users')
        group = Group.objects.get(name=data.get('group'))
        user = request.user
        task = multiuserassignsite.delay(user, pk, sites, users, group.id)
        if CeleryTaskProgress.objects.create(task_id=task.id, user=user, task_type=2):
            return HttpResponse('sucess')
        else:
            return HttpResponse('Failed')
# if(Group="Reviewer or Site Supervisor") and request.user not in test
# return reverse redirect login
# if(Gropp="Project Manager")and not in request.user not in test
# return reverse redirect login

# class MultiUserAssignSiteView(ProjectRoleMixin, TemplateView):
#     def get(self, request, pk):
#         project_obj = Project.objects.get(pk=pk)
#         return render(request, 'fieldsight/multi_user_assign.html',{'type': "site", 'pk':pk})

#     def post(self, request, *args, **kwargs):
#         data = json.loads(self.request.body)
#         sites = data.get('sites')
#         users = data.get('users')
#         group = Group.objects.get(name=data.get('group'))
#         response = ""
#         for site_id in sites:
#             site = Site.objects.get(pk=site_id)
#             for user in users:
              
#                 role, created = UserRole.objects.get_or_create(user_id=user, site_id=site.id,
#                                                                project__id=site.project.id, organization__id=site.project.organization_id, group=group, ended_at=None)
#                 if created:
               
#                     # description = "{0} was assigned  as {1} in {2}".format(
#                     #     role.user.get_full_name(), role.lgroup.name, role.project)
#                     noti_type = 8

#                     # if data.get('group') == "Reviewer":
#                     #     noti_type =7
                    
#                     # noti = role.logs.create(source=role.user, type=noti_type, title=description,
#                     #                         description=description, content_type=site, extra_object=self.request.user,
#                     #                         site=role.site)
#                     # result = {}
#                     # result['description'] = description
#                     # result['url'] = noti.get_absolute_url()
#                     # ChannelGroup("notify-{}".format(role.organization.id)).send({"text": json.dumps(result)})
#                     # ChannelGroup("project-{}".format(role.project.id)).send({"text": json.dumps(result)})
#                     # ChannelGroup("site-{}".format(role.site.id)).send({"text": json.dumps(result)})
#                     # ChannelGroup("notify-0").send({"text": json.dumps(result)})

#                     # Device = get_device_model()
#                     # if Device.objects.filter(name=role.user.email).exists():
#                     #     message = {'notify_type':'Assign Site', 'site':{'name': site.name, 'id': site.id}}
#                     #     Device.objects.filter(name=role.user.email).send_message(message)
#                 else:
#                     response += "Already exists."
#         return HttpResponse(response)



class MultiUserAssignProjectView(OrganizationRoleMixin, TemplateView):

    def post(self, request, pk, *args, **kwargs):
        data = json.loads(self.request.body)
        projects = data.get('projects')
        users = data.get('users')
        group = Group.objects.get(name=data.get('group'))
        group_id = Group.objects.get(name="Project Manager").id
        user = request.user
        task = multiuserassignproject.delay(user, pk, projects, users, group_id)
        if CeleryTaskProgress.objects.create(task_id=task.id, user=user, task_type=1):
            return HttpResponse("Sucess")
        else:
            return HttpResponse("Failed")


#May need it
# class MultiUserAssignProjectView(OrganizationRoleMixin, TemplateView):
#     def get(self, request, pk):
#         org_obj = Organization.objects.get(pk=pk)
#         return render(request, 'fieldsight/multi_user_assign.html',{'type': "project", 'pk':pk})

#     def post(self, request, *args, **kwargs):
#         data = json.loads(self.request.body)
#         projects = data.get('projects')
#         users = data.get('users')
     

#         group = Group.objects.get(name="Project Manager")
#         for project_id in projects:
#             project = Project.objects.get(pk=project_id)
#             for user in users:
#                 role, created = UserRole.objects.get_or_create(user_id=user, project_id=project_id,
#                                                                organization__id=project.organization.id,
#                                                                project__id=project_id,
#                                                                group=group, ended_at=None)
#                 if created:
#                     description = "{0} was assigned  as Project Manager in {1}".format(
#                         role.user.get_full_name(), role.project)
#                     noti = role.logs.create(source=role.user, type=6, title=description, description=description,
#                      content_object=role.project, extra_object=self.request.user)
#                     result = {}
#                     result['description'] = description
#                     result['url'] = noti.get_absolute_url()
#                     ChannelGroup("notify-{}".format(role.organization.id)).send({"text": json.dumps(result)})
#                     ChannelGroup("project-{}".format(role.project.id)).send({"text": json.dumps(result)})
#                     ChannelGroup("notify-0").send({"text": json.dumps(result)})
#         return HttpResponse("Sucess")


def viewfullmap(request):
    data = serialize('full_detail_geojson',
                     Site.objects.prefetch_related('site_instances').filter(is_survey=False, is_active=True),
                     geometry_field='location',
                     fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))

    dashboard_data = {

        'data': data,
    }
    return render(request, 'fieldsight/map.html', dashboard_data)


class OrgFullmap(LoginRequiredMixin, OrganizationRoleMixin, TemplateView):
    template_name = "fieldsight/map.html"
    def get_context_data(self, **kwargs):
        obj = Organization.objects.get(pk=self.kwargs.get('pk'))
        sites = Site.objects.filter(project__organization=obj,is_survey=False, is_active=True)

        data = serialize('full_detail_geojson', sites, geometry_field='location',
               fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))
        dashboard_data = {
           'data': data,
        }
        return dashboard_data


class ProjFullmap(ProjectRoleMixin, TemplateView):
    template_name = "fieldsight/map.html"
    def get_context_data(self, **kwargs):
        obj = Project.objects.get(pk=self.kwargs.get('pk'))
        sites = obj.sites.filter(is_active=True, is_survey=False)
        data = serialize('full_detail_geojson', sites, geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id',))
        dashboard_data = {
            'data': data,
        }
        return dashboard_data

class SiteFullmap(ReviewerRoleMixin, TemplateView):
    template_name = "fieldsight/map.html"

    def get_context_data(self, **kwargs):
        obj = Site.objects.get(pk=self.kwargs.get('pk'))
        data = serialize('full_detail_geojson', [obj], geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))
        dashboard_data = {

            'data': data,
        }
        return dashboard_data


class OrganizationdataSubmissionView(TemplateView):
    template_name = "fieldsight/organizationdata_submission.html"

    def get_context_data(self, **kwargs):
        data = super(OrganizationdataSubmissionView, self).get_context_data(**kwargs)
        data['obj'] = Organization.objects.get(pk=self.kwargs.get('pk'))
        data['pending'] = FInstance.objects.filter(project__organization=self.kwargs.get('pk'), form_status='0').order_by('-date')
        data['rejected'] = FInstance.objects.filter(project__organization=self.kwargs.get('pk'), form_status='1').order_by('-date')
        data['flagged'] = FInstance.objects.filter(project__organization=self.kwargs.get('pk'), form_status='2').order_by('-date')
        data['approved'] = FInstance.objects.filter(project__organization=self.kwargs.get('pk'), form_status='3').order_by('-date')
        data['type'] = self.kwargs.get('type')

        return data


class ProjectdataSubmissionView(ReadonlyProjectLevelRoleMixin, TemplateView):
    template_name = "fieldsight/projectdata_submission.html"

    def get_context_data(self, **kwargs):
        data = super(ProjectdataSubmissionView, self).get_context_data(**kwargs)
        data['obj'] = Project.objects.get(pk=self.kwargs.get('pk'))
        data['pending'] = FInstance.objects.filter(project_id=self.kwargs.get('pk'), project_fxf_id__isnull=False, form_status='0').order_by('-date')
        data['rejected'] = FInstance.objects.filter(project_id=self.kwargs.get('pk'), project_fxf_id__isnull=False, form_status='1').order_by('-date')
        data['flagged'] = FInstance.objects.filter(project_id=self.kwargs.get('pk'), project_fxf_id__isnull=False, form_status='2').order_by('-date')
        data['approved'] = FInstance.objects.filter(project_id=self.kwargs.get('pk'), project_fxf_id__isnull=False, form_status='3').order_by('-date')
        data['type'] = self.kwargs.get('type')

        return data


class SitedataSubmissionView(ReadonlySiteLevelRoleMixin, TemplateView):
    template_name = "fieldsight/sitedata_submission.html"

    def get_context_data(self, **kwargs):
        data = super(SitedataSubmissionView, self).get_context_data(**kwargs)
        data['obj'] = Site.objects.get(pk=self.kwargs.get('pk'))
        data['pending'] = FInstance.objects.filter(site_id = self.kwargs.get('pk'), site_fxf_id__isnull=False, form_status = '0').order_by('-date')
        data['rejected'] = FInstance.objects.filter(site_id = self.kwargs.get('pk'), site_fxf_id__isnull=False, form_status = '1').order_by('-date')
        data['flagged'] = FInstance.objects.filter(site_id = self.kwargs.get('pk'), site_fxf_id__isnull=False, form_status = '2').order_by('-date')
        data['approved'] = FInstance.objects.filter(site_id = self.kwargs.get('pk'), site_fxf_id__isnull=False, form_status = '3').order_by('-date')
        data['type'] = self.kwargs.get('type')

        return data



class RegionView(object):
    model = Region
    success_url = reverse_lazy('fieldsight:region-list')
    form_class = RegionForm

class RegionListView(RegionView, LoginRequiredMixin, ListView):
    def get_context_data(self, **kwargs):
        context = super(RegionListView, self).get_context_data(**kwargs)
        project = Project.objects.get(pk=self.kwargs.get('pk'))
        context['project'] = project
        context['pk'] = self.kwargs.get('pk')
        context['type'] = "region"
        return context

    def get_queryset(self):
        queryset = Region.objects.filter(project_id=self.kwargs.get('pk'), is_active=True)
        return queryset


class RegionCreateView(RegionView, LoginRequiredMixin, CreateView):

    def get_context_data(self, **kwargs):
        context = super(RegionCreateView, self).get_context_data(**kwargs)
        project = Project.objects.get(pk=self.kwargs.get('pk'))
        context['project'] = project
        context['pk'] = self.kwargs.get('pk')
        context['json_questions'] = json.dumps(project.site_meta_attributes)
        return context

    def form_valid(self, form):
        # print form.cleaned_data['identifier']
        self.object = form.save(commit=False)
        self.object.project_id=self.kwargs.get('pk')
        existing_identifier = Region.objects.filter(identifier=form.cleaned_data.get('identifier'))
        if existing_identifier:
            messages.add_message(self.request, messages.INFO, 'Your identifier conflict with existing region please use different identifier to create region')
            return HttpResponseRedirect(reverse('fieldsight:region-add', kwargs={'pk': self.kwargs.get('pk')}))
        else:
            self.object.save()
            messages.add_message(self.request, messages.INFO, 'Sucessfully new region is created')
            return HttpResponseRedirect(self.get_success_url())
        return HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('fieldsight:region-list', kwargs={'pk': self.kwargs.get('pk')})


class RegionDeleteView(RegionView, DeleteView):
    def dispatch(self, request, *args, **kwargs):
        site = Site.objects.filter(region_id=self.kwargs.get('pk'))
        site.update(region_id=None)
        return super(RegionDeleteView, self).dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse('fieldsight:region-list', kwargs={'pk': self.object.project.id})


# class RegionDeactivateView(View):
#
#     def get(self, request, pk, *args, **kwargs):
#         region = Region.objects.get(pk=pk)
#         project_id = region.project.id
#         site=Site.objects.filter(region_id=self.kwargs.get('pk'))
#         site.update(region=None)
#         region.is_active = False
#         region.save()
#
#         return HttpResponseRedirect(reverse('fieldsight:project-dashboard', kwargs={'pk':region.project.id}))


class RegionUpdateView(RegionView, LoginRequiredMixin, UpdateView):

    def get_context_data(self, **kwargs):
        context = super(RegionUpdateView, self).get_context_data(**kwargs)
        region = Region.objects.get(pk=self.kwargs.get('pk'))
        context['project'] = region.project
        context['pk'] = self.kwargs.get('pk')
        return context

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.save()
        return HttpResponseRedirect(reverse('fieldsight:project-dashboard', kwargs={'pk':self.object.project.id}))




class RegionalSitelist(ProjectRoleMixin, TemplateView):
    def get(self, request, *args, **kwargs):
        if self.kwargs.get('region_pk') == "0":
            return render(request, 'fieldsight/site_list.html',{'project_id':self.kwargs.get('pk'),'type':"Unregioned",'pk':self.kwargs.get('region_pk'),})

        obj = get_object_or_404(Region, id=self.kwargs.get('region_pk'))
        return render(request, 'fieldsight/site_list.html',{'obj':obj, 'type':"region",'pk':self.kwargs.get('region_pk'),})


class RegionalSiteCreateView(SiteView, ProjectRoleMixin, CreateView):
    def get_context_data(self, **kwargs):
        context = super(RegionalSiteCreateView, self).get_context_data(**kwargs)
        project =Project.objects.get(pk=self.kwargs.get('pk'))
        context['project'] = project
        context['json_questions'] = json.dumps(project.site_meta_attributes)
        context['pk'] = self.kwargs.get('pk')
        return context

    def get_success_url(self):
        return reverse('fieldsight:site-dashboard', kwargs={'pk': self.object.id})

    def form_valid(self, form):
        self.object = form.save(project_id=self.kwargs.get('pk'), region_id=self.kwargs.get('region_pk'), new=True)
        noti = self.object.logs.create(source=self.request.user, type=11, title="new Site",
                                       organization=self.object.project.organization,
                                       project=self.object.project, content_object=self.object, extra_object=self.object.project,
                                       description='{0} created a new site named {1} in {2}'.format(self.request.user.get_full_name(),
                                                                                 self.object.name, self.object.project.name))
        result = {}
        result['description'] = '{0} created a new site named {1} in {2}'.format(self.request.user.get_full_name(),
                                                                                 self.object.name, self.object.project.name)
        result['url'] = noti.get_absolute_url()
        ChannelGroup("project-{}".format(self.object.project.id)).send({"text": json.dumps(result)})
        # ChannelGroup("notify-0").send({"text": json.dumps(result)})

        return HttpResponseRedirect(self.get_success_url())


class MultiUserAssignRegionView(ProjectRoleMixin, TemplateView):
    def get(self, request, pk):
        project_obj = Project.objects.get(pk=pk)
        return render(request, 'fieldsight/multi_user_assign.html',{'type': "site", 'pk':pk})

    def post(self, request, pk, *args, **kwargs):
        data = json.loads(self.request.body)
        regions = data.get('regions')
        users = data.get('users')
        group = Group.objects.get(name=data.get('group'))
        user = request.user
        task = multiuserassignregion.delay(user, pk, regions, users, group.id)
        if CeleryTaskProgress.objects.create(task_id=task.id, user=user, task_type=2):
            return HttpResponse('sucess')
        else:
            return HttpResponse('Failed')


def project_html_export(request, pk):
    
    # site_responses_report(forms)
    # # data = {}
    # # for fsxf in forms:
    # #     data['form_detail'] = fsxf
    # #     xform = fsxf.xf
    # #     id_string = xform.id_string
    # #     data['form_responces'] = get_instances_for_project_field_sight_form(fsxf_id)
    # forms = Organization.objects.all()
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="My Users.pdf"'
    base_url = request.get_host()
    report = MyPrint(buffer, 'Letter')
    pdf = report.print_users(pk, base_url)

    buffer.seek(0)

    #     with open('arquivo.pdf', 'wb') as f:
    #         f.write()
    response.write(buffer.read())

    # Get the value of the BytesIO buffer and write it to the response.
    pdf = buffer.getvalue()
    buffer.close()

    return response

class OrganizationSearchView(ListView):
    model = Organization
    template_name = 'fieldsight/organization_list.html'

    def get_queryset(self):
        query = self.request.GET.get("q")
        return self.model.objects.filter(name__icontains=query)


class ProjectSearchView(ListView):
    model = Project
    template_name = 'fieldsight/project_list.html'

    def get_context_data(self, **kwargs):
        context = super(ProjectSearchView, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['type'] = "project"
        return context

    def get_queryset(self):
        query = self.request.GET.get("q")
        return self.model.objects.filter(name__icontains=query)

class OrganizationUserSearchView(ListView):
    model = UserRole
    template_name = "fieldsight/user_list_updated.html"

    def get_context_data(self, **kwargs):
        context = super(OrganizationUserSearchView, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        return context

    def get_queryset(self):
        query = self.request.GET.get("q")
        return self.model.objects.filter(user__username__icontains=query, organization_id=self.kwargs.get('pk'),project__isnull=True, site__isnull=True).distinct('user')
        return queryset

class ProjectUserSearchView(ListView):
    model = UserRole
    template_name = "fieldsight/user_list_updated.html"

    def get_context_data(self, **kwargs):
        context = super(ProjectUserSearchView, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['obj'] = Project.objects.get(pk=self.kwargs.get('pk'))
        context['organization_id'] = Project.objects.get(pk=self.kwargs.get('pk')).organization.id
        context['type'] = "project"
        return context

    def get_queryset(self):
        query = self.request.GET.get("q")
        return self.model.objects.select_related('user').filter(user__username__icontains=query, project_id=self.kwargs.get('pk'),
                                                                  ended_at__isnull=True).distinct('user_id')

class SiteUserSearchView(ListView):
    model = UserRole
    template_name = "fieldsight/user_list_updated.html"

    def get_queryset(self):
        queryset = UserRole.objects.select_related('user').filter(site_id=self.kwargs.get('pk'),
                                                                  ended_at__isnull=True).distinct('user_id')

        return queryset
    def get_context_data(self, **kwargs):
        context = super(SiteUserSearchView, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['obj'] = Site.objects.get(pk=self.kwargs.get('pk'))
        context['organization_id'] = Site.objects.get(pk=self.kwargs.get('pk')).project.organization.id
        context['type'] = "site"
        return context

    def get_queryset(self):
        query = self.request.GET.get("q")
        return self.model.objects.select_related('user').filter(user__username__icontains=query, site_id=self.kwargs.get('pk'),
                                                                  ended_at__isnull=True).distinct('user_id')

class DefineProjectSiteMeta(ProjectRoleMixin, TemplateView):
    def get(self, request, pk):
        project_obj = Project.objects.get(pk=pk)
        json_questions = json.dumps(project_obj.site_meta_attributes)
        return render(request, 'fieldsight/project_define_site_meta.html', {'obj': project_obj, 'json_questions': json_questions,})

    def post(self, request, pk, *args, **kwargs):
        project = Project.objects.get(pk=pk)
        project.site_meta_attributes = request.POST.get('json_questions');
        project.save()
        return HttpResponseRedirect(reverse('fieldsight:project-dashboard', kwargs={'pk': self.kwargs.get('pk')}))


class SiteMetaForm(ReviewerRoleMixin, TemplateView):
    def get(self, request, pk):
        site_obj = Site.objects.get(pk=pk)
        json_answers = json.dumps(site_obj.site_meta_attributes_ans)
        json_questions = json.dumps(site_obj.project.site_meta_attributes)
        return render(request, 'fieldsight/site_meta_form.html', {'obj': site_obj, 'json_questions': json_questions, 'json_answers': json_answers})

    def post(self, request, pk, *args, **kwargs):
        project = Project.objects.get(pk=pk)
        project.site_meta_attributes = request.POST.get('json_questions');
        project.save()
        return HttpResponseRedirect(reverse('fieldsight:project-dashboard', kwargs={'pk': self.kwargs.get('pk')}))

class MultiSiteAssignRegionView(ProjectRoleMixin, TemplateView):
    def get(self, request, pk):
        project = Project.objects.get(pk=pk)

        if project.cluster_sites is False:
            raise PermissionDenied()

        return render(request, 'fieldsight/multi_site_assign_region.html', {'project':project})

    def post(self, request, pk, *args, **kwargs):
        data = json.loads(self.request.body)
        region = data.get('region')
        sites = data.get('sites')
        if len(region) == 0:
            sitetoassign = Site.objects.filter(pk__in=sites)
            sitetoassign.update(region=None)
        else:        
            sitetoassign = Site.objects.filter(pk__in=sites)
            sitetoassign.update(region_id=region[0])

        return HttpResponse("Success")

class ExcelBulkSiteSample(ProjectRoleMixin, View):
    def get(self, request, pk):
        project = Project.objects.get(pk=pk)
        response = HttpResponse(content_type='application/ms-excel')
        response['Content-Disposition'] = 'attachment; filename="bulk_upload_sites.xls"'

        wb = xlwt.Workbook(encoding='utf-8')
        ws = wb.add_sheet('Sites')

        # Sheet header, first row
        row_num = 0

        font_style = xlwt.XFStyle()
        font_style.font.bold = True

        columns = ['id', 'name', 'type', 'phone', 'address', 'public_desc', 'additional_desc', 'latitude', 'longitude',]
        if project.cluster_sites:
            columns += ['region_id',]
        meta_ques = project.site_meta_attributes
        for question in meta_ques:
            columns += [question['question_name']]
        for col_num in range(len(columns)):
            ws.write(row_num, col_num, columns[col_num], font_style)

        # Sheet body, remaining rows
        font_style = xlwt.XFStyle()

        wb.save(response)
        return response

class ProjectSearchView(ListView):
    model = Project
    template_name = 'fieldsight/project_list.html'

    def get_context_data(self, **kwargs):
        context = super(ProjectSearchView, self).get_context_data(**kwargs)
        context['pk'] = self.kwargs.get('pk')
        context['type'] = "project"
        return context

    def get_queryset(self):
        query = self.request.REQUEST.get("q")
        return self.model.objects.filter(name__icontains=query)

class ProjectStageResponsesStatus(ProjectRoleMixin, View): 
    def get(self, request, pk):
            data = []
            ss_index = {}
            stages_rows = []
            head_row = ["Site ID", "Name"]
            obj = get_object_or_404(Project, pk=pk)
            project = Project.objects.get(pk=pk)

            stages = project.stages.filter(stage__isnull=True)
            
            table_head = []
            substages =[]
            table_head.append({"name":"Site Id", "rowspan":2, "colspan":1 })
            table_head.append({"name":"Site Name", "rowspan":2, "colspan":1 })
            
            for stage in stages:
                sub_stages = stage.parent.all()
                if len(sub_stages) > 0:
                    stages_rows.append("Stage :"+stage.name)
                    table_head.append({"name":stage.name, "rowspan":1, "colspan":len(sub_stages) })

                    for ss in sub_stages:
                        head_row.append("Sub Stage :"+ss.name)
                        ss_index.update({head_row.index("Sub Stage :"+ss.name): ss.id})
                        substages.append(ss.name)

            

            # data.append(head_row)
            def filterbyvalue(seq, value):
                for el in seq:
                    if el.project_stage_id==value: yield el

            def getStatus(el):
                if el is not None and el.form_status==3: return "Approved"
                elif el is not None and el.form_status==2: return "Flagged"
                elif el is not None and el.form_status==1: return "Rejected"
                else: return "Pending"
            keyword = self.request.GET.get("q", None)
            if keyword is not None:
                site_list = project.sites.filter(name__icontains=keyword, is_active=True, is_survey=False).prefetch_related(Prefetch('stages__stage_forms__site_form_instances', queryset=FInstance.objects.order_by('-id')))
                get_params = "?q="+keyword +"&page="
            else:
                site_list = project.sites.filter(is_active=True, is_survey=False).prefetch_related(Prefetch('stages__stage_forms__site_form_instances', queryset=FInstance.objects.order_by('-id')))    
                get_params = "?page="
            paginator = Paginator(site_list, 15) # Show 25 contacts per page
            page = request.GET.get('page')
            try:
                sites = paginator.page(page)
            except PageNotAnInteger:
                # If page is not an integer, deliver first page.
                sites = paginator.page(1)
            except EmptyPage:
            # If page is out of range (e.g. 9999), deliver last page of results.
                sites = paginator.page(paginator.num_pages)
            for site in sites:
                site_row = [site.identifier, site.name]
                for k, v in ss_index.items():
                    substage = filterbyvalue(site.stages.all(), v)
                    substage1 = next(substage, None)
                    if substage1 is not None:
                        if  substage1.stage_forms.site_form_instances.all():
                             get_status = getStatus(substage1.stage_forms.site_form_instances.all()[0])
                             status = get_status
                        else:
                            status = "No submission."
                    else:
                         status = "-"
                    site_row.append(status)
                data.append(site_row)

            if sites.has_next():
                has_next = sites.next_page_number()
            else:
                has_next = None
            if has_next:
                next_page_url = request.build_absolute_uri(reverse('fieldsight:ProjectStageResponsesStatus', kwargs={'pk': pk})) + get_params + str(has_next)
            else:
                next_page_url =  None
            content={'head_cols':table_head, 'sub_stages':substages, 'rows':data}
            main_body = {'next_page':next_page_url,'content':content}
            return HttpResponse(json.dumps(main_body), status=200)

class StageTemplateView(ReadonlyProjectLevelRoleMixin, View):
    def get(self, request, pk):
        obj = Project.objects.get(pk=pk)
        return render(request, 'fieldsight/ProjectStageResponsesStatus.html', {'obj':obj,})
            # return HttpResponse(table_head)\

def response_export(request, pk):
    
    buffer = BytesIO()
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Report.pdf"'
    base_url = request.get_host()
    report = MyPrint(buffer, 'Letter')
    pdf = report.print_individual_response(pk, base_url)

    buffer.seek(0)

    #     with open('arquivo.pdf', 'wb') as f:
    #         f.write()
    response.write(buffer.read())

    # Get the value of the BytesIO buffer and write it to the response.
    pdf = buffer.getvalue()
    buffer.close()

    return response

class FormlistAPI(View):
    def get(self, request, pk):
        mainstage=[]
        schedule = FieldSightXF.objects.filter(site_id=pk, is_scheduled = True, is_staged=False, is_survey=False).values('id','xf__title')
        stages = Stage.objects.filter(site_id=pk)
        for stage in stages:
            if stage.stage_id is None:
                substages=stage.get_sub_stage_list()
                main_stage = {'id':stage.id, 'title':stage.name, 'sub_stages':list(substages)}
                # stagegroup = {'main_stage':main_stage,}
                mainstage.append(main_stage)

        survey = FieldSightXF.objects.filter(site_id=pk, is_scheduled = False, is_staged=False, is_survey=True).values('id','xf__title')
        general = FieldSightXF.objects.filter(site_id=pk, is_scheduled = False, is_staged=False, is_survey=False).values('id','xf__title')
        content={'general':list(general), 'schedule':list(schedule), 'stage':list(mainstage), 'survey':list(survey)}
        return HttpResponse(json.dumps(content, cls=DjangoJSONEncoder, ensure_ascii=False).encode('utf8'), status=200)

    def post(self, request, pk, **kwargs):
        buffer = BytesIO()
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="Report.pdf"'
        base_url = request.get_host()
        report = MyPrint(buffer, 'Letter')
        data = json.loads(self.request.body)
        fs_ids = data.get('fs_ids')
        pdf = report.generateCustomSiteReport(pk, base_url,fs_ids)
        buffer.seek(0)
        pdf = buffer.getvalue()
        file = open("media/contract.pdf", "wb")
        file.write(pdf)
        response.write(pdf)
        buffer.close()
        return response

class GenerateCustomReport(ReviewerRoleMixin, View):
    def get(self, request, pk):
        schedule = FieldSightXF.objects.filter(site_id=pk, is_scheduled = True, is_staged=False, is_survey=False).values('id','xf__title','date_created')
        stage = FieldSightXF.objects.filter(site_id=pk, is_scheduled = False, is_staged=True, is_survey=False).values('id','xf__title','date_created')
        survey = FieldSightXF.objects.filter(site_id=pk, is_scheduled = False, is_staged=False, is_survey=True).values('id','xf__title','date_created')
        general = FieldSightXF.objects.filter(site_id=pk, is_scheduled = False, is_staged=False, is_survey=False).values('id','xf__title','date_created')
        content={'general':list(general), 'schedule':list(schedule), 'stage':list(stage), 'survey':list(survey)}
        return HttpResponse(json.dumps(content, cls=DjangoJSONEncoder, ensure_ascii=False).encode('utf8'), status=200)

class RecentResponseImages(ReviewerRoleMixin, View):
    def get(self, request, pk):
        recent_resp_imgs = get_images_for_site(pk)
        content={'images':list(recent_resp_imgs)}
        return HttpResponse(json.dumps(content, cls=DjangoJSONEncoder, ensure_ascii=False).encode('utf8'), status=200)

class SiteResponseCoordinates(ReviewerRoleMixin, View):
    def get(self, request, pk):
        coord_datas = get_site_responses_coords(pk)
        obj = Site.objects.get(pk=self.kwargs.get('pk'))
        return render(request, 'fieldsight/site_response_map_view.html', {'co_ords':json.dumps(list(coord_datas["result"]), cls=DjangoJSONEncoder, ensure_ascii=False).encode('utf8')})

    def post(self, request, pk):
        coord_datas = get_site_responses_coords(pk)
        content={'coords-data':list(coord_datas["result"])}
        return HttpResponse(json.dumps(content, cls=DjangoJSONEncoder, ensure_ascii=False).encode('utf8'), status=200)

class DonorProjectDashboard(DonorRoleMixin, TemplateView):
    template_name = "fieldsight/donor_project_dashboard.html"
    
    def get_context_data(self, **kwargs):
        dashboard_data = super(DonorProjectDashboard, self).get_context_data(**kwargs)
        obj = Project.objects.get(pk=self.kwargs.get('pk'))

        peoples_involved = obj.project_roles.filter(ended_at__isnull=True).distinct('user')
        total_sites = obj.sites.filter(is_active=True, is_survey=False).count()
        sites = obj.sites.filter(is_active=True, is_survey=False)
        data = serialize('custom_geojson', sites, geometry_field='location',
                         fields=('location', 'id',))

        total_sites = sites.count()
        total_survey_sites = obj.sites.filter(is_survey=True).count()
        outstanding, flagged, approved, rejected = obj.get_submissions_count()
        bar_graph = BarGenerator(sites)
        line_chart = LineChartGenerator(obj)
        line_chart_data = line_chart.data()
        roles_project = UserRole.objects.filter(organization__isnull = False, project_id = self.kwargs.get('pk'), site__isnull = True, ended_at__isnull=True)

        dashboard_data = {
            'sites': sites,
            'obj': obj,
            'peoples_involved': peoples_involved,
            'total_sites': total_sites,
            'total_survey_sites': total_survey_sites,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
            'progress_data': bar_graph.data.values(),
            'progress_labels': bar_graph.data.keys(),
            'roles_project': roles_project,
    }
        return dashboard_data

class DonorSiteDashboard(DonorSiteViewRoleMixin, TemplateView):
    template_name = 'fieldsight/donor_site_dashboard.html'

    def get_context_data(self, **kwargs):
        dashboard_data = super(DonorSiteDashboard, self).get_context_data(**kwargs)
        obj = Site.objects.get(pk=self.kwargs.get('pk'))
        peoples_involved = obj.site_roles.filter(ended_at__isnull=True).distinct('user')
        data = serialize('custom_geojson', [obj], geometry_field='location',
                         fields=('name', 'public_desc', 'additional_desc', 'address', 'location', 'phone', 'id'))

        line_chart = LineChartGeneratorSite(obj)
        line_chart_data = line_chart.data()
        progress_chart = ProgressGeneratorSite(obj)
        progress_chart_data = progress_chart.data()
        meta_questions = obj.project.site_meta_attributes
        meta_answers = obj.site_meta_attributes_ans
        mylist =[]
        for question in meta_questions:
            if question['question_name'] in meta_answers:
                mylist.append({question['question_text'] : meta_answers[question['question_name']]})
        myanswers = mylist
        outstanding, flagged, approved, rejected = obj.get_site_submission()
        dashboard_data = {
            'obj': obj,
            'peoples_involved': peoples_involved,
            'outstanding': outstanding,
            'flagged': flagged,
            'approved': approved,
            'rejected': rejected,
            'data': data,
            'cumulative_data': line_chart_data.values(),
            'cumulative_labels': line_chart_data.keys(),
            'progress_chart_data_data': progress_chart_data.keys(),
            'progress_chart_data_labels': progress_chart_data.values(),
            'meta_data': myanswers,
        }
        return dashboard_data
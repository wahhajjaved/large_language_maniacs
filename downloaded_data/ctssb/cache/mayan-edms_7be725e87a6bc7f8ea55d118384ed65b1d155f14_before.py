import zipfile

from django.utils.translation import ugettext as _
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.contrib import messages
from django.views.generic.list_detail import object_detail, object_list
from django.core.urlresolvers import reverse
from django.views.generic.create_update import create_object, delete_object, update_object
from django.core.files.base import File
from django.conf import settings
from django.utils.http import urlencode
from django.template.defaultfilters import slugify
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile    

from common.utils import pretty_size
from converter.api import convert, in_image_cache, QUALITY_DEFAULT, \
    UnkownConvertError, UnknownFormat
from converter import TRANFORMATION_CHOICES
from filetransfers.api import serve_file
from filesystem_serving.api import document_create_fs_links, document_delete_fs_links
from filesystem_serving.conf.settings import FILESERVING_ENABLE
from ocr.models import add_document_to_queue
from permissions.api import check_permissions


from documents.conf.settings import DELETE_STAGING_FILE_AFTER_UPLOAD
from documents.conf.settings import USE_STAGING_DIRECTORY
from documents.conf.settings import STAGING_FILES_PREVIEW_SIZE
from documents.conf.settings import PREVIEW_SIZE
from documents.conf.settings import THUMBNAIL_SIZE
from documents.conf.settings import GROUP_MAX_RESULTS
from documents.conf.settings import GROUP_SHOW_EMPTY
from documents.conf.settings import GROUP_SHOW_THUMBNAIL
from documents.conf.settings import DEFAULT_TRANSFORMATIONS
from documents.conf.settings import AUTOMATIC_OCR
from documents.conf.settings import UNCOMPRESS_COMPRESSED_LOCAL_FILES
from documents.conf.settings import UNCOMPRESS_COMPRESSED_STAGING_FILES

from documents import PERMISSION_DOCUMENT_CREATE, \
    PERMISSION_DOCUMENT_CREATE, PERMISSION_DOCUMENT_PROPERTIES_EDIT, \
    PERMISSION_DOCUMENT_METADATA_EDIT, PERMISSION_DOCUMENT_VIEW, \
    PERMISSION_DOCUMENT_DELETE, PERMISSION_DOCUMENT_DOWNLOAD, \
    PERMISSION_DOCUMENT_TRANSFORM, PERMISSION_DOCUMENT_TOOLS

from forms import DocumentTypeSelectForm, DocumentCreateWizard, \
        MetadataForm, DocumentForm, DocumentForm_edit, DocumentForm_view, \
        StagingDocumentForm, DocumentTypeMetadataType, DocumentPreviewForm, \
        MetadataFormSet, DocumentPageForm, DocumentPageTransformationForm
   
from metadata import save_metadata, save_metadata_list, decode_metadata_from_url
from models import Document, DocumentMetadata, DocumentType, MetadataType, \
    DocumentPage, DocumentPageTransformation
from staging import StagingFile
from utils import document_save_to_temp_dir


def document_list(request):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_VIEW])
            
    return object_list(
        request,
        queryset=Document.objects.all(),
        template_name='generic_list.html',
        extra_context={
            'title':_(u'documents'),
        },
    )

def document_create(request, multiple=True):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_CREATE])

    if DocumentType.objects.all().count() == 1:
        wizard = DocumentCreateWizard(
            document_type=DocumentType.objects.all()[0],
            form_list=[MetadataFormSet], multiple=multiple,
            step_titles = [
            _(u'document metadata'),
            ])
    else:
        wizard = DocumentCreateWizard(form_list=[DocumentTypeSelectForm, MetadataFormSet], multiple=multiple)
        
    return wizard(request)

def document_create_sibling(request, document_id, multiple=True):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_CREATE])
            
    document = get_object_or_404(Document, pk=document_id)
    urldata = []
    for id, metadata in enumerate(document.documentmetadata_set.all()):
        if hasattr(metadata, 'value'):
            urldata.append(('metadata%s_id' % id, metadata.metadata_type.id))   
            urldata.append(('metadata%s_value' % id, metadata.value))
        
    if multiple:
        view = 'upload_multiple_documents_with_type'
    else:
        view = 'upload_document_with_type'
    
    url = reverse(view, args=[document.document_type.id])
    return HttpResponseRedirect('%s?%s' % (url, urlencode(urldata)))


def _handle_save_document(request, document, form=None):
    if AUTOMATIC_OCR:
        document_queue = add_document_to_queue(document)
        messages.success(request, _(u'Document: %(document)s was added to the OCR queue: %(queue)s.') % {
            'document':document, 'queue':document_queue.label})
    
    if form and 'document_type_available_filenames' in form.cleaned_data:
        if form.cleaned_data['document_type_available_filenames']:
            document.file_filename = form.cleaned_data['document_type_available_filenames'].filename
            document.save()

    save_metadata_list(decode_metadata_from_url(request.GET), document)
    try:
        document_create_fs_links(document)
    except Exception, e:
        messages.error(request, e)


def _handle_zip_file(request, uploaded_file, document_type):
    filename = getattr(uploaded_file, 'filename', getattr(uploaded_file, 'name', ''))
    if filename.lower().endswith('zip'):
        zfobj = zipfile.ZipFile(uploaded_file)
        for filename in zfobj.namelist():
            if not filename.endswith('/'):
                zip_document = Document(file=SimpleUploadedFile(
                    name=filename, content=zfobj.read(filename)),
                    document_type=document_type)
                zip_document.save()
                _handle_save_document(request, zip_document)
                messages.success(request, _(u'Extracted file: %s, uploaded successfully.') % filename)
        #Signal that uploaded file was a zip file
        return True
    else:
        #Otherwise tell parent to handle file
        return False
    

def upload_document_with_type(request, document_type_id, multiple=True):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_CREATE])
            
    document_type = get_object_or_404(DocumentType, pk=document_type_id)
    local_form = DocumentForm(prefix='local', initial={'document_type':document_type})
    if USE_STAGING_DIRECTORY:
        staging_form = StagingDocumentForm(prefix='staging', 
            initial={'document_type':document_type})
    
    if request.method == 'POST':
        if 'local-submit' in request.POST.keys():
            local_form = DocumentForm(request.POST, request.FILES,
                prefix='local', initial={'document_type':document_type})
            if local_form.is_valid():
                try:
                    if (not UNCOMPRESS_COMPRESSED_LOCAL_FILES) or (UNCOMPRESS_COMPRESSED_LOCAL_FILES and not _handle_zip_file(request, request.FILES['local-file'], document_type)):
                        instance = local_form.save()
                        _handle_save_document(request, instance, local_form)
                        messages.success(request, _(u'Document uploaded successfully.'))
                except Exception, e:
                    messages.error(request, e)

                if multiple:
                    return HttpResponseRedirect(request.get_full_path())
                else:
                    return HttpResponseRedirect(reverse('document_list'))
        elif 'staging-submit' in request.POST.keys() and USE_STAGING_DIRECTORY:
            staging_form = StagingDocumentForm(request.POST, request.FILES,
                prefix='staging', initial={'document_type':document_type})
            if staging_form.is_valid():
                try:
                    staging_file = StagingFile.get(staging_form.cleaned_data['staging_file_id'])
                    if (not UNCOMPRESS_COMPRESSED_STAGING_FILES) or (UNCOMPRESS_COMPRESSED_STAGING_FILES and not _handle_zip_file(request, staging_file.upload(), document_type)):
                        document = Document(file=staging_file.upload(), document_type=document_type)
                        document.save()
                        _handle_save_document(request, document, staging_form)
                        messages.success(request, _(u'Staging file: %s, uploaded successfully.') % staging_file.filename)
           
                    if DELETE_STAGING_FILE_AFTER_UPLOAD:
                        staging_file.delete()
                        messages.success(request, _(u'Staging file: %s, deleted successfully.') % staging_file.filename)
                except Exception, e:
                    messages.error(request, e)

                if multiple:
                    return HttpResponseRedirect(request.META['HTTP_REFERER'])
                else:
                    return HttpResponseRedirect(reverse('document_list'))                


    context = {
        'document_type_id':document_type_id,
        'form_list':[
            {
                'form':local_form,
                'title':_(u'upload a local document'),
                'grid':6,
                'grid_clear':False if USE_STAGING_DIRECTORY else True,
            },
        ],
    }
    
    if USE_STAGING_DIRECTORY:
        try:
            filelist = StagingFile.get_all()
        except Exception, e:
            messages.error(request, e)
            filelist = []
        finally:
            context.update({
                'subtemplates_dict':[
                    {
                        'name':'generic_list_subtemplate.html',
                        'title':_(u'files in staging'),
                        'object_list':filelist,
                        'hide_link':True,
                    },
                ],
            })
            context['form_list'].append(
                {
                    'form':staging_form,
                    'title':_(u'upload a document from staging'),
                    'grid':6,
                    'grid_clear':True,   
                },
            )
    
    return render_to_response('generic_form.html', context,
        context_instance=RequestContext(request))
    
def document_view(request, document_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_VIEW])
            
    document = get_object_or_404(Document, pk=document_id)
    form = DocumentForm_view(instance=document, extra_fields=[
        {'label':_(u'Filename'), 'field':'file_filename'},
        {'label':_(u'File extension'), 'field':'file_extension'},
        {'label':_(u'File mimetype'), 'field':'file_mimetype'},
        {'label':_(u'File mime encoding'), 'field':'file_mime_encoding'},
        {'label':_(u'File size'), 'field':lambda x: pretty_size(x.file.storage.size(x.file.path)) if x.exists() else '-'},
        {'label':_(u'Exists in storage'), 'field':'exists'},
        {'label':_(u'Date added'), 'field':lambda x: x.date_added.date()},
        {'label':_(u'Time added'), 'field':lambda x: unicode(x.date_added.time()).split('.')[0]},
        {'label':_(u'Checksum'), 'field':'checksum'},
        {'label':_(u'UUID'), 'field':'uuid'},
        {'label':_(u'Pages'), 'field':lambda x: x.documentpage_set.count()},
    ])

        
    metadata_groups, errors = document.get_metadata_groups()
    if request.user.is_staff and errors:
        for error in errors:
            messages.warning(request, _(u'Metadata group query error: %s' % error))

    preview_form = DocumentPreviewForm(document=document)
    form_list = [
        {
            'form':form,
            'object':document,
            'grid':6,
        },
        {
            'form':preview_form,
            'title':_(u'document preview'),
            'object':document,
            'grid':6,
            'grid_clear':True,
        },
    ]
    subtemplates_dict = [
            {
                'name':'generic_list_subtemplate.html',
                'title':_(u'metadata'),
                'object_list':document.documentmetadata_set.all(),
                'extra_columns':[{'name':_(u'value'), 'attribute':'value'}],
                'hide_link':True,
            },
        ]
    
    if FILESERVING_ENABLE:
        subtemplates_dict.append({
            'name':'generic_list_subtemplate.html',
            'title':_(u'index links'),
            'object_list':document.documentmetadataindex_set.all(),
            'hide_link':True})

    sidebar_groups = []
    for group, data in metadata_groups.items():
        if len(data) or GROUP_SHOW_EMPTY:
            if len(data):
                if len(data) > GROUP_MAX_RESULTS:
                    total_string = '(%s out of %s)' % (GROUP_MAX_RESULTS, len(data))
                else:
                    total_string = '(%s)' % len(data)
            else:
                total_string = ''
              
            extra_columns = [{'name':'current','attribute':lambda x:
                    '<span class="famfam active famfam-resultset_previous"></span>' if x == document else ''}]
                    
            if GROUP_SHOW_THUMBNAIL:
                extra_columns.append({'name':_(u'thumbnail'), 'attribute': 
                        lambda x: '<a class="fancybox" href="%s"><img src="%s" /></a>' % (reverse('document_preview', args=[x.id]),
                        reverse('document_thumbnail', args=[x.id]))})
                
            sidebar_groups.append({
                'title':'%s %s' % (group.label, total_string),
                'name':'generic_list_subtemplate.html',
                'object_list':data[:GROUP_MAX_RESULTS],
                'hide_columns':True,
                'hide_header':True,
                'extra_columns':extra_columns,
                })
            
    return render_to_response('generic_detail.html', {
        'form_list':form_list,
        'object':document,
        'subtemplates_dict':subtemplates_dict,
        'sidebar_subtemplates_dict':sidebar_groups,
    }, context_instance=RequestContext(request))


def document_delete(request, document_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_DELETE])
            
    document = get_object_or_404(Document, pk=document_id)

    previous = request.POST.get('previous', request.GET.get('previous', request.META.get('HTTP_REFERER', None)))

    if request.method == 'POST':
        try:
            document_delete_fs_links(document)
            document.delete()
            messages.success(request, _(u'Document deleted successfully.'))
            return HttpResponseRedirect(reverse('document_list'))
        except Exception, e:
            messages.error(request, _(u'Document delete error: %s') % e)
            return HttpResponseRedirect(previous)
        
    return render_to_response('generic_confirm.html', {
        'object':document,
        'delete_view':True,
        'object_name':_(u'document'),
        'previous':previous,
    }, context_instance=RequestContext(request))
        
        
def document_edit(request, document_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_PROPERTIES_EDIT])
            
    document = get_object_or_404(Document, pk=document_id)
    if request.method == 'POST':
        form = DocumentForm_edit(request.POST, initial={'document_type':document.document_type})
        if form.is_valid():
            try:
                document_delete_fs_links(document)
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(reverse('document_list'))

            document.file_filename = form.cleaned_data['new_filename']

            if 'document_type_available_filenames' in form.cleaned_data:
                if form.cleaned_data['document_type_available_filenames']:
                    document.file_filename = form.cleaned_data['document_type_available_filenames'].filename
                
            document.save()
            
            messages.success(request, _(u'Document %s edited successfully.') % document)
            
            try:
                document_create_fs_links(document)
                messages.success(request, _(u'Document filesystem links updated successfully.'))                
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(document.get_absolute_url())
                
            return HttpResponseRedirect(document.get_absolute_url())
    else:
        form = DocumentForm_edit(instance=document, initial={
            'new_filename':document.file_filename, 'document_type':document.document_type})

    return render_to_response('generic_form.html', {
        'form':form,
        'object':document,
    
    }, context_instance=RequestContext(request))


def document_edit_metadata(request, document_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_METADATA_EDIT])
            
    document = get_object_or_404(Document, pk=document_id)

    initial=[]
    for item in DocumentTypeMetadataType.objects.filter(document_type=document.document_type):
        initial.append({
            'metadata_type':item.metadata_type,
            'document_type':document.document_type,
            'value':document.documentmetadata_set.get(metadata_type=item.metadata_type).value if document.documentmetadata_set.filter(metadata_type=item.metadata_type) else None
        })
    #for metadata in document.documentmetadata_set.all():
    #    initial.append({
    #        'metadata_type':metadata.metadata_type,
    #        'document_type':document.document_type,
    #        'value':metadata.value,
    #    })    

    formset = MetadataFormSet(initial=initial)
    if request.method == 'POST':
        formset = MetadataFormSet(request.POST)
        if formset.is_valid():
            save_metadata_list(formset.cleaned_data, document)
            try:
                document_delete_fs_links(document)
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(reverse('document_list'))
           
            messages.success(request, _(u'Metadata for document %s edited successfully.') % document)
            
            try:
                document_create_fs_links(document)
                messages.success(request, _(u'Document filesystem links updated successfully.'))                
            except Exception, e:
                messages.error(request, e)
                return HttpResponseRedirect(document.get_absolute_url())
                
            return HttpResponseRedirect(document.get_absolute_url())
        
        
    return render_to_response('generic_form.html', {
        'form_display_mode_table':True,
        'form':formset,
        'object':document,
    
    }, context_instance=RequestContext(request))
    

def get_document_image(request, document_id, size=PREVIEW_SIZE, quality=QUALITY_DEFAULT):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_VIEW])
        
    document = get_object_or_404(Document, pk=document_id)

    page = int(request.GET.get('page', 1))
    transformation_list = []
    try:
        #Catch invalid or non existing pages
        document_page = DocumentPage.objects.get(document=document, page_number=page)
        for page_transformation in document_page.documentpagetransformation_set.all():
            try:
                if page_transformation.transformation in TRANFORMATION_CHOICES:
                    output = TRANFORMATION_CHOICES[page_transformation.transformation] % eval(page_transformation.arguments)
                    transformation_list.append(output)
            except Exception, e:
                if request.user.is_staff:
                    messages.warning(request, _(u'Error for transformation %(transformation)s:, %(error)s') % 
                        {'transformation':page_transformation.get_transformation_display(),
                        'error':e})
                else:
                    pass
    except ObjectDoesNotExist:
        pass

    tranformation_string = ' '.join(transformation_list)
    try:
        filepath = in_image_cache(document.checksum, size=size, quality=quality, extra_options=tranformation_string, page=page-1)
        if filepath:
            return serve_file(request, File(file=open(filepath, 'r')), content_type='image/jpeg')
        #Save to a temporary location
        filepath = document_save_to_temp_dir(document, filename=document.checksum)
        output_file = convert(filepath, size=size, format='jpg', quality=quality, extra_options=tranformation_string, page=page-1)
        return serve_file(request, File(file=open(output_file, 'r')), content_type='image/jpeg')
    except UnkownConvertError, e:
        if request.user.is_staff or request.user.is_superuser:
            messages.error(request, e)
        if size == THUMBNAIL_SIZE:
            return serve_file(request, File(file=open('%simages/picture_error.png' % settings.MEDIA_ROOT, 'r')))
        else:
            return serve_file(request, File(file=open('%simages/1297211435_error.png' % settings.MEDIA_ROOT, 'r')))
    except UnknownFormat:
        if size == THUMBNAIL_SIZE:
            return serve_file(request, File(file=open('%simages/1299549572_unknown2.png' % settings.MEDIA_ROOT, 'r')))
        else:
            return serve_file(request, File(file=open('%simages/1299549805_unknown.png' % settings.MEDIA_ROOT, 'r')))
    except Exception, e:
        if request.user.is_staff or request.user.is_superuser:
            messages.error(request, e)
        if size == THUMBNAIL_SIZE:
            return serve_file(request, File(file=open('%simages/picture_error.png' % settings.MEDIA_ROOT, 'r')))
        else:
            return serve_file(request, File(file=open('%simages/1297211435_error.png' % settings.MEDIA_ROOT, 'r')))

        
def document_download(request, document_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_DOWNLOAD])
    
    document = get_object_or_404(Document, pk=document_id)
    try:
        #Test permissions and trigger exception
        document.open()
        return serve_file(request, document.file, save_as='%s' % document.get_fullname())
    except Exception, e:
        messages.error(request, e)
        return HttpResponseRedirect(request.META['HTTP_REFERER'])


#TODO: Need permission
def staging_file_preview(request, staging_file_id):
    transformation_list = []
    for page_transformation in DEFAULT_TRANSFORMATIONS:
        try:
            if page_transformation['name'] in TRANFORMATION_CHOICES:
                output = TRANFORMATION_CHOICES[page_transformation['name']] % eval(page_transformation['arguments'])
                transformation_list.append(output)
        except Exception, e:
            if request.user.is_staff:
                messages.warning(request, _(u'Error for transformation %(transformation)s:, %(error)s') % 
                    {'transformation':page_transformation.get_transformation_display(),
                    'error':e})
            else:
                pass
    tranformation_string = ' '.join(transformation_list)
     
    try:
        filepath = StagingFile.get(staging_file_id).filepath
        output_file = convert(filepath, size=STAGING_FILES_PREVIEW_SIZE, extra_options=tranformation_string, cleanup_files=False)
        return serve_file(request, File(file=open(output_file, 'r')))
    except Exception, e:
        return serve_file(request, File(file=open('%simages/1297211435_error.png' % settings.MEDIA_ROOT, 'r')))        


#TODO: Need permission     
def staging_file_delete(request, staging_file_id):
    staging_file = StagingFile.get(staging_file_id)
    next = request.POST.get('next', request.GET.get('next', request.META.get('HTTP_REFERER', None)))
    previous = request.POST.get('previous', request.GET.get('previous', request.META.get('HTTP_REFERER', None)))

    if request.method == 'POST':
        try:
            staging_file.delete()
            messages.success(request, _(u'Staging file delete successfully.'))
        except Exception, e:
            messages.error(request, e)
        return HttpResponseRedirect(next)
        
    return render_to_response('generic_confirm.html', {
        'delete_view':True,
        'object':staging_file,
        'next':next,
        'previous':previous,
    }, context_instance=RequestContext(request))


def document_page_view(request, document_page_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_VIEW])
        
    document_page = get_object_or_404(DocumentPage, pk=document_page_id)
    document_page_form = DocumentPageForm(instance=document_page)

    form_list = [
        {
            'form':document_page_form,
            'title':_(u'details for document page: %s') % document_page.page_number,
            'object':document_page,
            'grid':6,
        },
    ]
    subtemplates_dict = [
        {
            'name':'generic_list_subtemplate.html',
            'title':_(u'transformations'),
            'object_list':document_page.documentpagetransformation_set.all(),
            'extra_columns':[
                {'name':_(u'order'), 'attribute':'order'},
                {'name':_(u'transformation'), 'attribute':lambda x: x.get_transformation_display()},
                {'name':_(u'arguments'), 'attribute':'arguments'}
                ],
            'hide_link':True,
            'hide_object':True,
            'grid':6,
            'grid_clear':True,
            'hide_header':True,
        },
    ]
           
    return render_to_response('generic_detail.html', {
        'form_list':form_list,
        'object':document_page,
        'subtemplates_dict':subtemplates_dict,
    }, context_instance=RequestContext(request))
    
    
def document_page_transformation_create(request, document_page_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_TRANSFORM])

    document_page = get_object_or_404(DocumentPage, pk=document_page_id)
        
    if request.method == 'POST':
        form = DocumentPageTransformationForm(request.POST, initial={'document_page':document_page})
        if form.is_valid():
            form.save()
            return HttpResponseRedirect(reverse('document_page_view', args=[document_page_id]))
    else:
        form = DocumentPageTransformationForm(initial={'document_page':document_page})

    return render_to_response('generic_form.html', {
        'form':form,
        'object':document_page,
        'title':_(u'Create new transformation for page: %(page)s of document: %(document)s') % {
            'page':document_page.page_number, 'document':document_page.document},
    }, context_instance=RequestContext(request))            


def document_page_transformation_edit(request, document_page_transformation_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_TRANSFORM])

    document_page_transformation = get_object_or_404(DocumentPageTransformation, pk=document_page_transformation_id)
    return update_object(request, template_name='generic_form.html', 
        form_class=DocumentPageTransformationForm, 
        object_id=document_page_transformation_id,
        post_save_redirect=reverse('document_page_view', args=[document_page_transformation.document_page.id]),
        extra_context={
            'object_name':_(u'transformation')}
        )

    return render_to_response('generic_form.html', {
        'form':form,
        'object':document_page_transformation.document_page,
        'title':_(u'Edit transformation "%(transformation)s" for page: %(page)s of document: %(document)s') % {
            'transformation':document_page_transformation.get_transformation_display(),
            'page':document_page_transformation.document_page.page_number,
            'document':document_page_transformation.document_page.document},
    }, context_instance=RequestContext(request))     


def document_page_transformation_delete(request, document_page_transformation_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_TRANSFORM])

    previous = request.POST.get('previous', request.GET.get('previous', request.META.get('HTTP_REFERER', None)))
            
    document_page_transformation = get_object_or_404(DocumentPageTransformation, pk=document_page_transformation_id)
        
    return delete_object(request, model=DocumentPageTransformation, object_id=document_page_transformation_id, 
        template_name='generic_confirm.html', 
        post_delete_redirect=reverse('document_page_view', args=[document_page_transformation.document_page.id]),
        extra_context={
            'delete_view':True,
            'object':document_page_transformation,
            'object_name':_(u'document transformation'),
            'title':_(u'Are you sure you wish to delete transformation "%(transformation)s" for page: %(page)s of document: %(document)s') % {
                'transformation':document_page_transformation.get_transformation_display(),
                'page':document_page_transformation.document_page.page_number,
                'document':document_page_transformation.document_page.document},
            'previous':previous,
        })


def document_find_duplicates(request, document_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_VIEW])
            
    document = get_object_or_404(Document, pk=document_id)
    return _find_duplicate_list(request, [document], include_source=True, confirmation=False)    


def _find_duplicate_list(request, source_document_list=Document.objects.all(), include_source=False, confirmation=True):
    previous = request.POST.get('previous', request.GET.get('previous', request.META.get('HTTP_REFERER', None)))
    
    if confirmation and request.method != 'POST':
        return render_to_response('generic_confirm.html', {
            'previous':previous,
            'message':_(u'On large databases this operation may take some time to execute.'),
        }, context_instance=RequestContext(request))
    else:     
        duplicated = []
        for document in source_document_list:
            if document.pk not in duplicated:
                results = Document.objects.filter(checksum=document.checksum).exclude(id__in=duplicated).exclude(pk=document.pk).values_list('pk', flat=True)
                duplicated.extend(results)

                if include_source and results:
                    duplicated.append(document.pk)

        return render_to_response('generic_list.html', {
            'object_list':Document.objects.filter(pk__in=duplicated),
            'title':_(u'duplicated documents'),
        }, context_instance=RequestContext(request))   


def document_find_all_duplicates(request):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_VIEW])

    return _find_duplicate_list(request, include_source=True)


def document_clear_transformations(request, document_id):
    check_permissions(request.user, 'documents', [PERMISSION_DOCUMENT_TRANSFORM])

    previous = request.POST.get('previous', request.GET.get('previous', request.META.get('HTTP_REFERER', None)))
            
    document = get_object_or_404(Document, pk=document_id)
        
    if request.method == 'POST':
        for document_page in document.documentpage_set.all():
            for transformation in document_page.documentpagetransformation_set.all():
                transformation.delete()
                
        messages.success(request, _(u'All the page transformations for document: %s, have been deleted successfully.') % document)
        return HttpResponseRedirect(reverse('document_view', args=[document.pk]))
        

    return render_to_response('generic_confirm.html', {
        'object_name':_(u'document transformation'),
        'delete_view':True,
        'object':document,
        'title':_(u'Are you sure you with to clear all the page transformations for document: %s?') % document,
        'previous':previous,
    }, context_instance=RequestContext(request))

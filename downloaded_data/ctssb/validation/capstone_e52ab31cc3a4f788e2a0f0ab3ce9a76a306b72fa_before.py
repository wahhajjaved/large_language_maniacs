from capdb.utils import generate_unique_slug
from django.db import IntegrityError

from tqdm import tqdm

from capdb.models import VolumeMetadata, TrackingToolUser, Reporter, ProcessStep, TrackingToolLog, BookRequest, Jurisdiction
from tracking_tool.models import BookRequests, Eventloggers, Hollis, Pstep, Reporters, Users, Volumes

user_field_map = {'id': 'id', 'privlevel': 'privilege_level', 'email': 'email', 'created_at': 'created_at', 'updated_at': 'updated_at' }
book_request_field_map = {'id': 'id', 'updated_by': 'updated_by', 'created_at': 'created_at', 'updated_at': 'updated_at', 'recipients': 'recipients', 'from_field': 'from_field', 'mail_body': 'mail_body', 'note': 'note', 'send_date': 'send_date', 'label': 'label', 'sent_at': 'sent_at', 'subject': 'subject', 'delivery_date': 'delivery_date'} 
pstep_field_map = {'step_id': 'step', 'name': 'label', 'prereq': 'prerequisites', 'desc': 'description', 'created_at': 'created_at', 'updated_at': 'updated_at'}
reporter_field_map = {'id': 'id', 'reporter': 'full_name', 'short': 'short_name', 'start_date': 'start_year', 'end_date': 'end_year', 'volumes': 'volume_count', 'created_at': 'created_at', 'updated_at': 'updated_at', 'notes': 'notes'}
volume_field_map = {'bar_code': 'barcode', 'hollis_no': 'hollis_number', 'volume': 'volume_number', 'publisher': 'publisher', 'publicationyear': 'publication_year', 'reporter_id': 'reporter', 'nom_volume': 'nominative_volume_number', 'nominative_name': 'nominative_name', 'series_volume': 'series_volume_number', 'spine_start_date': 'spine_start_year', 'spine_end_date': 'spine_end_year', 'start_date': 'start_year', 'end_date': 'end_year', 'page_start_date': 'page_start_year', 'page_end_date': 'page_end_year', 'contributing_library': 'contributing_library', 'rare': 'rare', 'hscrev': 'hsc_review', 'needs_repair': 'needs_repair', 'missing_text_pages': 'missing_text_pages', 'created_by': 'created_by', 'bibrev': 'bibliographic_review', 'pages': 'analyst_page_count', 'dup': 'duplicate', 'created_at': 'created_at', 'updated_at': 'updated_at', 'replaced_pages': 'replaced_pages', 'marginalia': 'has_marginalia', 'pop': 'publication_city', 'title': 'title', 'handfeed': 'hand_feed', 'imgct': 'image_count', 'request_id': 'request', 'pub_del_pg': 'publisher_deleted_pages', 'notes': 'notes', 'original_barcode': 'original_barcode', 'scope_reason': 'scope_reason', 'out_of_scope': 'out_of_scope', 'meyer_box_barcode': 'meyer_box_barcode', 'uv_box_barcode': 'uv_box_barcode', 'meyer_ky_truck': 'meyer_ky_truck', 'meyer_pallet': 'meyer_pallet' }
eventloggers_field_map = {'id': 'id', 'bar_code': 'volume', 'type': 'entry_text', 'notes': 'notes', 'created_by': 'created_by', 'created_at': 'created_at', 'updated_at': 'updated_at', 'pstep_id': 'pstep', 'exception': 'exception', 'warning': 'warning', 'version_string': 'version_string'}

# I'm sure there's an elegant way to combine this with dup_field, but it wasn't imperative enough for me to figure out
foreign_key_map = {'created_by': {'model': TrackingToolUser, 'query_field': 'id'}, 'pstep': { 'model': ProcessStep, 'query_field': 'step'}, 'volume': { 'model': VolumeMetadata, 'query_field': 'barcode'}, 'reporter': { 'model': Reporter, 'query_field': 'id'}, 'request': { 'model': BookRequest, 'query_field': 'id'} }

def ingest(dupcheck):
    """
    If we decide to copy more tables over, just add a new entry:
    copyModel(sourcemodel, destinationmodel, dupcheck)
    """

    copyModel(Users, TrackingToolUser, user_field_map, dupcheck)
    copyModel(BookRequests, BookRequest, book_request_field_map, dupcheck)
    copyModel(Pstep, ProcessStep, pstep_field_map, dupcheck, dupe_field='step_id')
    copyModel(Reporters, Reporter, reporter_field_map, dupcheck)
    copyModel(Volumes, VolumeMetadata, volume_field_map, dupcheck, dupe_field='bar_code')
    copyModel(Eventloggers, TrackingToolLog, eventloggers_field_map, dupcheck)
    

def copyModel(source, destination, field_map, dupcheck, dupe_field='id'):

    """
    This essentially just copies all records in one table to another 
    table with the same column names.

    The only problem I had with the data was Django not correctly interpreting
    date fields that were set to 'allballs,' so I just went into the tracking
    tool db and ran:

    update eventloggers set updated_at = created_at 
    where updated_at = '0000-00-00 00:00:00+00';
    """

    print("Copying {} to {}".format(source.__name__, destination.__name__))

    source_collection=source.objects.all()
    if dupcheck:
        dupe_set = set(destination.objects.values_list(field_map[dupe_field], flat=True))

    for source_record in tqdm(source_collection, total=source_collection.count()):
        if dupcheck:
            if getattr(source_record, dupe_field) in dupe_set:
                continue

        destination_record = destination()
        # with Reporter, make an array of hollis numbers
        if source.__name__ == 'Reporters':
            hollis_numbers = Hollis.objects.filter(id=source_record.id).values_list('hollis_no', flat=True)
            destination_record.hollis = list(hollis_numbers)

        for source_field_name, dest_field_name in field_map.items():
            value = getattr(source_record, source_field_name)
            
            # field specific operations
            # null value in boolean field should be False
            if destination._meta.get_field(dest_field_name).get_internal_type() == 'BooleanField':
                if not value or value == 'N':
                    value = False
                elif value == 'Y':
                    value = True
            # replace id populated fk fields` with model instances
            elif destination._meta.get_field(dest_field_name).get_internal_type() == 'ForeignKey':
                kwargs = {}
                kwargs[foreign_key_map[dest_field_name]['query_field']] = value
                results = foreign_key_map[dest_field_name]['model'].objects.filter(**kwargs)

                if results.count() < 1:
                    # skip broken request_id links -- sources don't exist
                    if source_field_name == 'request_id':
                        value = None
                    # Skip log entries for which the volume was deleted
                    elif source_field_name == 'bar_code' and destination.__name__ == 'TrackingToolLog':
                        continue
                else:
                    value = results[0]

            setattr(destination_record, dest_field_name, value)

        try:
            destination_record.save()
            if source.__name__ == 'Reporters':
                destination_record.jurisdictions.add(Jurisdiction.objects.get(name=source_record.state))
                destination_record.save()

        except IntegrityError as e:
            print(e)

def populate_jurisdiction():
    """This populates the jurisdiction table based on what's in the tracking tool stub"""
    reporters = Reporters.objects.values('state').distinct() 
    for jurisdiction in reporters:
        # ensures no dupes if the command was already run. Small enough dataset to check every time
        if Jurisdiction.objects.filter(name=jurisdiction['state']).count() > 1:
            continue
        new_jurisdiction = Jurisdiction()
        new_jurisdiction.name = jurisdiction['state']
        new_jurisdiction.slug = generate_unique_slug(Jurisdiction, 'slug', jurisdiction['state'])
        new_jurisdiction.save()

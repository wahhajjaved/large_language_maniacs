from django.core.management.base import BaseCommand, CommandError
from content.models import Entry, TagVal, FavoriteTag, Voter
from taggit.models import Tag
import os

class Command(BaseCommand):
    args = ''
    help = 'Decay for entry scores.'
    def handle(self, *args, **options):
        print('Use this command to change the name of a tag. Everything here is case sensitive, so it can be used to change capitalization.')
        taginput = raw_input('Which tag do you want to change?  ')
        if Tag.objects.filter(name = taginput):
            print('found '+str(tagchange)+'.')
        else:
            print('no tag with the name '+taginput+' exists.')
            maybe = [ tag.name for tag in Tag.objects.filter(name_iexact=taginput) ]
            if maybe:
                print('Try '+' or '.join(maybe)+', maybe?')
            return
        
        newtaginput = raw_input('What would you like to change it to?  ')
        if Tag.objects.filter(name = newtaginput):
            print('tag '+str(newtaginput)+' already exists.')
            return

        
        print('Changing tag '+str(taginput)+' to '+str(newtaginput)+'...')
        tagchange = Tag.objects.get(name=taginput)
        tagchange.name = newtaginput
        tagchange.save()
        
        entries = Entry.objects.filter(tags_name_in=[taginput])
        for entry in entries:
            entry.tags.remove(taginput)
            entry.tags.add(newtaginput)
        print('changed tag on '+str(len(entries))+' Entries...')
        
        tvs = TagVal.objects.filter(tag=taginput)
        for tv in tvs:
            tv.tag = newtaginput
            tv.save()
        print('changed tag on '+str(len(tvs))+' TagVals...')

        favtags = [ favtag for favtag in FavoriteTag.objects.all() if taginput in favtag.tags.split('+') ]
        for favtag in favtags:
            tags=favtag.tags.split('+')
            for i, tag in enumerate(tags):
                if tag == taginput:
                    tags[i]=newtaginput
            favtag.tags = '+'.join(tags)
            favtag.save()
        print('changed tag in '+str(len(favtags))+' FavoriteTags...')
                    
        voters = Voter.objects.filter(tag=taginput)
        for voter in voters:
            voter.tag = newtaginput
            voter.save()
        print('changed tag on '+str(len(voters))+' Voters...')

        
            
        

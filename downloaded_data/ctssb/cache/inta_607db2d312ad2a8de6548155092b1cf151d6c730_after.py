from django.core.management.base import BaseCommand, CommandError
from content.models import Entry, TagVal, FavoriteTag, Voter, DataList
from taggit.models import Tag
import os

class Command(BaseCommand):
    args = ''
    help = 'Decay for entry scores.'
    def handle(self, *args, **options):
        print('Use this command to change the name of a tag. Everything here is case sensitive, so it can be used to change capitalization.')
        taginput = raw_input('Which tag do you want to change?  ')
        if Tag.objects.filter(name = taginput):
            print('found '+str(taginput)+'.')
            tagchange = Tag.objects.get(name=taginput)
            datalistnames = ['top_'+taginput]+['top_d'+str(i)+'_'+taginput for i in range(1,9) ]
            datalists = [ DataList.objects.get(name=name) for name in datalistnames ]
            activetags = DataList.objects.get(id=1)
            activetagids = eval(activetags.data)
        else:
            print('no tag with the name '+taginput+' exists.')
            maybe = [ tag.name for tag in Tag.objects.filter(name__iexact=taginput) ]
            if maybe:
                print('Try '+' or '.join(maybe)+', maybe?')
            return
        
        newtaginput = raw_input('What would you like to change it to?  ')
        alreadyexists=Tag.objects.filter(name = newtaginput)
        if alreadyexists:
            decision = raw_input('This tag already exists. Would you like to merge '+str(taginput)+' and '+str(newtaginput)+'? (y/n)  ')
            if decision == 'y':
                print('merging tags...')
                if activetagids.__contains__(tagchange.id): #this tag is going to be deleted, so remove it from activetags
                    activetagids.remove(tagchange.id)
                activetagids.append(alreadyexists[0].id) #make the changed tag active
                activetags.data=activetagids
                activetags.save()
                for dl in datalists: #no need to hold on to rankings from old tag
                    dl.delete()
            else:
                return
        else:
            print('Changing tag '+str(taginput)+' to '+str(newtaginput)+'...')
            tagchange.name = newtaginput
            tagchange.save()
            for name in ['top_'+newtaginput]+['top_d'+str(i)+'_'+newtaginput for i in range(1,9) ]: #set up new datalists for ranking
                DataList.objects.create(name=name, data=[])
        
        entries = Entry.objects.filter(tags__name__in=[taginput])
        doubles = entries.filter(tags__name__in=[newtaginput])
        if not alreadyexists or not doubles:
            for entry in entries:
                entry.tags.remove(taginput)
                entry.tags.add(newtaginput)
        else:
            print('Some Entries ('+str(doubles)+') have both tags you wanted to merge. There\'s probably a good way around this but I haven\'t worked it out yet. sorry')
            return
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

        if alreadyexists:
            tagchange.delete() #only delete tagchange if the new tag already existed because otherwise we just changed tagchange.name so we need to keep it

        details = raw_input('Done! Details? (y/n)  ')
        if details == 'n':
            return
        else:
            print('Changed:')
            print('Entries:  '+str(entries))
            print('TagVals:  '+str(tvs))
            print('FavTags:  '+str(favtags))
            print('Voters:   '+str(voters))
            return

        
            
        

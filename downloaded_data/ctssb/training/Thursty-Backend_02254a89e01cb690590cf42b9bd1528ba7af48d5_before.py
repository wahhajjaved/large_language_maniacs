#-----------------------
# Purpose: Views dealing with guest checkin, checkout and payment
# Author: Siddharth Joshi
# Date Created: 07/04/18
#------------------------
from Guest.models import Guest
from rest_framework import generics
from Guest.serializers import GuestSerializer

#Guest CheckIn
class GuestCheckIn(generics.ListCreateAPIView):
    queryset = Guest.objects.all()
    serializer_class = GuestSerializer
 
    def perform_create(self, serializer):
        serializer.save()
 
#Individual Guest Instance - used for updating payment, and exit time etc. 
class GuestDetail(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = GuestSerializer
    lookup_field = 'pk'
    def get_queryset(self):
        queryset = Guest.objects.all()

        guestinstanceid = self.kwargs['pk']
       
        if guestinstanceid is not None:
            queryset = queryset.filter(guestInstanceID = guestinstanceid)
            
        return queryset

#Guest List for Party
class GuestList(generics.ListAPIView):
    serializer_class = GuestSerializer
    lookup_field = 'pk'
    
    def get_queryset(self):
        queryset = Guest.objects.all()

        partyID = self.kwargs['pk']

        if partyID is not None:
            queryset = queryset.filter(partyid__icontains = partyID)

        return queryset
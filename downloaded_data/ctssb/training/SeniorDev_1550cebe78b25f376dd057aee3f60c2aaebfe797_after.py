from backend.models import Reservation, ReservationRequest, ItemType
from django.shortcuts import get_object_or_404,render,redirect
from django.contrib.auth.decorators import login_required
from backend.forms import ReservationRequestForm, ReservationRequestApprovalForm
from datetime import datetime

@login_required
def request(request):
    if request.method == "POST":
        form = ReservationRequestForm(request.POST)
        if form.is_valid():
            obj = form.save(commit = False)
            obj.requester = request.user
            obj.save()
            # for now redirect back to the same page
            return redirect('request')
    else:
        form = ReservationRequestForm()
        return render(request, 'reserveItem.html', {'title': 'Reserve Item', 'form': form})


@login_required
def view_requests(request):
    requests = ReservationRequest.objects.filter(approvedOn = None, approvedBy = None)
    return render(request, 'reservationRequests.html', {'title': 'Pending Reservations', 'requests': requests})


@login_required()
def edit_request(request, request_id):
    if request.method == "POST":
        #get form data that may have been changed
        form = ReservationRequestApprovalForm(request.POST)
        if form.is_valid():
            #breakout item info if no specific type
            rr = ReservationRequest.objects.get(pk=request_id)
            if rr.itemTypeID is None:
                itemTypes = ItemType.objects.filter(subCategoryID=rr.itemSubCategoryID)
                for it in itemTypes:
                    # get an object
                    obj = form.save(commit=False)
                    obj.reservationRequestID = rr
                    obj.itemTypeID = it
                    obj.userID = rr.personRequestedFor
                    obj.save()
            else:
                # get an object
                obj = form.save(commit=False)
                obj.reservationRequestID = rr
                obj.itemTypeID = rr.itemTypeID
                obj.userID = rr.personRequestedFor
                obj.save()
            # set approval info
            rr.approvedBy = request.user
            rr.approvedOn = datetime.now()
            rr.save()
        return(view_requests(request))
    else:
        rr = get_object_or_404(ReservationRequest, pk=int(request_id))
        reservationInstance = Reservation
        reservationInstance.endDate = rr.endDate
        reservationInstance.startDate = rr.startDate
        reservationInstance.lengthOfCheckout = rr.lengthOfCheckout
        reservationInstance.quantity = rr.quantity
        form = ReservationRequestApprovalForm(instance=reservationInstance)
        return render(request, 'editReservation.html', {'title': 'Edit Reservation', 'request': rr, 'form':form})


@login_required
def list_reservations(request):
    reservations = Reservation.objects.all()
    return render(request, 'viewReservations.html', {'title': 'View Reservations', 'reservations': reservations})

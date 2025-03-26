from __future__ import absolute_import

from django.db.models import Q

from django.views.generic import ListView, DetailView, FormView, View
from django.views.generic.detail import SingleObjectMixin
from django.http import HttpResponseForbidden

from django.shortcuts import render
from django.core.urlresolvers import reverse

from .forms import ListingForm, TransactionRequestForm
from .models import Listing, TransactionRequestThread
from books.forms import TextbookForm, AuthorFormSet, ProfessorForm, SemesterForm


class ListingList(ListView):
    """
    List of all available listings. Filtering and ordering specified by GET parameters.
    """
    model = Listing
    queryset = Listing.objects.select_related().filter(status=Listing.AVAILABLE).order_by('-date_created')

    paginate_by = 10

    context_object_name = 'listings_list'
    template_name = 'buy/list-partial.html'

    def get_queryset(self):
        qs = super(ListingList, self).get_queryset()
        query = Q()

        sort_field = None
        for key in self.request.GET:
            if key == u'order_by':
                if self.request.GET[key] in [u'book__title', u'-asking_price', u'asking_price', u'-date_created']:
                    sort_field = self.request.GET[key]

            if key not in [u'title', u'isbn', u'course_code']:
                continue

            iexact = 'book__%s__iexact' % key
            icontains = 'book__%s__icontains' % key
            values = self.request.GET.getlist(key)

            kquery = Q()
            for v in values:
                kquery |= Q(**{iexact: v})
                kquery |= Q(**{icontains: v})
            query &= kquery

        qs = qs.filter(query)
        if sort_field is not None:
            qs = qs.order_by(sort_field)

        return qs


class ListingDetail(DetailView):
    """
    Detail for a specific listing.
    """
    model = Listing
    queryset = Listing.objects.select_related().filter(status=Listing.AVAILABLE)

    context_object_name = 'listing'
    template_name = 'buy/listing-detail.html'


class CreateEditListing(View):
    """
    Listing form view for creating a new listing or editing an existing one.
    """
    template_name = 'sell/index.html'
    post_url = 'sell'

    def render_to_template(self, pk, extra_context):
        if pk is not None:
            action = reverse(self.post_url, kwargs={'pk': pk})
        else:
            action = reverse(self.post_url)

        context = {
            'active': 'sell',
            'action': action,
        }

        context.update(extra_context)

        return render(self.request, self.template_name, context)

    def get(self, request, *args, **kwargs):
        """
        Form is bound if pk is in kwargs, otherwise return a blank form.
        """
        if 'pk' not in kwargs:
            book_form = TextbookForm()
            listing_form = ListingForm()
            author_formset = AuthorFormSet()
            professor_form = ProfessorForm()
            semester_form = SemesterForm()

            pk = None
        else:
            pk = int(kwargs['pk'])

            listing = Listing.objects.select_related().get(pk=pk)
            if listing.owner != request.user:
                return HttpResponseForbidden()

            book_form = TextbookForm(instance=listing.book)
            listing_form = ListingForm(instance=listing)

            initial = []
            for author in listing.book.authors.all():
                initial.append({'author': unicode(author)})
            author_formset = AuthorFormSet(initial=initial)

            if listing.book.professor is not None:
                professor_form = ProfessorForm(initial={'professor': unicode(listing.book.professor)})
            else:
                professor_form = ProfessorForm()

            if listing.book.semester is not None:
                semester_form = SemesterForm(initial={
                    'semester': listing.book.semester.semester,
                    'year': listing.book.semester.year
                })
            else:
                semester_form = SemesterForm()

        return self.render_to_template(pk, {
            'book_form': book_form,
            'listing_form': listing_form,
            'author_formset': author_formset,
            'professor_form': professor_form,
            'semester_form': semester_form,
        })

    def post(self, request, *args, **kwargs):
        """
        Form has associated instances if pk in kwargs, otherwise create a new listing.
        """
        prof_form = ProfessorForm(request.POST)
        sem_form = SemesterForm(request.POST)
        author_formset = AuthorFormSet(request.POST)

        if 'pk' not in kwargs:
            book_form = TextbookForm(request.POST)
            listing_form = ListingForm(request.POST)
            pk = None
            current_book_authors = []
        else:
            pk = int(kwargs['pk'])

            listing = Listing.objects.select_related().get(pk=pk)
            if listing.owner != request.user:
                return HttpResponseForbidden()
            book_form = TextbookForm(request.POST, instance=listing.book)
            listing_form = ListingForm(request.POST, instance=listing)

            current_book_authors = list(listing.book.authors.all())

        biv = book_form.is_valid()
        liv = listing_form.is_valid()
        aiv = author_formset.is_valid()
        piv = prof_form.is_valid()
        siv = sem_form.is_valid()

        extra_context = {}
        valid = biv and liv and aiv and piv and siv

        if valid:
            book = book_form.save(commit=False)

            semester = sem_form.save()
            if semester is not None:
                book.semester = semester

            prof = prof_form.save()
            book.professor = prof

            book.save()

            # On update, delete all authors that aren't kept in the form, save new authors
            for form in author_formset.forms:
                new_author = form.save(book, commit=False)
                if new_author is None:
                    continue

                if new_author in current_book_authors:
                    current_book_authors.remove(new_author)
                else:
                    new_author.save()

            # These are the authors that weren't resubmitted - delete them
            for leftover_author in current_book_authors:
                leftover_author.delete()

            listing_form.save(book=book, owner=request.user)

            extra_context.update({'success_message': 'Listing successfully added!'})

        # pk None means listing created - return blank forms. Otherwise, return bound stuff
        if pk is None and valid:
            book_form = TextbookForm()
            listing_form = ListingForm()
            author_formset = AuthorFormSet()
            prof_form = ProfessorForm()
            sem_form = SemesterForm()

        extra_context.update({
            'book_form': book_form,
            'listing_form': listing_form,
            'author_formset': author_formset,
            'professor_form': prof_form,
            'semester_form': sem_form,
        })

        if not valid:
            extra_context.update({'error_message': 'There were issues with your submission'})

        return self.render_to_template(pk, extra_context)


class ProfileListings(ListView):
    """
    List of all listings the authenticated user has created.
    """
    model = Listing

    context_object_name = 'listings_list'
    template_name = 'profile/your-listings.html'

    def get_queryset(self):
        return Listing.objects.select_related().filter(owner=self.request.user).order_by('-date_created')


class BoxBase(ListView):
    """
    Base CBV for inbox and outbox.
    """
    model = TransactionRequestThread

    context_object_name = 'request_list'
    template_name = 'profile/inbox.html'

    # Set to either 'inbox' or 'outbox' by subclasses
    box = None

    def get_context_data(self, **kwargs):
        context = super(BoxBase, self).get_context_data(**kwargs)
        context.update({'box': self.box})

        return context


class Inbox(BoxBase):
    """
    List of all requests the authenticated user has received for his/her listings.
    """
    box = 'inbox'

    def get_queryset(self):
        return TransactionRequestThread.objects.select_related().filter(listing__owner=self.request.user).order_by('-date_created')


class Outbox(BoxBase):
    """
    List of all requests the authenticated user has sent.
    """
    box = 'outbox'

    def get_queryset(self):
        return TransactionRequestThread.objects.select_related().filter(sender=self.request.user).order_by('-date_created')


class RequestThreadDisplay(DetailView):
    """
    View to display message thread and empty form for submitting a reply.
    """
    model = TransactionRequestThread

    context_object_name = 'thread'
    template_name = 'profile/thread.html'

    def get_queryset(self):
        """
        Limit to message threads that the authenticated user is involved in.
        """
        return TransactionRequestThread.objects.select_related().filter(
            Q(listing__owner=self.request.user) | Q(sender=self.request.user)
        )

    def get_context_data(self, **kwargs):
        context = super(RequestThreadDisplay, self).get_context_data(**kwargs)
        context['form'] = TransactionRequestForm()

        return context


class RequestThreadSubmit(SingleObjectMixin, FormView):
    """
    View that handles message thread reply form submission.
    """
    form_class = TransactionRequestForm

    model = TransactionRequestThread
    context_object_name = 'thread'

    template_name = 'profile/thread.html'

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        return super(RequestThreadSubmit, self).post(request, *args, **kwargs)

    def get_queryset(self):
        """
        Limit to message threads that the authenticated user is involved in.
        """
        return TransactionRequestThread.objects.select_related().filter(
            Q(listing__owner=self.request.user) | Q(sender=self.request.user)
        )

    def form_valid(self, form):
        thread = self.get_object()
        form.save(thread=thread, user=self.request.user)

        return super(RequestThreadSubmit, self).form_valid(form)

    def get_success_url(self):
        return reverse('thread', kwargs={'pk': self.get_object().pk})


class RequestThreadDetail(View):
    """
    Combines RequestThreadSubmit and RequestThreadDisplay views.
    """
    def dispatch(self, request, *args, **kwargs):
        """
        Return 403 if accessing user isn't involved in the message thread.
        """
        if 'pk' in kwargs:
            thread = TransactionRequestThread.objects.get(pk=int(kwargs['pk']))
            if thread.listing.owner != request.user and thread.sender != request.user:
                return HttpResponseForbidden()

            thread.mark_seen_by(request.user)

        return super(RequestThreadDetail, self).dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        view = RequestThreadDisplay.as_view()
        return view(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        view = RequestThreadSubmit.as_view()
        return view(request, *args, **kwargs)


class CreateListingRequest(SingleObjectMixin, FormView):
    """
    Create (or update) a listing thread for a listing. If the authenticated
    user already has a pending request for this listing, this will add the
    request message to the thread.
    """
    form_class = TransactionRequestForm

    model = Listing
    queryset = Listing.objects.filter(status=Listing.AVAILABLE)
    context_object_name = 'listing'

    template_name = 'buy/send_request.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Return an error message with no form if listing owner is submitter.
        """
        self.object = self.get_object()

        if self.object.owner == request.user:
            # You can't buy your own book
            return render(request, 'buy/send_request.html', {
                'error_message': "You can't buy your own book!",
            })

        return super(CreateListingRequest, self).dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        form = self.get_form(self.get_form_class())

        if form.is_valid():
            return self.form_valid(form, **kwargs)
        else:
            return self.form_invalid(form, **kwargs)

    def form_valid(self, form, **kwargs):
        listing = self.object

        # Did this user already create a request thread for this listing?
        qs = listing.requests.filter(sender=self.request.user)
        if qs.exists():
            form.save(thread=qs[0], user=self.request.user)
        else:
            # Create a new thread
            thread = TransactionRequestThread(
                sender=self.request.user,
                listing=listing,
            )

            thread.save()

            # Save this message to the thread
            form.save(thread=thread, user=self.request.user)

        form = self.get_form_class()()

        context = super(CreateListingRequest, self).get_context_data(**kwargs)
        context.update({'form': form})

        context.update({'success_message': 'Listing request successfully created!'})

        return self.render_to_response(context)

    def form_invalid(self, form, **kwargs):
        context = super(CreateListingRequest, self).get_context_data(**kwargs)
        context.update({'form': form})
        context.update({'error_message': 'There was an error with your submission.'})

        return self.render_to_response(context)

    def get_success_url(self):
        return reverse('create_thread', kwargs={'pk': self.get_object().pk})

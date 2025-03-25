from collections import defaultdict
from datetime import datetime

from dal import autocomplete
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import is_safe_url
from django.utils.timezone import now, utc
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from sorl.thumbnail import get_thumbnail

from main.utils import send_mobilepay_request
from .forms import (UserRegForm, ProfileRegForm, TilmeldForm, EditUserForm, EditProfileForm, TournamentTeamForm,
                    FoodOrderForm)
from .models import LanProfile, Profile, Tournament, TournamentTeam, Event, FoodOrder, Lan


# Actual pages

def index(request):
    """Front page"""
    return render(request, 'index.html')


def info(request):
    """Information page"""
    return render(request, 'info.html')


def _table(seats, current, is_staff):
    row_width = 0

    # Consists of bool, (str, None or dict) tuples
    # bool is weather it's a header
    table = []
    for row in seats:
        if isinstance(row, str):
            line = row.split('|')
            data = {'title': line[0].strip()}
            if len(line) > 1:
                data['text'] = line[1].strip()
            table.append((True, data))
            continue
        table_row = []

        for seat, lp in row:
            if seat is None:
                table_row.append(None)
            else:
                attrs = {'seat': seat}
                classes = []
                if lp:
                    prof = lp.profile
                    classes.append('occupied')
                    if prof.user.is_staff:
                        classes.append('staff')
                    if seat == current:
                        classes.append('current')
                    if prof.profile:
                        im = get_thumbnail(prof.photo, '60x60', crop='center')
                        if im:
                            attrs['style'] = 'background-image: url({})'.format(im.url)

                    attrs['url'] = reverse('profile', kwargs={'username': prof.user.username})
                    attrs['name'] = prof.user.first_name
                    attrs['username'] = prof.user.username
                    attrs['grade'] = prof.get_grade_display()

                    if prof and is_staff and lp.paid:
                        attrs['paid'] = 'True'
                else:
                    classes.append('available')

                attrs['class'] = ' '.join(classes)
                table_row.append(attrs)

        if len(table_row) > row_width:
            row_width = len(table_row)
        table.append((False, table_row or [None]))
    return table, row_width


def tilmeld(request):
    """Tilmeldings page"""
    lan = Lan.get_next(request=request)
    context = {}
    if lan is not None:
        seats, count = lan.parse_seats()

        prof = request.user.profile if request.user.is_authenticated else None

        try:
            current = LanProfile.objects.get(lan=lan, profile=prof).seat
        except (LanProfile.DoesNotExist, AttributeError):
            current = 0

        table, row_width = _table(seats, current, request.user.is_staff)

        if request.method == 'POST':
            form = TilmeldForm(request.POST, seats=seats, lan=lan, profile=prof)
            if form.is_valid() and lan.is_open():
                if count[1] < count[2] or form.cleaned_data['seat'] == '':
                    created = form.save(profile=prof, lan=lan)
                    if created:
                        messages.add_message(request, messages.SUCCESS, "Du er nu tilmeldt LAN!")
                    else:
                        messages.add_message(request, messages.SUCCESS, "Tilmelding ændret!")
                    return redirect(reverse("tilmeld"))
            messages.add_message(request, messages.ERROR, "Tilmelding ikke mulig!")
        else:
            form = TilmeldForm(seats=seats, lan=lan, profile=prof)

        open_time = (lan.open - now()).total_seconds()

        context.update({'profile': prof,
                        'current': current,
                        'table': table,
                        'row_width': row_width,
                        'form': form,
                        'opens_time': open_time,
                        'count': count})
    return render(request, 'tilmeld.html', context)


def tilmeldlist(request):
    lan = Lan.get_next(request=request)
    profiles = LanProfile.objects.filter(lan=lan).select_related('profile').select_related('profile__user')
    return render(request, 'tilmeldlist.html', {'profiles': profiles})


def register(request):
    """Registration page"""
    if request.method == 'POST':
        user_form = UserRegForm(request.POST)
        profile_form = ProfileRegForm(request.POST)
        user_form_valid = user_form.is_valid()
        profile_form_valid = profile_form.is_valid()
        if user_form_valid and profile_form_valid:
            user = user_form.save()
            prof = profile_form.save(commit=False)
            prof.user = user
            prof.save()
            login(request, user)
            return redirect(reverse('registered'))
    else:
        user_form = UserRegForm()
        profile_form = ProfileRegForm()

    return render(request, 'register.html', {'user_form': user_form, 'profile_form': profile_form})


def registered(request):
    """After registration page"""
    return render(request, 'registered.html')


def profile(request, username=None):
    """Profile view/edit page"""
    user_form, profile_form = None, None
    start_edit = False

    if username is None:
        if request.user.is_authenticated:
            username = request.user.username
        else:
            return redirect(reverse('needlogin'))

    try:
        prof = Profile.objects.filter(user__username=username).select_related('user')[0]
    except (IndexError, Profile.DoesNotExist):
        raise Http404
    try:
        if request.method == 'POST':
            if prof.id == request.user.profile.id:
                user_form = EditUserForm(request.POST, instance=request.user)
                profile_form = EditProfileForm(request.POST, request.FILES,
                                               instance=request.user.profile,
                                               groups=request.user.groups,
                                               request=request)
                if user_form.is_valid() and profile_form.is_valid():
                    user_form.save()
                    prof = profile_form.save()
                    messages.add_message(request, messages.SUCCESS, 'Profil opdateret!')
                    return redirect("profile", username=prof.user.username)
                else:
                    start_edit = True
        else:
            if prof.id == request.user.profile.id:
                user_form = EditUserForm(instance=request.user)
                profile_form = EditProfileForm(instance=request.user.profile, groups=request.user.groups,
                                               request=request)
    except AttributeError:
        pass

    lan = Lan.get_next(request)
    try:
        lan_profile = prof.lanprofile_set.get(profile=prof, lan=lan)
    except LanProfile.DoesNotExist:
        lan_profile = None

    return render(request, 'profile.html', {'user_form': user_form, 'profile_form': profile_form,
                                            'profile': prof, 'start_edit': start_edit,
                                            'lan': lan, 'lan_profile': lan_profile})


def tournaments(request):
    lan = Lan.get_next(request=request)
    tournaments = Tournament.objects.filter(lan=lan).select_related('game').select_related('lan')
    games = defaultdict(list)
    for t in tournaments:
        if t.open or t.live or request.user.is_staff:
            games[t.game].append(t)

    if request.user.is_authenticated:
        if request.method == 'POST':
            if 'frameld' in request.POST:
                try:
                    team = TournamentTeam.objects.get(id=int(request.POST['frameld']),
                                                      profiles__in=[request.user.profile])
                    messages.add_message(request, messages.SUCCESS,
                                         'Holdet {} er blevet frameldt turneringen'.format(team.name))
                    team.delete()
                except (TournamentTeam.DoesNotExist, ValueError):
                    messages.add_message(request, messages.ERROR,
                                         'Der opstod en fejl. Prøv igen senere, eller kontakt LanCrew.')
                return redirect(reverse('tournaments'))

        teams = (TournamentTeam.objects.filter(tournament__lan=lan, profiles__in=[request.user.profile])
                 .prefetch_related('profiles__user')
                 .select_related('tournament')
                 .select_related('tournament__game'))
    else:
        teams = None
    return render(request, 'tournaments.html', {'games': dict(games), 'teams': teams})


def tournament(request, game, lan_id, name):
    t = get_object_or_404(Tournament, game__name=game, lan__id=lan_id, name=name)
    teams = TournamentTeam.objects.filter(tournament=t).prefetch_related('profiles__user')
    if request.user.is_authenticated:
        if request.method == 'POST':
            form = TournamentTeamForm(request.POST, tournament=t, profile=request.user.profile)
            if form.is_valid() and t.open:
                team = form.save()
                messages.add_message(request, messages.SUCCESS, 'Hold tilmeldt successfuldt!')
                send_tournament_mails(request, team)
                return redirect(reverse('tournament', kwargs={'game': game, 'lan_id': lan_id, 'name': name}))
        else:
            form = TournamentTeamForm(tournament=t, profile=request.user.profile)
    else:
        form = None
    return render(request, 'tournament.html', {'tournament': t, 'teams': teams, 'form': form})


def send_tournament_mails(request, team):
    site = 'https://htxaarhuslan.dk'  # Naughty naugthy hard code
    for p in team.profiles.all():
        p.user.email_user(
            '{} tilmeldt til {} på HTXAarhusLAN.dk'.format(team.name, team.tournament.name),
            render_to_string('tournament_mail.html', {'team': team, 'profile': p, 'site': site})
        )


def legacy(request):
    return render(request, 'legacy.html')


def needlogin(request):
    referrer = request.GET.get('next', None)
    if request.user.is_authenticated:
        if referrer is not None:
            return redirect(referrer)
        else:
            return redirect(reverse('index'))
    return render(request, 'needlogin.html')


def policy(request):
    return render(request, 'policy.html')


def food(request):
    orders = []
    lan = Lan.get_next(request=request)
    show = lan is not None and lan.is_open() and lan.food_open and request.user.is_authenticated
    if request.user.is_authenticated:
        prof = request.user.profile
        try:
            lp = LanProfile.objects.get(lan=lan, profile=prof)

            if request.method == 'POST':
                form = FoodOrderForm(request.POST, lanprofile=lp, profile=prof)
                if show and form.is_valid():
                    form.save()
                    messages.add_message(request, messages.SUCCESS,
                                         'Din bestilling er modtaget. Du kan nu betale.')
                    return redirect(reverse('food'))
            else:
                form = FoodOrderForm(lanprofile=lp, profile=prof)

            orders = FoodOrder.objects.filter(lanprofile=lp)

        except LanProfile.DoesNotExist:
            show = False
            form = None
    else:
        form = None
        prof = None
    return render(request, 'food.html', {'show': show, 'orders': orders, 'form': form, 'profile': prof})


def event(request, event_id):
    return render(request, 'event.html', {'event': get_object_or_404(Event, id=event_id)})


# Meta pages

@sensitive_post_parameters()
@sensitive_variables('username', 'password')
def login_view(request):
    """Post url for login form, always redirects the user back unless legacy."""
    referrer = request.GET.get('next', reverse('index'))
    if not is_safe_url(referrer, allowed_hosts=[request.get_host()], require_https=request.is_secure()):
        referrer = reverse('index')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user is not None:
            is_legacy = (user.date_joined < datetime(2016, 11, 22).replace(tzinfo=utc) and not user.last_login)
            login(request, user)
            if is_legacy:
                return redirect(reverse('legacy'))
        else:
            messages.add_message(request, messages.ERROR, 'Fejl i brugernavn eller kodeord')
    return redirect(referrer)


def logout_view(request):
    """Logout and redirect."""
    logout(request)
    referrer = request.GET.get('next', reverse('index'))
    if not is_safe_url(referrer, allowed_hosts=[request.get_host()], require_https=request.is_secure()):
        referrer = reverse('index')
    return redirect(referrer)


def frameld(request):
    """Framelds a user"""
    lan = Lan.get_next(request=request)
    success = False
    if request.method == 'POST':
        try:
            current = LanProfile.objects.get(lan=lan, profile=request.user.profile)
            success = current.delete(keep_parents=True)
            try:
                teams = TournamentTeam.objects.filter(tournament__lan=lan,
                                                      profiles__in=[request.user.profile])
                teams.delete()
            except (TournamentTeam.DoesNotExist, ValueError):
                pass
        except LanProfile.DoesNotExist:
            pass
        except AttributeError:
            pass
    if success:
        messages.add_message(request, messages.SUCCESS, "Du er nu frameldt LAN!")
    else:
        messages.add_message(request, messages.ERROR, "Der opstod en fejl med din framelding. Prøv igen senere.")
    return redirect(reverse("tilmeld"))


class ProfileAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return False

        lan = Lan.get_next()
        qs = Profile.objects.filter(lanprofile__lan=lan)

        exclude = [self.request.user.profile.id]
        for x in self.forwarded.values():
            try:
                exclude.append(int(x))
            except ValueError:
                pass
        qs = qs.exclude(pk__in=exclude)

        if self.q:
            qs = qs.filter(Q(user__username__icontains=self.q) |
                           Q(user__first_name__icontains=self.q) |
                           Q(grade__icontains=self.q))

        return qs

    def get_result_label(self, item):
        html = ''
        if item.photo:
            im = get_thumbnail(item.photo, '60x60', crop='center')
            if im:
                html += '<img src="{}" />'.format(im.url)
        html += '<span>{}</span><br><span>{}<span>&nbsp;({})</span></span>'.format(item.user.first_name,
                                                                                   item.user.username,
                                                                                   item.get_grade_display())
        return html


def calendar(request, feed_name):
    lan = Lan.get_next(request=request)
    events = []
    if feed_name == 'tournament':
        ts = Tournament.objects.filter(lan=lan, start__isnull=False)
    elif feed_name == 'misc':
        ts = Event.objects.filter(lan=lan, start__isnull=False)
    else:
        raise Http404
    for t in ts:
        url = ''
        if isinstance(t, Tournament):
            if not (t.live or t.open) or not t.show_on_calendar:
                continue
            url = t.get_absolute_url()
        elif isinstance(t, Event):
            url = t.url
            if (url == '' or url is None) and (t.text != '' and t.text is not None):
                url = t.get_absolute_url()
        evt = {
            'title': '{}'.format(t.name),
            'start': t.start.isoformat(),
            'id': t.pk,
        }
        if url:
            evt['url'] = url
        if t.end:
            evt['end'] = t.end.isoformat()
        events.append(evt)
    return JsonResponse(events, safe=False)


def payment(request, service, type, id):
    if request.user.is_authenticated:
        if service == 'mobilepay':
            if type == 'mad':
                order = get_object_or_404(FoodOrder, id=id)
                prof = order.lanprofile.profile
                lan = order.lanprofile.lan
                text = 'LAN mad'
                amount = order.price
            else:  # type == tilmelding
                lanprofile = get_object_or_404(LanProfile, id=id)
                prof = lanprofile.profile
                lan = lanprofile.lan
                text = 'LAN tilmelding'
                amount = lanprofile.lan.price
            if request.user == prof.user:
                if prof.phone:
                    send_mobilepay_request(lan=lan,
                                           profile=prof,
                                           type=text,
                                           amount=amount,
                                           id=id)
                    messages.add_message(request, messages.INFO,
                                         'En anmodning på {}kr. '
                                         'er blevet sendt til (+45) {}'.format(amount, prof.phone))
                else:
                    messages.add_message(request, messages.ERROR,
                                         'Fejl! Du har ikke skrevet noget telefonnummer på din profil!')
                referrer = request.GET.get('next', reverse('index'))
                return redirect(referrer)
    raise Http404

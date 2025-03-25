from django.utils import timezone
from datetime import datetime, timedelta

from api.fake_user import generate_fake_user
from api.models import SexualPreference
from matchmaking import models
from matchmaking.models import DateStatus
from matchmaking.views import generateDateOfDateFromDay, convertDateToJson
from datetime import time as dt_time
from datetime import date as dt_date
from datetime import datetime
from datetime import timedelta
from django.utils import timezone
from RealServer.tools import convertLocalTimeToUTC
from django.http import JsonResponse

def getHardcodedDates(user, day):
    if getattr(user, day + '_date') and getattr(user, day + '_date').expires_at >= timezone.now():
        return JsonResponse(convertDateToJson(user, getattr(user, day + '_date')), safe=False)

    match = generate_fake_user(SexualPreference.WOMEN.value, None, None)
    place = 'barcadia-dallas'
    category = 'drinks'
    time = dt_time(hour=18)
    local_midnight = convertLocalTimeToUTC(
        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
        user.timezone)
    date = models.Date(user1=user, user2=match, day=day, start_time=time,
                       date_of_date=generateDateOfDateFromDay(day),
                       expires_at=(local_midnight + timedelta(days=1)),
                       place_id=place,
                       category=category)
    date.original_expires_at = date.expires_at
    # Change who likes whom depending on the day
    if day == 'sun':
        date.user1_likes = DateStatus.UNDECIDED.value
        date.user2_likes = DateStatus.UNDECIDED.value
    elif day == 'mon':
        date.user1_likes = DateStatus.UNDECIDED.value
        date.user2_likes = DateStatus.LIKES.value
    elif day == 'tue':
        date.user1_likes = DateStatus.UNDECIDED.value
        date.user2_likes = DateStatus.PASS.value
    elif day == 'wed':
        date.user1_likes = DateStatus.LIKES.value
        date.user2_likes = DateStatus.UNDECIDED.value
    elif day == 'thur':
        date.user1_likes = DateStatus.LIKES.value
        date.user2_likes = DateStatus.LIKES.value
    elif day == 'fri':
        date.user1_likes = DateStatus.LIKES.value
        date.user2_likes = DateStatus.PASS.value
    elif day == 'sat':
        date.user1_likes = DateStatus.PASS.value
        date.user2_likes = DateStatus.LIKES.value
    date.save()
    setattr(user, day + '_date', date)
    setattr(match, day + '_date', date)
    user.save()
    match.save()
    mutual_friend = models.MutualFriend.objects.create(first_name='Matthew',
                                                       picture='https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn',
                                                       date=date)
    return JsonResponse(convertDateToJson(user, date), safe=False)
"""
respond_by = timezone.now() + timedelta(hours=24)
dates = {}
dates['sun'] = {
    'date':
        {
            'date_id': '1',
            'potential_date_likes': False,
            'primary_user_likes': 'undecided',
            'respond_by': respond_by.isoformat(),
            'match':
                {
                    'user_id': '1',
                    'name': 'Maksym',
                    'age': '27',
                    'occupation': 'World Traveler',
                    'education': 'Yale University',
                    'about': 'I\'m trying to be clever.',
                    'main_picture': 'https://realdatingbucket.s3.amazonaws.com/1829561367333153/sqbtyajqlhpb',
                    'detail_pictures': [
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/bvdtjxvqfhdo'
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/fhjkoiqciraw',
                    ],
                    'mutual_friends': [
                        {'friend':
                             {
                                 'name': 'Matthew',
                                 'picture': 'https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn'
                             }
                         }
                    ]
                },
            'time':
                {
                    'day': 'sun',
                    'start_time': '7:00pm'
                },
            'place':
                {
                    'place_id': 'barcadia-dallas',
                }
        }
    }

dates['mon'] = {
    'date':
        {
            'date_id': '2',
            'potential_date_likes': True,
            'primary_user_likes': 'undecided',
            'respond_by': respond_by.isoformat(),
            'match':
                {
                    'user_id': '1',
                    'name': 'Maksym',
                    'age': '27',
                    'occupation': 'World Traveler',
                    'education': 'Yale University',
                    'about': 'I\'m trying to be clever.',
                    'main_picture': 'https://realdatingbucket.s3.amazonaws.com/1829561367333153/sqbtyajqlhpb',
                    'detail_pictures': [
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/bvdtjxvqfhdo'
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/fhjkoiqciraw',
                    ],
                    'mutual_friends': [
                        {'friend':
                             {
                                 'name': 'Matthew',
                                 'picture': 'https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn'
                             }
                         }
                    ]
                },
            'time':
                {
                    'day': 'mon',
                    'start_time': '9:00pm'
                },
            'place':
                {
                    'place_id': 'barcadia-dallas',
                }
        }
    }

dates['tue'] = {
    'date':
        {
            'date_id': '3',
            'potential_date_likes': False,
            'primary_user_likes': 'pass',
            'respond_by': respond_by.isoformat(),
            'match':
                {
                    'user_id': '1',
                    'name': 'Maksym',
                    'age': '27',
                    'occupation': 'World Traveler',
                    'education': 'Yale University',
                    'about': 'I\'m trying to be clever.',
                    'main_picture': 'https://realdatingbucket.s3.amazonaws.com/1829561367333153/sqbtyajqlhpb',
                    'detail_pictures': [
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/bvdtjxvqfhdo'
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/fhjkoiqciraw',
                    ],
                    'mutual_friends': [
                        {'friend':
                             {
                                 'name': 'Matthew',
                                 'picture': 'https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn'
                             }
                         }
                    ]
                },
            'time':
                {
                    'day': 'tue',
                    'start_time': '10:00pm'
                },
            'place':
                {
                    'place_id': 'barcadia-dallas',
                }
        }
    }

dates['wed'] = {
    'date':
        {
            'date_id': '4',
            'potential_date_likes': False,
            'primary_user_likes': 'undecided',
            'respond_by': respond_by.isoformat(),
            'match':
                {
                    'user_id': '1',
                    'name': 'Maksym',
                    'age': '27',
                    'occupation': 'World Traveler',
                    'education': 'Yale University',
                    'about': 'I\'m trying to be clever.',
                    'main_picture': 'https://realdatingbucket.s3.amazonaws.com/1829561367333153/sqbtyajqlhpb',
                    'detail_pictures': [
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/bvdtjxvqfhdo'
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/fhjkoiqciraw',
                    ],
                    'mutual_friends': [
                        {'friend':
                             {
                                 'name': 'Matthew',
                                 'picture': 'https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn'
                             }
                         }
                    ]
                },
            'time':
                {
                    'day': 'wed',
                    'start_time': '12:00pm'
                },
            'place':
                {
                    'place_id': 'barcadia-dallas',
                }
        }
    }

dates['thur'] = {
    'date':
        {
            'date_id': '5',
            'potential_date_likes': False,
            'primary_user_likes': 'undecided',
            'respond_by': respond_by.isoformat(),
            'match':
                {
                    'user_id': '1',
                    'name': 'Maksym',
                    'age': '27',
                    'occupation': 'World Traveler',
                    'education': 'Yale University',
                    'about': 'I\'m trying to be clever.',
                    'main_picture': 'https://realdatingbucket.s3.amazonaws.com/1829561367333153/sqbtyajqlhpb',
                    'detail_pictures': [
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/bvdtjxvqfhdo'
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/fhjkoiqciraw',
                    ],
                    'mutual_friends': [
                        {'friend':
                             {
                                 'name': 'Matthew',
                                 'picture': 'https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn'
                             }
                         }
                    ]
                },
            'time':
                {
                    'day': 'thur',
                    'start_time': '2:00pm'
                },
            'place':
                {
                    'place_id': 'barcadia-dallas',
                }
        }
    }

dates['fri'] = {
    'date':
        {
            'date_id': '6',
            'potential_date_likes': True,
            'primary_user_likes': 'likes',
            'last_sent_message': 'OMG I\'m so excited for our date!',
            'respond_by': respond_by.isoformat(),
            'match':
                {
                    'user_id': '1',
                    'name': 'Maksym',
                    'age': '27',
                    'occupation': 'World Traveler',
                    'education': 'Yale University',
                    'about': 'I\'m trying to be clever.',
                    'main_picture': 'https://realdatingbucket.s3.amazonaws.com/1829561367333153/sqbtyajqlhpb',
                    'detail_pictures': [
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/bvdtjxvqfhdo'
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/fhjkoiqciraw',
                    ],
                    'mutual_friends': [
                        {'friend':
                             {
                                 'name': 'Matthew',
                                 'picture': 'https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn'
                             }
                         }
                    ]
                },
            'time':
                {
                    'day': 'fri',
                    'start_time': '2:00pm'
                },
            'place':
                {
                    'place_id': 'white-rock-lake-dallas',
                }
        }
    }

dates['sat'] = {
    'date':
        {
            'date_id': '7',
            'potential_date_likes': False,
            'primary_user_likes': 'likes',
            'respond_by': respond_by.isoformat(),
            'match':
                {
                    'user_id': '1',
                    'name': 'Maksym',
                    'age': '27',
                    'occupation': 'World Traveler',
                    'education': 'Yale University',
                    'about': 'I\'m trying to be clever.',
                    'main_picture': 'https://realdatingbucket.s3.amazonaws.com/1829561367333153/sqbtyajqlhpb',
                    'detail_pictures': [
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/bvdtjxvqfhdo'
                        'https://realdatingbucket.s3.amazonaws.com/1829561367333153/fhjkoiqciraw',
                    ],
                    'mutual_friends': [
                        {'friend':
                             {
                                 'name': 'Matthew',
                                 'picture': 'https://realdatingbucket.s3.amazonaws.com/2959531196950/rgifzhzprsmn'
                             }
                         }
                    ]
                },
            'time':
                {
                    'day': 'sat',
                    'start_time': '2:00pm'
                },
            'place':
                {
                    'place_id': 'white-rock-lake-dallas',
                }
        }
    }
"""
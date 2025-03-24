from json import JSONDecodeError
from django.http import HttpResponse, Http404, JsonResponse
from django.views.decorators.http import require_http_methods, require_GET
from django.views.decorators.csrf import csrf_exempt
import json
import os
import requests


""" 
REST endpoints for HMS django frontend and proxy functions
"""

request_header = {"User-Agent": "Mozilla/5.0"}


@require_GET
def delineate_watershed(request):
    request_query = request.GET.dict()
    latitude = request_query["latitude"]
    longitude = request_query["longitude"]
    url = "https://streamstats.usgs.gov/streamstatsservices/watershed.geojson?rcode=NY&xlocation={0}&ylocation={1}&crs=4326&includeparameters=false&includeflowtypes=false&includefeatures=true&simplify=true"\
        .format(longitude, latitude)
    data = requests.request(method="get", url=url)
    json_data = json.loads(data.content.decode('utf-8', "ignore"))
    return HttpResponse(content=json.dumps(json_data), content_type="application/json")


@csrf_exempt
def pass_through_proxy(request, module):
    if os.environ['HMS_LOCAL'] == "True" and os.environ["IN_DOCKER"] == "False":
        proxy_url = "http://localhost:60050/api/" + module
    else:
        # proxy_url = os.environ.get('HMS_BACKEND_SERVER') + "/HMSWS/api/" + module
        proxy_url = str(os.environ.get('HMS_BACKEND_SERVER_INTERNAL')) + "/api/" + module
        # proxy_url = str(os.environ.get('HMS_BACKEND_SERVER_DOCKER')) + "/HMSWS/api/" + module
    method = str(request.method)
    print("HMS proxy: " + method + " url: " + proxy_url)
    if method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except JSONDecodeError as e:
            return HttpResponse(
                {
                    "POST Data ERROR": "POST request body was not valid or the type specified was not json. Error message: " + str(e)
                }
            )
        hms_request = requests.request("post", proxy_url, json=data, timeout=120)
        return HttpResponse(hms_request, content_type="application/json")
    elif method == "GET":
        hms_request = requests.request("get", proxy_url, timeout=120)
        return HttpResponse(hms_request, content_type="application/json")
    else:
        print("Django to Flask proxy url invalid.")
        raise Http404


@csrf_exempt
@require_http_methods(["GET", "POST"])
def flask_proxy(request, flask_url):
    if os.environ["HMS_LOCAL"] == "True" and os.environ["IN_DOCKER"] == "False":
        proxy_url = "http://localhost:7777" + "/" + flask_url
    else:
        proxy_url = os.environ.get('UBERTOOL_REST_SERVER') + "/" + flask_url
        # proxy_url = 'http://qed_flask:7777/' + flask_url
    method = str(request.method)
    print("Django to Flask proxy method: " + method + " url: " + proxy_url)
    if method == "POST":
        proxy_url = proxy_url + "/"
        flask_request = requests.request("post", proxy_url, data=request.POST, timeout=120)
        return HttpResponse(flask_request, content_type="application/json")
    elif method == "GET":
        proxy_url += "?" + request.GET.urlencode()
        flask_request = requests.request("get", proxy_url, timeout=120)
        return HttpResponse(flask_request, content_type="application/json")
    else:
        print("Django to Flask proxy url invalid.")
        raise Http404

@csrf_exempt
@require_http_methods(["POST"])
def flask_proxy_v3(request, model):
    if os.environ["HMS_LOCAL"] == "True" and os.environ["IN_DOCKER"] == "False":
        proxy_url = "http://localhost:7777" + "/hms/proxy/" + model
    else:
        # proxy_url = 'http://qed_flask:7777/hms/proxy/' + model
        proxy_url = os.environ.get('UBERTOOL_REST_SERVER') + "/hms/proxy/" + model
    method = str(request.method)
    print("Django to Flask proxy method: " + method + " url: " + proxy_url)
    if method == "POST":
        if len(request.POST) == 0:
            try:
                data = json.loads(request.body)
            except JSONDecodeError:
                return Http404
        else:
            data = request.POST
        proxy_url = proxy_url + "/"
        flask_request = requests.request("post", proxy_url, json=data, timeout=120, headers=request_header)
        return HttpResponse(flask_request, content_type="application/json")
    else:
        print("Django to Flask proxy url invalid.")
        raise Http404

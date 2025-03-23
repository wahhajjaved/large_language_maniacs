from collections import namedtuple
from django.utils.translation import ugettext
from barcode.writer import SVGWriter, ImageWriter
from django.http.response import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render, get_object_or_404
import barcode
from kirppu.app.models import Item, Event, CommandCode


def index(request):
    return HttpResponse("")


def get_items(request, sid):
    """
    Get a page containing all items for vendor.

    :param request: HttpRequest object.
    :type request: django.http.request.HttpRequest
    :param sid: Vendor ID
    :type sid: str
    :return: HttpResponse or HttpResponseBadRequest
    """
    # TODO: This view should filter by event and vendor__index | vendor__id
    bar_type = request.GET.get("format", "svg").lower()

    if bar_type not in ('svg', 'png'):
        return HttpResponseBadRequest(u"Image extension not supported")

    sid = int(sid)
    items = Item.objects.filter(seller__id=sid).exclude(code=u"")

    if not items:
        return HttpResponseBadRequest(u"No items for this vendor found.")
    

    return render(request, "app_items.html", {'items': items, 'bar_type': bar_type})


def get_item_image(request, iid, ext):
    """
    Get a barcode image for given item.

    :param request: HttpRequest object
    :type request: django.http.request.HttpRequest
    :param iid: Item identifier
    :type iid: str
    :param ext: Extension/image type to be used
    :type ext: str
    :return: Response containing raw image data
    :rtype: HttpResponse
    """
    ext = ext.lower()
    if len(ext) == 0:
        ext = "svg"
    if ext not in ('svg', 'png'):
        return HttpResponseBadRequest(u"Image extension not supported")

    if ext == 'svg':
        writer, mimetype = SVGWriter(), 'image/svg+xml'
    else:
        writer, mimetype = ImageWriter(), 'image/png'

    item = get_object_or_404(Item, code=iid)
    bar = barcode.Code128(item.code, writer=writer)

    response = HttpResponse(mimetype=mimetype)
    bar.write(response, {
        'text_distance': 4,
        'module_height': 10,
        'module_width': 0.4,
    })

    return response


def get_commands(request, eid):
    bar_type = request.GET.get("format", "svg").lower()

    if bar_type not in ('svg', 'png'):
        return HttpResponseBadRequest(u"Image extension not supported")

    eid = int(eid)
    event = get_object_or_404(Event, pk=eid)
    items = []
    code_item = namedtuple("CodeItem", "name code action")

    for c in event.clerks.all():
        code = event.get_clerk_code(c)
        name = c.get_short_name()
        if len(name) == 0:
            name = c.get_username()

        cc = CommandCode.encode_code(CommandCode.START_CLERK, code)
        items.append(code_item(name=name, code=cc, action=ugettext(u"Start")))

        cc = CommandCode.encode_code(CommandCode.END_CLERK, code)
        items.append(code_item(name=name, code=cc, action=ugettext(u"End")))

    return render(request, "app_clerks.html", {'items': items, 'bar_type': bar_type})


def get_command_image(request, iid, ext):
    """
    Get a barcode image for given item.

    :param request: HttpRequest object
    :type request: django.http.request.HttpRequest
    :param iid: Item identifier
    :type iid: str
    :param ext: Extension/image type to be used
    :type ext: str
    :return: Response containing raw image data
    :rtype: HttpResponse
    """
    ext = ext.lower()
    if len(ext) == 0:
        ext = "svg"
    if ext not in ('svg', 'png'):
        return HttpResponseBadRequest(u"Image extension not supported")

    if ext == 'svg':
        writer, mimetype = SVGWriter(), 'image/svg+xml'
    else:
        writer, mimetype = ImageWriter(), 'image/png'

    bar = barcode.Code128(iid, writer=writer)

    response = HttpResponse(mimetype=mimetype)
    bar.write(response, {
        'text_distance': 4,
        'module_height': 10,
        'module_width': 0.4,
    })

    return response


def registry_view(request, eid):
    """
    Registry view.

    :param request: HttpRequest object
    :type request: django.http.request.HttpRequest
    :param eid: Event id number
    :type eid: str
    :return: Response containing the view.
    :rtype: HttpResponse
    """
    return render(request, "app_registry.html")


def registry_add_item(request, eid):
    """
    Add item to receipt. Expects item code in POST.code and receipt id in
    POST.receipt.

    :param request: HttpRequest object
    :type request: django.http.request.HttpRequest
    :param eid:
    :type eid: str
    :rtype: HttpResponse
    """
    pass


def registry_del_item(request, eid):
    """
    Remove item from receipt. Expects item code in POST.code and receipt id
    in POST.receipt.

    :param request: HttpRequest object.
    :type request: django.http.request.HttpRequest
    :param eid:
    :type eid: str
    :rtype: HttpResponse
    """
    pass


def registry_finish_receipt(request, eid):
    """
    Finish receipt. Expects receipt id in POST.receipt.

    :param request: HttpRequest object.
    :type request: django.http.request.HttpRequest
    :param eid:
    :type eid: str
    :rtype: HttpResponse
    """
    pass

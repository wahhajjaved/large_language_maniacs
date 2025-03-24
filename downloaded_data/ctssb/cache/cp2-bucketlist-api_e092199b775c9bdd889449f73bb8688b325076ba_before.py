from datetime import datetime

from flask import jsonify, request
from flask_restful import Resource

from app.auth import authenticate_token
from app.models import (db, BucketList, BucketListItem,
                        BucketlistItemSchema)

schema = BucketlistItemSchema()


def get_bucketlist(bucketlist_id):
        bucketlist = BucketList.query.get(bucketlist_id)
        if bucketlist:
            return bucketlist
        else:
            return None


def get_bucketlist_item(item_id):
        """Gets buckelist item with
        the id <item_id>"""
        item = BucketListItem.query.get(item_id)
        if item:
            return item
        else:
            return False


class BucketListItems(Resource):
    """This class creates the endpoints
    for creating and getting bucketlists.
    """

    def post(self, bucketlist_id):
        """Creates new bucketlist item"""
        authenticate_token(request)
        data = request.get_json(silent=True)
        try:
            name = data["name"]
        except Exception:
            return {"error": "Item has no data"}, 400
        exists = db.session.query(BucketListItem).filter_by(
            name=name).scalar() is not None
        if not exists:
            new_item = BucketListItem(name, bucketlist_id)
            db.session.add(new_item)
            db.session.commit()
            return {"message": "created new item",
                    "name": "{}".format(name)}, 201
        else:
            return {"error": "Item already exists"}

    def get(self, bucketlist_id):
        """Gets all buckelist items"""
        authenticate_token(request)
        bucketlist = get_bucketlist(bucketlist_id)
        if bucketlist:
            items = BucketListItem.query.filter_by(bucketlist_id=bucketlist_id)
            items_list = []
            for item in items:
                item_json = schema.dump(item)
                items_list.append(item_json.data)
            return jsonify(items_list)
        else:
            return {"error": "bucketlist not found"}, 404


class BucketListItemSingle(Resource):
    """This class creates the endpoints
    for updating and deleting bucketlists.
    """

    def get(self, bucketlist_id, item_id):
        """Gets a item with the id <item_id>
        for buckelist with the id <bucketlist_id>"""
        authenticate_token(request)
        item = get_bucketlist_item(item_id)
        if item:
            item_json = schema.dump(item)
            return jsonify(item_json.data)
        else:
            return {"error": "Item not found"}, 404

    def put(self, bucketlist_id, item_id):
        """Edits buckelist item"""
        authenticate_token(request)
        item = get_bucketlist_item(item_id)
        if item:
            data = request.get_json(silent=True)
            try:
                new_name = data["name"]
                done = data["done"]
            except Exception:
                return {"error": "'name' or 'done' key is missing"}, 400
            item.name = new_name
            item.date_modified = datetime.utcnow()
            item.done = done
            db.session.add(item)
            db.session.commit()
            return {"message": "Modified item {0}".format(item.id)}
        else:
            return {"error": "Item not found"}, 404

    def delete(self, bucketlist_id, item_id):
        """Deletes bucketlist item"""
        authenticate_token(request)
        item = get_bucketlist_item(bucketlist_id)
        if item:
            db.session.delete(item)
            db.session.commit()
            return {"message": "Deleted item {0}"
                    .format(bucketlist_id)}, 204
        else:
            return {"error": "Item not found"}, 404

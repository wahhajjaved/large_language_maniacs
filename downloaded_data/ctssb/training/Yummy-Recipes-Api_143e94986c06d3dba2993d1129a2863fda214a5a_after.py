"""module to create pagination"""
from flask import url_for, jsonify

class PaginationHelper():
    """helper class to generate paginated list of items"""
    def __init__(self, request, query, resource_for_url, key_name, schema):
        self.request = request
        self.query = query
        self.resource_for_url = resource_for_url
        self.key_name = key_name
        self.schema = schema

    def paginate_query(self):
        """method to query data from database object"""
        # If no page number is specified, we assume the request wants page #1
        page_number = self.request.args.get("page", default=1, type=int)
        results_per_page = self.request.args.get("limit", default=5, type=int)
        paginated_objects = self.query.paginate(page_number, per_page=results_per_page, \
                                                error_out=False)
        objects = paginated_objects.items

        if paginated_objects.has_prev:
            previous_page_url = url_for(self.resource_for_url, page=page_number-1, _external=True)
        else:
            previous_page_url = None

        if paginated_objects.has_next:
            next_page_url = url_for(self.resource_for_url, page=page_number+1, _external=True)
        else:
            next_page_url = None

        dumped_objects = self.schema.dump(objects, many=True).data
        return ({self.key_name: dumped_objects, 'previous': previous_page_url, \
                'next': next_page_url, 'items': paginated_objects.total, \
                'pages': paginated_objects.pages, 'page':paginated_objects.page})
    @staticmethod
    def display(name, page, result):
        """function to view category"""
        if page and not isinstance(page, str):
            if page > result['pages'] and result['pages'] > 0 and isinstance(page, str) or page > result['pages']:
                response = jsonify({"message":"invalid search or page doesn't exist!"}), 404
            else:
                if result['items'] > 0:
                    response = jsonify({name:result}), 200
                else:
                    response = jsonify({"message": 'No {} found!'.format(name)}), 404
        else:
            response = jsonify({"message":"invalid page number!"}), 404
        return response

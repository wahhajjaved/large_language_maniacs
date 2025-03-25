import json
from rest_framework.response import Response
from kitchenrock_api.models.food_recipe import FoodRecipe, FoodMaterial
from kitchenrock_api.models.user import User
from kitchenrock_api.permissions import IsAuthenticated
from kitchenrock_api.serializers.food_category import CategorySerializer
from kitchenrock_api.serializers.food_recipe import FoodRecipeSerializer
from kitchenrock_api.serializers.materials import MaterialsSerializer
from kitchenrock_api.serializers.review import ReviewSerializer
from kitchenrock_api.serializers.user import UserSerializer
from kitchenrock_api.services.food_recipe import FoodRecipeService
from kitchenrock_api.views import BaseViewSet
from rest_framework.decorators import list_route,detail_route

class FoodRecipeViewSet(BaseViewSet):
    view_set = 'foodrecipe'
    serializer_class = FoodRecipeSerializer
    permission_classes = (IsAuthenticated,)
    # permission_classes = ()

    def retrieve(self,request, *args, **kwargs):
        """
        @apiVersion 1.0.0
        @api {GET} /foodrecipe/<pk> Cong thuc mon an có pk
        @apiName CTMA
        @apiGroup FoodRecipes
        @apiPermission User

        @apiHeader {number} Type Device type (1: Mobile, 2: Android phone, 3: IOS phone, 4: Window phone, 5: Android tablet, 6: IOS tablet, 7: Mobile web, tablet web, 8: Desktop web)
        @apiHeader {string} Device Required, Device id, If from browser, please use md5 of useragent.
        @apiHeader {string} Appid Required
        @apiHeader {string} Agent Optional
        @apiHeader {string} Authorization Required. format: token <token_string>
        @apiHeaderExample {json} Request Header Authenticated Example:
        {
            "Type": 1,
            "Device": "postman-TEST",
            "Appid": "1",
            "Agent": "Samsung A5 2016, Android app, build_number other_info",
            "Authorization": "token QS7VF3JF29K22U1IY7LAYLNKRW66BNSWF9CH4BND"
        }
        @apiSuccess {json} result
        @apiSuccess {boolean} result.is_favourite Is this food favourite?
        @apiSuccess {number} food.id id of FR
        @apiSuccess {string} food.name name of FR
        @apiSuccess {string} food.picture picture link of FR
        @apiSuccess {int} food.level Level of FR
        @apiSuccess {string} food.prepare_time Prepare time
        @apiSuccess {string} food.cook_time execution time
        @apiSuccess {string} food.method How to do FR
        @apiSuccess {int} food.lovers Lover number
        @apiSuccess {date} food.create_date Create date
        @apiSuccess {int} food.serve How many people for FR?
        @apiSuccess {int} result.materials.material_id id of material
        @apiSuccess {string} result.materials.name name of material
        @apiSuccess {string} result.materials.unit unit of material
        @apiSuccess {int} result.materials.value value of material
        @apiSuccess {json[]} result.categories Food Categories
        @apiSuccess {int} result.categories.id ID Food Categories
        @apiSuccess {string} result.categories.name Name of Food Categories
        @apiSuccess {json[]} result.nutritions  Food nutritions
        @apiSuccess {int} result.nutritions.nutrition_id id of Food nutrition
        @apiSuccess {string} result.nutritions.name name of Food nutrition
        @apiSuccess {string} result.nutritions.value value of Food nutrition
        """
        pk = kwargs.get('pk')
        id_user = request.user.id
        foodrecipe = FoodRecipe.objects.get(pk=pk)
        user = User.objects.filter(foodrecipe=pk, pk=id_user)
        serializer = self.serializer_class(foodrecipe)
        result = serializer.data.copy()
        result['materials'] = FoodRecipeService.get_material(foodrecipe)
        result['categories'] = FoodRecipeService.get_category(foodrecipe)
        result['nutritions'] = FoodRecipeService.get_nutrition(foodrecipe)
        # if user_id and food recipes are exists in favourite foods table
        result['is_favourite'] = FoodRecipeService.get_favourite(id_user,pk)
        return Response(result)


    def list(self,request, **kwargs):
        """
        @apiVersion 1.0.0
        @api {GET} /foodrecipe List Cong thuc mon an
        @apiName ListCTMA
        @apiGroup FoodRecipes
        @apiPermission User

        @apiHeader {number} Type Device type (1: Mobile, 2: Android phone, 3: IOS phone, 4: Window phone, 5: Android tablet, 6: IOS tablet, 7: Mobile web, tablet web, 8: Desktop web)
        @apiHeader {string} Device Required, Device id, If from browser, please use md5 of useragent.
        @apiHeader {string} Appid Required
        @apiHeader {string} Agent Optional
        @apiHeader {string} Authorization Required. format: token <token_string>
        @apiHeaderExample {json} Request Header Authenticated Example:
        {
            "Type": 1,
            "Device": "postman-TEST",
            "Appid": "1",
            "Agent": "Samsung A5 2016, Android app, build_number other_info",
            "Authorization": "token QS7VF3JF29K22U1IY7LAYLNKRW66BNSWF9CH4BND"
        }
        @apiSuccess {object[]} food
        @apiSuccess {number} food.id id of FR
        @apiSuccess {string} food.name name of FR
        @apiSuccess {string} food.picture picture link of FR
        @apiSuccess {int} food.level Level of FR
        @apiSuccess {string} food.prepare_time Prepare time
        @apiSuccess {string} food.cook_time execution time
        @apiSuccess {string} food.method How to do FR
        @apiSuccess {int} food.lovers Lover number
        @apiSuccess {date} food.create_date Create date
        @apiSuccess {int} food.serve How many people for FR?
        @apiSuccess {boolean} food.is_favourite Is this food favourite?
        """
        kwargs['limit'] = int(request.query_params.get('limit', '30'))
        kwargs['offset'] = int(request.query_params.get('offset', '0'))
        kwargs['search'] = request.query_params.get('search', None)

        list_food = FoodRecipeService.get_list(**kwargs)
        if len(list_food) == 0:
            return Response({
                'message': 'Không có dữ liệu'
            })
        list_result = []
        for obj in list_food:
            serializer = self.serializer_class(obj)
            item = serializer.data.copy()
            item['is_favourite'] = FoodRecipeService.get_favourite(request.user.id, item['id'])
            list_result.append(item)
        return Response(list_result)

    @list_route(methods=['get'])
    def list_top(self,request, **kwargs):
        """
        @apiVersion 1.0.0
        @api {GET} /foodrecipe/list_top List 10 Cong thuc mon an được yêu thích nhất
        @apiName List_topCTMA
        @apiGroup FoodRecipes
        @apiPermission User

        @apiHeader {number} Type Device type (1: Mobile, 2: Android phone, 3: IOS phone, 4: Window phone, 5: Android tablet, 6: IOS tablet, 7: Mobile web, tablet web, 8: Desktop web)
        @apiHeader {string} Device Required, Device id, If from browser, please use md5 of useragent.
        @apiHeader {string} Appid Required
        @apiHeader {string} Agent Optional
        @apiHeader {string} Authorization Required. format: token <token_string>
        @apiHeaderExample {json} Request Header Authenticated Example:
        {
            "Type": 1,
            "Device": "postman-TEST",
            "Appid": "1",
            "Agent": "Samsung A5 2016, Android app, build_number other_info",
            "Authorization": "token QS7VF3JF29K22U1IY7LAYLNKRW66BNSWF9CH4BND"
        }
        @apiSuccess {object[]} food
        @apiSuccess {number} food.id id of FR
        @apiSuccess {string} food.name name of FR
        @apiSuccess {string} food.picture picture link of FR
        @apiSuccess {int} food.level Level of FR
        @apiSuccess {string} food.prepare_time Prepare time
        @apiSuccess {string} food.cook_time execution time
        @apiSuccess {string} food.method How to do FR
        @apiSuccess {int} food.lovers Lover number
        @apiSuccess {date} food.create_date Create date
        @apiSuccess {int} food.serve How many people for FR?
        @apiSuccess {boolean} food.is_favourite Is this food favourite?
        """
        kwargs['limit'] = int(request.query_params.get('limit', '10'))
        kwargs['search'] = request.query_params.get('search', None)

        kwargs['order'] = '-lovers'
        list_food = FoodRecipeService.get_list(**kwargs)
        if len(list_food) == 0:
            return Response({
                'message': 'Không có dữ liệu'
            })
        list_result = []
        for obj in list_food:
            serializer = self.serializer_class(obj)
            item = serializer.data.copy()
            item['is_favourite'] = FoodRecipeService.get_favourite(request.user.id, item['id'])
            list_result.append(item)
        return Response(list_result)

    @detail_route(methods=['get'])
    def list_by_category(self, request, **kwargs):
        """
        @apiVersion 1.0.0
        @api {GET} /foodrecipe/<pk>/list_by_category  List Cong thuc mon an theo category
        @apiName List_catCTMA
        @apiGroup FoodRecipes
        @apiPermission User

        @apiHeader {number} Type Device type (1: Mobile, 2: Android phone, 3: IOS phone, 4: Window phone, 5: Android tablet, 6: IOS tablet, 7: Mobile web, tablet web, 8: Desktop web)
        @apiHeader {string} Device Required, Device id, If from browser, please use md5 of useragent.
        @apiHeader {string} Appid Required
        @apiHeader {string} Agent Optional
        @apiHeader {string} Authorization Required. format: token <token_string>
        @apiHeaderExample {json} Request Header Authenticated Example:
        {
            "Type": 1,
            "Device": "postman-TEST",
            "Appid": "1",
            "Agent": "Samsung A5 2016, Android app, build_number other_info",
            "Authorization": "token QS7VF3JF29K22U1IY7LAYLNKRW66BNSWF9CH4BND"
        }
        @apiSuccess {object[]} food
        @apiSuccess {number} food.id id of FR
        @apiSuccess {string} food.name name of FR
        @apiSuccess {string} food.picture picture link of FR
        @apiSuccess {int} food.level Level of FR
        @apiSuccess {string} food.prepare_time Prepare time
        @apiSuccess {string} food.cook_time execution time
        @apiSuccess {string} food.method How to do FR
        @apiSuccess {int} food.lovers Lover number
        @apiSuccess {date} food.create_date Create date
        @apiSuccess {int} food.serve How many people for FR?
        @apiSuccess {boolean} result.is_favourite Is this food favourite?
        """
        kwargs['limit'] = int(request.query_params.get('limit', '30'))
        kwargs['offset'] = int(request.query_params.get('offset', '0'))
        kwargs['search'] = request.query_params.get('search', None)
        pk = kwargs.get('pk')
        list_food = FoodRecipeService.get_list_by_category(pk,**kwargs)
        if len(list_food) == 0:
            return Response({
                'message': 'Không có dữ liệu'
            })
        list_result = []
        for obj in list_food:
            serializer = self.serializer_class(obj)
            item = serializer.data.copy()
            item['is_favourite'] = FoodRecipeService.get_favourite(request.user.id, item['id'])
            list_result.append(item)
        return Response(list_result)

    @list_route(methods=['get'])
    def list_by_user(self, request, **kwargs):
        """
        @apiVersion 1.0.0
        @api {GET} /foodrecipe/list_by_user  List Cong thuc mon an được  user yêu thích
        @apiName List_favouriteCTMA
        @apiGroup FoodRecipes
        @apiPermission User

        @apiHeader {number} Type Device type (1: Mobile, 2: Android phone, 3: IOS phone, 4: Window phone, 5: Android tablet, 6: IOS tablet, 7: Mobile web, tablet web, 8: Desktop web)
        @apiHeader {string} Device Required, Device id, If from browser, please use md5 of useragent.
        @apiHeader {string} Appid Required
        @apiHeader {string} Agent Optional
        @apiHeader {string} Authorization Required. format: token <token_string>
        @apiHeaderExample {json} Request Header Authenticated Example:
        {
            "Type": 1,
            "Device": "postman-TEST",
            "Appid": "1",
            "Agent": "Samsung A5 2016, Android app, build_number other_info",
            "Authorization": "token QS7VF3JF29K22U1IY7LAYLNKRW66BNSWF9CH4BND"
        }
        @apiSuccess {object[]} food
        @apiSuccess {number} food.id id of FR
        @apiSuccess {string} food.name name of FR
        @apiSuccess {string} food.picture picture link of FR
        @apiSuccess {int} food.level Level of FR
        @apiSuccess {string} food.prepare_time Prepare time
        @apiSuccess {string} food.cook_time execution time
        @apiSuccess {string} food.method How to do FR
        @apiSuccess {int} food.lovers Lover number
        @apiSuccess {date} food.create_date Create date
        @apiSuccess {int} food.serve How many people for FR?
        """
        kwargs['limit'] = int(request.query_params.get('limit', '30'))
        kwargs['offset'] = int(request.query_params.get('offset', '0'))
        kwargs['search'] = request.query_params.get('search', None)
        pk = request.user.id
        list_result = User.objects.get(pk=pk).foodrecipe.all()
        if len(list_result) == 0:
            return Response({
                'message': 'Không có dữ liệu'
            })
        serializer = self.serializer_class(list_result, many=True)
        return Response(serializer.data)

    @detail_route(methods=['get'])
    def reviews(self,request,*args, **kwargs):
        """
        @apiVersion 1.0.0
        @api {GET} /foodrecipe/<pk>/reviews  List comment
        @apiName ListComment
        @apiGroup FoodRecipes
        @apiPermission User

        @apiHeader {number} Type Device type (1: Mobile, 2: Android phone, 3: IOS phone, 4: Window phone, 5: Android tablet, 6: IOS tablet, 7: Mobile web, tablet web, 8: Desktop web)
        @apiHeader {string} Device Required, Device id, If from browser, please use md5 of useragent.
        @apiHeader {string} Appid Required
        @apiHeader {string} Agent Optional
        @apiHeader {string} Authorization Required. format: token <token_string>
        @apiHeaderExample {json} Request Header Authenticated Example:
        {
           "Type": 1,
           "Device": "postman-TEST",
           "Appid": "1",
           "Agent": "Samsung A5 2016, Android app, build_number other_info",
           "Authorization": "token QS7VF3JF29K22U1IY7LAYLNKRW66BNSWF9CH4BND"
        }
        @apiSuccess {object[]} result
        @apiSuccess {int} result.star
        @apiSuccess {string} result.content
        @apiSuccess {date} result.create_date
        @apiSuccess {string} result.foodrecipe
        @apiSuccess {string} result.user
        """
        kwargs['limit'] = int(request.query_params.get('limit', '5'))
        kwargs['offset'] = int(request.query_params.get('offset', '0'))
        list_result = FoodRecipeService.get_list_review( **kwargs)
        if len(list_result) == 0:
            return Response({
                'message': 'Không có dữ liệu'
            })
        list_reviews = []
        for obj in list_result:
            serializer = ReviewSerializer(obj)
            item = serializer.data.copy()
            item['user'] = UserSerializer(obj.user).data.copy()
            list_reviews.append(item)
        return Response(list_reviews)

    @list_route(methods=['put'])
    def favourite(self, request, *args, **kwargs):
        """
        @apiVersion 1.0.0
        @api {PUT} /foodrecipe/favourite  Favourite
        @apiName MakeFavouriteFood
        @apiGroup FoodRecipes
        @apiPermission User

        @apiHeader {number} Type Device type (1: Mobile, 2: Android phone, 3: IOS phone, 4: Window phone, 5: Android tablet, 6: IOS tablet, 7: Mobile web, tablet web, 8: Desktop web)
        @apiHeader {string} Device Required, Device id, If from browser, please use md5 of useragent.
        @apiHeader {string} Appid Required
        @apiHeader {string} Agent Optional
        @apiHeader {string} Authorization Optional. format: token <token_string>
        @apiHeaderExample {json} Request Header Authenticated Example:
        {
           "Type": 1,
           "Device": "postman-TEST",
           "Appid": "1",
           "Agent": "Samsung A5 2016, Android app, build_number other_info",
           "Authorization": "token QS7VF3JF29K22U1IY7LAYLNKRW66BNSWF9CH4BND"
        }
        @apiParam {boolean} is_favourite Status favourite of FR
        @apiParam {int} id_foodrecipe id of FR

        @apiSuccess {boolean} is_favourite
        """

        is_favourite = bool(int(request.data.get('is_favourite')))
        id_foodrecipe = request.data.get('id_foodrecipe')
        user = request.user
        foodrecipe = FoodRecipe.objects.get(pk=id_foodrecipe)
        if is_favourite:
            user.foodrecipe.add(foodrecipe)
            foodrecipe.lovers  = foodrecipe.user_set.all().count()
        else:
            user.foodrecipe.remove(foodrecipe)
            foodrecipe.lovers = foodrecipe.user_set.all().count()
        foodrecipe.save()
        return Response({'is_favourite': is_favourite})
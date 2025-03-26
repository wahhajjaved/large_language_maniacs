from django.shortcuts import render
from shellbook.models import Book_info
from django.http import HttpResponse
# 引入我们创建的表单类
from .forms import AddUserForm
from shellbook.models import Personal_info
from shellbook.models import Book_Review
from django.views.decorators.csrf import csrf_protect
from django.http import HttpResponseRedirect
from shellbook.models import User_Relationship
from shellbook.models import Message_Record

# Create your views here.
def home(request):
	if request.method == "GET":
		if len(request.GET) == 0:
			return render(request, 'home.html', {'books': Book_info.GetbooksbyNewDate(), 'hotbooks': Book_info.GetbooksbyPoint()})
		elif len(request.GET) > 0:
			a = Book_Review.GetCommentsBybookname(request.GET['book'])
			a1 = Book_info.objects.get(bookname = request.GET['book'],classification = request.GET['class'])
			return render(request,'book.html',{'bookobject':a1,'username':request.GET['username'],'comment':a})
	else:
		if len(request.POST) == 0:
			return render(request, 'home.html', {'books': Book_info.GetbooksbyNewDate(), 'hotbooks': Book_info.GetbooksbyPoint()})
		elif len(request.GET) == 0:
			if request.POST['select'] == "书名":
				a = Book_info.GetbooksbyBookname(request.POST['search'])
				return render(request, 'searchresults.html', {'books': a,'flag':0}) 
			elif request.POST['select'] == "作者":
				a = Book_info.GetbooksbyWriter(request.POST['search'])
				return render(request, 'searchresults.html', {'books': a,'flag':0})
			elif request.POST['select'] == "类别":
				a = Book_info.GetbooksbyClassification(request.POST['search'])
				return render(request, 'searchresults.html', {'books': a,'flag':0})	
		else:
			Book_Review.StoreComment(request.GET['book'],request.GET['username'],request.POST['comment'])
			a = Book_Review.GetCommentsBybookname(request.GET['book'])
			a1 = Book_info.objects.get(bookname = request.GET['book'],classification = request.GET['class'])
			return render(request,'book.html',{'bookobject':a1,'username':request.GET['username'],'comment':a})

@csrf_protect
def userregister(request):
	if request.POST:   # 当提交表单时
		a = request.POST['username']
		b = request.POST['userpassword']
		if Personal_info.MAddUser(a,b) == 0:
			return render(request, 'user_registration.html', {'flag': 0})
		else:
			return HttpResponseRedirect("../login/")
	else:# 当正常访问时
		return render(request, 'user_registration.html')
def userlogin(request):
	print(request.POST)
	if request.POST:   # 当提交表单时  
		if len(request.POST) == 5:
			if request.POST['select'] == "书名":
				a = Book_info.GetbooksbyBookname(request.POST['search'])
				return render(request, 'searchresults.html', {'books': a,'flag':1,'username':request.POST['username']}) 
			elif request.POST['select'] == "作者":
				a = Book_info.GetbooksbyWriter(request.POST['search'])
				return render(request, 'searchresults.html', {'books': a,'flag':1,'username':request.POST['username']})
			elif request.POST['select'] == "类别":
				a = Book_info.GetbooksbyClassification(request.POST['search'])
				return render(request, 'searchresults.html', {'books': a,'flag':1,'username':request.POST['username']})
		elif len(request.POST) == 3:
			a = request.POST['username']
			b = request.POST['userpassword']
			if Personal_info.VerifyLogin(a,b) == 1:
				return render(request, 'home.html', {'flag': 1, 'username': a, 'books': Book_info.GetbooksbyNewDate(), 'hotbooks': Book_info.GetbooksbyPoint()})
			else:
				return render(request, 'user_login.html',{'flag': 0})
	else:# 当正常访问时
		return render(request, 'user_login.html')
def userinfo(request):
	if request.POST:
		if len(request.POST) >= 6:# 当提交表单时
			a = request.POST['nickname']
			b = request.POST['region']
			c = request.POST['introduce']
			d = request.POST['userinfo']
			e = request.POST['gender']
			friends = User_Relationship.FindFriends(d)
			results = []
			for friend in friends:
				results.append(Personal_info.objects.get(username = friend.username2))
			message = []
			message = Message_Record.FindMessage(d)
			if len(request.FILES) == 1:
				f = request.FILES['img']
				Personal_info.Changeuserinfo(d,a,b,c,e,f)
				return render(request, 'personalhome.html',{'username':d,
					'nickname':Personal_info.GetUserByName(d).nickname,
					'region':Personal_info.GetUserByName(d).region,
					'introduce':Personal_info.GetUserByName(d).introduce,
					'gender':Personal_info.GetUserByName(d).gender,
					'img':Personal_info.GetUserByName(d).photo.url,
					'friends':results})
			else:
				f = ""
				Personal_info.Changeuserinfo(d,a,b,c,e,f)
				return render(request, 'personalhome.html',{'username':d,
					'nickname':Personal_info.GetUserByName(d).nickname,
					'region':Personal_info.GetUserByName(d).region,
					'introduce':Personal_info.GetUserByName(d).introduce,
					'gender':Personal_info.GetUserByName(d).gender,
					'img':"http://127.0.0.1:8000/media/upload/desert.jpg",
					'friends':results})
		elif len(request.POST) == 4:
			a = request.POST['friends']
			b = request.POST['username']
			User_Relationship.AddFriend(b,a)
			friends = User_Relationship.FindFriends(b)
			results = []
			for friend in friends:
				results.append(Personal_info.objects.get(username = friend.username2))
			message = []
			message = Message_Record.FindMessage(b)
			if Personal_info.objects.get(username = b).photo == "":
				return render(request, 'personalhome.html',{'username':b,
					'nickname':Personal_info.GetUserByName(b).nickname,
					'region':Personal_info.GetUserByName(b).region,
					'introduce':Personal_info.GetUserByName(b).introduce,
					'gender':Personal_info.GetUserByName(b).gender,
					'img':"http://127.0.0.1:8000/media/upload/desert.jpg",
					'friends':results,
					'message':message})
			else:
				return render(request, 'personalhome.html',{'username':b,
					'nickname':Personal_info.GetUserByName(b).nickname,
					'region':Personal_info.GetUserByName(b).region,
					'introduce':Personal_info.GetUserByName(b).introduce,
					'gender':Personal_info.GetUserByName(b).gender,
					'img':Personal_info.GetUserByName(b).photo.url,
					'friends':results,
					'message':message})
		elif len(request.POST) == 5:
			a = request.POST['friend']
			b = request.POST['username']
			c = request.POST['context']
			Message_Record.StoreMessage(b,a,c)
			friends = User_Relationship.FindFriends(b)
			results = []
			for friend in friends:
				results.append(Personal_info.objects.get(username = friend.username2))
			message = []
			message = Message_Record.FindMessage(b)
			if Personal_info.objects.get(username = b).photo == "":
				return render(request, 'personalhome.html',{'username':b,
					'nickname':Personal_info.GetUserByName(b).nickname,
					'region':Personal_info.GetUserByName(b).region,
					'introduce':Personal_info.GetUserByName(b).introduce,
					'gender':Personal_info.GetUserByName(b).gender,
					'img':"http://127.0.0.1:8000/media/upload/desert.jpg",
					'friends':results,
					'message':message})
			else:
				return render(request, 'personalhome.html',{'username':b,
					'nickname':Personal_info.GetUserByName(b).nickname,
					'region':Personal_info.GetUserByName(b).region,
					'introduce':Personal_info.GetUserByName(b).introduce,
					'gender':Personal_info.GetUserByName(b).gender,
					'img':Personal_info.GetUserByName(b).photo.url,
					'friends':results,
					'message':message})	
			
	mname = str(request.GET['username'])
	friends = User_Relationship.FindFriends(mname)
	results = []
	for friend in friends:
		results.append(Personal_info.objects.get(username = friend.username2))
	message = []
	message = Message_Record.FindMessage(mname)
	print(message)
	print(1)
	if Personal_info.GetUserByName(mname).photo == "":
		return render(request, 'personalhome.html',{'username':mname,
				'nickname':Personal_info.GetUserByName(mname).nickname,
				'region':Personal_info.GetUserByName(mname).region,
				'introduce':Personal_info.GetUserByName(mname).introduce,
				'gender':Personal_info.GetUserByName(mname).gender,
				'img':"http://127.0.0.1:8000/media/upload/desert.jpg",
				'friends':results,
				'message':message})
	else:
		return render(request, 'personalhome.html',{'username':mname,
				'nickname':Personal_info.GetUserByName(mname).nickname,
				'region':Personal_info.GetUserByName(mname).region,
				'introduce':Personal_info.GetUserByName(mname).introduce,
				'gender':Personal_info.GetUserByName(mname).gender,
				'img':Personal_info.GetUserByName(mname).photo.url,
				'friends':results,
				'message':message})
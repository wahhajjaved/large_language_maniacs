from django.db import models

# Create your models here.

description = '''Hello world, this is a default description.'''


class Category(models.Model):
    name = models.CharField(max_length=255)

    @classmethod
    def str_category(cls):
        cat = {
            'name': cls.name,
        }
        return cat

    def save_category(self):
        self.save()

    def delete_category(self):
        self.delete()

    def __str__(self):
        return f'Name: {self.name}'

    class Meta:
        db_table = 'category'


class Location(models.Model):
    place = models.CharField(max_length=255)

    def __str__(self):
        return f'Place: {self.place}'

    def save_location(self):
        self.save()

    def delete_location(self):
        self.delete()

    class Meta:
        db_table = 'location'


class Image(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField(default=description)
    category = models.ForeignKey(Category, related_name='images', on_delete=models.CASCADE)
    location = models.ForeignKey(Location, on_delete=models.CASCADE)
    submitted = models.DateTimeField(auto_now_add=True)
    image_url = models.ImageField(upload_to='images/')

    def get_image_information(self):
        info = {
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'location': self.location,
            'submitted': self.submitted,
            'image_url': self.image_url,
        }
        return str(info)

    def update_image(self, name=name, category=None):
        self.name = name if name else self.name
        self.category = category if category else self.category
        self.save()

    @classmethod
    def get_image_by_id(cls, id):
        return cls.objects.get(pk=id)

    @classmethod
    def search_image(cls, key):
        images = cls.objects.filter(
            cls(description__contains=key) | cls(Name__icontains=key) | cls(location__place__icontains=key))
        print(images)
        return images

    @classmethod
    def search_by_title(cls, search_term):
        news = cls.objects.filter(title__icontains=search_term)
        return news

    def save_image(self):
        self.save()

    def delete_image(self):
        self.delete()

    def __repr__(self):
        return f'''
            name: {self.name},
            description: {self.description},
            category: {self.category},
            location: {self.location},
            submitted: {self.submitted},
            image_url: {self.image_url},
                '''

    class Meta:
        db_table = 'image'
        ordering = ['submitted']

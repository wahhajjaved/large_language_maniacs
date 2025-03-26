from django import forms
from ticketing.models import Product, Picture, Ticket
from registration.models import CreditCard
import datetime
import braintree


braintree.Configuration.configure(
    braintree.Environment.Sandbox,
    merchant_id='cyttpz8353vkpbrd',
    public_key='nrn2r5tngvrn5f2v',
    private_key='0f09fcb2f66e479b3473297b35d85d35'
)

class TicketPurchaseForm(forms.Form):
    quantity = forms.ChoiceField(choices=[(x,x) for x in range(1,11)],
                                 widget=forms.Select(attrs={'class': 'selectpicker form-control'}))

    def purchase(self, user, product_id):
        product = Product.objects.get(pk=product_id)
        charge_amount = product.pricing_per_ticket * int(self.cleaned_data['quantity'])
        credit_card = CreditCard.objects.get(pk=1)
        result = braintree.Transaction.sale({
                "amount": charge_amount,
                "credit_card": {
                    "number": credit_card.card_number,
                    "expiration_date": credit_card.exp_date
                }
            })
        if result.is_success:
            print("success!: " + result.transaction.id)
            for ticket in range(1, int(self.cleaned_data['quantity'])):
                Ticket.objects.create(user=user,product=product)
        elif result.transaction:
            print("Error processing transaction:")
            print("  code: " + result.transaction.processor_response_code)
            print("  text: " + result.transaction.processor_response_text)
        else:
            for error in result.errors.deep_errors:
                print("attribute: " + error.attribute)
                print("  code: " + error.code)
                print("  message: " + error.message)
        return result

class CreateRaffleForm(forms.Form):
    name = forms.CharField(max_length=125,
                           widget=forms.TextInput(attrs={'class': 'form-control',
                                                         'placeholder': 'product name'}))
    description = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control',
                                                                'placeholder': 'product description'}))
    total_number_of_tickets = forms.IntegerField(widget=forms.NumberInput(attrs={'class': 'form-control',
                                                                'placeholder': 100}))
    start_time = forms.DateTimeField(initial=datetime.date.today,
                                 # input_formats=['%Y-%m-%d %H:%M:%S'],
                                 widget=forms.DateTimeInput(attrs={'class': 'form-control'}))
    end_time = forms.DateTimeField(initial=datetime.date.today,
                               # input_formats=['%Y-%m-%d %H:%M:%S'],
                               widget=forms.DateTimeInput(attrs={'class': 'form-control'}))
    pricing_per_ticket = forms.FloatField(widget=forms.NumberInput(attrs={'class': 'form-control',
                                                                'placeholder': 100}))

    picture_upload = forms.ImageField(widget=forms.FileInput(attrs={'class': 'form-control'}))
    picture_description = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control',
                                                                'placeholder': 'Picture description'}))

    def save(self, user):

        product = Product.objects.create(name=self.cleaned_data['name'],
                                         description=self.cleaned_data['description'],
                                         total_number_of_tickets=self.cleaned_data['total_number_of_tickets'],
                                         start_time=self.cleaned_data['start_time'],
                                         end_time=self.cleaned_data['end_time'],
                                         pricing_per_ticket=self.cleaned_data['pricing_per_ticket'],
                                         user=user)
        pic = Picture.objects.create(description=self.cleaned_data['picture_description'],
                                     image=self.cleaned_data['picture_upload'],
                                     product=product)
        product.default_picture = pic
        product.save()
        return product
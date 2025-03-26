import datetime
import boto3
import ast
import jwt

from .aws_srp import AWSSRP


def attribute_dict(attributes):
    """
    :param attributes: Dictionary of User Pool attribute names/values
    :return: list of User Pool attribute formatted dicts: {'Name': <attr_name>, 'Value': <attr_value>}
    """
    return [{'Name': key, 'Value': value} for key, value in attributes.items()]


class UserObj(object):

    def __init__(self, username, attribute_list, metadata={}):
        """
        :param username:
        :param attribute_list:
        :param metadata: Dictionary of User metadata
        """
        self.username = username
        self.pk = username
        for a in attribute_list:
            name = a.get('Name')
            value = a.get('Value')
            if value in ['true','false']:
                value = ast.literal_eval(value.capitalize())
            setattr(self, name, value)
        for key, value in metadata.items():
            setattr(self, key.lower(), value)



class Cognito(object):

    user_class = UserObj

    def __init__(
            self, user_pool_id, client_id,
            username=None,
            id_token=None,refresh_token=None,
            access_token=None,secret_hash=None,
            access_key=None, secret_key=None,
            ):
        """
        :param user_pool_id: Cognito User Pool ID
        :param client_id: Cognito User Pool Application client ID
        :param username: User Pool username
        :param id_token: ID Token returned by authentication
        :param refresh_token: Refresh Token returned by authentication
        :param access_token: Access Token returned by authentication
        :param access_key: AWS IAM access key
        :param secret_key: AWS IAM secret key
        """

        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.username = username
        self.id_token = id_token
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.secret_hash = secret_hash
        self.token_type = None

        if access_key and secret_key:
            self.client = boto3.client('cognito-idp',
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                )
        else:
            self.client = boto3.client('cognito-idp')

    def get_user_obj(self,username=None,attribute_list=[],metadata={}):
        return self.user_class(username=username,attribute_list=attribute_list,
                               metadata=metadata)

    def switch_session(self,session):
        """
        Primarily used for unit testing so we can take advantage of the
        placebo library (https://githhub.com/garnaat/placebo)
        :param session: boto3 session
        :return:
        """
        self.client = session.client('cognito-idp')

    def check_token(self):
        """
        Checks the exp attribute of the access_token and either refreshes
        the tokens by calling the renew_access_tokens method or does nothing
        :return: None
        """
        if not self.access_token:
            raise AttributeError('Access Token Required to Check Token')
        now = datetime.datetime.now()
        dec_access_token = jwt.decode(self.access_token,verify=False)

        if now > datetime.datetime.fromtimestamp(dec_access_token['exp']):
            self.renew_access_token()
            return True
        return False

    def register(self, username, password, **kwargs):
        """
        Register the user. Other base attributes from AWS Cognito User Pools
        are  address, birthdate, email, family_name (last name), gender,
        given_name (first name), locale, middle_name, name, nickname,
        phone_number, picture, preferred_username, profile, zoneinfo,
        updated at, website
        :param username: User Pool username
        :param password: User Pool password
        :param kwargs: Additional User Pool attributes
        :return response: Response from Cognito

        Example response::
        {
            'UserConfirmed': True|False,
            'CodeDeliveryDetails': {
                'Destination': 'string', # This value will be obfuscated
                'DeliveryMedium': 'SMS'|'EMAIL',
                'AttributeName': 'string'
            }
        }
        """
        user_attrs = [{'Name': key, 'Value': value} for key, value in kwargs.items()]
        response = self.client.sign_up(
            ClientId=self.client_id,
            Username=username,
            Password=password,
            UserAttributes=attribute_dict(kwargs)
        )
        kwargs.update(username=username, password=password)
        self._set_attributes(response, kwargs)

        response.pop('ResponseMetadata')
        return response

    def confirm_sign_up(self,confirmation_code,username=None):
        """
        Using the confirmation code that is either sent via email or text
        message.
        :param confirmation_code: Confirmation code sent via text or email
        :param username: User's username
        :return:
        """
        if not username:
            username = self.username
        self.client.confirm_sign_up(
            ClientId=self.client_id,
            Username=username,
            ConfirmationCode=confirmation_code
        )

    def authenticate(self, password):
        """
        Authenticate the user.
        :param user_pool_id: User Pool Id found in Cognito User Pool
        :param client_id: App Client ID found in the Apps section of the Cognito User Pool
        :return:
        """
        auth_params = {
                'USERNAME': self.username,
                'PASSWORD': password
            }

        tokens = self.client.admin_initiate_auth(
            UserPoolId=self.user_pool_id,
            ClientId=self.client_id,
            # AuthFlow='USER_SRP_AUTH'|'REFRESH_TOKEN_AUTH'|'REFRESH_TOKEN'|'CUSTOM_AUTH'|'ADMIN_NO_SRP_AUTH',
            AuthFlow='ADMIN_NO_SRP_AUTH',
            AuthParameters=auth_params,
        )



        self.id_token = tokens['AuthenticationResult']['IdToken']
        self.refresh_token = tokens['AuthenticationResult']['RefreshToken']
        self.access_token = tokens['AuthenticationResult']['AccessToken']
        self.token_type = tokens['AuthenticationResult']['TokenType']

    def authenticate_user(self, password):
        """
        Authenticate the user.
        :param password:
        :return:
        """
        aws = AWSSRP(username=self.username, password=password, pool_id=self.user_pool_id,
                     client_id=self.client_id, client=self.client)
        tokens = aws.authenticate_user()
        self.id_token = tokens['AuthenticationResult']['IdToken']
        self.refresh_token = tokens['AuthenticationResult']['RefreshToken']
        self.access_token = tokens['AuthenticationResult']['AccessToken']
        self.token_type = tokens['AuthenticationResult']['TokenType']

    def logout(self):
        """
        Logs the user out of all clients and removes the expires_in,
        expires_datetime, id_token, refresh_token, access_token, and token_type
        attributes
        :return:
        """
        self.client.global_sign_out(
            AccessToken=self.access_token
        )

        self.id_token = None
        self.refresh_token = None
        self.access_token = None
        self.token_type = None

    def update_profile(self, attrs):
        """
        Updates User attributes
        :parm attrs: Dictionary of attribute name, values
        """
        user_attrs = attribute_dict(attrs)
        response = self.client.update_user_attributes(
            UserAttributes=user_attrs,
            AccessToken=self.access_token
        )

    def get_user(self):
        # self.check_token()
        user = self.client.get_user(
                AccessToken=self.access_token
            )
        user_metadata = {
            'username': user.get('Username'),
            'id_token': self.id_token,
            'access_token': self.access_token,
            'refresh_token': self.refresh_token
        }

        return self.get_user_obj(username=self.username,
                                 attribute_list=user.get('UserAttributes'),
                                 metadata=user_metadata)

    def admin_get_user(self):
        """
        Get the user's details
        :param user_pool_id: The Cognito User Pool Id
        :return: UserObj object
        """
        user = self.client.admin_get_user(
                           UserPoolId=self.user_pool_id,
                           Username=self.username)
        user_metadata = {
            'user_status':user.get('UserStatus'),
            'username':user.get('Username'),
            'id_token': self.id_token,
            'access_token': self.access_token,
            'refresh_token': self.refresh_token
        }
        return self.get_user_obj(username=self.username,
                                 attribute_list=user.get('UserAttributes'),
                                 metadata=user_metadata)


    def send_verification(self, attribute='email'):
        """
        Sends the user an attribute verification code for the specified attribute name.
        :param attribute: Attribute to confirm
        """
        self.check_token()
        self.client.get_user_attribute_verification_code(
            AccessToken=self.access_token,
            AttributeName=attribute
        )

    def validate_verification(self, confirmation_code, attribute='email'):
        """
        Verifies the specified user attributes in the user pool.
        :param confirmation_code: Code sent to user upon intiating verification
        :param attribute: Attribute to confirm
        """
        self.check_token()
        return self.client.verify_user_attribute(
            AccessToken=self.access_token,
            AttributeName=attribute,
            Code=confirmation_code
        )

    def renew_access_token(self):
        """
        Sets a new access token on the User using the refresh token.
        """
        refresh_response = self.client.admin_initiate_auth(
            UserPoolId=self.user_pool_id,
            ClientId=self.client_id,
            AuthFlow='REFRESH_TOKEN',
            AuthParameters={
                'REFRESH_TOKEN': self.refresh_token
            },
        )

        self._set_attributes(
            refresh_response,
            {
                'access_token': refresh_response['AuthenticationResult']['AccessToken'],
                'id_token': refresh_response['AuthenticationResult']['IdToken'],
                'token_type': refresh_response['AuthenticationResult']['TokenType']
            }
        )

    def initiate_forgot_password(self):
        """
        Sends a verification code to the user to use to change their password.
        """
        self.client.forgot_password(
            ClientId=self.client_id,
            Username=self.username
        )

    def confirm_forgot_password(self, confirmation_code, password):
        """
        Allows a user to enter a code provided when they reset their password
        to update their password.
        :param confirmation_code: The confirmation code sent by a user's request
        to retrieve a forgotten password
        :param password: New password
        """
        response = self.client.confirm_forgot_password(
            ClientId=self.client_id,
            Username=self.username,
            ConfirmationCode=confirmation_code,
            Password=password
        )
        self._set_attributes(response, {'password': password})

    def change_password(self, previous_password, proposed_password):
        """
        Change the User password
        """
        self.check_token()
        response = self.client.change_password(
            PreviousPassword=previous_password,
            ProposedPassword=proposed_password,
            AccessToken=self.access_token
        )
        self._set_attributes(response, {'password': proposed_password})

    def _set_attributes(self, response, attribute_dict):
        """
        Set user attributes based on response code
        :param response: HTTP response from Cognito
        :attribute dict: Dictionary of attribute name and values
        """
        status_code = response.get(
            'HTTPStatusCode',
            response['ResponseMetadata']['HTTPStatusCode']
        )
        if status_code == 200:
            for k, v in attribute_dict.items():
                setattr(self, k, v)

import uuid
from datetime import timedelta

from twitcher.utils import now, localize_datetime
from twitcher.owsexceptions import OWSForbidden

import logging
logger = logging.getLogger(__name__)

# defaults
DEFAULT_VALID_IN_HOURS = 1


class TokenStorage(object):
    def __init__(self, db):
        self.db = db.tokens

        
    def create_access_token(self, valid_in_hours=DEFAULT_VALID_IN_HOURS):
        """
        Generates an access token.

        TODO: check valid in hours
        TODO: maybe specify how often a token can be used
        """
        access_token = AccessToken(
            access_token = str(uuid.uuid1().get_hex()),
            creation_time = now(),
            valid_in_hours = valid_in_hours)
        self.db.insert_one(access_token)
        return access_token

    
    def delete_access_token(self, token):
        if isinstance(token, AccessToken):
            self.db.delete_one(token)
        else:
            self.db.delete_one({'access_token': token})

    
    def get_access_token(self, token):
        access_token = None
        if isinstance(token, AccessToken):
            access_token = self.db.find_one(token)
        else:
            access_token = self.db.find_one({'access_token': token})
        if not access_token is None:
            access_token = AccessToken(access_token)
        return access_token

    def validate_access_token(self, request):
        token = None
        if 'access_token' in request.params:
            token = request.params['access_token']   # in params
        elif 'Access-Token' in request.headers:
            token = request.headers['Access-Token']  # in header
        else:
            raise OWSForbidden() # no access token provided

        access_token = self.get_access_token(token)
        if access_token is None:
            raise OWSForbidden() # no access token in store
        if not access_token.is_valid():
            raise OWSForbidden() # access token not valid


class AccessToken(dict):
    """
    Dictionary that contains access token. It always has ``'access_token'`` key.
    """
    
    def __init__(self, *args, **kwargs):
        super(AccessToken, self).__init__(*args, **kwargs)
        if 'access_token' not in self:
            raise TypeError("'access_token' is required")
        if 'creation_time' not in self:
            raise TypeError("'creation_time' is required")

            
    @property
    def access_token(self):
        """(:class:`basestring`) Access token."""
        return self['access_token']

        
    @property
    def creation_time(self):
        return self['creation_time']

    
    @property
    def valid_in_hours(self):
        return self.get('valid_in_hours', DEFAULT_VALID_IN_HOURS)

    
    def not_before(self):
        """
        Access token is not valid before this time.
        """
        return localize_datetime(self.creation_time)

    
    def not_after(self):
        """
        Access token is not valid after this time.
        """
        return self.not_before() + timedelta(hours=self.valid_in_hours)

    
    def is_valid(self):
        """
        Checks if token is valid.
        """
        return self.not_before() <= now() and now() <= self.not_after()

    
    def __str__(self):
        return self.access_token

    
    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)



    





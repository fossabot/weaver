from weaver.exceptions import ServiceNotFound, InvalidIdentifierValue
from weaver.warning import TimeZoneInfoAlreadySetWarning
from weaver.status import map_status
from datetime import datetime
from lxml import etree
# noinspection PyProtectedMember
from lxml.etree import _Element as xmlElement
from typing import Union, Any, Dict, List, AnyStr, Iterable, Optional, TYPE_CHECKING
from pyramid.httpexceptions import HTTPError as PyramidHTTPError
from pyramid.request import Request
from requests import HTTPError as RequestsHTTPError
from six.moves.urllib.parse import urlparse, parse_qs
from distutils.dir_util import mkpath
from distutils.version import LooseVersion
import os
import time
import pytz
import types
import re
import platform
import warnings
import logging
if TYPE_CHECKING:
    from weaver.typedefs import Settings

LOGGER = logging.getLogger(__name__)


def get_weaver_url(settings):
    # type: (Settings) -> AnyStr
    return settings.get('weaver.url').rstrip('/').strip()


def get_any_id(info):
    # type: (Dict[AnyStr, AnyStr]) -> AnyStr
    """Retrieves a dictionary 'id'-like key using multiple common variations [id, identifier, _id].
    :param info: dictionary that potentially contains an 'id'-like key.
    :returns: value of the matched 'id'-like key."""
    return info.get('id', info.get('identifier', info.get('_id')))


def get_any_value(info):
    # type: (Dict[AnyStr, AnyStr]) -> Union[AnyStr, None]
    """Retrieves a dictionary 'value'-like key using multiple common variations [href, value, reference].
    :param info: dictionary that potentially contains a 'value'-like key.
    :returns: value of the matched 'id'-like key."""
    return info.get('href', info.get('value', info.get('reference', info.get('data'))))


def get_any_message(info):
    # type: (Dict[AnyStr, AnyStr]) -> AnyStr
    """Retrieves a dictionary 'value'-like key using multiple common variations [message].
    :param info: dictionary that potentially contains a 'message'-like key.
    :returns: value of the matched 'message'-like key or an empty string if not found. """
    return info.get('message', '').strip()


def is_valid_url(url):
    # type: (Union[AnyStr, None]) -> bool
    # noinspection PyBroadException
    try:
        parsed_url = urlparse(url)
        return True if all([parsed_url.scheme, ]) else False
    except Exception:
        return False


def parse_extra_options(option_str):
    """
    Parses the extra options parameter.

    The option_str is a string with coma separated ``opt=value`` pairs.
    Example::

        tempdir=/path/to/tempdir,archive_root=/path/to/archive

    :param option_str: A string parameter with the extra options.
    :return: A dict with the parsed extra options.
    """
    if option_str:
        try:
            extra_options = option_str.split(',')
            extra_options = dict([('=' in opt) and opt.split('=', 1) for opt in extra_options])
        except Exception:
            msg = "Can not parse extra-options: {}".format(option_str)
            from pyramid.exceptions import ConfigurationError
            raise ConfigurationError(msg)
    else:
        extra_options = {}
    return extra_options


def parse_service_name(url, protected_path):
    # type: (AnyStr, AnyStr) -> AnyStr
    parsed_url = urlparse(url)
    service_name = None
    if parsed_url.path.startswith(protected_path):
        parts_without_protected_path = parsed_url.path[len(protected_path)::].strip('/').split('/')
        if 'proxy' in parts_without_protected_path:
            parts_without_protected_path.remove('proxy')
        if len(parts_without_protected_path) > 0:
            service_name = parts_without_protected_path[0]
    if not service_name:
        raise ServiceNotFound
    return service_name


def fully_qualified_name(obj):
    # type: (Any) -> AnyStr
    return '.'.join([obj.__module__, type(obj).__name__])


def now():
    # type: (...) -> datetime
    return localize_datetime(datetime.utcnow())


def now_secs():
    # type: (...) -> int
    """
    Return the current time in seconds since the Epoch.
    """
    return int(time.time())


def wait_secs(run_step=-1):
    secs_list = (2, 2, 2, 2, 2, 5, 5, 5, 5, 5, 10, 10, 10, 10, 10, 20, 20, 20, 20, 20, 30)
    if run_step >= len(secs_list):
        run_step = -1
    return secs_list[run_step]


def expires_at(hours=1):
    # type: (Optional[int]) -> int
    return now_secs() + hours * 3600


def localize_datetime(dt, tz_name='UTC'):
    # type: (datetime, Optional[AnyStr]) -> datetime
    """
    Provide a timezone-aware object for a given datetime and timezone name
    """
    tz_aware_dt = dt
    if dt.tzinfo is None:
        utc = pytz.timezone('UTC')
        aware = utc.localize(dt)
        timezone = pytz.timezone(tz_name)
        tz_aware_dt = aware.astimezone(timezone)
    else:
        warnings.warn("tzinfo already set", TimeZoneInfoAlreadySetWarning)
    return tz_aware_dt


def get_base_url(url):
    # type: (AnyStr) -> AnyStr
    """
    Obtains the base URL from the given `url`.
    """
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        raise ValueError('bad url')
    service_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path.strip())
    return service_url


def path_elements(path):
    # type: (AnyStr) -> List[AnyStr]
    elements = [el.strip() for el in path.split('/')]
    elements = [el for el in elements if len(el) > 0]
    return elements


def lxml_strip_ns(tree):
    # type: (xmlElement) -> None
    for node in tree.iter():
        try:
            has_namespace = node.tag.startswith('{')
        except AttributeError:
            continue  # node.tag is not a string (node is a comment or similar)
        if has_namespace:
            node.tag = node.tag.split('}', 1)[1]


def pass_http_error(exception, expected_http_error):
    # type: (Exception, Union[PyramidHTTPError, Iterable[PyramidHTTPError]]) -> None
    """
    Given an `HTTPError` of any type (pyramid, requests), ignores (pass) the exception if the actual
    error matches the status code. Other exceptions are re-raised.

    :param exception: any `Exception` instance ("object" from a `try..except exception as "object"` block).
    :param expected_http_error: single or list of specific pyramid `HTTPError` to handle and ignore.
    :raise exception: if it doesn't match the status code or is not an `HTTPError` of any module.
    """
    if not hasattr(expected_http_error, '__iter__'):
        expected_http_error = [expected_http_error]
    if isinstance(exception, (PyramidHTTPError, RequestsHTTPError)):
        try:
            status_code = exception.status_code
        except AttributeError:
            # exception may be a response raised for status in which case status code is here:
            status_code = exception.response.status_code

        if status_code in [e.code for e in expected_http_error]:
            return
    raise exception


def raise_on_xml_exception(xml_node):
    """
    Raises an exception with the description if the XML response document defines an ExceptionReport.
    :param xml_node: instance of :class:`etree.Element`
    :raise Exception: on found ExceptionReport document.
    """
    # noinspection PyProtectedMember
    if not isinstance(xml_node, etree._Element):
        raise TypeError("Invalid input, expecting XML element node.")
    if 'ExceptionReport' in xml_node.tag:
        node = xml_node
        while len(node.getchildren()):
            node = node.getchildren()[0]
        raise Exception(node.text)


def replace_caps_url(xml, url, prev_url=None):
    ns = {
        'ows': 'http://www.opengis.net/ows/1.1',
        'xlink': 'http://www.w3.org/1999/xlink'}
    doc = etree.fromstring(xml)
    # wms 1.1.1 onlineResource
    if 'WMT_MS_Capabilities' in doc.tag:
        LOGGER.debug("replace proxy urls in wms 1.1.1")
        for element in doc.findall('.//OnlineResource[@xlink:href]', namespaces=ns):
            parsed_url = urlparse(element.get('{http://www.w3.org/1999/xlink}href'))
            new_url = url
            if parsed_url.query:
                new_url += '?' + parsed_url.query
            element.set('{http://www.w3.org/1999/xlink}href', new_url)
        xml = etree.tostring(doc)
    # wms 1.3.0 onlineResource
    elif 'WMS_Capabilities' in doc.tag:
        LOGGER.debug("replace proxy urls in wms 1.3.0")
        for element in doc.findall('.//{http://www.opengis.net/wms}OnlineResource[@xlink:href]', namespaces=ns):
            parsed_url = urlparse(element.get('{http://www.w3.org/1999/xlink}href'))
            new_url = url
            if parsed_url.query:
                new_url += '?' + parsed_url.query
            element.set('{http://www.w3.org/1999/xlink}href', new_url)
        xml = etree.tostring(doc)
    # wps operations
    elif 'Capabilities' in doc.tag:
        for element in doc.findall('ows:OperationsMetadata//*[@xlink:href]', namespaces=ns):
            element.set('{http://www.w3.org/1999/xlink}href', url)
        xml = etree.tostring(doc)
    elif prev_url:
        xml = xml.decode('utf-8', 'ignore')
        xml = xml.replace(prev_url, url)
    return xml


def islambda(func):
    # type: (AnyStr) -> bool
    return isinstance(func, types.LambdaType) and func.__name__ == (lambda: None).__name__


first_cap_re = re.compile('(.)([A-Z][a-z]+)')
all_cap_re = re.compile('([a-z0-9])([A-Z])')


def convert_snake_case(name):
    # type: (AnyStr) -> AnyStr
    s1 = first_cap_re.sub(r'\1_\2', name)
    return all_cap_re.sub(r'\1_\2', s1).lower()


def parse_request_query(request):
    # type: (Request) -> Dict[AnyStr, Dict[Union[int, AnyStr], AnyStr]]
    """
    :param request:
    :return: dict of dict where k=v are accessible by d[k][0] == v and q=k=v are accessible by d[q][k] == v, lowercase
    """
    queries = parse_qs(request.query_string.lower())
    queries_dict = dict()
    for q in queries:
        queries_dict[q] = dict()
        for i, kv in enumerate(queries[q]):
            kvs = kv.split('=')
            if len(kvs) > 1:
                queries_dict[q][kvs[0]] = kvs[1]
            else:
                queries_dict[q][i] = kvs[0]
    return queries_dict


def get_log_fmt():
    # type: (...) -> AnyStr
    return '[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s'


def get_log_datefmt():
    # type: (...) -> AnyStr
    return '%Y-%m-%d %H:%M:%S'


def get_job_log_msg(status, message, progress=0, duration=None):
    # type: (AnyStr, AnyStr, Optional[int], Optional[AnyStr]) -> AnyStr
    return '{d} {p:3d}% {s:10} {m}'.format(d=duration or '', p=int(progress or 0), s=map_status(status), m=message)


def make_dirs(path, mode=0o755, exist_ok=True):
    """Alternative to 'makedirs' with 'exists_ok' parameter only available for python>3.5"""
    if LooseVersion(platform.python_version()) >= LooseVersion('3.5'):
        os.makedirs(path, mode=mode, exist_ok=exist_ok)
        return
    dir_path = os.path.dirname(path)
    if not os.path.isfile(path) or not os.path.isdir(dir_path):
        for subdir in mkpath(dir_path):
            if not os.path.isdir(subdir):
                os.mkdir(subdir, mode)


def get_sane_name(name, min_len=3, max_len=None, assert_invalid=True, replace_invalid=False):
    if assert_invalid:
        assert_sane_name(name, min_len, max_len)
    if name is None:
        return None
    name = name.strip()
    if len(name) < min_len:
        return None
    if replace_invalid:
        max_len = max_len or 25
        name = re.sub("[^a-z]", "_", name.lower()[:max_len])
    return name


def assert_sane_name(name, min_len=3, max_len=None):
    if name is None:
        raise InvalidIdentifierValue('Invalid process name : {0}'.format(name))
    name = name.strip()
    if '--' in name \
       or name.startswith('-') \
       or name.endswith('-') \
       or len(name) < min_len \
       or (max_len is not None and len(name) > max_len) \
       or not re.match(r"^[a-zA-Z0-9_\-]+$", name):
        raise InvalidIdentifierValue('Invalid process name : {0}'.format(name))

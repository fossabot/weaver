"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_
"""

import urllib
from httplib2 import Http

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest, HTTPBadGateway, HTTPNotAcceptable
from pyramid.response import Response

from twitcher.registry import registry_factory

import logging
logger = logging.getLogger(__name__)


allowed_content_types = (
    "application/xml", "text/xml",
    "application/vnd.ogc.se_xml",           # OGC Service Exception
    "application/vnd.ogc.se+xml",           # OGC Service Exception
    #"application/vnd.ogc.success+xml",      # OGC Success (SLD Put)
    #"application/vnd.ogc.wms_xml",          # WMS Capabilities
    #"application/vnd.ogc.gml",              # GML
    #"application/vnd.ogc.sld+xml",          # SLD
    #"application/vnd.google-earth.kml+xml", # KML
    )

class OWSProxy(object):
    def __init__(self, request):
        self.request = request

          
    def send_request(self, service):
        # TODO: fix way to build url
        logger.debug('params = %s', self.request.params)
        url = service['url'] + '?' + urllib.urlencode(self.request.params)

        # forward request to target (without Host Header)
        http = Http(disable_ssl_certificate_validation=True)
        h = dict(self.request.headers)
        h.pop("Host", h)
        try:
            resp, content = http.request(url, method=self.request.method, body=self.request.body, headers=h)
        except:
            return HTTPBadGateway()

        # check for allowed content types
        if resp.has_key("content-type"):
            ct = resp["content-type"]
            if not ct.split(";")[0] in allowed_content_types:
                return HTTPForbidden()
        else:
            return HTTPNotAcceptable()

        # replace urls in xml content
        if 'xml' in ct:
            content = content.replace(service['url'], service['proxy_url'])

        return Response(content, status=resp.status, headers={"Content-Type": ct})
    
    @view_config(route_name='owsproxy')
    @view_config(route_name='owsproxy_secured')
    def owsproxy(self):
        service_name = self.request.matchdict.get('service_name')
        if service_name is None:
            return HTTPBadRequest('Param service_name is required')
        
        service = None
        try:
            registry = registry_factory(request)
            service = reqistry.get_service(service_name)
        except Exception as err:
            return HTTPBadRequest("Could not find service: %s" % (err.message))

        return self.send_request(service)

def includeme(config):
    # include mongodb
    config.include('twitcher.db')
    
    config.add_route('owsproxy', '/ows/proxy/{service_name}')
    config.add_route('owsproxy_secured', '/ows/proxy/{service_name}/{access_token}')

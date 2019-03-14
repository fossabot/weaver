"""
Based on tests from:

* https://github.com/geopython/pywps/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""
# noinspection PyPackageRequirements
import pytest
import unittest
import pyramid.testing
from xml.etree import ElementTree
from weaver.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE
from weaver.processes.wps_default import Hello
from weaver.processes.wps_testing import WpsTestProcess
from weaver.tests.utils import (
    setup_config_with_mongodb,
    setup_config_with_pywps,
    setup_mongodb_processstore,
    setup_config_with_celery,
    get_test_weaver_config,
    get_test_weaver_app,
)


@pytest.mark.functional
class WpsAppTest(unittest.TestCase):
    def setUp(self):
        self.wps_path = '/ows/wps'
        settings = {
            'weaver.url': '',
            'weaver.wps': True,
            'weaver.wps_path': self.wps_path
        }
        config = get_test_weaver_config(settings=settings)
        config = setup_config_with_mongodb(config)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
        self.process_store = setup_mongodb_processstore(config)
        self.app = get_test_weaver_app(config=config, settings=settings)

        # add processes by database Process type
        self.process_public = WpsTestProcess(identifier='process_public')
        self.process_private = WpsTestProcess(identifier='process_private')
        self.process_store.save_process(self.process_public)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

        # add processes by pywps Process type
        self.process_store.save_process(Hello())
        self.process_store.set_visibility(Hello.identifier, VISIBILITY_PUBLIC)

    def tearDown(self):
        pyramid.testing.tearDown()

    def make_url(self, params):
        return '{}?{}'.format(self.wps_path, params)

    @pytest.mark.online
    def test_getcaps(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.online
    def test_getcaps_filtered_processes_by_visibility(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessOfferings>')
        root = ElementTree.fromstring(resp.text)
        process_offerings = list(filter(lambda e: 'ProcessOfferings' in e.tag, list(root)))
        assert len(process_offerings) == 1
        processes = [p for p in process_offerings[0]]
        identifiers = [pi.text for pi in [filter(lambda e: e.tag.endswith('Identifier'), p)[0] for p in processes]]
        assert self.process_private.identifier not in identifiers
        assert self.process_public.identifier in identifiers

    @pytest.mark.online
    def test_describeprocess(self):
        params = "service=wps&request=describeprocess&version=1.0.0&identifier={}".format(Hello.identifier)
        resp = self.app.get(self.make_url(params))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.online
    def test_describeprocess_filtered_processes_by_visibility(self):
        param_template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"

        url = self.make_url(param_template.format(self.process_public.identifier))
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

        url = self.make_url(param_template.format(self.process_private.identifier))
        resp = self.app.get(url, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<ows:ExceptionText>Unknown process')

    @pytest.mark.online
    def test_execute_allowed(self):
        params = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=name=tux".format(Hello.identifier)
        url = self.make_url(params)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessSucceeded>PyWPS Process {} finished</wps:ProcessSucceeded>'.format(Hello.title))

    @pytest.mark.online
    def test_execute_with_visibility(self):
        params_template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=test_input=test"
        url = self.make_url(params_template.format(self.process_public.identifier, ))
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessSucceeded>PyWPS Process {} finished</wps:ProcessSucceeded>'
                         .format(self.process_public.title))

        url = self.make_url(params_template.format(self.process_private.identifier))
        resp = self.app.get(url, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<ows:ExceptionText>Unknown process')
"""
Based on tests from:

* https://github.com/geopython/pywps/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""
import unittest
from xml.etree import ElementTree

import pyramid.testing
import pytest

from tests.utils import (
    get_test_weaver_app,
    get_test_weaver_config,
    setup_config_with_celery,
    setup_config_with_mongodb,
    setup_config_with_pywps,
    setup_mongodb_processstore
)
from weaver.formats import CONTENT_TYPE_ANY_XML
from weaver.processes.wps_default import HelloWPS
from weaver.processes.wps_testing import WpsTestProcess
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC


@pytest.mark.functional
class WpsAppTest(unittest.TestCase):
    def setUp(self):
        self.wps_path = "/ows/wps"
        settings = {
            "weaver.url": "",
            "weaver.wps": True,
            "weaver.wps_path": self.wps_path
        }
        config = get_test_weaver_config(settings=settings)
        config = setup_config_with_mongodb(config)
        config = setup_config_with_pywps(config)
        config = setup_config_with_celery(config)
        self.process_store = setup_mongodb_processstore(config)
        self.app = get_test_weaver_app(config=config, settings=settings)

        # add processes by database Process type
        self.process_public = WpsTestProcess(identifier="process_public")
        self.process_private = WpsTestProcess(identifier="process_private")
        self.process_store.save_process(self.process_public)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

        # add processes by pywps Process type
        self.process_store.save_process(HelloWPS())
        self.process_store.set_visibility(HelloWPS.identifier, VISIBILITY_PUBLIC)

    def tearDown(self):
        pyramid.testing.tearDown()

    def make_url(self, params):
        return "{}?{}".format(self.wps_path, params)

    @pytest.mark.online
    def test_getcaps(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        resp.mustcontain("</wps:Capabilities>")

    @pytest.mark.online
    def test_getcaps_filtered_processes_by_visibility(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        resp.mustcontain("<wps:ProcessOfferings>")
        root = ElementTree.fromstring(resp.text)
        process_offerings = list(filter(lambda e: "ProcessOfferings" in e.tag, list(root)))
        assert len(process_offerings) == 1
        processes = [p for p in process_offerings[0]]
        ids = [pi.text for pi in [list(filter(lambda e: e.tag.endswith("Identifier"), p))[0] for p in processes]]
        assert self.process_private.identifier not in ids
        assert self.process_public.identifier in ids

    @pytest.mark.online
    def test_describeprocess(self):
        template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"
        params = template.format(HelloWPS.identifier)
        resp = self.app.get(self.make_url(params))
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")

    @pytest.mark.online
    def test_describeprocess_filtered_processes_by_visibility(self):
        param_template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"

        url = self.make_url(param_template.format(self.process_public.identifier))
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")

        url = self.make_url(param_template.format(self.process_private.identifier))
        resp = self.app.get(url, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        resp.mustcontain("<ows:ExceptionText>Unknown process")

    @pytest.mark.online
    def test_execute_allowed(self):
        template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=name=tux"
        params = template.format(HelloWPS.identifier)
        url = self.make_url(params)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        status = "<wps:ProcessSucceeded>PyWPS Process {} finished</wps:ProcessSucceeded>".format(HelloWPS.title)
        resp.mustcontain(status)

    @pytest.mark.online
    def test_execute_with_visibility(self):
        params_template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=test_input=test"
        url = self.make_url(params_template.format(self.process_public.identifier, ))
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        resp.mustcontain("<wps:ProcessSucceeded>PyWPS Process {} finished</wps:ProcessSucceeded>"
                         .format(self.process_public.title))

        url = self.make_url(params_template.format(self.process_private.identifier))
        resp = self.app.get(url, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type in CONTENT_TYPE_ANY_XML
        resp.mustcontain("<ows:ExceptionText>Unknown process")

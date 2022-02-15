import logging
import os
from configparser import ConfigParser
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from owslib.wps import WPSExecution
from pyramid.httpexceptions import HTTPBadRequest, HTTPSeeOther
from pywps.app import Process as ProcessWPS, WPSRequest
from pywps.app.Service import Service as ServiceWPS
from pywps.inout.storage import StorageAbstract
from pywps.response import WPSResponse
from pywps.response.execute import ExecuteResponse
from requests.structures import CaseInsensitiveDict

from weaver.database import get_db
from weaver.datatype import Process
from weaver.exceptions import handle_known_exceptions
from weaver.formats import ContentType
from weaver.owsexceptions import OWSNoApplicableCode
from weaver.processes.convert import wps2json_job_payload
from weaver.processes.execution import submit_job_handler
from weaver.processes.types import ProcessType
from weaver.processes.utils import get_job_submission_response, get_process
from weaver.store.base import StoreProcesses
from weaver.utils import get_header, get_registry, get_settings, get_weaver_url
from weaver.visibility import Visibility
from weaver.wps.utils import (
    check_wps_status,
    get_wps_local_status_location,
    get_wps_output_context,
    get_wps_output_dir,
    get_wps_output_url,
    load_pywps_config
)
from weaver.wps_restapi import swagger_definitions as sd

LOGGER = logging.getLogger(__name__)
if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Union

    from weaver.datatype import Job
    from weaver.typedefs import (
        AnyRequestType,
        AnyHeadersContainer,
        HeadersType,
        HTTPValid,
        JSON,
        SettingsType,
        WPS_InputData,
        WPS_OutputRequested
    )


class ReferenceStatusLocationStorage(StorageAbstract):
    """
    Simple storage that simply redirects to a pre-existing status location.
    """
    # pylint: disable=W0222  # ignore mismatch signature of method params not employed

    def __init__(self, url_location, settings):
        # type: (str, SettingsType) -> None
        self._url = url_location
        # location might not exist yet based on worker execution timing
        self._file = get_wps_local_status_location(url_location, settings, must_exist=False)

    def url(self, *_, **__):
        """
        URL location of the XML status file.
        """
        return self._url

    def location(self, *_, **__):
        """
        Directory location of the XML status file.
        """
        return self._file

    def store(self, *_, **__):
        pass

    def write(self, *_, **__):
        pass


class WorkerRequest(WPSRequest):
    """
    Extended :mod:`pywps` request with additional handling provided by :mod:`weaver`.
    """
    _auth_headers = CaseInsensitiveDict({  # take advantage of case insensitive only, value don't care
        "Authorization": None,
        "X-Auth": None,
        sd.XAuthVaultFileHeader.name: None,
    })

    def __init__(self, http_request=None, http_headers=None, **kwargs):
        # type: (Optional[AnyRequestType], Optional[AnyHeadersContainer], Any) -> None
        super(WorkerRequest, self).__init__(http_request, **kwargs)
        self.auth_headers = CaseInsensitiveDict()
        if http_request:
            self.auth_headers.update(self.parse_auth_headers(http_request.headers))
        if http_headers:
            self.auth_headers.update(self.parse_auth_headers(http_headers))

    def parse_auth_headers(self, headers):
        # type: (Optional[AnyHeadersContainer]) -> HeadersType
        if not headers:
            return {}
        if isinstance(headers, list):
            headers = dict(headers)
        auth_headers = {}
        for name, value in headers.items():
            if name in self._auth_headers:
                auth_headers[name] = value
        return auth_headers


class WorkerExecuteResponse(ExecuteResponse):
    """
    XML response generator from predefined job status URL and executed process definition.
    """
    # pylint: disable=W0231,W0233  # FIXME: tmp until patched

    def __init__(self, wps_request, uuid, process, job_url, settings, *_, **__):
        # type: (WorkerRequest, str, ProcessWPS, str, SettingsType, Any, Any) -> None

        # FIXME: https://github.com/geopython/pywps/pull/578
        # temp patch, do what 'ExecuteResponse.__init__' does bypassing the problem super() call
        WPSResponse.__init__(self, wps_request, uuid)  # pylint: disable=W0231,W0233  # tmp until patched
        self.process = process
        self.outputs = {o.identifier: o for o in self.process.outputs}
        # should be following call, but causes infinite recursion until above fix is applied
        #   super(WorkerExecuteResponse, self).__init__(wps_request, job_id, process=wps_process)
        # --- end of patch ---

        # extra setup
        self.process._status_store = ReferenceStatusLocationStorage(job_url, settings)
        self.store_status_file = True  # enforce storage to provide the status location URL
        self.wps_request.raw = None    # make sure doc gets generated by disabling alternate raw data mode
        self._update_status_doc()      # generate 'doc' property with XML content for response


class WorkerService(ServiceWPS):
    """
    Dispatches PyWPS requests from WPS-1/2 XML endpoint to WPS-REST as appropriate.

    .. note::
        For every WPS-Request type, the parsing of XML content is already handled by the PyWPS service for GET/POST.
        All data must be retrieved from parsed :class:`WPSRequest` to avoid managing argument location and WPS versions.

    When ``GetCapabilities`` or ``DescribeProcess`` requests are received, directly return to result as XML based
    on content (no need to subprocess as Celery task that gets resolved quickly with only the process(es) details).
    When JSON content is requested, instead return the redirect link to corresponding WPS-REST API endpoint.

    When receiving ``Execute`` request, convert the XML payload to corresponding JSON and
    dispatch it to the Celery Worker to actually process it after job setup for monitoring.
    """

    def __init__(self, *_, is_worker=False, settings=None, **__):
        super(WorkerService, self).__init__(*_, **__)
        self.is_worker = is_worker
        self.settings = settings or get_settings()
        self.dispatched_processes = {}  # type: Dict[str, Process]

    @handle_known_exceptions
    def _get_capabilities_redirect(self, wps_request, *_, **__):
        # type: (WPSRequest, Any, Any) -> Optional[Union[WPSResponse, HTTPValid]]
        """
        Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON.
        """
        req = wps_request.http_request
        accept_type = get_header("Accept", req.headers)
        if accept_type == ContentType.APP_JSON:
            url = get_weaver_url(self.settings)
            resp = HTTPSeeOther(location="{}{}".format(url, sd.processes_service.path))  # redirect
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp
        return None

    def get_capabilities(self, wps_request, *_, **__):
        # type: (WPSRequest, Any, Any) -> Union[WPSResponse, HTTPValid]
        """
        Handles the ``GetCapabilities`` KVP/XML request submitted on the WPS endpoint.

        Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON or handle ``GetCapabilities`` normally.
        """
        resp = self._get_capabilities_redirect(wps_request, *_, **__)
        return resp or super(WorkerService, self).get_capabilities(wps_request, *_, **__)

    @handle_known_exceptions
    def _describe_process_redirect(self, wps_request, *_, **__):
        # type: (WPSRequest, Any, Any) -> Optional[Union[WPSResponse, HTTPValid]]
        """
        Redirects to WPS-REST endpoint if requested ``Content-Type`` is JSON.
        """
        req = wps_request.http_request
        accept_type = get_header("Accept", req.headers)
        if accept_type == ContentType.APP_JSON:
            url = get_weaver_url(self.settings)
            proc = wps_request.identifiers
            if not proc:
                raise HTTPBadRequest(sd.BadRequestGetProcessInfoResponse.description)
            if len(proc) > 1:
                raise HTTPBadRequest("Unsupported multi-process ID for description. Only provide one.")
            path = sd.process_service.path.format(process_id=proc[0])
            resp = HTTPSeeOther(location="{}{}".format(url, path))  # redirect
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp
        return None

    def describe(self, wps_request, *_, **__):
        # type: (WPSRequest, Any, Any) -> Union[WPSResponse, HTTPValid]
        """
        Handles the ``DescribeProcess`` KVP/XML request submitted on the WPS endpoint.

        Redirect to WPS-REST endpoint if requested ``Content-Type`` is JSON or handle ``DescribeProcess`` normally.
        """
        resp = self._describe_process_redirect(wps_request, *_, **__)
        return resp or super(WorkerService, self).describe(wps_request, *_, **__)

    @handle_known_exceptions
    def _submit_job(self, wps_request):
        # type: (WPSRequest) -> Union[WPSResponse, HTTPValid, JSON]
        """
        Dispatch operation to WPS-REST endpoint, which in turn should call back the real Celery Worker for execution.

        Returns the status response as is if XML, or convert it to JSON, according to request ``Accept`` header.
        """
        req = wps_request.http_request
        pid = wps_request.identifier
        ctx = get_wps_output_context(req)  # re-validate here in case submitted via WPS endpoint instead of REST-API
        proc = get_process(process_id=pid, settings=self.settings)  # raises if invalid or missing
        wps_process = self.processes.get(pid)

        # create the JSON payload from the XML content and submit job
        is_workflow = proc.type == ProcessType.WORKFLOW
        tags = req.args.get("tags", "").split(",") + ["xml", "wps-{}".format(wps_request.version)]
        data = wps2json_job_payload(wps_request, wps_process)
        body = submit_job_handler(data, self.settings, proc.processEndpointWPS1,
                                  process_id=pid, is_local=True, is_workflow=is_workflow, visibility=Visibility.PUBLIC,
                                  language=wps_request.language, tags=tags, auth=dict(req.headers), context=ctx)

        # if Accept was JSON, provide response content as is
        # if anything else (even */*), return as XML
        # NOTE:
        #   It is very important to respect default XML since 'owslib.wps.WebProcessingService' does not provide any
        #   way to provide explicitly Accept header. Even our Wps1Process as Workflow step depends on this behaviour.
        accept_type = get_header("Accept", req.headers)
        if accept_type == ContentType.APP_JSON:
            resp = get_job_submission_response(body)
            setattr(resp, "_update_status", lambda *_, **__: None)  # patch to avoid pywps server raising
            return resp

        return body

    @handle_known_exceptions
    def prepare_process_for_execution(self, identifier):
        # type: (str) -> ProcessWPS
        """
        Handles dispatched remote provider process preparation during execution request.
        """
        # remote provider processes to instantiate
        dispatch_process = self.dispatched_processes.get(identifier)
        if dispatch_process:
            LOGGER.debug("Preparing dispatched remote provider process definition for execution: [%s]", identifier)
            try:
                self.processes[identifier] = dispatch_process.wps()  # prepare operation looks within this mapping
                process_wps = super(WorkerService, self).prepare_process_for_execution(identifier)
            except Exception as exc:
                LOGGER.error("Error occurred during remote provider process creation for execution.", exc_info=exc)
                raise
            finally:
                # cleanup temporary references
                self.dispatched_processes.pop(identifier, None)
                self.processes.pop(identifier, None)
            return process_wps

        # local processes already loaded by the service
        return super(WorkerService, self).prepare_process_for_execution(identifier)

    def execute(self, identifier, wps_request, uuid):
        # type: (str, Union[WPSRequest, WorkerRequest], str) -> Union[WPSResponse, HTTPValid]
        """
        Handles the ``Execute`` KVP/XML request submitted on the WPS endpoint.

        Submit WPS request to corresponding WPS-REST endpoint and convert back for requested ``Accept`` content-type.

        Overrides the original execute operation, that will instead be handled by :meth:`execute_job` following
        callback from Celery Worker, which handles process job creation and monitoring.

        If ``Accept`` is JSON, the result is directly returned from :meth:`_submit_job`.
        If ``Accept`` is XML or undefined, :class:`WorkerExecuteResponse` converts the received JSON with XML template.
        """
        result = self._submit_job(wps_request)
        if not isinstance(result, dict):
            return result  # pre-built HTTP response with JSON contents when requested

        # otherwise, recreate the equivalent content with expected XML template format
        job_id = result["jobID"]
        wps_process = self.processes.get(wps_request.identifier)

        # because we are building the XML response (and JSON not explicitly requested)
        # caller is probably a WPS-1 client also expecting a status XML file
        # remap the status location accordingly from the current REST endpoint
        job_url = result["location"]
        if urlparse(job_url).path.endswith(f"/jobs/{job_id}"):
            # file status does not exist yet since client calling this method is waiting for it
            # pywps will generate it once the WorkerExecuteResponse is returned
            status_path = get_wps_local_status_location(job_url, self.settings, must_exist=False)
            wps_dir = get_wps_output_dir(self.settings)
            wps_url = get_wps_output_url(self.settings)
            job_url = status_path.replace(wps_dir, wps_url, 1)

        # when called by the WSGI app, 'WorkerExecuteResponse.__call__' on will generate the XML from 'doc' property,
        # which itself is generated by template substitution of data from above 'json' property
        try:
            return WorkerExecuteResponse(wps_request, job_id, wps_process, job_url, settings=self.settings)
        except Exception as ex:  # noqa
            LOGGER.exception("Error building XML response by PyWPS Service during WPS Execute result from worker.")
            message = "Failed building XML response from WPS Execute result. Error [{!r}]".format(ex)
            raise OWSNoApplicableCode(message, locator=job_id)

    def execute_job(self,
                    job,                # type: Job
                    wps_inputs,         # type: List[WPS_InputData]
                    wps_outputs,        # type: List[WPS_OutputRequested]
                    remote_process,     # type: Optional[Process]
                    headers,            # type: Optional[AnyHeadersContainer]
                    ):                  # type: (...) -> WPSExecution
        """
        Real execution of the process by active Celery Worker.
        """
        process_id = job.process
        execution = WPSExecution(version="2.0", url="localhost")
        xml_request = execution.buildRequest(process_id, wps_inputs, wps_outputs, mode=job.execution_mode, lineage=True)
        wps_request = WorkerRequest(http_headers=headers)
        wps_request.identifier = process_id
        wps_request.check_and_set_language(job.accept_language)
        wps_request.set_version("2.0.0")
        request_parser = wps_request._post_request_parser(wps_request.WPS.Execute().tag)  # noqa: W0212
        request_parser(xml_request)  # parses the submitted inputs/outputs data and request parameters

        # FIXME: patch erroneous WPS outputs mimeType as None handling until fixed
        #        (see: https://github.com/geopython/pywps/pull/623)
        for out in wps_request.outputs.values():
            if "mimetype" in out and out["mimetype"] is None:
                out["mimetype"] = ""

        # NOTE:
        #  Setting 'status = false' will disable async execution of 'pywps.app.Process.Process'
        #  but this is needed since this job is running within Celery worker already async
        #  (daemon process can't have children processes).
        wps_request.status = "false"

        # When 'execute' is called, pywps will in turn call 'prepare_process_for_execution',
        # which then setups and retrieves currently loaded 'local' processes.
        # Since only local processes were defined by 'get_pywps_service',
        # a temporary process must be added for remote providers execution.
        if not remote_process:
            worker_process_id = process_id
        else:
            worker_process_id = "wps_package-{}-{}".format(process_id, job.uuid)
            self.dispatched_processes[worker_process_id] = remote_process

        wps_response = super(WorkerService, self).execute(worker_process_id, wps_request, job.uuid)
        # re-enable creation of status file so we can find it since we disabled 'status' earlier for sync execution
        wps_response.store_status_file = True
        # update execution status with actual status file and apply required references
        execution = check_wps_status(location=wps_response.process.status_location, settings=self.settings)
        execution.request = xml_request
        return execution


def get_pywps_service(environ=None, is_worker=False):
    """
    Generates the PyWPS Service that provides WPS-1/2 XML endpoint.
    """
    environ = environ or {}
    try:
        # get config file
        registry = get_registry()
        settings = get_settings(registry)
        pywps_cfg = environ.get("PYWPS_CFG") or settings.get("PYWPS_CFG") or os.getenv("PYWPS_CFG")
        if not isinstance(pywps_cfg, ConfigParser) or not settings.get("weaver.wps_configured"):
            load_pywps_config(settings, config=pywps_cfg)

        # call pywps application with processes filtered according to the adapter's definition
        process_store = get_db(registry).get_store(StoreProcesses)  # type: StoreProcesses
        processes_wps = [process.wps() for process in
                         process_store.list_processes(visibility=Visibility.PUBLIC)]
        service = WorkerService(processes_wps, is_worker=is_worker, settings=settings)
    except Exception as ex:
        LOGGER.exception("Error occurred during PyWPS Service and/or Processes setup.")
        raise OWSNoApplicableCode("Failed setup of PyWPS Service and/or Processes. Error [{!r}]".format(ex))
    return service

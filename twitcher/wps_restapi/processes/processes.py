import json
import urllib2
from owslib.wps import is_reference
from time import sleep
from datetime import datetime
from twitcher.adapter import servicestore_factory
from owslib.wps import WebProcessingService
from owslib.wps import WPSException
from owslib.wps import ComplexDataInput
from owslib.wps import ASYNC, SYNC
from twitcher.wps_restapi.utils import *
from twitcher.wps_restapi.jobs import add_job, check_status
from twitcher.db import MongoDB
from pyramid_celery import celery_app as app
from lxml import etree


from celery.utils.log import get_task_logger
logger = get_task_logger(__name__)


def get_processes(request):
    """
    Retrieve available processes
    """
    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')

    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    processes = []
    for process in wps.processes:
        item = dict(
            id=process.identifier,
            title=getattr(process, 'title', ''),
            abstract=getattr(process, 'abstract', ''),
            url='{base_url}/providers/{provider_id}/processes/{process_id}'.format(
                base_url=restapi_base_url(request),
                provider_id=provider_id,
                process_id=process.identifier))
        processes.append(item)
    return processes



def describe_process(request):
    """
    Retrieve a process description
    """
    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')

    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    process = wps.describeprocess(process_id)

    inputs = [dict(
        id=getattr(dataInput, 'identifier', ''),
        title=getattr(dataInput, 'title', ''),
        abstract=getattr(dataInput, 'abstract', ''),
        minOccurs=getattr(dataInput, 'minOccurs', 0),
        maxOccurs=getattr(dataInput, 'maxOccurs', 0),
        dataType=dataInput.dataType,
        defaultValue=jsonify(getattr(dataInput, 'defaultValue', None)),
        allowedValues=[jsonify(value) for value in getattr(dataInput, 'allowedValues', [])],
        supportedValues=[jsonify(value) for value in getattr(dataInput, 'supportedValues', [])],
    ) for dataInput in getattr(process, 'dataInputs', [])]
    outputs = [dict(
        id=getattr(processOutput, 'identifier', ''),
        title=getattr(processOutput, 'title', ''),
        abstract=getattr(processOutput, 'abstract', ''),
        dataType=processOutput.dataType,
        defaultValue=jsonify(getattr(processOutput, 'defaultValue', None))
    ) for processOutput in getattr(process, 'processOutputs', [])]
    return dict(
        id=process_id,
        label=getattr(process, 'title', ''),
        description=getattr(process, 'abstract', ''),
        inputs = inputs,
        outputs = outputs
    )


def wait_secs(run_step=-1):
    secs_list = (2, 2, 2, 2, 2, 5, 5, 5, 5, 5, 10, 10, 10, 10, 10, 20, 20, 20, 20, 20, 30)
    if run_step >= len(secs_list):
        run_step = -1
    return secs_list[run_step]


def save_log(job, error=None):
    if error:
        log_msg = 'ERROR: {0.text} - code={0.code} - locator={0.locator}'.format(error)
    else:
        log_msg = '{0} {1:3d}%: {2}'.format(
            job.get('duration', 0),
            job.get('progress', 0),
            job.get('status_message', 'no message'))
    if 'log' not in job:
        job['log'] = []
    # skip same log messages
    if len(job['log']) == 0 or job['log'][-1] != log_msg:
        job['log'].append(log_msg)
        if error:
            logger.error(log_msg)
        else:
            logger.info(log_msg)


def _get_data(input_value):
    """
    Extract the data from the input value
    """
    # process output data are append into a list and
    # WPS standard v1.0.0 specify that Output data field has zero or one value
    if input_value.data:
        return input_value.data[0]
    else:
        return None


def _read_reference(input_value):
    """
    Read a WPS reference and return the content
    """
    try:
        return urllib2.urlopen(input_value.reference).read()
    except urllib2.URLError:
        # Don't raise exceptions coming from that.
        return None

def _get_json_multiple_inputs(input_value):
    """
    Since WPS standard does not allow to return multiple values for a single output,
    a lot of process actually return a json array containing references to these outputs.
    This function goal is to detect this particular format
    :return: An array of references if the input_value is effectively a json containing that,
             None otherwise
    """

    # Check for the json datatype and mimetype
    if input_value.dataType == 'ComplexData' and input_value.mimeType == 'application/json':

        # If the json data is referenced read it's content
        if input_value.reference:
            json_data_str = _read_reference(input_value)
        # Else get the data directly
        else:
            json_data_str = _get_data(input_value)

        # Load the actual json dict
        json_data = json.loads(json_data_str)

        if isinstance(json_data, list):
            for value in json_data:
                if not is_reference(value):
                    return None
            return json_data
    return None


def _jsonify_output(output, datatype):
    """
    Utility method to jsonify an output element.
    :param output An owslib.wps.Output to jsonify
    """
    json_output = dict(identifier=output.identifier,
                       title=output.title,
                       dataType=output.dataType or datatype)

    if not output.dataType:
        output.dataType = datatype

    # WPS standard v1.0.0 specify that either a reference or a data field has to be provided
    if output.reference:
        json_output['reference'] = output.reference

        # Handle special case where we have a reference to a json array containing dataset reference
        # Avoid reference to reference by fetching directly the dataset references
        json_array = _get_json_multiple_inputs(output)
        if json_array and all(str(ref).startswith('http') for ref in json_array):
            json_output['data'] = json_array
    else:
        # WPS standard v1.0.0 specify that Output data field has Zero or one value
        json_output['data'] = output.data[0] if output.data else None

    if json_output['dataType'] == 'ComplexData':
        json_output['mimeType'] = output.mimeType

    return json_output


@app.task(bind=True)
def execute_process(self, url, service_name, identifier, provider, inputs, outputs,
                    async=True, userid=None, caption=None, headers=None):
    registry = app.conf['PYRAMID_REGISTRY']
    db = MongoDB.get(registry)
    job = add_job(
        db,
        userid=userid,
        task_id=self.request.id,
        service_name=service_name,
        process_id=identifier,
        provider_id=provider,
        is_workflow=False,
        async=async,
        caption=caption)

    try:
        wps = WebProcessingService(url=url, headers=get_cookie_headers(headers), skip_caps=False, verify=False)
        #execution = wps.execute(identifier, inputs=inputs, output=outputs, async=async, lineage=True)
        execution = wps.execute(identifier, inputs=inputs, output=outputs, mode= ASYNC if async else SYNC, lineage=True)
        # job['service'] = wps.identification.title
        # job['title'] = getattr(execution.process, "title")
        if not execution.process and execution.errors:
            raise execution.errors[0]

        job['abstract'] = getattr(execution.process, "abstract")
        job['status_location'] = execution.statusLocation
        job['request'] = execution.request
        job['response'] = etree.tostring(execution.response)

        logger.debug("job init done %s ...", self.request.id)

        num_retries = 0
        run_step = 0
        while execution.isNotComplete() or run_step == 0:
            if num_retries >= 5:
                raise Exception("Could not read status document after 5 retries. Giving up.")
            try:
                execution = check_status(url=execution.statusLocation, verify=False,
                                         sleep_secs=wait_secs(run_step))
                job['response'] = etree.tostring(execution.response)
                job['status'] = execution.getStatus()
                job['status_message'] = execution.statusMessage
                job['progress'] = execution.percentCompleted
                duration = datetime.now() - job.get('created', datetime.now())
                job['duration'] = str(duration).split('.')[0]

                if execution.isComplete():
                    job['finished'] = datetime.now()
                    if execution.isSucceded():
                        logger.debug("job succeded")
                        job['progress'] = 100

                        process = wps.describeprocess(job['process_id'])

                        output_datatype = {
                            getattr(processOutput, 'identifier', ''): processOutput.dataType
                            for processOutput in getattr(process, 'processOutputs', [])}

                        job['outputs'] = [_jsonify_output(output, output_datatype[output.identifier])
                                          for output in execution.processOutputs]
                    else:
                        logger.debug("job failed.")
                        job['status_message'] = '\n'.join(error.text for error in execution.errors)
                        job['exceptions'] = [{
                            'Code': error.code,
                            'Locator': error.locator,
                            'Text': error.text
                        } for error in execution.errors]
                        for error in execution.errors:
                            save_log(job, error)
            except:
                num_retries += 1
                logger.exception("Could not read status xml document for job %s. Trying again ...", self.request.id)
                sleep(1)
            else:
                logger.debug("update job %s ...", self.request.id)
                num_retries = 0
                run_step += 1
            finally:
                save_log(job)
                db.jobs.update({'identifier': job['identifier']}, job)

    except (WPSException, Exception) as exc:
        logger.exception("Failed to run Job")
        job['status'] = "ProcessFailed"
        if isinstance(exc, WPSException):
            job['status_message'] = "Error: [{0}] {1}".format(exc.locator, exc.text)
        else:
            job['status_message'] = "Error: {0}".format(exc.message)

    finally:
        save_log(job)
        db.jobs.update({'identifier': job['identifier']}, job)

    return job['status']


def submit_job(request):
    """
    Execute a process. Parameters: ?sync-execute=true|false (false being the default value)

    Content-Type: application/json;

{
    "inputs": [
        {
            "id": "sosInputNiederschlag",
            "value": "http://www.fluggs.de/sos2/sos?service%3DSOS&version%3D2.0.0&request%3DGetObservation&responseformat%3Dhttp://www.opengis.net/om/2.0&observedProperty%3DNiederschlagshoehe&procedure%3DTagessumme&featureOfInterest%3DBever-Talsperre&&namespaces%3Dxmlns%28sams%2Chttp%3A%2F%2Fwww.opengis.net%2FsamplingSpatial%2F2.0%29%2Cxmlns%28om%2Chttp%3A%2F%2Fwww.opengis.net%2Fom%2F2.0%29&temporalFilter%3Dom%3AphenomenonTime%2C2016-01-01T10:00:00.00Z%2F2016-04-30T23:59:00.000Z",
			"type" : "text/plain"
        },
        {
            "id": "sosInputFuellstand",
            "value": "http://www.fluggs.de/sos2/sos?service%3DSOS&version%3D2.0.0&request%3DGetObservation&responseformat%3Dhttp://www.opengis.net/om/2.0&observedProperty%3DSpeicherfuellstand&procedure%3DEinzelwert&featureOfInterest%3DBever-Talsperre_Windenhaus&namespaces%3Dxmlns%28sams%2Chttp%3A%2F%2Fwww.opengis.net%2FsamplingSpatial%2F2.0%29%2Cxmlns%28om%2Chttp%3A%2F%2Fwww.opengis.net%2Fom%2F2.0%29&temporalFilter%3Dom%3AphenomenonTime%2C2016-01-01T10:00:00.00Z%2F2016-04-30T23:59:00.000Z",
			"type" : "text/plain"
        },
        {
            "id": "sosInputTarget",
            "value": "http://fluggs.wupperverband.de/sos2-tamis/service?service%3DSOS&version%3D2.0.0&request%3DGetObservation&responseformat%3Dhttp://www.opengis.net/om/2.0&observedProperty%3DWasserstand_im_Damm&procedure%3DHandeingabe&featureOfInterest%3DBever-Talsperre_MQA7_Piezometer_Kalkzone&namespaces%3Dxmlns%28sams%2Chttp%3A%2F%2Fwww.opengis.net%2FsamplingSpati-al%2F2.0%29%2Cxmlns%28om%2Chttp%3A%2F%2Fwww.opengis.net%2Fom%2F2.0%29&temporalFilter%3Dom%3AphenomenonTime%2C2016-01-01T00:01:00.00Z%2F2016-04-30T23:59:00.000Z",
			"type" : "text/plain"
        }
    ],
    "outputs": [
      {
              "id": "targetObs_plot",
              "type": "image/png"
       },
      {
              "id": "model_diagnostics",
              "type": "image/png"
       },
      {
              "id": "relations",
              "type": "image/png"
       },
      {
              "id": "model_prediction",
              "type": "text/csv"
       },
      {
              "id": "metaJson",
              "type": "application/json"
       },
      {
              "id": "dataJson",
              "type": "application/json"
       }
    ]
}

    """

    store = servicestore_factory(request.registry)

    # TODO Validate param somehow
    provider_id = request.matchdict.get('provider_id')
    process_id = request.matchdict.get('process_id')
    async = not request.params.getone('sync-execute') if 'sync-execute' in request.params else True

    service = store.fetch_by_name(provider_id, request=request)
    wps = WebProcessingService(url=service.url, headers=get_cookie_headers(request.headers))
    process = wps.describeprocess(process_id)

    # prepare inputs
    comp_inpts = []
    for inpt in process.dataInputs:
        if 'ComplexData' in inpt.dataType:
            comp_inpts.append(inpt.identifier)

    try:
        # need to use ComplexDataInput structure for complex input
        inputs = [(inpt['id'],
                   ComplexDataInput(inpt['value']) if inpt['id'] in comp_inpts else inpt['value'])
                  for inpt in request.json_body['inputs']]
    except KeyError:
        inputs = []

    # prepare outputs
    outputs = []
    for output in process.processOutputs:
        outputs.append(
            (output.identifier, output.dataType == 'ComplexData'))

    result = execute_process.delay(
        userid=request.unauthenticated_userid,
        url=wps.url,
        service_name=process_id,
        identifier=process.identifier,
        provider=provider_id,
        inputs=inputs,
        outputs=outputs,
        async=async,
        #Convert EnvironHeaders to a simple dict (should cherrypick the required headers)
        headers={k: v for k, v in request.headers.iteritems()})

    # Should return 201 response
    return {'jobID': result.id,
            'status': "ProcessAccepted",
            'location' : '{base_url}/providers/{provider_id}/processes/{process_id}/jobs/{job_id}'.format(
                base_url=restapi_base_url(request),
                provider_id=provider_id,
                process_id=process.identifier,
                job_id=result.id)
    }
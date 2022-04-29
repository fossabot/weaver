"""
Schema definitions for `OpenAPI` generation and validation of data from received requests and returned responses.

This module should contain any and every definitions in use to build the Swagger UI and the OpenAPI JSON schema
so that one can update the specification without touching any other files after the initial integration.

Schemas defined in this module are employed (through ``deserialize`` method calls) to validate that data conforms to
reported definitions. This makes the documentation of the API better aligned with resulting code execution under it.
It also provides a reference point for external users to understand expected data structures with complete schema
definitions generated on the exposed endpoints (JSON and Swagger UI).

The definitions are also employed to generate the `OpenAPI` definitions reported in the documentation published
on `Weaver`'s `ReadTheDocs` page.
"""
# pylint: disable=C0103,invalid-name
import datetime
import os
from copy import copy
from typing import TYPE_CHECKING

import duration
import yaml
from colander import DateTime, Email, Money, OneOf, Range, Regex, drop, null, required
from dateutil import parser as date_parser

from weaver import __meta__
from weaver.config import WeaverFeature
from weaver.execute import ExecuteControlOption, ExecuteMode, ExecuteResponse, ExecuteTransmissionMode
from weaver.formats import AcceptLanguage, ContentType
from weaver.owsexceptions import OWSMissingParameterValue
from weaver.processes.constants import (
    CWL_REQUIREMENT_APP_BUILTIN,
    CWL_REQUIREMENT_APP_DOCKER,
    CWL_REQUIREMENT_APP_DOCKER_GPU,
    CWL_REQUIREMENT_APP_ESGF_CWT,
    CWL_REQUIREMENT_APP_WPS1,
    CWL_REQUIREMENT_INIT_WORKDIR,
    OAS_DATA_TYPES,
    OAS_COMPLEX_TYPES,
    PACKAGE_ARRAY_BASE,
    PACKAGE_ARRAY_ITEMS,
    PACKAGE_CUSTOM_TYPES,
    PACKAGE_ENUM_BASE,
    PACKAGE_TYPE_POSSIBLE_VALUES,
    WPS_LITERAL_DATA_TYPE_NAMES,
    ProcessSchema
)
from weaver.quotation.status import QuoteStatus
from weaver.sort import Sort, SortMethods
from weaver.status import JOB_STATUS_CODE_API, Status
from weaver.visibility import Visibility
from weaver.wps_restapi.colander_extras import (
    AllOfKeywordSchema,
    AnyOfKeywordSchema,
    BoundedRange,
    EmptyMappingSchema,
    ExtendedBoolean as Boolean,
    ExtendedFloat as Float,
    ExtendedInteger as Integer,
    ExtendedMappingSchema,
    ExtendedSchemaNode,
    ExtendedSequenceSchema,
    ExtendedString as String,
    NotKeywordSchema,
    OneOfCaseInsensitive,
    OneOfKeywordSchema,
    PermissiveMappingSchema,
    PermissiveSequenceSchema,
    SchemeURL,
    SemanticVersion,
    StringRange,
    XMLObject
)
from weaver.wps_restapi.constants import ConformanceCategory, JobInputsOutputsSchema
from weaver.wps_restapi.patches import ServiceOnlyExplicitGetHead as Service  # warning: don't use 'cornice.Service'

if TYPE_CHECKING:
    from typing import Any, Union

    from weaver.typedefs import DatetimeIntervalType, SettingsType, TypedDict

    ViewInfo = TypedDict("ViewInfo", {"name": str, "pattern": str})


WEAVER_CONFIG_REMOTE_LIST = "[" + ", ".join(WeaverFeature.REMOTE) + "]"

API_TITLE = "Weaver REST API"
API_INFO = {
    "description": __meta__.__description__,
    "contact": {"name": __meta__.__authors__, "email": __meta__.__emails__, "url": __meta__.__source_repository__}
}
API_DOCS = {
    "description": f"{__meta__.__title__} documentation",
    "url": __meta__.__documentation_url__
}
DOC_URL = f"{__meta__.__documentation_url__}/en/latest"

CWL_VERSION = "v1.1"
CWL_REPO_URL = "https://github.com/common-workflow-language"
CWL_BASE_URL = "https://www.commonwl.org"
CWL_SPEC_URL = f"{CWL_BASE_URL}/#Specification"
CWL_USER_GUIDE_URL = f"{CWL_BASE_URL}/user_guide"
CWL_CMD_TOOL_URL = f"{CWL_BASE_URL}/{CWL_VERSION}/CommandLineTool.html"
CWL_WORKFLOW_URL = f"{CWL_BASE_URL}/{CWL_VERSION}/Workflow.html"
CWL_DOC_MESSAGE = (
    "Note that multiple formats are supported and not all specification variants or parameters "
    f"are presented here. Please refer to official CWL documentation for more details ({CWL_BASE_URL})."
)

IO_INFO_IDS = (
    "Identifier of the {first} {what}. To merge details between corresponding {first} and {second} "
    "{what} specifications, this is the value that will be used to associate them together."
)

OGC_API_REPO_URL = "https://github.com/opengeospatial/ogcapi-processes"
OGC_API_SCHEMA_URL = "https://raw.githubusercontent.com/opengeospatial/ogcapi-processes"
OGC_API_SCHEMA_VERSION = "master"

DATETIME_INTERVAL_CLOSED_SYMBOL = "/"
DATETIME_INTERVAL_OPEN_START_SYMBOL = "../"
DATETIME_INTERVAL_OPEN_END_SYMBOL = "/.."

# fields ordering for generation of ProcessDescription body (shared for OGC/OLD schema format)
PROCESS_DESCRIPTION_FIELD_FIRST = [
    "id",
    "title",
    "version",
    "mutable",
    "abstract",  # backward compat for deployment
    "description",
    "keywords",
    "metadata",
    "inputs",
    "outputs"
]
PROCESS_DESCRIPTION_FIELD_AFTER = [
    "processDescriptionURL",
    "processEndpointWPS1",
    "executeEndpoint",
    "links"
]
# fields ordering for nested process definition of OLD schema format of ProcessDescription
PROCESS_DESCRIPTION_FIELD_FIRST_OLD_SCHEMA = ["process"]
PROCESS_DESCRIPTION_FIELD_AFTER_OLD_SCHEMA = ["links"]

PROCESS_IO_FIELD_FIRST = ["id", "title", "description", "minOccurs", "maxOccurs"]
PROCESS_IO_FIELD_AFTER = ["literalDataDomains", "formats", "crs", "bbox"]

PROVIDER_DESCRIPTION_FIELD_FIRST = [
    "id",
    "title",
    "version",
    "mutable",
    "description",
    "url",
    "type",
    "public",
    "keywords",
    "metadata",
]
PROVIDER_DESCRIPTION_FIELD_AFTER = ["links"]

#########################################################
# Examples
#########################################################

# load examples by file names as keys
SCHEMA_EXAMPLE_DIR = os.path.join(os.path.dirname(__file__), "examples")
EXAMPLES = {}
for name in os.listdir(SCHEMA_EXAMPLE_DIR):
    path = os.path.join(SCHEMA_EXAMPLE_DIR, name)
    ext = os.path.splitext(name)[-1]
    with open(path, "r", encoding="utf-8") as f:
        if ext in [".json", ".yaml", ".yml"]:
            EXAMPLES[name] = yaml.safe_load(f)  # both JSON/YAML
        else:
            EXAMPLES[name] = f.read()


#########################################################
# API tags
#########################################################

TAG_API = "API"
TAG_JOBS = "Jobs"
TAG_VISIBILITY = "Visibility"
TAG_BILL_QUOTE = "Billing & Quoting"
TAG_PROVIDERS = "Providers"
TAG_PROCESSES = "Processes"
TAG_GETCAPABILITIES = "GetCapabilities"
TAG_DESCRIBEPROCESS = "DescribeProcess"
TAG_EXECUTE = "Execute"
TAG_DISMISS = "Dismiss"
TAG_STATUS = "Status"
TAG_DEPLOY = "Deploy"
TAG_RESULTS = "Results"
TAG_EXCEPTIONS = "Exceptions"
TAG_LOGS = "Logs"
TAG_VAULT = "Vault"
TAG_WPS = "WPS"
TAG_DEPRECATED = "Deprecated Endpoints"

###############################################################################
# API endpoints
# These "services" are wrappers that allow Cornice to generate the JSON API
###############################################################################

api_frontpage_service = Service(name="api_frontpage", path="/")
api_openapi_ui_service = Service(name="api_openapi_ui", path="/api")  # idem to swagger
api_swagger_ui_service = Service(name="api_swagger_ui", path="/swagger")
api_redoc_ui_service = Service(name="api_redoc_ui", path="/redoc")
api_versions_service = Service(name="api_versions", path="/versions")
api_conformance_service = Service(name="api_conformance", path="/conformance")
openapi_json_service = Service(name="openapi_json", path="/json")

quotes_service = Service(name="quotes", path="/quotations")
quote_service = Service(name="quote", path=quotes_service.path + "/{quote_id}")
bills_service = Service(name="bills", path="/bills")
bill_service = Service(name="bill", path=bills_service.path + "/{bill_id}")

jobs_service = Service(name="jobs", path="/jobs")
job_service = Service(name="job", path=jobs_service.path + "/{job_id}")
job_results_service = Service(name="job_results", path=job_service.path + "/results")
job_exceptions_service = Service(name="job_exceptions", path=job_service.path + "/exceptions")
job_outputs_service = Service(name="job_outputs", path=job_service.path + "/outputs")
job_inputs_service = Service(name="job_inputs", path=job_service.path + "/inputs")
job_logs_service = Service(name="job_logs", path=job_service.path + "/logs")

processes_service = Service(name="processes", path="/processes")
process_service = Service(name="process", path=processes_service.path + "/{process_id}")
process_quotes_service = Service(name="process_quotes", path=process_service.path + quotes_service.path)
process_quote_service = Service(name="process_quote", path=process_service.path + quote_service.path)
process_visibility_service = Service(name="process_visibility", path=process_service.path + "/visibility")
process_package_service = Service(name="process_package", path=process_service.path + "/package")
process_payload_service = Service(name="process_payload", path=process_service.path + "/payload")
process_jobs_service = Service(name="process_jobs", path=process_service.path + jobs_service.path)
process_job_service = Service(name="process_job", path=process_service.path + job_service.path)
process_results_service = Service(name="process_results", path=process_service.path + job_results_service.path)
process_inputs_service = Service(name="process_inputs", path=process_service.path + job_inputs_service.path)
process_outputs_service = Service(name="process_outputs", path=process_service.path + job_outputs_service.path)
process_exceptions_service = Service(name="process_exceptions", path=process_service.path + job_exceptions_service.path)
process_logs_service = Service(name="process_logs", path=process_service.path + job_logs_service.path)
process_execution_service = Service(name="process_execution", path=process_service.path + "/execution")

providers_service = Service(name="providers", path="/providers")
provider_service = Service(name="provider", path=providers_service.path + "/{provider_id}")
provider_processes_service = Service(name="provider_processes", path=provider_service.path + processes_service.path)
provider_process_service = Service(name="provider_process", path=provider_service.path + process_service.path)
provider_jobs_service = Service(name="provider_jobs", path=provider_service.path + process_jobs_service.path)
provider_job_service = Service(name="provider_job", path=provider_service.path + process_job_service.path)
provider_results_service = Service(name="provider_results", path=provider_service.path + process_results_service.path)
provider_inputs_service = Service(name="provider_inputs", path=provider_service.path + process_inputs_service.path)
provider_outputs_service = Service(name="provider_outputs", path=provider_service.path + process_outputs_service.path)
provider_logs_service = Service(name="provider_logs", path=provider_service.path + process_logs_service.path)
provider_exceptions_service = Service(name="provider_exceptions",
                                      path=provider_service.path + process_exceptions_service.path)
provider_execution_service = Service(name="provider_execution", path=provider_service.path + "/execution")

# backward compatibility deprecated routes
job_result_service = Service(name="job_result", path=job_service.path + "/result")
process_result_service = Service(name="process_result", path=process_service.path + job_result_service.path)
provider_result_service = Service(name="provider_result", path=provider_service.path + process_result_service.path)

vault_service = Service(name="vault", path="/vault")
vault_file_service = Service(name="vault_file", path=vault_service.path + "/{file_id}")

#########################################################
# Generic schemas
#########################################################


class SLUG(ExtendedSchemaNode):
    schema_type = String
    description = "Slug name pattern."
    example = "some-object-slug-name"
    pattern = r"^[A-Za-z0-9]+(?:(-|_)[A-Za-z0-9]+)*$"


class URL(ExtendedSchemaNode):
    schema_type = String
    description = "URL reference."
    format = "url"


class MediaType(ExtendedSchemaNode):
    schema_type = String
    description = "IANA identifier of content and format."
    example = ContentType.APP_JSON
    pattern = r"^\w+\/[-.\w]+(?:\+[-.\w]+)?(?:\;\s*.+)*$"


class QueryBoolean(Boolean):
    description = "Boolean query parameter that allows handles common truthy/falsy values."

    def __init__(self, *_, **__):
        # type: (*Any, **Any) -> None
        super(QueryBoolean, self).__init__(
            allow_string=True,
            false_choices=("False", "false", "0", "off", "no", "null", "Null", "none", "None", ""),
            true_choices=("True", "true", "1", "on", "yes")
        )


class DateTimeInterval(ExtendedSchemaNode):
    schema_type = String
    description = (
        "DateTime format against OGC API - Processes, "
        "to get values before a certain date-time use '../' before the date-time, "
        "to get values after a certain date-time use '/..' after the date-time like the example, "
        "to get values between two date-times use '/' between the date-times, "
        "to get values with a specific date-time just pass the datetime. "
    )
    example = "2022-03-02T03:32:38.487000+00:00/.."
    regex_datetime = r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(([+-]\d\d:\d\d)|Z)?)"
    regex_interval_closed = fr"{regex_datetime}\/{regex_datetime}"
    regex_interval_open_start = fr"\.\.\/{regex_datetime}"
    regex_interval_open_end = fr"{regex_datetime}\/\.\."

    pattern = fr"^{regex_datetime}|{regex_interval_closed}|{regex_interval_open_start}|{regex_interval_open_end}$"


class S3Bucket(ExtendedSchemaNode):
    schema_type = String
    description = "S3 bucket shorthand URL representation [s3://{bucket}/{job-uuid}/{output}.ext]"
    pattern = r"^s3://\S+$"


class FileLocal(ExtendedSchemaNode):
    schema_type = String
    description = "Local file reference."
    format = "file"
    validator = Regex(r"^(file://)?(?:/|[/?]\S+)$")


class FileURL(ExtendedSchemaNode):
    schema_type = String
    description = "URL file reference."
    format = "url"
    validator = SchemeURL(schemes=["http", "https"])


class VaultReference(ExtendedSchemaNode):
    schema_type = String
    description = "Vault file reference."
    example = "vault://399dc5ac-ff66-48d9-9c02-b144a975abe4"
    pattern = r"^vault://[a-f0-9]{8}(?:-?[a-f0-9]{4}){3}-?[a-f0-9]{12}$"


class ReferenceURL(AnyOfKeywordSchema):
    _any_of = [
        FileURL(),
        FileLocal(),
        S3Bucket(),
    ]


class ExecuteReferenceURL(AnyOfKeywordSchema):
    _any_of = [
        FileURL(),
        FileLocal(),
        S3Bucket(),
        VaultReference(),
    ]


class UUID(ExtendedSchemaNode):
    schema_type = String
    description = "Unique identifier."
    example = "a9d14bf4-84e0-449a-bac8-16e598efe807"
    format = "uuid"
    pattern = "^[a-f0-9]{8}(?:-?[a-f0-9]{4}){3}-?[a-f0-9]{12}$"
    title = "UUID"


class AnyIdentifier(SLUG):
    pass


class ProcessIdentifier(AnyOfKeywordSchema):
    description = "Process identifier."
    _any_of = [
        # UUID first because more strict than SLUG, and SLUG can be similar to UUID, but in the end any is valid
        UUID(description="Unique identifier."),
        SLUG(description="Generic identifier. This is a user-friendly slug-name. "
                         "Note that this will represent the latest process matching this name. "
                         "For specific process version, use the UUID instead.", title="ID"),
    ]


class Version(ExtendedSchemaNode):
    # note: internally use LooseVersion, so don't be too strict about pattern
    schema_type = String
    description = "Version string."
    example = "1.2.3"
    validator = SemanticVersion()


class ContentTypeHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Content-Type"
    schema_type = String


class ContentLengthHeader(ExtendedSchemaNode):
    name = "Content-Length"
    schema_type = String
    example = "125"


class ContentDispositionHeader(ExtendedSchemaNode):
    name = "Content-Disposition"
    schema_type = String
    example = "attachment; filename=test.json"


class DateHeader(ExtendedSchemaNode):
    description = "Creation date and time of the contents."
    name = "Date"
    schema_type = String
    example = "Thu, 13 Jan 2022 12:37:19 GMT"


class LastModifiedHeader(ExtendedSchemaNode):
    description = "Modification date and time of the contents."
    name = "Last-Modified"
    schema_type = String
    example = "Thu, 13 Jan 2022 12:37:19 GMT"


class AcceptHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept"
    schema_type = String
    # FIXME: raise HTTPNotAcceptable in not one of those?
    validator = OneOf([
        ContentType.APP_JSON,
        ContentType.APP_XML,
        ContentType.TEXT_XML,
        ContentType.TEXT_HTML,
        ContentType.TEXT_PLAIN,
        ContentType.ANY,
    ])
    missing = drop
    default = ContentType.APP_JSON  # defaults to JSON for easy use within browsers


class AcceptLanguageHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "Accept-Language"
    schema_type = String
    missing = drop
    default = AcceptLanguage.EN_CA
    # FIXME: oneOf validator for supported languages (?)


class JsonHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.APP_JSON, default=ContentType.APP_JSON)


class HtmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.TEXT_HTML, default=ContentType.TEXT_HTML)


class XmlHeader(ExtendedMappingSchema):
    content_type = ContentTypeHeader(example=ContentType.APP_XML, default=ContentType.APP_XML)


class XAuthDockerHeader(ExtendedSchemaNode):
    summary = "Authentication header for private Docker registry access."
    description = (
        "Authentication header for private registry access in order to retrieve the Docker image reference "
        "specified in an Application Package during Process deployment. When provided, this header should "
        "contain similar details as typical Authentication or X-Auth-Token headers "
        f"(see {DOC_URL}/package.html#dockerized-applications for more details)."
    )
    name = "X-Auth-Docker"
    example = "Basic {base64-auth-credentials}"
    schema_type = String
    missing = drop


class RequestContentTypeHeader(OneOfKeywordSchema):
    _one_of = [
        JsonHeader(),
        XmlHeader(),
    ]


class ResponseContentTypeHeader(OneOfKeywordSchema):
    _one_of = [
        JsonHeader(),
        XmlHeader(),
        HtmlHeader(),
    ]


class RequestHeaders(RequestContentTypeHeader):
    """
    Headers that can indicate how to adjust the behavior and/or result the be provided in the response.
    """
    accept = AcceptHeader()
    accept_language = AcceptLanguageHeader()


class ResponseHeaders(ResponseContentTypeHeader):
    """
    Headers describing resulting response.
    """


class RedirectHeaders(ResponseHeaders):
    Location = URL(example="https://job/123/result", description="Redirect resource location.")


class NoContent(ExtendedMappingSchema):
    description = "Empty response body."
    default = {}


class FileUploadHeaders(RequestContentTypeHeader):
    # MUST be multipart for upload
    content_type = ContentTypeHeader(
        example=f"{ContentType.MULTI_PART_FORM}; boundary=43003e2f205a180ace9cd34d98f911ff",
        default=ContentType.MULTI_PART_FORM,
        description="Desired Content-Type of the file being uploaded.", missing=required)
    content_length = ContentLengthHeader(description="Uploaded file contents size in bytes.")
    content_disposition = ContentDispositionHeader(example="form-data; name=\"file\"; filename=\"desired-name.ext\"",
                                                   description="Expected ")


class FileUploadContent(ExtendedSchemaNode):
    schema_type = String()
    description = (
        "Contents of the file being uploaded with multipart. When prefixed with 'Content-Type: {media-type}', the "
        "specified format will be applied to the input that will be attributed the 'vault://{UUID}' during execution. "
        "Contents can also have 'Content-Disposition' definition to provide the desired file name."
    )


class FileResponseHeaders(NoContent):
    content_type = ContentTypeHeader(example=ContentType.APP_JSON)
    content_length = ContentLengthHeader()
    content_disposition = ContentDispositionHeader()
    date = DateHeader()
    last_modified = LastModifiedHeader()


class AccessToken(ExtendedSchemaNode):
    schema_type = String


class DescriptionSchema(ExtendedMappingSchema):
    description = ExtendedSchemaNode(String(), description="Description of the obtained contents.")


class KeywordList(ExtendedSequenceSchema):
    keyword = ExtendedSchemaNode(String())


class Language(ExtendedSchemaNode):
    schema_type = String
    example = AcceptLanguage.EN_CA
    validator = OneOf(AcceptLanguage.values())


class ValueLanguage(ExtendedMappingSchema):
    lang = Language(missing=drop, description="Language of the value content.")


class LinkLanguage(ExtendedMappingSchema):
    hreflang = Language(missing=drop, description="Language of the content located at the link.")


class LinkHeader(ExtendedSchemaNode):
    schema_type = String
    example = "<http://example.com>; rel=\"relation\"; type=text/plain"


class MetadataBase(ExtendedMappingSchema):
    title = ExtendedSchemaNode(String(), missing=drop)


class MetadataRole(ExtendedMappingSchema):
    role = URL(missing=drop)


class LinkRelationshipType(OneOfKeywordSchema):
    description = (
        "Link relation as registered or extension type "
        "(see https://www.rfc-editor.org/rfc/rfc8288.html#section-2.1)."
    )
    _one_of = [
        SLUG(description=(
            "Relationship of the link to the current content. "
            "This should be one item amongst registered relations https://www.iana.org/assignments/link-relations/."
        )),
        URL(description="Fully qualified extension link relation to the current content.")
    ]


class LinkRelationship(ExtendedMappingSchema):
    rel = LinkRelationshipType()


class LinkBase(LinkLanguage, MetadataBase):
    href = URL(description="Hyperlink reference.")
    type = MediaType(description="IANA identifier of content-type located at the link.", missing=drop)


class Link(LinkRelationship, LinkBase):
    pass


class MetadataValue(NotKeywordSchema, ValueLanguage, MetadataBase):
    _not = [
        # make sure value metadata does not allow 'rel' and 'hreflang' reserved for link reference
        # explicitly refuse them such that when an href/rel link is provided, only link details are possible
        LinkRelationship(description="Field 'rel' must refer to a link reference with 'href'."),
        LinkLanguage(description="Field 'hreflang' must refer to a link reference with 'href'."),
    ]
    value = ExtendedSchemaNode(String(), description="Plain text value of the information.")


class MetadataLink(Link):
    pass


class MetadataContent(OneOfKeywordSchema):
    _one_of = [
        MetadataLink(),
        MetadataValue(),
    ]


class Metadata(MetadataContent, MetadataRole):
    pass


class MetadataList(ExtendedSequenceSchema):
    metadata = Metadata()


class LinkList(ExtendedSequenceSchema):
    description = "List of links relative to the applicable object."
    title = "Links"
    link = Link()


class LandingPage(ExtendedMappingSchema):
    links = LinkList()


# sub-schema within:
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/format.yaml
class FormatSchema(OneOfKeywordSchema):
    _one_of = [
        # pointer to a file or JSON schema relative item (as in OpenAPI definitions)
        ReferenceURL(description="Reference where the schema definition can be retrieved to describe referenced data."),
        # literal JSON schema, permissive since it can be anything
        PermissiveMappingSchema(description="Explicit schema definition of the formatted reference data.")
    ]

    # because some pre-existing processes + pywps default schema is ""
    # deserialization against the validator pattern of 'ReferenceURL' makes it always fail
    # this causes the whole 'Format' container (and others similar) fail and be dropped
    # to resolve this issue, preemptively detect the empty string and signal the parent OneOf to remove it
    def deserialize(self, cstruct):  # type: ignore
        if isinstance(cstruct, str) and cstruct == "":
            return drop  # field that refers to this schema will drop the field key entirely
        return super(FormatSchema, self).deserialize(cstruct)


class FormatMimeType(ExtendedMappingSchema):
    """
    Used to respect ``mimeType`` field to work with pre-existing processes.
    """
    mimeType = MediaType(default=ContentType.TEXT_PLAIN, example=ContentType.APP_JSON)
    encoding = ExtendedSchemaNode(String(), missing=drop)
    schema = FormatSchema(missing=drop)


class Format(ExtendedMappingSchema):
    """
    Used to respect ``mediaType`` field as suggested per `OGC-API`.
    """
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/format.yaml"
    mediaType = MediaType(default=ContentType.TEXT_PLAIN, example=ContentType.APP_JSON)
    encoding = ExtendedSchemaNode(String(), missing=drop)
    schema = FormatSchema(missing=drop)


class DeployFormatDefaultMimeType(FormatMimeType):
    description = (
        "Format for process input are assumed plain/text if the media-type was omitted and is not one of the known "
        "formats by this instance. When executing a job, the best match against supported formats by the process "
        "definition will be used to run the process, and will fallback to the default as last resort."
    )
    # NOTE:
    # The default is overridden from FormatMimeType since the FormatSelection 'oneOf' always fails,
    # due to the 'default' value which is always generated and it causes the presence of both Format and FormatMimeType
    mimeType = MediaType(example=ContentType.APP_JSON)


class DeployFormatDefault(Format):
    description = (
        "Format for process input are assumed plain/text if the media-type was omitted and is not one of the known "
        "formats by this instance. When executing a job, the best match against supported formats by the process "
        "definition will be used to run the process, and will fallback to the default as last resort."
    )
    # NOTE:
    # The default is overridden from Format since the FormatSelection 'oneOf' always fails,
    # due to the 'default' value which is always generated and it causes the presence of both Format and FormatMimeType
    mediaType = MediaType(example=ContentType.APP_JSON)


class FormatSelection(OneOfKeywordSchema):
    """
    Validation against ``mimeType`` or ``mediaType`` format.

    .. seealso::
        - :class:`DeployFormatDefault`
        - :class:`DeployFormatDefaultMimeType`

    .. note::
        Format are validated to be retro-compatible with pre-existing/deployed/remote processes.
    """
    _one_of = [
        DeployFormatDefault(),
        DeployFormatDefaultMimeType()
    ]


# only extra portion from:
# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1538-L1547
class FormatDescription(ExtendedMappingSchema):
    maximumMegabytes = ExtendedSchemaNode(Integer(), missing=drop, validator=Range(min=1))


# although original schema defines 'default' in above 'FormatDescription', separate it in order to omit it
# from 'ResultFormat' employed for result reporting, which shouldn't have a default (applied vs supported format)
class FormatDefault(ExtendedMappingSchema):
    default = ExtendedSchemaNode(
        Boolean(), missing=drop,
        # don't insert "default" field if omitted in deploy body to avoid causing differing "inputs"/"outputs"
        # definitions between the submitted payload and the validated one (in 'weaver.processes.utils._check_deploy')
        # default=False,
        description=(
            "Indicates if this format should be considered as the default one in case none of the other "
            "allowed or supported formats was matched nor provided as input during job submission."
        )
    )


class DescriptionFormat(Format, FormatDescription, FormatDefault):
    pass


class DeploymentFormat(FormatSelection, FormatDescription, FormatDefault):
    # NOTE:
    #   The 'OGC-API' suggest to use 'mediaType' field for format representation, but retro-compatibility is
    #   supported during deployment only, where either old 'mimeType' or new 'mediaType', but only 'mediaType'
    #   is used for process description and result reporting. This support is added for deployment so that
    #   pre-existing deploy definitions remain valid without need to update them.
    pass


class ResultFormat(FormatDescription):
    """
    Format employed for reference results respecting 'OGC API - Processes' schemas.
    """
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/formatDescription.yaml"
    mediaType = MediaType(String())
    encoding = ExtendedSchemaNode(String(), missing=drop)
    schema = FormatSchema(missing=drop)


class DescriptionFormatList(ExtendedSequenceSchema):
    format_item = DescriptionFormat()


class DeploymentFormatList(ExtendedSequenceSchema):
    format_item = DeploymentFormat()


class AdditionalParameterUnique(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), title="InputParameterLiteral.String"),
        ExtendedSchemaNode(Boolean(), title="InputParameterLiteral.Boolean"),
        ExtendedSchemaNode(Integer(), title="InputParameterLiteral.Integer"),
        ExtendedSchemaNode(Float(), title="InputParameterLiteral.Float"),
        # PermissiveMappingSchema(title="InputParameterLiteral.object"),
    ]


class AdditionalParameterListing(ExtendedSequenceSchema):
    param = AdditionalParameterUnique()


class AdditionalParameterValues(OneOfKeywordSchema):
    _one_of = [
        AdditionalParameterUnique(),
        AdditionalParameterListing()
    ]


class AdditionalParameterDefinition(ExtendedMappingSchema):
    name = SLUG(title="AdditionalParameterName", example="EOImage")
    values = AdditionalParameterValues(example=["true"])


class AdditionalParameterList(ExtendedSequenceSchema):
    param = AdditionalParameterDefinition()


class AdditionalParametersMeta(OneOfKeywordSchema):
    _one_of = [
        LinkBase(title="AdditionalParameterLink"),
        MetadataRole(title="AdditionalParameterRole")
    ]


class AdditionalParameters(ExtendedMappingSchema):
    parameters = AdditionalParameterList()


class AdditionalParametersItem(AnyOfKeywordSchema):
    _any_of = [
        AdditionalParametersMeta(),
        AdditionalParameters()
    ]


class AdditionalParametersList(ExtendedSequenceSchema):
    additionalParameter = AdditionalParametersItem()


class Content(ExtendedMappingSchema):
    href = ReferenceURL(description="URL to CWL file.", title="OWSContentURL",
                        default=drop,       # if invalid, drop it completely,
                        missing=required,   # but still mark as 'required' for parent objects
                        example="http://some.host/applications/cwl/multisensor_ndvi.cwl")


class Offering(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String(), missing=drop, description="Descriptor of represented information in 'content'.")
    content = Content()


class OWSContext(ExtendedMappingSchema):
    description = "OGC Web Service definition from an URL reference."
    title = "owsContext"
    offering = Offering()


class DescriptionBase(ExtendedMappingSchema):
    title = ExtendedSchemaNode(String(), missing=drop, description="Short human-readable name of the object.")
    description = ExtendedSchemaNode(String(), missing=drop, description="Detailed explanation of the object.")


class DescriptionLinks(ExtendedMappingSchema):
    links = LinkList(missing=drop, description="References to endpoints with information related to object.")


class ProcessContext(ExtendedMappingSchema):
    owsContext = OWSContext(missing=drop)


class DescriptionExtra(ExtendedMappingSchema):
    additionalParameters = AdditionalParametersList(missing=drop)


class DescriptionType(DescriptionBase, DescriptionLinks, DescriptionExtra):
    pass


class DeploymentType(DescriptionType):
    deprecated = True
    abstract = ExtendedSchemaNode(
        String(), missing=drop, deprecated=True,
        description="Description of the object. Will be replaced by 'description' field if not already provided. "
                    "Preserved for backward compatibility of pre-existing process deployment. "
                    "Consider using 'description' directly instead."
    )


class DescriptionMeta(ExtendedMappingSchema):
    # employ empty lists by default if nothing is provided for process description
    keywords = KeywordList(
        default=[],
        description="Keywords applied to the process for search and categorization purposes.")
    metadata = MetadataList(
        default=[],
        description="External references to documentation or metadata sources relevant to the process.")


class ProcessDeployMeta(ExtendedMappingSchema):
    # don't require fields at all for process deployment, default to empty if omitted
    keywords = KeywordList(
        missing=drop, default=[],
        description="Keywords applied to the process for search and categorization purposes.")
    metadata = MetadataList(
        missing=drop, default=[],
        description="External references to documentation or metadata sources relevant to the process.")


class InputOutputDescriptionMeta(ExtendedMappingSchema):
    # remove unnecessary empty lists by default if nothing is provided for inputs/outputs
    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        super(InputOutputDescriptionMeta, self).__init__(*args, **kwargs)
        for child in self.children:
            if child.name in ["keywords", "metadata"]:
                child.missing = drop


class ReferenceOAS(ExtendedMappingSchema):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/reference.yaml"
    _ref = ReferenceURL(name="$ref", description="External OpenAPI schema reference.")


class TypeOAS(ExtendedSchemaNode):
    name = "type"
    schema_type = String
    validator = OneOf(OAS_DATA_TYPES)


class EnumItemOAS(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String()),
    ]


class EnumOAS(ExtendedSequenceSchema):
    enum = EnumItemOAS()


class RequiredOAS(ExtendedSequenceSchema):
    required_field = ExtendedSchemaNode(String(), description="Name of the field that is required under the object.")


class MultipleOfOAS(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
    ]


class PermissiveDefinitionOAS(NotKeywordSchema, PermissiveMappingSchema):
    _not = [
        ReferenceOAS
    ]


# cannot make recursive declarative schemas
# simulate it and assume it is sufficient for validation purposes
class PseudoObjectOAS(OneOfKeywordSchema):
    _one_of = [
        ReferenceOAS(),
        PermissiveDefinitionOAS(),
    ]


class KeywordObjectOAS(ExtendedSequenceSchema):
    item = PseudoObjectOAS()


class AdditionalPropertiesOAS(OneOfKeywordSchema):
    _one_of = [
        ReferenceOAS(),
        PermissiveDefinitionOAS(),
        ExtendedSchemaNode(Boolean())
    ]


class AnyValueOAS(AnyOfKeywordSchema):
    _any_of = [
        PermissiveMappingSchema(),
        PermissiveSequenceSchema(),
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(Boolean()),
        ExtendedSchemaNode(String()),
    ]


# reference:
#   https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/schema.yaml
# note:
#   although reference definition provides multiple 'default: 0|false' entries, we omit them since the behaviour
#   of colander with extended schema nodes is to set this value by default in deserialize result if they were missing,
#   but reference 'default' correspond more to the default *interpretation* value if none was provided.
#   It is preferable in our case to omit (i.e.: drop) these defaults to keep obtained/resolved definitions succinct,
#   since those defaults can be defined (by default...) if needed. No reason to add them explicitly.
class PropertyOAS(PermissiveMappingSchema):
    _type = TypeOAS(name="type", missing=drop)  # not present if top-most schema is {allOf,anyOf,oneOf,not}
    _format = ExtendedSchemaNode(String(), name="format", missing=drop)
    default = AnyValueOAS(unknown="preserve", missing=drop)
    example = AnyValueOAS(unknown="preserve", missing=drop)
    title = ExtendedSchemaNode(String(), missing=drop)
    description = ExtendedSchemaNode(String(), missing=drop)
    enum = EnumOAS(missing=drop)
    items = PseudoObjectOAS(name="items", missing=drop)
    required = RequiredOAS(missing=drop)
    nullable = ExtendedSchemaNode(Boolean(), missing=drop)
    deprecated = ExtendedSchemaNode(Boolean(), missing=drop)
    read_only = ExtendedSchemaNode(Boolean(), name="readOnly", missing=drop)
    write_only = ExtendedSchemaNode(Boolean(), name="writeOnly", missing=drop)
    multiple_of = MultipleOfOAS(name="multipleOf", missing=drop, validator=BoundedRange(min=0, exclusive_min=True))
    minimum = ExtendedSchemaNode(Integer(), name="minLength", missing=drop, validator=Range(min=0))  # default=0
    maximum = ExtendedSchemaNode(Integer(), name="maxLength", missing=drop, validator=Range(min=0))
    exclusive_min = ExtendedSchemaNode(Boolean(), name="exclusiveMinimum", missing=drop)  # default=False
    exclusive_max = ExtendedSchemaNode(Boolean(), name="exclusiveMaximum", missing=drop)  # default=False
    min_length = ExtendedSchemaNode(Integer(), name="minLength", missing=drop, validator=Range(min=0))  # default=0
    max_length = ExtendedSchemaNode(Integer(), name="maxLength", missing=drop, validator=Range(min=0))
    pattern = ExtendedSchemaNode(Integer(), missing=drop)
    min_items = ExtendedSchemaNode(Integer(), name="minItems", missing=drop, validator=Range(min=0))  # default=0
    max_items = ExtendedSchemaNode(Integer(), name="maxItems", missing=drop, validator=Range(min=0))
    unique_items = ExtendedSchemaNode(Boolean(), name="uniqueItems", missing=drop)  # default=False
    min_prop = ExtendedSchemaNode(Integer(), name="minProperties", missing=drop, validator=Range(min=0))  # default=0
    max_prop = ExtendedSchemaNode(Integer(), name="maxProperties", missing=drop, validator=Range(min=0))
    content_type = ExtendedSchemaNode(String(), name="contentMediaType", missing=drop)
    content_encode = ExtendedSchemaNode(String(), name="contentEncoding", missing=drop)
    content_schema = ExtendedSchemaNode(String(), name="contentSchema", missing=drop)
    _not = PseudoObjectOAS(name="not", title="not", missing=drop)
    _all_of = KeywordObjectOAS(name="allOf", missing=drop)
    _any_of = KeywordObjectOAS(name="anyOf", missing=drop)
    _one_of = KeywordObjectOAS(name="oneOf", missing=drop)
    x_props = AdditionalPropertiesOAS(name="additionalProperties", missing=drop)
    properties = PermissiveMappingSchema(missing=drop)  # cannot do real recursive definitions, simply check mapping


class ObjectPropertiesOAS(ExtendedMappingSchema):
    property_name = PropertyOAS(
        variable="{property-name}",
        description="Named of the property being defined under the OpenAPI object.",
    )


# would not need this if we could do explicit recursive definitions but at the very least, validate that when a
# object type is specified, its properties are as well and are slightly more specific than permissive mapping
class ObjectOAS(ExtendedMappingSchema):
    _type = TypeOAS(name="type", missing=drop, validator=OneOf(OAS_COMPLEX_TYPES))
    properties = ObjectPropertiesOAS()  # required and more specific contrary to 'properties' in 'PropertyOAS'


# since we redefine 'properties', do not cause validation error for 'oneOf'
class DefinitionOAS(AnyOfKeywordSchema):
    _any_of = [
        ObjectOAS(),
        PropertyOAS(),  # for top-level keyword schemas {allOf,anyOf,oneOf,not}
    ]


class OAS(OneOfKeywordSchema):
    description = "OpenAPI schema definition."
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/schema.yaml"
    _one_of = [
        ReferenceOAS(),
        DefinitionOAS(),
    ]


class InputOutputDescriptionSchema(ExtendedMappingSchema):
    # empty dict means 'anything' in OpenAPI, in case it failed resolution
    # add it to avoid failing the full input deserialization in case our OpenAPI schemas definitions
    # are faulty/insufficiently defined (eg: recursive objects/properties) or missing OAS parameters
    schema = OAS(missing={}, default={})


class MinOccursDefinition(OneOfKeywordSchema):
    description = "Minimum amount of values required for this input."
    title = "MinOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0), title="MinOccurs.integer",
                           ddescription="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$", title="MinOccurs.string",
                           description="Numerical string representing a positive integer."),
    ]


class MaxOccursDefinition(OneOfKeywordSchema):
    description = "Maximum amount of values allowed for this input."
    title = "MaxOccurs"
    example = 1
    _one_of = [
        ExtendedSchemaNode(Integer(), validator=Range(min=0), title="MaxOccurs.integer",
                           description="Positive integer."),
        ExtendedSchemaNode(String(), validator=StringRange(min=0), pattern="^[0-9]+$", title="MaxOccurs.string",
                           description="Numerical string representing a positive integer."),
        ExtendedSchemaNode(String(), validator=OneOf(["unbounded"]), title="MaxOccurs.unbounded",
                           description="Special value indicating no limit to occurrences."),
    ]


class DescribeMinMaxOccurs(ExtendedMappingSchema):
    minOccurs = MinOccursDefinition()
    maxOccurs = MaxOccursDefinition()


class DeployMinMaxOccurs(ExtendedMappingSchema):
    # entirely omitted definitions are permitted to allow inference from fields in package (CWL) or using defaults
    # if explicitly provided though, schema format and values should be validated
    # - do not use 'missing=drop' to ensure we raise provided invalid value instead of ignoring it
    # - do not use any specific value (e.g.: 1) for 'default' such that we do not inject an erroneous value when it
    #   was originally omitted, since it could be resolved differently depending on matching CWL inputs definitions
    minOccurs = MinOccursDefinition(default=null, missing=null)
    maxOccurs = MaxOccursDefinition(default=null, missing=null)


# does not inherit from 'DescriptionLinks' because other 'ProcessDescription<>' schema depend from this without 'links'
class ProcessDescriptionType(DescriptionBase, DescriptionExtra):
    id = ProcessIdentifier()
    version = Version(missing=drop)
    mutable = ExtendedSchemaNode(Boolean(), default=True, description=(
        "Indicates if the process is mutable (dynamically deployed), or immutable (builtin with this instance)."
    ))


class InputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="input"))


class OutputIdentifierType(ExtendedMappingSchema):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="WPS", second="CWL", what="output"))


class DescribeWithFormats(ExtendedMappingSchema):
    formats = DescriptionFormatList()


class DeployWithFormats(ExtendedMappingSchema):
    formats = DeploymentFormatList()


class DescribeComplexInputType(DescribeWithFormats):
    pass


class DeployComplexInputType(DeployWithFormats):
    pass


class SupportedCRS(ExtendedMappingSchema):
    crs = URL(title="CRS", description="Coordinate Reference System")
    default = ExtendedSchemaNode(Boolean(), missing=drop)


class SupportedCRSList(ExtendedSequenceSchema):
    crs = SupportedCRS(title="SupportedCRS")


class BoundingBoxInputType(ExtendedMappingSchema):
    supportedCRS = SupportedCRSList()


# FIXME: support byte/binary type (string + format:byte) ?
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/binaryInputValue.yaml
class AnyLiteralType(OneOfKeywordSchema):
    """
    Submitted values that correspond to literal data.

    .. seealso::
        - :class:`AnyLiteralDataType`
        - :class:`AnyLiteralValueType`
        - :class:`AnyLiteralDefaultType`
    """
    _one_of = [
        ExtendedSchemaNode(Float(), description="Literal data type representing a floating point number."),
        ExtendedSchemaNode(Integer(), description="Literal data type representing an integer number."),
        ExtendedSchemaNode(Boolean(), description="Literal data type representing a boolean flag."),
        ExtendedSchemaNode(String(), description="Literal data type representing a generic string."),
    ]


class NumberType(OneOfKeywordSchema):
    """
    Represents a literal number, integer or float.
    """
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
    ]


class NumericType(OneOfKeywordSchema):
    """
    Represents a numeric-like value.
    """
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String(), pattern="^[0-9]+$"),
    ]


class LiteralReference(ExtendedMappingSchema):
    reference = ReferenceURL()


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1707-L1716
class NameReferenceType(ExtendedMappingSchema):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/nameReferenceType.yaml"
    name = ExtendedSchemaNode(String())
    reference = ReferenceURL(missing=drop, description="Reference URL to schema definition of the named entity.")


class DataTypeSchema(NameReferenceType):
    description = "Type of the literal data representation."
    title = "DataType"
    # any named type that can be converted by: 'weaver.processes.convert.any2wps_literal_datatype'
    name = ExtendedSchemaNode(String(), validator=OneOf(list(WPS_LITERAL_DATA_TYPE_NAMES)))


class UomSchema(NameReferenceType):
    title = "UnitOfMeasure"


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1423
# NOTE: Original is only 'string', but we allow any literal type
class AllowedValuesList(ExtendedSequenceSchema):
    value = AnyLiteralType()


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1772-L1787
# NOTE:
#   Contrary to original schema where all fields are 'string', we allow any literal type as well since those make more
#   sense when parsing corresponding data values (eg: float, integer, bool).
class AllowedRange(ExtendedMappingSchema):
    minimumValue = NumericType(missing=drop)
    maximumValue = NumericType(missing=drop)
    spacing = NumericType(missing=drop)
    rangeClosure = ExtendedSchemaNode(String(), missing=drop,
                                      validator=OneOf(["closed", "open", "open-closed", "closed-open"]))


class AllowedRangesList(ExtendedSequenceSchema):
    range = AllowedRange()


class AllowedValues(OneOfKeywordSchema):
    _one_of = [
        AllowedRangesList(description="List of value ranges and constraints."),  # array of {range}
        AllowedValuesList(description="List of enumerated allowed values."),     # array of "value"
        ExtendedSchemaNode(String(), description="Single allowed value."),       # single "value"
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1425-L1430
class AnyValue(ExtendedMappingSchema):
    anyValue = ExtendedSchemaNode(
        Boolean(), missing=drop, default=True,
        description="Explicitly indicate if any value is allowed. "
                    "This is the default behaviour if no other constrains are specified."
    )


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1801-L1803
class ValuesReference(ReferenceURL):
    description = "URL where to retrieve applicable values."


class ArrayLiteralType(ExtendedSequenceSchema):
    value_item = AnyLiteralType()


class ArrayLiteralDataType(ExtendedMappingSchema):
    data = ArrayLiteralType()


class ArrayLiteralValueType(ExtendedMappingSchema):
    value = ArrayLiteralType()


class AnyLiteralDataType(ExtendedMappingSchema):
    data = AnyLiteralType()


class AnyLiteralValueType(ExtendedMappingSchema):
    value = AnyLiteralType()


class AnyLiteralDefaultType(ExtendedMappingSchema):
    default = AnyLiteralType()


class LiteralDataValueDefinition(OneOfKeywordSchema):
    _one_of = [
        AllowedValues(description="Constraints of allowed values."),
        ValuesReference(description="Reference URL where to retrieve allowed values."),
        # 'AnyValue' must be last because it's the most permissive (always valid, default)
        AnyValue(description="Permissive definition for any allowed value."),
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1675-L1688
#  literalDataDomain:
#    valueDefinition: oneOf(<allowedValues, anyValue, valuesReference>)
#    defaultValue: <string>
#    dataType: <nameReferenceType>
#    uom: <nameReferenceType>
class LiteralDataDomain(ExtendedMappingSchema):
    default = ExtendedSchemaNode(Boolean(), default=True,
                                 description="Indicates if this literal data domain definition is the default one.")
    defaultValue = AnyLiteralType(missing=drop, description="Default value to employ if none was provided.")
    dataType = DataTypeSchema(missing=drop, description="Type name and reference of the literal data representation.")
    uom = UomSchema(missing=drop, description="Unit of measure applicable for the data.")
    valueDefinition = LiteralDataValueDefinition(description="Literal data domain constraints.")


class LiteralDataDomainList(ExtendedSequenceSchema):
    """
    Constraints that apply to the literal data values.
    """
    literalDataDomain = LiteralDataDomain()


# https://github.com/opengeospatial/ogcapi-processes/blob/e6893b/extensions/workflows/openapi/workflows.yaml#L1689-L1697
class LiteralDataType(NotKeywordSchema, ExtendedMappingSchema):
    # NOTE:
    #   Apply 'missing=drop' although original schema of 'literalDataDomains' (see link above) requires it because
    #   we support omitting it for minimalistic literal input definition.
    #   This is because our schema validation allows us to do detection of 'basic' types using the literal parsing.
    #   Because there is not explicit requirement though (ie: missing would fail schema validation), we must check
    #   that 'format' is not present to avoid conflict with minimalistic literal data definition in case of ambiguity.
    literalDataDomains = LiteralDataDomainList(missing=drop)
    _not = [
        DescribeWithFormats,
    ]


class LiteralInputType(LiteralDataType):
    pass


class DescribeInputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        # NOTE:
        #   LiteralInputType could be used to represent a complex input if the 'format' is missing in
        #   process description definition but is instead provided in CWL definition.
        #   This use case is still valid because 'format' can be inferred from the combining Process/CWL contents.
        BoundingBoxInputType,
        DescribeComplexInputType,  # should be 2nd to last because very permissive, but requires format at least
        LiteralInputType,  # must be last because it"s the most permissive (all can default if omitted)
    ]


class DeployInputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        # NOTE:
        #   LiteralInputType could be used to represent a complex input if the 'format' is missing in
        #   process deployment definition but is instead provided in CWL definition.
        #   This use case is still valid because 'format' can be inferred from the combining Process/CWL contents.
        BoundingBoxInputType,
        DeployComplexInputType,  # should be 2nd to last because very permissive, but requires formats at least
        LiteralInputType,  # must be last because it"s the most permissive (all can default if omitted)
    ]


class DescribeInputType(AllOfKeywordSchema):
    _all_of = [
        DescriptionType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DescribeInputTypeDefinition(),
        DescribeMinMaxOccurs(),
        DescriptionExtra(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DescribeInputTypeWithID(InputIdentifierType, DescribeInputType):
    title = "DescribeInputTypeWithID"


# Different definition than 'Describe' such that nested 'complex' type 'formats' can be validated and backward
# compatible with pre-existing/deployed/remote processes, with either ``mediaType`` and ``mimeType`` formats.
class DeployInputType(AllOfKeywordSchema):
    _all_of = [
        DeploymentType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DeployInputTypeDefinition(),
        DeployMinMaxOccurs(),
        DescriptionExtra(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DeployInputTypeWithID(InputIdentifierType, DeployInputType):
    pass


# for [{id: "", ...}] representation within ProcessDescription (OLD schema)
class DescribeInputTypeList(ExtendedSequenceSchema):
    """
    Listing of process inputs descriptions.
    """
    input = DescribeInputTypeWithID()


# for {"<id>": {...}} representation within ProcessDescription (OGC schema)
class DescribeInputTypeMap(PermissiveMappingSchema):
    """
    Description of all process inputs under mapping.
    """
    input_id = DescribeInputType(
        variable="{input-id}",
        description="Input definition under mapping of process description.",
        missing=drop,  # allowed because process can have empty inputs (see schema: ProcessDescriptionOGC)
    )


# for [{id: "", ...}] representation within ProcessDeployment (OLD schema)
class DeployInputTypeList(ExtendedSequenceSchema):
    """
    Listing of process input definitions to deploy.
    """
    input_item = DeployInputTypeWithID()


# for {"<id>": {...}} representation within ProcessDeployment (OGC schema)
class DeployInputTypeMap(PermissiveMappingSchema):
    """
    Definition of all process inputs under mapping.
    """
    input_id = DeployInputType(
        variable="{input-id}",
        description="Input definition under mapping of process deployment."
    )


class DeployInputTypeAny(OneOfKeywordSchema):
    _one_of = [
        DeployInputTypeList(),
        DeployInputTypeMap(),
    ]


class LiteralOutputType(LiteralDataType):
    pass


class BoundingBoxOutputType(ExtendedMappingSchema):
    supportedCRS = SupportedCRSList()


class DescribeComplexOutputType(DescribeWithFormats):
    pass


class DeployComplexOutputType(DeployWithFormats):
    pass


class DescribeOutputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        BoundingBoxOutputType,
        DescribeComplexOutputType,  # should be 2nd to last because very permissive, but requires formats at least
        LiteralOutputType,  # must be last because it's the most permissive (all can default if omitted)
    ]


class DeployOutputTypeDefinition(OneOfKeywordSchema):
    _one_of = [
        BoundingBoxOutputType,
        DeployComplexOutputType,  # should be 2nd to last because very permissive, but requires formats at least
        LiteralOutputType,  # must be last because it's the most permissive (all can default if omitted)
    ]


class DescribeOutputType(AllOfKeywordSchema):
    _all_of = [
        DescriptionType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DescribeOutputTypeDefinition(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DescribeOutputTypeWithID(OutputIdentifierType, DescribeOutputType):
    pass


class DescribeOutputTypeList(ExtendedSequenceSchema):
    """
    Listing of process outputs descriptions.
    """
    output = DescribeOutputTypeWithID()


# for {"<id>": {...}} representation within ProcessDescription (OGC schema)
class DescribeOutputTypeMap(PermissiveMappingSchema):
    """
    Definition of all process outputs under mapping.
    """
    output_id = DescribeOutputType(
        variable="{output-id}", title="ProcessOutputDefinition",
        description="Output definition under mapping of process description."
    )


# Different definition than 'Describe' such that nested 'complex' type 'formats' can be validated and backward
# compatible with pre-existing/deployed/remote processes, with either ``mediaType`` and ``mimeType`` formats.
class DeployOutputType(AllOfKeywordSchema):
    _all_of = [
        DeploymentType(),
        InputOutputDescriptionMeta(),
        InputOutputDescriptionSchema(),
        DeployOutputTypeDefinition(),
    ]

    _sort_first = PROCESS_IO_FIELD_FIRST
    _sort_after = PROCESS_IO_FIELD_AFTER


class DeployOutputTypeWithID(OutputIdentifierType, DeployOutputType):
    pass


# for [{id: "", ...}] representation within ProcessDeployment (OLD schema)
class DeployOutputTypeList(ExtendedSequenceSchema):
    """
    Listing of process output definitions to deploy.
    """
    input = DeployOutputTypeWithID()


# for {"<id>": {...}} representation within ProcessDeployment (OGC schema)
class DeployOutputTypeMap(PermissiveMappingSchema):
    """
    Definition of all process outputs under mapping.
    """
    input_id = DeployOutputType(
        variable="{input-id}",
        description="Output definition under mapping of process deployment."
    )


class DeployOutputTypeAny(OneOfKeywordSchema):
    _one_of = [
        DeployOutputTypeList,
        DeployOutputTypeMap,
    ]


class JobExecuteModeEnum(ExtendedSchemaNode):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/execute.yaml"
    schema_type = String
    title = "JobExecuteMode"
    # no default to enforce required input as per OGC-API schemas
    # default = EXECUTE_MODE_AUTO
    example = ExecuteMode.ASYNC
    validator = OneOf(ExecuteMode.values())


class JobControlOptionsEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobControlOptions"
    default = ExecuteControlOption.ASYNC
    example = ExecuteControlOption.ASYNC
    validator = OneOf(ExecuteControlOption.values())


class JobResponseOptionsEnum(ExtendedSchemaNode):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/execute.yaml"
    schema_type = String
    title = "JobResponseOptions"
    # no default to enforce required input as per OGC-API schemas
    # default = ExecuteResponse.DOCUMENT
    example = ExecuteResponse.DOCUMENT
    validator = OneOf(ExecuteResponse.values())


class TransmissionModeEnum(ExtendedSchemaNode):
    schema_type = String
    title = "TransmissionMode"
    default = ExecuteTransmissionMode.VALUE
    example = ExecuteTransmissionMode.VALUE
    validator = OneOf(ExecuteTransmissionMode.values())


class JobStatusEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobStatus"
    default = Status.ACCEPTED
    example = Status.ACCEPTED
    validator = OneOf(JOB_STATUS_CODE_API)


class JobTypeEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobType"
    default = null
    example = "process"
    validator = OneOf(["process", "provider", "service"])


class JobSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "JobSortingMethod"
    default = Sort.CREATED
    example = Sort.CREATED
    validator = OneOf(SortMethods.JOB)


class ProcessSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "ProcessSortMethod"
    default = Sort.ID
    example = Sort.CREATED
    validator = OneOf(SortMethods.PROCESS)


class QuoteSortEnum(ExtendedSchemaNode):
    schema_type = String
    title = "QuoteSortingMethod"
    default = Sort.ID
    example = Sort.PROCESS
    validator = OneOf(SortMethods.QUOTE)


class LaunchJobQuerystring(ExtendedMappingSchema):
    tags = ExtendedSchemaNode(String(), title="JobTags", default=None, missing=drop,
                              description="Comma separated tags that can be used to filter jobs later")


class VisibilityValue(ExtendedSchemaNode):
    schema_type = String
    validator = OneOf(Visibility.values())
    example = Visibility.PUBLIC


class JobAccess(VisibilityValue):
    pass


class VisibilitySchema(ExtendedMappingSchema):
    value = VisibilityValue()


#########################################################
# Path parameter definitions
#########################################################


class ProcessPath(ExtendedMappingSchema):
    # FIXME: support versioning with <id:tag> (https://github.com/crim-ca/weaver/issues/107)
    process_id = AnyIdentifier(description="Process identifier.", example="jsonarray2netcdf")


class ProviderPath(ExtendedMappingSchema):
    provider_id = AnyIdentifier(description="Remote provider identifier.", example="hummingbird")


class JobPath(ExtendedMappingSchema):
    job_id = UUID(description="Job ID", example="14c68477-c3ed-4784-9c0f-a4c9e1344db5")


class BillPath(ExtendedMappingSchema):
    bill_id = UUID(description="Bill ID")


class QuotePath(ExtendedMappingSchema):
    quote_id = UUID(description="Quote ID")


class ResultPath(ExtendedMappingSchema):
    result_id = UUID(description="Result ID")


#########################################################
# These classes define each of the endpoints parameters
#########################################################


class FrontpageEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class VersionsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class ConformanceQueries(ExtendedMappingSchema):
    category = ExtendedSchemaNode(
        String(),
        missing=drop,
        default=ConformanceCategory.CONFORMANCE,
        validator=OneOf(ConformanceCategory.values()),
        description="Select the desired conformance item references to be returned."
    )


class ConformanceEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = ConformanceQueries()


class OpenAPIEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class SwaggerUIEndpoint(ExtendedMappingSchema):
    pass


class RedocUIEndpoint(ExtendedMappingSchema):
    pass


class OWSNamespace(XMLObject):
    prefix = "ows"
    namespace = "http://www.opengis.net/ows/1.1"


class WPSNamespace(XMLObject):
    prefix = "wps"
    namespace = "http://www.opengis.net/wps/1.0.0"


class XMLNamespace(XMLObject):
    prefix = "xml"


class XMLReferenceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "href"
    prefix = "xlink"
    format = "url"


class MimeTypeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "mimeType"
    prefix = drop
    example = ContentType.APP_JSON


class EncodingAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "encoding"
    prefix = drop
    example = "UTF-8"


class OWSVersion(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Version"
    default = "1.0.0"
    example = "1.0.0"


class OWSAcceptVersions(ExtendedSequenceSchema, OWSNamespace):
    description = "Accepted versions to produce the response."
    name = "AcceptVersions"
    item = OWSVersion()


class OWSLanguage(ExtendedSchemaNode, OWSNamespace):
    description = "Desired language to produce the response."
    schema_type = String
    name = "Language"
    default = AcceptLanguage.EN_US
    example = AcceptLanguage.EN_CA


class OWSLanguageAttribute(OWSLanguage):
    description = "RFC-4646 language code of the human-readable text."
    name = "language"
    attribute = True


class OWSService(ExtendedSchemaNode, OWSNamespace):
    description = "Desired service to produce the response (SHOULD be 'WPS')."
    schema_type = String
    name = "service"
    attribute = True
    default = AcceptLanguage.EN_US
    example = AcceptLanguage.EN_CA


class WPSServiceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "service"
    attribute = True
    default = "WPS"
    example = "WPS"


class WPSVersionAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "version"
    attribute = True
    default = "1.0.0"
    example = "1.0.0"


class WPSLanguageAttribute(ExtendedSchemaNode, XMLNamespace):
    schema_type = String
    name = "lang"
    attribute = True
    default = AcceptLanguage.EN_US
    example = AcceptLanguage.EN_CA


class WPSParameters(ExtendedMappingSchema):
    service = ExtendedSchemaNode(String(), example="WPS", description="Service selection.",
                                 validator=OneOfCaseInsensitive(["WPS"]))
    request = ExtendedSchemaNode(String(), example="GetCapabilities", description="WPS operation to accomplish",
                                 validator=OneOfCaseInsensitive(["GetCapabilities", "DescribeProcess", "Execute"]))
    version = Version(exaple="1.0.0", default="1.0.0", validator=OneOf(["1.0.0", "2.0.0", "2.0"]))
    identifier = ExtendedSchemaNode(String(), exaple="hello", missing=drop,
                                    example="example-process,another-process",
                                    description="Single or comma-separated list of process identifiers to describe, "
                                                "and single one for execution.")
    data_inputs = ExtendedSchemaNode(String(), name="DataInputs", missing=drop,
                                     example="message=hi&names=user1,user2&value=1",
                                     description="Process execution inputs provided as Key-Value Pairs (KVP).")


class WPSOperationGetNoContent(ExtendedMappingSchema):
    description = "No content body provided (GET requests)."
    default = {}


class WPSOperationPost(ExtendedMappingSchema):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/RequestBaseType.xsd"
    accepted_versions = OWSAcceptVersions(missing=drop, default="1.0.0")
    language = OWSLanguageAttribute(missing=drop)
    service = OWSService()


class WPSGetCapabilitiesPost(WPSOperationPost, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_request.xsd"
    name = "GetCapabilities"
    title = "GetCapabilities"


class OWSIdentifier(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Identifier"


class OWSIdentifierList(ExtendedSequenceSchema, OWSNamespace):
    name = "Identifiers"
    item = OWSIdentifier()


class OWSTitle(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Title"


class OWSAbstract(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "Abstract"


class OWSMetadataLink(ExtendedSchemaNode, XMLObject):
    schema_name = "Metadata"
    schema_type = String
    attribute = True
    name = "Metadata"
    prefix = "xlink"
    example = "WPS"
    wrapped = False  # metadata xlink at same level as other items


class OWSMetadata(ExtendedSequenceSchema, OWSNamespace):
    schema_type = String
    name = "Metadata"
    title = OWSMetadataLink(missing=drop)


class WPSDescribeProcessPost(WPSOperationPost, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_request.xsd"
    name = "DescribeProcess"
    title = "DescribeProcess"
    identifier = OWSIdentifierList(
        description="Single or comma-separated list of process identifier to describe.",
        example="example"
    )


class WPSExecuteDataInputs(ExtendedMappingSchema, WPSNamespace):
    description = "XML data inputs provided for WPS POST request (Execute)."
    name = "DataInputs"
    title = "DataInputs"
    # FIXME: missing details about 'DataInputs'


class WPSExecutePost(WPSOperationPost, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_request.xsd"
    name = "Execute"
    title = "Execute"
    identifier = OWSIdentifier(description="Identifier of the process to execute with data inputs.")
    dataInputs = WPSExecuteDataInputs(description="Data inputs to be provided for process execution.")


class WPSRequestBody(OneOfKeywordSchema):
    _one_of = [
        WPSExecutePost(),
        WPSDescribeProcessPost(),
        WPSGetCapabilitiesPost(),
    ]
    examples = {
        "Execute": {
            "summary": "Execute request example.",
            "value": EXAMPLES["wps_execute_request.xml"]
        }
    }


class WPSHeaders(ExtendedMappingSchema):
    accept = AcceptHeader(missing=drop)


class WPSEndpointGet(ExtendedMappingSchema):
    header = WPSHeaders()
    querystring = WPSParameters()
    body = WPSOperationGetNoContent(missing=drop)


class WPSEndpointPost(ExtendedMappingSchema):
    header = WPSHeaders()
    body = WPSRequestBody()


class XMLBooleanAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = Boolean
    attribute = True


class XMLString(ExtendedSchemaNode, XMLObject):
    schema_type = String


class OWSString(ExtendedSchemaNode, OWSNamespace):
    schema_type = String


class OWSKeywordList(ExtendedSequenceSchema, OWSNamespace):
    title = "OWSKeywords"
    keyword = OWSString(name="Keyword", title="OWSKeyword", example="Weaver")


class OWSType(ExtendedMappingSchema, OWSNamespace):
    schema_type = String
    name = "Type"
    example = "theme"
    additionalProperties = {
        "codeSpace": {
            "type": "string",
            "example": "ISOTC211/19115",
            "xml": {"attribute": True}
        }
    }


class OWSPhone(ExtendedMappingSchema, OWSNamespace):
    name = "Phone"
    voice = OWSString(name="Voice", title="OWSVoice", example="1-234-567-8910", missing=drop)
    facsimile = OWSString(name="Facsimile", title="OWSFacsimile", missing=drop)


class OWSAddress(ExtendedMappingSchema, OWSNamespace):
    name = "Address"
    delivery_point = OWSString(name="DeliveryPoint", title="OWSDeliveryPoint",
                               example="123 Place Street", missing=drop)
    city = OWSString(name="City", title="OWSCity", example="Nowhere", missing=drop)
    country = OWSString(name="Country", title="OWSCountry", missing=drop)
    admin_area = OWSString(name="AdministrativeArea", title="AdministrativeArea", missing=drop)
    postal_code = OWSString(name="PostalCode", title="OWSPostalCode", example="A1B 2C3", missing=drop)
    email = OWSString(name="ElectronicMailAddress", title="OWSElectronicMailAddress",
                      example="mail@me.com", validator=Email, missing=drop)


class OWSContactInfo(ExtendedMappingSchema, OWSNamespace):
    name = "ContactInfo"
    phone = OWSPhone(missing=drop)
    address = OWSAddress(missing=drop)


class OWSServiceContact(ExtendedMappingSchema, OWSNamespace):
    name = "ServiceContact"
    individual = OWSString(name="IndividualName", title="OWSIndividualName", example="John Smith", missing=drop)
    position = OWSString(name="PositionName", title="OWSPositionName", example="One Man Team", missing=drop)
    contact = OWSContactInfo(missing=drop, default={})


class OWSServiceProvider(ExtendedMappingSchema, OWSNamespace):
    description = "Details about the institution providing the service."
    name = "ServiceProvider"
    title = "ServiceProvider"
    provider_name = OWSString(name="ProviderName", title="OWSProviderName", example="EXAMPLE")
    provider_site = OWSString(name="ProviderName", title="OWSProviderName", example="http://schema-example.com")
    contact = OWSServiceContact(required=False, defalult={})


class WPSDescriptionType(ExtendedMappingSchema, OWSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/DescriptionType.xsd"
    name = "DescriptionType"
    _title = OWSTitle(description="Title of the service.", example="Weaver")
    abstract = OWSAbstract(description="Detail about the service.", example="Weaver WPS example schema.", missing=drop)
    metadata = OWSMetadata(description="Metadata of the service.", example="Weaver WPS example schema.", missing=drop)


class OWSServiceIdentification(WPSDescriptionType, OWSNamespace):
    name = "ServiceIdentification"
    title = "ServiceIdentification"
    keywords = OWSKeywordList(name="Keywords")
    type = OWSType()
    svc_type = OWSString(name="ServiceType", title="ServiceType", example="WPS")
    svc_type_ver1 = OWSString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="1.0.0")
    svc_type_ver2 = OWSString(name="ServiceTypeVersion", title="ServiceTypeVersion", example="2.0.0")
    fees = OWSString(name="Fees", title="Fees", example="NONE", missing=drop, default="NONE")
    access = OWSString(name="AccessConstraints", title="AccessConstraints",
                       example="NONE", missing=drop, default="NONE")
    provider = OWSServiceProvider()


class OWSOperationName(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    attribute = True
    name = "name"
    example = "GetCapabilities"
    validator = OneOf(["GetCapabilities", "DescribeProcess", "Execute"])


class OperationLink(ExtendedSchemaNode, XMLObject):
    schema_type = String
    attribute = True
    name = "href"
    prefix = "xlink"
    example = "http://schema-example.com/wps"


class OperationRequest(ExtendedMappingSchema, OWSNamespace):
    href = OperationLink()


class OWS_HTTP(ExtendedMappingSchema, OWSNamespace):  # noqa: N802
    get = OperationRequest(name="Get", title="OWSGet")
    post = OperationRequest(name="Post", title="OWSPost")


class OWS_DCP(ExtendedMappingSchema, OWSNamespace):  # noqa: N802
    http = OWS_HTTP(name="HTTP", missing=drop)
    https = OWS_HTTP(name="HTTPS", missing=drop)


class Operation(ExtendedMappingSchema, OWSNamespace):
    name = OWSOperationName()
    dcp = OWS_DCP()


class OperationsMetadata(ExtendedSequenceSchema, OWSNamespace):
    name = "OperationsMetadata"
    op = Operation()


class ProcessVersion(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    attribute = True


class OWSProcessSummary(ExtendedMappingSchema, WPSNamespace):
    version = ProcessVersion(name="processVersion", default="None", example="1.2",
                             description="Version of the corresponding process summary.")
    identifier = OWSIdentifier(example="example", description="Identifier to refer to the process.")
    _title = OWSTitle(example="Example Process", description="Title of the process.")
    abstract = OWSAbstract(example="Process for example schema.", description="Detail about the process.")


class WPSProcessOfferings(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOfferings"
    title = "ProcessOfferings"
    process = OWSProcessSummary(name="Process")


class WPSLanguagesType(ExtendedSequenceSchema, WPSNamespace):
    title = "LanguagesType"
    wrapped = False
    lang = OWSLanguage(name="Language")


class WPSLanguageSpecification(ExtendedMappingSchema, WPSNamespace):
    name = "Languages"
    title = "Languages"
    default = OWSLanguage(name="Default")
    supported = WPSLanguagesType(name="Supported")


class WPSResponseBaseType(PermissiveMappingSchema, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/ResponseBaseType.xsd"
    service = WPSServiceAttribute()
    version = WPSVersionAttribute()
    lang = WPSLanguageAttribute()


class WPSProcessVersion(ExtendedSchemaNode, WPSNamespace):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/common/ProcessVersion.xsd"
    schema_type = String
    description = "Release version of this Process."
    name = "processVersion"
    attribute = True


class WPSInputDescriptionType(WPSDescriptionType):
    identifier = OWSIdentifier(description="Unique identifier of the input.")
    # override below to have different examples/descriptions
    _title = OWSTitle(description="Human-readable representation of the process input.")
    abstract = OWSAbstract(missing=drop)
    metadata = OWSMetadata(missing=drop)


class WPSLiteralInputType(ExtendedMappingSchema, XMLObject):
    pass


class WPSLiteralData(WPSLiteralInputType):
    name = "LiteralData"


class WPSCRSsType(ExtendedMappingSchema, WPSNamespace):
    crs = XMLString(name="CRS", description="Coordinate Reference System")


class WPSSupportedCRS(ExtendedSequenceSchema):
    crs = WPSCRSsType(name="CRS")


class WPSSupportedCRSType(ExtendedMappingSchema, WPSNamespace):
    name = "SupportedCRSsType"
    default = WPSCRSsType(name="Default")
    supported = WPSSupportedCRS(name="Supported")


class WPSBoundingBoxData(ExtendedMappingSchema, XMLObject):
    data = WPSSupportedCRSType(name="BoundingBoxData")


class WPSFormatDefinition(ExtendedMappingSchema, XMLObject):
    mime_type = XMLString(name="MimeType", default=ContentType.TEXT_PLAIN, example=ContentType.TEXT_PLAIN)
    encoding = XMLString(name="Encoding", missing=drop, example="base64")
    schema = XMLString(name="Schema", missing=drop)


class WPSFileFormat(ExtendedMappingSchema, XMLObject):
    name = "Format"
    format_item = WPSFormatDefinition()


class WPSFormatList(ExtendedSequenceSchema):
    format_item = WPSFileFormat()


class WPSComplexInputType(ExtendedMappingSchema, WPSNamespace):
    max_mb = XMLString(name="maximumMegabytes", attribute=True)
    defaults = WPSFileFormat(name="Default")
    supported = WPSFormatList(name="Supported")


class WPSComplexData(ExtendedMappingSchema, XMLObject):
    data = WPSComplexInputType(name="ComplexData")


class WPSInputFormChoice(OneOfKeywordSchema):
    title = "InputFormChoice"
    _one_of = [
        WPSComplexData(),
        WPSLiteralData(),
        WPSBoundingBoxData(),
    ]


class WPSMinOccursAttribute(MinOccursDefinition, XMLObject):
    name = "minOccurs"
    attribute = True


class WPSMaxOccursAttribute(MinOccursDefinition, XMLObject):
    name = "maxOccurs"
    prefix = drop
    attribute = True


class WPSDataInputDescription(ExtendedMappingSchema):
    min_occurs = WPSMinOccursAttribute()
    max_occurs = WPSMaxOccursAttribute()


class WPSDataInputItem(AllOfKeywordSchema, WPSNamespace):
    _all_of = [
        WPSInputDescriptionType(),
        WPSInputFormChoice(),
        WPSDataInputDescription(),
    ]


class WPSDataInputs(ExtendedSequenceSchema, WPSNamespace):
    name = "DataInputs"
    title = "DataInputs"
    input = WPSDataInputItem()


class WPSOutputDescriptionType(WPSDescriptionType):
    name = "OutputDescriptionType"
    title = "OutputDescriptionType"
    identifier = OWSIdentifier(description="Unique identifier of the output.")
    # override below to have different examples/descriptions
    _title = OWSTitle(description="Human-readable representation of the process output.")
    abstract = OWSAbstract(missing=drop)
    metadata = OWSMetadata(missing=drop)


class ProcessOutputs(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = WPSOutputDescriptionType()


class WPSGetCapabilities(WPSResponseBaseType):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsGetCapabilities_response.xsd"
    name = "Capabilities"
    title = "Capabilities"  # not to be confused by 'GetCapabilities' used for request
    svc = OWSServiceIdentification()
    ops = OperationsMetadata()
    offering = WPSProcessOfferings()
    languages = WPSLanguageSpecification()


class WPSProcessDescriptionType(WPSResponseBaseType, WPSProcessVersion):
    name = "ProcessDescriptionType"
    description = "Description of the requested process by identifier."
    store = XMLBooleanAttribute(name="storeSupported", example=True, default=True)
    status = XMLBooleanAttribute(name="statusSupported", example=True, default=True)
    inputs = WPSDataInputs()
    outputs = ProcessOutputs()


class WPSProcessDescriptionList(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessDescriptions"
    title = "ProcessDescriptions"
    description = "Listing of process description for every requested identifier."
    wrapped = False
    process = WPSProcessDescriptionType()


class WPSDescribeProcess(WPSResponseBaseType):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsDescribeProcess_response.xsd"
    name = "DescribeProcess"
    title = "DescribeProcess"
    process = WPSProcessDescriptionList()


class WPSStatusLocationAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "statusLocation"
    prefix = drop
    attribute = True
    format = "file"


class WPSServiceInstanceAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "serviceInstance"
    prefix = drop
    attribute = True
    format = "url"


class CreationTimeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = DateTime
    name = "creationTime"
    title = "CreationTime"
    prefix = drop
    attribute = True


class WPSStatusSuccess(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    name = "ProcessSucceeded"
    title = "ProcessSucceeded"


class WPSStatusFailed(ExtendedSchemaNode, WPSNamespace):
    schema_type = String
    name = "ProcessFailed"
    title = "ProcessFailed"


class WPSStatus(ExtendedMappingSchema, WPSNamespace):
    name = "Status"
    title = "Status"
    creationTime = CreationTimeAttribute()
    status_success = WPSStatusSuccess(missing=drop)
    status_failed = WPSStatusFailed(missing=drop)


class WPSProcessSummary(ExtendedMappingSchema, WPSNamespace):
    name = "Process"
    title = "Process"
    identifier = OWSIdentifier()
    _title = OWSTitle()
    abstract = OWSAbstract(missing=drop)


class WPSOutputBase(ExtendedMappingSchema):
    identifier = OWSIdentifier()
    _title = OWSTitle()
    abstract = OWSAbstract(missing=drop)


class WPSOutputDefinitionItem(WPSOutputBase, WPSNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'WPSProcessOutputs'
    title = "OutputDefinition"


class WPSOutputDefinitions(ExtendedSequenceSchema, WPSNamespace):
    name = "OutputDefinitions"
    title = "OutputDefinitions"
    out_def = WPSOutputDefinitionItem()


class WPSOutputLiteral(ExtendedMappingSchema):
    data = ()


class WPSReference(ExtendedMappingSchema, WPSNamespace):
    href = XMLReferenceAttribute()
    mimeType = MimeTypeAttribute()
    encoding = EncodingAttribute()


class WPSOutputReference(ExtendedMappingSchema):
    title = "OutputReference"
    reference = WPSReference(name="Reference")


class WPSOutputData(OneOfKeywordSchema):
    _one_of = [
        WPSOutputLiteral(),
        WPSOutputReference(),
    ]


class WPSDataOutputItem(AllOfKeywordSchema, WPSNamespace):
    name = "Output"
    # use different title to avoid OpenAPI schema definition clash with 'Output' of 'WPSOutputDefinitions'
    title = "DataOutput"
    _all_of = [
        WPSOutputBase(),
        WPSOutputData(),
    ]


class WPSProcessOutputs(ExtendedSequenceSchema, WPSNamespace):
    name = "ProcessOutputs"
    title = "ProcessOutputs"
    output = WPSDataOutputItem()


class WPSExecuteResponse(WPSResponseBaseType, WPSProcessVersion):
    schema_ref = "http://schemas.opengis.net/wps/1.0.0/wpsExecute_response.xsd"
    name = "ExecuteResponse"
    title = "ExecuteResponse"  # not to be confused by 'Execute' used for request
    location = WPSStatusLocationAttribute()
    svc_loc = WPSServiceInstanceAttribute()
    process = WPSProcessSummary()
    status = WPSStatus()
    inputs = WPSDataInputs(missing=drop)          # when lineage is requested only
    out_def = WPSOutputDefinitions(missing=drop)  # when lineage is requested only
    outputs = WPSProcessOutputs()


class WPSXMLSuccessBodySchema(OneOfKeywordSchema):
    _one_of = [
        WPSGetCapabilities(),
        WPSDescribeProcess(),
        WPSExecuteResponse(),
    ]


class OWSExceptionCodeAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "exceptionCode"
    title = "Exception"
    attribute = True


class OWSExceptionLocatorAttribute(ExtendedSchemaNode, XMLObject):
    schema_type = String
    name = "locator"
    attribute = True


class OWSExceptionText(ExtendedSchemaNode, OWSNamespace):
    schema_type = String
    name = "ExceptionText"


class OWSException(ExtendedMappingSchema, OWSNamespace):
    name = "Exception"
    title = "Exception"
    code = OWSExceptionCodeAttribute(example="MissingParameterValue")
    locator = OWSExceptionLocatorAttribute(default="None", example="service")
    text = OWSExceptionText(example="Missing service")


class OWSExceptionReport(ExtendedMappingSchema, OWSNamespace):
    name = "ExceptionReport"
    title = "ExceptionReport"
    exception = OWSException()


class WPSException(ExtendedMappingSchema):
    report = OWSExceptionReport()


class OkWPSResponse(ExtendedMappingSchema):
    description = "WPS operation successful"
    header = XmlHeader()
    body = WPSXMLSuccessBodySchema()


class ErrorWPSResponse(ExtendedMappingSchema):
    description = "Unhandled error occurred on WPS endpoint."
    header = XmlHeader()
    body = WPSException()


class ProviderEndpoint(ProviderPath):
    header = RequestHeaders()


class ProcessDescriptionQuery(ExtendedMappingSchema):
    # see: 'ProcessDescription' schema and 'Process.offering' method
    schema = ExtendedSchemaNode(
        String(), example=ProcessSchema.OGC, default=ProcessSchema.OGC,
        validator=OneOfCaseInsensitive(ProcessSchema.values()),
        summary="Selects the desired schema representation of the process description",
        description=(
            "Selects the desired schema representation of the process description. "
            f"When '{ProcessSchema.OGC}' is used, inputs and outputs will be represented as mapping of objects. "
            "Process metadata are also directly provided at the root of the content. "
            f"When '{ProcessSchema.OLD}' is used, inputs and outputs will be represented as list of objects with ID. "
            "Process metadata are also reported nested under a 'process' field. "
            "See '#/definitions/ProcessDescription' schema for more details about each case."
        )
    )


class ProviderProcessEndpoint(ProviderPath, ProcessPath):
    header = RequestHeaders()
    querystring = ProcessDescriptionQuery()


class ProcessEndpoint(ProcessPath):
    header = RequestHeaders()
    querystring = ProcessDescriptionQuery()


class ProcessPackageEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessPayloadEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityGetEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessVisibilityPutEndpoint(ProcessPath):
    header = RequestHeaders()
    body = VisibilitySchema()


class ProviderJobEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobEndpoint(JobPath):
    header = RequestHeaders()


class ProcessInputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderInputsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobInputsOutputsQuery(ExtendedMappingSchema):
    schema = ExtendedSchemaNode(
        String(),
        title="JobInputsOutputsQuerySchema",
        example=JobInputsOutputsSchema.OGC,
        default=JobInputsOutputsSchema.OLD,
        validator=OneOfCaseInsensitive(JobInputsOutputsSchema.values()),
        summary="Selects the schema employed for representation of submitted job inputs and outputs.",
        description=(
            "Selects the schema employed for representing job inputs and outputs that were submitted for execution. "
            f"When '{JobInputsOutputsSchema.OLD}' is employed, listing of object with IDs is returned. "
            f"When '{JobInputsOutputsSchema.OGC}' is employed, mapping of object definitions is returned. "
            "If no schema is requested, the original formats from submission are employed, which could be a mix of "
            "both representations. Providing a schema forces their corresponding conversion as applicable."
        )
    )


class JobInputsEndpoint(JobPath):
    header = RequestHeaders()
    querystring = JobInputsOutputsQuery()


class JobOutputQuery(ExtendedMappingSchema):
    schema = ExtendedSchemaNode(
        String(),
        title="JobOutputResultsSchema",
        example=JobInputsOutputsSchema.OGC,
        default=JobInputsOutputsSchema.OLD,
        validator=OneOfCaseInsensitive(JobInputsOutputsSchema.values()),
        summary="Selects the schema employed for representation of job outputs.",
        description=(
            "Selects the schema employed for representation of job outputs for providing file Content-Type details. "
            f"When '{JobInputsOutputsSchema.OLD}' is employed, "
            "'format.mimeType' is used and 'type' is reported as well. "
            f"When '{JobInputsOutputsSchema.OGC}' is employed, "
            "'format.mediaType' is used and 'type' is reported as well. "
            "When the '+strict' value is added, only the 'format' or 'type' will be represented according to the "
            f"reference standard ({JobInputsOutputsSchema.OGC}, {JobInputsOutputsSchema.OLD}) representation."
        )
    )


class ProcessOutputsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()
    querystring = JobOutputQuery()


class ProviderOutputsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()
    querystring = JobOutputQuery()


class JobOutputsEndpoint(JobPath):
    header = RequestHeaders()
    querystring = JobOutputQuery()


class ProcessResultEndpoint(ProcessOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class ProviderResultEndpoint(ProviderOutputsEndpoint):
    deprecated = True
    header = RequestHeaders()


class JobResultEndpoint(JobPath):
    deprecated = True
    header = RequestHeaders()


class ProcessResultsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobResultsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderExceptionsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobExceptionsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessExceptionsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


class ProviderLogsEndpoint(ProviderPath, ProcessPath, JobPath):
    header = RequestHeaders()


class JobLogsEndpoint(JobPath):
    header = RequestHeaders()


class ProcessLogsEndpoint(ProcessPath, JobPath):
    header = RequestHeaders()


##################################################################
# These classes define schemas for requests that feature a body
##################################################################


class ProviderPublic(ExtendedMappingSchema):
    public = ExtendedSchemaNode(
        Boolean(),
        default=False,
        description="Whether the service is defined as publicly visible. "
                    "This will not control allowance/denial of requests to the registered endpoint of the service. "
                    "It only indicates if it should appear during listing of providers."
    )


class CreateProviderRequestBody(ProviderPublic):
    id = AnyIdentifier()
    url = URL(description="Endpoint where to query the provider.")


class ExecuteInputDataType(InputIdentifierType):
    pass


class ExecuteOutputDataType(OutputIdentifierType):
    pass


class ExecuteOutputDefinition(ExtendedMappingSchema):
    transmissionMode = TransmissionModeEnum(missing=drop)
    format = Format(missing=drop)


class ExecuteOutputItem(ExecuteOutputDataType, ExecuteOutputDefinition):
    pass


class ExecuteOutputSpecList(ExtendedSequenceSchema):
    """
    Filter list of outputs to be obtained from execution and their reporting method.
    """
    output = ExecuteOutputItem()


class ExecuteOutputMapAdditionalProperties(ExtendedMappingSchema):
    output_id = ExecuteOutputDefinition(variable="{output-id}", title="ExecuteOutputSpecMap",
                                        description="Desired output reporting method.")


class ExecuteOutputSpecMap(AnyOfKeywordSchema):
    _any_of = [
        ExecuteOutputMapAdditionalProperties(),  # normal {"<output-id>": {...}}
        EmptyMappingSchema(),                    # allows explicitly provided {}
    ]


class ExecuteOutputSpec(OneOfKeywordSchema):
    """
    Filter list of outputs to be obtained from execution and define their reporting method.
    """
    _one_of = [
        # OLD format: {"outputs": [{"id": "<id>", "transmissionMode": "value|reference"}, ...]}
        ExecuteOutputSpecList(),
        # OGC-API:    {"inputs": {"<id>": {"transmissionMode": "value|reference"}, ...}}
        ExecuteOutputSpecMap(),
    ]


class ProviderNameSchema(AnyIdentifier):
    title = "ProviderName"
    description = "Identifier of the remote provider."


class ProviderSummarySchema(DescriptionType, ProviderPublic, DescriptionMeta, DescriptionLinks):
    """
    Service provider summary definition.
    """
    id = ProviderNameSchema()
    url = URL(description="Endpoint of the service provider.")
    type = ExtendedSchemaNode(String())

    _sort_first = PROVIDER_DESCRIPTION_FIELD_FIRST
    _sort_after = PROVIDER_DESCRIPTION_FIELD_AFTER


class ProviderCapabilitiesSchema(ProviderSummarySchema):
    """
    Service provider detailed capabilities.
    """


class TransmissionModeList(ExtendedSequenceSchema):
    transmissionMode = TransmissionModeEnum()


class JobControlOptionsList(ExtendedSequenceSchema):
    jobControlOption = JobControlOptionsEnum()


class ExceptionReportType(ExtendedMappingSchema):
    code = ExtendedSchemaNode(String())
    description = ExtendedSchemaNode(String(), missing=drop)


class ProcessControl(ExtendedMappingSchema):
    jobControlOptions = JobControlOptionsList(missing=ExecuteControlOption.values(),
                                              default=ExecuteControlOption.values())
    outputTransmission = TransmissionModeList(missing=ExecuteTransmissionMode.values(),
                                              default=ExecuteTransmissionMode.values())


class ProcessLocations(ExtendedMappingSchema):
    """
    Additional endpoint locations specific to the process.
    """
    processDescriptionURL = URL(description="Process description endpoint using OGC-API interface.",
                                missing=drop, title="processDescriptionURL")
    processEndpointWPS1 = URL(description="Process description endpoint using WPS-1 interface.",
                              missing=drop, title="processEndpointWPS1")
    executeEndpoint = URL(description="Endpoint where the process can be executed from.",
                          missing=drop, title="executeEndpoint")
    # 'links' already included via 'ProcessDescriptionType->DescriptionType'


class ProcessSummary(
    ProcessDescriptionType,
    DescriptionMeta,
    ProcessControl,
    ProcessLocations,
    DescriptionLinks
):
    """
    Summary process definition.
    """
    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class ProcessSummaryList(ExtendedSequenceSchema):
    summary = ProcessSummary()


class ProcessNamesList(ExtendedSequenceSchema):
    process_name = ProcessIdentifier()


class ProcessListing(OneOfKeywordSchema):
    _one_of = [
        ProcessSummaryList(description="Listing of process summary details from existing definitions."),
        ProcessNamesList(description="Listing of process names when not requesting details.",
                         missing=drop),  # in case of empty list, both schema are valid, drop this one to resolve
    ]


class ProcessCollection(ExtendedMappingSchema):
    processes = ProcessListing()


class ProcessPagingQuery(ExtendedMappingSchema):
    sort = ProcessSortEnum(missing=drop)
    # if page is omitted but limit provided, use reasonable zero by default
    page = ExtendedSchemaNode(Integer(allow_string=True), missing=0, default=0, validator=Range(min=0))
    limit = ExtendedSchemaNode(Integer(allow_string=True), missing=None, default=None, validator=Range(min=1))


class ProcessVisibility(ExtendedMappingSchema):
    visibility = VisibilityValue(missing=drop)


class Process(
    # following are like 'ProcessSummary',
    # except without 'ProcessControl' and 'DescriptionLinks' that are outside of nested 'process'
    ProcessDescriptionType, DescriptionMeta,
    # following are additional fields only in description, just like for OGC-API ProcessDescription
    ProcessContext, ProcessVisibility, ProcessLocations
):
    """
    Old nested process schema for process description.
    """
    # note: deprecated in favor of OGC-API schema
    inputs = DescribeInputTypeList(description="Inputs definition of the process.")
    outputs = DescribeOutputTypeList(description="Outputs definition of the process.")

    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class ProcessDescriptionOLD(ProcessControl, DescriptionLinks):
    """
    Old schema for process description.
    """
    deprecated = True
    process = Process()

    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST_OLD_SCHEMA
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER_OLD_SCHEMA


class ProcessDescriptionOGC(ProcessSummary, ProcessContext, ProcessVisibility, ProcessLocations, DescriptionLinks):
    """
    OGC-API schema for process description.
    """
    # technically, empty inputs are allowed for processes that should generate constant/randomized outputs
    # example:
    #   https://pavics.ouranos.ca/twitcher/ows/proxy/catalog
    #   ?service=WPS&request=DescribeProcess&version=1.0.0&identifier=pavicstestdocs
    inputs = DescribeInputTypeMap(description="Inputs definition of the process.", missing=drop, default={})
    outputs = DescribeOutputTypeMap(description="Outputs definition of the process.")

    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class ProcessDescription(OneOfKeywordSchema):
    """
    Supported schema representations of a process description (based on specified query parameters).
    """
    _one_of = [
        ProcessDescriptionOGC,
        ProcessDescriptionOLD,
    ]


class ProcessDeployment(ProcessSummary, ProcessContext, ProcessDeployMeta):
    # explicit "abstract" handling for bw-compat, new versions should use "description"
    # only allowed in deploy to support older servers that report abstract (or parsed from WPS-1/2)
    # recent OGC-API v1+ will usually provide directly "description" as per the specification
    abstract = ExtendedSchemaNode(String(), missing=drop, deprecated=True,
                                  description="Detailed explanation of the process being deployed. "
                                              "[Deprecated] Consider using 'description' instead.")
    # allowed undefined I/O during deploy because of reference from owsContext or executionUnit
    inputs = DeployInputTypeAny(
        missing=drop, title="DeploymentInputs",
        description="Additional definitions for process inputs to extend generated details by the referred package. "
                    "These are optional as they can mostly be inferred from the 'executionUnit', but allow specific "
                    f"overrides (see '{DOC_URL}/package.html#correspondence-between-cwl-and-wps-fields')")
    outputs = DeployOutputTypeAny(
        missing=drop, title="DeploymentOutputs",
        description="Additional definitions for process outputs to extend generated details by the referred package. "
                    "These are optional as they can mostly be inferred from the 'executionUnit', but allow specific "
                    f"overrides (see '{DOC_URL}/package.html#correspondence-between-cwl-and-wps-fields')")
    visibility = VisibilityValue(missing=drop)

    _sort_first = PROCESS_DESCRIPTION_FIELD_FIRST
    _sort_after = PROCESS_DESCRIPTION_FIELD_AFTER


class Duration(ExtendedSchemaNode):
    # note: using String instead of Time because timedelta object cannot be directly handled (missing parts at parsing)
    schema_type = String
    description = "Human-readable representation of the duration."
    example = "hh:mm:ss"


# FIXME: use ISO-8601 duration (?) - P[n]Y[n]M[n]DT[n]H[n]M[n]S
#       https://pypi.org/project/isodate/
#       https://en.wikipedia.org/wiki/ISO_8601#Durations
#   See:
#       'duration.to_iso8601' already employed for quotes, should apply for jobs as well
class DurationISO(ExtendedSchemaNode):
    """
    Duration represented using ISO-8601 format.

    .. seealso::
        - https://json-schema.org/draft/2019-09/json-schema-validation.html#rfc.section.7.3.1
        - :rfc:`3339#appendix-A`
    """
    schema_ref = "https://json-schema.org/draft/2019-09/json-schema-validation.html#rfc.section.7.3.1"
    schema_type = String
    description = "ISO-8601 representation of the duration."
    example = "P[n]Y[n]M[n]DT[n]H[n]M[n]S"
    format = "duration"

    def deserialize(self, cstruct):
        # type: (Union[datetime.timedelta, str]) -> str
        if isinstance(cstruct, datetime.timedelta) or isinstance(cstruct, str) and not cstruct.startswith("P"):
            return duration.to_iso8601(cstruct)
        return cstruct


class JobStatusInfo(ExtendedMappingSchema):
    jobID = UUID(example="a9d14bf4-84e0-449a-bac8-16e598efe807", description="ID of the job.")
    processID = ProcessIdentifier(missing=None, default=None,
                                  description="Process identifier corresponding to the job execution.")
    providerID = ProcessIdentifier(missing=None, default=None,
                                   description="Provider identifier corresponding to the job execution.")
    type = JobTypeEnum(description="Type of the element associated to the creation of this job.")
    status = JobStatusEnum(description="Last updated status.")
    message = ExtendedSchemaNode(String(), missing=drop, description="Information about the last status update.")
    created = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process execution job was created.")
    started = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp when the process started execution if applicable.")
    finished = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                  description="Timestamp when the process completed execution if applicable.")
    updated = ExtendedSchemaNode(DateTime(), missing=drop, default=None,
                                 description="Timestamp of the last update of the job status. This can correspond to "
                                             "any of the other timestamps according to current execution status or "
                                             "even slightly after job finished execution according to the duration "
                                             "needed to deallocate job resources and store results.")
    duration = Duration(missing=drop, description="Duration since the start of the process execution.")
    runningDuration = DurationISO(missing=drop,
                                  description="Duration in ISO-8601 format since the start of the process execution.")
    runningSeconds = NumberType(missing=drop,
                                description="Duration in seconds since the start of the process execution.")
    expirationDate = ExtendedSchemaNode(DateTime(), missing=drop,
                                        description="Timestamp when the job will be canceled if not yet completed.")
    estimatedCompletion = ExtendedSchemaNode(DateTime(), missing=drop)
    nextPoll = ExtendedSchemaNode(DateTime(), missing=drop,
                                  description="Timestamp when the job will prompted for updated status details.")
    percentCompleted = NumberType(example=0, validator=Range(min=0, max=100),
                                  description="Completion percentage of the job as indicated by the process.")
    progress = ExtendedSchemaNode(Integer(), example=100, validator=Range(0, 100),
                                  description="Completion progress of the job (alias to 'percentCompleted').")
    links = LinkList(missing=drop)


class JobEntrySchema(OneOfKeywordSchema):
    # note:
    #   Since JobID is a simple string (not a dict), no additional mapping field can be added here.
    #   They will be discarded by `OneOfKeywordSchema.deserialize()`.
    _one_of = [
        JobStatusInfo,
        UUID(description="Job ID."),
    ]


class JobCollection(ExtendedSequenceSchema):
    item = JobEntrySchema()


class CreatedJobStatusSchema(DescriptionSchema):
    jobID = UUID(description="Unique identifier of the created job for execution.")
    processID = ProcessIdentifier(description="Identifier of the process that will be executed.")
    providerID = AnyIdentifier(description="Remote provider identifier if applicable.", missing=drop)
    status = ExtendedSchemaNode(String(), example=Status.ACCEPTED)
    location = ExtendedSchemaNode(String(), example="http://{host}/weaver/processes/{my-process-id}/jobs/{my-job-id}")


class CreatedQuotedJobStatusSchema(CreatedJobStatusSchema):
    bill = UUID(description="ID of the created bill.")


class GetPagingJobsSchema(ExtendedMappingSchema):
    jobs = JobCollection()
    limit = ExtendedSchemaNode(Integer(), missing=10, default=10, validator=Range(min=1, max=10000))
    page = ExtendedSchemaNode(Integer(), validator=Range(min=0))


class JobCategoryFilters(PermissiveMappingSchema):
    category = ExtendedSchemaNode(String(), title="CategoryFilter", variable="{category}", default=None, missing=None,
                                  description="Value of the corresponding parameter forming that category group.")


class GroupedJobsCategorySchema(ExtendedMappingSchema):
    category = JobCategoryFilters(description="Grouping values that compose the corresponding job list category.")
    jobs = JobCollection(description="List of jobs that matched the corresponding grouping values.")
    count = ExtendedSchemaNode(Integer(), description="Number of matching jobs for the corresponding group category.")


class GroupedCategoryJobsSchema(ExtendedSequenceSchema):
    job_group_category_item = GroupedJobsCategorySchema()


class GetGroupedJobsSchema(ExtendedMappingSchema):
    groups = GroupedCategoryJobsSchema()


class GetQueriedJobsSchema(OneOfKeywordSchema):
    _one_of = [
        GetPagingJobsSchema(description="Matched jobs according to filter queries."),
        GetGroupedJobsSchema(description="Matched jobs grouped by specified categories."),
    ]
    total = ExtendedSchemaNode(Integer(),
                               description="Total number of matched jobs regardless of grouping or paging result.")
    links = LinkList(missing=drop)


class DismissedJobSchema(ExtendedMappingSchema):
    status = JobStatusEnum()
    jobID = UUID(description="ID of the job.")
    message = ExtendedSchemaNode(String(), example="Job dismissed.")
    percentCompleted = ExtendedSchemaNode(Integer(), example=0)


# same as base Format, but for process/job responses instead of process submission
# (ie: 'Format' is for allowed/supported formats, this is the result format)
class DataEncodingAttributes(FormatSelection):
    pass


class Reference(ExtendedMappingSchema):
    title = "Reference"
    href = ExecuteReferenceURL(description="Endpoint of the reference.")
    format = DataEncodingAttributes(missing=drop)
    body = ExtendedSchemaNode(String(), missing=drop)
    bodyReference = ReferenceURL(missing=drop)


class ArrayReference(ExtendedSequenceSchema):
    item = Reference()


class ArrayReferenceValueType(ExtendedMappingSchema):
    value = ArrayReference()


# Backward compatible data-input that allows values to be nested under 'data' or 'value' fields,
# both for literal values and link references, for inputs submitted as list-items.
# Also allows the explicit 'href' (+ optional format) reference for a link.
#
# Because this data-input structure applies only to list-items (see 'ExecuteInputItem' below), mapping is always needed.
# (i.e.: values cannot be submitted inline in the list, because field 'id' of each input must also be provided)
# For this reason, one of 'value', 'data', 'href' or 'reference' is mandatory.
class ExecuteInputAnyType(OneOfKeywordSchema):
    """
    Permissive variants that we attempt to parse automatically.
    """
    _one_of = [
        # Array of literal data with 'data' key
        ArrayLiteralDataType(),
        # same with 'value' key (OGC specification)
        ArrayLiteralValueType(),
        # Array of HTTP references with various keywords
        ArrayReferenceValueType(),
        # literal data with 'data' key
        AnyLiteralDataType(),
        # same with 'value' key (OGC specification)
        AnyLiteralValueType(),
        # HTTP references with various keywords
        LiteralReference(),
        Reference()
    ]


class ExecuteInputItem(ExecuteInputDataType, ExecuteInputAnyType):
    description = (
        "Default value to be looked for uses key 'value' to conform to older drafts of OGC-API standard. "
        "Even older drafts that allowed other fields 'data' instead of 'value' and 'reference' instead of 'href' "
        "are also looked for to remain back-compatible."
    )


# backward compatible definition:
#
#   inputs: [
#     {"id": "<id>", "value": <data>},
#     {"id": "<id>", "href": <link>}
#     ... (other variants) ...
#   ]
#
class ExecuteInputListValues(ExtendedSequenceSchema):
    input_item = ExecuteInputItem(summary="Received list input value definition during job submission.")


# same as 'ExecuteInputReference', but using 'OGC' schema with 'type' field
# Defined as:
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/link.yaml
# But explicitly in the context of an execution input, rather than any other link (eg: metadata)
class ExecuteInputFileLink(Link):  # for other metadata (title, hreflang, etc.)
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/link.yaml"
    href = ExecuteReferenceURL(  # no just a plain 'URL' like 'Link' has (extended with s3, vault, etc.)
        description="Location of the file reference."
    )
    type = MediaType(
        default=ContentType.TEXT_PLAIN,  # as per OGC, not mandatory (ie: 'default' supported format)
        description="IANA identifier of content-type located at the link."
    )
    rel = LinkRelationshipType(missing=drop)  # optional opposite to normal 'Link'


# same as 'ExecuteInputLink', but using 'OLD' schema with 'format' field
class ExecuteInputReference(Reference):
    summary = "Execute input reference link definition with parameters."


class ExecuteInputFile(AnyOfKeywordSchema):
    _any_of = [
        ExecuteInputFileLink(),   # 'OGC' schema with 'type: <MediaType>'
        ExecuteInputReference(),  # 'OLD' schema with 'format: {mimeType|mediaType: <MediaType>}'
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/inputValueNoObject.yaml
# Any literal value directly provided inline in input mapping.
#
#   {"inputs": {"<id>": <literal-data>}}
#
# Excludes objects to avoid conflict with later object mapping and {"value": <data>} definitions.
# Excludes array literals that will be defined separately with allowed array of any item within this schema.
# FIXME: does not support byte/binary type (string + format:byte) - see also: 'AnyLiteralType'
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/binaryInputValue.yaml
# FIXME: does not support bbox
#   https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/bbox.yaml
class ExecuteInputInlineValue(OneOfKeywordSchema):
    description = "Execute input value provided inline."
    _one_of = [
        ExtendedSchemaNode(Float(), title="ExecuteInputValueFloat"),
        ExtendedSchemaNode(Integer(), title="ExecuteInputValueInteger"),
        ExtendedSchemaNode(Boolean(), title="ExecuteInputValueBoolean"),
        ExtendedSchemaNode(String(), title="ExecuteInputValueString"),
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/inputValue.yaml
#
#   oneOf:
#     - $ref: "inputValueNoObject.yaml"
#     - type: object
class ExecuteInputObjectData(OneOfKeywordSchema):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/inputValue.yaml"
    description = "Data value of any schema "
    _one_of = [
        ExecuteInputInlineValue(),
        PermissiveMappingSchema(description="Data provided as any object schema."),
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/qualifiedInputValue.yaml
class ExecuteInputQualifiedValue(Format):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/qualifiedInputValue.yaml"
    value = ExecuteInputObjectData()    # can be anything, including literal value, array of them, nested object


# https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/inlineOrRefData.yaml
#
#   oneOf:
#     - $ref: "inputValueNoObject.yaml"     # in OGC-API spec, includes a generic array
#     - $ref: "qualifiedInputValue.yaml"
#     - $ref: "link.yaml"
#
class ExecuteInputInlineOrRefData(OneOfKeywordSchema):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/inlineOrRefData.yaml"
    _one_of = [
        ExecuteInputInlineValue(),     # <inline-literal>
        ExecuteInputQualifiedValue(),  # {"value": <anything>}
        ExecuteInputFile(),  # 'href' with either 'type' (OGC) or 'format' (OLD)
        # FIXME: other types here, 'bbox+crs', 'collection', 'nested process', etc.
    ]


class ExecuteInputArrayValues(ExtendedSequenceSchema):
    item_value = ExecuteInputInlineOrRefData()


# combine 'inlineOrRefData' and its 'array[inlineOrRefData]' variants to simplify 'ExecuteInputAny' definition
class ExecuteInputData(OneOfKeywordSchema):
    description = "Execute data definition of the input."
    _one_of = [
        ExecuteInputInlineOrRefData,
        ExecuteInputArrayValues,
    ]


# https://github.com/opengeospatial/ogcapi-processes/blob/master/core/openapi/schemas/execute.yaml
#
#   inputs:
#     additionalProperties:           # this is the below 'variable=<input-id>'
#       oneOf:
# 	    - $ref: "inlineOrRefData.yaml"
# 	    - type: array
# 	      items:
# 	        $ref: "inlineOrRefData.yaml"
#
class ExecuteInputMapAdditionalProperties(ExtendedMappingSchema):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/execute.yaml"
    input_id = ExecuteInputData(variable="{input-id}", title="ExecuteInputValue",
                                description="Received mapping input value definition during job submission.")


class ExecuteInputMapValues(AnyOfKeywordSchema):
    _any_of = [
        ExecuteInputMapAdditionalProperties(),  # normal {"<input-id>": {...}}
        EmptyMappingSchema(),                   # allows explicitly provided {}
    ]


class ExecuteInputValues(OneOfKeywordSchema):
    _one_of = [
        # OLD format: {"inputs": [{"id": "<id>", "value": <data>}, ...]}
        ExecuteInputListValues(description="Process job execution inputs defined as item listing."),
        # OGC-API:    {"inputs": {"<id>": <data>, "<id>": {"value": <data>}, ...}}
        ExecuteInputMapValues(description="Process job execution inputs defined as mapping."),
    ]


class ExecuteInputOutputs(ExtendedMappingSchema):
    # Permit unspecified (optional) inputs for processes that could technically allow no-inputs definition (CWL).
    # This is very unusual in real world scenarios, but has some possible cases: constant endpoint fetcher, RNG output.
    #
    # NOTE:
    #   It is **VERY** important to use 'default={}' and not 'missing=drop' contrary to other optional fields.
    #   Using 'drop' causes and invalid input definition to be ignored/removed and not be validated for expected schema.
    #   We want to ensure format is validated if present to rapidly report the issue and not move on to full execution.
    #   If 'inputs' are indeed omitted, the default with match against and empty 'ExecuteInputMapValues' schema.
    #   If 'inputs' are explicitly provided as '{}' or '[]', it will also behave the right way for no-inputs process.
    #
    # See tests validating both cases (incorrect schema vs optionals inputs):
    #   - 'tests.wps_restapi.test_processes.WpsRestApiProcessesTest.test_execute_process_missing_required_params'
    #   - 'tests.wps_restapi.test_providers.WpsRestApiProcessesTest.test_execute_process_no_error_not_required_params'
    #   - 'tests.wps_restapi.test_providers.WpsRestApiProcessesTest.test_get_provider_process_no_inputs'
    #   - 'tests.wps_restapi.test_colander_extras.test_oneof_variable_dict_or_list'
    #
    # OGC 'execute.yaml' also does not enforce any required item.
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/execute.yaml"
    inputs = ExecuteInputValues(default={}, description="Values submitted for execution.")
    outputs = ExecuteOutputSpec(
        description=(
            "Defines which outputs to be obtained from the execution (filtered or all), "
            "as well as the reporting method for each output according to 'transmissionMode', "
            "the 'response' type, and the execution 'mode' provided "
            "(see for more details: https://pavics-weaver.readthedocs.io/en/latest/processes.html#execution-body)."
        ),
        default={}
    )


class Execute(ExecuteInputOutputs):
    mode = JobExecuteModeEnum(
        missing=drop,
        default=ExecuteMode.AUTO,
        deprecated=True,
        description=(
            "Desired execution mode specified directly. This is intended for backward compatibility support. "
            "To obtain more control over execution mode selection, employ the official Prefer header instead "
            "(see for more details: https://pavics-weaver.readthedocs.io/en/latest/processes.html#execution-mode)."
        ),
        validator=OneOf(ExecuteMode.values())
    )
    response = JobResponseOptionsEnum(
        missing=drop,
        default=ExecuteResponse.DOCUMENT,
        description=(
            "Indicates the desired representation format of the response. "
            "(see for more details: https://pavics-weaver.readthedocs.io/en/latest/processes.html#execution-body)."
        ),
        validator=OneOf(ExecuteResponse.values())
    )
    notification_email = ExtendedSchemaNode(
        String(),
        missing=drop,
        validator=Email(),
        description="Optionally send a notification email when the job is done."
    )


class QuoteStatusSchema(ExtendedSchemaNode):
    schema_type = String
    validator = OneOf(QuoteStatus.values())


class PartialQuoteSchema(ExtendedMappingSchema):
    id = UUID(description="Quote ID.")
    status = QuoteStatusSchema()
    processID = ProcessIdentifier(description="Process identifier corresponding to the quote definition.")


class Price(ExtendedSchemaNode):
    schema_type = Money
    # not official, but common (https://github.com/OAI/OpenAPI-Specification/issues/845#issuecomment-378139730)
    format = "decimal"


class QuoteProcessParameters(PermissiveMappingSchema, ExecuteInputOutputs):
    description = (
        "Parameters passed for traditional process execution (inputs, outputs) "
        "with added metadata for quote evaluation."
    )


class UserIdSchema(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), missing=drop),
        ExtendedSchemaNode(Integer(), default=None),
    ]


class StepQuotation(PartialQuoteSchema):
    detail = ExtendedSchemaNode(String(), description="Detail about quote processing.", missing=None)
    price = Price(description="Estimated price for process execution.")
    currency = ExtendedSchemaNode(String(), description="Currency code in ISO-4217 format.", missing=None)
    expire = ExtendedSchemaNode(DateTime(), description="Expiration date and time of the quote in ISO-8601 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the quote in ISO-8601 format.")
    userID = UserIdSchema(description="User ID that requested the quote.", missing=required, default=None)
    estimatedTime = Duration(missing=drop,
                             description="Estimated duration of process execution in human-readable format.")
    estimatedSeconds = ExtendedSchemaNode(Integer(), missing=drop,
                                          description="Estimated duration of process execution in seconds.")
    estimatedDuration = DurationISO(missing=drop,
                                    description="Estimated duration of process execution in ISO-8601 format.")
    processParameters = QuoteProcessParameters(title="QuoteProcessParameters")


class StepQuotationList(ExtendedSequenceSchema):
    description = "Detailed child processes and prices part of the complete quote."
    step = StepQuotation(description="Quote of a workflow step process.")


class Quotation(StepQuotation):
    steps = StepQuotationList(missing=drop)


class QuoteStepReferenceList(ExtendedSequenceSchema):
    description = "Summary of child process quote references part of the complete quote."
    ref = ReferenceURL()


class QuoteSummary(PartialQuoteSchema):
    steps = QuoteStepReferenceList()
    total = Price(description="Total of the quote including step processes if applicable.")


class QuoteSchema(Quotation):
    total = Price(description="Total of the quote including step processes if applicable.")


class QuotationList(ExtendedSequenceSchema):
    quote = UUID(description="Quote ID.")


class QuotationListSchema(ExtendedMappingSchema):
    quotations = QuotationList()


class BillSchema(ExtendedMappingSchema):
    id = UUID(description="Bill ID.")
    quoteID = UUID(description="Original quote ID that produced this bill.", missing=drop)
    title = ExtendedSchemaNode(String(), description="Name of the bill.")
    description = ExtendedSchemaNode(String(), missing=drop)
    price = Price(description="Price associated to the bill.")
    currency = ExtendedSchemaNode(String(), description="Currency code in ISO-4217 format.")
    created = ExtendedSchemaNode(DateTime(), description="Creation date and time of the bill in ISO-8601 format.")
    userID = ExtendedSchemaNode(Integer(), description="User id that requested the quote.")


class BillList(ExtendedSequenceSchema):
    bill = UUID(description="Bill ID.")


class BillListSchema(ExtendedMappingSchema):
    bills = BillList()


class SupportedValues(ExtendedMappingSchema):
    pass


class DefaultValues(ExtendedMappingSchema):
    pass


class CWLClass(ExtendedSchemaNode):
    # in this case it is ok to use 'name' because target fields receiving it will
    # never be able to be named 'class' because of Python reserved keyword
    name = "class"
    title = "Class"
    schema_type = String
    example = "CommandLineTool"
    validator = OneOf(["CommandLineTool", "ExpressionTool", "Workflow"])
    description = (
        "CWL class specification. This is used to differentiate between single Application Package (AP)"
        "definitions and Workflow that chains multiple packages."
    )


class RequirementClass(ExtendedSchemaNode):
    # in this case it is ok to use 'name' because target fields receiving it will
    # never be able to be named 'class' because of Python reserved keyword
    name = "class"
    title = "RequirementClass"
    schema_type = String
    description = "CWL requirement class specification."


class DockerRequirementSpecification(PermissiveMappingSchema):
    dockerPull = ExtendedSchemaNode(
        String(),
        example="docker-registry.host.com/namespace/image:1.2.3",
        title="Docker pull reference",
        description="Reference package that will be retrieved and executed by CWL."
    )


class DockerRequirementMap(ExtendedMappingSchema):
    DockerRequirement = DockerRequirementSpecification(
        name=CWL_REQUIREMENT_APP_DOCKER,
        title=CWL_REQUIREMENT_APP_DOCKER
    )


class DockerRequirementClass(DockerRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_DOCKER, validator=OneOf([CWL_REQUIREMENT_APP_DOCKER]))


class DockerGpuRequirementSpecification(DockerRequirementSpecification):
    description = (
        "Docker requirement with GPU-enabled support (https://github.com/NVIDIA/nvidia-docker). "
        "The instance must have the NVIDIA toolkit installed to use this feature."
    )


class DockerGpuRequirementMap(ExtendedMappingSchema):
    req = DockerGpuRequirementSpecification(name=CWL_REQUIREMENT_APP_DOCKER_GPU)


class DockerGpuRequirementClass(DockerGpuRequirementSpecification):
    title = CWL_REQUIREMENT_APP_DOCKER_GPU
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_DOCKER_GPU, validator=OneOf([CWL_REQUIREMENT_APP_DOCKER_GPU]))


class DirectoryListing(PermissiveMappingSchema):
    entry = ExtendedSchemaNode(String(), missing=drop)


class InitialWorkDirListing(ExtendedSequenceSchema):
    listing = DirectoryListing()


class InitialWorkDirRequirementSpecification(PermissiveMappingSchema):
    listing = InitialWorkDirListing()


class InitialWorkDirRequirementMap(ExtendedMappingSchema):
    req = InitialWorkDirRequirementSpecification(name=CWL_REQUIREMENT_INIT_WORKDIR)


class InitialWorkDirRequirementClass(InitialWorkDirRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_INIT_WORKDIR,
                              validator=OneOf([CWL_REQUIREMENT_INIT_WORKDIR]))


class BuiltinRequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_BUILTIN
    description = (
        "Hint indicating that the Application Package corresponds to a builtin process of "
        "this instance. (note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Builtin process identifier.")


class BuiltinRequirementMap(ExtendedMappingSchema):
    req = BuiltinRequirementSpecification(name=CWL_REQUIREMENT_APP_BUILTIN)


class BuiltinRequirementClass(BuiltinRequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_BUILTIN, validator=OneOf([CWL_REQUIREMENT_APP_BUILTIN]))


class ESGF_CWT_RequirementSpecification(PermissiveMappingSchema):  # noqa: N802
    title = CWL_REQUIREMENT_APP_ESGF_CWT
    description = (
        "Hint indicating that the Application Package corresponds to an ESGF-CWT provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote ESGF-CWT provider.")
    provider = URL(description="ESGF-CWT provider endpoint.")


class ESGF_CWT_RequirementMap(ExtendedMappingSchema):  # noqa: N802
    req = ESGF_CWT_RequirementSpecification(name=CWL_REQUIREMENT_APP_ESGF_CWT)


class ESGF_CWT_RequirementClass(ESGF_CWT_RequirementSpecification):  # noqa: N802
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_ESGF_CWT, validator=OneOf([CWL_REQUIREMENT_APP_ESGF_CWT]))


class WPS1RequirementSpecification(PermissiveMappingSchema):
    title = CWL_REQUIREMENT_APP_WPS1
    description = (
        "Hint indicating that the Application Package corresponds to a WPS-1 provider process"
        "that should be remotely executed and monitored by this instance. "
        "(note: can only be an 'hint' as it is unofficial CWL specification)."
    )
    process = AnyIdentifier(description="Process identifier of the remote WPS provider.")
    provider = URL(description="WPS provider endpoint.")


class WPS1RequirementMap(ExtendedMappingSchema):
    req = WPS1RequirementSpecification(name=CWL_REQUIREMENT_APP_WPS1)


class WPS1RequirementClass(WPS1RequirementSpecification):
    _class = RequirementClass(example=CWL_REQUIREMENT_APP_WPS1, validator=OneOf([CWL_REQUIREMENT_APP_WPS1]))


class UnknownRequirementClass(PermissiveMappingSchema):
    _class = RequirementClass(example="UnknownRequirement")


class CWLRequirementsMap(AnyOfKeywordSchema):
    _any_of = [
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        PermissiveMappingSchema(missing=drop),
    ]


class CWLRequirementsItem(OneOfKeywordSchema):
    _one_of = [
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
        UnknownRequirementClass(missing=drop),  # allows anything, must be last
    ]


class CWLRequirementsList(ExtendedSequenceSchema):
    requirement = CWLRequirementsItem()


class CWLRequirements(OneOfKeywordSchema):
    _one_of = [
        CWLRequirementsMap(),
        CWLRequirementsList(),
    ]


class CWLHintsMap(AnyOfKeywordSchema, PermissiveMappingSchema):
    _any_of = [
        BuiltinRequirementMap(missing=drop),
        DockerRequirementMap(missing=drop),
        DockerGpuRequirementMap(missing=drop),
        InitialWorkDirRequirementMap(missing=drop),
        ESGF_CWT_RequirementMap(missing=drop),
        WPS1RequirementMap(missing=drop),
    ]


class CWLHintsItem(OneOfKeywordSchema, PermissiveMappingSchema):
    # validators of individual requirements define which one applies
    # in case of ambiguity, 'discriminator' distinguish between them using their 'example' values in 'class' field
    discriminator = "class"
    _one_of = [
        BuiltinRequirementClass(missing=drop),
        DockerRequirementClass(missing=drop),
        DockerGpuRequirementClass(missing=drop),
        InitialWorkDirRequirementClass(missing=drop),
        ESGF_CWT_RequirementClass(missing=drop),
        WPS1RequirementClass(missing=drop),
        UnknownRequirementClass(missing=drop),  # allows anything, must be last
    ]


class CWLHintsList(ExtendedSequenceSchema):
    hint = CWLHintsItem()


class CWLHints(OneOfKeywordSchema):
    _one_of = [
        CWLHintsMap(),
        CWLHintsList(),
    ]


class CWLArguments(ExtendedSequenceSchema):
    argument = ExtendedSchemaNode(String())


class CWLTypeString(ExtendedSchemaNode):
    schema_type = String
    description = "Field type definition."
    example = "float"
    validator = OneOf(PACKAGE_TYPE_POSSIBLE_VALUES)


class CWLTypeSymbolValues(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(Float()),
        ExtendedSchemaNode(Integer()),
        ExtendedSchemaNode(String()),
    ]


class CWLTypeSymbols(ExtendedSequenceSchema):
    symbol = CWLTypeSymbolValues()


class CWLTypeArray(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), example=PACKAGE_ARRAY_BASE, validator=OneOf([PACKAGE_ARRAY_BASE]))
    items = CWLTypeString(title="CWLTypeArrayItems", validator=OneOf(PACKAGE_ARRAY_ITEMS))


class CWLTypeEnum(ExtendedMappingSchema):
    type = ExtendedSchemaNode(String(), example=PACKAGE_ENUM_BASE, validator=OneOf(PACKAGE_CUSTOM_TYPES))
    symbols = CWLTypeSymbols(summary="Allowed values composing the enum.")


class CWLTypeBase(OneOfKeywordSchema):
    _one_of = [
        CWLTypeString(summary="CWL type as literal value."),
        CWLTypeArray(summary="CWL type as list of items."),
        CWLTypeEnum(summary="CWL type as enum of values."),
    ]


class CWLTypeList(ExtendedSequenceSchema):
    type = CWLTypeBase()


class CWLType(OneOfKeywordSchema):
    title = "CWL Type"
    _one_of = [
        CWLTypeBase(summary="CWL type definition."),
        CWLTypeList(summary="Combination of allowed CWL types."),
    ]


class AnyLiteralList(ExtendedSequenceSchema):
    default = AnyLiteralType()


class CWLDefault(OneOfKeywordSchema):
    _one_of = [
        AnyLiteralType(),
        AnyLiteralList(),
    ]


class CWLInputObject(PermissiveMappingSchema):
    type = CWLType()
    default = CWLDefault(missing=drop, description="Default value of input if not provided for task execution.")
    inputBinding = PermissiveMappingSchema(missing=drop, title="Input Binding",
                                           description="Defines how to specify the input for the command.")


class CWLTypeStringList(ExtendedSequenceSchema):
    description = "List of allowed direct CWL type specifications as strings."
    type = CWLType()


class CWLInputType(OneOfKeywordSchema):
    description = "CWL type definition of the input."
    _one_of = [
        CWLTypeString(summary="Direct CWL type string specification."),
        CWLTypeStringList(summary="List of allowed CWL type strings."),
        CWLInputObject(summary="CWL type definition with parameters."),
    ]


class CWLInputMap(PermissiveMappingSchema):
    input_id = CWLInputType(variable="{input-id}", title="CWLInputDefinition",
                            description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input") +
                            " (Note: '{input-id}' is a variable corresponding for each identifier)")


class CWLInputItem(CWLInputObject):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="CWL", second="WPS", what="input"))


class CWLInputList(ExtendedSequenceSchema):
    input = CWLInputItem(title="Input", description="Input specification. " + CWL_DOC_MESSAGE)


class CWLInputsDefinition(OneOfKeywordSchema):
    _one_of = [
        CWLInputList(description="Package inputs defined as items."),
        CWLInputMap(description="Package inputs defined as mapping."),
    ]


class OutputBinding(PermissiveMappingSchema):
    glob = ExtendedSchemaNode(String(), missing=drop,
                              description="Glob pattern the will find the output on disk or mounted docker volume.")


class CWLOutputObject(PermissiveMappingSchema):
    type = CWLType()
    # 'outputBinding' should usually be there most of the time (if not always) to retrieve file,
    # but can technically be omitted in some very specific use-cases such as output literal or output is std logs
    outputBinding = OutputBinding(
        missing=drop,
        description="Defines how to retrieve the output result from the command."
    )


class CWLOutputType(OneOfKeywordSchema):
    _one_of = [
        CWLTypeString(summary="Direct CWL type string specification."),
        CWLTypeStringList(summary="List of allowed CWL type strings."),
        CWLOutputObject(summary="CWL type definition with parameters."),
    ]


class CWLOutputMap(ExtendedMappingSchema):
    output_id = CWLOutputType(variable="{output-id}", title="CWLOutputDefinition",
                              description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output") +
                              " (Note: '{output-id}' is a variable corresponding for each identifier)")


class CWLOutputItem(CWLOutputObject):
    id = AnyIdentifier(description=IO_INFO_IDS.format(first="CWL", second="WPS", what="output"))


class CWLOutputList(ExtendedSequenceSchema):
    input = CWLOutputItem(description="Output specification. " + CWL_DOC_MESSAGE)


class CWLOutputsDefinition(OneOfKeywordSchema):
    _one_of = [
        CWLOutputList(description="Package outputs defined as items."),
        CWLOutputMap(description="Package outputs defined as mapping."),
    ]


class CWLCommandParts(ExtendedSequenceSchema):
    cmd = ExtendedSchemaNode(String())


class CWLCommand(OneOfKeywordSchema):
    _one_of = [
        ExtendedSchemaNode(String(), title="String command."),
        CWLCommandParts(title="Command Parts")
    ]


class CWLVersion(Version):
    description = "CWL version of the described application package."
    example = CWL_VERSION
    validator = SemanticVersion(v_prefix=True, rc_suffix=False)


class CWL(PermissiveMappingSchema):
    cwlVersion = CWLVersion()
    _class = CWLClass()
    requirements = CWLRequirements(description="Explicit requirement to execute the application package.", missing=drop)
    hints = CWLHints(description="Non-failing additional hints that can help resolve extra requirements.", missing=drop)
    baseCommand = CWLCommand(description="Command called in the docker image or on shell according to requirements "
                                         "and hints specifications. Can be omitted if already defined in the "
                                         "docker image.", missing=drop)
    arguments = CWLArguments(description="Base arguments passed to the command.", missing=drop)
    inputs = CWLInputsDefinition(description="All inputs available to the Application Package.")
    outputs = CWLOutputsDefinition(description="All outputs produced by the Application Package.")


class Unit(ExtendedMappingSchema):
    unit = CWL(description="Execution unit definition as CWL package specification. " + CWL_DOC_MESSAGE)


class UndeploymentResult(ExtendedMappingSchema):
    id = AnyIdentifier()


class DeploymentResult(ExtendedMappingSchema):
    processSummary = ProcessSummary()


class ProviderSummaryList(ExtendedSequenceSchema):
    provider_service = ProviderSummarySchema()


class ProviderNamesList(ExtendedSequenceSchema):
    provider_name = ProviderNameSchema()


class ProviderListing(OneOfKeywordSchema):
    _one_of = [
        ProviderSummaryList(description="Listing of provider summary details retrieved from remote service."),
        ProviderNamesList(description="Listing of provider names, possibly unvalidated from remote service.",
                          missing=drop),  # in case of empty list, both schema are valid, drop this one to resolve
    ]


class ProvidersBodySchema(ExtendedMappingSchema):
    checked = ExtendedSchemaNode(
        Boolean(),
        description="Indicates if the listed providers have been validated and are accessible from registered URL. "
                    "In such case, provider metadata was partially retrieved from remote services and is accessible. "
                    "Otherwise, only local metadata is provided and service availability is not guaranteed."
    )
    providers = ProviderListing(description="Providers listing according to specified query parameters.")


class ProviderProcessesSchema(ExtendedSequenceSchema):
    provider_process = ProcessSummary()


class JobOutputReference(ExtendedMappingSchema):
    href = ReferenceURL(description="Output file reference.")
    # either with 'type', 'format.mediaType' or 'format.mimeType' according requested 'schema=OGC/OLD'
    # if 'schema=strict' as well, either 'type' or 'format' could be dropped altogether
    type = MediaType(missing=drop, description="IANA Content-Type of the file reference.")
    format = FormatSelection(missing=drop)


class JobOutputValue(OneOfKeywordSchema):
    _one_of = [
        JobOutputReference(tilte="JobOutputReference"),
        AnyLiteralDataType(title="JobOutputLiteral")
    ]


class JobOutput(AllOfKeywordSchema):
    _all_of = [
        OutputIdentifierType(),
        JobOutputValue(),
    ]


class JobOutputMap(ExtendedMappingSchema):
    output_id = JobOutputValue(
        variable="{output-id}", title="JobOutputData",
        description=(
            "Output data as literal value or file reference. "
            "(Note: '{output-id}' is a variable corresponding for each identifier)"
        )
    )


class JobOutputList(ExtendedSequenceSchema):
    title = "JobOutputList"
    output = JobOutput(description="Job output result with specific keyword according to represented format.")


class JobOutputs(OneOfKeywordSchema):
    _one_of = [
        JobOutputMap(),
        JobOutputList(),
    ]


# implement only literal parts from following schemas:
# https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/inlineOrRefData.yaml
# https://raw.githubusercontent.com/opengeospatial/ogcapi-processes/master/core/openapi/schemas/qualifiedInputValue.yaml
#
# Other parts are implemented separately with:
#   - 'ValueFormatted' (qualifiedInputValue)
#   - 'ResultReference' (link)
class ResultLiteral(AnyLiteralValueType):
    # value = <AnyLiteralValueType>
    pass


class ResultLiteralList(ExtendedSequenceSchema):
    result = ResultLiteral()


class ValueFormatted(ExtendedMappingSchema):
    value = ExtendedSchemaNode(
        String(),
        example="<xml><data>test</data></xml>",
        description="Formatted content value of the result."
    )
    format = ResultFormat()


class ValueFormattedList(ExtendedSequenceSchema):
    result = ValueFormatted()


class ResultReference(ExtendedMappingSchema):
    href = ReferenceURL(description="Result file reference.")
    type = MediaType(description="IANA Content-Type of the file reference.")
    format = ResultFormat()


class ResultReferenceList(ExtendedSequenceSchema):
    result = ResultReference()


class ResultData(OneOfKeywordSchema):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/result.yaml"
    _one_of = [
        # must place formatted value first since both value/format fields are simultaneously required
        # other classes require only one of the two, and therefore are more permissive during schema validation
        ValueFormatted(description="Result formatted content value."),
        ValueFormattedList(description="Result formatted content of multiple values."),
        ResultReference(description="Result reference location."),
        ResultReferenceList(description="Result locations for multiple references."),
        ResultLiteral(description="Result literal value."),
        ResultLiteralList(description="Result list of literal values."),
    ]


class Result(ExtendedMappingSchema):
    """
    Result outputs obtained from a successful process job execution.
    """
    example_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/examples/json/Result.json"
    output_id = ResultData(
        variable="{output-id}", title="ResultData",
        description=(
            "Resulting value of the output that conforms to 'OGC API - Processes' standard. "
            "(Note: '{output-id}' is a variable corresponding for each output identifier of the process)"
        )
    )


class JobInputsBody(ExecuteInputOutputs):
    links = LinkList(missing=drop)


class JobOutputsBody(ExtendedMappingSchema):
    outputs = JobOutputs()
    links = LinkList(missing=drop)


class JobExceptionPlain(ExtendedSchemaNode):
    schema_type = String
    description = "Generic exception description corresponding to any error message."


class JobExceptionDetailed(ExtendedMappingSchema):
    description = "Fields correspond exactly to 'owslib.wps.WPSException' represented as dictionary."
    Code = ExtendedSchemaNode(String())
    Locator = ExtendedSchemaNode(String(), default=None)
    Text = ExtendedSchemaNode(String())


class JobException(OneOfKeywordSchema):
    _one_of = [
        JobExceptionDetailed(),
        JobExceptionPlain()
    ]


class JobExceptionsSchema(ExtendedSequenceSchema):
    exceptions = JobException()


class JobLogsSchema(ExtendedSequenceSchema):
    log = ExtendedSchemaNode(String())


class FrontpageParameterSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), example="api")
    enabled = ExtendedSchemaNode(Boolean(), example=True)
    url = URL(description="Referenced parameter endpoint.", example="https://weaver-host", missing=drop)
    doc = ExtendedSchemaNode(String(), example="https://weaver-host/api", missing=drop)


class FrontpageParameters(ExtendedSequenceSchema):
    parameter = FrontpageParameterSchema()


class FrontpageSchema(ExtendedMappingSchema):
    message = ExtendedSchemaNode(String(), default="Weaver Information", example="Weaver Information")
    configuration = ExtendedSchemaNode(String(), default="default", example="default")
    parameters = FrontpageParameters()


class SwaggerJSONSpecSchema(ExtendedMappingSchema):
    pass


class SwaggerUISpecSchema(ExtendedMappingSchema):
    pass


class VersionsSpecSchema(ExtendedMappingSchema):
    name = ExtendedSchemaNode(String(), description="Identification name of the current item.", example="weaver")
    type = ExtendedSchemaNode(String(), description="Identification type of the current item.", example="api")
    version = Version(description="Version of the current item.", example="0.1.0")


class VersionsList(ExtendedSequenceSchema):
    version = VersionsSpecSchema()


class VersionsSchema(ExtendedMappingSchema):
    versions = VersionsList()


class ConformanceList(ExtendedSequenceSchema):
    conformance = URL(description="Conformance specification link.",
                      example="http://www.opengis.net/spec/WPS/2.0/req/service/binding/rest-json/core")


class ConformanceSchema(ExtendedMappingSchema):
    conformsTo = ConformanceList()


#################################################################
# Local Processes schemas
#################################################################


class PackageBody(ExtendedMappingSchema):
    pass


class ExecutionUnit(OneOfKeywordSchema):
    _one_of = [
        Reference(name="Reference", title="Reference", description="Execution Unit reference."),
        Unit(name="Unit", title="Unit", description="Execution Unit definition."),
    ]


class ExecutionUnitList(ExtendedSequenceSchema):
    unit = ExecutionUnit(
        name="ExecutionUnit",
        title="ExecutionUnit",
        description="Definition of the Application Package to execute."
    )


class DeployProcessOffering(ProcessControl):
    process = ProcessDeployment(description="Process definition nested under process field for backward compatibility.")
    processVersion = Version(title="processVersion", missing=drop)


class DeployProcessDescription(ProcessDeployment, ProcessControl):
    schema_ref = f"{OGC_API_SCHEMA_URL}/{OGC_API_SCHEMA_VERSION}/core/openapi/schemas/process.yaml"
    description = "Process description fields directly provided."


class ProcessDescriptionChoiceType(OneOfKeywordSchema):
    _one_of = [
        Reference(),
        DeployProcessOffering(),
        DeployProcessDescription()
    ]


class Deploy(ExtendedMappingSchema):
    processDescription = ProcessDescriptionChoiceType()
    executionUnit = ExecutionUnitList()
    immediateDeployment = ExtendedSchemaNode(Boolean(), missing=drop, default=True)
    deploymentProfileName = URL(missing=drop)
    owsContext = OWSContext(missing=drop)


class DeployHeaders(RequestHeaders):
    x_auth_docker = XAuthDockerHeader()


class PostProcessesEndpoint(ExtendedMappingSchema):
    header = DeployHeaders(description="Headers employed for process deployment.")
    body = Deploy(title="Deploy")


class WpsOutputContextHeader(ExtendedSchemaNode):
    # ok to use 'name' in this case because target 'key' in the mapping must
    # be that specific value but cannot have a field named with this format
    name = "X-WPS-Output-Context"
    description = (
        "Contextual location where to store WPS output results from job execution. ",
        "When provided, value must be a directory or sub-directories slug. ",
        "Resulting contextual location will be relative to server WPS outputs when no context is provided.",
    )
    schema_type = String
    missing = drop
    example = "my-directory/sub-project"
    default = None


class ExecuteHeaders(RequestHeaders):
    description = "Request headers supported for job execution."
    x_wps_output_context = WpsOutputContextHeader()


class PostProcessJobsEndpoint(ProcessPath):
    header = ExecuteHeaders()
    body = Execute()


class GetJobsQueries(ExtendedMappingSchema):
    # note:
    #   This schema is also used to generate any missing defaults during filter parameter handling.
    #   Items with default value are added if omitted, except 'default=null' which are removed after handling by alias.
    detail = ExtendedSchemaNode(QueryBoolean(), default=False, example=True, missing=drop,
                                description="Provide job details instead of IDs.")
    groups = ExtendedSchemaNode(String(),
                                description="Comma-separated list of grouping fields with which to list jobs.",
                                default=False, example="process,service", missing=drop)
    page = ExtendedSchemaNode(Integer(allow_string=True), missing=0, default=0, validator=Range(min=0))
    limit = ExtendedSchemaNode(Integer(allow_string=True), missing=10, default=10, validator=Range(min=1, max=10000))
    min_duration = ExtendedSchemaNode(
        Integer(allow_string=True), name="minDuration", missing=drop, default=null, validator=Range(min=0),
        description="Minimal duration (seconds) between started time and current/finished time of jobs to find.")
    max_duration = ExtendedSchemaNode(
        Integer(allow_string=True), name="maxDuration", missing=drop, default=null, validator=Range(min=0),
        description="Maximum duration (seconds) between started time and current/finished time of jobs to find.")
    datetime = DateTimeInterval(missing=drop, default=None)
    status = JobStatusEnum(missing=drop, default=None)
    processID = ProcessIdentifier(missing=drop, default=null, description="Alias to 'process' for OGC-API compliance.")
    process = ProcessIdentifier(missing=drop, default=None, description="Identifier of the process to filter search.")
    service = AnyIdentifier(missing=drop, default=null, description="Alias to 'provider' for backward compatibility.")
    provider = AnyIdentifier(missing=drop, default=None, description="Identifier of service provider to filter search.")
    type = JobTypeEnum(missing=drop, default=null,
                       description="Filter jobs only to matching type (note: 'service' and 'provider' are aliases).")
    sort = JobSortEnum(missing=drop)
    access = JobAccess(missing=drop, default=None)
    notification_email = ExtendedSchemaNode(String(), missing=drop, validator=Email())
    tags = ExtendedSchemaNode(String(), missing=drop, default=None,
                              description="Comma-separated values of tags assigned to jobs")


class GetJobsRequest(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetJobsQueries()


class GetJobsEndpoint(GetJobsRequest):
    pass


class GetProcessJobsEndpoint(GetJobsRequest, ProcessPath):
    pass


class GetProviderJobsEndpoint(GetJobsRequest, ProviderPath, ProcessPath):
    pass


class JobIdentifierList(ExtendedSequenceSchema):
    job_id = UUID(description="ID of a job to dismiss. Identifiers not matching any known job are ignored.")


class DeleteJobsBodySchema(ExtendedMappingSchema):
    jobs = JobIdentifierList()


class DeleteJobsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    body = DeleteJobsBodySchema()


class DeleteProcessJobsEndpoint(DeleteJobsEndpoint, ProcessPath):
    pass


class DeleteProviderJobsEndpoint(DeleteJobsEndpoint, ProviderPath, ProcessPath):
    pass


class GetProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


class DeleteProcessJobEndpoint(ProcessPath):
    header = RequestHeaders()


class BillsEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class BillEndpoint(BillPath):
    header = RequestHeaders()


class ProcessQuotesEndpoint(ProcessPath):
    header = RequestHeaders()


class ProcessQuoteEndpoint(ProcessPath, QuotePath):
    header = RequestHeaders()


class GetQuotesQueries(ExtendedMappingSchema):
    page = ExtendedSchemaNode(Integer(), missing=drop, default=0)
    limit = ExtendedSchemaNode(Integer(), missing=10, default=10, validator=Range(min=1, max=10000))
    process = AnyIdentifier(missing=None)
    sort = QuoteSortEnum(missing=drop)


class QuotesEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()
    querystring = GetQuotesQueries()


class QuoteEndpoint(QuotePath):
    header = RequestHeaders()


class PostProcessQuote(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = NoContent()


class PostQuote(QuotePath):
    header = RequestHeaders()
    body = NoContent()


class QuoteProcessParametersSchema(ExecuteInputOutputs):
    pass


class PostProcessQuoteRequestEndpoint(ProcessPath, QuotePath):
    header = RequestHeaders()
    body = QuoteProcessParametersSchema()


# ################################################################
# Provider Processes schemas
# ################################################################


class ProvidersQuerySchema(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="Return summary details about each provider, or simply their IDs."
    )
    check = ExtendedSchemaNode(
        QueryBoolean(),
        example=True, default=True, missing=drop,
        description="List only reachable providers, dropping unresponsive ones that cannot be checked for listing. "
                    "Otherwise, all registered providers are listed regardless of their availability. When requesting "
                    "details, less metadata will be provided since it will not be fetched from remote services."
    )
    ignore = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="When listing providers with check of reachable remote service definitions, unresponsive response "
                    "or unprocessable contents will be silently ignored and dropped from full listing in the response. "
                    "Disabling this option will raise an error immediately instead of ignoring invalid services."
    )


class GetProviders(ExtendedMappingSchema):
    querystring = ProvidersQuerySchema()
    header = RequestHeaders()


class PostProvider(ExtendedMappingSchema):
    header = RequestHeaders()
    body = CreateProviderRequestBody()


class ProcessDetailQuery(ExtendedMappingSchema):
    detail = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="Return summary details about each process, or simply their IDs."
    )


class ProviderProcessesQuery(ProcessPagingQuery, ProcessDetailQuery):
    pass


class ProviderProcessesEndpoint(ProviderPath):
    header = RequestHeaders()
    querystring = ProviderProcessesQuery()


class GetProviderProcess(ExtendedMappingSchema):
    header = RequestHeaders()


class PostProviderProcessJobRequest(ExtendedMappingSchema):
    """
    Launching a new process request definition.
    """
    header = ExecuteHeaders()
    querystring = LaunchJobQuerystring()
    body = Execute()


# ################################################################
# Responses schemas
# ################################################################

class ErrorDetail(ExtendedMappingSchema):
    code = ExtendedSchemaNode(Integer(), description="HTTP status code.", example=400)
    status = ExtendedSchemaNode(String(), description="HTTP status detail.", example="400 Bad Request")


class OWSErrorCode(ExtendedSchemaNode):
    schema_type = String
    example = "InvalidParameterValue"
    description = "OWS error code."


class OWSExceptionResponse(ExtendedMappingSchema):
    """
    Error content in XML format.
    """
    description = "OWS formatted exception."
    code = OWSErrorCode(example="NoSuchProcess")
    locator = ExtendedSchemaNode(String(), example="identifier",
                                 description="Indication of the element that caused the error.")
    message = ExtendedSchemaNode(String(), example="Invalid process ID.",
                                 description="Specific description of the error.")


class ErrorJsonResponseBodySchema(ExtendedMappingSchema):
    code = OWSErrorCode()
    description = ExtendedSchemaNode(String(), description="Detail about the cause of error.")
    error = ErrorDetail(missing=drop)
    exception = OWSExceptionResponse(missing=drop)


class BadRequestResponseSchema(ExtendedMappingSchema):
    description = "Incorrectly formed request contents."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class UnprocessableEntityResponseSchema(ExtendedMappingSchema):
    description = "Wrong format of given parameters."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProcessAccessResponseSchema(ExtendedMappingSchema):
    description = "Referenced process is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProviderAccessResponseSchema(ExtendedMappingSchema):
    description = "Referenced provider is not accessible."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenProviderLocalResponseSchema(ExtendedMappingSchema):
    description = (
        "Provider operation is not allowed on local-only Weaver instance. "
        f"Applies only when application configuration is not within: {WEAVER_CONFIG_REMOTE_LIST}"
    )
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class InternalServerErrorResponseSchema(ExtendedMappingSchema):
    description = "Unhandled internal server error."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetFrontpageResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = FrontpageSchema()


class OkGetSwaggerJSONResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = SwaggerJSONSpecSchema(description="OpenAPI JSON schema of Weaver API.")


class OkGetSwaggerUIResponse(ExtendedMappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Swagger UI of Weaver API.")


class OkGetRedocUIResponse(ExtendedMappingSchema):
    header = HtmlHeader()
    body = SwaggerUISpecSchema(description="Redoc UI of Weaver API.")


class OkGetVersionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = VersionsSchema()


class OkGetConformanceResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ConformanceSchema()


class OkGetProvidersListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProvidersBodySchema()


class OkGetProviderCapabilitiesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderCapabilitiesSchema()


class NoContentDeleteProviderSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = NoContent()


class NotImplementedDeleteProviderResponse(ExtendedMappingSchema):
    description = "Provider removal not supported using referenced storage."


class OkGetProviderProcessesSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderProcessesSchema()


class GetProcessesQuery(ProcessPagingQuery, ProcessDetailQuery):
    providers = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=False, missing=drop,
        description="List local processes as well as all sub-processes of all registered providers. "
                    "Paging and sorting query parameters are unavailable when providers are requested since lists are "
                    "populated dynamically and cannot ensure consistent process lists per page across providers. "
                    f"Applicable only for Weaver configurations {WEAVER_CONFIG_REMOTE_LIST}, ignored otherwise."
    )
    ignore = ExtendedSchemaNode(
        QueryBoolean(), example=True, default=True, missing=drop,
        description="Only when listing provider processes, any unreachable remote service definitions "
                    "or unprocessable contents will be silently ignored and dropped from full listing in the response. "
                    "Disabling this option will raise an error immediately instead of ignoring invalid providers."
    )


class GetProcessesEndpoint(ExtendedMappingSchema):
    querystring = GetProcessesQuery()


class ProviderProcessesListing(ProcessCollection):
    _sort_first = ["id", "processes"]
    id = ProviderNameSchema()


class ProviderProcessesList(ExtendedSequenceSchema):
    item = ProviderProcessesListing(description="Processes offered by the identified remote provider.")


class ProvidersProcessesCollection(ExtendedMappingSchema):
    providers = ProviderProcessesList(missing=drop)


class ProcessListingMetadata(ExtendedMappingSchema):
    description = "Metadata relative to the listed processes."
    page = ExtendedSchemaNode(Integer(), misisng=drop, default=None, validator=Range(min=0))
    limit = ExtendedSchemaNode(Integer(), missing=drop, default=None, validator=Range(min=1))
    total = ExtendedSchemaNode(Integer(), description="Total number of local processes, or also including all "
                                                      "remote processes across providers if requested.")
    links = LinkList(missing=drop)


class MultiProcessesListing(DescriptionSchema, ProcessCollection, ProvidersProcessesCollection, ProcessListingMetadata):
    _sort_first = ["description", "processes"]
    _sort_after = ["links"]


class OkGetProcessesListResponse(ExtendedMappingSchema):
    description = "Listing of available processes successful."
    header = ResponseHeaders()
    body = MultiProcessesListing()


class OkPostProcessDeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully deployed.")
    processSummary = ProcessSummary(missing=drop, description="Deployed process summary if successful.")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of deploy failure if applicable.")


class OkPostProcessesResponse(ExtendedMappingSchema):
    description = "Process successfully deployed."
    header = ResponseHeaders()
    body = OkPostProcessDeployBodySchema()


class BadRequestGetProcessInfoResponse(ExtendedMappingSchema):
    description = "Missing process identifier."
    body = NoContent()


class OkGetProcessInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessDescription()


class OkGetProcessPackageSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = NoContent()


class OkGetProcessPayloadSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = NoContent()


class ProcessVisibilityResponseBodySchema(ExtendedMappingSchema):
    value = VisibilityValue()


class OkGetProcessVisibilitySchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessVisibilityResponseBodySchema()


class OkPutProcessVisibilitySchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessVisibilityResponseBodySchema()


class ForbiddenVisibilityUpdateResponseSchema(ExtendedMappingSchema):
    description = "Visibility value modification not allowed."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkDeleteProcessUndeployBodySchema(ExtendedMappingSchema):
    deploymentDone = ExtendedSchemaNode(Boolean(), default=False, example=True,
                                        description="Indicates if the process was successfully undeployed.")
    identifier = ExtendedSchemaNode(String(), example="workflow")
    failureReason = ExtendedSchemaNode(String(), missing=drop,
                                       description="Description of undeploy failure if applicable.")


class OkDeleteProcessResponse(ExtendedMappingSchema):
    description = "Process successfully undeployed."
    header = ResponseHeaders()
    body = OkDeleteProcessUndeployBodySchema()


class OkGetProviderProcessDescriptionResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProcessDescription()


class CreatedPostProvider(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = ProviderSummarySchema()


class NotImplementedPostProviderResponse(ExtendedMappingSchema):
    description = "Provider registration not supported using specified definition."


class PreferenceAppliedHeader(ExtendedSchemaNode):
    description = "Applied preferences from submitted 'Prefer' header after validation."
    name = "Preference-Applied"
    schema_type = String
    example = "wait=10s, respond-async"


class LocationHeader(URL):
    name = "Location"


class CreatedJobLocationHeader(ResponseHeaders):
    location = LocationHeader(description="Status monitoring location of the job execution.")
    prefer_applied = PreferenceAppliedHeader(missing=drop)


class CreatedLaunchJobResponse(ExtendedMappingSchema):
    description = "Job successfully submitted to processing queue. Execution should begin when resources are available."
    header = CreatedJobLocationHeader()
    body = CreatedJobStatusSchema()


class CompletedJobLocationHeader(ResponseHeaders):
    location = LocationHeader(description="Status location of the completed job execution.")
    prefer_applied = PreferenceAppliedHeader(missing=drop)


class CompletedJobStatusSchema(DescriptionSchema, JobStatusInfo):
    pass


class CompletedJobResponse(ExtendedMappingSchema):
    description = "Job submitted and completed execution synchronously."
    header = CompletedJobLocationHeader()
    body = CompletedJobStatusSchema()


class FailedSyncJobResponse(CompletedJobResponse):
    description = "Job submitted and failed synchronous execution. See server logs for more details."


class OkDeleteProcessJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetQueriedJobsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = GetQueriedJobsSchema()


class BatchDismissJobsBodySchema(DescriptionSchema):
    jobs = JobIdentifierList(description="Confirmation of jobs that have been dismissed.")


class OkBatchDismissJobsResponseSchema(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BatchDismissJobsBodySchema()


class OkDismissJobResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = DismissedJobSchema()


class OkGetJobStatusResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobStatusInfo()


class InvalidJobResponseSchema(ExtendedMappingSchema):
    description = "Job reference is not a valid UUID."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class NotFoundJobResponseSchema(ExtendedMappingSchema):
    description = "Job reference UUID cannot be found."
    examples = {
        "JobNotFound": {
            "summary": "Example response when specified job reference cannot be found.",
            "value": EXAMPLES["job_not_found.json"]
        }
    }
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class GoneJobResponseSchema(ExtendedMappingSchema):
    description = "Job reference UUID cannot be dismissed again or its result artifacts were removed."
    examples = {
        "JobDismissed": {
            "summary": "Example response when specified job reference was already dismissed.",
            "value": EXAMPLES["job_dismissed_error.json"]
        }
    }
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class OkGetJobInputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobInputsBody()


class OkGetJobOutputsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobOutputsBody()


class RedirectResultResponse(ExtendedMappingSchema):
    header = RedirectHeaders()


class OkGetJobResultsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = Result()


class NoContentJobResultsHeaders(NoContent):
    content_length = ContentLengthHeader(example="0")
    link = LinkHeader(description=(
        "Link to a result requested by reference output transmission. "
        "Link relation indicates the result ID. "
        "Additional parameters indicate expected content-type of the resource. "
        "Literal data requested by reference are returned with contents dumped to plain text file."
    ))


class NoContentJobResultsResponse(ExtendedMappingSchema):
    header = NoContentJobResultsHeaders()
    body = NoContent(default="")


class CreatedQuoteExecuteResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = CreatedQuotedJobStatusSchema()


class CreatedQuoteResponse(ExtendedMappingSchema):
    description = "Quote successfully obtained for process execution definition."
    header = ResponseHeaders()
    body = QuoteSchema()


class AcceptedQuoteResponse(ExtendedMappingSchema):
    summary = "Quote successfully submitted."
    description = (
        "Quote successfully submitted for evaluating process execution definition. "
        "Complete details will be available once evaluation has completed."
    )
    header = ResponseHeaders()
    body = PartialQuoteSchema()


class OkGetQuoteInfoResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuoteSchema()


class OkGetQuoteListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = QuotationListSchema()


class OkGetBillDetailResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillSchema()


class OkGetBillListResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = BillListSchema()


class OkGetJobExceptionsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobExceptionsSchema()


class OkGetJobLogsResponse(ExtendedMappingSchema):
    header = ResponseHeaders()
    body = JobLogsSchema()


class VaultFileID(UUID):
    description = "Vault file identifier."
    example = "78977deb-28af-46f3-876b-cdd272742678"


class VaultAccessToken(UUID):
    description = "Vault file access token."
    example = "30d889cfb7ae3a63229a8de5f91abc1ef5966bb664972f234a4db9d28f8148e0e"  # nosec


class VaultEndpoint(ExtendedMappingSchema):
    header = RequestHeaders()


class VaultUploadBody(ExtendedSchemaNode):
    schema_type = String
    description = "Multipart file contents for upload to the vault."
    examples = {
        ContentType.MULTI_PART_FORM: {
            "summary": "Upload JSON file to vault as multipart content.",
            "value": EXAMPLES["vault_file_upload.txt"],
        }
    }


class VaultUploadEndpoint(ExtendedMappingSchema):
    header = FileUploadHeaders()
    body = VaultUploadBody()


class VaultFileUploadedBodySchema(ExtendedMappingSchema):
    access_token = AccessToken()
    file_id = VaultFileID()
    file_href = VaultReference()


class VaultFileUploadedHeaders(ResponseHeaders):
    location = URL(name="Location", description="File download location.",
                   example="https://localhost:4002" + vault_file_service.path.format(file_id=VaultFileID.example))


class OkVaultFileUploadedResponse(ExtendedMappingSchema):
    description = "File successfully uploaded to vault."
    header = VaultFileUploadedHeaders()
    body = VaultFileUploadedBodySchema()


class BadRequestVaultFileUploadResponse(ExtendedMappingSchema):
    description = "Missing or incorrectly formed file contents."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class UnprocessableEntityVaultFileUploadResponse(ExtendedMappingSchema):
    description = (
        "Invalid filename refused for upload. "
        "Filename should include only alphanumeric, underscore, dash, and dot characters. "
        "Filename should include both the base name and the desired file extension."
    )
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class XAuthVaultFileHeader(ExtendedSchemaNode):
    summary = "Authorization header with token for Vault file access."
    description = (
        "For accessing a single file from the Vault, such as to obtain file metadata, requests can simply provide "
        "the 'token {access-token}' portion in the header without additional parameters. If multiple files require "
        "access such as during an Execute request, all applicable tokens should be provided using a comma separated "
        "list of access tokens, each with their indented input ID and array index if applicable "
        f"(see {DOC_URL}/processes.html#file-vault-inputs for more details)."
    )
    name = "X-Auth-Vault"
    example = "token {access-token}[; id={vault-id}]"
    schema_type = String


class VaultFileRequestHeaders(ExtendedMappingSchema):
    access_token = XAuthVaultFileHeader()


class VaultFileEndpoint(VaultEndpoint):
    header = VaultFileRequestHeaders()
    file_id = VaultFileID()


class OkVaultFileDetailResponse(ExtendedMappingSchema):
    header = FileResponseHeaders()
    body = NoContent(default="")


class OkVaultFileDownloadResponse(OkVaultFileDetailResponse):
    pass


class BadRequestVaultFileAccessResponse(ExtendedMappingSchema):
    description = "Invalid file vault reference."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class ForbiddenVaultFileDownloadResponse(ExtendedMappingSchema):
    description = "Forbidden access to vault file. Invalid authorization from provided token."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


class GoneVaultFileDownloadResponse(ExtendedMappingSchema):
    description = "Vault File resource corresponding to specified ID is not available anymore."
    header = ResponseHeaders()
    body = ErrorJsonResponseBodySchema()


get_api_frontpage_responses = {
    "200": OkGetFrontpageResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_openapi_json_responses = {
    "200": OkGetSwaggerJSONResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_swagger_ui_responses = {
    "200": OkGetSwaggerUIResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_redoc_ui_responses = {
    "200": OkGetRedocUIResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_versions_responses = {
    "200": OkGetVersionsResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_api_conformance_responses = {
    "200": OkGetConformanceResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_processes_responses = {
    "200": OkGetProcessesListResponse(examples={
        "ProcessesListing": {
            "summary": "Listing of identifiers of local processes registered in Weaver.",
            "value": EXAMPLES["local_process_listing.json"],
        },
        "ProcessesDetails": {
            "summary": "Detailed definitions of local processes registered in Weaver.",
            "value": EXAMPLES["local_process_listing.json"],
        },
        "ProvidersProcessesListing": {
            "summary": "List of identifiers combining all local and remote processes known by Weaver.",
            "value": EXAMPLES["providers_processes_listing.json"],
        },
        "ProvidersProcessesDetails": {
            "summary": "Detailed definitions Combining all local and remote processes known by Weaver.",
            "value": EXAMPLES["providers_processes_listing.json"],
        }
    }),
    "400": BadRequestResponseSchema(description="Error in case of invalid listing query parameters."),
    "500": InternalServerErrorResponseSchema(),
}
post_processes_responses = {
    "201": OkPostProcessesResponse(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_responses = {
    "200": OkGetProcessInfoResponse(description="success", examples={
        "ProcessDescriptionSchemaOGC": {
            "summary": "Description of a local process registered in Weaver (OGC Schema) "
                       "with fields on top-level and using inputs/outputs as mapping with keys as IDs.",
            "value": EXAMPLES["local_process_description_ogc_api.json"],
        },
        "ProcessDescriptionSchemaOld": {
            "summary": "Description of a local process registered in Weaver (Old Schema) "
                       "with fields nested under a process section and using inputs/outputs listed with IDs.",
            "value": EXAMPLES["local_process_description.json"],
        }
    }),
    "400": BadRequestGetProcessInfoResponse(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_package_responses = {
    "200": OkGetProcessPackageSchema(description="success", examples={
        "PackageCWL": {
            "summary": "CWL Application Package definition of the local process.",
            "value": EXAMPLES["local_process_package.json"],
        }
    }),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_payload_responses = {
    "200": OkGetProcessPayloadSchema(description="success", examples={
        "Payload": {
            "summary": "Payload employed during process deployment and registration.",
            "value": EXAMPLES["local_process_payload.json"],
        }
    }),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_process_visibility_responses = {
    "200": OkGetProcessVisibilitySchema(description="success"),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
put_process_visibility_responses = {
    "200": OkPutProcessVisibilitySchema(description="success"),
    "403": ForbiddenVisibilityUpdateResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_process_responses = {
    "200": OkDeleteProcessResponse(),
    "403": ForbiddenProcessAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_providers_list_responses = {
    "200": OkGetProvidersListResponse(description="success", examples={
        "ProviderList": {
            "summary": "Listing of registered remote providers.",
            "value": EXAMPLES["provider_listing.json"],
        },
        "ProviderNames": {
            "summary": "Listing of registered providers names without validation.",
            "value": EXAMPLES["provider_names.json"],
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_provider_responses = {
    "200": OkGetProviderCapabilitiesSchema(description="success", examples={
        "ProviderDescription": {
            "summary": "Description of a registered remote WPS provider.",
            "value": EXAMPLES["provider_description.json"],
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_provider_responses = {
    "204": NoContentDeleteProviderSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
    "501": NotImplementedDeleteProviderResponse(),
}
get_provider_processes_responses = {
    "200": OkGetProviderProcessesSchema(description="success"),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_provider_process_responses = {
    "200": OkGetProviderProcessDescriptionResponse(description="success", examples={
        "ProviderProcessWPS": {
            "summary": "Description of a remote WPS provider process converted to OGC-API Processes format.",
            "value": EXAMPLES["provider_process_description.json"]
        }
    }),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_provider_responses = {
    "201": CreatedPostProvider(description="success"),
    "400": ExtendedMappingSchema(description=OWSMissingParameterValue.description),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
    "501": NotImplementedPostProviderResponse(),
}
post_provider_process_job_responses = {
    "200": CompletedJobResponse(description="success"),
    "201": CreatedLaunchJobResponse(description="success"),
    "204": NoContentJobResultsResponse(description="success"),
    "400": FailedSyncJobResponse(),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
post_process_jobs_responses = {
    "200": CompletedJobResponse(description="success"),
    "201": CreatedLaunchJobResponse(description="success"),
    "204": NoContentJobResultsResponse(description="success"),
    "400": FailedSyncJobResponse(),
    "403": ForbiddenProviderAccessResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_all_jobs_responses = {
    "200": OkGetQueriedJobsResponse(description="success", examples={
        "JobListing": {
            "summary": "Job ID listing with default queries.",
            "value": EXAMPLES["jobs_listing.json"]
        }
    }),
    "400": BadRequestResponseSchema(description="Error in case of invalid search query parameters."),
    "422": UnprocessableEntityResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_jobs_responses = {
    "200": OkBatchDismissJobsResponseSchema(description="success"),
    "400": BadRequestResponseSchema(),
    "422": UnprocessableEntityResponseSchema(),
}
get_prov_all_jobs_responses = copy(get_all_jobs_responses)
get_prov_all_jobs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_single_job_status_responses = {
    "200": OkGetJobStatusResponse(description="success", examples={
        "JobStatusSuccess": {
            "summary": "Successful job status response.",
            "value": EXAMPLES["job_status_success.json"]},
        "JobStatusFailure": {
            "summary": "Failed job status response.",
            "value": EXAMPLES["job_status_failed.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_single_job_status_responses = copy(get_single_job_status_responses)
get_prov_single_job_status_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
delete_job_responses = {
    "200": OkDismissJobResponse(description="success"),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
delete_prov_job_responses = copy(delete_job_responses)
delete_prov_job_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_job_inputs_responses = {
    "200": OkGetJobInputsResponse(description="success", examples={
        "JobInputs": {
            "summary": "Submitted job input values at for process execution.",
            "value": EXAMPLES["job_inputs.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_inputs_responses = copy(get_job_inputs_responses)
get_prov_inputs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_job_outputs_responses = {
    "200": OkGetJobOutputsResponse(description="success", examples={
        "JobOutputs": {
            "summary": "Obtained job outputs values following process execution.",
            "value": EXAMPLES["job_outputs.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_outputs_responses = copy(get_job_outputs_responses)
get_prov_outputs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_result_redirect_responses = {
    "308": RedirectResultResponse(description="Redirects '/result' (without 's') to corresponding '/results' path."),
}
get_job_results_responses = {
    "200": OkGetJobResultsResponse(description="success", examples={
        "JobResults": {
            "summary": "Obtained job results.",
            "value": EXAMPLES["job_results.json"],
        }
    }),
    "204": NoContentJobResultsResponse(description="success"),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_results_responses = copy(get_job_results_responses)
get_prov_results_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_exceptions_responses = {
    "200": OkGetJobExceptionsResponse(description="success", examples={
        "JobExceptions": {
            "summary": "Job exceptions that occurred during failing process execution.",
            "value": EXAMPLES["job_exceptions.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_exceptions_responses = copy(get_exceptions_responses)
get_prov_exceptions_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_logs_responses = {
    "200": OkGetJobLogsResponse(description="success", examples={
        "JobLogs": {
            "summary": "Job logs registered and captured throughout process execution.",
            "value": EXAMPLES["job_logs.json"],
        }
    }),
    "400": InvalidJobResponseSchema(),
    "404": NotFoundJobResponseSchema(),
    "410": GoneJobResponseSchema(),
    "500": InternalServerErrorResponseSchema(),
}
get_prov_logs_responses = copy(get_logs_responses)
get_prov_logs_responses.update({
    "403": ForbiddenProviderLocalResponseSchema(),
})
get_quote_list_responses = {
    "200": OkGetQuoteListResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_quote_responses = {
    "200": OkGetQuoteInfoResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
post_quotes_responses = {
    "201": CreatedQuoteResponse(),
    "202": AcceptedQuoteResponse(),
    "500": InternalServerErrorResponseSchema(),
}
post_quote_responses = {
    "201": CreatedQuoteExecuteResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_list_responses = {
    "200": OkGetBillListResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
get_bill_responses = {
    "200": OkGetBillDetailResponse(description="success"),
    "500": InternalServerErrorResponseSchema(),
}
post_vault_responses = {
    "200": OkVaultFileUploadedResponse(description="success", examples={
        "VaultFileUploaded": {
            "summary": "File successfully uploaded to vault.",
            "value": EXAMPLES["vault_file_uploaded.json"],
        }
    }),
    "400": BadRequestVaultFileUploadResponse(),
    "422": UnprocessableEntityVaultFileUploadResponse(),
    "500": InternalServerErrorResponseSchema(),
}
head_vault_file_responses = {
    "200": OkVaultFileDetailResponse(description="success", examples={
        "VaultFileDetails": {
            "summary": "Obtain vault file metadata.",
            "value": EXAMPLES["vault_file_head.json"],
        }
    }),
    "400": BadRequestVaultFileAccessResponse(),
    "403": ForbiddenVaultFileDownloadResponse(),
    "410": GoneVaultFileDownloadResponse(),
    "500": InternalServerErrorResponseSchema(),
}
get_vault_file_responses = {
    "200": OkVaultFileDownloadResponse(description="success"),
    "400": BadRequestVaultFileAccessResponse(),
    "403": ForbiddenVaultFileDownloadResponse(),
    "410": GoneVaultFileDownloadResponse(),
    "500": InternalServerErrorResponseSchema(),
}
wps_responses = {
    "200": OkWPSResponse(examples={
        "GetCapabilities": {
            "summary": "GetCapabilities example response.",
            "value": EXAMPLES["wps_getcapabilities.xml"]
        },
        "DescribeProcess": {
            "summary": "DescribeProcess example response.",
            "value": EXAMPLES["wps_describeprocess.xml"]
        },
        "Execute": {
            "summary": "Execute example response.",
            "value": EXAMPLES["wps_execute_response.xml"]
        }
    }),
    "400": ErrorWPSResponse(examples={
        "MissingParameterError": {
            "summary": "Error report in case of missing request parameter.",
            "value": EXAMPLES["wps_missing_parameter.xml"],
        }
    }),
    "500": ErrorWPSResponse(),
}


#################################################################
# Utility methods
#################################################################


def service_api_route_info(service_api, settings):
    # type: (Service, SettingsType) -> ViewInfo
    """
    Automatically generates the view configuration parameters from the :mod:`cornice` service definition.

    :param service_api: cornice service with name and path definition.
    :param settings: settings to obtain the base path of the application.
    :return: view configuration parameters that can be passed directly to ``config.add_route`` call.
    """
    from weaver.wps_restapi.utils import wps_restapi_base_path  # import here to avoid circular import errors

    api_base = wps_restapi_base_path(settings)
    return {"name": service_api.name, "pattern": f"{api_base}{service_api.path}"}


def datetime_interval_parser(datetime_interval):
    # type: (str) -> DatetimeIntervalType
    """
    This function parses a given datetime or interval into a dictionary that will be easy for database process.
    """
    parsed_datetime = {}

    if datetime_interval.startswith(DATETIME_INTERVAL_OPEN_START_SYMBOL):
        datetime_interval = datetime_interval.replace(DATETIME_INTERVAL_OPEN_START_SYMBOL, "")
        parsed_datetime["before"] = date_parser.parse(datetime_interval)

    elif datetime_interval.endswith(DATETIME_INTERVAL_OPEN_END_SYMBOL):
        datetime_interval = datetime_interval.replace(DATETIME_INTERVAL_OPEN_END_SYMBOL, "")
        parsed_datetime["after"] = date_parser.parse(datetime_interval)

    elif DATETIME_INTERVAL_CLOSED_SYMBOL in datetime_interval:
        datetime_interval = datetime_interval.split(DATETIME_INTERVAL_CLOSED_SYMBOL)
        parsed_datetime["after"] = date_parser.parse(datetime_interval[0])
        parsed_datetime["before"] = date_parser.parse(datetime_interval[-1])
    else:
        parsed_datetime["match"] = date_parser.parse(datetime_interval)

    return parsed_datetime

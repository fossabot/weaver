"""
Functional tests for :mod:`weaver.cli`.
"""

import contextlib
import copy
import json
import logging
import os
import shutil
import tempfile
import uuid
from typing import TYPE_CHECKING

import pytest

from tests.functional.utils import ResourcesUtil, WpsConfigBase
from tests.utils import (
    get_weaver_url,
    mocked_dismiss_process,
    mocked_execute_celery,
    mocked_sub_requests,
    mocked_wps_output,
    run_command
)
from weaver.cli import WeaverClient, main as weaver_cli
from weaver.formats import ContentType, OutputFormat
from weaver.status import Status
from weaver.wps.utils import map_wps_output_location

if TYPE_CHECKING:
    from typing import Dict


@pytest.mark.cli
@pytest.mark.functional
class TestWeaverClientBase(WpsConfigBase, ResourcesUtil):
    def __init__(self, *args, **kwargs):
        # won't run this as a test suite, only its derived classes
        setattr(self, "__test__", self is TestWeaverClientBase)
        super(TestWeaverClientBase, self).__init__(*args, **kwargs)

    @classmethod
    def setUpClass(cls):
        cls.settings.update({
            "weaver.vault_dir": tempfile.mkdtemp(prefix="weaver-test-"),
            "weaver.wps_output_dir": tempfile.mkdtemp(prefix="weaver-test-"),
            "weaver.wps_output_url": "http://random-file-server.com/wps-outputs"
        })
        super(TestWeaverClientBase, cls).setUpClass()
        cls.url = get_weaver_url(cls.app.app.registry)
        cls.client = WeaverClient(cls.url)
        cli_logger = logging.getLogger("weaver.cli")
        cli_logger.setLevel(logging.DEBUG)

        cls.test_process_prefix = "test-client"

    def setUp(self):
        processes = self.process_store.list_processes()
        test_processes = filter(lambda _proc: _proc.id.startswith(self.test_process_prefix), processes)
        for proc in test_processes:
            self.process_store.delete_process(proc.id)

        # make one process available for testing features
        self.test_process = {}
        self.test_payload = {}
        for process in ["Echo", "CatFile"]:
            self.test_process[process] = f"{self.test_process_prefix}-{process}"
            self.test_payload[process] = self.retrieve_payload(process, "deploy", local=True)
            self.deploy_process(self.test_payload[process], process_id=self.test_process[process])

    @classmethod
    def tearDownClass(cls):
        super(TestWeaverClientBase, cls).tearDownClass()
        for tmp_dir_cfg in ["weaver.vault_dir", "weaver.wps_output_dir"]:
            tmp_wps_out = cls.settings.get(tmp_dir_cfg, "")
            if os.path.isdir(tmp_wps_out):
                shutil.rmtree(tmp_wps_out, ignore_errors=True)


class TestWeaverClient(TestWeaverClientBase):
    @classmethod
    def setUpClass(cls):
        super(TestWeaverClient, cls).setUpClass()
        cls.test_tmp_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        super(TestWeaverClient, cls).tearDownClass()
        shutil.rmtree(cls.test_tmp_dir, ignore_errors=True)

    def setup_test_file(self, original_file, substitutions):
        # type: (str, Dict[str, str]) -> str
        path = os.path.join(self.test_tmp_dir, str(uuid.uuid4()))
        os.makedirs(path, exist_ok=True)
        test_file_path = os.path.join(path, os.path.split(original_file)[-1])
        with open(original_file, mode="r", encoding="utf-8") as real_file:
            data = real_file.read()
            for sub, new in substitutions.items():
                data = data.replace(sub, new)
        with open(test_file_path, mode="w", encoding="utf-8") as test_file:
            test_file.write(data)
        return test_file_path

    def process_listing_op(self, operation):
        result = mocked_sub_requests(self.app, operation)
        assert result.success
        assert "processes" in result.body
        assert set(result.body["processes"]) == {
            # builtin
            "file2string_array",
            "file_index_selector",
            "jsonarray2netcdf",
            "metalink2netcdf",
            # test process
            self.test_process["CatFile"],
            self.test_process["Echo"],
        }
        assert "undefined" not in result.message

    def test_capabilities(self):
        self.process_listing_op(self.client.capabilities)

    def test_processes(self):
        self.process_listing_op(self.client.processes)

    def test_deploy_payload_body_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-body-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload["executionUnit"][0] = {"unit": package}

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_file_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-file-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload["executionUnit"][0] = {"href": package}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cwl") as body_file:
            json.dump(payload, body_file)
            body_file.flush()
            body_file.seek(0)
            result = mocked_sub_requests(self.app, self.client.deploy, test_id, body_file.name)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_inject_cwl_body(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-body"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload.pop("executionUnit", None)

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload, package)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_payload_inject_cwl_file(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-file"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload.pop("executionUnit", None)

        result = mocked_sub_requests(self.app, self.client.deploy, test_id, payload, package)
        assert result.success
        assert "processSummary" in result.body
        assert result.body["processSummary"]["id"] == test_id
        assert "deploymentDone" in result.body
        assert result.body["deploymentDone"] is True
        assert "undefined" not in result.message

    def test_deploy_with_undeploy(self):
        test_id = f"{self.test_process_prefix}-deploy-undeploy-flag"
        deploy = self.test_payload["Echo"]
        result = mocked_sub_requests(self.app, self.client.deploy, test_id, deploy)
        assert result.success
        result = mocked_sub_requests(self.app, self.client.deploy, test_id, deploy, undeploy=True)
        assert result.success
        assert "undefined" not in result.message

    def test_undeploy(self):
        # deploy a new process to leave the test one available
        other_payload = copy.deepcopy(self.test_payload["Echo"])
        other_process = self.test_process["Echo"] + "-other"
        self.deploy_process(other_payload, process_id=other_process)

        result = mocked_sub_requests(self.app, self.client.undeploy, other_process)
        assert result.success
        assert result.body.get("undeploymentDone", None) is True
        assert "undefined" not in result.message

        path = f"/processes/{other_process}"
        resp = mocked_sub_requests(self.app, "get", path, expect_errors=True)
        assert resp.status_code == 404

    def test_describe(self):
        result = mocked_sub_requests(self.app, self.client.describe, self.test_process["Echo"])
        assert result.success
        # see deployment file for details that are expected here
        assert result.body["id"] == self.test_process["Echo"]
        assert result.body["version"] == "1.0"
        assert result.body["keywords"] == ["test", "application"]  # app is added by Weaver since not CWL Workflow
        assert "message" in result.body["inputs"]
        assert result.body["inputs"]["message"]["title"] == "message"
        assert result.body["inputs"]["message"]["description"] == "Message to echo."
        assert result.body["inputs"]["message"]["minOccurs"] == 1
        assert result.body["inputs"]["message"]["maxOccurs"] == 1
        assert result.body["inputs"]["message"]["literalDataDomains"][0]["dataType"]["name"] == "string"
        assert "output" in result.body["outputs"]
        assert result.body["outputs"]["output"]["title"] == "output"
        assert result.body["outputs"]["output"]["description"] == "Output file with echo message."
        assert result.body["outputs"]["output"]["formats"] == [{"default": True, "mediaType": ContentType.TEXT_PLAIN}]
        assert "undefined" not in result.message, "CLI should not have confused process description as response detail."
        assert "description" not in result.body, "CLI should not have overridden the process description field."

    def run_execute_inputs_schema_variant(self, inputs_param, process="Echo",
                                          preload=False, location=False, expect_success=True, mock_exec=True):
        if isinstance(inputs_param, str):
            ref = {"location": inputs_param} if location else {"ref_name": inputs_param}
            if preload:
                inputs_param = self.retrieve_payload(process=process, local=True, **ref)
            else:
                inputs_param = self.retrieve_payload(process=process, local=True, **ref)
        with contextlib.ExitStack() as stack_exec:
            # use pass-through function because don't care about execution result here, only the parsing of I/O
            if mock_exec:
                mock_exec_func = lambda *_, **__: None  # noqa
            else:
                mock_exec_func = None
            for mock_exec_proc in mocked_execute_celery(func_execute_task=mock_exec_func):
                stack_exec.enter_context(mock_exec_proc)
            result = mocked_sub_requests(self.app, self.client.execute, self.test_process[process], inputs=inputs_param)
        if expect_success:
            assert result.success, result.message + (result.text if result.text else "")
            assert "jobID" in result.body
            assert "processID" in result.body
            assert "status" in result.body
            assert "location" in result.body
            assert result.body["processID"] == self.test_process[process]
            assert result.body["status"] == Status.ACCEPTED
            assert result.body["location"] == result.headers["Location"]
            assert "undefined" not in result.message
        else:
            assert not result.success, result.text
        return result

    def test_execute_inputs_cwl_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", preload=False)

    def test_execute_inputs_ogc_value_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_value_schema.yml", preload=False)

    def test_execute_inputs_ogc_mapping_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_mapping_schema.yml", preload=False)

    def test_execute_inputs_old_listing_file_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_old_listing_schema.yml", preload=False)

    def test_execute_inputs_cwl_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", preload=True)

    def test_execute_inputs_ogc_value_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_value_schema.yml", preload=True)

    def test_execute_inputs_ogc_mapping_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_ogc_mapping_schema.yml", preload=True)

    def test_execute_inputs_old_listing_literal_schema(self):
        self.run_execute_inputs_schema_variant("Execute_Echo_old_listing_schema.yml", preload=True)

    def test_execute_inputs_representation_literal_schema(self):
        self.run_execute_inputs_schema_variant(["message='hello world'"], preload=True)

    def test_execute_inputs_invalid(self):
        """
        Mostly check that errors don't raise an error in the client, but are handled and gracefully return a result.
        """
        for invalid_inputs_schema in [
            [1, 2, 3, 4],  # missing the ID
            [{"id": "message"}],  # missing the value
            {}  # valid schema, but missing inputs of process
        ]:
            self.run_execute_inputs_schema_variant(invalid_inputs_schema, expect_success=False)

    def test_execute_manual_monitor_status_and_download_results(self):
        """
        Test a typical case of :term:`Job` execution, result retrieval and download, but with manual monitoring.

        Manual monitoring can be valid in cases where a *very* long :term:`Job` must be executed, and the user does
        not intend to wait after it. This avoids leaving some shell/notebook/etc. open of a long time and provide a
        massive ``timeout`` value. Instead, the user can simply re-call :meth:`WeaverClient.monitor` at a later time
        to resume monitoring. Other situation can be if the connection was dropped or script runner crashed, and the
        want to pick up monitoring again.

        .. note::
            The :meth:`WeaverClient.execute` is accomplished synchronously during this test because of the mock.
            The :meth:`WeaverClient.monitor` step can therefore only return ``success``/``failed`` directly
            without any intermediate and asynchronous pooling of ``running`` status.
            The first status result from  :meth:`WeaverClient.execute` is ``accept`` because this is the
            default status that is generated by the HTTP response from the :term:`Job` creation.
            Any following GET status will directly return the final :term:`Job` result.
        """
        result = self.run_execute_inputs_schema_variant("Execute_Echo_cwl_schema.yml", mock_exec=False)
        job_id = result.body["jobID"]
        result = mocked_sub_requests(self.app, self.client.monitor, job_id, timeout=1, interval=1)
        assert result.success, result.text
        assert "undefined" not in result.message
        assert result.body.get("status") == Status.SUCCEEDED
        links = result.body.get("links")
        assert isinstance(links, list)
        assert len(list(filter(lambda _link: _link["rel"].endswith("results"), links))) == 1

        # first test to get job results details, but not downloading yet
        result = mocked_sub_requests(self.app, self.client.results, job_id)
        assert result.success, result.text
        assert "undefined" not in result.message
        outputs_body = result.body
        assert isinstance(outputs_body, dict) and len(outputs_body) == 1
        output = outputs_body.get("output")  # single of this process
        assert isinstance(output, dict) and "href" in output, "Output named 'output' should be a 'File' reference."
        output_href = output.get("href")
        assert isinstance(output_href, str) and output_href.startswith(self.settings["weaver.wps_output_url"])

        # test download feature
        with contextlib.ExitStack() as stack:
            server_mock = stack.enter_context(mocked_wps_output(self.settings))
            target_dir = stack.enter_context(tempfile.TemporaryDirectory())
            result = mocked_sub_requests(self.app, self.client.results,
                                         job_id, download=True, out_dir=target_dir,  # 'client.results' parameters
                                         only_local=True)  # mock parameter (avoid download HTTP redirect to TestApp)
            assert result.success, result.text
            assert "undefined" not in result.message
            assert result.body != outputs_body, "Download operation should modify the original outputs body."
            output = result.body.get("output", {})
            assert output.get("href") == output_href
            output_path = output.get("path")  # inserted by download
            assert isinstance(output_path, str) and output_path.startswith(target_dir)
            output_name = output_href.split(job_id)[-1][1:]  # everything after jobID, and without the first '/'
            output_file = os.path.join(target_dir, output_name)
            assert output_path == output_file
            assert os.path.isfile(output_file) and not os.path.islink(output_file)
            assert len(server_mock.calls) == 1  # list of (PreparedRequest, Response)
            assert server_mock.calls[0][0].url == output_href

    @pytest.mark.xfail(reason="not implemented")
    def test_execute_with_auto_monitor(self):
        """
        Test case where monitoring is accomplished automatically and inline to the execution before result download.
        """
        # FIXME: Properly test execute+monitor,
        #   Need an actual (longer) async call because 'mocked_execute_celery' blocks until complete.
        #   Therefore, no pooling monitoring actually occurs (only single get status with final result).
        #   Test should wrap 'get_job' in 'get_job_status' view (or similar wrapping approach) to validate that
        #   status was periodically pooled and returned 'running' until the final 'succeeded' resumes to download.
        raise NotImplementedError

    # NOTE:
    #   For all below '<>_auto_resolve_vault' test cases, the local file referenced in the Execute request body
    #   should be automatically handled by uploading to the Vault and forwarding the relevant X-Auth-Vault header.
    def run_execute_inputs_with_vault_file(self, test_input_file, process="CatFile", preload=False, embed=False):
        test_data = "DUMMY DATA"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt") as tmp_file:
            tmp_file.write(test_data)
            tmp_file.flush()
            tmp_file.seek(0)
            if embed:
                test_file = [test_input_file.format(test_file=tmp_file.name)]
            else:
                exec_file = self.retrieve_payload(process=process, ref_name=test_input_file, local=True, ref_found=True)
                test_file = self.setup_test_file(exec_file, {"<TEST_FILE>": tmp_file.name})
            result = self.run_execute_inputs_schema_variant(test_file, process=process,
                                                            preload=preload, location=True, mock_exec=False)
        job_id = result.body["jobID"]
        result = mocked_sub_requests(self.app, self.client.results, job_id)
        assert result.success, result.message
        output = result.body["output"]["href"]
        output = map_wps_output_location(output, self.settings, exists=True)
        assert os.path.isfile(output)
        with open(output, mode="r", encoding="utf-8") as out_file:
            out_data = out_file.read()
        assert out_data == test_data

    @pytest.mark.vault
    def test_execute_inputs_cwl_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_cwl_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_ogc_mapping_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_ogc_mapping_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_old_listing_file_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_old_listing_schema.yml", "CatFile", preload=False)

    @pytest.mark.vault
    def test_execute_inputs_cwl_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_cwl_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_ogc_mapping_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_ogc_mapping_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_old_listing_literal_schema_auto_resolve_vault(self):
        self.run_execute_inputs_with_vault_file("Execute_CatFile_old_listing_schema.yml", "CatFile", preload=True)

    @pytest.mark.vault
    def test_execute_inputs_representation_literal_schema_auto_resolve_vault(self):
        # 1st 'file' is the name of the process input
        # 2nd 'File' is the type (CWL) to ensure proper detection/conversion to href URL
        # 'test_file' will be replaced by the actual temp file instantiated with dummy data
        for input_data in [
            "file:File={test_file}",
            "file:File='{test_file}'",
            "file:File=\"{test_file}\"",
        ]:
            self.run_execute_inputs_with_vault_file(input_data, "CatFile", preload=False, embed=True)

    @mocked_dismiss_process()
    def test_dismiss(self):
        for status in [Status.ACCEPTED, Status.FAILED, Status.RUNNING, Status.SUCCEEDED]:
            proc = self.test_process["Echo"]
            job = self.job_store.save_job(task_id="12345678-1111-2222-3333-111122223333", process=proc)
            job.status = status
            job = self.job_store.update_job(job)
            result = mocked_sub_requests(self.app, self.client.dismiss, str(job.id))
            assert result.success
            assert "undefined" not in result.message


class TestWeaverCLI(TestWeaverClientBase):
    @classmethod
    def setUpClass(cls):
        super(TestWeaverCLI, cls).setUpClass()
        cls.test_job = cls.job_store.save_job(task_id="12345678-1111-2222-3333-111122223333", process="fake-process")

    def test_help_operations(self):
        lines = run_command(
            [
                "weaver",
                "--help",
            ],
            trim=False,
        )
        operations = [
            "deploy",
            "undeploy",
            "capabilities",
            "processes",
            "describe",
            "execute",
            "monitor",
            "dismiss",
            "results",
            "status",
        ]
        assert all(any(op in line for line in lines) for op in operations)

    def test_log_options_any_level(self):
        """
        Logging parameters should be allowed at main parser level or under any operation subparser.
        """
        proc = self.test_process["Echo"]
        for options in [
            ["--verbose", "describe", "-u", self.url, "-p", proc],
            ["describe", "-u", self.url, "--verbose", "-p", proc],
            ["describe", "-u", self.url, "-p", proc, "--verbose"],
        ]:
            lines = mocked_sub_requests(
                self.app, run_command,
                options,
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"id\": \"{proc}\"" in line for line in lines)

    def test_deploy_no_process_id_option(self):
        payload = self.retrieve_payload("Echo", "deploy", local=True, ref_found=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "--body", payload,  # no --process/--id, but available through --body
                "--cwl", package,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any("\"id\": \"Echo\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_body_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-body-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload["executionUnit"][0] = {"unit": package}

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", test_id,
                "-b", json.dumps(payload),  # literal JSON string accepted for CLI
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_file_cwl_embedded(self):
        test_id = f"{self.test_process_prefix}-deploy-file-no-cwl"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload["executionUnit"][0] = {"href": package}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".cwl") as body_file:
            json.dump(payload, body_file)
            body_file.flush()
            body_file.seek(0)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # weaver
                    "deploy",
                    "-u", self.url,
                    "-p", test_id,
                    "-b", body_file.name,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
            assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_inject_cwl_body(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-body"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True)
        payload.pop("executionUnit", None)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", test_id,
                "--body", json.dumps(payload),  # literal JSON string accepted for CLI
                "--cwl", json.dumps(package),   # literal JSON string accepted for CLI
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_deploy_payload_inject_cwl_file(self):
        test_id = f"{self.test_process_prefix}-deploy-body-with-cwl-file"
        payload = self.retrieve_payload("Echo", "deploy", local=True)
        package = self.retrieve_payload("Echo", "package", local=True, ref_found=True)
        payload.pop("executionUnit", None)

        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # weaver
                "deploy",
                "-u", self.url,
                "-p", test_id,
                "--body", json.dumps(payload),  # literal JSON string accepted for CLI
                "--cwl", package,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert any(f"\"id\": \"{test_id}\"" in line for line in lines)
        assert any("\"deploymentDone\": true" in line for line in lines)

    def test_describe(self):
        # prints formatted JSON ProcessDescription over many lines
        proc = self.test_process["Echo"]
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "describe",
                "-u", self.url,
                "-p", proc,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        # ignore indents of fields from formatted JSON content
        assert any(f"\"id\": \"{proc}\"" in line for line in lines)
        assert any("\"inputs\": {" in line for line in lines)
        assert any("\"outputs\": {" in line for line in lines)

    def test_describe_no_links(self):
        # prints formatted JSON ProcessDescription over many lines
        proc = self.test_process["Echo"]
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "describe",
                "-u", self.url,
                "-p", proc,
                "-L",
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        # ignore indents of fields from formatted JSON content
        assert any(f"\"id\": \"{proc}\"" in line for line in lines)
        assert any("\"inputs\": {" in line for line in lines)
        assert any("\"outputs\": {" in line for line in lines)
        assert all("\"links\":" not in line for line in lines)

    def test_execute_inputs_capture(self):
        """
        Verify that specified inputs are captured for a limited number of 1 item per ``-I`` option.
        """
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'",  # if -I not capture as indented, URL after would be combined in it
                    "-M",
                    "-T", 10,
                    "-W", 1,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any(f"\"status\": \"{Status.SUCCEEDED}\"" in line for line in lines)

    def test_execute_manual_monitor(self):
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'"
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            # ignore indents of fields from formatted JSON content
            assert any(f"\"processID\": \"{proc}\"" in line for line in lines)
            assert any("\"jobID\": \"" in line for line in lines)
            assert any("\"location\": \"" in line for line in lines)
            job_loc = [line for line in lines if "location" in line][0]
            job_ref = [line for line in job_loc.split("\"") if line][-1]
            job_id = job_ref.split("/")[-1]

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "monitor",
                    "-j", job_ref,
                    "-T", 10,
                    "-W", 1,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )

            assert any(f"\"jobID\": \"{job_id}\"" in line for line in lines)
            assert any(f"\"status\": \"{Status.SUCCEEDED}\"" in line for line in lines)
            assert any(f"\"href\": \"{job_ref}/results\"" in line for line in lines)
            assert any("\"rel\": \"http://www.opengis.net/def/rel/ogc/1.0/results\"" in line for line in lines)

    def test_execute_auto_monitor(self):
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", "message='TEST MESSAGE!'",
                    "-M",
                    "-T", 10,
                    "-W", 1
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert any("\"jobID\": \"" in line for line in lines)  # don't care value, self-handled
            assert any(f"\"status\": \"{Status.SUCCEEDED}\"" in line for line in lines)
            assert any("\"rel\": \"http://www.opengis.net/def/rel/ogc/1.0/results\"" in line for line in lines)

    def test_execute_result_by_reference(self):
        """
        Validate option to obtain outputs by reference returned with ``Link`` header.

        Result obtained is validated both with API outputs and extended auto-download outputs.
        """
        proc = self.test_process["Echo"]
        with contextlib.ExitStack() as stack_exec:
            out_tmp = stack_exec.enter_context(tempfile.TemporaryDirectory())
            stack_exec.enter_context(mocked_wps_output(self.settings))
            for mock_exec_proc in mocked_execute_celery():
                stack_exec.enter_context(mock_exec_proc)

            msg = "TEST MESSAGE!"
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "execute",
                    "-u", self.url,
                    "-p", proc,
                    "-I", f"message='{msg}'",
                    "-R", "output",
                    "-M",
                    "-T", 10,
                    "-W", 1,
                    "-F", OutputFormat.YAML,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert "jobID: " in lines[0]  # don't care value, self-handled
            assert any(f"status: {Status.SUCCEEDED}" in line for line in lines)

            job_id = lines[0].split(":")[-1].strip()
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "results",
                    "-u", self.url,
                    "-j", job_id,
                    "-H",   # must display header to get 'Link'
                    "-F", OutputFormat.YAML,
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            sep = lines.index("---")
            headers = lines[:sep]
            content = lines[sep+1:-1]  # ignore final newline
            assert len(headers) and any("Link:" in hdr for hdr in headers)
            assert content == ["null"], "When no download involved, body should be the original no-content results."

            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "results",
                    "-u", self.url,
                    "-j", job_id,
                    "-H",   # must display header to get 'Link'
                    "-F", OutputFormat.YAML,
                    "-D",
                    "-O", out_tmp
                ],
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            sep = lines.index("---")
            headers = lines[:sep]
            content = lines[sep+1:]

            assert len(content), "Content should have been populated from download to provide downloaded file paths."
            link = None
            for header in headers:
                if "Link:" in header:
                    link = header.split(":", 1)[-1].strip()
                    break
            assert link
            link = link.split(";")[0].strip("<>")
            path = map_wps_output_location(link, self.settings, url=False)
            assert os.path.isfile(path), "Original file results should exist in job output dir."

            # path should be in contents as well, pre-resolved within download dir (not same as job output dir)
            assert len([line for line in content if "path:" in line]) == 1
            path = None
            for line in content:
                if "path:" in line:
                    path = line.split(":", 1)[-1].strip()
                    break
            assert path
            assert path.startswith(out_tmp)
            assert os.path.isfile(path)
            with open(path, mode="r", encoding="utf-8") as file:
                data = file.read()
            assert msg in data  # technically, output is log of echoed input message, so not exactly equal

    def test_execute_help_details(self):
        """
        Verify that formatting of the execute operation help provides multiple paragraphs with more details.
        """
        lines = run_command(
            [
                "weaver",
                "execute",
                "--help",
            ],
            trim=False
        )
        start = -1
        end = -1
        for index, line in enumerate(lines):
            if "-I INPUTS, --inputs INPUTS" in line:
                start = index + 1
            if "Example:" in line:
                end = index
                break
        assert 0 < start < end
        indent = "  " * lines[start].count("  ")
        assert len(indent) > 4
        assert all(line.startswith(indent) for line in lines[start:end])
        assert len([line for line in lines[start:end] if line == indent]) > 3, "Inputs should have a few paragraphs."

    def test_execute_invalid_format(self):
        proc = self.test_process["Echo"]
        bad_input_value = "'this is my malformed message'"  # missing '<id>=' portion
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "execute",
                "-u", self.url,
                "-p", proc,
                "-I", bad_input_value,
                "-M",
                "-T", 10,
                "-W", 1
            ],
            trim=False,
            entrypoint=weaver_cli,
            expect_error=True,
            only_local=True,
        )
        assert any(bad_input_value in line for line in lines)

    def test_jobs(self):
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "jobs",
                "-u", self.url,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert lines
        assert any("jobs" in line for line in lines)
        assert any("total" in line for line in lines)
        assert any("limit" in line for line in lines)

    def test_output_format_json_pretty(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        for format_option in [[], ["-F", OutputFormat.JSON_STR]]:
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "status",
                    "-j", job_url,
                ] + format_option,
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert len(lines) > 1, "should be indented, pretty printed"
            assert lines[0].startswith("{")
            assert lines[-1].endswith("}")
            assert any("jobID" in line for line in lines)

    def test_output_format_json_pretty_and_headers(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.JSON_STR,
                "-H"
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0] == "Headers:"
        sep = "---"
        sep_pos = lines.index(sep)
        assert any("Content-Type:" in line for line in lines[1:sep_pos])
        result = lines[sep_pos+1:]
        assert len(result) > 1, "should be indented, pretty printed"
        assert result[0].startswith("{")
        assert result[-1].endswith("}")
        assert any("jobID" in line for line in result)

    def test_output_format_json_raw(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        for format_option in [["-F", OutputFormat.JSON], ["-F", OutputFormat.JSON_RAW]]:
            lines = mocked_sub_requests(
                self.app, run_command,
                [
                    # "weaver",
                    "status",
                    "-j", job_url,
                ] + format_option,
                trim=False,
                entrypoint=weaver_cli,
                only_local=True,
            )
            assert len(lines) == 1, "should NOT be indented, raw data directly in one block"
            assert lines[0].startswith("{")
            assert lines[0].endswith("}")
            assert "jobID" in lines[0]

    def test_output_format_yaml_pretty(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.YAML,
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0] == f"jobID: {self.test_job.id}"

    def test_output_format_xml_pretty(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.XML_STR
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0].startswith("<?xml")
        assert lines[1].startswith("<result>")
        assert lines[-1].endswith("</result>")
        assert any("jobID" in line for line in lines)

    def test_output_format_xml_pretty_and_headers(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.XML_STR,
                "-H"
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) > 1, "should be indented, pretty printed"
        assert lines[0] == "Headers:"
        sep = "---"
        sep_pos = lines.index(sep)
        assert any("Content-Type:" in line for line in lines[1:sep_pos])
        result = lines[sep_pos+1:]
        assert len(result) > 1, "should be indented, pretty printed"
        assert result[0].startswith("<?xml")
        assert result[1].startswith("<result>")
        assert result[-1].endswith("</result>")
        assert any("jobID" in line for line in result)

    def test_output_format_xml_raw(self):
        job_url = f"{self.url}/jobs/{self.test_job.id}"
        lines = mocked_sub_requests(
            self.app, run_command,
            [
                # "weaver",
                "status",
                "-j", job_url,
                "-F", OutputFormat.XML_RAW
            ],
            trim=False,
            entrypoint=weaver_cli,
            only_local=True,
        )
        assert len(lines) == 1, "should NOT be indented, raw data directly in one block"
        assert lines[0].startswith("<?xml")
        assert lines[0].endswith("</result>")
# -*- coding: utf-8 -*-
# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests oozie parser"""
from os import path
from typing import NamedTuple, Set, Dict

import unittest
from unittest import mock
from xml.etree import ElementTree as ET

from parameterized import parameterized

from o2a.converter import parser
from o2a.converter.mappers import ACTION_MAP
from o2a.converter.workflow import Workflow

from o2a.definitions import EXAMPLE_DEMO_PATH, EXAMPLES_PATH

from o2a.mappers import dummy_mapper, pig_mapper
from o2a.mappers import ssh_mapper
from o2a.o2a_libs.property_utils import PropertySet


class TestOozieParser(unittest.TestCase):
    def setUp(self):
        props = PropertySet(job_properties={}, config={})
        workflow = Workflow(
            input_directory_path=EXAMPLE_DEMO_PATH, output_directory_path="/tmp", dag_name="DAG_NAME_B"
        )
        self.parser = parser.OozieParser(
            workflow=workflow, props=props, action_mapper=ACTION_MAP, renderer=mock.MagicMock()
        )

    @mock.patch("o2a.mappers.kill_mapper.KillMapper.on_parse_node", wraps=None)
    def test_parse_kill_node(self, on_parse_node_mock):
        node_name = "kill_name"
        # language=XML
        kill_string = f"""
<kill name="{node_name}">
    <message>kill-text-to-log</message>
</kill>
"""
        self.parser.parse_kill_node(ET.fromstring(kill_string))

        self.assertIn(node_name, self.parser.workflow.nodes)

        on_parse_node_mock.assert_called_once_with()

    @mock.patch("o2a.mappers.end_mapper.EndMapper.on_parse_node", wraps=None)
    def test_parse_end_node(self, on_parse_node_mock):
        node_name = "end_name"
        # language=XML
        end_node_str = f"<end name='{node_name}'/>"

        end = ET.fromstring(end_node_str)
        self.parser.parse_end_node(end)

        self.assertIn(node_name, self.parser.workflow.nodes)

        on_parse_node_mock.assert_called_once_with()

    @mock.patch("o2a.mappers.dummy_mapper.DummyMapper.on_parse_node", wraps=None)
    @mock.patch("o2a.converter.parser.OozieParser.parse_node")
    def test_parse_fork_node(self, parse_node_mock, on_parse_node_mock):
        node_name = "fork_name"
        # language=XML
        root_string = f"""
<root>
    <fork name="{node_name}">
        <path start="task1" />
        <path start="task2" />
    </fork>
    <action name="task1" />
    <action name="task2" />
    <join name="join" to="end_node" />
    <end name="end_node" />
</root>
"""
        root = ET.fromstring(root_string)
        fork = root.find("fork")
        node1, node2 = root.findall("action")[0:2]
        self.parser.parse_fork_node(root, fork)
        node = self.parser.workflow.nodes[node_name]
        self.assertEqual(["task1", "task2"], node.get_downstreams())
        self.assertIn(node_name, self.parser.workflow.nodes)
        parse_node_mock.assert_any_call(root, node1)
        parse_node_mock.assert_any_call(root, node2)

        on_parse_node_mock.assert_called_once_with()

    @mock.patch("o2a.mappers.dummy_mapper.DummyMapper.on_parse_node", wraps=None)
    def test_parse_join_node(self, on_parse_node_mock):
        node_name = "join_name"
        end_name = "end_name"
        # language=XML
        join_str = f"<join name='{node_name}' to='{end_name}' />"
        join = ET.fromstring(join_str)
        self.parser.parse_join_node(join)

        node = self.parser.workflow.nodes[node_name]
        self.assertIn(node_name, self.parser.workflow.nodes)
        self.assertEqual([end_name], node.get_downstreams())

        on_parse_node_mock.assert_called_once_with()

    @mock.patch("o2a.mappers.decision_mapper.DecisionMapper.on_parse_node", wraps=None)
    def test_parse_decision_node(self, on_parse_node_mock):
        node_name = "decision_node"
        # language=XML
        decision_str = f"""
<decision name="{node_name}">
    <switch>
        <case to="down1">${{fs:fileSize(secondjobOutputDir) gt 10 * GB}}</case>
        <case to="down2">${{fs:filSize(secondjobOutputDir) lt 100 * MB}}</case>
        <default to="end1" />
    </switch>
    </decision>
"""
        decision = ET.fromstring(decision_str)
        self.parser.parse_decision_node(decision)

        p_op = self.parser.workflow.nodes[node_name]
        self.assertIn(node_name, self.parser.workflow.nodes)
        self.assertEqual(["down1", "down2", "end1"], p_op.get_downstreams())

        on_parse_node_mock.assert_called_once_with()

    @mock.patch("o2a.mappers.start_mapper.StartMapper.on_parse_node", wraps=None)
    @mock.patch("uuid.uuid4")
    def test_parse_start_node(self, uuid_mock, on_parse_node_mock):
        uuid_mock.return_value = "1234"
        node_name = "start_node_1234"
        end_name = "end_name"
        # language=XML
        start_node_str = f"<start to='{end_name}'/>"
        start = ET.fromstring(start_node_str)
        self.parser.parse_start_node(start)

        p_op = self.parser.workflow.nodes[node_name]
        self.assertIn(node_name, self.parser.workflow.nodes)
        self.assertEqual([end_name], p_op.get_downstreams())

        on_parse_node_mock.assert_called_once_with()

    @mock.patch("o2a.mappers.ssh_mapper.SSHMapper.on_parse_node", wraps=None)
    def test_parse_action_node_ssh(self, on_parse_node_mock):
        self.parser.action_map = {"ssh": ssh_mapper.SSHMapper}
        node_name = "action_name"
        # language=XML
        action_string = f"""
<action name='{node_name}'>
    <ssh>
        <host>user@apache.org</host>
        <command>ls</command>
        <args>-l</args>
        <args>-a</args>
        <capture-output/>
    </ssh>
    <ok to='end1'/>
    <error to='fail1'/>
</action>
"""
        action_node = ET.fromstring(action_string)
        self.parser.parse_action_node(action_node)

        p_op = self.parser.workflow.nodes[node_name]
        self.assertIn(node_name, self.parser.workflow.nodes)
        self.assertEqual(["end1"], p_op.get_downstreams())
        self.assertEqual("fail1", p_op.get_error_downstream_name())

        on_parse_node_mock.assert_called_once_with()

    def test_parse_action_node_pig_with_file_and_archive(self):
        self.parser.action_map = {"pig": pig_mapper.PigMapper}
        node_name = "pig-node"
        self.parser.props.job_properties = {"nameNode": "myNameNode"}
        # language=XML
        action_string = f"""
<action name='{node_name}'>
    <pig>
        <resource-manager>myResManager</resource-manager>
        <name-node>myNameNode</name-node>
        <script>id.pig</script>
        <file>/test_dir/test.txt#test_link.txt</file>
        <archive>/test_dir/test2.zip#test_zip_dir</archive>
    </pig>
    <ok to='end1'/>
    <error to='fail1'/>
</action>
"""
        action_node = ET.fromstring(action_string)
        self.parser.parse_action_node(action_node)

        p_op = self.parser.workflow.nodes[node_name]
        self.assertIn(node_name, self.parser.workflow.nodes)
        self.assertEqual(["end1"], p_op.get_downstreams())
        self.assertEqual("fail1", p_op.get_error_downstream_name())
        self.assertEqual(["myNameNode/test_dir/test.txt#test_link.txt"], p_op.mapper.hdfs_files)
        self.assertEqual(["myNameNode/test_dir/test2.zip#test_zip_dir"], p_op.mapper.hdfs_archives)

    def test_parse_mapreduce_node(self):
        self.parser.job_properties = {"nameNode": "hdfs://"}
        self.parser.config = {"dataproc_cluster": "mycluster", "gcp_region": "europe-west3"}
        node_name = "mr-node"
        # language=XML
        xml = f"""
<action name='{node_name}'>
    <map-reduce>
        <name-node>hdfs://</name-node>
        <prepare>
            <delete path="hdfs:///user/mapreduce/examples/apps/mapreduce/output"/>
        </prepare>
    </map-reduce>
    <ok to="end"/>
    <error to="fail"/>
</action>
"""
        action_node = ET.fromstring(xml)
        self.parser.parse_action_node(action_node)
        self.assertIn(node_name, self.parser.workflow.nodes)
        mr_node = self.parser.workflow.nodes[node_name]
        self.assertEqual(["end"], mr_node.get_downstreams())
        self.assertEqual("fail", mr_node.get_error_downstream_name())

    @mock.patch("o2a.mappers.dummy_mapper.DummyMapper.on_parse_node", wraps=None)
    def test_parse_action_node_unknown(self, on_parse_node_mock):
        self.parser.action_map = {"unknown": dummy_mapper.DummyMapper}
        node_name = "action_name"
        # language=XML
        action_str = """
<action name="action_name">
    <ssh><host />
    <command />
    <args />
    <args />
    <capture-output />
    </ssh>
    <ok to="end1" />
    <error to="fail1" />
</action>
"""
        action = ET.fromstring(action_str)
        self.parser.parse_action_node(action)

        p_op = self.parser.workflow.nodes[node_name]
        self.assertIn(node_name, self.parser.workflow.nodes)
        self.assertEqual(["end1"], p_op.get_downstreams())
        self.assertEqual("fail1", p_op.get_error_downstream_name())

        on_parse_node_mock.assert_called_once_with()

    @mock.patch("o2a.converter.parser.OozieParser.parse_action_node")
    def test_parse_node_action(self, action_mock):
        root = ET.Element("root")
        action = ET.SubElement(root, "action", attrib={"name": "test_name"})
        self.parser.parse_node(root, action)
        action_mock.assert_called_once_with(action)

    @mock.patch("o2a.converter.parser.OozieParser.parse_start_node")
    def test_parse_node_start(self, start_mock):
        root = ET.Element("root")
        start = ET.SubElement(root, "start", attrib={"name": "test_name"})
        self.parser.parse_node(root, start)
        start_mock.assert_called_once_with(start)

    @mock.patch("o2a.converter.parser.OozieParser.parse_kill_node")
    def test_parse_node_kill(self, kill_mock):
        root = ET.Element("root")
        kill = ET.SubElement(root, "kill", attrib={"name": "test_name"})
        self.parser.parse_node(root, kill)
        kill_mock.assert_called_once_with(kill)

    @mock.patch("o2a.converter.parser.OozieParser.parse_end_node")
    def test_parse_node_end(self, end_mock):
        root = ET.Element("root")
        end = ET.SubElement(root, "end", attrib={"name": "test_name"})
        self.parser.parse_node(root, end)
        end_mock.assert_called_once_with(end)

    @mock.patch("o2a.converter.parser.OozieParser.parse_fork_node")
    def test_parse_node_fork(self, fork_mock):
        root = ET.Element("root")
        fork = ET.SubElement(root, "fork", attrib={"name": "test_name"})
        self.parser.parse_node(root, fork)
        fork_mock.assert_called_once_with(root, fork)

    @mock.patch("o2a.converter.parser.OozieParser.parse_join_node")
    def test_parse_node_join(self, join_mock):
        root = ET.Element("root")
        join = ET.SubElement(root, "join", attrib={"name": "test_name"})
        self.parser.parse_node(root, join)
        join_mock.assert_called_once_with(join)

    @mock.patch("o2a.converter.parser.OozieParser.parse_decision_node")
    def test_parse_node_decision(self, decision_mock):
        root = ET.Element("root")
        decision = ET.SubElement(root, "decision", attrib={"name": "test_name"})
        self.parser.parse_node(root, decision)
        decision_mock.assert_called_once_with(decision)


class WorkflowTestCase(NamedTuple):
    name: str
    node_names: Set[str]
    job_properties: Dict[str, str]
    config: Dict[str, str]


class TestOozieExamples(unittest.TestCase):
    @parameterized.expand(
        [
            (
                WorkflowTestCase(
                    name="decision",
                    node_names={"start_node_1234", "decision-node", "first", "end", "kill"},
                    job_properties={"nameNode": "hdfs://"},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="demo",
                    node_names={
                        "start_node_1234",
                        "fork-node",
                        "pig-node",
                        "subworkflow-node",
                        "shell-node",
                        "join-node",
                        "decision-node",
                        "hdfs-node",
                        "end",
                        "fail",
                    },
                    job_properties={"nameNode": "hdfs://"},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="el",
                    node_names={"start_node_1234", "ssh", "end", "fail"},
                    job_properties={"hostname": "user@BBB", "nameNode": "hdfs://"},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="fs",
                    node_names={
                        "start_node_1234",
                        "end",
                        "fail",
                        "chmod",
                        "mkdir",
                        "fs-node",
                        "delete",
                        "move",
                        "touchz",
                        "chgrp",
                        "join",
                    },
                    job_properties={"hostname": "user@BBB", "nameNode": "hdfs://localhost:8020/"},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="mapreduce",
                    node_names={"start_node_1234", "end", "fail", "mr-node"},
                    job_properties={"dataproc_cluster": "A", "nameNode": "hdfs://"},
                    config={"gcp_region": "B"},
                ),
            ),
            (
                WorkflowTestCase(
                    name="pig",
                    node_names={"start_node_1234", "end", "fail", "pig-node"},
                    job_properties={"oozie.wf.application.path": "hdfs://", "nameNode": "hdfs://"},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="shell",
                    node_names={"start_node_1234", "end", "fail", "shell-node"},
                    job_properties={"nameNode": "hdfs://"},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="spark",
                    node_names={"start_node_1234", "end", "fail", "spark-node"},
                    job_properties={"nameNode": "hdfs://"},
                    config={"dataproc_cluster": "A", "gcp_region": "B"},
                ),
            ),
            (
                WorkflowTestCase(
                    name="ssh",
                    node_names={"start_node_1234", "end", "fail", "ssh"},
                    job_properties={"hostname": "user@BBB", "nameNode": "hdfs://"},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="subwf",
                    node_names={"start_node_1234", "end", "fail", "subworkflow-node"},
                    job_properties={},
                    config={},
                ),
            ),
            (
                WorkflowTestCase(
                    name="distcp",
                    node_names={"start_node_1234", "end", "fail", "distcp-node"},
                    job_properties={
                        "hostname": "AAAA@BBB",
                        "nameNode": "hdfs://",
                        "nameNode1": "hdfs://localhost:8081",
                        "nameNode2": "hdfs://localhost:8082",
                    },
                    config={},
                ),
            ),
        ],
        name_func=lambda func, num, p: f"{func.__name__}_{num}_{p.args[0].name}",
    )
    @mock.patch("uuid.uuid4", return_value="1234")
    def test_parse_workflow_examples(self, case: WorkflowTestCase, _):
        workflow = Workflow(
            input_directory_path=path.join(EXAMPLES_PATH, case.name),
            output_directory_path="/tmp",
            dag_name="DAG_NAME_B",
        )
        current_parser = parser.OozieParser(
            workflow=workflow,
            props=PropertySet(job_properties=case.job_properties, config=case.config),
            action_mapper=ACTION_MAP,
            renderer=mock.MagicMock(),
        )
        current_parser.parse_workflow()
        self.assertEqual(case.node_names, set(current_parser.workflow.nodes.keys()))
        self.assertEqual(set(), current_parser.workflow.relations)

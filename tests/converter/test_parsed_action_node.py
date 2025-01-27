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
"""Tests parsed node"""
import unittest
from unittest import mock
from xml.etree.ElementTree import Element

from airflow.utils.trigger_rule import TriggerRule

from o2a.converter import parsed_action_node
from o2a.converter.task import Task
from o2a.mappers import dummy_mapper


class TestParseActiondNode(unittest.TestCase):
    def setUp(self):
        oozie_node = Element("dummy")
        op1 = dummy_mapper.DummyMapper(oozie_node=oozie_node, name="task1", dag_name="DAG_NAME_B")
        self.p_node = parsed_action_node.ParsedActionNode(op1)

    def test_add_downstream_node_name(self):
        self.p_node.add_downstream_node_name("task1")
        self.assertIn("task1", self.p_node.get_downstreams())
        self.assertIn("task1", self.p_node.downstream_names)

    def test_set_downstream_error_node_name(self):
        self.p_node.set_error_node_name("task1")
        self.assertIn("task1", self.p_node.get_error_downstream_name())
        self.assertIn("task1", self.p_node.error_xml)

    def test_update_trigger_rule_both(self):
        self.p_node.is_ok = True
        self.p_node.is_error = True
        self.p_node.update_trigger_rule()
        self.assertTrue(all(task.trigger_rule == TriggerRule.DUMMY for task in self.p_node.tasks))

    def test_update_trigger_rule_ok(self):
        self.p_node.is_ok = True
        self.p_node.is_error = False
        self.p_node.update_trigger_rule()
        self.assertTrue(all(task.trigger_rule == TriggerRule.ALL_SUCCESS for task in self.p_node.tasks))

    def test_update_trigger_rule_error(self):
        self.p_node.is_ok = False
        self.p_node.is_error = True
        self.p_node.update_trigger_rule()
        self.assertTrue(all(task.trigger_rule == TriggerRule.ONE_FAILED for task in self.p_node.tasks))

    def test_update_trigger_rule_(self):
        self.p_node.is_ok = False
        self.p_node.is_error = False
        self.p_node.update_trigger_rule()
        self.assertTrue(all(task.trigger_rule == TriggerRule.DUMMY for task in self.p_node.tasks))


class TestParserNodeMultipleOperators(unittest.TestCase):
    def test_first_task_id(self):
        op1 = mock.Mock()
        p_node = parsed_action_node.ParsedActionNode(op1, tasks=self._get_tasks())

        self.assertEqual("first_task_id", p_node.first_task_id)

    def test_last_task_id(self):
        op1 = mock.Mock()
        p_node = parsed_action_node.ParsedActionNode(op1, tasks=self._get_tasks())

        self.assertEqual("last_task_id", p_node.last_task_id)

    @staticmethod
    def _get_dummy_task(task_id):
        return Task(task_id=task_id, template_name="dummy.tpl")

    @classmethod
    def _get_tasks(cls):
        return [
            cls._get_dummy_task("first_task_id"),
            cls._get_dummy_task("second_task_id"),
            cls._get_dummy_task("last_task_id"),
        ]

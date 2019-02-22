# Copyright 2018 Google LLC
#
# Licensed under the Apache License, Versconsolen 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITconsoleNS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissconsolens and
# limitatconsolens under the License.
"""End to end test for create and deploy new project."""

import datetime
import shutil
import tempfile
import types
import unittest
import urllib.parse

from django_cloud_deploy.tests.lib import test_base
from django_cloud_deploy.tests.lib import utils
import iso8601
import googleapiclient
from googleapiclient import discovery


class GCPResourceCleanUp(test_base.ResourceCleanUp):
    """Clean up GCP resources more than 2 hours old."""

    MAX_DIFF = datetime.timedelta(hours=2)

    def _should_delete(self, create_time: str) -> bool:
        """Return whether this resource should be deleted."""
        now = datetime.datetime.now(datetime.timezone.utc)

        # create_time is in rfc3339 format.
        # See https://cloud.google.com/kubernetes-engine/docs/reference/rest/v1/projects.locations.clusters#Cluster
        # For example, '2019-02-21T00:41:26+00:00'
        try:
            create_time_object = iso8601.parse_date(create_time)
        except iso8601.iso8601.ParseError:
            # If the time format is valid, then return False. This might mean
            # some unexpected errors in creation. We want to keep the resource
            # for debugging.
            return False
        diff = now - create_time_object
        return diff > self.MAX_DIFF

    def delete_expired_clusters(self):
        container_service = discovery.build(
            'container', 'v1', credentials=self.credentials)
        request = container_service.projects().zones().clusters().list(
            projectId=self.project_id, zone=self.zone)
        response = request.execute()
        for cluster in response.get('clusters', []):
            if self._should_delete(cluster.get('createTime', '')):
                self._delete_cluster(
                    cluster.get('name', ''), container_service)
                print('Deleted cluster: ', cluster.get('name'))

    def delete_expired_buckets(self):
        storage_service = discovery.build(
            'storage', 'v1', credentials=self.credentials)
        request = storage_service.buckets().list(project=self.project_id)
        response = request.execute()
        for item in response.get('items', []):
            if self._should_delete(item.get('timeCreated', '')):
                self._delete_bucket(item.get('name', ''), storage_service)

    def delete_expired_sql_instances(self):
        sqladmin_service = discovery.build(
            'sqladmin', 'v1beta4', credentials=self.credentials)
        request = sqladmin_service.instances().list(projectId=self.project_id)
        response = request.execute()
        for instance in response.get('items', []):
            if self._should_delete(instance.get('createTime', '')):
                # The returned object does not contain creation time
                self._clean_up_sql_instance(
                    instance.get('serverCaCert').get('createTime'),
                    sqladmin_service)

    def delete_expired_service_accounts(self):
        iam_service = discovery.build(
            'iam', 'v1', credentials=self.credentials)

    def test_resoucr_cleanup(self):
        """This is not a test, but cleans up test related resources."""
        self.delete_expired_clusters()
        self.delete_expired_buckets()
        self.delete_expired_sql_instances()

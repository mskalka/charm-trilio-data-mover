import mock
from unittest.mock import (
    patch,
    mock_open
)

import lib.trilio.trilio_data_mover_utils as datamover_utils
import unit_tests.test_utils

import charmhelpers
import os
import time
import shutil
import subprocess  # noqa


class TestTrilioDataMoverUtils(unit_tests.test_utils.CharmTestCase):

    def setUp(self):
        super(TestTrilioDataMoverUtils, self).setUp()
        self.obj = datamover_utils
        self.patches = ['config', 'status_set', 'log']
        self.patch_all()

    @patch.object(charmhelpers.fetch, 'add_source')
    @patch.object(charmhelpers.fetch, 'apt_update')
    @patch.object(charmhelpers.fetch, 'apt_install')
    def test_install_plugin(
            self,
            ch_add_source,
            ch_apt_update,
            ch_apt_install):
        result = datamover_utils.install_plugin('1.2.3.4', 'version', 'venv')
        self.status_set.assert_called_once_with('maintenance', 'Starting')
        self.assertTrue(result)

    @patch.object(subprocess, 'check_call')
    @patch.object(os, 'remove')
    @patch.object(shutil, 'rmtree')
    @patch.object(charmhelpers.core.host, 'service_running')
    @patch.object(datamover_utils, 'uninstall_plugin')
    def test_uninstall_plugin_no_timeout(
            self,
            subprocess_check_call,
            os_remove,
            shutil_rmtree,
            ch_service_running,
            uninstall_plugin):
        pass

    @patch.object(subprocess, 'check_call')
    @patch.object(os, 'remove')
    @patch.object(shutil, 'rmtree')
    @patch.object(charmhelpers.core.host, 'service_running')
    @patch.object(charmhelpers.core.host, 'mounts')
    @patch.object(charmhelpers.core.host, 'unmount')
    @patch.object(time, 'sleep')
    @patch.object(charmhelpers.fetch, 'apt_purge')
    @patch.object(datamover_utils, 'uninstall_plugin')
    def test_uninstall_plugin_timeout(
            self,
            subprocess_check_call,
            os_remove,
            shutil_rmtree,
            ch_service_running,
            ch_mounts,
            ch_unmount,
            time_sleep,
            ch_apt_purge,
            uninstall_plugin):
        pass

    @patch.object(subprocess, 'check_call')
    def test_validate_ip_valid_ipv4(
            self,
            subprocess_check_call):
        subprocess_check_call.return_value = True
        self.assertTrue(datamover_utils.validate_ip('1.2.3.4'))

    def test_validate_ip_invalid_ipv4(self):
        self.assertFalse(datamover_utils.validate_ip('1.2.3.X'))

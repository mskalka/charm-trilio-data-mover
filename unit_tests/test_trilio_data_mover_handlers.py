import mock
import charms.reactive
import unit_tests.test_utils

from unittest.mock import patch
import charms_openstack.test_utils as test_utils

# Mock out reactive decorators prior to importing reactive.data_mover_handers
dec_mock = mock.MagicMock()
dec_mock.return_value = lambda x: x
charms.reactive.hook = dec_mock
charms.reactive.when = dec_mock
charms.reactive.when_not = dec_mock

import reactive.trilio_data_mover_handlers as handlers


class TestRegisteredHooks(test_utils.TestRegisteredHooks):

    def test_hooks(self):
        # test that the hooks actually registered the relation expressions that
        # are meaningful for this interface: this is to handle regressions.
        # The keys are the function names that the hook attaches to.
        hook_set = {
            'when': {
                'config_changed': ('config.changed',
                                   'tvault-contego.installed'),
                'stop_tvault_contego_plugin': ('tvault-contego.stopping', ),
            },
            'when_not': {
                'install_tvault_contego_plugin': (
                    'tvault-contego.installed', ),
            },
        }
        # test that the hooks were registered via the
        # reactive.trilio_data_mover_handlers
        self.registered_hooks_test_helper(handlers, hook_set, [])

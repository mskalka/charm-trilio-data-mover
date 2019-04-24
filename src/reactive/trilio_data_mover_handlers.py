import subprocess

from charms.reactive import (
    when,
    when_not,
    set_flag,
    hook,
    remove_state,
    set_state,
)
from charmhelpers.core.hookenv import (
    status_set,
    config,
    log,
    application_version_set,
)
from charmhelpers.core.host import (
    service_start,
    service_stop,
    service_restart,
)
from trilio.trilio_data_mover_utils import (
    add_users,
    create_conf,
    create_service_file,
    create_virt_env,
    ensure_files,
    ensure_data_dir,
    get_new_version,
    uninstall_plugin,
    validate_ip,
    validate_nfs,
)


@when_not('tvault-contego.installed')
def install_tvault_contego_plugin():

    status_set('maintenance', 'Installing...')

    # Read config parameters TrilioVault IP, backup target
    tv_ip = config('triliovault-ip')

    # Validate triliovault_ip
    if not validate_ip(tv_ip):
        return

    # Valildate backup target
    if not validate_nfs():
        log("Failed while validating NFS mount")
        return

    # Proceed as triliovault_ip Address is valid
    if not add_users():
        log("Failed while adding Users")
        return

    if not create_virt_env():
        log("Failed while Creating Virtual Env")
        return

    if not ensure_files():
        log("Failed while ensuring files")
        return

    if not create_conf():
        log("Failed while creating conf files")
        return

    if not ensure_data_dir():
        log("Failed while ensuring datat directories")
        return

    if not create_service_file():
        log("Failed while creating DataMover service file")
        return

    subprocess.check_call(['systemctl', 'daemon-reload'])
    # Enable and start the datamover service
    subprocess.check_call(['systemctl', 'enable', 'tvault-contego'])
    service_restart('tvault-contego')

    # Install was successful
    status_set('active', 'Unit is ready')
    # Add the flag "installed" since it's done
    application_version_set(get_new_version('tvault-contego'))
    set_flag('tvault-contego.installed')


@when('config.changed')
@when('tvault-contego.installed')
def config_changed():
    ''' Stop the Trilio service, render new config, restart the service '''
    service_stop('tvault-contego')
    if validate_nfs():
        create_conf()
        status_set('active', 'Unit is ready')
    service_start('tvault-contego')


@hook('stop')
def stop_handler():
    # Set the user defined "stopping" state when this hook event occurs.
    set_state('tvault-contego.stopping')


@when('tvault-contego.stopping')
def stop_tvault_contego_plugin():

    status_set('maintenance', 'Stopping Trilio service')
    # Call the script to stop and uninstll TrilioVault Datamover
    if uninstall_plugin():
        # Uninstall was successful
        # Remove the state "stopping" since it's done
        remove_state('tvault-contego.stopping')

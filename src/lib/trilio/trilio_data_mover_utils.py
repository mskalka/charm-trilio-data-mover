import configparser
import netaddr
import os
import re
import shutil
import subprocess
import time

from charmhelpers.core.host import (
    service_stop,
    service_running,
    write_file,
    mount,
    umount,
    mounts,
    add_user_to_group,
    symlink,
    mkdir,
    chownr,
)
from charmhelpers.core.hookenv import (
    status_set,
    config,
    log,
)
from charmhelpers.fetch import (
    add_source,
    apt_install,
    apt_update,
    apt_purge,
    filter_missing_packages,
    archiveurl,
)


TVAULT_VIRTENV_PATH = '/home/tvault/.virtenv'
TVAULT_HOME = '/home/tvault'
DATAMOVER_CONF = '/etc/tvault-contego/tvault-contego.conf'
TV_DATA_DIR = '/var/triliovault-mounts'
TV_DATA_DIR_OLD = '/var/triliovault'
DM_EXT_USR = 'nova'
DM_EXT_GRP = 'nova'


def get_new_version(pkg):
    """
    Get the latest version available on the TrilioVault node.
    """
    tv_ip = config('triliovault-ip')
    tv_port = 8081

    curl_cmd = 'curl -s http://{}:{}/packages/'.format(tv_ip, tv_port).split()
    pkgs = subprocess.check_output(curl_cmd)
    new_ver = re.search(
        r'packages/{}-\s*([\d.]+)'.format(pkg),
        pkgs.decode('utf-8')).group(1)[:-1]

    return new_ver


def check_presence(tv_file):
    """
    Just a wrpper of 'ls' command
    """
    try:
        subprocess.check_output(['ls', tv_file])
        return True
    except subprocess.CalledProcessError:
        return False
    return False


def validate_nfs():
    """
    Validate the nfs mount device
    """
    usr = DM_EXT_USR
    grp = DM_EXT_GRP
    data_dir = TV_DATA_DIR
    device = config('nfs-shares')

    # install nfs-common package
    if not filter_missing_packages(['nfs-common']):
        log("'nfs-common' package not found, installing the package...")
        apt_install(['nfs-common'], fatal=True)

    if not device:
        log("NFS shares can not be empty."
            "Check 'nfs-shares' value in config")
        status_set(
            'blocked',
            'No valid nfs-shares configuration found, please recheck')
        return False

    # Ensure mount directory exists
    mkdir(data_dir, owner=usr, group=grp, perms=501, force=True)

    # check for mountable device
    if not mount(device, data_dir, filesystem='nfs'):
        log("Unable to mount, please enter valid mount device")
        status_set(
            'blocked',
            'Failed while validating NFS mount, please recheck configuration')
        return False
    log("Device mounted successfully")
    umount(data_dir)
    log("Device unmounted successfully")
    return True


def add_users():
    """
    Adding passwordless sudo access to nova user and adding to required groups
    """
    usr = DM_EXT_USR
    path = '/etc/sudoers.d/tvault-nova'
    source = '/usr/lib'
    destination = '/usr/lib64'
    content = '{} ALL=(ALL) NOPASSWD: ALL'.format(usr)
    try:
        write_file(path, content, owner='root', group='root', perms=501)

        # Adding nova user to system groups
        add_user_to_group(usr, 'kvm')
        add_user_to_group(usr, 'disk')

        # create symlink /usr/lib64/
        symlink(source, destination)
    except Exception as e:
        log("Failed while adding user with msg: {}".format(e))
        status_set('blocked', 'Failed while adding Users')
        return False

    return True


def create_virt_env():
    """
    Checks if latest version is installed or else imports the new virtual env
    And installs the Datamover package.
    """
    usr = DM_EXT_USR
    grp = DM_EXT_GRP
    path = TVAULT_HOME
    venv_path = TVAULT_VIRTENV_PATH
    tv_ip = config('triliovault-ip')
    dm_ver = None
    # create virtenv dir(/home/tvault) if it does not exist
    mkdir(path, owner=usr, group=grp, perms=501, force=True)

    latest_dm_ver = get_new_version('tvault-contego')
    if dm_ver == latest_dm_ver:
        log("Latest TrilioVault DataMover package is already installed,"
            " exiting")
        return True

    # Create virtual environment for DataMover
    handler = archiveurl.ArchiveUrlFetchHandler()
    try:
        # remove old venv if it exists
        shutil.rmtree(venv_path)
        venv_src = 'http://{}:8081/packages/queens_ubuntu'\
                   '/tvault-contego-virtenv.tar.gz'.format(tv_ip)
        venv_dest = path
        handler.install(venv_src, venv_dest)
        log("Virtual Environment installed successfully")
    except Exception as e:
        log("Failed to install Virtual Environment")
        status_set('blocked', 'Failed while Creating Virtual Env')
        return False

    # Get dependent libraries paths
    try:
        cmd = ['/usr/bin/python', 'files/trilio/get_pkgs.py']
        sym_link_paths = \
            subprocess.check_output(cmd).decode('utf-8').strip().split('\n')
    except Exception as e:
        log("Failed to get the dependent packages--{}".format(e))
        return False

    # Install TrilioVault Datamover package
    if not install_plugin(tv_ip, latest_dm_ver, '/usr'):
        return False

    # Create symlinks of the dependent libraries
    venv_pkg_path = '{}/lib/python2.7/site-packages/'.format(venv_path)
    shutil.rmtree('{}/cryptography'.format(venv_pkg_path))
    shutil.rmtree('{}/cffi'.format(venv_pkg_path))

    symlink(sym_link_paths[0], '{}/cryptography'.format(venv_pkg_path))
    symlink(sym_link_paths[2], '{}/cffi'.format(venv_pkg_path))

    shutil.copy(sym_link_paths[1], '{}/libvirtmod.so'.format(venv_pkg_path))
    shutil.copy(sym_link_paths[3], '{}/_cffi_backend.so'.format(venv_pkg_path))

    # change virtenv dir(/home/tvault) users to nova
    chownr(path, usr, grp)

    # Copy Trilio sudoers and filters files
    shutil.copy('files/trilio/trilio_sudoers', '/etc/sudoers.d/')
    shutil.copy('files/trilio/trilio.filters', '/etc/nova/rootwrap.d/')

    return True


def ensure_files():
    """
    Ensures all the required files or directories
    are present before it starts the datamover service.
    """
    usr = DM_EXT_USR
    grp = DM_EXT_GRP
    dm_bin = '/usr/bin/tvault-contego'
    log_path = '/var/log/nova'
    log_file = '{}/tvault-contego.log'.format(log_path)
    conf_path = '/etc/tvault-contego'
    # Creates log directory if doesn't exists
    mkdir(log_path, owner=usr, group=grp, perms=501, force=True)
    write_file(log_file, '', owner=usr, group=grp, perms=501)
    if not check_presence(dm_bin):
        log("TrilioVault Datamover binary is not present")
        status_set(
            'blocked',
            'TrilioVault Datamover binary is not present on TVault VM')
        return False

    # Creates conf directory if doesn't exists
    mkdir(conf_path, owner=usr, group=grp, perms=501, force=True)

    return True


def create_conf():
    """
    Creates datamover config file.
    """
    nfs_share = config('nfs-shares')
    nfs_options = config('nfs-options')

    tv_config = configparser.RawConfigParser()
    tv_config.set('DEFAULT', 'vault_storage_nfs_export', nfs_share)
    tv_config.set('DEFAULT', 'vault_storage_nfs_options', nfs_options)
    tv_config.set('DEFAULT', 'vault_storage_type', 'nfs')
    tv_config.set('DEFAULT', 'vault_data_directory_old', TV_DATA_DIR_OLD)
    tv_config.set('DEFAULT', 'vault_data_directory', TV_DATA_DIR)
    tv_config.set('DEFAULT', 'log_file', '/var/log/nova/tvault-contego.log')
    tv_config.set('DEFAULT', 'debug', False)
    tv_config.set('DEFAULT', 'verbose', True)
    tv_config.set('DEFAULT', 'max_uploads_pending', 3)
    tv_config.set('DEFAULT', 'max_commit_pending', 3)
    tv_config.set('DEFAULT', 'qemu_agent_ping_timeout', 600)
    tv_config.add_section('contego_sys_admin')
    tv_config.set('contego_sys_admin', 'helper_command',
                  'sudo /usr/bin/privsep-helper')
    tv_config.add_section('conductor')
    tv_config.set('conductor', 'use_local', True)

    with open(DATAMOVER_CONF, 'w') as cf:
        tv_config.write(cf)
        return True

    status_set('blocked', 'Failed while writing conf files')
    return False


def ensure_data_dir():
    """
    Ensures all the required directories are present
    and have appropriate permissions.
    """
    usr = DM_EXT_USR
    grp = DM_EXT_GRP
    data_dir = TV_DATA_DIR
    data_dir_old = TV_DATA_DIR_OLD
    # ensure that data_dir is present
    mkdir(data_dir, owner=usr, group=grp, perms=501, force=True)
    # remove data_dir_old
    shutil.rmtree(data_dir_old)
    # recreate the data_dir_old
    mkdir(data_dir_old, owner=usr, group=grp, perms=501, force=True)

    # create logrotate file for tvault-contego.log
    src = 'files/trilio/tvault-contego'
    dest = '/etc/logrotate.d/tvault-contego'
    shutil.copy(src, dest)

    return True


def create_service_file():
    """
    Creates datamover service file.
    """
    usr = DM_EXT_USR
    grp = DM_EXT_GRP
    venv_path = TVAULT_VIRTENV_PATH
    cmd = ['{}/bin/python'.format(venv_path), 'files/trilio/get_nova_conf.py']

    config_files = subprocess.check_output(cmd).decode('utf-8').split('\n')[0]
    config_files = '{} --config-file={}'.format(
        config_files, DATAMOVER_CONF)
    if check_presence('/etc/nova/nova.conf.d'):
        config_files = '{} --config-dir=/etc/nova/nova.conf.d'.format(
            config_files)

    # create service file
    exec_start = '/usr/bin/python /usr/bin/tvault-contego {}\
                 '.format(config_files)
    tv_config = configparser.RawConfigParser()
    tv_config.optionxform = str
    tv_config.add_section('Unit')
    tv_config.add_section('Service')
    tv_config.add_section('Install')
    tv_config.set('Unit', 'Description', 'TrilioVault DataMover')
    tv_config.set('Unit', 'After', 'openstack-nova-compute.service')
    tv_config.set('Service', 'User', usr)
    tv_config.set('Service', 'Group', grp)
    tv_config.set('Service', 'Type', 'simple')
    tv_config.set('Service', 'ExecStart', exec_start)
    tv_config.set('Service', 'TimeoutStopSec', 20)
    tv_config.set('Service', 'KillMode', 'process')
    tv_config.set('Service', 'Restart', 'always')
    tv_config.set('Install', 'WantedBy', 'multi-user.target')

    with open('/etc/systemd/system/tvault-contego.service', 'w') as cf:
        tv_config.write(cf)
        return True
    status_set('blocked', 'Failed while creating DataMover service file')
    return False


def validate_ip(ip):
    """
    Validate triliovault_ip provided by the user
    triliovault_ip should not be blank
    triliovault_ip should have a valid IP address and reachable
    """

    if ip and ip.strip():
        # Not blank
        if netaddr.valid_ipv4(ip):
            try:
                subprocess.check_call(['nc', '-vzw', '1', ip, '8781'])
                return True
            except subprocess.CalledProcessError:
                status_set(
                    'blocked',
                    'Unable to reach TVault appliance')
                return False
            return True
        else:
            status_set(
                'blocked',
                'Invalid IP address, please provide correct IP address')
            return False
    return False


def install_plugin(ip, ver, venv):
    """
    Install TrilioVault DataMover package
    """
    add_source('deb http://{}:8085 deb-repo/'.format(ip))

    try:
        apt_update()
        apt_install(['tvault-contego'],
                    options=['--allow-unauthenticated'], fatal=True)
        log("TrilioVault DataMover package installation passed")

        status_set('maintenance', 'Starting')
        return True
    except Exception as e:
        # Datamover package installation failed
        log("TrilioVault Datamover package installation failed")
        log("With exception --{}".format(e))
        return False


def uninstall_plugin():
    """
    Uninstall TrilioVault DataMover packages
    """
    retry_count = 0
    try:
        path = TVAULT_VIRTENV_PATH
        service_stop('tvault-contego')
        subprocess.check_call(
            ['sudo', 'systemctl', 'disable', 'tvault-contego'])
        os.remove('/etc/systemd/system/tvault-contego.service')
        subprocess.check_call('sudo systemctl daemon-reload')
        shutil.rmtree(path)
        os.remove('/etc/logrotate.d/tvault-contego')
        os.remove(DATAMOVER_CONF)
        os.remove('/var/log/nova/tvault-contego.log')
        # Get the mount points and un-mount tvault's mount points.
        mount_points = mounts()
        sorted_list = [mp[0] for mp in mount_points
                       if TV_DATA_DIR in mp[0]]
        # stopping the tvault-object-store service may take time
        while service_running('tvault-object-store') and retry_count < 3:
            log('Waiting for tvault-object-store service to stop')
            retry_count += 1
            time.sleep(5)

        for sl in sorted_list:
            umount(sl)
        # Uninstall tvault-contego package
        apt_purge(['tvault-contego'])

        log("TrilioVault Datamover package uninstalled successfully")
        return True
    except Exception as e:
        # package uninstallation failed
        log("TrilioVault Datamover package un-installation failed:"
            " {}".format(e))
        return False

#---------------------------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License. See License.txt in the project root for license information.
#---------------------------------------------------------------------------------------------

import argparse
import base64
import socket

from azure.cli.commands.arm import is_valid_resource_id, resource_id
from azure.cli._util import CLIError
from azure.cli.commands.validators import SPECIFIED_SENTINEL
from azure.cli.commands.client_factory import get_subscription_id

# PARAMETER VALIDATORS

def _generate_lb_subproperty_id(
        resource_group, load_balancer_name, child_type, child_name, subscription=None):
    return resource_id(
        subscription=subscription or get_subscription_id(),
        resource_group=resource_group,
        namespace='Microsoft.Network',
        type='loadBalancers',
        name=load_balancer_name,
        child_type=child_type,
        child_name=child_name)

def _generate_lb_id_list_from_names_or_ids(namespace, prop, child_type):
    raw = getattr(namespace, prop)
    if not raw:
        return
    raw = raw if isinstance(raw, list) else [raw]
    result = []
    subscription = get_subscription_id()
    lb_name = namespace.load_balancer_name
    for item in raw:
        if is_valid_resource_id(item):
            result.append({'id': item})
        else:
            if not lb_name:
                raise CLIError('Unable to process {}. Please supply a well-formed ID or '
                               '--lb-name.'.format(item))
            else:
                result.append({'id': _generate_lb_subproperty_id(
                    subscription=subscription,
                    resource_group=namespace.resource_group_name,
                    load_balancer_name=lb_name,
                    child_type=child_type,
                    child_name=item)})
    setattr(namespace, prop, result)

def validate_inbound_nat_rule_id_list(namespace):
    _generate_lb_id_list_from_names_or_ids(
        namespace, 'load_balancer_inbound_nat_rule_ids', 'inboundNatRules')

def validate_address_pool_id_list(namespace):
    _generate_lb_id_list_from_names_or_ids(
        namespace, 'load_balancer_backend_address_pool_ids', 'backendAddressPools')

def validate_inbound_nat_rule_name_or_id(namespace):
    rule_name = namespace.inbound_nat_rule
    lb_name = namespace.load_balancer_name

    if is_valid_resource_id(rule_name):
        if lb_name:
            raise CLIError('Please omit --lb-name when specifying an inbound NAT rule ID.')
    else:
        if not lb_name:
            raise CLIError('Please specify --lb-name when specifying an inbound NAT rule name.')
        namespace.inbound_nat_rule = _generate_lb_subproperty_id(
            resource_group=namespace.resource_group_name,
            load_balancer_name=lb_name,
            child_type='inboundNatRules',
            child_name=rule_name)

def validate_address_pool_name_or_id(namespace):
    pool_name = namespace.backend_address_pool
    lb_name = namespace.load_balancer_name

    if is_valid_resource_id(pool_name):
        if lb_name:
            raise CLIError('Please omit --lb-name when specifying an address pool ID.')
    else:
        if not lb_name:
            raise CLIError('Please specify --lb-name when specifying an address pool name.')
        namespace.backend_address_pool = _generate_lb_subproperty_id(
            resource_group=namespace.resource_group_name,
            load_balancer_name=lb_name,
            child_type='backendAddressPools',
            child_name=pool_name)

def validate_subnet_name_or_id(namespace):
    """ Validates a subnet ID or, if a name is provided, formats it as an ID. """
    if namespace.virtual_network_name is None and namespace.subnet is None:
        return
    if namespace.subnet == '':
        return

    # error if vnet-name is provided without subnet
    if namespace.virtual_network_name and not namespace.subnet:
        raise CLIError('You must specify --subnet name when using --vnet-name.')

    # determine if subnet is name or ID
    is_id = is_valid_resource_id(namespace.subnet)

    # error if vnet-name is provided along with a subnet ID
    if is_id and namespace.virtual_network_name:
        raise argparse.ArgumentError(None, 'Please omit --vnet-name when specifying a subnet ID')
    elif not is_id and not namespace.virtual_network_name:
        raise argparse.ArgumentError(None,
                                     'Please specify --vnet-name when specifying a subnet name')
    if not is_id:
        namespace.subnet = resource_id(
            subscription=get_subscription_id(),
            resource_group=namespace.resource_group_name,
            namespace='Microsoft.Network',
            type='virtualNetworks',
            name=namespace.virtual_network_name,
            child_type='subnets',
            child_name=namespace.subnet)

def validate_private_ip_address(namespace):
    if namespace.private_ip_address:
        namespace.private_ip_address_allocation = 'static'

def validate_public_ip_name_or_id(namespace):
    """ Validates a public IP ID or, if a name is provided, formats it as an ID. """
    if namespace.public_ip_address:
        # determine if public_ip_address is name or ID
        is_id = is_valid_resource_id(namespace.public_ip_address)
        if not is_id:
            namespace.public_ip_address = resource_id(
                subscription=get_subscription_id(),
                resource_group=namespace.resource_group_name,
                namespace='Microsoft.Network',
                type='publicIPAddresses',
                name=namespace.public_ip_address)

def validate_public_ip_type(namespace): # pylint: disable=unused-argument
    if namespace.subnet:
        namespace.public_ip_address_type = 'none'
        if namespace.public_ip_address:
            raise argparse.ArgumentError(
                None, 'Cannot specify --subnet and --public-ip-address when creating a '
                      'load balancer.')

    if namespace.public_ip_address:
        if namespace.public_ip_dns_name and namespace.public_ip_address_type != 'new':
            raise argparse.ArgumentError(
                None, 'Can only specify --public-ip-dns-name when creating a new public '
                      'IP address.')

def validate_nsg_name_or_id(namespace):
    """ Validates a NSG ID or, if a name is provided, formats it as an ID. """
    if namespace.network_security_group:
        # determine if network_security_group is name or ID
        is_id = is_valid_resource_id(namespace.network_security_group)
        if not is_id:
            namespace.network_security_group = resource_id(
                subscription=get_subscription_id(),
                resource_group=namespace.resource_group_name,
                namespace='Microsoft.Network',
                type='networkSecurityGroups',
                name=namespace.network_security_group)

def validate_address_prefixes(namespace):

    subnet_prefix_set = SPECIFIED_SENTINEL in namespace.subnet_address_prefix
    vnet_prefix_set = SPECIFIED_SENTINEL in namespace.vnet_address_prefix
    namespace.subnet_address_prefix = \
        namespace.subnet_address_prefix.replace(SPECIFIED_SENTINEL, '')
    namespace.vnet_address_prefix = namespace.vnet_address_prefix.replace(SPECIFIED_SENTINEL, '')

    if namespace.subnet_type != 'new' and (subnet_prefix_set or vnet_prefix_set):
        raise CLIError('Existing subnet ({}) found. Cannot specify address prefixes when '
                       'reusing an existing subnet.'.format(namespace.subnet))

def validate_servers(namespace):
    servers = []
    for item in namespace.servers if namespace.servers else []:
        try:
            socket.inet_aton(item) #pylint:disable=no-member
            servers.append({'IpAddress': item})
        except socket.error: #pylint:disable=no-member
            servers.append({'Fqdn': item})
    namespace.servers = servers

def validate_cert(namespace):

    params = [namespace.cert_data, namespace.cert_password]
    if all([not x for x in params]):
        # no cert supplied -- use HTTP
        namespace.http_listener_protocol = 'http'
        if not namespace.frontend_port:
            namespace.frontend_port = 80
    else:
        # cert supplied -- use HTTPS
        if not all(params):
            raise argparse.ArgumentError(
                None, 'To use SSL certificate, you must specify both the filename and password')

        # extract the certificate data from the provided file
        with open(namespace.cert_data, 'rb') as f:
            contents = f.read()
            base64_data = base64.b64encode(contents)
            try:
                namespace.cert_data = base64_data.decode('utf-8')
            except UnicodeDecodeError:
                namespace.cert_data = str(base64_data)

        # change default to frontend port 443 for https
        namespace.http_listener_protocol = 'https'
        if not namespace.frontend_port:
            namespace.frontend_port = 443

# COMMAND NAMESPACE VALIDATORS

def process_app_gateway_namespace(namespace):

    if namespace.public_ip:
        namespace.frontend_type = 'publicIp'
    else:
        namespace.frontend_type = 'privateIp'
        namespace.private_ip_address_allocation = 'static' if namespace.private_ip_address \
            else 'dynamic'

    if not namespace.public_ip_type:
        namespace.public_ip_type = 'none'


def process_lb_create_namespace(namespace):
    if namespace.public_ip_dns_name:
        namespace.dns_name_type = 'new'

    if namespace.subnet and namespace.public_ip_address:
        raise argparse.ArgumentError(
            None, 'Must specify a subnet OR a public IP address, not both.')

def process_nic_create_namespace(namespace):
    if namespace.internal_dns_name_label:
        namespace.use_dns_settings = 'true'

    if not namespace.public_ip_address:
        namespace.public_ip_address_type = 'none'

    if not namespace.network_security_group:
        namespace.network_security_group_type = 'none'

def process_public_ip_create_namespace(namespace):
    if namespace.dns_name:
        namespace.public_ip_address_type = 'dns'

# ACTIONS

class markSpecifiedAction(argparse.Action): # pylint: disable=too-few-public-methods
    """ Use this to identify when a parameter is explicitly set by the user (as opposed to a
    default). You must remove the __SET__ sentinel substring in a follow-up validator."""
    def __call__(self, parser, args, values, option_string=None):
        setattr(args, self.dest, '__SET__{}'.format(values))
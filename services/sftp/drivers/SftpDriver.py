from services.Evaluator import Evaluator

import botocore


class SftpDriver(Evaluator):
    # Transfer Family security policies that still allow older ciphers/MACs/KEX.
    LEGACY_SECURITY_POLICIES = [
        'TransferSecurityPolicy-2018-11',
        'TransferSecurityPolicy-2020-06',
        'TransferSecurityPolicy-2022-03',
        'TransferSecurityPolicy-FIPS-2020-06',
        'TransferSecurityPolicy-Restricted-2018-11',
        'TransferSecurityPolicy-Restricted-2020-06',
    ]

    # Upper bound on describe_user calls per server, to keep scans fast.
    MAX_USERS_INSPECTED = 100

    def __init__(self, server, transfer_client):
        self.server = server
        self.transfer_client = transfer_client
        self.__config_prefix = 'sftp::'

        self.results = {}

        self._resourceName = server['ServerId']

        self.init()

    # ---------------- Security ----------------

    def _checkPublicEndpoint(self):
        endpoint_type = self.server.get('EndpointType', 'PUBLIC')
        if endpoint_type == 'PUBLIC':
            self.results['PublicEndpoint'] = [-1, 'PUBLIC']
        else:
            self.results['PublicEndpoint'] = [1, endpoint_type]

    def _checkInsecureProtocols(self):
        protocols = self.server.get('Protocols', [])
        if 'FTP' in protocols:
            self.results['FtpEnabled'] = [-1, ', '.join(protocols)]
        else:
            self.results['FtpEnabled'] = [1, ', '.join(protocols)]

    def _checkSecurityPolicy(self):
        policy = self.server.get('SecurityPolicyName')
        if not policy:
            return

        if policy in self.LEGACY_SECURITY_POLICIES:
            self.results['SecurityPolicy'] = [-1, policy]
        else:
            self.results['SecurityPolicy'] = [1, policy]

    def _checkLogging(self):
        has_role = bool(self.server.get('LoggingRole'))
        has_structured = bool(self.server.get('StructuredLogDestinations'))

        if has_role or has_structured:
            self.results['Logging'] = [1, 'Enabled']
        else:
            self.results['Logging'] = [-1, 'Disabled']

    def _checkEndpointSecurityGroups(self):
        # Only VPC-hosted endpoints have security groups
        if self.server.get('EndpointType') != 'VPC':
            return

        endpoint_details = self.server.get('EndpointDetails') or {}
        if endpoint_details.get('SecurityGroupIds'):
            self.results['VpcSecurityGroups'] = [1, 'Configured']
        else:
            self.results['VpcSecurityGroups'] = [-1, 'None']

    def _checkFtpsCertificate(self):
        if 'FTPS' not in self.server.get('Protocols', []):
            return

        if self.server.get('Certificate'):
            self.results['FtpsCertificate'] = [1, 'Configured']
        else:
            self.results['FtpsCertificate'] = [-1, 'Missing']

    def _checkIdentityProvider(self):
        idp = self.server.get('IdentityProviderType')
        if not idp:
            return

        if idp == 'SERVICE_MANAGED':
            self.results['ServiceManagedIdentity'] = [-1, idp]
        else:
            self.results['ServiceManagedIdentity'] = [1, idp]

    def _checkLoginBanner(self):
        if self.server.get('PreAuthenticationLoginBanner'):
            self.results['LoginBanner'] = [1, 'Configured']
        else:
            self.results['LoginBanner'] = [-1, 'Not configured']

    def _checkUserHomeDirectory(self):
        # User records are only managed in Transfer Family for SERVICE_MANAGED servers
        if self.server.get('IdentityProviderType') != 'SERVICE_MANAGED':
            return
        if not self.server.get('UserCount'):
            return

        server_id = self.server['ServerId']
        inspected = 0
        non_logical = 0

        try:
            paginator = self.transfer_client.get_paginator('list_users')
            for page in paginator.paginate(ServerId=server_id):
                for user in page.get('Users', []):
                    if inspected >= self.MAX_USERS_INSPECTED:
                        break
                    inspected += 1

                    detail = self.transfer_client.describe_user(
                        ServerId=server_id,
                        UserName=user['UserName']
                    )
                    home_type = detail['User'].get('HomeDirectoryType', 'PATH')
                    if home_type != 'LOGICAL':
                        non_logical += 1
                if inspected >= self.MAX_USERS_INSPECTED:
                    break
        except botocore.exceptions.ClientError as e:
            print("(Not showstopper): Error during transfer list_users/describe_user {}".format(e.response['Error']['Code']))
            return

        if inspected == 0:
            return

        if non_logical > 0:
            self.results['UserHomeDirectory'] = [-1, '{} of {} users not using logical home directory'.format(non_logical, inspected)]
        else:
            self.results['UserHomeDirectory'] = [1, 'All users use logical home directories']

    # ---------------- Reliability ----------------

    def _checkMultiAzEndpoint(self):
        if self.server.get('EndpointType') != 'VPC':
            return

        endpoint_details = self.server.get('EndpointDetails') or {}
        subnet_ids = endpoint_details.get('SubnetIds', [])
        if not subnet_ids:
            return

        if len(subnet_ids) < 2:
            self.results['SingleAzEndpoint'] = [-1, '{} subnet'.format(len(subnet_ids))]
        else:
            self.results['SingleAzEndpoint'] = [1, '{} subnets'.format(len(subnet_ids))]

    # ---------------- Cost Optimization ----------------

    def _checkNoUsers(self):
        if self.server.get('IdentityProviderType') != 'SERVICE_MANAGED':
            return

        if self.server.get('UserCount', 0) == 0:
            self.results['NoUsers'] = [-1, 'No users']
        else:
            self.results['NoUsers'] = [1, '{} users'.format(self.server['UserCount'])]

    def _checkMultipleProtocols(self):
        protocols = self.server.get('Protocols', [])
        if len(protocols) > 1:
            self.results['MultipleProtocols'] = [-1, ', '.join(protocols)]
        else:
            self.results['MultipleProtocols'] = [1, ', '.join(protocols)]

    def _checkServerOffline(self):
        state = self.server.get('State')
        if state in ['OFFLINE', 'STOPPED']:
            self.results['ServerOffline'] = [-1, state]

    # ---------------- Performance ----------------

    def _checkDirectoryListingOptimization(self):
        if self.server.get('Domain') != 'S3':
            return

        s3_options = self.server.get('S3StorageOptions') or {}
        if s3_options.get('DirectoryListingOptimization') == 'ENABLED':
            self.results['DirectoryListing'] = [1, 'Enabled']
        else:
            self.results['DirectoryListing'] = [-1, 'Disabled']

    # ---------------- Operational Excellence ----------------

    def _checkResourceTags(self):
        if self.server.get('Tags'):
            self.results['ResourceTags'] = [1, 'Tagged']
        else:
            self.results['ResourceTags'] = [-1, 'No tags']

    def _checkStructuredLogging(self):
        if self.server.get('StructuredLogDestinations'):
            self.results['StructuredLogging'] = [1, 'Enabled']
        else:
            self.results['StructuredLogging'] = [-1, 'Not configured']

import botocore
from services.Evaluator import Evaluator

class ControltowerAccount(Evaluator):
    def __init__(self, ctClient, orgClient):
        super().__init__()
        self.ctClient = ctClient
        self.orgClient = orgClient
        self._resourceName = 'ControlTower::Account'
        self.init()

    def _checkLandingZoneExists(self):
        try:
            resp = self.ctClient.list_landing_zones()
            zones = resp.get('landingZones', [])
            if not zones:
                self.results['CTNoLandingZone'] = [-1, 'No Control Tower landing zone found']
                return
            # Check for drift
            for zone in zones:
                detail = self.ctClient.get_landing_zone(landingZoneIdentifier=zone.get('arn'))
                lz = detail.get('landingZone', {})
                status = lz.get('driftStatus', {}).get('status', '')
                if status == 'DRIFTED':
                    self.results['CTLandingZoneDrifted'] = [-1, 'Landing zone has drifted from expected configuration']
        except botocore.exceptions.ClientError as e:
            if 'AccessDeniedException' in str(e):
                self.results['CTAccessDenied'] = [0, 'Insufficient permissions to check Control Tower']

    def _checkEnabledControls(self):
        try:
            resp = self.ctClient.list_enabled_controls(targetIdentifier='')
            controls = resp.get('enabledControls', [])
            if len(controls) < 5:
                self.results['CTFewControlsEnabled'] = [0, f'Only {len(controls)} controls enabled — review coverage']
        except botocore.exceptions.ClientError:
            pass

    def _checkOrganizationExists(self):
        try:
            resp = self.orgClient.describe_organization()
            org = resp.get('Organization', {})
            if org.get('FeatureSet') != 'ALL':
                self.results['CTOrgNotAllFeatures'] = [-1, 'Organization is not using all features — required for Control Tower']
        except botocore.exceptions.ClientError as e:
            if 'AWSOrganizationsNotInUseException' in str(e):
                self.results['CTNoOrganization'] = [-1, 'AWS Organizations is not enabled']

    def _checkSecurityOU(self):
        try:
            root_resp = self.orgClient.list_roots()
            roots = root_resp.get('Roots', [])
            if not roots:
                return
            root_id = roots[0]['Id']
            paginator = self.orgClient.get_paginator('list_organizational_units_for_parent')
            found_security = False
            for page in paginator.paginate(ParentId=root_id):
                for ou in page.get('OrganizationalUnits', []):
                    if 'security' in ou.get('Name', '').lower():
                        found_security = True
                        break
            if not found_security:
                self.results['CTNoSecurityOU'] = [0, 'No Security OU found — recommended for Control Tower']
        except botocore.exceptions.ClientError:
            pass

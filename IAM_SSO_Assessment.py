import boto3
import pandas as pd
from datetime import datetime, timezone
import os
import time
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

ROLE_NAME = 'CrossAccountReadOnlyRole'

def get_downloads_path():
    return os.path.join(os.path.expanduser('~'), 'Downloads')

def get_child_accounts():
    org_client = boto3.client('organizations')
    accounts = []
    try:
        paginator = org_client.get_paginator('list_accounts')
        for page in paginator.paginate():
            for account in page['Accounts']:
                if account['Status'] == 'ACTIVE':
                    accounts.append({'Id': account['Id'], 'Name': account['Name']})
    except Exception as e:
        print(f"Error listing accounts: {str(e)}")
    return accounts

def assume_role(account_id):
    sts_client = boto3.client('sts')
    try:
        response = sts_client.assume_role(
            RoleArn=f'arn:aws:iam::{account_id}:role/{ROLE_NAME}',
            RoleSessionName=f'IAMAssessment-{account_id}'
        )
        credentials = response['Credentials']
        return boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
    except Exception as e:
        print(f"Error assuming role in account {account_id}: {str(e)}")
        return None

def get_security_contact_info(session):
    try:
        account_client = session.client('account')
        response = account_client.get_alternate_contact(AlternateContactType='SECURITY')
        contact_info = {
            'Name': response.get('AlternateContact', {}).get('Name', 'Not Set'),
            'Title': response.get('AlternateContact', {}).get('Title', 'Not Set'),
            'Email': response.get('AlternateContact', {}).get('EmailAddress', 'Not Set'),
            'Phone': response.get('AlternateContact', {}).get('PhoneNumber', 'Not Set')
        }
        contact_info['Security_Contact_Configured'] = all(v != 'Not Set' for v in contact_info.values())
        return contact_info
    except Exception as e:
        print(f"Error getting security contact: {str(e)}")
        return {'Name': 'Not Set', 'Title': 'Not Set', 'Email': 'Not Set',
                'Phone': 'Not Set', 'Security_Contact_Configured': False}

def check_console_access(iam_client, username):
    try:
        iam_client.get_login_profile(UserName=username)
        return True
    except iam_client.exceptions.NoSuchEntityException:
        return False
    except Exception:
        return False

def get_user_groups(iam_client, username):
    try:
        groups = iam_client.list_groups_for_user(UserName=username)
        group_names = [g['GroupName'] for g in groups['Groups']]
        return ', '.join(group_names) if group_names else 'No Groups'
    except Exception:
        return 'Error retrieving groups'

def get_user_privileges_separated(iam_client, username):
    inline_policies = []
    managed_policies = []
    try:
        user_inline = iam_client.list_user_policies(UserName=username)
        for policy_name in user_inline['PolicyNames']:
            inline_policies.append(f"User: {policy_name}")
        user_managed = iam_client.list_attached_user_policies(UserName=username)
        for policy in user_managed['AttachedPolicies']:
            managed_policies.append(f"User: {policy['PolicyName']}")
        groups = iam_client.list_groups_for_user(UserName=username)
        for group in groups['Groups']:
            group_name = group['GroupName']
            group_inline = iam_client.list_group_policies(GroupName=group_name)
            for policy_name in group_inline['PolicyNames']:
                inline_policies.append(f"Group({group_name}): {policy_name}")
            group_managed = iam_client.list_attached_group_policies(GroupName=group_name)
            for policy in group_managed['AttachedPolicies']:
                managed_policies.append(f"Group({group_name}): {policy['PolicyName']}")
        return {
            'inline': '\n'.join(inline_policies) if inline_policies else 'None',
            'managed': '\n'.join(managed_policies) if managed_policies else 'None'
        }
    except Exception:
        return {'inline': 'Error', 'managed': 'Error'}

def get_detailed_service_last_accessed(iam_client, username):
    try:
        user_arn = iam_client.get_user(UserName=username)['User']['Arn']
        response = iam_client.generate_service_last_accessed_details(Arn=user_arn)
        job_id = response['JobId']
        for _ in range(15):
            report = iam_client.get_service_last_accessed_details(JobId=job_id)
            if report['JobStatus'] == 'COMPLETED':
                service_details = []
                for service in report.get('ServicesLastAccessed', []):
                    ns = service.get('ServiceNamespace', 'Unknown')
                    if 'LastAuthenticated' in service:
                        last = service['LastAuthenticated']
                        days = (datetime.now(timezone.utc) - last).days
                        service_details.append(f"{ns}: {last.strftime('%Y-%m-%d')} ({days} days ago)")
                    else:
                        service_details.append(f"{ns}: Never accessed")
                return '\n'.join(service_details) if service_details else 'No services tracked'
            time.sleep(1)
        return 'Report timeout'
    except Exception:
        return 'Error retrieving'

def check_admin_access(iam_client, username):
    try:
        attached = iam_client.list_attached_user_policies(UserName=username)
        for policy in attached['AttachedPolicies']:
            if 'AdministratorAccess' in policy['PolicyName']:
                return True
        groups = iam_client.list_groups_for_user(UserName=username)
        for group in groups['Groups']:
            group_policies = iam_client.list_attached_group_policies(GroupName=group['GroupName'])
            for policy in group_policies['AttachedPolicies']:
                if 'AdministratorAccess' in policy['PolicyName']:
                    return True
        return False
    except Exception:
        return False

def get_iam_details_for_account(session, account_id, account_name):
    try:
        iam_client = session.client('iam')
        iam_results = []
        security_contact = get_security_contact_info(session)
        try:
            password_policy = iam_client.get_account_password_policy()['PasswordPolicy']
            password_length_compliant = password_policy.get('MinimumPasswordLength', 0) >= 14
            password_expiry_compliant = 0 < password_policy.get('MaxPasswordAge', 0) <= 90
            password_reuse_compliant = password_policy.get('PasswordReusePrevention', 0) >= 4
        except Exception:
            password_length_compliant = False
            password_expiry_compliant = False
            password_reuse_compliant = False

        paginator = iam_client.get_paginator('list_users')
        for page in paginator.paginate():
            for user in page['Users']:
                username = user['UserName']
                print(f"  Processing IAM user: {username}")
                try:
                    has_console_access = check_console_access(iam_client, username)
                except Exception:
                    has_console_access = 'Error'
                try:
                    group_membership = get_user_groups(iam_client, username)
                except Exception:
                    group_membership = 'Error'
                try:
                    privileges = get_user_privileges_separated(iam_client, username)
                except Exception:
                    privileges = {'inline': 'Error', 'managed': 'Error'}
                try:
                    service_access_details = get_detailed_service_last_accessed(iam_client, username)
                except Exception:
                    service_access_details = 'Error retrieving'
                try:
                    has_admin_access = check_admin_access(iam_client, username)
                except Exception:
                    has_admin_access = 'Error'
                try:
                    mfa_devices = iam_client.list_mfa_devices(UserName=username)
                    mfa_enabled = len(mfa_devices['MFADevices']) > 0
                except Exception:
                    mfa_enabled = 'Error'
                try:
                    key_paginator = iam_client.get_paginator('list_access_keys')
                    access_keys = []
                    for key_page in key_paginator.paginate(UserName=username):
                        access_keys.extend(key_page['AccessKeyMetadata'])
                except Exception:
                    access_keys = []

                base_data = {
                    'Account_ID': account_id,
                    'Account_Name': account_name,
                    'UserName': username,
                    'Group_Membership': group_membership,
                    'Inline_Policies': privileges['inline'],
                    'Managed_Policies': privileges['managed'],
                    'Services_Last_Accessed_Details': service_access_details,
                    'Has_Admin_Access': has_admin_access,
                    'MFA_Enabled': mfa_enabled,
                    'Has_Console_Access': has_console_access,
                    'Password_Length_Compliant': password_length_compliant,
                    'Password_Expiry_Compliant': password_expiry_compliant,
                    'Password_Reuse_Compliant': password_reuse_compliant,
                    'Security_Contact_Configured': security_contact['Security_Contact_Configured'],
                    'Security_Contact_Name': security_contact['Name'],
                    'Security_Contact_Title': security_contact['Title'],
                    'Security_Contact_Email': security_contact['Email'],
                    'Security_Contact_Phone': security_contact['Phone']
                }
                if not access_keys:
                    iam_results.append({
                        **base_data,
                        'AccessKeyID': 'No Access Key',
                        'AccessKey_Status': 'N/A',
                        'AccessKey_Age_Days': 0,
                        'AccessKey_Rotation_Compliant': True,
                        'LastUsedDate': 'N/A',
                        'Days_Since_Last_Used': 'N/A'
                    })
                for key in access_keys:
                    key_id = key['AccessKeyId']
                    key_status = key['Status']
                    key_age = (datetime.now(timezone.utc) - key['CreateDate']).days
                    try:
                        last_used = iam_client.get_access_key_last_used(AccessKeyId=key_id)
                        last_used_date_obj = last_used.get('AccessKeyLastUsed', {}).get('LastUsedDate')
                        if last_used_date_obj:
                            last_used_date = last_used_date_obj.strftime('%Y-%m-%d')
                            days_since_last_used = (datetime.now(timezone.utc) - last_used_date_obj).days
                        else:
                            last_used_date = 'Never used'
                            days_since_last_used = 'Never used'
                    except Exception:
                        last_used_date = 'Error retrieving'
                        days_since_last_used = 'Error retrieving'
                    iam_results.append({
                        **base_data,
                        'AccessKeyID': key_id,
                        'AccessKey_Status': key_status,
                        'AccessKey_Age_Days': key_age,
                        'AccessKey_Rotation_Compliant': key_age <= 90,
                        'LastUsedDate': last_used_date,
                        'Days_Since_Last_Used': days_since_last_used
                    })
        return iam_results
    except Exception as e:
        print(f"  [ERROR] IAM scan failed for account {account_id}: {str(e)}")
        return []


# ============================================================
# SSO / IAM Identity Center functions
# ============================================================

def get_sso_instance():
    """Get the IAM Identity Center instance ARN and Identity Store ID"""
    sso_admin = boto3.client('sso-admin')
    try:
        resp = sso_admin.list_instances()
        instances = resp.get('Instances', [])
        if not instances:
            print("No IAM Identity Center instance found.")
            return None, None, None
        instance = instances[0]
        return instance['InstanceArn'], instance['IdentityStoreId'], sso_admin
    except Exception as e:
        print(f"Error getting SSO instance: {str(e)}")
        return None, None, None


def get_all_sso_users(identity_store_id):
    """Get all SSO users from the Identity Store"""
    ids_client = boto3.client('identitystore')
    users = []
    try:
        paginator = ids_client.get_paginator('list_users')
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            users.extend(page.get('Users', []))
    except Exception as e:
        print(f"Error listing SSO users: {str(e)}")
    return users, ids_client


def get_sso_user_groups(ids_client, identity_store_id, user_id):
    """Get all groups the SSO user belongs to"""
    groups = []
    try:
        paginator = ids_client.get_paginator('list_group_memberships_for_member')
        for page in paginator.paginate(
            IdentityStoreId=identity_store_id,
            MemberId={'UserId': user_id}
        ):
            for membership in page.get('GroupMemberships', []):
                group_id = membership['GroupId']
                try:
                    grp = ids_client.describe_group(
                        IdentityStoreId=identity_store_id,
                        GroupId=group_id
                    )
                    groups.append(grp.get('DisplayName', group_id))
                except Exception:
                    groups.append(group_id)
    except Exception as e:
        print(f"  Error getting groups for SSO user: {str(e)}")
    return groups


def get_permission_set_details(sso_admin, instance_arn, permission_set_arn):
    """Get full details of a permission set including managed + inline policies"""
    details = {}
    try:
        resp = sso_admin.describe_permission_set(
            InstanceArn=instance_arn,
            PermissionSetArn=permission_set_arn
        )
        ps = resp.get('PermissionSet', {})
        details['Name'] = ps.get('Name', 'Unknown')
        details['Description'] = ps.get('Description', '')
        details['SessionDuration'] = ps.get('SessionDuration', '')
        details['RelayState'] = ps.get('RelayState', '')

        # Managed policies attached to permission set
        managed = []
        try:
            pag = sso_admin.get_paginator('list_managed_policies_in_permission_set')
            for page in pag.paginate(InstanceArn=instance_arn, PermissionSetArn=permission_set_arn):
                for p in page.get('AttachedManagedPolicies', []):
                    managed.append(p.get('Name', p.get('Arn', '')))
        except Exception:
            pass
        details['ManagedPolicies'] = '\n'.join(managed) if managed else 'None'

        # Customer managed policies
        customer_managed = []
        try:
            pag = sso_admin.get_paginator('list_customer_managed_policy_references_in_permission_set')
            for page in pag.paginate(InstanceArn=instance_arn, PermissionSetArn=permission_set_arn):
                for p in page.get('CustomerManagedPolicyReferences', []):
                    customer_managed.append(p.get('Name', ''))
        except Exception:
            pass
        details['CustomerManagedPolicies'] = '\n'.join(customer_managed) if customer_managed else 'None'

        # Inline policy
        try:
            inline_resp = sso_admin.get_inline_policy_for_permission_set(
                InstanceArn=instance_arn,
                PermissionSetArn=permission_set_arn
            )
            details['InlinePolicy'] = inline_resp.get('InlinePolicy', 'None') or 'None'
        except Exception:
            details['InlinePolicy'] = 'None'

        # Check if admin access
        details['HasAdminAccess'] = 'AdministratorAccess' in details['ManagedPolicies']

    except Exception as e:
        details['Name'] = permission_set_arn.split('/')[-1]
        details['Error'] = str(e)
    return details


def get_user_account_assignments(sso_admin, instance_arn, identity_store_id, user_id, accounts):
    """Get all account assignments for an SSO user (direct + via groups)"""
    assignments = []

    # Build account ID → name map
    account_map = {a['Id']: a['Name'] for a in accounts}

    # Get all permission sets in the instance
    all_permission_sets = []
    try:
        pag = sso_admin.get_paginator('list_permission_sets')
        for page in pag.paginate(InstanceArn=instance_arn):
            all_permission_sets.extend(page.get('PermissionSets', []))
    except Exception as e:
        print(f"  Error listing permission sets: {str(e)}")

    for account_id, account_name in account_map.items():
        for ps_arn in all_permission_sets:
            try:
                # Check direct user assignment
                pag = sso_admin.get_paginator('list_account_assignments')
                for page in pag.paginate(
                    InstanceArn=instance_arn,
                    AccountId=account_id,
                    PermissionSetArn=ps_arn
                ):
                    for assignment in page.get('AccountAssignments', []):
                        if (assignment.get('PrincipalType') == 'USER' and
                                assignment.get('PrincipalId') == user_id):
                            ps_details = get_permission_set_details(sso_admin, instance_arn, ps_arn)
                            assignments.append({
                                'Account_ID': account_id,
                                'Account_Name': account_name,
                                'Assignment_Type': 'Direct (User)',
                                'PermissionSet_Name': ps_details.get('Name', ''),
                                'PermissionSet_ARN': ps_arn,
                                'SessionDuration': ps_details.get('SessionDuration', ''),
                                'ManagedPolicies': ps_details.get('ManagedPolicies', ''),
                                'CustomerManagedPolicies': ps_details.get('CustomerManagedPolicies', ''),
                                'InlinePolicy': ps_details.get('InlinePolicy', ''),
                                'HasAdminAccess': ps_details.get('HasAdminAccess', False)
                            })
            except Exception:
                pass

    return assignments


def get_all_sso_user_details(instance_arn, identity_store_id, sso_admin, accounts):
    """Build full SSO user details including groups, account assignments, permissions"""
    print("\n=== Collecting IAM Identity Center (SSO) User Details ===")
    ids_client = boto3.client('identitystore')
    sso_results = []

    users, ids_client = get_all_sso_users(identity_store_id)
    print(f"Found {len(users)} SSO users")

    for user in users:
        user_id = user.get('UserId')
        username = user.get('UserName', '')

        # Basic profile
        display_name = user.get('DisplayName', '')
        first_name = ''
        last_name = ''
        for name in user.get('Name', {}).items() if isinstance(user.get('Name'), dict) else []:
            pass
        name_obj = user.get('Name', {})
        if isinstance(name_obj, dict):
            first_name = name_obj.get('GivenName', '')
            last_name = name_obj.get('FamilyName', '')

        # Primary email
        emails = user.get('Emails', [])
        primary_email = ''
        for email in emails:
            if email.get('Primary', False):
                primary_email = email.get('Value', '')
                break
        if not primary_email and emails:
            primary_email = emails[0].get('Value', '')

        # Phone
        phones = user.get('PhoneNumbers', [])
        phone = phones[0].get('Value', '') if phones else ''

        # Active status
        active = user.get('Active', True)

        # Title / department
        title = user.get('Title', '')
        dept = user.get('Department', '')
        org = user.get('Organization', '')

        print(f"  Processing SSO user: {username} ({display_name})")

        # Groups
        groups = get_sso_user_groups(ids_client, identity_store_id, user_id)

        # Account assignments + permissions
        assignments = get_user_account_assignments(
            sso_admin, instance_arn, identity_store_id, user_id, accounts
        )

        base = {
            'User_ID': user_id,
            'UserName': username,
            'Display_Name': display_name,
            'First_Name': first_name,
            'Last_Name': last_name,
            'Primary_Email': primary_email,
            'Phone': phone,
            'Title': title,
            'Department': dept,
            'Organization': org,
            'Active': active,
            'SSO_Groups': '\n'.join(groups) if groups else 'No Groups',
            'Group_Count': len(groups)
        }

        if not assignments:
            sso_results.append({
                **base,
                'Assigned_Account_ID': 'No Account Assignments',
                'Assigned_Account_Name': '',
                'Assignment_Type': '',
                'PermissionSet_Name': '',
                'PermissionSet_ARN': '',
                'SessionDuration': '',
                'ManagedPolicies': '',
                'CustomerManagedPolicies': '',
                'InlinePolicy': '',
                'HasAdminAccess': False
            })
        else:
            for assignment in assignments:
                sso_results.append({
                    **base,
                    'Assigned_Account_ID': assignment['Account_ID'],
                    'Assigned_Account_Name': assignment['Account_Name'],
                    'Assignment_Type': assignment['Assignment_Type'],
                    'PermissionSet_Name': assignment['PermissionSet_Name'],
                    'PermissionSet_ARN': assignment['PermissionSet_ARN'],
                    'SessionDuration': assignment['SessionDuration'],
                    'ManagedPolicies': assignment['ManagedPolicies'],
                    'CustomerManagedPolicies': assignment['CustomerManagedPolicies'],
                    'InlinePolicy': assignment['InlinePolicy'],
                    'HasAdminAccess': assignment['HasAdminAccess']
                })

    return sso_results


def format_excel(ws):
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.border = thin_border
        cell.alignment = Alignment(horizontal='center')
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center', wrap_text=True)


def auto_fit_columns(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                val = str(cell.value) if cell.value else ''
                line_max = max((len(line) for line in val.split('\n')), default=0)
                if line_max > max_len:
                    max_len = line_max
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 60)


def main():
    print("=== IAM + SSO Identity Center Security Assessment ===")
    print("=" * 70)

    accounts = get_child_accounts()
    if not accounts:
        print("No accounts found.")
        return
    print(f"Found {len(accounts)} accounts.")

    sts_client = boto3.client('sts')
    mgmt_account_id = sts_client.get_caller_identity()['Account']

    # ── IAM Users (existing logic) ──────────────────────────────────────
    all_iam_data = []
    for account in accounts:
        account_id = account['Id']
        account_name = account['Name']
        print(f"\nScanning IAM for account: {account_name} ({account_id})")
        if account_id == mgmt_account_id:
            session = boto3.Session()
        else:
            session = assume_role(account_id)
        if session:
            results = get_iam_details_for_account(session, account_id, account_name)
            all_iam_data.extend(results)
        else:
            print(f"  Skipped - could not assume role")

    # ── SSO / Identity Center Users ────────────────────────────────────
    instance_arn, identity_store_id, sso_admin = get_sso_instance()
    all_sso_data = []
    if instance_arn:
        all_sso_data = get_all_sso_user_details(
            instance_arn, identity_store_id, sso_admin, accounts
        )
    else:
        print("Skipping SSO assessment — no Identity Center instance found.")

    # ── Write Excel ─────────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"IAM_SSO_Security_Assessment_{timestamp}.xlsx"
    output_path = os.path.join(get_downloads_path(), filename)

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:

        # Sheet 1 — IAM Users
        if all_iam_data:
            df_iam = pd.DataFrame(all_iam_data)
            df_iam.to_excel(writer, index=False, sheet_name='IAM Users')
            ws_iam = writer.sheets['IAM Users']
            format_excel(ws_iam)
            auto_fit_columns(ws_iam)

        # Sheet 2 — SSO Users Full Details
        if all_sso_data:
            df_sso = pd.DataFrame(all_sso_data)
            df_sso.to_excel(writer, index=False, sheet_name='SSO Users - Full Details')
            ws_sso = writer.sheets['SSO Users - Full Details']
            format_excel(ws_sso)
            auto_fit_columns(ws_sso)

        # Sheet 3 — SSO Admin Access Summary
        if all_sso_data:
            admin_rows = [r for r in all_sso_data if r.get('HasAdminAccess')]
            if admin_rows:
                df_admin = pd.DataFrame(admin_rows)[[
                    'UserName', 'Display_Name', 'Primary_Email',
                    'Assigned_Account_Name', 'Assigned_Account_ID',
                    'PermissionSet_Name', 'ManagedPolicies', 'SSO_Groups'
                ]]
                df_admin.to_excel(writer, index=False, sheet_name='SSO Admin Access')
                ws_admin = writer.sheets['SSO Admin Access']
                format_excel(ws_admin)
                auto_fit_columns(ws_admin)

        # Sheet 4 — SSO Users with No Assignments
        if all_sso_data:
            no_assign = [r for r in all_sso_data if r.get('Assigned_Account_ID') == 'No Account Assignments']
            if no_assign:
                df_no = pd.DataFrame(no_assign)[[
                    'UserName', 'Display_Name', 'Primary_Email',
                    'Active', 'SSO_Groups', 'Department', 'Title'
                ]]
                df_no.to_excel(writer, index=False, sheet_name='SSO Unassigned Users')
                ws_no = writer.sheets['SSO Unassigned Users']
                format_excel(ws_no)
                auto_fit_columns(ws_no)

    print(f"\n{'='*70}")
    print(f"Report saved to: {output_path}")
    print(f"IAM users found: {len(all_iam_data)}")
    print(f"SSO users found: {len(set(r['UserName'] for r in all_sso_data)) if all_sso_data else 0}")
    print(f"SSO assignment rows: {len(all_sso_data)}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

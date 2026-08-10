"""
SSO / IAM Identity Center User Assessment
==========================================
Runs from the management account.
Fetches all Identity Center users with:
  - Full profile (name, email, phone, title, department)
  - Group memberships
  - Account assignments (which accounts they can access)
  - Permission sets (managed policies, customer managed, inline, session duration)
  - Admin access flag

Output: Excel file with 4 sheets saved to Downloads folder
"""

import boto3
import pandas as pd
from datetime import datetime
import os
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment


# ── Helpers ────────────────────────────────────────────────────────────

def get_downloads_path():
    return os.path.join(os.path.expanduser('~'), 'Downloads')


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
        cell.alignment = Alignment(horizontal='center', vertical='center')
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='left', vertical='top', wrap_text=True)


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
        ws.column_dimensions[col_letter].width = min(max_len + 4, 65)


# ── AWS Org accounts ───────────────────────────────────────────────────

def get_all_accounts():
    """Get all active accounts from AWS Organizations"""
    org_client = boto3.client('organizations')
    accounts = []
    try:
        paginator = org_client.get_paginator('list_accounts')
        for page in paginator.paginate():
            for account in page['Accounts']:
                if account['Status'] == 'ACTIVE':
                    accounts.append({'Id': account['Id'], 'Name': account['Name']})
        print(f"Found {len(accounts)} active accounts in the organization.")
    except Exception as e:
        print(f"[WARN] Could not list org accounts: {str(e)}")
        print("       Will still fetch SSO users but account names may be missing.")
        # fallback: use management account only
        sts = boto3.client('sts')
        mgmt_id = sts.get_caller_identity()['Account']
        accounts = [{'Id': mgmt_id, 'Name': 'Management Account'}]
    return accounts


# ── Identity Center instance ───────────────────────────────────────────

def get_sso_instance():
    sso_admin = boto3.client('sso-admin')
    try:
        resp = sso_admin.list_instances()
        instances = resp.get('Instances', [])
        if not instances:
            print("[ERROR] No IAM Identity Center instance found in this account.")
            return None, None, None
        instance = instances[0]
        print(f"Identity Center instance: {instance['InstanceArn']}")
        return instance['InstanceArn'], instance['IdentityStoreId'], sso_admin
    except Exception as e:
        print(f"[ERROR] Could not get SSO instance: {str(e)}")
        return None, None, None


# ── SSO Users ──────────────────────────────────────────────────────────

def get_all_sso_users(identity_store_id):
    ids_client = boto3.client('identitystore')
    users = []
    try:
        paginator = ids_client.get_paginator('list_users')
        for page in paginator.paginate(IdentityStoreId=identity_store_id):
            users.extend(page.get('Users', []))
        print(f"Found {len(users)} SSO users in Identity Center.")
    except Exception as e:
        print(f"[ERROR] Could not list SSO users: {str(e)}")
    return users, ids_client


def get_user_groups(ids_client, identity_store_id, user_id):
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
        print(f"  [WARN] Could not get groups for user {user_id}: {str(e)}")
    return groups


# ── Permission Sets ────────────────────────────────────────────────────

def get_all_permission_sets(sso_admin, instance_arn):
    """Cache all permission set ARNs"""
    ps_list = []
    try:
        pag = sso_admin.get_paginator('list_permission_sets')
        for page in pag.paginate(InstanceArn=instance_arn):
            ps_list.extend(page.get('PermissionSets', []))
    except Exception as e:
        print(f"[WARN] Could not list permission sets: {str(e)}")
    return ps_list


def get_permission_set_details(sso_admin, instance_arn, ps_arn, ps_cache):
    """Get permission set details, using cache to avoid repeated API calls"""
    if ps_arn in ps_cache:
        return ps_cache[ps_arn]

    details = {
        'Name': ps_arn.split('/')[-1],
        'Description': '',
        'SessionDuration': '',
        'ManagedPolicies': 'None',
        'CustomerManagedPolicies': 'None',
        'InlinePolicy': 'None',
        'HasAdminAccess': False
    }

    try:
        resp = sso_admin.describe_permission_set(
            InstanceArn=instance_arn,
            PermissionSetArn=ps_arn
        )
        ps = resp.get('PermissionSet', {})
        details['Name'] = ps.get('Name', details['Name'])
        details['Description'] = ps.get('Description', '')
        details['SessionDuration'] = ps.get('SessionDuration', '')

        # AWS Managed Policies
        managed = []
        try:
            pag = sso_admin.get_paginator('list_managed_policies_in_permission_set')
            for page in pag.paginate(InstanceArn=instance_arn, PermissionSetArn=ps_arn):
                for p in page.get('AttachedManagedPolicies', []):
                    managed.append(p.get('Name', p.get('Arn', '')))
        except Exception:
            pass
        details['ManagedPolicies'] = '\n'.join(managed) if managed else 'None'

        # Customer Managed Policies
        customer = []
        try:
            pag = sso_admin.get_paginator('list_customer_managed_policy_references_in_permission_set')
            for page in pag.paginate(InstanceArn=instance_arn, PermissionSetArn=ps_arn):
                for p in page.get('CustomerManagedPolicyReferences', []):
                    customer.append(p.get('Name', ''))
        except Exception:
            pass
        details['CustomerManagedPolicies'] = '\n'.join(customer) if customer else 'None'

        # Inline Policy
        try:
            inline_resp = sso_admin.get_inline_policy_for_permission_set(
                InstanceArn=instance_arn,
                PermissionSetArn=ps_arn
            )
            details['InlinePolicy'] = inline_resp.get('InlinePolicy') or 'None'
        except Exception:
            details['InlinePolicy'] = 'None'

        details['HasAdminAccess'] = 'AdministratorAccess' in details['ManagedPolicies']

    except Exception as e:
        print(f"  [WARN] Could not describe permission set {ps_arn}: {str(e)}")

    ps_cache[ps_arn] = details
    return details


# ── Account Assignments ────────────────────────────────────────────────

def get_user_assignments(sso_admin, instance_arn, user_id, accounts, ps_list, ps_cache):
    """Get all account+permission set assignments for a specific user"""
    assignments = []
    account_map = {a['Id']: a['Name'] for a in accounts}

    for account_id, account_name in account_map.items():
        for ps_arn in ps_list:
            try:
                pag = sso_admin.get_paginator('list_account_assignments')
                for page in pag.paginate(
                    InstanceArn=instance_arn,
                    AccountId=account_id,
                    PermissionSetArn=ps_arn
                ):
                    for assignment in page.get('AccountAssignments', []):
                        if (assignment.get('PrincipalType') == 'USER' and
                                assignment.get('PrincipalId') == user_id):
                            ps_details = get_permission_set_details(
                                sso_admin, instance_arn, ps_arn, ps_cache)
                            assignments.append({
                                'Account_ID': account_id,
                                'Account_Name': account_name,
                                'Assignment_Type': 'Direct (User)',
                                'PermissionSet_Name': ps_details['Name'],
                                'PermissionSet_Description': ps_details['Description'],
                                'SessionDuration': ps_details['SessionDuration'],
                                'ManagedPolicies': ps_details['ManagedPolicies'],
                                'CustomerManagedPolicies': ps_details['CustomerManagedPolicies'],
                                'InlinePolicy': ps_details['InlinePolicy'],
                                'HasAdminAccess': ps_details['HasAdminAccess']
                            })
            except Exception:
                pass
    return assignments


# ── Main collector ─────────────────────────────────────────────────────

def collect_sso_users(instance_arn, identity_store_id, sso_admin, accounts):
    print("\n--- Collecting SSO user details ---")
    results = []

    users, ids_client = get_all_sso_users(identity_store_id)
    ps_list  = get_all_permission_sets(sso_admin, instance_arn)
    ps_cache = {}  # shared cache to avoid redundant API calls

    print(f"Permission sets found: {len(ps_list)}")
    print(f"Accounts in scope   : {len(accounts)}")
    print()

    for idx, user in enumerate(users, 1):
        user_id      = user.get('UserId', '')
        username     = user.get('UserName', '')
        display_name = user.get('DisplayName', '')

        name_obj   = user.get('Name', {}) or {}
        first_name = name_obj.get('GivenName', '')
        last_name  = name_obj.get('FamilyName', '')

        emails        = user.get('Emails', []) or []
        primary_email = next((e.get('Value', '') for e in emails if e.get('Primary')),
                             emails[0].get('Value', '') if emails else '')

        phones = user.get('PhoneNumbers', []) or []
        phone  = phones[0].get('Value', '') if phones else ''

        active = user.get('Active', True)
        title  = user.get('Title', '')
        dept   = user.get('Department', '')
        org    = user.get('Organization', '')

        print(f"  [{idx}/{len(users)}] {username} ({display_name})")

        # Groups
        groups = get_user_groups(ids_client, identity_store_id, user_id)

        # Account assignments
        assignments = get_user_assignments(
            sso_admin, instance_arn, user_id, accounts, ps_list, ps_cache
        )

        base = {
            'User_ID'       : user_id,
            'UserName'      : username,
            'Display_Name'  : display_name,
            'First_Name'    : first_name,
            'Last_Name'     : last_name,
            'Primary_Email' : primary_email,
            'Phone'         : phone,
            'Title'         : title,
            'Department'    : dept,
            'Organization'  : org,
            'Active'        : active,
            'SSO_Groups'    : '\n'.join(groups) if groups else 'No Groups',
            'Group_Count'   : len(groups),
        }

        if not assignments:
            results.append({
                **base,
                'Assigned_Account_ID'         : 'No Account Assignments',
                'Assigned_Account_Name'       : '',
                'Assignment_Type'             : '',
                'PermissionSet_Name'          : '',
                'PermissionSet_Description'   : '',
                'SessionDuration'             : '',
                'ManagedPolicies'             : '',
                'CustomerManagedPolicies'     : '',
                'InlinePolicy'               : '',
                'HasAdminAccess'             : False,
            })
        else:
            for a in assignments:
                results.append({
                    **base,
                    'Assigned_Account_ID'       : a['Account_ID'],
                    'Assigned_Account_Name'     : a['Account_Name'],
                    'Assignment_Type'           : a['Assignment_Type'],
                    'PermissionSet_Name'        : a['PermissionSet_Name'],
                    'PermissionSet_Description' : a['PermissionSet_Description'],
                    'SessionDuration'           : a['SessionDuration'],
                    'ManagedPolicies'           : a['ManagedPolicies'],
                    'CustomerManagedPolicies'   : a['CustomerManagedPolicies'],
                    'InlinePolicy'             : a['InlinePolicy'],
                    'HasAdminAccess'           : a['HasAdminAccess'],
                })

    return results


# ── Excel writer ───────────────────────────────────────────────────────

def write_excel(all_data, output_path):
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:

        # Sheet 1 — All SSO Users with full details
        df = pd.DataFrame(all_data)
        df.to_excel(writer, index=False, sheet_name='SSO Users - Full Details')
        ws = writer.sheets['SSO Users - Full Details']
        format_excel(ws)
        auto_fit_columns(ws)

        # Sheet 2 — Admin access only
        admin_rows = [r for r in all_data if r.get('HasAdminAccess')]
        if admin_rows:
            df_admin = pd.DataFrame(admin_rows)[[
                'UserName', 'Display_Name', 'Primary_Email', 'Active',
                'Assigned_Account_Name', 'Assigned_Account_ID',
                'PermissionSet_Name', 'ManagedPolicies', 'SSO_Groups'
            ]]
            df_admin.to_excel(writer, index=False, sheet_name='SSO Admin Access')
            ws = writer.sheets['SSO Admin Access']
            format_excel(ws)
            auto_fit_columns(ws)

        # Sheet 3 — Users with no account assignments
        no_assign = [r for r in all_data
                     if r.get('Assigned_Account_ID') == 'No Account Assignments']
        if no_assign:
            df_no = pd.DataFrame(no_assign)[[
                'UserName', 'Display_Name', 'Primary_Email',
                'Active', 'SSO_Groups', 'Department', 'Title'
            ]]
            df_no.to_excel(writer, index=False, sheet_name='SSO Unassigned Users')
            ws = writer.sheets['SSO Unassigned Users']
            format_excel(ws)
            auto_fit_columns(ws)

        # Sheet 4 — Summary per user (unique users, total accounts assigned)
        unique_users = {}
        for r in all_data:
            uname = r['UserName']
            if uname not in unique_users:
                unique_users[uname] = {
                    'UserName'      : uname,
                    'Display_Name'  : r['Display_Name'],
                    'Primary_Email' : r['Primary_Email'],
                    'Active'        : r['Active'],
                    'Title'         : r['Title'],
                    'Department'    : r['Department'],
                    'SSO_Groups'    : r['SSO_Groups'],
                    'Accounts_Assigned': 0,
                    'Permission_Sets'  : set(),
                    'HasAdminAccess'   : False,
                }
            if r.get('Assigned_Account_ID') != 'No Account Assignments':
                unique_users[uname]['Accounts_Assigned'] += 1
                if r.get('PermissionSet_Name'):
                    unique_users[uname]['Permission_Sets'].add(r['PermissionSet_Name'])
            if r.get('HasAdminAccess'):
                unique_users[uname]['HasAdminAccess'] = True

        summary_rows = []
        for u in unique_users.values():
            summary_rows.append({
                'UserName'          : u['UserName'],
                'Display_Name'      : u['Display_Name'],
                'Primary_Email'     : u['Primary_Email'],
                'Active'            : u['Active'],
                'Title'             : u['Title'],
                'Department'        : u['Department'],
                'SSO_Groups'        : u['SSO_Groups'],
                'Accounts_Assigned' : u['Accounts_Assigned'],
                'Permission_Sets'   : '\n'.join(sorted(u['Permission_Sets'])) if u['Permission_Sets'] else 'None',
                'HasAdminAccess'    : u['HasAdminAccess'],
            })

        df_summary = pd.DataFrame(summary_rows)
        df_summary.to_excel(writer, index=False, sheet_name='SSO User Summary')
        ws = writer.sheets['SSO User Summary']
        format_excel(ws)
        auto_fit_columns(ws)

    print(f"\nReport saved to: {output_path}")


# ── Entry point ────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  SSO / IAM Identity Center User Assessment")
    print("  Running from Management Account")
    print("=" * 65)

    # Get org accounts (needed to check assignments across all accounts)
    accounts = get_all_accounts()

    # Get Identity Center instance
    instance_arn, identity_store_id, sso_admin = get_sso_instance()
    if not instance_arn:
        print("\n[ERROR] Cannot proceed — no Identity Center instance found.")
        return

    # Collect all SSO user data
    all_data = collect_sso_users(instance_arn, identity_store_id, sso_admin, accounts)

    if not all_data:
        print("\nNo SSO user data collected.")
        return

    # Write Excel report
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename    = f"SSO_Users_Assessment_{timestamp}.xlsx"
    output_path = os.path.join(get_downloads_path(), filename)
    write_excel(all_data, output_path)

    # Summary
    unique_users = len(set(r['UserName'] for r in all_data))
    admin_users  = len(set(r['UserName'] for r in all_data if r.get('HasAdminAccess')))
    no_assign    = len(set(r['UserName'] for r in all_data
                          if r.get('Assigned_Account_ID') == 'No Account Assignments'))

    print(f"\n{'=' * 65}")
    print(f"  Total SSO users          : {unique_users}")
    print(f"  Users with admin access  : {admin_users}")
    print(f"  Users with no assignment : {no_assign}")
    print(f"  Total assignment rows    : {len(all_data)}")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()

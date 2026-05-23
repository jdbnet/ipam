# ── Imports ───────────────────────────────────────────────────────────────────
import os
import re
import csv
import json
import shutil
import hashlib
import base64
import secrets
import logging
from io import StringIO, BytesIO
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse
from ipaddress import ip_network, ip_address, IPv4Address, IPv6Address

import pyotp
import qrcode
import mysql.connector
from dotenv import load_dotenv
from flask import (
    Flask, session, request, abort, jsonify, redirect,
    send_from_directory, send_file, current_app,
)
from werkzeug.utils import safe_join

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()
logging.basicConfig(level=logging.INFO)

# ── Config & app creation ─────────────────────────────────────────────────────
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'changeme')
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'user')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', 'password')
app.config['MYSQL_DATABASE'] = os.environ.get('MYSQL_DATABASE', 'ipam')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['NAME'] = os.environ.get('NAME', 'JDB-NET')
app.config['LOGO_PNG'] = os.environ.get('LOGO_PNG', 'https://assets.jdbnet.co.uk/logo/128x128.png')
app.config['VERSION'] = os.environ.get('VERSION', 'unknown')

from db import init_db, hash_password, get_db_connection, verify_password, generate_api_key

# ── TOTP / 2FA helpers ───────────────────────────────────────────────────────
def generate_totp_secret():
    """Generate a new TOTP secret"""
    return pyotp.random_base32()

def get_totp_uri(secret, email, issuer_name="IPAM"):
    """Generate TOTP URI for QR code"""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(
        name=email,
        issuer_name=issuer_name
    )

def generate_qr_code(uri):
    """Generate QR code image from URI"""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

def verify_totp(secret, code):
    """Verify a TOTP code"""
    if not secret or not code:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(code, valid_window=1)  # Allow 1 time step window for clock skew
    except Exception:
        return False

def generate_backup_codes(count=10):
    """Generate backup codes for 2FA"""
    return [secrets.token_urlsafe(8).upper() for _ in range(count)]

def verify_backup_code(backup_codes_json, code):
    """Verify a backup code and remove it if valid"""
    if not backup_codes_json or not code:
        return False, None
    
    try:
        codes = json.loads(backup_codes_json)
        code_upper = code.upper().strip()
        if code_upper in codes:
            codes.remove(code_upper)
            return True, json.dumps(codes) if codes else None
        return False, None
    except (json.JSONDecodeError, AttributeError):
        return False, None

def format_backup_codes(codes):
    """Format backup codes for display (group in pairs)"""
    formatted = []
    for i in range(0, len(codes), 2):
        if i + 1 < len(codes):
            formatted.append(f"{codes[i]}  {codes[i+1]}")
        else:
            formatted.append(codes[i])
    return formatted

# ── Auth & permissions ────────────────────────────────────────────────────────

def _api_key_from_request():
    if 'X-API-Key' in request.headers:
        return request.headers['X-API-Key']
    if 'api_key' in request.args:
        return request.args.get('api_key')
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def load_permissions_for_user(user_id, conn):
    """Return the set of permission names granted to a user via their role."""
    cursor = conn.cursor()
    cursor.execute('SELECT role_id FROM User WHERE id = %s', (user_id,))
    role_result = cursor.fetchone()
    if not role_result or not role_result[0]:
        return set()
    cursor.execute('''
        SELECT p.name FROM RolePermission rp
        JOIN Permission p ON rp.permission_id = p.id
        WHERE rp.role_id = %s
    ''', (role_result[0],))
    return {row[0] for row in cursor.fetchall()}


def _user_record_from_row(row, conn):
    user = {
        'id': row[0],
        'name': row[1],
        'email': row[2],
        'role_id': row[3],
    }
    user['permissions'] = load_permissions_for_user(user['id'], conn)
    return user


def get_user_from_api_key(api_key):
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, email, role_id FROM User WHERE api_key = %s', (api_key,))
        result = cursor.fetchone()
        if result:
            return _user_record_from_row(result, conn)
    return None


def establish_user_session(user_id, conn=None):
    """Populate session after successful authentication."""
    close_conn = False
    if conn is None:
        conn = get_db_connection(current_app)
        close_conn = True
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT name, email FROM User WHERE id = %s', (user_id,))
        row = cursor.fetchone()
        session['user_name'] = row[0] if row else ''
        session['user_email'] = row[1] if row else ''
        session['permissions'] = list(load_permissions_for_user(user_id, conn))
        session['logged_in'] = True
        session['user_id'] = user_id
        session.modified = True
    finally:
        if close_conn:
            conn.close()


def resolve_auth():
    """Return authenticated user dict or None (session or API key)."""
    if session.get('logged_in') and session.get('user_id'):
        return {
            'id': session['user_id'],
            'name': session.get('user_name', ''),
            'email': session.get('user_email', ''),
            'permissions': set(session.get('permissions', [])),
            'auth_type': 'session',
        }
    api_key = _api_key_from_request()
    if api_key:
        user = get_user_from_api_key(api_key)
        if user:
            user['auth_type'] = 'api_key'
            return user
    return None


def current_user():
    return getattr(request, 'current_user', None)


def has_permission(permission_name, user=None):
    user = user or current_user()
    if not user:
        return False
    perms = user.get('permissions')
    if isinstance(perms, set):
        return permission_name in perms
    if isinstance(perms, list):
        return permission_name in perms
    return False


def require_permission(permission_name):
    """Decorator: session cookie or API key; enforces RBAC permission."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = resolve_auth()
            if not user:
                return jsonify({'error': 'Unauthorized'}), 401
            if permission_name and not has_permission(permission_name, user):
                return jsonify({'error': 'Permission denied', 'permission': permission_name}), 403
            request.current_user = user
            response = f(*args, **kwargs)
            if user.get('auth_type') == 'api_key' and request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
                try:
                    status_code = response.status_code if hasattr(response, 'status_code') else (
                        response[1] if isinstance(response, tuple) and len(response) > 1 else None
                    )
                    details = f"API call: {request.method} {request.path}"
                    if status_code:
                        details += f" (Status: {status_code})"
                    add_audit_log(user['id'], 'api_usage', details, subnet_id=None)
                except Exception as e:
                    logging.error(f"Failed to log API usage: {e}")
            return response
        return decorated_function
    return decorator


def require_auth(f):
    """Decorator: authenticated only (no specific permission)."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = resolve_auth()
        if not user:
            return jsonify({'error': 'Unauthorized'}), 401
        request.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def json_body():
    return request.get_json(silent=True) or {}


def items_response(items):
    return jsonify({'items': items})


def build_audit_filters():
    """Build WHERE clause and params for audit log queries from request args."""
    clauses = []
    params = []
    user = request.args.get('user', '').strip()
    if user:
        clauses.append('u.name LIKE %s')
        params.append(f'%{user}%')
    action = request.args.get('action', '').strip()
    if action:
        clauses.append('al.action = %s')
        params.append(action)
    from_date = request.args.get('from', '').strip()
    if from_date:
        clauses.append('al.timestamp >= %s')
        params.append(f'{from_date} 00:00:00')
    to_date = request.args.get('to', '').strip()
    if to_date:
        clauses.append('al.timestamp <= %s')
        params.append(f'{to_date} 23:59:59')
    where_sql = ('WHERE ' + ' AND '.join(clauses)) if clauses else ''
    return where_sql, params


def get_current_user_id():
    user = current_user()
    return user['id'] if user else session.get('user_id')

def add_audit_log(user_id, action, details=None, subnet_id=None, conn=None):
    import datetime
    close_conn = False
    if conn is None:
        from flask import current_app
        conn = get_db_connection(current_app)
        close_conn = True
    cursor = conn.cursor()
    utc_now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    cursor.execute('''INSERT INTO AuditLog (user_id, action, details, subnet_id, timestamp) VALUES (%s, %s, %s, %s, %s)''',
                   (user_id, action, details, subnet_id, utc_now))
    if close_conn:
        conn.commit()
        conn.close()


def get_ip_history_from_audit_logs(device_id=None, ip_address=None, conn=None):
    """
    Extract IP assignment history from audit logs.
    Returns a list of history entries sorted by timestamp (newest first).
    Each entry contains: ip, action, device_name, subnet_name, subnet_cidr, user_name, timestamp
    """
    import re
    close_conn = False
    if conn is None:
        from flask import current_app
        conn = get_db_connection(current_app)
        close_conn = True
    
    try:
        cursor = conn.cursor(dictionary=True)

        device_name = None
        if device_id:
            cursor.execute('SELECT name FROM Device WHERE id = %s', (device_id,))
            device_result = cursor.fetchone()
            if device_result:
                device_name = device_result['name']
            else:
                return []

        query = '''
            SELECT al.id, al.action, al.details, al.timestamp,
                   COALESCE(u.name, 'Deleted User') as user_name,
                   s.name as subnet_name, s.cidr as subnet_cidr
            FROM AuditLog al
            LEFT JOIN User u ON al.user_id = u.id
            LEFT JOIN Subnet s ON al.subnet_id = s.id
            WHERE (al.action = 'device_add_ip' OR al.action = 'device_delete_ip')
        '''
        params = []

        if ip_address:
            query += ' AND al.details LIKE %s'
            params.append(f'%IP {ip_address}%')

        if device_id and device_name:
            query += ' AND al.details LIKE %s'
            params.append(f'%device {device_name}%')
        
        query += ' ORDER BY al.timestamp DESC'
        
        cursor.execute(query, params)
        logs = cursor.fetchall()
        
        history = []
        # Pattern to extract IP, subnet info, and device name from audit log details
        # Format: "Assigned IP 192.168.1.1 (SubnetName 192.168.1.0/24) to device DeviceName"
        # Format: "Removed IP 192.168.1.1 (SubnetName 192.168.1.0/24) from device DeviceName"
        ip_pattern = r'IP\s+([\d\.]+)'
        device_pattern = r'(?:to|from)\s+device\s+([^\s]+)'
        
        for log in logs:
            details = log['details'] or ''
            
            # Extract IP address
            ip_match = re.search(ip_pattern, details)
            if not ip_match:
                continue
            
            extracted_ip = ip_match.group(1)
            
            # If filtering by specific IP, skip if it doesn't match
            if ip_address and extracted_ip != ip_address:
                continue
            
            # Extract device name
            device_match = re.search(device_pattern, details)
            extracted_device_name = device_match.group(1) if device_match else 'Unknown'
            
            # If filtering by device_id, verify device name matches
            if device_id and device_name:
                if extracted_device_name != device_name:
                    continue
            
            history.append({
                'ip': extracted_ip,
                'action': 'assigned' if log['action'] == 'device_add_ip' else 'removed',
                'device_name': extracted_device_name,
                'subnet_name': log['subnet_name'] or 'Unknown',
                'subnet_cidr': log['subnet_cidr'] or '',
                'user_name': log['user_name'],
                'timestamp': log['timestamp']
            })
        
        return history
    finally:
        if close_conn:
            conn.close()


def validate_custom_field_value(field_def, value):
    """
    Validate a custom field value against its field definition.
    Returns (is_valid, error_message)
    """
    if value is None or value == '':
        if field_def.get('required', False):
            return False, f"{field_def.get('name', 'Field')} is required"
        return True, None
    
    field_type = field_def.get('field_type', 'text')
    validation_rules = field_def.get('validation_rules')
    
    # Parse validation rules if it's a JSON string
    if isinstance(validation_rules, str):
        try:
            validation_rules = json.loads(validation_rules)
        except json.JSONDecodeError:
            validation_rules = {}
    elif validation_rules is None:
        validation_rules = {}
    
    # Type-specific validation
    if field_type == 'ip_address':
        try:
            ip_address(value)
        except ValueError:
            return False, f"Invalid IP address format: {value}"
    
    elif field_type == 'email':
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, value):
            return False, f"Invalid email format: {value}"
    
    elif field_type == 'url':
        try:
            result = urlparse(value)
            if not all([result.scheme, result.netloc]):
                return False, f"Invalid URL format: {value}"
        except Exception:
            return False, f"Invalid URL format: {value}"
    
    elif field_type == 'date':
        try:
            datetime.strptime(value, '%Y-%m-%d')
        except ValueError:
            return False, f"Invalid date format. Expected YYYY-MM-DD: {value}"
    
    elif field_type == 'datetime':
        try:
            datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return False, f"Invalid datetime format. Expected ISO format: {value}"
    
    elif field_type == 'number':
        try:
            int(value)
        except ValueError:
            return False, f"Invalid integer: {value}"
        if 'min_value' in validation_rules:
            if int(value) < validation_rules['min_value']:
                return False, f"Value must be at least {validation_rules['min_value']}"
        if 'max_value' in validation_rules:
            if int(value) > validation_rules['max_value']:
                return False, f"Value must be at most {validation_rules['max_value']}"
    
    elif field_type == 'decimal':
        try:
            float(value)
        except ValueError:
            return False, f"Invalid decimal number: {value}"
        if 'min_value' in validation_rules:
            if float(value) < validation_rules['min_value']:
                return False, f"Value must be at least {validation_rules['min_value']}"
        if 'max_value' in validation_rules:
            if float(value) > validation_rules['max_value']:
                return False, f"Value must be at most {validation_rules['max_value']}"
    
    elif field_type == 'boolean':
        if value not in [True, False, 'true', 'false', '1', '0', 1, 0]:
            return False, f"Invalid boolean value: {value}"
    
    elif field_type == 'select':
        if 'select_options' in validation_rules:
            if value not in validation_rules['select_options']:
                return False, f"Value must be one of: {', '.join(validation_rules['select_options'])}"
    
    # Text length validation (applies to text, textarea, and string-based types)
    if field_type in ['text', 'textarea', 'ip_address', 'email', 'url']:
        if 'min_length' in validation_rules:
            if len(str(value)) < validation_rules['min_length']:
                return False, f"Value must be at least {validation_rules['min_length']} characters"
        if 'max_length' in validation_rules:
            if len(str(value)) > validation_rules['max_length']:
                return False, f"Value must be at most {validation_rules['max_length']} characters"
    
    # Regex pattern validation
    if 'regex_pattern' in validation_rules:
        try:
            if not re.match(validation_rules['regex_pattern'], str(value)):
                return False, f"Value does not match required pattern"
        except re.error:
            # Invalid regex pattern, skip validation
            pass
    
    return True, None

def parse_custom_field_value(field_type, raw_value):
    """Parse and normalize a custom field value based on its type"""
    if raw_value is None or raw_value == '':
        return None
    
    if field_type == 'number':
        try:
            return int(raw_value)
        except ValueError:
            return None
    elif field_type == 'decimal':
        try:
            return float(raw_value)
        except ValueError:
            return None
    elif field_type == 'boolean':
        if isinstance(raw_value, bool):
            return raw_value
        if str(raw_value).lower() in ['true', '1', 'yes']:
            return True
        if str(raw_value).lower() in ['false', '0', 'no']:
            return False
        return None
    elif field_type in ['date', 'datetime']:
        # Return as string, validation ensures format
        return str(raw_value)
    else:
        # text, textarea, ip_address, email, url, select
        return str(raw_value)

def validate_vlan_id(vlan_id_str):
    """
    Validate VLAN ID. Must be integer between 1-4094 (standard VLAN range).
    Returns (is_valid, error_message, vlan_id_int)
    """
    if vlan_id_str is None or vlan_id_str == '':
        return True, None, None
    
    try:
        vlan_id = int(vlan_id_str)
        if vlan_id < 1 or vlan_id > 4094:
            return False, "VLAN ID must be between 1 and 4094", None
        return True, None, vlan_id
    except ValueError:
        return False, "VLAN ID must be a valid integer", None

def get_custom_fields_for_entity(entity_type, entity_id, conn=None):
    """
    Retrieve custom field definitions with their values for an entity.
    Returns list of dicts with field definition and current value.
    """
    close_conn = False
    if conn is None:
        from flask import current_app
        conn = get_db_connection(current_app)
        close_conn = True
    
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get field definitions for this entity type
        cursor.execute('''
            SELECT id, entity_type, name, field_key, field_type, required, 
                   default_value, help_text, display_order, validation_rules
            FROM CustomFieldDefinition
            WHERE entity_type = %s
            ORDER BY display_order, name
        ''', (entity_type,))
        field_defs = cursor.fetchall()
        
        # Get current values from entity table
        table_name = 'Device' if entity_type == 'device' else 'Subnet'
        cursor.execute(f'SELECT custom_fields FROM {table_name} WHERE id = %s', (entity_id,))
        result = cursor.fetchone()
        
        current_values = {}
        if result and result.get('custom_fields'):
            try:
                current_values = json.loads(result['custom_fields'])
            except (json.JSONDecodeError, TypeError):
                current_values = {}
        
        # Merge definitions with values
        fields_with_values = []
        for field_def in field_defs:
            field_key = field_def['field_key']
            current_value = current_values.get(field_key)
            
            # Use default value if no current value
            if current_value is None and field_def.get('default_value'):
                current_value = field_def['default_value']
            
            # Parse validation_rules if it's a JSON string
            validation_rules = field_def.get('validation_rules')
            if isinstance(validation_rules, str):
                try:
                    validation_rules = json.loads(validation_rules)
                except (json.JSONDecodeError, TypeError):
                    validation_rules = {}
            elif validation_rules is None:
                validation_rules = {}
            
            field_def['current_value'] = current_value
            field_def['validation_rules'] = validation_rules
            fields_with_values.append(field_def)
        
        return fields_with_values
    finally:
        if close_conn:
            conn.close()

# ── Data helpers (queries & business logic) ───────────────────────────────────

def get_subnet_utilization(cursor, subnet_id, include_available=False):
    """Return utilization stats for a single subnet."""
    cursor.execute('SELECT COUNT(*) FROM IPAddress WHERE subnet_id = %s', (subnet_id,))
    total_ips = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(*) FROM IPAddress ip
        INNER JOIN DeviceIPAddress dia ON ip.id = dia.ip_id
        WHERE ip.subnet_id = %s
    ''', (subnet_id,))
    assigned_ips = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(*) FROM IPAddress ip
        LEFT JOIN DeviceIPAddress dia ON ip.id = dia.ip_id
        WHERE ip.subnet_id = %s AND ip.hostname = 'DHCP' AND dia.ip_id IS NULL
    ''', (subnet_id,))
    dhcp_ips = cursor.fetchone()[0]

    used_ips = assigned_ips + dhcp_ips
    utilization_percent = (used_ips / total_ips * 100) if total_ips > 0 else 0
    stats = {
        'total': total_ips,
        'assigned': assigned_ips,
        'dhcp': dhcp_ips,
        'used': used_ips,
        'percent': round(utilization_percent, 1),
    }
    if include_available:
        stats['available'] = total_ips - assigned_ips - dhcp_ips
    return stats


def get_all_subnet_utilizations(cursor):
    """Return utilization stats keyed by subnet_id."""
    cursor.execute('''
        SELECT ip.subnet_id,
               COUNT(*) AS total,
               SUM(CASE WHEN dia.ip_id IS NOT NULL THEN 1 ELSE 0 END) AS assigned,
               SUM(CASE WHEN dia.ip_id IS NULL AND ip.hostname = 'DHCP' THEN 1 ELSE 0 END) AS dhcp
        FROM IPAddress ip
        LEFT JOIN DeviceIPAddress dia ON ip.id = dia.ip_id
        GROUP BY ip.subnet_id
    ''')
    result = {}
    for row in cursor.fetchall():
        if isinstance(row, dict):
            subnet_id = row['subnet_id']
            total = int(row['total'])
            assigned = int(row['assigned'])
            dhcp = int(row['dhcp'])
        else:
            subnet_id, total, assigned, dhcp = row
            total = int(total)
            assigned = int(assigned)
            dhcp = int(dhcp)
        used = assigned + dhcp
        result[subnet_id] = {
            'total': total,
            'assigned': assigned,
            'dhcp': dhcp,
            'used': used,
            'percent': round((used / total * 100) if total > 0 else 0, 1),
        }
    return result


def get_dhcp_pool(cursor, subnet_id):
    cursor.execute(
        'SELECT start_ip, end_ip, excluded_ips FROM DHCPPool WHERE subnet_id = %s',
        (subnet_id,),
    )
    return cursor.fetchone()


def is_ip_dhcp_reserved(cursor, subnet_id, ip):
    dhcp_row = get_dhcp_pool(cursor, subnet_id)
    if not dhcp_row:
        return False
    start_ip, end_ip, excluded_ips = dhcp_row
    excluded_list = [x for x in (excluded_ips or '').replace(' ', '').split(',') if x]
    if ip in excluded_list:
        return False
    in_range = False
    cursor.execute(
        'SELECT ip FROM IPAddress WHERE subnet_id = %s ORDER BY INET_ATON(ip)',
        (subnet_id,),
    )
    for (pool_ip,) in cursor.fetchall():
        if pool_ip == start_ip:
            in_range = True
        if in_range and pool_ip not in excluded_list and pool_ip == ip:
            return True
        if pool_ip == end_ip:
            in_range = False
    return False


def filter_ips_outside_dhcp(cursor, subnet_id, ips):
    """Filter list of {id, ip} dicts, removing IPs inside DHCP pool range."""
    dhcp_row = get_dhcp_pool(cursor, subnet_id)
    if not dhcp_row:
        return ips
    start_ip, end_ip, excluded_ips = dhcp_row
    excluded_list = [x for x in (excluded_ips or '').replace(' ', '').split(',') if x]
    in_range = False
    filtered = []
    for ip_obj in ips:
        ip = ip_obj['ip']
        if ip == start_ip:
            in_range = True
        if ip in excluded_list or not (in_range and ip not in excluded_list):
            filtered.append(ip_obj)
        if ip == end_ip:
            in_range = False
    return filtered


def get_subnet_name_cidr(cursor, subnet_id):
    cursor.execute('SELECT name, cidr FROM Subnet WHERE id = %s', (subnet_id,))
    row = cursor.fetchone()
    return (row[0], row[1]) if row else (None, None)


def get_device_name(cursor, device_id):
    cursor.execute('SELECT name FROM Device WHERE id = %s', (device_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def normalize_site(site):
    return site if site else 'Unassigned'


def assign_ip_to_device(conn, device_id, ip_id, user_id):
    """Assign an IP to a device. Raises ValueError on failure."""
    cursor = conn.cursor()
    cursor.execute('SELECT ip, subnet_id FROM IPAddress WHERE id = %s', (ip_id,))
    ip_row = cursor.fetchone()
    if not ip_row:
        raise ValueError('IP not found')
    ip, subnet_id = ip_row[0], ip_row[1]

    cursor.execute('SELECT site FROM Subnet WHERE id = %s', (subnet_id,))
    subnet_row = cursor.fetchone()
    if not subnet_row:
        raise ValueError('Subnet not found')
    new_site = normalize_site(subnet_row[0])

    cursor.execute('''
        SELECT DISTINCT s.site
        FROM DeviceIPAddress dia
        JOIN IPAddress ip ON dia.ip_id = ip.id
        JOIN Subnet s ON ip.subnet_id = s.id
        WHERE dia.device_id = %s
    ''', (device_id,))
    existing_sites = {normalize_site(row[0]) for row in cursor.fetchall()}
    if existing_sites and new_site not in existing_sites:
        if len(existing_sites) == 1:
            home = next(iter(existing_sites))
            raise ValueError(
                f'Device is homed at site "{home}"; cannot assign an IP from site "{new_site}"'
            )
        raise ValueError(
            f'Device already has IPs at other sites; cannot assign an IP from site "{new_site}"'
        )

    cursor.execute('SELECT id FROM DeviceIPAddress WHERE ip_id = %s', (ip_id,))
    if cursor.fetchone():
        raise ValueError('IP already assigned')

    if is_ip_dhcp_reserved(cursor, subnet_id, ip):
        raise ValueError('IP is reserved for DHCP')

    device_name = get_device_name(cursor, device_id)
    if not device_name:
        raise ValueError('Device not found')

    subnet_name, subnet_cidr = get_subnet_name_cidr(cursor, subnet_id)
    cursor.execute(
        'INSERT INTO DeviceIPAddress (device_id, ip_id) VALUES (%s, %s)',
        (device_id, ip_id),
    )
    cursor.execute('UPDATE IPAddress SET hostname = %s WHERE id = %s', (device_name, ip_id))
    details = f"Assigned IP {ip} ({subnet_name} {subnet_cidr}) to device {device_name}"
    add_audit_log(user_id, 'device_add_ip', details, subnet_id, conn=conn)
    return ip


def remove_ip_from_device(conn, device_ip_id, user_id):
    """Remove an IP assignment. Returns (ip, device_name) or raises ValueError."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT dia.device_id, ip.ip, ip.subnet_id, d.name
        FROM DeviceIPAddress dia
        JOIN IPAddress ip ON dia.ip_id = ip.id
        JOIN Device d ON dia.device_id = d.id
        WHERE dia.id = %s
    ''', (device_ip_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError('Assignment not found')
    _device_id, ip, subnet_id, device_name = row
    subnet_name, subnet_cidr = get_subnet_name_cidr(cursor, subnet_id)
    cursor.execute('DELETE FROM DeviceIPAddress WHERE id = %s', (device_ip_id,))
    cursor.execute('UPDATE IPAddress SET hostname = NULL WHERE ip = %s', (ip,))
    details = f"Removed IP {ip} ({subnet_name} {subnet_cidr}) from device {device_name}"
    add_audit_log(user_id, 'device_delete_ip', details, subnet_id, conn=conn)
    return ip, device_name


def delete_device_record(conn, device_id, user_id):
    """Delete device and clear IP hostnames. Returns device name or None."""
    cursor = conn.cursor()
    cursor.execute('SELECT name FROM Device WHERE id = %s', (device_id,))
    device_row = cursor.fetchone()
    if not device_row:
        return None
    device_name = device_row[0]
    add_audit_log(user_id, 'delete_device', f"Deleted device {device_name}", conn=conn)
    cursor.execute('SELECT ip_id FROM DeviceIPAddress WHERE device_id = %s', (device_id,))
    ip_ids = [row[0] for row in cursor.fetchall()]
    if ip_ids:
        cursor.executemany('UPDATE IPAddress SET hostname = NULL WHERE id = %s', [(i,) for i in ip_ids])
    cursor.execute('DELETE FROM DeviceIPAddress WHERE device_id = %s', (device_id,))
    cursor.execute('DELETE FROM Device WHERE id = %s', (device_id,))
    return device_name


def create_subnet_from_cidr(conn, name, cidr, site, vlan_id, vlan_description, vlan_notes, user_id):
    """Create subnet and populate IPAddress rows. Returns subnet_id."""
    network = ip_network(cidr, strict=False)
    if network.prefixlen < 24:
        raise ValueError('Subnet must be /24 or smaller')
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO Subnet (name, cidr, site, vlan_id, vlan_description, vlan_notes)
           VALUES (%s, %s, %s, %s, %s, %s)''',
        (name, cidr, site, vlan_id, vlan_description or None, vlan_notes or None),
    )
    subnet_id = cursor.lastrowid
    hosts = list(network.hosts())
    if hosts:
        cursor.executemany(
            'INSERT INTO IPAddress (ip, subnet_id) VALUES (%s, %s)',
            [(str(h), subnet_id) for h in hosts],
        )
    add_audit_log(user_id, 'add_subnet', f"Added subnet {name} ({cidr})", subnet_id, conn=conn)
    return subnet_id


def build_audit_filter_clause(request_args):
    """Build SQL AND-clause fragment and params for audit list/export queries."""
    conditions = []
    params = []
    user_ids = request_args.getlist('user_ids') if hasattr(request_args, 'getlist') else []
    if user_ids:
        placeholders = ','.join(['%s'] * len(user_ids))
        conditions.append(f'AuditLog.user_id IN ({placeholders})')
        params.extend(user_ids)
    subnet_id = request_args.get('subnet_id')
    if subnet_id:
        conditions.append('AuditLog.subnet_id = %s')
        params.append(subnet_id)
    action = request_args.get('action')
    if action:
        conditions.append('AuditLog.action = %s')
        params.append(action)
    device_name = request_args.get('device_name')
    if device_name:
        conditions.append('AuditLog.details LIKE %s')
        params.append(f'%{device_name}%')
    date_from = request_args.get('date_from')
    if date_from:
        conditions.append('AuditLog.timestamp >= %s')
        params.append(date_from)
    date_to = request_args.get('date_to')
    if date_to:
        conditions.append('AuditLog.timestamp <= %s')
        params.append(date_to + ' 23:59:59')
    search_query = request_args.get('search', '')
    if hasattr(request_args, 'get'):
        search_query = (search_query or '').strip()
    if search_query:
        conditions.append(
            "(AuditLog.details LIKE %s OR COALESCE(User.name, '') LIKE %s "
            "OR AuditLog.action LIKE %s OR COALESCE(Subnet.name, '') LIKE %s)"
        )
        pattern = f'%{search_query}%'
        params.extend([pattern, pattern, pattern, pattern])
    where = (' AND ' + ' AND '.join(conditions)) if conditions else ''
    return where, params


def configure_dhcp_pool(cursor, subnet_id, start_ip, end_ip, excluded_ips, subnet_name, subnet_cidr, user_id, conn, is_update):
    """Create or update a DHCP pool and mark IPs as DHCP-reserved."""
    excluded_ips = (excluded_ips or '').replace(' ', '')
    excluded_list = [ip for ip in excluded_ips.split(',') if ip]
    cursor.execute('SELECT ip FROM IPAddress WHERE subnet_id = %s', (subnet_id,))
    all_ips = [row[0] for row in cursor.fetchall()]
    if start_ip not in all_ips or end_ip not in all_ips:
        raise ValueError('Start and End IP must be within the subnet.')
    cursor.execute('UPDATE IPAddress SET hostname=NULL WHERE subnet_id=%s AND hostname="DHCP"', (subnet_id,))
    if is_update:
        cursor.execute(
            'UPDATE DHCPPool SET start_ip = %s, end_ip = %s, excluded_ips = %s WHERE subnet_id = %s',
            (start_ip, end_ip, excluded_ips, subnet_id),
        )
        action = 'dhcp_pool_update'
        details = f"Updated DHCP pool for subnet {subnet_name} ({subnet_cidr}): {start_ip} - {end_ip}, excluded: {excluded_ips}"
    else:
        cursor.execute(
            'INSERT INTO DHCPPool (subnet_id, start_ip, end_ip, excluded_ips) VALUES (%s, %s, %s, %s)',
            (subnet_id, start_ip, end_ip, excluded_ips),
        )
        action = 'dhcp_pool_create'
        details = f"Created DHCP pool for subnet {subnet_name} ({subnet_cidr}): {start_ip} - {end_ip}, excluded: {excluded_ips}"
    in_range = False
    for ip in all_ips:
        if ip == start_ip:
            in_range = True
        if in_range and ip not in excluded_list:
            cursor.execute('UPDATE IPAddress SET hostname="DHCP" WHERE subnet_id=%s AND ip=%s', (subnet_id, ip))
        if ip == end_ip:
            break
    add_audit_log(user_id, action, details, subnet_id, conn=conn)
    return {'start_ip': start_ip, 'end_ip': end_ip, 'excluded_ips': excluded_ips}


def remove_dhcp_pool(cursor, subnet_id, subnet_name, subnet_cidr, user_id, conn):
    cursor.execute('DELETE FROM DHCPPool WHERE subnet_id = %s', (subnet_id,))
    cursor.execute('UPDATE IPAddress SET hostname=NULL WHERE subnet_id=%s AND hostname="DHCP"', (subnet_id,))
    add_audit_log(user_id, 'dhcp_pool_remove', f"Removed DHCP pool for subnet {subnet_name} ({subnet_cidr})", subnet_id, conn=conn)


def assign_tag_to_device(conn, device_id, tag_id, user_id):
    """Assign tag to device. Returns (device_name, tag_name) or raises ValueError."""
    cursor = conn.cursor()
    device_name = get_device_name(cursor, device_id)
    if not device_name:
        raise ValueError('Device not found')
    cursor.execute('SELECT name FROM Tag WHERE id = %s', (tag_id,))
    tag_row = cursor.fetchone()
    if not tag_row:
        raise ValueError('Tag not found')
    tag_name = tag_row[0]
    cursor.execute('SELECT id FROM DeviceTag WHERE device_id = %s AND tag_id = %s', (device_id, tag_id))
    if cursor.fetchone():
        raise ValueError('Tag already assigned')
    cursor.execute('INSERT INTO DeviceTag (device_id, tag_id) VALUES (%s, %s)', (device_id, tag_id))
    add_audit_log(user_id, 'assign_device_tag', f"Assigned tag '{tag_name}' to device '{device_name}'", conn=conn)
    return device_name, tag_name


def remove_tag_from_device(conn, device_id, tag_id, user_id):
    """Remove tag from device. Returns (device_name, tag_name) or raises ValueError."""
    cursor = conn.cursor()
    device_name = get_device_name(cursor, device_id)
    if not device_name:
        raise ValueError('Device not found')
    cursor.execute('SELECT name FROM Tag WHERE id = %s', (tag_id,))
    tag_row = cursor.fetchone()
    if not tag_row:
        raise ValueError('Tag not found')
    tag_name = tag_row[0]
    cursor.execute('SELECT id FROM DeviceTag WHERE device_id = %s AND tag_id = %s', (device_id, tag_id))
    if not cursor.fetchone():
        raise ValueError('Tag not assigned')
    cursor.execute('DELETE FROM DeviceTag WHERE device_id = %s AND tag_id = %s', (device_id, tag_id))
    add_audit_log(user_id, 'remove_device_tag', f"Removed tag '{tag_name}' from device '{device_name}'", conn=conn)
    return device_name, tag_name


def update_entity_custom_fields(conn, entity_type, entity_id, submitted_data, user_id, is_json=False):
    """Validate and save custom field values. Returns list of errors (empty if ok)."""
    table = 'Device' if entity_type == 'device' else 'Subnet'
    audit_action = f'update_{entity_type}_custom_fields'
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        'SELECT id, field_key, field_type, required, validation_rules FROM CustomFieldDefinition WHERE entity_type = %s',
        (entity_type,),
    )
    field_defs = {f['field_key']: f for f in cursor.fetchall()}
    new_values = {}
    errors = []
    for field_key, field_def in field_defs.items():
        if is_json:
            submitted_value = submitted_data.get(field_key, '')
        else:
            submitted_value = submitted_data.get(f'custom_field_{field_key}', '')
        validation_rules = field_def.get('validation_rules')
        if isinstance(validation_rules, str):
            try:
                validation_rules = json.loads(validation_rules)
            except json.JSONDecodeError:
                validation_rules = {}
        elif validation_rules is None:
            validation_rules = {}
        field_def['validation_rules'] = validation_rules
        if submitted_value == '' and not field_def.get('required'):
            continue
        is_valid, error_msg = validate_custom_field_value(field_def, submitted_value)
        if not is_valid:
            errors.append(error_msg)
        else:
            parsed_value = parse_custom_field_value(field_def['field_type'], submitted_value)
            if parsed_value is not None:
                new_values[field_key] = parsed_value
    if errors:
        return errors
    cursor.execute(f'UPDATE {table} SET custom_fields = %s WHERE id = %s', (json.dumps(new_values), entity_id))
    add_audit_log(user_id, audit_action, f"Updated custom fields for {entity_type} {entity_id}", conn=conn)
    return []


def build_validation_rules_from_form(form, field_type=None):
    """Build validation_rules JSON from custom field form data."""
    rules = {}
    if field_type is None or field_type in ('text', 'textarea'):
        if form.get('min_length'):
            rules['min_length'] = int(form['min_length'])
        if form.get('max_length'):
            rules['max_length'] = int(form['max_length'])
        if form.get('regex_pattern'):
            rules['regex_pattern'] = form['regex_pattern']
    if field_type is None or field_type in ('number', 'decimal'):
        if form.get('min_value'):
            rules['min_value'] = float(form['min_value'])
        if form.get('max_value'):
            rules['max_value'] = float(form['max_value'])
    if field_type is None or field_type == 'select':
        if form.get('select_options'):
            rules['select_options'] = [o.strip() for o in form['select_options'].split(',') if o.strip()]
    return json.dumps(rules) if rules else None


def load_rack_view(conn, rack_id, side='front', networked_only=True):
    """Load rack page context: rack dict, rack_devices, site_devices."""
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM Rack WHERE id = %s', (rack_id,))
    rack = cursor.fetchone()
    if not rack:
        return None
    cursor.execute('SELECT * FROM RackDevice WHERE rack_id = %s', (rack_id,))
    rack_devices = cursor.fetchall()
    device_ids = [rd['device_id'] for rd in rack_devices if rd['device_id']]
    device_names = {}
    if device_ids:
        fmt = ','.join(['%s'] * len(device_ids))
        cursor.execute(f'SELECT id, name FROM Device WHERE id IN ({fmt})', tuple(device_ids))
        for row in cursor.fetchall():
            device_names[row['id']] = row['name']
    for rd in rack_devices:
        if rd['device_id']:
            rd['device_name'] = device_names.get(rd['device_id'], 'Unknown')
        else:
            rd['device_name'] = rd['nonnet_device_name']
    if networked_only:
        cursor.execute('''
            SELECT DISTINCT Device.id, Device.name, Device.description
            FROM Device JOIN DeviceIPAddress ON Device.id = DeviceIPAddress.device_id
            JOIN IPAddress ON DeviceIPAddress.ip_id = IPAddress.id
            JOIN Subnet ON IPAddress.subnet_id = Subnet.id
            WHERE Subnet.site = %s
        ''', (rack['site'],))
    else:
        cursor.execute('SELECT id, name, description FROM Device')
    site_devices = cursor.fetchall()
    return {'rack': rack, 'rack_devices': rack_devices, 'site_devices': site_devices, 'current_side': side}


def enrich_devices_batch(cursor, devices):
    """Attach ip_addresses, tags, custom_fields to device dicts in batch."""
    if not devices:
        return devices
    device_ids = [d['id'] for d in devices]
    placeholders = ','.join(['%s'] * len(device_ids))

    cursor.execute(f'''
        SELECT dia.device_id, ip.id, ip.ip, ip.hostname, ip.notes, s.id as subnet_id, s.name as subnet_name, s.cidr, s.site
        FROM DeviceIPAddress dia
        JOIN IPAddress ip ON dia.ip_id = ip.id
        JOIN Subnet s ON ip.subnet_id = s.id
        WHERE dia.device_id IN ({placeholders})
    ''', tuple(device_ids))
    ips_by_device = {}
    for row in cursor.fetchall():
        ips_by_device.setdefault(row['device_id'], []).append(row)

    cursor.execute(f'''
        SELECT dt.device_id, t.id, t.name, t.color
        FROM DeviceTag dt JOIN Tag t ON dt.tag_id = t.id
        WHERE dt.device_id IN ({placeholders}) ORDER BY t.name
    ''', tuple(device_ids))
    tags_by_device = {}
    for row in cursor.fetchall():
        tags_by_device.setdefault(row['device_id'], []).append(
            {'id': row['id'], 'name': row['name'], 'color': row['color']}
        )

    cursor.execute(f'SELECT id, custom_fields FROM Device WHERE id IN ({placeholders})', tuple(device_ids))
    cf_by_id = {}
    for row in cursor.fetchall():
        cf = row['custom_fields']
        if cf:
            try:
                cf_by_id[row['id']] = json.loads(cf)
            except (json.JSONDecodeError, TypeError):
                cf_by_id[row['id']] = {}
        else:
            cf_by_id[row['id']] = {}

    for device in devices:
        did = device['id']
        device['ip_addresses'] = ips_by_device.get(did, [])
        device['tags'] = tags_by_device.get(did, [])
        device['custom_fields'] = cf_by_id.get(did, {})
    return devices


def parse_custom_fields_json(raw):
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def fetch_subnet_ip_rows(cursor, subnet_id):
    cursor.execute('''
        SELECT ip.id, ip.ip, ip.hostname, d.id, d.description, ip.notes
        FROM IPAddress ip
        LEFT JOIN DeviceIPAddress dia ON ip.id = dia.ip_id
        LEFT JOIN Device d ON dia.device_id = d.id
        WHERE ip.subnet_id = %s
        ORDER BY INET_ATON(ip.ip)
    ''', (subnet_id,))
    return cursor.fetchall()


def subnet_ip_csv_rows(ip_rows):
    """Convert IP query rows to CSV data rows."""
    rows = []
    for ip in ip_rows:
        device_desc = ip[4] or ''
        ip_notes = ip[5] if len(ip) > 5 and ip[5] else ''
        combined_desc = device_desc
        if ip_notes:
            combined_desc = f"{combined_desc}\n{ip_notes}" if combined_desc else ip_notes
        rows.append([ip[1] or '', ip[2] or '', combined_desc])
    return rows


def csv_attachment(rows, headers, filename):
    output = StringIO()
    writer = csv.writer(output)
    if headers:
        writer.writerow(headers)
    writer.writerows(rows)
    output_bytes = BytesIO(output.getvalue().encode('utf-8'))
    output_bytes.seek(0)
    return send_file(output_bytes, mimetype='text/csv', as_attachment=True, download_name=filename)


def check_rack_placement(cursor, rack_id, position_u, side):
    """Return (height_u, error_message). height_u is None if rack not found."""
    cursor.execute('SELECT height_u FROM Rack WHERE id = %s', (rack_id,))
    rack = cursor.fetchone()
    if not rack:
        return None, 'Rack not found'
    height_u = rack['height_u']
    if position_u < 1 or position_u > height_u:
        return height_u, f"Invalid U position: {position_u}. Rack is {height_u}U tall."
    cursor.execute(
        'SELECT COUNT(*) AS cnt FROM RackDevice WHERE rack_id = %s AND position_u = %s AND side = %s',
        (rack_id, position_u, side),
    )
    if cursor.fetchone()['cnt'] > 0:
        return height_u, f"U{position_u} on the {side} is already occupied."
    return height_u, None


def group_devices_by_site(devices):
    """Group device dicts by site key."""
    sites = {}
    seen_ids = set()
    for device in devices:
        if device['id'] in seen_ids:
            continue
        seen_ids.add(device['id'])
        site = device.get('site') or 'Unassigned'
        sites.setdefault(site, []).append(device)
    return sites


# ── Auth & account (v2) ───────────────────────────────────────────────────────

@app.route('/api/v2/auth/login', methods=['POST'])
def api_auth_login():
    data = json_body()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, password FROM User WHERE email = %s', (email,))
        user = cursor.fetchone()
        if not user or not verify_password(password, user[1]):
            logging.info(f"Failed login attempt for email: {email}")
            return jsonify({'error': 'Invalid email or password'}), 401
        user_id = user[0]
        cursor.execute('''
            SELECT u.totp_enabled, u.two_fa_setup_complete, r.require_2fa
            FROM User u LEFT JOIN Role r ON u.role_id = r.id WHERE u.id = %s
        ''', (user_id,))
        result = cursor.fetchone()
        totp_enabled = result[0] if result else False
        setup_complete = result[1] if result else False
        role_requires_2fa = result[2] if result else False
        if role_requires_2fa and not setup_complete:
            session['pending_user_id'] = user_id
            session['pending_email'] = email
            return jsonify({'requires_setup': True})
        if totp_enabled:
            session['pending_user_id'] = user_id
            session['pending_email'] = email
            return jsonify({'requires_2fa': True})
        establish_user_session(user_id, conn=conn)
    logging.info(f"User {email} logged in successfully.")
    return jsonify({'ok': True})


@app.route('/api/v2/auth/logout', methods=['POST'])
def api_auth_logout():
    session.clear()
    return jsonify({'ok': True})


@app.route('/api/v2/auth/me', methods=['GET'])
def api_auth_me():
    user = resolve_auth()
    if not user:
        return jsonify({
            'logged_in': False,
            'app_version': app.config['VERSION'],
            'org': {'name': app.config['NAME'], 'logo': app.config['LOGO_PNG']},
        })
    return jsonify({
        'logged_in': True,
        'app_version': app.config['VERSION'],
        'org': {'name': app.config['NAME'], 'logo': app.config['LOGO_PNG']},
        'user': {'id': user['id'], 'name': user['name'], 'email': user.get('email', '')},
        'permissions': sorted(user.get('permissions') or []),
    })


@app.route('/api/v2/auth/verify-2fa', methods=['POST'])
def api_auth_verify_2fa():
    data = json_body()
    pending_user_id = session.get('pending_user_id')
    if not pending_user_id:
        return jsonify({'error': 'No pending login'}), 400
    code = (data.get('code') or '').strip()
    use_backup = bool(data.get('use_backup'))
    if not code:
        return jsonify({'error': 'Verification code required'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT totp_secret, backup_codes FROM User WHERE id = %s', (pending_user_id,))
        result = cursor.fetchone()
        if not result:
            return jsonify({'error': 'User not found'}), 404
        totp_secret, backup_codes_json = result
        if not totp_secret:
            return jsonify({'error': '2FA is not configured for this account'}), 400
        if use_backup:
            if not backup_codes_json:
                return jsonify({'error': 'No backup codes available'}), 400
            valid, updated_codes = verify_backup_code(backup_codes_json, code)
            if not valid:
                return jsonify({'error': 'Invalid backup code'}), 401
            cursor.execute('UPDATE User SET backup_codes = %s WHERE id = %s', (updated_codes, pending_user_id))
            conn.commit()
        else:
            if len(code) != 6 or not code.isdigit():
                return jsonify({'error': 'Invalid code format'}), 400
            if not verify_totp(totp_secret, code):
                return jsonify({'error': 'Invalid verification code'}), 401
        establish_user_session(pending_user_id, conn=conn)
        session.pop('pending_user_id', None)
        session.pop('pending_email', None)
    return jsonify({'ok': True})


@app.route('/api/v2/auth/setup-2fa', methods=['POST'])
def api_auth_setup_2fa():
    data = json_body()
    action = data.get('action', 'generate')
    user_id = session.get('pending_user_id') or session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    if action == 'generate':
        secret = generate_totp_secret()
        session['temp_totp_secret'] = secret
        with get_db_connection(current_app) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT email FROM User WHERE id = %s', (user_id,))
            row = cursor.fetchone()
            email = row[0] if row else ''
        uri = get_totp_uri(secret, email)
        return jsonify({'secret': secret, 'qr_code': generate_qr_code(uri), 'email': email})
    if action == 'verify':
        code = (data.get('code') or '').strip()
        secret = session.get('temp_totp_secret')
        if not secret:
            return jsonify({'error': 'Session expired. Generate a new secret.'}), 400
        if not verify_totp(secret, code):
            return jsonify({'error': 'Invalid code'}), 401
        backup_codes = generate_backup_codes()
        backup_codes_json = json.dumps(backup_codes)
        with get_db_connection(current_app) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE User SET totp_secret = %s, totp_enabled = TRUE, backup_codes = %s, two_fa_setup_complete = TRUE
                WHERE id = %s
            ''', (secret, backup_codes_json, user_id))
            conn.commit()
        session.pop('temp_totp_secret', None)
        complete_login = session.get('pending_user_id') == user_id
        if complete_login:
            establish_user_session(user_id, conn=conn)
            session.pop('pending_user_id', None)
            session.pop('pending_email', None)
        return jsonify({'ok': True, 'backup_codes': backup_codes})
    return jsonify({'error': 'Invalid action'}), 400


@app.route('/api/v2/account', methods=['GET'])
@require_auth
def api_account_get():
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT u.totp_enabled, u.two_fa_setup_complete, u.backup_codes, r.require_2fa
            FROM User u LEFT JOIN Role r ON u.role_id = r.id WHERE u.id = %s
        ''', (get_current_user_id(),))
        row = cursor.fetchone()
    backup_codes = None
    if row and row.get('backup_codes'):
        try:
            codes = json.loads(row['backup_codes'])
            backup_codes = format_backup_codes(codes)
        except json.JSONDecodeError:
            pass
    return jsonify({
        'user': {'id': get_current_user_id(), 'name': current_user()['name'], 'email': current_user().get('email', '')},
        'totp_enabled': bool(row and row.get('totp_enabled')),
        'two_fa_setup_complete': bool(row and row.get('two_fa_setup_complete')),
        'role_requires_2fa': bool(row and row.get('require_2fa')),
        'backup_codes': backup_codes,
    })


@app.route('/api/v2/account/change-password', methods=['POST'])
@require_auth
def api_account_change_password():
    data = json_body()
    current_pw = data.get('current_password') or ''
    new_pw = data.get('new_password') or ''
    if not current_pw or not new_pw:
        return jsonify({'error': 'Current and new password required'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT password FROM User WHERE id = %s', (get_current_user_id(),))
        row = cursor.fetchone()
        if not row or not verify_password(current_pw, row[0]):
            return jsonify({'error': 'Current password is incorrect'}), 401
        cursor.execute('UPDATE User SET password = %s WHERE id = %s', (hash_password(new_pw), get_current_user_id()))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/account/disable-2fa', methods=['POST'])
@require_auth
def api_account_disable_2fa():
    data = json_body()
    password = data.get('password') or ''
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT password, totp_enabled FROM User WHERE id = %s', (get_current_user_id(),))
        row = cursor.fetchone()
        if not row or not verify_password(password, row[0]):
            return jsonify({'error': 'Password is incorrect'}), 401
        if not row[1]:
            return jsonify({'error': '2FA is not enabled'}), 400
        cursor.execute('''
            UPDATE User SET totp_secret = NULL, totp_enabled = FALSE, backup_codes = NULL, two_fa_setup_complete = FALSE
            WHERE id = %s
        ''', (get_current_user_id(),))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/account/regenerate-backup-codes', methods=['POST'])
@require_auth
def api_account_regenerate_backup_codes():
    data = json_body()
    password = data.get('password') or ''
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT password, totp_enabled FROM User WHERE id = %s', (get_current_user_id(),))
        row = cursor.fetchone()
        if not row or not verify_password(password, row[0]):
            return jsonify({'error': 'Password is incorrect'}), 401
        if not row[1]:
            return jsonify({'error': '2FA is not enabled'}), 400
        backup_codes = generate_backup_codes()
        cursor.execute('UPDATE User SET backup_codes = %s WHERE id = %s', (json.dumps(backup_codes), get_current_user_id()))
        conn.commit()
    return jsonify({'backup_codes': backup_codes})


# ── API v2 routes ─────────────────────────────────────────────────────────────

@app.route('/api/v2/info', methods=['GET'])
@require_auth
def api_info():
    """Get API information and authenticated user info"""
    return jsonify({
        'api_version': '2.0',
        'user': {
            'id': get_current_user_id(),
            'name': current_user()['name'],
            'email': current_user()['email']
        }
    })

# Devices API
@app.route('/api/v2/devices', methods=['GET'])
@require_permission('view_devices')
def api_devices():
    """Get all devices"""
    tag_filter = request.args.get('tag')
    site_filter = request.args.get('site')
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        if tag_filter:
            cursor.execute('''
                SELECT DISTINCT d.id, d.name, d.description
                FROM Device d
                JOIN DeviceTag dtag ON d.id = dtag.device_id
                JOIN Tag t ON dtag.tag_id = t.id
                WHERE t.name = %s
                ORDER BY d.name
            ''', (tag_filter,))
        elif site_filter:
            site_val = None if site_filter == 'Unassigned' else site_filter
            cursor.execute('''
                SELECT DISTINCT d.id, d.name, d.description
                FROM Device d
                JOIN DeviceIPAddress dia ON d.id = dia.device_id
                JOIN IPAddress ip ON dia.ip_id = ip.id
                JOIN Subnet s ON ip.subnet_id = s.id
                WHERE s.site <=> %s
                ORDER BY d.name
            ''', (site_val,))
        else:
            cursor.execute('SELECT id, name, description FROM Device ORDER BY name')
        devices = cursor.fetchall()
        enrich_devices_batch(cursor, devices)
    return items_response(devices)

@app.route('/api/v2/devices/<int:device_id>', methods=['GET'])
@require_permission('view_device')
def api_device(device_id):
    """Get a specific device"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT d.id, d.name, d.description
            FROM Device d
            WHERE d.id = %s
        ''', (device_id,))
        device = cursor.fetchone()
        if not device:
            return jsonify({'error': 'Device not found'}), 404
        cursor.execute('''
            SELECT ip.id, ip.ip, ip.hostname, ip.notes, s.id as subnet_id, s.name as subnet_name, s.cidr, s.site
            FROM DeviceIPAddress dia
            JOIN IPAddress ip ON dia.ip_id = ip.id
            JOIN Subnet s ON ip.subnet_id = s.id
            WHERE dia.device_id = %s
        ''', (device_id,))
        device['ip_addresses'] = cursor.fetchall()
        cursor.execute('''
            SELECT t.id, t.name, t.color
            FROM DeviceTag dt
            JOIN Tag t ON dt.tag_id = t.id
            WHERE dt.device_id = %s
            ORDER BY t.name
        ''', (device_id,))
        device['tags'] = cursor.fetchall()
        # Get custom fields
        cursor.execute('SELECT custom_fields FROM Device WHERE id = %s', (device_id,))
        cf_result = cursor.fetchone()
        if cf_result and cf_result.get('custom_fields'):
            try:
                device['custom_fields'] = json.loads(cf_result['custom_fields'])
            except (json.JSONDecodeError, TypeError):
                device['custom_fields'] = {}
        else:
            device['custom_fields'] = {}
    return jsonify(device)

@app.route('/api/v2/devices', methods=['POST'])
@require_permission('add_device')
def api_add_device():
    """Create a new device"""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Device name is required'}), 400
    
    name = data['name']
    description = data.get('description', '')
    
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO Device (name, description) VALUES (%s, %s)',
                      (name, description))
        device_id = cursor.lastrowid
        add_audit_log(get_current_user_id(), 'add_device', f"Added device {name}", conn=conn)
        conn.commit()
    return jsonify({'id': device_id, 'name': name, 'description': description}), 201

@app.route('/api/v2/devices/<int:device_id>', methods=['PUT'])
@require_permission('edit_device')
def api_update_device(device_id):
    """Update a device"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, description FROM Device WHERE id = %s', (device_id,))
        current = cursor.fetchone()
        if not current:
            return jsonify({'error': 'Device not found'}), 404
        current_name, current_description = current
        
        updates = []
        values = []
        rename = False
        new_name = current_name
        if 'name' in data:
            new_name = data['name']
            if new_name != current_name:
                updates.append('name = %s')
                values.append(new_name)
                rename = True
        if 'description' in data and data['description'] != current_description:
            updates.append('description = %s')
            values.append(data['description'])
        
        if not updates:
            return jsonify({'error': 'No changes to apply'}), 400
        
        values.append(device_id)
        cursor.execute(f'UPDATE Device SET {", ".join(updates)} WHERE id = %s', values)
        
        if rename:
            cursor.execute('UPDATE IPAddress SET hostname = %s WHERE hostname = %s', (new_name, current_name))
            add_audit_log(get_current_user_id(), 'rename_device', f"Renamed device '{current_name}' to '{new_name}'", conn=conn)
        
        conn.commit()
    return jsonify({'message': 'Device updated successfully', 'device': {'id': device_id, 'name': new_name}})

@app.route('/api/v2/devices/<int:device_id>', methods=['DELETE'])
@require_permission('delete_device')
def api_delete_device(device_id):
    """Delete a device"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        device_name = delete_device_record(conn, device_id, get_current_user_id())
        if not device_name:
            return jsonify({'error': 'Device not found'}), 404
        conn.commit()
    return jsonify({'message': 'Device deleted successfully', 'device': {'id': device_id, 'name': device_name}})

@app.route('/api/v2/devices/<int:device_id>/ips', methods=['POST'])
@require_permission('add_device_ip')
def api_add_device_ip(device_id):
    """Add an IP address to a device"""
    data = request.get_json()
    if not data or 'ip_id' not in data:
        return jsonify({'error': 'ip_id is required'}), 400
    
    ip_id = data['ip_id']
    from flask import current_app
    try:
        with get_db_connection(current_app) as conn:
            assign_ip_to_device(conn, device_id, ip_id, get_current_user_id())
            conn.commit()
    except ValueError as e:
        msg = str(e)
        if 'not found' in msg.lower():
            return jsonify({'error': msg}), 404
        return jsonify({'error': msg}), 400
    return jsonify({'message': 'IP address added to device successfully', 'ip_id': ip_id}), 201

@app.route('/api/v2/devices/<int:device_id>/ips/<int:ip_id>', methods=['DELETE'])
@require_permission('remove_device_ip')
def api_remove_device_ip(device_id, ip_id):
    """Remove an IP address from a device"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT ip.ip, ip.subnet_id, d.name
            FROM DeviceIPAddress dia
            JOIN IPAddress ip ON dia.ip_id = ip.id
            JOIN Device d ON dia.device_id = d.id
            WHERE dia.device_id = %s AND dia.ip_id = %s
        ''', (device_id, ip_id))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'IP address not found on device'}), 404
        ip, subnet_id, device_name = row
        cursor.execute('DELETE FROM DeviceIPAddress WHERE device_id = %s AND ip_id = %s', (device_id, ip_id))
        cursor.execute('UPDATE IPAddress SET hostname = NULL WHERE id = %s', (ip_id,))
        cursor.execute('SELECT name, cidr FROM Subnet WHERE id = %s', (subnet_id,))
        subnet_row = cursor.fetchone()
        if subnet_row:
            subnet_name, subnet_cidr = subnet_row
            details = f"Removed IP {ip} ({subnet_name} {subnet_cidr}) from device {device_name}"
        else:
            details = f"Removed IP {ip} from device {device_name}"
        add_audit_log(get_current_user_id(), 'device_delete_ip', details, subnet_id, conn=conn)
        conn.commit()
    return jsonify({'message': 'IP address removed from device successfully', 'ip_id': ip_id})

# Subnets API
@app.route('/api/v2/subnets', methods=['GET'])
@require_permission('view_subnet')
def api_subnets():
    """Get all subnets"""
    include_util = request.args.get('include') == 'utilization'
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, cidr, site, vlan_id, vlan_description, vlan_notes, custom_fields FROM Subnet ORDER BY site, name')
        subnets = cursor.fetchall()
        utils = get_all_subnet_utilizations(cursor) if include_util else {}
        for subnet in subnets:
            subnet['custom_fields'] = parse_custom_fields_json(subnet.pop('custom_fields', None))
            if include_util:
                u = utils.get(subnet['id'], {'total': 0, 'used': 0, 'percent': 0})
                subnet['utilization'] = u['percent']
                subnet['total_ips'] = u['total']
                subnet['used_ips'] = u['used']
    return items_response(subnets)

@app.route('/api/v2/subnets/<int:subnet_id>', methods=['GET'])
@require_permission('view_subnet')
def api_subnet(subnet_id):
    """Get a specific subnet with IP addresses"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, cidr, site, vlan_id, vlan_description, vlan_notes FROM Subnet WHERE id = %s', (subnet_id,))
        subnet = cursor.fetchone()
        if not subnet:
            return jsonify({'error': 'Subnet not found'}), 404
        cursor.execute('''
            SELECT ip.id, ip.ip, ip.hostname, ip.notes, d.id as device_id, d.name as device_name, d.description
            FROM IPAddress ip
            LEFT JOIN DeviceIPAddress dia ON ip.id = dia.ip_id
            LEFT JOIN Device d ON dia.device_id = d.id
            WHERE ip.subnet_id = %s
            ORDER BY INET_ATON(ip.ip)
        ''', (subnet_id,))
        subnet['ip_addresses'] = cursor.fetchall()
        # Get custom fields
        cursor.execute('SELECT custom_fields FROM Subnet WHERE id = %s', (subnet_id,))
        cf_result = cursor.fetchone()
        if cf_result and cf_result.get('custom_fields'):
            try:
                subnet['custom_fields'] = json.loads(cf_result['custom_fields'])
            except (json.JSONDecodeError, TypeError):
                subnet['custom_fields'] = {}
        else:
            subnet['custom_fields'] = {}
    return jsonify(subnet)

@app.route('/api/v2/subnets/<int:subnet_id>/next_free_ip', methods=['GET'])
@require_permission('view_subnet')
def api_subnet_next_free_ip(subnet_id):
    """Get the next free IP address in a subnet"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        # First check if subnet exists
        cursor.execute('SELECT id FROM Subnet WHERE id = %s', (subnet_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Subnet not found'}), 404
        
        # Find the first unassigned IP outside DHCP pools
        cursor.execute('''
            SELECT ip.id, ip.ip
            FROM IPAddress ip
            LEFT JOIN DeviceIPAddress dia ON ip.id = dia.ip_id
            WHERE ip.subnet_id = %s AND dia.ip_id IS NULL
            ORDER BY INET_ATON(ip.ip)
        ''', (subnet_id,))
        ips = [{'id': r['id'], 'ip': r['ip']} for r in cursor.fetchall()]
        ips = filter_ips_outside_dhcp(cursor, subnet_id, ips)
        if not ips:
            return jsonify({'error': 'No free IP addresses available in this subnet'}), 404

        return jsonify({'id': ips[0]['id'], 'ip': ips[0]['ip']})

@app.route('/api/v2/subnets', methods=['POST'])
@require_permission('add_subnet')
def api_add_subnet():
    """Create a new subnet"""
    data = request.get_json()
    if not data or 'name' not in data or 'cidr' not in data:
        return jsonify({'error': 'Name and CIDR are required'}), 400
    
    name = data['name']
    cidr = data['cidr']
    site = data.get('site', '')
    vlan_id_str = str(data.get('vlan_id', '')).strip() if data.get('vlan_id') else ''
    vlan_description = data.get('vlan_description', '').strip() if data.get('vlan_description') else ''
    vlan_notes = data.get('vlan_notes', '').strip() if data.get('vlan_notes') else ''
    
    # Validate VLAN ID if provided
    if vlan_id_str:
        is_valid, error_msg, vlan_id = validate_vlan_id(vlan_id_str)
        if not is_valid:
            return jsonify({'error': error_msg}), 400
    else:
        vlan_id = None
    
    try:
        with get_db_connection(current_app) as conn:
            subnet_id = create_subnet_from_cidr(
                conn, name, cidr, site, vlan_id, vlan_description, vlan_notes, get_current_user_id(),
            )
            conn.commit()
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception:
        return jsonify({'error': 'Invalid CIDR format'}), 400
    
    return jsonify({
        'id': subnet_id, 
        'name': name, 
        'cidr': cidr, 
        'site': site,
        'vlan_id': vlan_id,
        'vlan_description': vlan_description if vlan_description else None,
        'vlan_notes': vlan_notes if vlan_notes else None
    }), 201

@app.route('/api/v2/subnets/<int:subnet_id>', methods=['PUT'])
@require_permission('edit_subnet')
def api_update_subnet(subnet_id):
    """Update a subnet"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, cidr, site, vlan_id, vlan_description, vlan_notes FROM Subnet WHERE id = %s', (subnet_id,))
        old_subnet = cursor.fetchone()
        if not old_subnet:
            return jsonify({'error': 'Subnet not found'}), 404
        old_name, old_cidr, old_site, old_vlan_id, old_vlan_desc, old_vlan_notes = old_subnet
        
        new_name = data.get('name', old_name)
        new_cidr = data.get('cidr', old_cidr)
        new_site = data.get('site', old_site)
        
        # Handle VLAN fields
        vlan_id_str = str(data.get('vlan_id', '')).strip() if data.get('vlan_id') is not None else ''
        new_vlan_description = data.get('vlan_description', '').strip() if data.get('vlan_description') else ''
        new_vlan_notes = data.get('vlan_notes', '').strip() if data.get('vlan_notes') else ''
        
        # Validate VLAN ID if provided
        if vlan_id_str:
            is_valid, error_msg, new_vlan_id = validate_vlan_id(vlan_id_str)
            if not is_valid:
                return jsonify({'error': error_msg}), 400
        elif 'vlan_id' in data and data['vlan_id'] is None:
            new_vlan_id = None
        else:
            new_vlan_id = old_vlan_id
        
        # Use old values if not provided in request
        if 'vlan_description' not in data:
            new_vlan_description = old_vlan_desc if old_vlan_desc else ''
        if 'vlan_notes' not in data:
            new_vlan_notes = old_vlan_notes if old_vlan_notes else ''
        
        updates = []
        values = []
        if new_name != old_name:
            updates.append('name = %s')
            values.append(new_name)
        if new_cidr != old_cidr:
            updates.append('cidr = %s')
            values.append(new_cidr)
        if new_site != old_site:
            updates.append('site = %s')
            values.append(new_site)
        if new_vlan_id != old_vlan_id:
            updates.append('vlan_id = %s')
            values.append(new_vlan_id)
        if new_vlan_description != (old_vlan_desc or ''):
            updates.append('vlan_description = %s')
            values.append(new_vlan_description if new_vlan_description else None)
        if new_vlan_notes != (old_vlan_notes or ''):
            updates.append('vlan_notes = %s')
            values.append(new_vlan_notes if new_vlan_notes else None)
        
        if not updates:
            return jsonify({'error': 'No changes to apply'}), 400
        
        values.append(subnet_id)
        cursor.execute(f'UPDATE Subnet SET {", ".join(updates)} WHERE id = %s', values)
        vlan_info = f" (VLAN {new_vlan_id})" if new_vlan_id else ""
        add_audit_log(
            get_current_user_id(),
            'edit_subnet',
            f"Edited subnet from {old_name} ({old_cidr}) to {new_name} ({new_cidr}) at site {new_site or 'Unassigned'}{vlan_info}",
            subnet_id,
            conn=conn
        )
        conn.commit()
    return jsonify({
        'message': 'Subnet updated successfully', 
        'subnet': {
            'id': subnet_id, 
            'name': new_name, 
            'cidr': new_cidr, 
            'site': new_site,
            'vlan_id': new_vlan_id,
            'vlan_description': new_vlan_description if new_vlan_description else None,
            'vlan_notes': new_vlan_notes if new_vlan_notes else None
        }
    })

@app.route('/api/v2/subnets/<int:subnet_id>', methods=['DELETE'])
@require_permission('delete_subnet')
def api_delete_subnet(subnet_id):
    """Delete a subnet"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, cidr FROM Subnet WHERE id = %s', (subnet_id,))
        subnet = cursor.fetchone()
        if not subnet:
            return jsonify({'error': 'Subnet not found'}), 404
        subnet_name, subnet_cidr = subnet
        cursor.execute('SELECT id FROM IPAddress WHERE subnet_id = %s', (subnet_id,))
        ip_ids = [row[0] for row in cursor.fetchall()]
        if ip_ids:
            cursor.executemany('DELETE FROM DeviceIPAddress WHERE ip_id = %s', [(ip_id,) for ip_id in ip_ids])
        cursor.execute('DELETE FROM DHCPPool WHERE subnet_id = %s', (subnet_id,))
        cursor.execute('UPDATE AuditLog SET subnet_id = NULL WHERE subnet_id = %s', (subnet_id,))
        cursor.execute('DELETE FROM IPAddress WHERE subnet_id = %s', (subnet_id,))
        cursor.execute('DELETE FROM Subnet WHERE id = %s', (subnet_id,))
        add_audit_log(get_current_user_id(), 'delete_subnet', f"Deleted subnet {subnet_name} ({subnet_cidr})", subnet_id, conn=conn)
        conn.commit()
    return jsonify({'message': 'Subnet deleted successfully', 'subnet': {'id': subnet_id, 'name': subnet_name, 'cidr': subnet_cidr}})

# Racks API
@app.route('/api/v2/racks', methods=['GET'])
@require_permission('view_racks')
def api_racks():
    """Get all racks"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, site, height_u FROM Rack ORDER BY site, name')
        racks = cursor.fetchall()
        for rack in racks:
            cursor.execute('SELECT COUNT(*) as used FROM RackDevice WHERE rack_id = %s AND side = %s', (rack['id'], 'front'))
            usage_row = cursor.fetchone()
            rack['used_u'] = usage_row['used'] if usage_row and 'used' in usage_row else 0
            rack['percent_full'] = int((rack['used_u'] / rack['height_u']) * 100) if rack['height_u'] else 0
            cursor.execute('''
                SELECT rd.id, rd.position_u, rd.side, rd.device_id, rd.nonnet_device_name,
                       d.name as device_name
                FROM RackDevice rd
                LEFT JOIN Device d ON rd.device_id = d.id
                WHERE rd.rack_id = %s
                ORDER BY rd.position_u, rd.side
            ''', (rack['id'],))
            rack['devices'] = cursor.fetchall()
    return items_response(racks)

@app.route('/api/v2/racks/<int:rack_id>', methods=['GET'])
@require_permission('view_rack')
def api_rack(rack_id):
    """Get a specific rack"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        ctx = load_rack_view(conn, rack_id)
        if not ctx:
            return jsonify({'error': 'Rack not found'}), 404
        rack = ctx['rack']
        rack['devices'] = [
            {
                'id': rd['id'],
                'position_u': rd['position_u'],
                'side': rd['side'],
                'device_id': rd['device_id'],
                'device_name': rd.get('device_name'),
                'nonnet_device_name': rd.get('nonnet_device_name'),
            }
            for rd in ctx['rack_devices']
        ]
        rack['site_devices'] = ctx['site_devices']
    return jsonify(rack)

@app.route('/api/v2/racks/<int:rack_id>', methods=['PUT'])
@require_permission('add_rack')
def api_update_rack(rack_id):
    """Update a rack"""
    data = json_body()
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, site, height_u FROM Rack WHERE id = %s', (rack_id,))
        rack = cursor.fetchone()
        if not rack:
            return jsonify({'error': 'Rack not found'}), 404
        name = (data.get('name') or rack['name']).strip()
        site = (data.get('site') or rack['site']).strip()
        height_u = data.get('height_u', rack['height_u'])
        try:
            height_u = int(height_u)
        except (TypeError, ValueError):
            return jsonify({'error': 'height_u must be an integer'}), 400
        if height_u <= 0:
            return jsonify({'error': 'height_u must be greater than zero'}), 400
        cursor.execute('UPDATE Rack SET name = %s, site = %s, height_u = %s WHERE id = %s',
                       (name, site, height_u, rack_id))
        add_audit_log(get_current_user_id(), 'edit_rack',
                      f"Updated rack '{rack['name']}' to '{name}' at site '{site}' ({height_u}U)", conn=conn)
        conn.commit()
    return jsonify({'id': rack_id, 'name': name, 'site': site, 'height_u': height_u})

@app.route('/api/v2/racks', methods=['POST'])
@require_permission('add_rack')
def api_add_rack():
    """Create a new rack"""
    from flask import current_app
    data = request.get_json()
    if not data or 'name' not in data or 'site' not in data or 'height_u' not in data:
        return jsonify({'error': 'Name, site, and height_u are required'}), 400
    
    name = data['name']
    site = data['site']
    height_u = data['height_u']
    try:
        height_u = int(height_u)
    except (TypeError, ValueError):
        return jsonify({'error': 'height_u must be an integer'}), 400
    if height_u <= 0:
        return jsonify({'error': 'height_u must be greater than zero'}), 400
    
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO Rack (name, site, height_u) VALUES (%s, %s, %s)', (name, site, height_u))
        rack_id = cursor.lastrowid
        add_audit_log(get_current_user_id(), 'add_rack', f"Added rack '{name}' at site '{site}' ({height_u}U)", conn=conn)
        conn.commit()
    return jsonify({'id': rack_id, 'name': name, 'site': site, 'height_u': height_u}), 201

@app.route('/api/v2/racks/<int:rack_id>', methods=['DELETE'])
@require_permission('delete_rack')
def api_delete_rack(rack_id):
    """Delete a rack"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM Rack WHERE id = %s', (rack_id,))
        rack = cursor.fetchone()
        if not rack:
            return jsonify({'error': 'Rack not found'}), 404
        rack_name = rack[0]
        cursor.execute('DELETE FROM Rack WHERE id = %s', (rack_id,))
        add_audit_log(get_current_user_id(), 'delete_rack', f"Deleted rack '{rack_name}'", conn=conn)
        conn.commit()
    return jsonify({'message': 'Rack deleted successfully', 'rack': {'id': rack_id, 'name': rack_name}})

@app.route('/api/v2/racks/<int:rack_id>/devices', methods=['POST'])
@require_permission('add_device_to_rack')
def api_add_device_to_rack(rack_id):
    """Add a device to a rack"""
    from flask import current_app
    data = request.get_json()
    if not data or 'position_u' not in data or 'side' not in data:
        return jsonify({'error': 'position_u and side are required'}), 400
    
    position_u = data['position_u']
    side = data['side']
    device_id = data.get('device_id')
    nonnet_device_name = data.get('nonnet_device_name')
    
    if device_id is None and not nonnet_device_name:
        return jsonify({'error': 'Either device_id or nonnet_device_name is required'}), 400
    
    try:
        position_u = int(position_u)
    except (TypeError, ValueError):
        return jsonify({'error': 'position_u must be an integer'}), 400
    side = str(side).lower()
    if side not in ('front', 'back'):
        return jsonify({'error': "side must be either 'front' or 'back'"}), 400
    if device_id is not None:
        try:
            device_id = int(device_id)
        except (TypeError, ValueError):
            return jsonify({'error': 'device_id must be an integer'}), 400
    
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT name, height_u FROM Rack WHERE id = %s', (rack_id,))
        rack = cursor.fetchone()
        if not rack:
            return jsonify({'error': 'Rack not found'}), 404
        if position_u < 1 or position_u > rack['height_u']:
            return jsonify({'error': f'Invalid U position: {position_u}. Rack is {rack["height_u"]}U tall.'}), 400
        
        cursor.execute('SELECT COUNT(*) as occupied_count FROM RackDevice WHERE rack_id = %s AND position_u = %s AND side = %s', (rack_id, position_u, side))
        occupied = cursor.fetchone()
        if occupied and occupied['occupied_count'] > 0:
            return jsonify({'error': f'U{position_u} on the {side} is already occupied.'}), 400
        
        if device_id is not None:
            cursor.execute('SELECT name FROM Device WHERE id = %s', (device_id,))
            device_row = cursor.fetchone()
            if not device_row:
                return jsonify({'error': 'Device not found'}), 404
            device_name = device_row['name']
            cursor.execute(
                'INSERT INTO RackDevice (rack_id, device_id, position_u, side, nonnet_device_name) VALUES (%s, %s, %s, %s, NULL)',
                (rack_id, device_id, position_u, side)
            )
            action = 'rack_add_device'
            details = f"Assigned device '{device_name}' to rack '{rack['name']}' U{position_u} ({side})"
        else:
            nonnet_device_name = (nonnet_device_name or '').strip()
            if not nonnet_device_name:
                return jsonify({'error': 'nonnet_device_name is required when device_id is not provided'}), 400
            cursor.execute(
                'INSERT INTO RackDevice (rack_id, device_id, position_u, side, nonnet_device_name) VALUES (%s, NULL, %s, %s, %s)',
                (rack_id, position_u, side, nonnet_device_name)
            )
            device_name = nonnet_device_name
            action = 'rack_add_nonnet_device'
            details = f"Added non-networked device '{device_name}' to rack '{rack['name']}' U{position_u} ({side})"
        
        rack_device_id = cursor.lastrowid
        add_audit_log(get_current_user_id(), action, details, conn=conn)
        conn.commit()
    return jsonify({
        'message': 'Device added to rack successfully',
        'rack_device': {
            'id': rack_device_id,
            'rack_id': rack_id,
            'device_id': device_id,
            'nonnet_device_name': device_name if device_id is None else None,
            'device_name': device_name,
            'position_u': position_u,
            'side': side
        }
    }), 201

@app.route('/api/v2/racks/<int:rack_id>/devices/<int:rack_device_id>', methods=['DELETE'])
@require_permission('remove_device_from_rack')
def api_remove_device_from_rack(rack_id, rack_device_id):
    """Remove a device from a rack"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT rd.device_id, rd.nonnet_device_name, rd.position_u, rd.side,
                   d.name AS device_name, r.name AS rack_name
            FROM RackDevice rd
            JOIN Rack r ON rd.rack_id = r.id
            LEFT JOIN Device d ON rd.device_id = d.id
            WHERE rd.id = %s AND rd.rack_id = %s
        ''', (rack_device_id, rack_id))
        rd = cursor.fetchone()
        if not rd:
            return jsonify({'error': 'Device not found in rack'}), 404
        if rd['device_id']:
            device_label = rd['device_name'] or str(rd['device_id'])
        else:
            device_label = rd['nonnet_device_name']
        cursor.execute('DELETE FROM RackDevice WHERE id = %s AND rack_id = %s', (rack_device_id, rack_id))
        add_audit_log(
            get_current_user_id(),
            'rack_remove_device',
            f"Removed device '{device_label}' from rack '{rd['rack_name']}' U{rd['position_u']} ({rd['side']})",
            conn=conn
        )
        conn.commit()
    return jsonify({'message': 'Device removed from rack successfully', 'rack_device_id': rack_device_id})

# Custom Fields API
@app.route('/api/v2/custom_fields/<entity_type>', methods=['GET'])
@require_permission('view_custom_fields')
def api_custom_fields_by_type(entity_type):
    """Get custom field definitions for a specific entity type"""
    if entity_type not in ['device', 'subnet']:
        return jsonify({'error': 'Invalid entity type. Must be "device" or "subnet"'}), 400
    
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, entity_type, name, field_key, field_type, required, 
                   default_value, help_text, display_order, validation_rules
            FROM CustomFieldDefinition
            WHERE entity_type = %s
            ORDER BY display_order, name
        ''', (entity_type,))
        fields = cursor.fetchall()
        # Parse validation_rules JSON strings
        for field in fields:
            if field.get('validation_rules'):
                try:
                    field['validation_rules'] = json.loads(field['validation_rules'])
                except (json.JSONDecodeError, TypeError):
                    field['validation_rules'] = {}
    return items_response(fields)

@app.route('/api/v2/custom_fields', methods=['POST'])
@require_permission('manage_custom_fields')
def api_add_custom_field():
    """Create a new custom field definition"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    required_fields = ['entity_type', 'name', 'field_key', 'field_type']
    for field in required_fields:
        if field not in data:
            return jsonify({'error': f'{field} is required'}), 400
    
    entity_type = data['entity_type']
    if entity_type not in ['device', 'subnet']:
        return jsonify({'error': 'Invalid entity_type. Must be "device" or "subnet"'}), 400
    
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            validation_rules = data.get('validation_rules', {})
            validation_rules_json = json.dumps(validation_rules) if validation_rules else None
            
            cursor.execute('''
                INSERT INTO CustomFieldDefinition 
                (entity_type, name, field_key, field_type, required, default_value, 
                 help_text, display_order, validation_rules)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (entity_type, data['name'], data['field_key'], data['field_type'],
                  data.get('required', False), data.get('default_value'),
                  data.get('help_text'), data.get('display_order', 0),
                  validation_rules_json))
            field_id = cursor.lastrowid
            add_audit_log(get_current_user_id(), 'add_custom_field',
                        f"Added custom field '{data['name']}' for {entity_type}", conn=conn)
            conn.commit()
            return jsonify({'id': field_id, 'message': 'Custom field created successfully'}), 201
        except mysql.connector.IntegrityError:
            return jsonify({'error': f'Field key "{data["field_key"]}" already exists'}), 400

@app.route('/api/v2/custom_fields/<int:field_id>', methods=['PUT'])
@require_permission('manage_custom_fields')
def api_update_custom_field(field_id):
    """Update a custom field definition"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id FROM CustomFieldDefinition WHERE id = %s', (field_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Custom field not found'}), 404
        
        updates = []
        values = []
        
        if 'name' in data:
            updates.append('name = %s')
            values.append(data['name'])
        if 'field_type' in data:
            updates.append('field_type = %s')
            values.append(data['field_type'])
        if 'required' in data:
            updates.append('required = %s')
            values.append(data['required'])
        if 'default_value' in data:
            updates.append('default_value = %s')
            values.append(data['default_value'])
        if 'help_text' in data:
            updates.append('help_text = %s')
            values.append(data['help_text'])
        if 'display_order' in data:
            updates.append('display_order = %s')
            values.append(data['display_order'])
        if 'validation_rules' in data:
            validation_rules_json = json.dumps(data['validation_rules']) if data['validation_rules'] else None
            updates.append('validation_rules = %s')
            values.append(validation_rules_json)
        
        if not updates:
            return jsonify({'error': 'No changes to apply'}), 400
        
        values.append(field_id)
        cursor.execute(f'UPDATE CustomFieldDefinition SET {", ".join(updates)} WHERE id = %s', values)
        add_audit_log(get_current_user_id(), 'edit_custom_field',
                     f"Updated custom field {field_id}", conn=conn)
        conn.commit()
    return jsonify({'message': 'Custom field updated successfully'})

@app.route('/api/v2/custom_fields/<int:field_id>', methods=['DELETE'])
@require_permission('manage_custom_fields')
def api_delete_custom_field(field_id):
    """Delete a custom field definition"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT name FROM CustomFieldDefinition WHERE id = %s', (field_id,))
        field = cursor.fetchone()
        if not field:
            return jsonify({'error': 'Custom field not found'}), 404
        
        cursor.execute('DELETE FROM CustomFieldDefinition WHERE id = %s', (field_id,))
        add_audit_log(get_current_user_id(), 'delete_custom_field',
                     f"Deleted custom field '{field['name']}'", conn=conn)
        conn.commit()
    return jsonify({'message': 'Custom field deleted successfully'})

# DHCP API
@app.route('/api/v2/subnets/<int:subnet_id>/dhcp', methods=['GET'])
@require_permission('view_dhcp')
def api_get_dhcp(subnet_id):
    """Get DHCP pools for a subnet"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, start_ip, end_ip, excluded_ips FROM DHCPPool WHERE subnet_id = %s', (subnet_id,))
        pools = cursor.fetchall()
    return jsonify({'pools': pools})

@app.route('/api/v2/subnets/<int:subnet_id>/dhcp', methods=['POST'])
@require_permission('configure_dhcp')
def api_configure_dhcp(subnet_id):
    """Configure DHCP pools for a subnet"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, cidr FROM Subnet WHERE id = %s', (subnet_id,))
        subnet = cursor.fetchone()
        if not subnet:
            return jsonify({'error': 'Subnet not found'}), 404
        subnet_name, subnet_cidr = subnet
        
        if data.get('remove'):
            remove_dhcp_pool(cursor, subnet_id, subnet_name, subnet_cidr, get_current_user_id(), conn)
            conn.commit()
            return jsonify({'message': 'DHCP pool removed successfully'})
        
        pools = data.get('pools')
        if not pools or not isinstance(pools, list):
            return jsonify({'error': 'pools array is required'}), 400
        pool = pools[0]
        start_ip = pool.get('start_ip')
        end_ip = pool.get('end_ip')
        if not start_ip or not end_ip:
            return jsonify({'error': 'start_ip and end_ip are required'}), 400
        excluded_ips = pool.get('excluded_ips', [])
        if not isinstance(excluded_ips, list):
            return jsonify({'error': 'excluded_ips must be a list of IP strings'}), 400
        excluded_list = [ip.strip() for ip in excluded_ips if ip.strip()]
        excluded_str = ','.join(excluded_list)
        
        cursor.execute('SELECT id FROM DHCPPool WHERE subnet_id = %s', (subnet_id,))
        is_update = cursor.fetchone() is not None
        try:
            result = configure_dhcp_pool(
                cursor, subnet_id, start_ip, end_ip, excluded_str,
                subnet_name, subnet_cidr, get_current_user_id(), conn, is_update,
            )
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        conn.commit()
    return jsonify({
        'message': 'DHCP pools configured successfully',
        'pool': {'start_ip': result['start_ip'], 'end_ip': result['end_ip'], 'excluded_ips': excluded_list},
    })

# Tags API
@app.route('/api/v2/tags', methods=['GET'])
@require_permission('view_tags')
def api_tags():
    """Get all tags"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, color, description, created_at FROM Tag ORDER BY name')
        tags = cursor.fetchall()
        for tag in tags:
            cursor.execute('SELECT COUNT(*) as device_count FROM DeviceTag WHERE tag_id = %s', (tag['id'],))
            tag['device_count'] = cursor.fetchone()['device_count']
    return items_response(tags)

@app.route('/api/v2/tags', methods=['POST'])
@require_permission('add_tag')
def api_add_tag():
    """Create a new tag"""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'error': 'Tag name is required'}), 400
    
    name = data['name'].strip()
    if not name:
        return jsonify({'error': 'Tag name cannot be empty'}), 400
    
    color = data.get('color', '#6B7280')
    description = data.get('description', '')
    
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO Tag (name, color, description) VALUES (%s, %s, %s)', (name, color, description))
            tag_id = cursor.lastrowid
            add_audit_log(get_current_user_id(), 'add_tag', f"Added tag '{name}'", conn=conn)
            conn.commit()
            return jsonify({'id': tag_id, 'name': name, 'color': color, 'description': description}), 201
        except mysql.connector.IntegrityError:
            return jsonify({'error': 'Tag name already exists'}), 400

@app.route('/api/v2/tags/<int:tag_id>', methods=['GET'])
@require_permission('view_tags')
def api_tag(tag_id):
    """Get a specific tag"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, color, description, created_at FROM Tag WHERE id = %s', (tag_id,))
        tag = cursor.fetchone()
        if not tag:
            return jsonify({'error': 'Tag not found'}), 404
        cursor.execute('''
            SELECT d.id, d.name, d.description
            FROM DeviceTag dtag
            JOIN Device d ON dtag.device_id = d.id
            WHERE dtag.tag_id = %s
            ORDER BY d.name
        ''', (tag_id,))
        tag['devices'] = cursor.fetchall()
    return jsonify(tag)

@app.route('/api/v2/tags/<int:tag_id>', methods=['PUT'])
@require_permission('edit_tag')
def api_update_tag(tag_id):
    """Update a tag"""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400
    
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, color, description FROM Tag WHERE id = %s', (tag_id,))
        current = cursor.fetchone()
        if not current:
            return jsonify({'error': 'Tag not found'}), 404
        
        current_name, current_color, current_description = current
        updates = []
        values = []
        
        if 'name' in data and data['name'].strip() != current_name:
            new_name = data['name'].strip()
            if not new_name:
                return jsonify({'error': 'Tag name cannot be empty'}), 400
            updates.append('name = %s')
            values.append(new_name)
        
        if 'color' in data and data['color'] != current_color:
            updates.append('color = %s')
            values.append(data['color'])
        
        if 'description' in data and data['description'] != current_description:
            updates.append('description = %s')
            values.append(data['description'])
        
        if not updates:
            return jsonify({'error': 'No changes to apply'}), 400
        
        values.append(tag_id)
        try:
            cursor.execute(f'UPDATE Tag SET {", ".join(updates)} WHERE id = %s', values)
            add_audit_log(get_current_user_id(), 'edit_tag', f"Updated tag '{current_name}'", conn=conn)
            conn.commit()
            return jsonify({'message': 'Tag updated successfully'})
        except mysql.connector.IntegrityError:
            return jsonify({'error': 'Tag name already exists'}), 400

@app.route('/api/v2/tags/<int:tag_id>', methods=['DELETE'])
@require_permission('delete_tag')
def api_delete_tag(tag_id):
    """Delete a tag"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name FROM Tag WHERE id = %s', (tag_id,))
        tag = cursor.fetchone()
        if not tag:
            return jsonify({'error': 'Tag not found'}), 404
        tag_name = tag[0]
        cursor.execute('DELETE FROM Tag WHERE id = %s', (tag_id,))
        add_audit_log(get_current_user_id(), 'delete_tag', f"Deleted tag '{tag_name}'", conn=conn)
        conn.commit()
    return jsonify({'message': 'Tag deleted successfully'})

@app.route('/api/v2/devices/<int:device_id>/tags', methods=['GET'])
@require_permission('view_device')
def api_device_tags(device_id):
    """Get tags for a specific device"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name FROM Device WHERE id = %s', (device_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Device not found'}), 404
        cursor.execute('''
            SELECT t.id, t.name, t.color, t.description, dt.created_at
            FROM DeviceTag dt
            JOIN Tag t ON dt.tag_id = t.id
            WHERE dt.device_id = %s
            ORDER BY t.name
        ''', (device_id,))
        tags = cursor.fetchall()
    return items_response(tags)

@app.route('/api/v2/devices/<int:device_id>/tags', methods=['POST'])
@require_permission('assign_device_tag')
def api_assign_device_tag(device_id):
    """Assign a tag to a device"""
    data = request.get_json()
    if not data or 'tag_id' not in data:
        return jsonify({'error': 'tag_id is required'}), 400
    
    tag_id = data['tag_id']
    with get_db_connection(current_app) as conn:
        try:
            assign_tag_to_device(conn, device_id, tag_id, get_current_user_id())
            conn.commit()
        except ValueError as exc:
            msg = str(exc)
            if 'not found' in msg.lower():
                return jsonify({'error': msg}), 404
            if 'already assigned' in msg.lower():
                return jsonify({'error': 'Tag already assigned to device'}), 400
            return jsonify({'error': msg}), 400
    return jsonify({'message': 'Tag assigned successfully'})

@app.route('/api/v2/devices/<int:device_id>/tags/<int:tag_id>', methods=['DELETE'])
@require_permission('remove_device_tag')
def api_remove_device_tag(device_id, tag_id):
    """Remove a tag from a device"""
    with get_db_connection(current_app) as conn:
        try:
            remove_tag_from_device(conn, device_id, tag_id, get_current_user_id())
            conn.commit()
        except ValueError as exc:
            msg = str(exc)
            if 'not found' in msg.lower():
                return jsonify({'error': msg}), 404
            if 'not assigned' in msg.lower():
                return jsonify({'error': 'Tag not assigned to device'}), 404
            return jsonify({'error': msg}), 400
    return jsonify({'message': 'Tag removed successfully'})

@app.route('/api/v2/devices/by-tag/<tag_identifier>', methods=['GET'])
@require_permission('view_devices')
def api_devices_by_tag(tag_identifier):
    """Get devices by tag name or ID. Use ?format=simple for simplified response."""
    from flask import current_app
    simple_format = request.args.get('format') == 'simple'
    
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        
        # Check if tag_identifier is numeric (tag ID) or string (tag name)
        try:
            tag_id = int(tag_identifier)
            # Query by tag ID
            if simple_format:
                cursor.execute('''
                    SELECT d.id, d.name
                    FROM DeviceTag dtag
                    JOIN Device d ON dtag.device_id = d.id
                    WHERE dtag.tag_id = %s
                    ORDER BY d.name
                ''', (tag_id,))
            else:
                cursor.execute('''
                    SELECT d.id, d.name, d.description
                    FROM DeviceTag dtag
                    JOIN Device d ON dtag.device_id = d.id
                    WHERE dtag.tag_id = %s
                    ORDER BY d.name
                ''', (tag_id,))
            # Get tag name for response
            cursor.execute('SELECT name FROM Tag WHERE id = %s', (tag_id,))
            tag_result = cursor.fetchone()
            if not tag_result:
                return jsonify({'error': 'Tag not found'}), 404
            tag_name = tag_result['name']
        except ValueError:
            # Query by tag name
            tag_name = tag_identifier
            if simple_format:
                cursor.execute('''
                    SELECT d.id, d.name
                    FROM DeviceTag dtag
                    JOIN Device d ON dtag.device_id = d.id
                    JOIN Tag t ON dtag.tag_id = t.id
                    WHERE t.name = %s
                    ORDER BY d.name
                ''', (tag_name,))
            else:
                cursor.execute('''
                    SELECT d.id, d.name, d.description
                    FROM DeviceTag dtag
                    JOIN Device d ON dtag.device_id = d.id
                    JOIN Tag t ON dtag.tag_id = t.id
                    WHERE t.name = %s
                    ORDER BY d.name
                ''', (tag_name,))
        
        devices = cursor.fetchall()
        
        if not devices:
            return jsonify({'items': [], 'meta': {'tag_name': tag_name, 'count': 0}})
        
        if simple_format:
            # Simple format: just name and first IP as clean array
            simple_devices = []
            for device in devices:
                cursor.execute('''
                    SELECT ip.ip
                    FROM DeviceIPAddress dia
                    JOIN IPAddress ip ON dia.ip_id = ip.id
                    WHERE dia.device_id = %s
                    ORDER BY INET_ATON(ip.ip)
                    LIMIT 1
                ''', (device['id'],))
                ip_result = cursor.fetchone()
                first_ip = ip_result['ip'] if ip_result else None
                
                # Only include devices that have an IP address
                if first_ip:
                    simple_devices.append({
                        'device': device['name'],
                        'ip': first_ip
                    })
                
            return jsonify(simple_devices)
        else:
            # Full format: complete device information
            for device in devices:
                cursor.execute('''
                    SELECT ip.id, ip.ip, ip.hostname, ip.notes, s.id as subnet_id, s.name as subnet_name, s.cidr, s.site
                    FROM DeviceIPAddress dia
                    JOIN IPAddress ip ON dia.ip_id = ip.id
                    JOIN Subnet s ON ip.subnet_id = s.id
                    WHERE dia.device_id = %s
                ''', (device['id'],))
                device['ip_addresses'] = cursor.fetchall()
                
                cursor.execute('''
                    SELECT t.id, t.name, t.color
                    FROM DeviceTag dtag
                    JOIN Tag t ON dtag.tag_id = t.id
                    WHERE dtag.device_id = %s
                    ORDER BY t.name
                ''', (device['id'],))
                device['tags'] = cursor.fetchall()
                
            return jsonify({'items': devices, 'meta': {'tag_name': tag_name, 'count': len(devices)}})

# Audit Log API
@app.route('/api/v2/audit/actions', methods=['GET'])
@require_permission('view_audit')
def api_audit_actions():
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT action FROM AuditLog ORDER BY action')
        actions = [row[0] for row in cursor.fetchall()]
    return items_response(actions)


@app.route('/api/v2/audit', methods=['GET'])
@require_permission('view_audit')
def api_audit():
    """Get audit log entries"""
    from flask import current_app
    where_sql, filter_params = build_audit_filters()
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f'''
            SELECT COUNT(*) as total
            FROM AuditLog al
            LEFT JOIN User u ON al.user_id = u.id
            {where_sql}
        ''', tuple(filter_params))
        total = cursor.fetchone()['total']
        cursor.execute(f'''
            SELECT al.id, al.user_id, u.name as user_name, al.action, al.details, al.subnet_id, al.timestamp
            FROM AuditLog al
            LEFT JOIN User u ON al.user_id = u.id
            {where_sql}
            ORDER BY al.timestamp DESC
            LIMIT %s OFFSET %s
        ''', tuple(filter_params) + (limit, offset))
        logs = cursor.fetchall()
    return jsonify({'items': logs, 'total': total})

# Users API (admin only)
@app.route('/api/v2/users', methods=['GET'])
@require_permission('view_users')
def api_users():
    """Get all users (admin only)"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT u.id, u.name, u.email, r.id as role_id, r.name as role_name
            FROM User u
            LEFT JOIN Role r ON u.role_id = r.id
            ORDER BY u.name
        ''')
        users = cursor.fetchall()
        # Don't return API keys in list
        for user in users:
            user.pop('api_key', None)
    return items_response(users)

# Roles API (admin only)
@app.route('/api/v2/roles', methods=['GET'])
@require_permission('view_users')
def api_roles():
    """Get all roles (admin only)"""
    from flask import current_app
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, description, require_2fa FROM Role ORDER BY name')
        roles = cursor.fetchall()
        for role in roles:
            cursor.execute('''
                SELECT p.id, p.name, p.description, p.category
                FROM RolePermission rp
                JOIN Permission p ON rp.permission_id = p.id
                WHERE rp.role_id = %s
            ''', (role['id'],))
            role['permissions'] = cursor.fetchall()
    return items_response(roles)


# ── Extended v2 endpoints ─────────────────────────────────────────────────────

@app.route('/api/v2/dashboard', methods=['GET'])
@require_permission('view_index')
def api_dashboard():
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        utils = get_all_subnet_utilizations(cursor)
        cursor.execute('SELECT COUNT(*) AS n FROM Device')
        device_count = cursor.fetchone()['n']
        cursor.execute('SELECT COUNT(*) AS n FROM Subnet')
        subnet_count = cursor.fetchone()['n']

        total_ips = sum(u['total'] for u in utils.values())
        used_ips = sum(u['used'] for u in utils.values())
        available_ips = max(total_ips - used_ips, 0)
        utilization_percent = round((used_ips / total_ips * 100) if total_ips > 0 else 0, 1)
        alerting_subnets = sum(1 for u in utils.values() if u['percent'] >= 90)

        cursor.execute('SELECT id, name, cidr, site, vlan_id FROM Subnet ORDER BY name')
        subnet_overview = []
        for s in cursor.fetchall():
            u = utils.get(s['id'], {'total': 0, 'used': 0, 'percent': 0})
            pct = u['percent']
            subnet_overview.append({
                'id': s['id'],
                'name': s['name'],
                'cidr': s['cidr'],
                'site': s['site'] or 'Unassigned',
                'vlan_id': s['vlan_id'],
                'utilization': pct,
                'available': u['total'] - u['used'],
                'status': 'alerting' if pct >= 90 else 'active',
            })

        cursor.execute('''
            SELECT HOUR(timestamp) AS hour, COUNT(*) AS count
            FROM AuditLog
            WHERE timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY HOUR(timestamp)
            ORDER BY hour
        ''')
        activity_by_hour = {row['hour']: row['count'] for row in cursor.fetchall()}
        activity = [{'hour': h, 'count': activity_by_hour.get(h, 0)} for h in range(24)]

    return jsonify({
        'stats': {
            'total_ips': total_ips,
            'used_ips': used_ips,
            'available_ips': available_ips,
            'utilization_percent': utilization_percent,
            'subnet_count': subnet_count,
            'alerting_subnets': alerting_subnets,
            'device_count': device_count,
        },
        'subnet_overview': subnet_overview,
        'activity': activity,
    })


@app.route('/api/v2/search', methods=['GET'])
@require_auth
def api_search():
    query = (request.args.get('q') or '').strip()
    results = {'subnets': [], 'ips': [], 'devices': [], 'tags': [], 'racks': [], 'sites': []}
    if not query:
        return jsonify(results)
    pattern = f'%{query}%'
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT id, name, cidr, site FROM Subnet
            WHERE name LIKE %s OR cidr LIKE %s OR site LIKE %s ORDER BY site, name
        ''', (pattern, pattern, pattern))
        results['subnets'] = [{**r, 'site': r['site'] or 'Unassigned'} for r in cursor.fetchall()]
        cursor.execute('''
            SELECT ip.id, ip.ip, ip.hostname, ip.subnet_id, s.name as subnet_name, s.cidr, s.site
            FROM IPAddress ip JOIN Subnet s ON ip.subnet_id = s.id
            WHERE ip.ip LIKE %s OR ip.hostname LIKE %s OR ip.notes LIKE %s
            ORDER BY INET_ATON(ip.ip)
        ''', (pattern, pattern, pattern))
        results['ips'] = [{**r, 'site': r['site'] or 'Unassigned'} for r in cursor.fetchall()]
        cursor.execute('SELECT id, name, description FROM Device WHERE name LIKE %s OR description LIKE %s ORDER BY name', (pattern, pattern))
        results['devices'] = cursor.fetchall()
        cursor.execute('SELECT id, name, description FROM Tag WHERE name LIKE %s OR description LIKE %s ORDER BY name', (pattern, pattern))
        results['tags'] = cursor.fetchall()
        cursor.execute('SELECT id, name, site, height_u FROM Rack WHERE name LIKE %s OR site LIKE %s ORDER BY site, name', (pattern, pattern))
        results['racks'] = cursor.fetchall()
        all_sites = {x['site'] for x in results['subnets']} | {x['site'] for x in results['racks']} | {x['site'] for x in results['ips']}
        results['sites'] = sorted(s for s in all_sites if query.lower() in s.lower())
    return jsonify(results)


@app.route('/api/v2/devices/<int:device_id>/ip-history', methods=['GET'])
@require_permission('view_device')
def api_device_ip_history(device_id):
    with get_db_connection(current_app) as conn:
        history = get_ip_history_from_audit_logs(device_id=device_id, conn=conn)
    return jsonify({'items': history})


@app.route('/api/v2/ips/<path:ip_address>/history', methods=['GET'])
@require_permission('view_subnet')
def api_ip_history(ip_address):
    with get_db_connection(current_app) as conn:
        history = get_ip_history_from_audit_logs(ip_address=ip_address, conn=conn)
    return jsonify({'items': history, 'ip': ip_address})


@app.route('/api/v2/subnets/<int:subnet_id>/available-ips', methods=['GET'])
@require_permission('view_subnet')
def api_subnet_available_ips(subnet_id):
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id FROM Subnet WHERE id = %s', (subnet_id,))
        if not cursor.fetchone():
            return jsonify({'error': 'Subnet not found'}), 404
        cursor.execute('''
            SELECT ip.id, ip.ip FROM IPAddress ip
            LEFT JOIN DeviceIPAddress dia ON ip.id = dia.ip_id
            WHERE ip.subnet_id = %s AND dia.ip_id IS NULL ORDER BY INET_ATON(ip.ip)
        ''', (subnet_id,))
        ips = [{'id': r['id'], 'ip': r['ip']} for r in cursor.fetchall()]
        ips = filter_ips_outside_dhcp(cursor, subnet_id, ips)
    return items_response(ips)


@app.route('/api/v2/subnets/<int:subnet_id>/export', methods=['GET'])
@require_permission('export_subnet_csv')
def api_subnet_export(subnet_id):
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT name, cidr FROM Subnet WHERE id = %s', (subnet_id,))
        subnet = cursor.fetchone()
        if not subnet:
            return jsonify({'error': 'Subnet not found'}), 404
        rows = subnet_ip_csv_rows(fetch_subnet_ip_rows(cursor, subnet_id))
    return csv_attachment(rows, ['IP Address', 'Hostname', 'Description'], f"{subnet[0]}_{subnet[1]}.csv".replace('/', '_'))


@app.route('/api/v2/ip-addresses/<int:ip_id>', methods=['PATCH'])
@require_permission('edit_subnet')
def api_patch_ip_address(ip_id):
    data = json_body()
    notes = data.get('notes')
    if notes is None:
        return jsonify({'error': 'notes field required'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT ip, subnet_id FROM IPAddress WHERE id = %s', (ip_id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'IP not found'}), 404
        cursor.execute('UPDATE IPAddress SET notes = %s WHERE id = %s', (notes.strip() or None, ip_id))
        add_audit_log(get_current_user_id(), 'update_ip_notes', f"Updated notes for IP {row['ip']}", row['subnet_id'], conn=conn)
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/devices/<int:device_id>/custom-fields', methods=['PATCH'])
@require_permission('edit_device')
def api_patch_device_custom_fields(device_id):
    data = json_body()
    with get_db_connection(current_app) as conn:
        errors = update_entity_custom_fields(conn, 'device', device_id, data.get('custom_fields') or data, get_current_user_id(), is_json=True)
        if errors:
            return jsonify({'error': '; '.join(errors)}), 400
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/subnets/<int:subnet_id>/custom-fields', methods=['PATCH'])
@require_permission('edit_subnet')
def api_patch_subnet_custom_fields(subnet_id):
    data = json_body()
    with get_db_connection(current_app) as conn:
        errors = update_entity_custom_fields(conn, 'subnet', subnet_id, data.get('custom_fields') or data, get_current_user_id(), is_json=True)
        if errors:
            return jsonify({'error': '; '.join(errors)}), 400
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/custom-fields/reorder', methods=['POST'])
@require_permission('manage_custom_fields')
def api_reorder_custom_fields():
    data = json_body()
    entity_type = data.get('entity_type')
    field_orders = data.get('field_orders') or {}
    if entity_type not in ('device', 'subnet'):
        return jsonify({'error': 'Invalid entity_type'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        for field_id, order in field_orders.items():
            cursor.execute('UPDATE CustomFieldDefinition SET display_order = %s WHERE id = %s AND entity_type = %s',
                          (int(order), int(field_id), entity_type))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/audit/export', methods=['GET'])
@require_permission('view_audit')
def api_audit_export():
    where_sql, filter_params = build_audit_filters()
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute(f'''
            SELECT al.timestamp, u.name, al.action, al.details, s.name
            FROM AuditLog al
            LEFT JOIN User u ON al.user_id = u.id
            LEFT JOIN Subnet s ON al.subnet_id = s.id
            {where_sql}
            ORDER BY al.timestamp DESC
        ''', tuple(filter_params))
        rows = cursor.fetchall()
    return csv_attachment(rows, ['Timestamp', 'User', 'Action', 'Details', 'Subnet'], 'audit_log.csv')


@app.route('/api/v2/users', methods=['POST'])
@require_permission('manage_users')
def api_add_user():
    data = json_body()
    name = (data.get('name') or '').strip()
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    role_id = data.get('role_id')
    if not all([name, email, password]):
        return jsonify({'error': 'Name, email, and password required'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        try:
            api_key = generate_api_key()
            cursor.execute('INSERT INTO User (name, email, password, role_id, api_key) VALUES (%s, %s, %s, %s, %s)',
                          (name, email, hash_password(password), role_id, api_key))
            conn.commit()
            return jsonify({'id': cursor.lastrowid}), 201
        except mysql.connector.IntegrityError:
            return jsonify({'error': 'Email already exists'}), 400


@app.route('/api/v2/users/<int:user_id>', methods=['PUT'])
@require_permission('manage_users')
def api_update_user(user_id):
    data = json_body()
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        if 'name' in data:
            cursor.execute('UPDATE User SET name = %s WHERE id = %s', (data['name'].strip(), user_id))
        if 'email' in data:
            cursor.execute('UPDATE User SET email = %s WHERE id = %s', (data['email'].strip(), user_id))
        if 'password' in data and data['password']:
            cursor.execute('UPDATE User SET password = %s WHERE id = %s', (hash_password(data['password']), user_id))
        if 'role_id' in data:
            cursor.execute('UPDATE User SET role_id = %s WHERE id = %s', (data['role_id'], user_id))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/users/<int:user_id>', methods=['DELETE'])
@require_permission('manage_users')
def api_delete_user(user_id):
    if user_id == get_current_user_id():
        return jsonify({'error': 'Cannot delete your own account'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM User WHERE id = %s', (user_id,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/users/<int:user_id>/regenerate-api-key', methods=['POST'])
@require_permission('manage_users')
def api_regenerate_user_api_key(user_id):
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        new_key = generate_api_key()
        cursor.execute('UPDATE User SET api_key = %s WHERE id = %s', (new_key, user_id))
        conn.commit()
    return jsonify({'api_key': new_key})


@app.route('/api/v2/roles', methods=['POST'])
@require_permission('manage_roles')
def api_add_role():
    data = json_body()
    name = (data.get('name') or '').strip()
    description = (data.get('description') or '').strip()
    permission_ids = data.get('permission_ids') or []
    if not name:
        return jsonify({'error': 'Name required'}), 400
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO Role (name, description) VALUES (%s, %s)', (name, description))
            role_id = cursor.lastrowid
            for pid in permission_ids:
                cursor.execute('INSERT INTO RolePermission (role_id, permission_id) VALUES (%s, %s)', (role_id, pid))
            conn.commit()
            return jsonify({'id': role_id}), 201
        except mysql.connector.IntegrityError:
            return jsonify({'error': 'Role already exists'}), 400


@app.route('/api/v2/roles/<int:role_id>', methods=['PUT'])
@require_permission('manage_roles')
def api_update_role(role_id):
    data = json_body()
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        if 'name' in data:
            cursor.execute('UPDATE Role SET name = %s WHERE id = %s', (data['name'].strip(), role_id))
        if 'description' in data:
            cursor.execute('UPDATE Role SET description = %s WHERE id = %s', (data['description'], role_id))
        if 'require_2fa' in data:
            cursor.execute('UPDATE Role SET require_2fa = %s WHERE id = %s', (bool(data['require_2fa']), role_id))
        if 'permission_ids' in data:
            cursor.execute('DELETE FROM RolePermission WHERE role_id = %s', (role_id,))
            for pid in data['permission_ids']:
                cursor.execute('INSERT INTO RolePermission (role_id, permission_id) VALUES (%s, %s)', (role_id, pid))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/roles/<int:role_id>', methods=['DELETE'])
@require_permission('manage_roles')
def api_delete_role(role_id):
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM User WHERE role_id = %s', (role_id,))
        if cursor.fetchone()[0] > 0:
            return jsonify({'error': 'Role is assigned to users'}), 400
        cursor.execute('DELETE FROM RolePermission WHERE role_id = %s', (role_id,))
        cursor.execute('DELETE FROM Role WHERE id = %s', (role_id,))
        conn.commit()
    return jsonify({'ok': True})


@app.route('/api/v2/permissions', methods=['GET'])
@require_permission('manage_roles')
def api_permissions():
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT id, name, description, category FROM Permission ORDER BY category, name')
        return items_response(cursor.fetchall())


@app.route('/api/v2/bulk/assign-ips', methods=['POST'])
@require_permission('add_device_ip')
def api_bulk_assign_ips():
    data = json_body()
    device_id = data.get('device_id')
    ip_ids = data.get('ip_ids') or []
    results = {'success': [], 'failed': []}
    with get_db_connection(current_app) as conn:
        for ip_id in ip_ids:
            try:
                ip = assign_ip_to_device(conn, device_id, ip_id, get_current_user_id())
                results['success'].append({'ip_id': ip_id, 'ip': ip})
            except Exception as e:
                results['failed'].append({'ip_id': ip_id, 'reason': str(e)})
        conn.commit()
    return jsonify(results)


@app.route('/api/v2/bulk/create-devices', methods=['POST'])
@require_permission('add_device')
def api_bulk_create_devices():
    data = json_body()
    names = data.get('names') or []
    results = {'success': [], 'failed': []}
    user_id = get_current_user_id()
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        for name in names:
            name = name.strip()
            if not name:
                continue
            try:
                cursor.execute('INSERT INTO Device (name) VALUES (%s)', (name,))
                device_id = cursor.lastrowid
                add_audit_log(user_id, 'add_device', f"Added device {name}", conn=conn)
                results['success'].append({'id': device_id, 'name': name})
            except Exception as e:
                results['failed'].append({'name': name, 'reason': str(e)})
        conn.commit()
    return jsonify(results)


@app.route('/api/v2/bulk/assign-tags', methods=['POST'])
@require_permission('assign_device_tag')
def api_bulk_assign_tags():
    data = json_body()
    device_ids = data.get('device_ids') or []
    tag_id = data.get('tag_id')
    results = {'success': [], 'failed': []}
    with get_db_connection(current_app) as conn:
        for device_id in device_ids:
            try:
                assign_tag_to_device(conn, device_id, tag_id, get_current_user_id())
                results['success'].append({'device_id': device_id})
            except Exception as e:
                results['failed'].append({'device_id': device_id, 'reason': str(e)})
        conn.commit()
    return jsonify(results)


@app.route('/api/v2/bulk/export-subnets', methods=['POST'])
@require_permission('export_subnet_csv')
def api_bulk_export_subnets():
    data = json_body()
    subnet_ids = data.get('subnet_ids') or []
    output = StringIO()
    writer = csv.writer(output)
    with get_db_connection(current_app) as conn:
        cursor = conn.cursor()
        for subnet_id in subnet_ids:
            cursor.execute('SELECT name, cidr FROM Subnet WHERE id = %s', (subnet_id,))
            subnet = cursor.fetchone()
            if not subnet:
                continue
            writer.writerow([f"Subnet: {subnet[0]} ({subnet[1]})"])
            writer.writerow(['IP Address', 'Hostname', 'Description'])
            writer.writerows(subnet_ip_csv_rows(fetch_subnet_ip_rows(cursor, subnet_id)))
            writer.writerow([])
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name='bulk_subnet_export.csv')


@app.route('/api/v2/racks/<int:rack_id>/export', methods=['GET'])
@require_permission('export_rack_csv')
def api_rack_export(rack_id):
    with get_db_connection(current_app) as conn:
        ctx = load_rack_view(conn, rack_id, side='front', networked_only=False)
        if not ctx:
            return jsonify({'error': 'Rack not found'}), 404
        rack = ctx['rack']
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([f"Rack: {rack['name']} ({rack['site']})"])
        writer.writerow(['U', 'Side', 'Device'])
        for rd in sorted(ctx['rack_devices'], key=lambda x: (-x['position_u'], x['side'])):
            writer.writerow([rd['position_u'], rd['side'], rd.get('device_name') or rd.get('nonnet_device_name') or ''])
    output.seek(0)
    return send_file(BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv',
                     as_attachment=True, download_name=f"{rack['name']}_rack.csv".replace(' ', '_'))


# ── SPA static files ──────────────────────────────────────────────────────────
STATIC_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
DIST = os.path.join(STATIC_ROOT, 'dist')


@app.route('/favicon.ico')
def favicon():
    logo = app.config['LOGO_PNG']
    if logo.startswith(('http://', 'https://')):
        return redirect(logo)
    path = logo if os.path.isabs(logo) else os.path.join(os.path.dirname(os.path.abspath(__file__)), logo)
    if os.path.isfile(path):
        return send_file(path, mimetype='image/png')
    abort(404)


@app.route('/assets/<path:sub>')
def spa_assets(sub):
    return send_from_directory(os.path.join(DIST, 'assets'), sub)


@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def spa(path):
    if path.startswith('api/'):
        abort(404)
    index = os.path.join(DIST, 'index.html')
    if not os.path.isfile(index):
        return ('Frontend not built. Run: cd frontend && npm ci && npm run build', 503)
    if path:
        try:
            file_path = safe_join(DIST, path)
        except ValueError:
            file_path = None
        if file_path and os.path.isfile(file_path):
            return send_file(file_path)
    return send_from_directory(DIST, 'index.html')


# ── App startup ───────────────────────────────────────────────────────────────
init_db(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

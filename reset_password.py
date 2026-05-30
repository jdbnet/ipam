#!/usr/bin/env python3
"""Reset a user's password (admin CLI). Uses MYSQL_* env vars from .env."""

import argparse
import getpass
import os
import secrets
import sys

from dotenv import load_dotenv
from flask import Flask

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

app = Flask(__name__)
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'user')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', 'password')
app.config['MYSQL_DATABASE'] = os.environ.get('MYSQL_DATABASE', 'ipam')

from db import get_db_connection, hash_password


def reset_password(email, password):
    email = email.strip()
    if not email:
        raise SystemExit('Email is required.')

    conn = get_db_connection(app)
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT id, name FROM User WHERE email = %s', (email,))
        row = cursor.fetchone()
        if not row:
            raise SystemExit(f'No user found with email: {email}')

        user_id, name = row
        cursor.execute(
            'UPDATE User SET password = %s WHERE id = %s',
            (hash_password(password), user_id),
        )
    finally:
        conn.close()

    return name


def main():
    parser = argparse.ArgumentParser(
        description='Reset an IPAM user password.',
    )
    parser.add_argument('email', help='User email address')
    parser.add_argument(
        '--password', '-p',
        help='New password (prompted securely if omitted)',
    )
    parser.add_argument(
        '--generate', '-g',
        action='store_true',
        help='Generate a random password and print it',
    )
    args = parser.parse_args()

    if args.generate and args.password:
        raise SystemExit('Use either --password or --generate, not both.')

    if args.generate:
        password = secrets.token_urlsafe(16)
    elif args.password:
        password = args.password
    else:
        password = getpass.getpass('New password: ')
        confirm = getpass.getpass('Confirm password: ')
        if password != confirm:
            raise SystemExit('Passwords do not match.')

    if not password:
        raise SystemExit('Password cannot be empty.')

    name = reset_password(args.email, password)
    print(f'Password reset for {name} ({args.email}).')
    if args.generate:
        print(f'Generated password: {password}')


if __name__ == '__main__':
    main()

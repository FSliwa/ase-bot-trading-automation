"""
User database management for registration and authentication with PostgreSQL support.
"""

import hashlib
import json
import os
import secrets
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any

# PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False

class UserDatabase:
    def __init__(self, db_file='users.json'):
        self.db_file = db_file
        self.use_postgres = self._init_postgres()
        if not self.use_postgres:
            self.users = self._load_database()
    
    def _init_postgres(self) -> bool:
        """Initialize PostgreSQL connection if available and configured."""
        if not POSTGRES_AVAILABLE:
            return False
        
        # Check for PostgreSQL environment variables
        self.pg_config = {
            'host': os.getenv('POSTGRES_HOST', 'localhost'),
            'database': os.getenv('POSTGRES_DB', 'trading_bot'),
            'user': os.getenv('POSTGRES_USER', 'postgres'),
            'password': os.getenv('POSTGRES_PASSWORD', ''),
            'port': int(os.getenv('POSTGRES_PORT', '5432'))
        }
        
        if not self.pg_config['password']:
            return False
        
        try:
            # Test connection and create tables if needed
            self._create_tables()
            return True
        except Exception as e:
            print(f"PostgreSQL initialization failed: {e}")
            return False
    
    def _get_pg_connection(self):
        """Get PostgreSQL connection."""
        return psycopg2.connect(**self.pg_config)
    
    def _create_tables(self):
        """Create necessary tables in PostgreSQL."""
        with self._get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(50) UNIQUE NOT NULL,
                        email VARCHAR(255) UNIQUE NOT NULL,
                        password_hash VARCHAR(64) NOT NULL,
                        salt VARCHAR(32) NOT NULL,
                        first_name VARCHAR(100),
                        last_name VARCHAR(100),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        is_active BOOLEAN DEFAULT TRUE,
                        account_type VARCHAR(20) DEFAULT 'free',
                        settings JSONB DEFAULT '{}'::jsonb
                    );
                """)
                
                # Create indexes
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
                
                conn.commit()
    
    def _load_database(self) -> Dict[str, Any]:
        """Load user database from JSON file."""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_database(self):
        """Save user database to JSON file."""
        with open(self.db_file, 'w') as f:
            json.dump(self.users, f, indent=2)
    
    def _send_welcome_email(self, email: str, username: str, first_name: str = '') -> bool:
        """Send welcome email to new user (optional feature)."""
        try:
            # Email configuration - set these environment variables to enable
            smtp_server = os.getenv('SMTP_SERVER', '')  # e.g., 'smtp.gmail.com'
            smtp_port = int(os.getenv('SMTP_PORT', '587'))
            smtp_username = os.getenv('SMTP_USERNAME', '')  # your email
            smtp_password = os.getenv('SMTP_PASSWORD', '')  # app password
            
            if not all([smtp_server, smtp_username, smtp_password]):
                # Email not configured - skip sending
                return False
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = smtp_username
            msg['To'] = email
            msg['Subject'] = 'Witaj w Trading Panel!'
            
            # Email body
            name = first_name if first_name else username
            body = f"""
            Cześć {name}!
            
            Dziękujemy za rejestrację w Trading Panel! 🎉
            
            Twoje konto zostało pomyślnie utworzone:
            • Nazwa użytkownika: {username}
            • Email: {email}
            • Data rejestracji: {datetime.now().strftime('%d.%m.%Y %H:%M')}
            
            Możesz teraz zalogować się i rozpocząć handel:
            http://185.70.196.214/login
            
            Zespół Trading Panel
            """
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # Send email
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
            server.quit()
            
            return True
            
        except Exception as e:
            print(f"Email sending failed: {e}")
            return False
    
    def _hash_password(self, password: str, salt: str = None) -> tuple:
        """Hash password with salt."""
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Use SHA-256 for password hashing
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return password_hash, salt
    
    def user_exists(self, username: str) -> bool:
        """Check if user exists."""
        if self.use_postgres:
            try:
                with self._get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM users WHERE username = %s", (username.lower(),))
                        return cur.fetchone() is not None
            except Exception:
                return False
        else:
            return username.lower() in self.users
    
    def email_exists(self, email: str) -> bool:
        """Check if email is already registered."""
        if self.use_postgres:
            try:
                with self._get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1 FROM users WHERE email = %s", (email.lower(),))
                        return cur.fetchone() is not None
            except Exception:
                return False
        else:
            for user_data in self.users.values():
                if user_data.get('email', '').lower() == email.lower():
                    return True
            return False
    
    def register_user(self, username: str, password: str, email: str, 
                     first_name: str = '', last_name: str = '', account_type: str = 'free') -> Dict[str, Any]:
        """Register a new user."""
        # Validate input
        if not username or not password or not email:
            return {'success': False, 'error': 'Missing required fields'}
        
        if len(username) < 3:
            return {'success': False, 'error': 'Username must be at least 3 characters'}
        
        # For OAuth users, skip password validation
        if not account_type.startswith('oauth_') and len(password) < 8:
            return {'success': False, 'error': 'Password must be at least 8 characters'}
        
        if '@' not in email or '.' not in email:
            return {'success': False, 'error': 'Invalid email address'}
        
        # Check if user already exists
        if self.user_exists(username):
            return {'success': False, 'error': 'Username already exists'}
        
        if self.email_exists(email):
            return {'success': False, 'error': 'Email already registered'}
        
        # Hash password
        password_hash, salt = self._hash_password(password)
        
        if self.use_postgres:
            try:
                with self._get_pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO users (username, email, password_hash, salt, first_name, last_name, account_type, settings)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                            username.lower(),
                            email.lower(),
                            password_hash,
                            salt,
                            first_name,
                            last_name,
                            account_type,
                            json.dumps({
                                'theme': 'light',
                                'notifications': True,
                                'two_factor': False
                            })
                        ))
                        conn.commit()
            except Exception as e:
                return {'success': False, 'error': f'Database error: {str(e)}'}
        else:
            # Create user record for JSON
            user_data = {
                'username': username.lower(),
                'password_hash': password_hash,
                'salt': salt,
                'email': email.lower(),
                'first_name': first_name,
                'last_name': last_name,
                'created_at': datetime.now().isoformat(),
                'last_login': None,
                'is_active': True,
                'account_type': account_type,
                'settings': {
                    'theme': 'light',
                    'notifications': True,
                    'two_factor': False
                }
            }
            
            # Save to database
            self.users[username.lower()] = user_data
            self._save_database()
        
        # Send welcome email (optional - requires SMTP configuration)
        email_sent = self._send_welcome_email(email, username, first_name)
        
        return {
            'success': True, 
            'message': 'User registered successfully',
            'email_sent': email_sent
        }
    
    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate user with username and password."""
        if not username or not password:
            return {'success': False, 'error': 'Missing credentials'}
        
        username = username.lower()
        
        if self.use_postgres:
            try:
                with self._get_pg_connection() as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                        cur.execute("""
                            SELECT username, email, password_hash, salt, first_name, last_name, 
                                   is_active, account_type, settings, created_at
                            FROM users WHERE username = %s
                        """, (username,))
                        user_data = cur.fetchone()
                        
                        if not user_data:
                            return {'success': False, 'error': 'Invalid username or password'}
                        
                        # Check if account is active
                        if not user_data['is_active']:
                            return {'success': False, 'error': 'Account is disabled'}
                        
                        # Verify password
                        password_hash, _ = self._hash_password(password, user_data['salt'])
                        
                        if password_hash != user_data['password_hash']:
                            return {'success': False, 'error': 'Invalid username or password'}
                        
                        # Update last login
                        cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = %s", (username,))
                        conn.commit()
                        
                        # Return user info (without sensitive data)
                        return {
                            'success': True,
                            'user': {
                                'username': user_data['username'],
                                'email': user_data['email'],
                                'first_name': user_data.get('first_name', ''),
                                'last_name': user_data.get('last_name', ''),
                                'account_type': user_data.get('account_type', 'free'),
                                'settings': user_data.get('settings', {}),
                                'created_at': user_data.get('created_at', '').isoformat() if user_data.get('created_at') else ''
                            }
                        }
            except Exception as e:
                return {'success': False, 'error': f'Database error: {str(e)}'}
        else:
            # Check if user exists
            if username not in self.users:
                return {'success': False, 'error': 'Invalid username or password'}
            
            user_data = self.users[username]
            
            # Check if account is active
            if not user_data.get('is_active', True):
                return {'success': False, 'error': 'Account is disabled'}
            
            # Verify password
            password_hash, _ = self._hash_password(password, user_data['salt'])
            
            if password_hash != user_data['password_hash']:
                return {'success': False, 'error': 'Invalid username or password'}
            
            # Update last login
            self.users[username]['last_login'] = datetime.now().isoformat()
            self._save_database()
            
            # Return user info (without sensitive data)
            return {
                'success': True,
                'user': {
                    'username': username,
                    'email': user_data['email'],
                    'first_name': user_data.get('first_name', ''),
                    'last_name': user_data.get('last_name', ''),
                'account_type': user_data.get('account_type', 'free'),
                'created_at': user_data['created_at']
            }
        }
    
    def get_user_info(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information (without sensitive data)."""
        username = username.lower()
        
        if username not in self.users:
            return None
        
        user_data = self.users[username]
        
        return {
            'username': username,
            'email': user_data['email'],
            'first_name': user_data.get('first_name', ''),
            'last_name': user_data.get('last_name', ''),
            'account_type': user_data.get('account_type', 'free'),
            'created_at': user_data['created_at'],
            'last_login': user_data.get('last_login'),
            'settings': user_data.get('settings', {})
        }
    
    def update_user_settings(self, username: str, settings: Dict[str, Any]) -> bool:
        """Update user settings."""
        username = username.lower()
        
        if username not in self.users:
            return False
        
        self.users[username]['settings'].update(settings)
        self._save_database()
        return True
    
    def change_password(self, username: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """Change user password."""
        # First authenticate with old password
        auth_result = self.authenticate_user(username, old_password)
        
        if not auth_result['success']:
            return {'success': False, 'error': 'Invalid current password'}
        
        if len(new_password) < 8:
            return {'success': False, 'error': 'New password must be at least 8 characters'}
        
        # Hash new password
        password_hash, salt = self._hash_password(new_password)
        
        # Update password
        username = username.lower()
        self.users[username]['password_hash'] = password_hash
        self.users[username]['salt'] = salt
        self._save_database()
        
        return {'success': True, 'message': 'Password changed successfully'}
    
    def delete_user(self, username: str) -> bool:
        """Delete user account."""
        username = username.lower()
        
        if username in self.users:
            del self.users[username]
            self._save_database()
            return True
        
        return False
    
    def list_users(self) -> list:
        """List all usernames (for admin purposes)."""
        return list(self.users.keys())
    
    def get_user_stats(self) -> Dict[str, Any]:
        """Get user statistics."""
        total_users = len(self.users)
        active_users = sum(1 for u in self.users.values() if u.get('is_active', True))
        
        account_types = {}
        for user in self.users.values():
            acc_type = user.get('account_type', 'free')
            account_types[acc_type] = account_types.get(acc_type, 0) + 1
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': total_users - active_users,
            'account_types': account_types
        }


# Initialize default admin user if database is empty
if __name__ == "__main__":
    db = UserDatabase()
    
    # Create admin user if it doesn't exist
    if not db.user_exists('admin'):
        result = db.register_user(
            username='admin',
            password='password',
            email='admin@tradingbot.com',
            first_name='Admin',
            last_name='User'
        )
        print("Admin user created:", result)
    
    # Print stats
    print("User statistics:", db.get_user_stats())

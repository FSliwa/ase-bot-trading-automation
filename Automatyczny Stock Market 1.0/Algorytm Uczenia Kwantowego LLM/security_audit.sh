#!/bin/bash

# === ASE TRADING BOT SECURITY AUDIT SCRIPT ===
# Comprehensive security scan for API keys, passwords, and sensitive data
# Created: 2025-01-25T12:00:00Z

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_header() { echo -e "${BLUE}=== $1 ===${NC}"; }
print_success() { echo -e "${GREEN}✅ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠️  $1${NC}"; }
print_error() { echo -e "${RED}❌ $1${NC}"; }
print_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(realpath "$SCRIPT_DIR")"

print_header "ASE Trading Bot Security Audit"
print_info "Scanning directory: $PROJECT_ROOT"
echo

# === 1. COMPROMISED API KEYS ===
print_header "1. Scanning for Compromised API Keys"

# Known compromised Gemini API key
COMPROMISED_GEMINI="AIzaSyCcaYs9xm69_sWRrDDNEjN-9BjFDEgxxKM"
GEMINI_MATCHES=$(grep -r "$COMPROMISED_GEMINI" "$PROJECT_ROOT" --exclude-dir=.git --exclude-dir=node_modules 2>/dev/null | wc -l || echo "0")

if [ "$GEMINI_MATCHES" -gt "0" ]; then
    print_error "Found $GEMINI_MATCHES instances of compromised Gemini API key!"
    print_info "Showing locations:"
    grep -r "$COMPROMISED_GEMINI" "$PROJECT_ROOT" --exclude-dir=.git --exclude-dir=node_modules 2>/dev/null | head -10
    echo
else
    print_success "No compromised Gemini API keys found"
fi

# === 2. WEAK PASSWORDS AND SECRETS ===
print_header "2. Scanning for Weak Passwords and Hardcoded Secrets"

# Common weak patterns
declare -a WEAK_PATTERNS=(
    "password.*=.*123"
    "password.*=.*password"
    "secret.*=.*secret"
    "token.*=.*token"
    "pass.*=.*admin"
    "MIlik112"  # Found in deploy scripts
    "1LFd5OzPs9TIdqsNpBYjY576Nt20HHSs"  # PostgreSQL password
    "c5b496d5462d4c092121f62c642781e35d5e8b4c90d6df786cfa5782fcf312f5"  # JWT secret
)

WEAK_COUNT=0
for pattern in "${WEAK_PATTERNS[@]}"; do
    matches=$(grep -ri "$pattern" "$PROJECT_ROOT" --exclude-dir=.git --exclude-dir=node_modules --exclude="*.log" 2>/dev/null | wc -l || echo "0")
    if [ "$matches" -gt "0" ]; then
        print_error "Found $matches instances of weak pattern: $pattern"
        WEAK_COUNT=$((WEAK_COUNT + matches))
    fi
done

if [ "$WEAK_COUNT" -eq "0" ]; then
    print_success "No obvious weak passwords found"
else
    print_warning "Total weak patterns found: $WEAK_COUNT"
fi

# === 3. EXPOSED API KEYS PATTERNS ===
print_header "3. Scanning for Exposed API Key Patterns"

# API key patterns
declare -a API_PATTERNS=(
    "sk-[a-zA-Z0-9]{32,}"        # OpenAI API keys
    "AIza[a-zA-Z0-9]{35}"        # Google API keys
    "xoxb-[0-9]{12}-[0-9]{12}-[a-zA-Z0-9]{24}"  # Slack bot tokens
    "ghp_[a-zA-Z0-9]{36}"        # GitHub personal access tokens
    "glpat-[a-zA-Z0-9]{20}"      # GitLab personal access tokens
)

API_KEY_COUNT=0
for pattern in "${API_PATTERNS[@]}"; do
    matches=$(grep -rE "$pattern" "$PROJECT_ROOT" --exclude-dir=.git --exclude-dir=node_modules --exclude="*.log" 2>/dev/null | wc -l || echo "0")
    if [ "$matches" -gt "0" ]; then
        print_warning "Found $matches potential API keys matching pattern: $pattern"
        API_KEY_COUNT=$((API_KEY_COUNT + matches))
    fi
done

if [ "$API_KEY_COUNT" -eq "0" ]; then
    print_success "No exposed API key patterns found"
else
    print_warning "Total potential API keys found: $API_KEY_COUNT"
fi

# === 4. INSECURE FILE PERMISSIONS ===
print_header "4. Checking File Permissions"

# Check for files that should have restricted permissions
declare -a SENSITIVE_FILES=(
    ".env"
    "*.key"
    "*.pem"
    "*password*"
    "*secret*"
    "config.*"
)

PERMISSION_ISSUES=0
for pattern in "${SENSITIVE_FILES[@]}"; do
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            perms=$(stat -c "%a" "$file" 2>/dev/null || echo "000")
            if [ "$perms" != "600" ] && [ "$perms" != "400" ]; then
                print_warning "File $file has permissions $perms (should be 600 or 400)"
                PERMISSION_ISSUES=$((PERMISSION_ISSUES + 1))
            fi
        fi
    done < <(find "$PROJECT_ROOT" -name "$pattern" -type f -print0 2>/dev/null)
done

if [ "$PERMISSION_ISSUES" -eq "0" ]; then
    print_success "File permissions look secure"
else
    print_warning "Found $PERMISSION_ISSUES files with potentially insecure permissions"
fi

# === 5. CONFIGURATION FILES ANALYSIS ===
print_header "5. Analyzing Configuration Files"

# Find all config files
CONFIG_FILES=$(find "$PROJECT_ROOT" -name "*.env*" -o -name "config.*" -o -name "*.conf" -o -name "*.yml" -o -name "*.yaml" 2>/dev/null | grep -v node_modules | grep -v .git || echo "")

if [ -z "$CONFIG_FILES" ]; then
    print_warning "No configuration files found"
else
    print_info "Found configuration files:"
    echo "$CONFIG_FILES" | while read -r file; do
        if [ -f "$file" ]; then
            echo "  📄 $file"
            # Check if file contains any secrets
            if grep -qi "key\|secret\|password\|token" "$file" 2>/dev/null; then
                print_warning "    Contains sensitive data"
            fi
        fi
    done
fi

# === 6. DATABASE CREDENTIALS ===
print_header "6. Checking Database Credentials"

DB_ISSUES=0
# Look for database connection strings
DB_PATTERNS=(
    "postgresql://.*:.*@"
    "mysql://.*:.*@"
    "mongodb://.*:.*@"
    "redis://.*:.*@"
    "POSTGRES_PASSWORD="
    "MYSQL_PASSWORD="
    "DB_PASSWORD="
)

for pattern in "${DB_PATTERNS[@]}"; do
    matches=$(grep -ri "$pattern" "$PROJECT_ROOT" --exclude-dir=.git --exclude-dir=node_modules 2>/dev/null | wc -l || echo "0")
    if [ "$matches" -gt "0" ]; then
        print_warning "Found $matches database credential references"
        DB_ISSUES=$((DB_ISSUES + matches))
    fi
done

if [ "$DB_ISSUES" -eq "0" ]; then
    print_success "No hardcoded database credentials found"
else
    print_warning "Total database credential references: $DB_ISSUES"
fi

# === 7. DOCKER AND COMPOSE SECURITY ===
print_header "7. Docker Security Check"

DOCKER_FILES=$(find "$PROJECT_ROOT" -name "Dockerfile*" -o -name "docker-compose*.yml" -o -name "docker-compose*.yaml" 2>/dev/null || echo "")

if [ -n "$DOCKER_FILES" ]; then
    print_info "Found Docker files:"
    echo "$DOCKER_FILES" | while read -r file; do
        if [ -f "$file" ]; then
            echo "  🐳 $file"
            
            # Check for common security issues in Docker files
            if grep -qi "ADD.*http" "$file" 2>/dev/null; then
                print_warning "    Uses ADD with URL (potential security risk)"
            fi
            
            if grep -qi "USER.*root\|--user.*root" "$file" 2>/dev/null; then
                print_warning "    Runs as root user"
            fi
            
            if grep -qi "password.*=" "$file" 2>/dev/null; then
                print_warning "    Contains password references"
            fi
        fi
    done
else
    print_info "No Docker files found"
fi

# === 8. SSL/TLS CERTIFICATES ===
print_header "8. SSL/TLS Certificate Check"

CERT_FILES=$(find "$PROJECT_ROOT" -name "*.crt" -o -name "*.cert" -o -name "*.pem" -o -name "*.key" 2>/dev/null | grep -v node_modules | grep -v .git || echo "")

if [ -n "$CERT_FILES" ]; then
    print_info "Found certificate files:"
    echo "$CERT_FILES" | while read -r file; do
        if [ -f "$file" ]; then
            echo "  🔐 $file"
            
            # Check certificate expiry (for .crt and .pem files)
            if [[ "$file" =~ \.(crt|pem)$ ]] && command -v openssl &> /dev/null; then
                expiry=$(openssl x509 -in "$file" -noout -enddate 2>/dev/null | cut -d= -f2 || echo "Unknown")
                if [ "$expiry" != "Unknown" ]; then
                    print_info "    Expires: $expiry"
                fi
            fi
            
            # Check file permissions
            perms=$(stat -c "%a" "$file" 2>/dev/null || echo "000")
            if [ "$perms" != "600" ] && [ "$perms" != "400" ]; then
                print_warning "    Insecure permissions: $perms"
            fi
        fi
    done
else
    print_info "No certificate files found"
fi

# === 9. BACKUP AND LOG ANALYSIS ===
print_header "9. Backup and Log File Security"

# Check for potentially sensitive backup files
BACKUP_PATTERNS=(
    "*.bak"
    "*.backup"
    "*.sql"
    "*.dump"
    "backup*"
)

BACKUP_COUNT=0
for pattern in "${BACKUP_PATTERNS[@]}"; do
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            echo "  📦 $file"
            BACKUP_COUNT=$((BACKUP_COUNT + 1))
            
            # Check if backup contains sensitive data
            if grep -qi "password\|secret\|key\|token" "$file" 2>/dev/null; then
                print_warning "    May contain sensitive data"
            fi
        fi
    done < <(find "$PROJECT_ROOT" -name "$pattern" -type f -print0 2>/dev/null)
done

if [ "$BACKUP_COUNT" -eq "0" ]; then
    print_info "No backup files found"
else
    print_info "Found $BACKUP_COUNT backup files"
fi

# === 10. GENERATE SECURITY REPORT ===
print_header "10. Security Report Summary"

REPORT_FILE="$PROJECT_ROOT/SECURITY_AUDIT_REPORT_$(date +%Y%m%d_%H%M%S).md"

cat > "$REPORT_FILE" << EOF
# ASE Trading Bot Security Audit Report

**Generated:** $(date)  
**Audited Directory:** $PROJECT_ROOT  
**Audit Script Version:** 1.0  

## Executive Summary

This security audit identified several areas of concern that require immediate attention:

## Critical Issues

$(if [ "$GEMINI_MATCHES" -gt "0" ]; then echo "- 🔴 **CRITICAL**: Found $GEMINI_MATCHES instances of compromised Gemini API key"; fi)
$(if [ "$WEAK_COUNT" -gt "0" ]; then echo "- 🟡 **HIGH**: Found $WEAK_COUNT instances of weak passwords/secrets"; fi)
$(if [ "$API_KEY_COUNT" -gt "0" ]; then echo "- 🟡 **HIGH**: Found $API_KEY_COUNT potential exposed API keys"; fi)

## Medium Priority Issues

$(if [ "$PERMISSION_ISSUES" -gt "0" ]; then echo "- 🟡 **MEDIUM**: $PERMISSION_ISSUES files with insecure permissions"; fi)
$(if [ "$DB_ISSUES" -gt "0" ]; then echo "- 🟡 **MEDIUM**: $DB_ISSUES database credential references"; fi)

## Recommendations

### Immediate Actions Required

1. **Replace Compromised API Keys**
   - Generate new Gemini API key
   - Update all configuration files
   - Rotate all other API keys as precaution

2. **Strengthen Authentication**
   - Replace all hardcoded passwords with environment variables
   - Implement proper secret management
   - Use strong, unique passwords for all services

3. **Secure File Permissions**
   - Set restrictive permissions (600) on all .env and key files
   - Ensure configuration files are not world-readable

4. **Database Security**
   - Use connection pooling with encrypted connections
   - Implement database credential rotation
   - Enable database audit logging

### Long-term Security Improvements

1. **Implement Secret Management**
   - Use tools like HashiCorp Vault or AWS Secrets Manager
   - Implement automatic secret rotation
   - Add secret scanning to CI/CD pipeline

2. **Enhanced Monitoring**
   - Implement security event logging
   - Set up intrusion detection
   - Monitor for API key usage patterns

3. **Access Controls**
   - Implement principle of least privilege
   - Regular access reviews
   - Multi-factor authentication for all admin access

## Security Checklist

- [ ] Replace compromised Gemini API key
- [ ] Update all hardcoded passwords
- [ ] Fix file permissions on sensitive files
- [ ] Implement proper .env file structure
- [ ] Set up secret management system
- [ ] Enable database connection encryption
- [ ] Implement API rate limiting
- [ ] Set up security monitoring
- [ ] Regular security audits scheduled
- [ ] Incident response plan created

## Files Requiring Immediate Attention

$(if [ "$GEMINI_MATCHES" -gt "0" ]; then
    echo "### Files with Compromised API Keys"
    grep -r "$COMPROMISED_GEMINI" "$PROJECT_ROOT" --exclude-dir=.git --exclude-dir=node_modules 2>/dev/null | head -10 | sed 's/^/- /'
fi)

---

**Next Audit Scheduled:** $(date -d "+1 month" +%Y-%m-%d)  
**Auditor:** ASE Security Team  
EOF

print_success "Security audit completed!"
print_info "Report saved to: $REPORT_FILE"

# === SUMMARY ===
echo
print_header "AUDIT SUMMARY"
echo "🔍 Compromised API Keys: $GEMINI_MATCHES"
echo "🔑 Weak Passwords/Secrets: $WEAK_COUNT"
echo "🗝️  Potential API Keys: $API_KEY_COUNT"
echo "📁 File Permission Issues: $PERMISSION_ISSUES"
echo "💾 Database Credential Issues: $DB_ISSUES"
echo "📦 Backup Files Found: $BACKUP_COUNT"

echo
if [ "$GEMINI_MATCHES" -gt "0" ] || [ "$WEAK_COUNT" -gt "5" ] || [ "$API_KEY_COUNT" -gt "3" ]; then
    print_error "🚨 CRITICAL SECURITY ISSUES FOUND - IMMEDIATE ACTION REQUIRED"
    exit 1
elif [ "$PERMISSION_ISSUES" -gt "0" ] || [ "$DB_ISSUES" -gt "0" ]; then
    print_warning "⚠️  SECURITY IMPROVEMENTS RECOMMENDED"
    exit 0
else
    print_success "✅ SECURITY AUDIT PASSED - NO CRITICAL ISSUES FOUND"
    exit 0
fi

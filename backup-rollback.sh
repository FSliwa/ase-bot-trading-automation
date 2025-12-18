#!/bin/bash

################################################################################
# ASE-Bot Backup and Rollback System
# Kompleksowy system tworzenia kopii zapasowych i przywracania poprzednich wersji
# Wersja: 1.0
################################################################################

set -euo pipefail

# === KONFIGURACJA ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_VERSION="1.0"

# Ścieżki
DEPLOY_DIR="/home/admin/trading-platform"
BACKUP_ROOT="/home/admin/backups"
LOG_DIR="/var/log/asebot-backup"

# Konfiguracja backupów
MAX_BACKUPS=10  # Maksymalna liczba backupów do przechowywania
BACKUP_COMPRESSION=true  # Czy kompresować backupy
BACKUP_ENCRYPTION=false  # Czy szyfrować backupy (wymaga gpg)

# Remote backup (opcjonalnie)
REMOTE_BACKUP_ENABLED=false
REMOTE_BACKUP_HOST=""
REMOTE_BACKUP_USER=""
REMOTE_BACKUP_PATH=""

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# === FUNKCJE POMOCNICZE ===

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")  echo -e "${GREEN}[INFO]${NC}  [$timestamp] $message" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC}  [$timestamp] $message" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} [$timestamp] $message" ;;
        "DEBUG") echo -e "${BLUE}[DEBUG]${NC} [$timestamp] $message" ;;
        *)       echo -e "[$timestamp] $message" ;;
    esac
    
    # Zapisz do pliku loga
    mkdir -p "$LOG_DIR"
    echo "[$level] [$timestamp] $message" >> "$LOG_DIR/backup-$(date +%Y%m%d).log"
}

# Oblicz rozmiar katalogu/pliku
get_size() {
    local path=$1
    if [[ -d "$path" ]]; then
        du -sb "$path" 2>/dev/null | awk '{print $1}' || echo "0"
    elif [[ -f "$path" ]]; then
        stat -c%s "$path" 2>/dev/null || echo "0"
    else
        echo "0"
    fi
}

# Format human-readable rozmiaru
human_size() {
    local bytes=$1
    if [[ $bytes -gt 1073741824 ]]; then
        echo "$(( bytes / 1073741824 ))GB"
    elif [[ $bytes -gt 1048576 ]]; then
        echo "$(( bytes / 1048576 ))MB"
    else
        echo "$(( bytes / 1024 ))KB"
    fi
}

# Sprawdź dostępne miejsce
check_space() {
    local required_bytes=$1
    local target_dir=$2
    
    local available_bytes
    available_bytes=$(df "$target_dir" --output=avail | tail -1)
    available_bytes=$((available_bytes * 1024))  # Konwertuj z KB na bajty
    
    if [[ $available_bytes -gt $required_bytes ]]; then
        log "INFO" "Dostępne miejsce: $(human_size $available_bytes), wymagane: $(human_size $required_bytes) ✓"
        return 0
    else
        log "ERROR" "Za mało miejsca! Dostępne: $(human_size $available_bytes), wymagane: $(human_size $required_bytes)"
        return 1
    fi
}

# Generuj unikatową nazwę backupu
generate_backup_name() {
    local backup_type=${1:-"manual"}
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    echo "${backup_type}-backup-${timestamp}"
}

# Sprawdź integralność backupu
verify_backup_integrity() {
    local backup_path=$1
    
    log "INFO" "Sprawdzanie integralności backupu: $(basename "$backup_path")"
    
    # Sprawdź czy backup istnieje
    if [[ ! -e "$backup_path" ]]; then
        log "ERROR" "Backup nie istnieje: $backup_path"
        return 1
    fi
    
    # Dla archiwów tar, sprawdź integralność
    if [[ "$backup_path" == *.tar.gz ]]; then
        if tar -tzf "$backup_path" >/dev/null 2>&1; then
            log "INFO" "✅ Archiwum tar.gz jest prawidłowe"
        else
            log "ERROR" "❌ Archiwum tar.gz jest uszkodzone"
            return 1
        fi
    fi
    
    # Sprawdź podstawowe informacje
    local backup_size
    backup_size=$(get_size "$backup_path")
    
    if [[ $backup_size -gt 0 ]]; then
        log "INFO" "✅ Rozmiar backupu: $(human_size $backup_size)"
    else
        log "ERROR" "❌ Backup jest pusty lub uszkodzony"
        return 1
    fi
    
    # Sprawdź checksum jeśli istnieje
    local checksum_file="${backup_path}.sha256"
    if [[ -f "$checksum_file" ]]; then
        if sha256sum -c "$checksum_file" >/dev/null 2>&1; then
            log "INFO" "✅ Checksum SHA256 poprawny"
        else
            log "ERROR" "❌ Checksum SHA256 niepoprawny"
            return 1
        fi
    fi
    
    return 0
}

# === FUNKCJE BACKUP ===

backup_application_code() {
    local backup_name=$1
    local backup_dir="$BACKUP_ROOT/$backup_name"
    
    log "INFO" "📁 Tworzenie kopii zapasowej kodu aplikacji..."
    
    # Sprawdź czy katalog źródłowy istnieje
    if [[ ! -d "$DEPLOY_DIR" ]]; then
        log "ERROR" "Katalog aplikacji nie istnieje: $DEPLOY_DIR"
        return 1
    fi
    
    local source_size
    source_size=$(get_size "$DEPLOY_DIR")
    
    # Sprawdź miejsce
    if ! check_space $((source_size * 2)) "$BACKUP_ROOT"; then
        return 1
    fi
    
    # Utwórz katalog backupu
    mkdir -p "$backup_dir/code"
    
    # Lista plików/katalogów do backupu
    local include_patterns=(
        "*.py"
        "*.js"
        "*.html"
        "*.css"
        "*.json"
        "*.txt"
        "*.md"
        "*.conf"
        "*.ini"
        "frontend/"
        "templates/"
        "static/"
        "logs/"
        "requirements.txt"
        "package.json"
        "nginx_fix.conf"
    )
    
    # Wzorce wykluczeń
    local exclude_patterns=(
        "__pycache__"
        "*.pyc"
        "node_modules/"
        ".git/"
        "venv/"
        "env/"
        "*.log"
        "*.tmp"
        "nohup.out"
    )
    
    # Stwórz rsync command z filtami
    local rsync_cmd="rsync -av --progress"
    
    # Dodaj wykluczenia
    for pattern in "${exclude_patterns[@]}"; do
        rsync_cmd="$rsync_cmd --exclude=$pattern"
    done
    
    # Wykonaj backup
    log "INFO" "Kopiowanie plików aplikacji..."
    if eval "$rsync_cmd $DEPLOY_DIR/ $backup_dir/code/"; then
        log "INFO" "✅ Kod aplikacji skopiowany"
        
        # Sprawdź rozmiar backupu
        local backup_size
        backup_size=$(get_size "$backup_dir/code")
        log "INFO" "Rozmiar backupu kodu: $(human_size $backup_size)"
        
        return 0
    else
        log "ERROR" "❌ Błąd podczas kopiowania kodu aplikacji"
        return 1
    fi
}

backup_database() {
    local backup_name=$1
    local backup_dir="$BACKUP_ROOT/$backup_name"
    
    log "INFO" "🗄️ Tworzenie kopii zapasowej bazy danych..."
    
    mkdir -p "$backup_dir/database"
    
    # Backup SQLite database
    local db_file="$DEPLOY_DIR/trading.db"
    if [[ -f "$db_file" ]]; then
        log "INFO" "Kopiowanie bazy SQLite..."
        if cp "$db_file" "$backup_dir/database/trading.db"; then
            # Sprawdź integralność bazy
            if sqlite3 "$backup_dir/database/trading.db" "PRAGMA integrity_check;" | grep -q "ok"; then
                log "INFO" "✅ Baza SQLite skopiowana i zweryfikowana"
            else
                log "WARN" "⚠️ Baza SQLite skopiowana, ale może być uszkodzona"
            fi
            
            # Utwórz dump SQL jako dodatkowy backup
            log "INFO" "Tworzenie dumpu SQL..."
            if sqlite3 "$db_file" ".dump" > "$backup_dir/database/trading_dump.sql"; then
                log "INFO" "✅ Dump SQL utworzony"
            else
                log "WARN" "⚠️ Nie udało się utworzyć dumpu SQL"
            fi
        else
            log "ERROR" "❌ Nie udało się skopiować bazy SQLite"
            return 1
        fi
    else
        log "INFO" "ℹ️ Baza danych nie istnieje - pomijanie"
    fi
    
    # Backup innych plików danych
    local data_files=(
        "*.csv"
        "*.json" 
        "*.log"
    )
    
    for pattern in "${data_files[@]}"; do
        find "$DEPLOY_DIR" -name "$pattern" -type f 2>/dev/null | while read -r file; do
            local rel_path
            rel_path=$(realpath --relative-to="$DEPLOY_DIR" "$file")
            local target_dir
            target_dir="$backup_dir/database/$(dirname "$rel_path")"
            mkdir -p "$target_dir"
            cp "$file" "$target_dir/"
        done
    done
    
    return 0
}

backup_configuration() {
    local backup_name=$1
    local backup_dir="$BACKUP_ROOT/$backup_name"
    
    log "INFO" "⚙️ Tworzenie kopii zapasowej konfiguracji..."
    
    mkdir -p "$backup_dir/config"
    
    # Konfiguracja aplikacji
    local app_configs=(
        "$DEPLOY_DIR/.env"
        "$DEPLOY_DIR/config.py"
        "$DEPLOY_DIR/settings.py"
        "$DEPLOY_DIR/*.conf"
        "$DEPLOY_DIR/*.ini"
        "$DEPLOY_DIR/nginx_fix.conf"
    )
    
    for config_pattern in "${app_configs[@]}"; do
        find "$DEPLOY_DIR" -name "$(basename "$config_pattern")" -type f 2>/dev/null | while read -r file; do
            if [[ -f "$file" ]]; then
                cp "$file" "$backup_dir/config/"
                log "DEBUG" "Skopiowano konfigurację: $(basename "$file")"
            fi
        done
    done
    
    # Konfiguracja systemowa (jeśli dostępna)
    local system_configs=(
        "/etc/nginx/sites-available/ase-bot.live"
        "/etc/systemd/system/asebot*.service"
        "/etc/crontab"
    )
    
    for config in "${system_configs[@]}"; do
        if [[ -f "$config" ]]; then
            local config_name
            config_name=$(basename "$config")
            if sudo cp "$config" "$backup_dir/config/system_${config_name}" 2>/dev/null; then
                log "DEBUG" "Skopiowano konfigurację systemową: $config_name"
            fi
        fi
    done
    
    # Zapisz informacje o systemie
    cat > "$backup_dir/config/system_info.txt" << EOF
Backup created: $(date)
Hostname: $(hostname)
OS: $(lsb_release -d 2>/dev/null | cut -f2- || uname -a)
User: $(whoami)
Python version: $(python3 --version 2>&1)
Node version: $(node --version 2>/dev/null || echo "Not installed")
Running processes:
$(ps aux | grep -E "(python|node|nginx)" | head -20)

Network configuration:
$(ip addr show | grep -E "(inet |UP)" | head -10)
EOF
    
    log "INFO" "✅ Konfiguracja zbackupowana"
    return 0
}

backup_logs() {
    local backup_name=$1
    local backup_dir="$BACKUP_ROOT/$backup_name"
    
    log "INFO" "📋 Tworzenie kopii zapasowej logów..."
    
    mkdir -p "$backup_dir/logs"
    
    # Backup logów aplikacji
    local log_sources=(
        "$DEPLOY_DIR/logs/"
        "$LOG_DIR/"
        "/var/log/nginx/"
        "/var/log/syslog"
    )
    
    for log_source in "${log_sources[@]}"; do
        if [[ -e "$log_source" ]]; then
            local source_name
            source_name=$(basename "$log_source")
            
            if [[ -d "$log_source" ]]; then
                mkdir -p "$backup_dir/logs/$source_name"
                # Kopiuj tylko ostatnie logi (ostatnie 7 dni)
                find "$log_source" -name "*.log" -mtime -7 -type f 2>/dev/null | while read -r logfile; do
                    cp "$logfile" "$backup_dir/logs/$source_name/" 2>/dev/null || true
                done
            elif [[ -f "$log_source" ]]; then
                cp "$log_source" "$backup_dir/logs/" 2>/dev/null || true
            fi
        fi
    done
    
    log "INFO" "✅ Logi zbackupowane"
    return 0
}

create_full_backup() {
    local backup_type=${1:-"manual"}
    local backup_name
    backup_name=$(generate_backup_name "$backup_type")
    
    log "INFO" "🎯 Rozpoczynanie pełnego backupu: $backup_name"
    
    local backup_dir="$BACKUP_ROOT/$backup_name"
    
    # Utwórz główny katalog backupu
    if ! mkdir -p "$backup_dir"; then
        log "ERROR" "Nie można utworzyć katalogu backupu: $backup_dir"
        return 1
    fi
    
    # Zapisz metadane backupu
    cat > "$backup_dir/backup_metadata.json" << EOF
{
    "backup_name": "$backup_name",
    "backup_type": "$backup_type",
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "hostname": "$(hostname)",
    "user": "$(whoami)",
    "script_version": "$BACKUP_VERSION",
    "deploy_dir": "$DEPLOY_DIR"
}
EOF
    
    # Wykonaj poszczególne komponenty backupu
    local backup_steps=(
        "backup_application_code:Kod aplikacji"
        "backup_database:Baza danych"  
        "backup_configuration:Konfiguracja"
        "backup_logs:Logi"
    )
    
    local failed_steps=()
    
    for step_def in "${backup_steps[@]}"; do
        local step_function="${step_def%%:*}"
        local step_description="${step_def##*:}"
        
        log "INFO" "📦 $step_description..."
        
        if $step_function "$backup_name"; then
            log "INFO" "✅ $step_description - zakończono"
        else
            log "WARN" "⚠️ $step_description - błąd"
            failed_steps+=("$step_description")
        fi
    done
    
    # Kompresja (jeśli włączona)
    if [[ "$BACKUP_COMPRESSION" == true ]]; then
        log "INFO" "🗜️ Kompresowanie backupu..."
        local archive_path="$backup_dir.tar.gz"
        
        if tar -czf "$archive_path" -C "$BACKUP_ROOT" "$(basename "$backup_dir")"; then
            # Usuń nieskompresowany katalog
            rm -rf "$backup_dir"
            backup_dir="$archive_path"
            log "INFO" "✅ Backup skompresowany: $(basename "$archive_path")"
        else
            log "WARN" "⚠️ Kompresja nie powiodła się, zachowuję nieskompresowany backup"
        fi
    fi
    
    # Wygeneruj checksum
    log "INFO" "🔐 Generowanie checksum..."
    if sha256sum "$backup_dir" > "${backup_dir}.sha256"; then
        log "INFO" "✅ Checksum SHA256 wygenerowany"
    fi
    
    # Weryfikacja integralności
    if verify_backup_integrity "$backup_dir"; then
        log "INFO" "✅ Integralność backupu potwierdzona"
    else
        log "WARN" "⚠️ Problemy z integralnością backupu"
    fi
    
    # Podsumowanie
    local backup_size
    backup_size=$(get_size "$backup_dir")
    
    log "INFO" "📊 PODSUMOWANIE BACKUPU"
    log "INFO" "====================="
    log "INFO" "Nazwa: $backup_name"
    log "INFO" "Ścieżka: $backup_dir"
    log "INFO" "Rozmiar: $(human_size $backup_size)"
    log "INFO" "Status: $([ ${#failed_steps[@]} -eq 0 ] && echo "✅ Sukces" || echo "⚠️ Częściowy sukces")"
    
    if [[ ${#failed_steps[@]} -gt 0 ]]; then
        log "WARN" "Błędy w: ${failed_steps[*]}"
    fi
    
    # Wyczyść stare backupy
    cleanup_old_backups
    
    echo "$backup_name"
    return 0
}

# === FUNKCJE ROLLBACK ===

list_available_backups() {
    log "INFO" "📋 Dostępne backupy:"
    
    if [[ ! -d "$BACKUP_ROOT" ]]; then
        log "INFO" "Brak katalogu backupów: $BACKUP_ROOT"
        return 1
    fi
    
    local backups=()
    
    # Znajdź wszystkie backupy (katalogi i archiwa)
    while IFS= read -r -d '' backup; do
        backups+=("$backup")
    done < <(find "$BACKUP_ROOT" -maxdepth 1 \( -type d -name "*backup*" -o -name "*backup*.tar.gz" \) -print0 | sort -z)
    
    if [[ ${#backups[@]} -eq 0 ]]; then
        log "INFO" "Brak dostępnych backupów"
        return 1
    fi
    
    local i=1
    for backup in "${backups[@]}"; do
        local backup_name
        backup_name=$(basename "$backup")
        local backup_size
        backup_size=$(get_size "$backup")
        local backup_date
        backup_date=$(stat -c %y "$backup" | cut -d' ' -f1)
        
        echo "[$i] $backup_name"
        echo "    Rozmiar: $(human_size $backup_size)"
        echo "    Data: $backup_date"
        echo "    Ścieżka: $backup"
        
        # Sprawdź metadane jeśli dostępne
        local metadata_file
        if [[ -f "${backup%%.tar.gz}/backup_metadata.json" ]]; then
            metadata_file="${backup%%.tar.gz}/backup_metadata.json"
        elif [[ -f "$backup/backup_metadata.json" ]]; then
            metadata_file="$backup/backup_metadata.json"
        fi
        
        if [[ -n "${metadata_file:-}" && -f "$metadata_file" ]]; then
            local backup_type
            backup_type=$(grep '"backup_type"' "$metadata_file" 2>/dev/null | cut -d'"' -f4 || echo "unknown")
            echo "    Typ: $backup_type"
        fi
        
        echo ""
        ((i++))
    done
    
    return 0
}

restore_from_backup() {
    local backup_name=$1
    local restore_target=${2:-"$DEPLOY_DIR"}
    
    log "INFO" "🔄 Rozpoczynanie przywracania z backupu: $backup_name"
    
    local backup_path
    backup_path=$(find "$BACKUP_ROOT" -name "$backup_name" -o -name "${backup_name}.tar.gz" | head -1)
    
    if [[ -z "$backup_path" ]]; then
        log "ERROR" "Nie znaleziono backupu: $backup_name"
        return 1
    fi
    
    # Weryfikuj backup przed przywróceniem
    if ! verify_backup_integrity "$backup_path"; then
        log "ERROR" "Backup jest uszkodzony, przerwanie operacji"
        return 1
    fi
    
    # Utwórz backup obecnego stanu przed rollbackiem
    log "INFO" "Tworzenie backupu przed rollbackiem..."
    local pre_rollback_backup
    pre_rollback_backup=$(create_full_backup "pre-rollback")
    
    # Zatrzymaj aplikację
    log "INFO" "Zatrzymywanie aplikacji..."
    pkill -f "python.*simple_test_api" || true
    pkill -f "python.*unified_working" || true
    sleep 3
    
    # Przygotuj katalog tymczasowy
    local temp_dir
    temp_dir=$(mktemp -d)
    
    # Rozpakuj backup jeśli skompresowany
    local source_dir="$backup_path"
    if [[ "$backup_path" == *.tar.gz ]]; then
        log "INFO" "Rozpakowywanie backupu..."
        if tar -xzf "$backup_path" -C "$temp_dir"; then
            source_dir="$temp_dir/$(basename "${backup_path%.tar.gz}")"
            log "INFO" "✅ Backup rozpakowany"
        else
            log "ERROR" "❌ Błąd rozpakowywania backupu"
            rm -rf "$temp_dir"
            return 1
        fi
    fi
    
    # Przywróć kod aplikacji
    if [[ -d "$source_dir/code" ]]; then
        log "INFO" "Przywracanie kodu aplikacji..."
        
        # Utwórz backup obecnego kodu
        if [[ -d "$restore_target" ]]; then
            mv "$restore_target" "${restore_target}.pre-rollback" || true
        fi
        
        # Przywróć kod
        if cp -r "$source_dir/code" "$restore_target"; then
            log "INFO" "✅ Kod aplikacji przywrócony"
        else
            log "ERROR" "❌ Błąd przywracania kodu"
            # Przywróć poprzedni stan
            if [[ -d "${restore_target}.pre-rollback" ]]; then
                mv "${restore_target}.pre-rollback" "$restore_target"
            fi
            rm -rf "$temp_dir"
            return 1
        fi
    fi
    
    # Przywróć bazę danych
    if [[ -d "$source_dir/database" ]]; then
        log "INFO" "Przywracanie bazy danych..."
        
        if [[ -f "$source_dir/database/trading.db" ]]; then
            cp "$source_dir/database/trading.db" "$restore_target/"
            log "INFO" "✅ Baza SQLite przywrócona"
        fi
    fi
    
    # Przywróć konfigurację
    if [[ -d "$source_dir/config" ]]; then
        log "INFO" "Przywracanie konfiguracji..."
        
        find "$source_dir/config" -name "*.conf" -o -name "*.ini" -o -name ".env" | while read -r config_file; do
            local config_name
            config_name=$(basename "$config_file")
            cp "$config_file" "$restore_target/" 2>/dev/null || true
        done
        
        log "INFO" "✅ Konfiguracja przywrócona"
    fi
    
    # Wyczyść katalog tymczasowy
    rm -rf "$temp_dir"
    
    log "INFO" "✅ Rollback zakończony pomyślnie"
    log "INFO" "Backup pre-rollback dostępny jako: $pre_rollback_backup"
    
    return 0
}

# === FUNKCJE ZARZĄDZANIA ===

cleanup_old_backups() {
    log "INFO" "🧹 Czyszczenie starych backupów..."
    
    if [[ ! -d "$BACKUP_ROOT" ]]; then
        return 0
    fi
    
    # Znajdź wszystkie backupy i posortuj po dacie (najstarsze pierwsze)
    local backups=()
    while IFS= read -r -d '' backup; do
        backups+=("$backup")
    done < <(find "$BACKUP_ROOT" -maxdepth 1 \( -type d -name "*backup*" -o -name "*backup*.tar.gz" \) -print0 | sort -z)
    
    local backup_count=${#backups[@]}
    
    if [[ $backup_count -le $MAX_BACKUPS ]]; then
        log "INFO" "Liczba backupów ($backup_count) w limicie ($MAX_BACKUPS)"
        return 0
    fi
    
    local to_remove=$((backup_count - MAX_BACKUPS))
    log "INFO" "Usuwanie $to_remove najstarszych backupów..."
    
    for ((i=0; i<to_remove; i++)); do
        local backup_to_remove="${backups[i]}"
        local backup_name
        backup_name=$(basename "$backup_to_remove")
        
        log "INFO" "Usuwanie: $backup_name"
        
        # Usuń backup i związane z nim pliki
        rm -rf "$backup_to_remove"
        rm -f "${backup_to_remove}.sha256"
        
        log "INFO" "✅ Usunięto: $backup_name"
    done
    
    log "INFO" "✅ Czyszczenie zakończone"
}

get_backup_info() {
    local backup_name=$1
    
    local backup_path
    backup_path=$(find "$BACKUP_ROOT" -name "$backup_name" -o -name "${backup_name}.tar.gz" | head -1)
    
    if [[ -z "$backup_path" ]]; then
        log "ERROR" "Nie znaleziono backupu: $backup_name"
        return 1
    fi
    
    log "INFO" "📊 Informacje o backupie: $backup_name"
    log "INFO" "=========================="
    
    local backup_size
    backup_size=$(get_size "$backup_path")
    log "INFO" "Rozmiar: $(human_size $backup_size)"
    
    local backup_date
    backup_date=$(stat -c %y "$backup_path")
    log "INFO" "Data utworzenia: $backup_date"
    
    # Sprawdź integralność
    if verify_backup_integrity "$backup_path" >/dev/null 2>&1; then
        log "INFO" "Integralność: ✅ OK"
    else
        log "INFO" "Integralność: ❌ Uszkodzony"
    fi
    
    # Pokaż metadane jeśli dostępne
    local metadata_file
    if [[ "$backup_path" == *.tar.gz ]]; then
        # Dla archiwów tar.gz, spróbuj wyciągnąć metadane
        if tar -tzf "$backup_path" | grep -q "backup_metadata.json"; then
            log "INFO" "Metadane:"
            tar -xzf "$backup_path" --to-stdout "$(tar -tzf "$backup_path" | grep backup_metadata.json | head -1)" | jq . 2>/dev/null || cat
        fi
    elif [[ -f "$backup_path/backup_metadata.json" ]]; then
        log "INFO" "Metadane:"
        cat "$backup_path/backup_metadata.json" | jq . 2>/dev/null || cat "$backup_path/backup_metadata.json"
    fi
    
    return 0
}

# === MAIN ===

show_help() {
    echo "ASE-Bot Backup and Rollback System v$BACKUP_VERSION"
    echo ""
    echo "Użycie:"
    echo "  $0 COMMAND [OPTIONS]"
    echo ""
    echo "Komendy:"
    echo "  backup [TYPE]              Utwórz backup (typ: manual|auto|pre-deploy)"
    echo "  list                       Lista dostępnych backupów"
    echo "  restore BACKUP_NAME        Przywróć z backupu"
    echo "  info BACKUP_NAME           Informacje o backupie"
    echo "  cleanup                    Wyczyść stare backupy"
    echo "  verify BACKUP_NAME         Sprawdź integralność backupu"
    echo ""
    echo "Przykłady:"
    echo "  $0 backup                  # Utwórz backup ręczny"
    echo "  $0 backup pre-deploy       # Backup przed deploymentem"
    echo "  $0 list                    # Pokaż dostępne backupy"
    echo "  $0 restore manual-backup-20250925_143022"
    echo "  $0 info manual-backup-20250925_143022"
    echo "  $0 cleanup                 # Usuń stare backupy"
    echo ""
}

main() {
    local command=${1:-"help"}
    
    case $command in
        "backup"|"b")
            local backup_type=${2:-"manual"}
            create_full_backup "$backup_type"
            ;;
        "list"|"l"|"ls")
            list_available_backups
            ;;
        "restore"|"r"|"rollback")
            local backup_name=$2
            if [[ -z "$backup_name" ]]; then
                log "ERROR" "Użycie: $0 restore <backup_name>"
                exit 1
            fi
            restore_from_backup "$backup_name"
            ;;
        "info"|"i")
            local backup_name=$2
            if [[ -z "$backup_name" ]]; then
                log "ERROR" "Użycie: $0 info <backup_name>"
                exit 1
            fi
            get_backup_info "$backup_name"
            ;;
        "cleanup"|"clean")
            cleanup_old_backups
            ;;
        "verify"|"v")
            local backup_name=$2
            if [[ -z "$backup_name" ]]; then
                log "ERROR" "Użycie: $0 verify <backup_name>"
                exit 1
            fi
            local backup_path
            backup_path=$(find "$BACKUP_ROOT" -name "$backup_name" -o -name "${backup_name}.tar.gz" | head -1)
            if [[ -n "$backup_path" ]]; then
                verify_backup_integrity "$backup_path"
            else
                log "ERROR" "Nie znaleziono backupu: $backup_name"
                exit 1
            fi
            ;;
        "help"|"h"|"-h"|"--help")
            show_help
            ;;
        *)
            log "ERROR" "Nieznana komenda: $command"
            show_help
            exit 1
            ;;
    esac
}

# Uruchom główną funkcję
main "$@"

# 🔑 WYMAGANA KONFIGURACJA SSH

## ⚠️ WAŻNE: PRZED DEPLOYMENT'EM

Twoje SSH klucze nie są jeszcze skonfigurowane na VPS. Musisz dodać klucz publiczny w panelu VPS.

## 📋 Kroki do wykonania:

### 1. Skopiuj klucz publiczny SSH:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJse5FI4ZPuXQvtL7eqqKvCEGPr2FgQzQRW1CfxjWasr f.sliwa@nowybankpolski.pl
```

### 2. Dodaj klucz w panelu VPS:
1. Zaloguj się do panelu VPS (DigitalOcean, Linode, itp.)
2. Przejdź do sekcji **SSH Keys** lub **Klucze SSH**
3. Kliknij **"Add SSH Key"** lub **"Dodaj Klucz SSH"**
4. Wklej powyższy klucz publiczny
5. Nadaj nazwę, np: "MacBook-Filip"
6. Zapisz klucz

### 3. Sprawdź połączenie SSH:
```bash
ssh root@185.70.196.214
```

**Oczekiwany fingerprint:** `SHA256:e5b7EB06IiR3BcLaBUm2fhDpptU5VXX3xf4h8cv56xI`

### 4. Uruchom automatyczny deployment:
```bash
./auto_deploy_with_ssh.sh
```

## 🔍 Status sprawdzenia SSH:
- ❌ SSH connection failed - wymagane hasło
- ⏳ Oczekiwanie na konfigurację klucza w panelu VPS
- 🎯 **NASTĘPNY KROK:** Dodaj klucz SSH do panelu VPS

## 📞 Potrzebujesz pomocy?
Jeśli masz problemy z dodaniem klucza SSH, sprawdź dokumentację swojego providera VPS:
- DigitalOcean: Settings → Security → SSH Keys
- Linode: Profile → SSH Keys
- Vultr: Account → SSH Keys

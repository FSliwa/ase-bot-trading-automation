# 📊 PARAMETRY DASHBOARDU - Pełny Podgląd Środków na Giełdzie

## 💰 Stan Konta (Account Overview)
| Parametr | Opis | Jednostka |
|----------|------|-----------|
| **Total Balance** | Całkowity bilans konta | USD/USDT |
| **Available Balance** | Dostępne środki do otwarcia nowych pozycji | USD/USDT |
| **Margin Used** | Wykorzystany depozyt zabezpieczający | USD/USDT |
| **Free Margin** | Wolny depozyt (available - margin used) | USD/USDT |
| **Margin Level %** | Poziom depozytu (equity/margin used * 100) | % |
| **Unrealized PnL** | Niezrealizowany zysk/strata z otwartych pozycji | USD/USDT |
| **Realized PnL (24h/7d/30d)** | Zrealizowane zyski/straty | USD/USDT |

## 📈 Otwarte Pozycje (Open Positions)
| Parametr | Opis | Przykład |
|----------|------|----------|
| **Symbol** | Para tradingowa | BTC/USDT |
| **Side** | Kierunek pozycji | LONG/SHORT |
| **Entry Price** | Cena wejścia | $45,230.50 |
| **Current Price** | Aktualna cena rynkowa | $45,550.00 |
| **Quantity** | Wielkość pozycji | 0.5 BTC |
| **Leverage** | Użyta dźwignia | 5x |
| **Margin** | Depozyt zabezpieczający | $4,523.05 |
| **Unrealized PnL** | Bieżący zysk/strata | +$159.75 |
| **PnL %** | Procentowy zysk/strata | +0.71% |
| **Stop Loss** | Poziom stop loss | $44,000.00 |
| **Take Profit** | Poziom take profit | $47,000.00 |
| **Liquidation Price** | Cena likwidacji | $36,184.40 |

## ⚠️ Metryki Ryzyka (Risk Metrics)
| Parametr | Opis | Zakres |
|----------|------|--------|
| **Daily Drawdown** | Dzienna strata | 0-100% |
| **Max Drawdown** | Maksymalne obsunięcie kapitału | 0-100% |
| **Risk of Ruin %** | Prawdopodobieństwo bankructwa | 0-100% |
| **Value at Risk (VaR)** | Wartość narażona na ryzyko | USD |
| **Total Exposure %** | Całkowita ekspozycja do kapitału | 0-300% |
| **Correlation Risk** | Ryzyko korelacji między pozycjami | Low/Med/High |
| **Circuit Breaker Status** | Status automatycznych wyłączników | Active/Inactive |

## 📊 Performance (Wyniki)
| Parametr | Opis | Format |
|----------|------|--------|
| **Win Rate %** | Procent wygranych transakcji | 0-100% |
| **Average Win** | Średni zysk | USD |
| **Average Loss** | Średnia strata | USD |
| **Profit Factor** | Stosunek zysków do strat | 0.0-∞ |
| **Sharpe Ratio** | Wskaźnik Sharpe'a | -3.0 - +3.0 |
| **ROI %** | Zwrot z inwestycji | % |
| **Total Trades** | Liczba transakcji | Liczba |

## 🤖 Status Bota (Bot Status)
| Parametr | Opis | Wartości |
|----------|------|----------|
| **Bot Status** | Stan bota | RUNNING/STOPPED/ERROR |
| **Uptime** | Czas działania | HH:MM:SS |
| **Last Activity** | Ostatnia aktywność | Timestamp |
| **Active Strategies** | Aktywne strategie | Lista |
| **API Status** | Status połączeń API | OK/ERROR |
| **Error Count** | Liczba błędów | Liczba |

## 🧠 Analiza AI (AI Analysis)
| Parametr | Opis | Przykład |
|----------|------|----------|
| **Market Regime** | Obecny reżim rynkowy | Trending/Ranging |
| **Top Picks** | Najlepsze wybory AI | BTC/USDT LONG |
| **Risk Assessment** | Ocena ryzyka | Low/Medium/High |
| **Market Sentiment** | Sentyment rynkowy | Bullish/Neutral/Bearish |
| **AI Confidence** | Pewność rekomendacji | 0-100% |

## ⚡ Szybkie Akcje (Quick Actions)
| Akcja | Opis | Efekt |
|-------|------|-------|
| **Emergency Stop** | Awaryjne zatrzymanie | Natychmiastowe zatrzymanie bota |
| **Close All Positions** | Zamknij wszystkie pozycje | Zamyka wszystkie otwarte pozycje |
| **Pause Trading** | Wstrzymaj handel | Tymczasowe wstrzymanie nowych transakcji |
| **Adjust Risk Limits** | Dostosuj limity ryzyka | Zmiana parametrów ryzyka |
| **Export Report** | Eksportuj raport | Pobiera CSV z historią |

## 📱 Aktualizacje w Czasie Rzeczywistym
- **Stan konta**: co 2 sekundy
- **Pozycje**: co 3 sekundy
- **Performance**: co 10 sekund
- **Analiza AI**: co 30 sekund
- **Alerty**: co 5 sekund

## 🔗 Dostęp do Dashboardu
- **URL**: http://localhost:8010
- **Uruchomienie samego dashboardu**: `./run_dashboard.sh`
- **Uruchomienie bota z dashboardem**: `./run_auto_bot.sh`

Dashboard zapewnia kompletny wgląd w:
- Rzeczywisty stan środków
- Ryzyko w czasie rzeczywistym
- Performance tradingu
- Decyzje AI
- Możliwość natychmiastowej interwencji
